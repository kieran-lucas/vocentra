from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    matches = list(winget.glob(f"Gyan.FFmpeg*/**/{name}.exe"))
    if matches:
        return str(matches[0])
    raise RuntimeError(f"{name} is not installed")


def encode(master: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(master),
        "-af", "silenceremove=start_periods=1:start_duration=0.03:start_threshold=-50dB:stop_periods=1:stop_duration=0.08:stop_threshold=-50dB,loudnorm=I=-19:LRA=7:TP=-2",
        "-ac", "1", "-c:a", "libopus", "-b:a", "64k", "-vbr", "on", "-application", "voip", str(output),
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
    metadata["encoding_target_bps"] = 64000
    return metadata
