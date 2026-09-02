"""The one production path from spoken text to a verified Ogg Opus asset.

synthesize -> encode -> verify. No caller picks a voice, a source format or an
FFmpeg argument; they pass text and get back a verified file plus the profile
fingerprint that produced it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tools.ingest import audio_encode, audio_microsoft, audio_profile

PEAK_PATTERN = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB")


class SilentAudio(RuntimeError):
    """The service returned a file, but there is no speech in it."""


def master_peak_dbfs(master: Path) -> float:
    result = subprocess.run(
        [audio_encode.find_binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(master),
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    )
    found = PEAK_PATTERN.search(result.stderr)
    if not found:
        raise RuntimeError(f"Could not measure the level of {master.name}")
    return float(found.group(1))


def generate_production_audio(synthesis_text: str, master: Path, final: Path, retries: int = 5) -> dict:
    """Produce `final` (Ogg Opus 64 kbps mono) for `synthesis_text`.

    Reuses an existing master when one is already on disk so a retry after an
    encode or verification failure does not re-hit the speech service.
    """
    text = synthesis_text.strip()
    if not text:
        raise ValueError("synthesis_text is empty")
    if not master.exists() or master.stat().st_size <= 0:
        audio_microsoft.synthesize_text(text, master, retries=retries)
    peak = master_peak_dbfs(master)
    if peak < audio_profile.MIN_MASTER_PEAK_DBFS:
        master.unlink(missing_ok=True)
        raise SilentAudio(
            f"{audio_profile.VOICE} returned effectively silent audio for {text!r} "
            f"(peak {peak:.1f} dBFS, floor {audio_profile.MIN_MASTER_PEAK_DBFS} dBFS)"
        )
    if final.exists():
        final.unlink()
    audio_encode.encode(master, final)
    metadata = audio_encode.verify(final)
    return {
        "fingerprint": audio_profile.FINGERPRINT,
        "voice": audio_profile.VOICE,
        "sourceFormat": audio_profile.SOURCE_FORMAT,
        "masterPeakDbfs": peak,
        "sha256": metadata["sha256"],
        "durationSeconds": float(metadata["format"]["duration"]),
        "sizeBytes": int(metadata["format"]["size"]),
    }
