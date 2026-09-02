"""Minimal Edge Read Aloud client with a configurable outputFormat.

Benchmark-only. Production synthesis stays in tools/ingest/audio_microsoft.py.
The stock edge-tts Communicate hard-codes audio-24khz-48kbitrate-mono-mp3 in its
speech.config frame and rejects any Content-Type other than audio/mpeg, so it
cannot answer the "does Edge return real PCM?" question on its own. This client
reuses edge-tts' DRM token, headers and SSML shape and changes only the format.
"""

from __future__ import annotations

import asyncio
import random
import ssl
import time
from pathlib import Path
from xml.sax.saxutils import escape

import aiohttp
import certifi
from edge_tts.communicate import connect_id, date_to_string, get_headers_and_data
from edge_tts.constants import SEC_MS_GEC_VERSION, WSS_HEADERS, WSS_URL
from edge_tts.drm import DRM

DEFAULT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"


class FormatRejected(RuntimeError):
    """The service refused the requested outputFormat."""


def ssml(text: str, voice: str, rate: str, pitch: str, volume: str) -> str:
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
        f"<voice name='{voice}'>"
        f"<prosody pitch='{pitch}' rate='{rate}' volume='{volume}'>"
        f"{escape(text)}"
        "</prosody></voice></speak>"
    )


async def synthesize_bytes(
    text: str,
    voice: str,
    output_format: str = DEFAULT_FORMAT,
    rate: str = "-5%",
    pitch: str = "+0Hz",
    volume: str = "+0%",
) -> tuple[bytes, str | None]:
    """Return (audio bytes, Content-Type reported by the service)."""
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    chunks: list[bytes] = []
    content_type: str | None = None
    async with aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=60)) as session:
        async with session.ws_connect(
            f"{WSS_URL}&ConnectionId={connect_id()}"
            f"&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
            f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}",
            compress=15,
            headers=DRM.headers_with_muid(WSS_HEADERS),
            ssl=ssl_ctx,
        ) as websocket:
            await websocket.send_str(
                f"X-Timestamp:{date_to_string()}\r\n"
                "Content-Type:application/json; charset=utf-8\r\n"
                "Path:speech.config\r\n\r\n"
                '{"context":{"synthesis":{"audio":{"metadataoptions":{'
                '"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"},'
                f'"outputFormat":"{output_format}"'
                "}}}}\r\n"
            )
            await websocket.send_str(
                f"X-RequestId:{connect_id()}\r\n"
                "Content-Type:application/ssml+xml\r\n"
                f"X-Timestamp:{date_to_string()}Z\r\n"
                "Path:ssml\r\n\r\n"
                f"{ssml(text, voice, rate, pitch, volume)}"
            )
            async for received in websocket:
                if received.type == aiohttp.WSMsgType.TEXT:
                    encoded = received.data.encode("utf-8")
                    parameters, _ = get_headers_and_data(encoded, encoded.find(b"\r\n\r\n"))
                    if parameters.get(b"Path") == b"turn.end":
                        break
                elif received.type == aiohttp.WSMsgType.BINARY:
                    header_length = int.from_bytes(received.data[:2], "big")
                    parameters, data = get_headers_and_data(received.data, header_length)
                    if parameters.get(b"Path") != b"audio":
                        continue
                    reported = parameters.get(b"Content-Type")
                    if reported is not None:
                        content_type = reported.decode()
                    if data:
                        chunks.append(data)
                elif received.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
    audio = b"".join(chunks)
    if not audio:
        raise FormatRejected(f"No audio returned for outputFormat={output_format!r}")
    return audio, content_type


def synthesize(
    text: str,
    voice: str,
    destination: Path,
    output_format: str = DEFAULT_FORMAT,
    rate: str = "-5%",
    retries: int = 4,
) -> str | None:
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            audio, content_type = asyncio.run(
                synthesize_bytes(text, voice, output_format=output_format, rate=rate)
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(audio)
            return content_type
        except Exception as error:  # noqa: BLE001 - retry every transport failure
            last = error
            destination.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(min(15, 2**attempt) + random.random())
    raise RuntimeError(f"synthesis failed for {text!r} / {voice} / {output_format}: {last}") from last
