from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def bundled_candidates(name: str) -> list[Path]:
    """Where an installed build keeps FFmpeg, in resolution order.

    The app ships ffmpeg.exe, ffprobe.exe and their DLLs in an `ffmpeg` folder
    beside the importer executable, so an installed Lexium never depends on the
    user's PATH. A flat layout is accepted too for local experiments.
    """
    if not getattr(sys, "frozen", False):
        return []
    beside = Path(sys.executable).resolve().parent
    return [beside / "ffmpeg" / f"{name}.exe", beside / f"{name}.exe"]


def find_binary(name: str) -> str:
    # Trusted packaged copy first, so an installed app is deterministic.
    for candidate in bundled_candidates(name):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    matches = list(winget.glob(f"Gyan.FFmpeg*/**/{name}.exe"))
    if matches:
        return str(matches[0])
    raise RuntimeError(
        f"{name} was not found. An installed Lexium ships it beside the importer; "
        "a development checkout needs FFmpeg on PATH."
    )


# The production chain, named so tools/ingest/audio_profile.py can fingerprint it.
# Changing either constant changes the fingerprint, which marks existing audio stale.
FILTER_CHAIN = "silenceremove=start_periods=1:start_duration=0.03:start_threshold=-50dB:stop_periods=1:stop_duration=0.08:stop_threshold=-50dB,loudnorm=I=-19:LRA=7:TP=-2"
CODEC_ARGS = ("-ac", "1", "-c:a", "libopus", "-b:a", "64k", "-vbr", "on", "-application", "voip")
TARGET_BPS = 64000


def encode(master: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(master),
        "-af", FILTER_CHAIN, *CODEC_ARGS, str(output),
    ], check=True)


def verify(path: Path) -> dict:
    result = subprocess.run([
        find_binary("ffprobe"), "-v", "error", "-show_entries", "format=format_name,duration,size,bit_rate", "-show_entries", "stream=codec_name,channels", "-of", "json", str(path),
    ], check=True, capture_output=True, text=True)
    metadata = json.loads(result.stdout)
    stream = metadata.get("streams", [{}])[0]
    container = metadata.get("format", {})
    if stream.get("codec_name") != "opus" or stream.get("channels") != 1 or "ogg" not in container.get("format_name", "") or float(container.get("duration", 0)) <= 0 or int(container.get("size", 0)) <= 0:
        raise RuntimeError(f"Invalid encoded audio metadata: {metadata}")
    metadata["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata["encoding_target_bps"] = TARGET_BPS
    return metadata
