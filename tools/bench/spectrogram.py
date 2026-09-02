# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Render labelled waveform+spectrogram contact sheets for visual clip inspection."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_metrics  # noqa: E402

TILE_W, SPEC_H, WAVE_H, LABEL_H = 520, 190, 60, 18


def render(clip: Path, out: Path) -> Path:
    subprocess.run(
        [
            audio_metrics.ffmpeg(), "-v", "error", "-y", "-i", str(clip),
            "-lavfi",
            f"[0:a]showspectrumpic=s={TILE_W}x{SPEC_H}:legend=0:scale=log:stop=12000[sp];"
            f"[0:a]showwavespic=s={TILE_W}x{WAVE_H}:colors=white[wv];"
            "[sp][wv]vstack=inputs=2",
            "-frames:v", "1", str(out),
        ],
        check=True, capture_output=True,
    )
    return out


def sheet(clips: list[tuple[str, Path]], out: Path, columns: int = 3) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.parent / "_tiles"
    temp.mkdir(exist_ok=True)
    tiles = []
    for label, clip in clips:
        tile = render(clip, temp / (clip.stem + ".png"))
        tiles.append((label, Image.open(tile).convert("RGB")))
    rows = (len(tiles) + columns - 1) // columns
    cell_h = SPEC_H + WAVE_H + LABEL_H
    canvas = Image.new("RGB", (TILE_W * columns, cell_h * rows), (12, 12, 16))
    draw = ImageDraw.Draw(canvas)
    for index, (label, image) in enumerate(tiles):
        x = (index % columns) * TILE_W
        y = (index // columns) * cell_h
        draw.text((x + 6, y + 4), label, fill=(255, 220, 120))
        canvas.paste(image, (x, y + LABEL_H))
    canvas.save(out)
    for _, image in tiles:
        image.close()
    print(f"wrote {out} ({len(tiles)} tiles)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--label-part", type=int, default=1)
    args = parser.parse_args()
    root = Path(args.glob).parent
    clips = sorted(root.glob(Path(args.glob).name))
    labelled = [(clip.stem, clip) for clip in clips]
    sheet(labelled, Path(args.out), args.columns)


if __name__ == "__main__":
    main()
