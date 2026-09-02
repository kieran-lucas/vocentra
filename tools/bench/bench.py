# /// script
# requires-python = ">=3.11"
# dependencies = ["edge-tts==7.2.7", "numpy", "faster-whisper"]
# ///
"""Edge TTS voice/format benchmark driver for Lexium.

Benchmark-only. Writes under data/audio-benchmark/ and never touches the pilot
masters, the app database, ingestion checkpoints or semantic card data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_metrics  # noqa: E402
import edge_synth  # noqa: E402
from tools.ingest import audio_encode  # noqa: E402

BENCH = ROOT / "data" / "audio-benchmark"
RATE = "-5%"  # production setting, held constant everywhere
PITCH = "+0Hz"
VOLUME = "+0%"
BASELINE_FORMAT = "audio-24khz-48kbitrate-mono-mp3"

ROUND1_VOICES = [
    "en-US-JennyNeural",
    "en-US-EmmaNeural",
    "en-US-AvaNeural",
    "en-US-AndrewNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural",
    "en-US-AriaNeural",
    "en-US-RogerNeural",
    "en-US-EmmaMultilingualNeural",
    "en-US-BrianNeural",
    "en-US-MichelleNeural",
]

# Round 1 survivors. EmmaMultilingual is dropped as a measured duplicate of Emma
# (3.5 dB mean log-spectral distance versus 12-21 dB between distinct voices).
ROUND2_VOICES = [
    "en-US-AvaNeural",
    "en-US-JennyNeural",
    "en-US-AndrewNeural",
    "en-US-AriaNeural",
    "en-US-EmmaNeural",
]

ROUND1_WORDS = [
    "a", "an", "world", "girl", "comfortable", "architecture",
    "entrepreneur", "algorithm", "usually", "thoroughly", "heterogeneous", "record",
]

REPEAT_WORDS = [
    "world", "comfortable", "entrepreneur", "particularly",
    "thoroughly", "heterogeneous", "record", "rural",
]

FORMAT_WORDS = [
    "a", "world", "comfortable", "architecture", "entrepreneur",
    "algorithm", "usually", "thoroughly", "heterogeneous", "rural",
]

INTERACTION_WORDS = [
    "world", "girl", "comfortable", "entrepreneur", "particularly",
    "thoroughly", "heterogeneous", "rural", "architecture", "record",
]

CANDIDATE_FORMATS = [
    "audio-24khz-48kbitrate-mono-mp3",
    "audio-24khz-96kbitrate-mono-mp3",
    "audio-48khz-192kbitrate-mono-mp3",
    "riff-48khz-16bit-mono-pcm",
    "riff-24khz-16bit-mono-pcm",
    "raw-24khz-16bit-mono-pcm",
    "audio-24khz-160kbitrate-mono-mp3",
    "audio-48khz-96kbitrate-mono-mp3",
    "webm-24khz-16bit-mono-opus",
    "ogg-48khz-16bit-mono-opus",
]


def extension(output_format: str) -> str:
    if output_format.endswith("mp3"):
        return ".mp3"
    if output_format.endswith("pcm"):
        return ".wav" if output_format.startswith("riff") else ".pcm"
    if "opus" in output_format:
        return ".webm" if output_format.startswith("webm") else ".ogg"
    return ".bin"


def short_voice(voice: str) -> str:
    return voice.replace("en-US-", "").replace("Neural", "")


def short_format(output_format: str) -> str:
    return output_format.replace("audio-", "").replace("kbitrate", "k").replace("-mono", "")


def clip_id(word: str, voice: str, output_format: str, take: int) -> str:
    return f"{word}__{short_voice(voice)}__{short_format(output_format)}__t{take}"


async def _synth_all(jobs: list[dict], concurrency: int = 4) -> list[dict]:
    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict] = []

    async def one(job: dict) -> None:
        destination = Path(job["master"])
        async with semaphore:
            if destination.exists() and destination.stat().st_size > 0:
                job["content_type"] = "cached"
                job["bytes"] = destination.stat().st_size
                job["ok"] = True
                results.append(job)
                return
            last = None
            for attempt in range(1, 5):
                try:
                    audio, content_type = await edge_synth.synthesize_bytes(
                        job["word"], job["voice"], output_format=job["format"],
                        rate=RATE, pitch=PITCH, volume=VOLUME,
                    )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(audio)
                    job["content_type"] = content_type
                    job["bytes"] = len(audio)
                    job["attempts"] = attempt
                    job["ok"] = True
                    results.append(job)
                    return
                except Exception as error:  # noqa: BLE001
                    last = error
                    await asyncio.sleep(min(10, 2 ** attempt) + random.random())
            job["ok"] = False
            job["error"] = f"{type(last).__name__}: {last}"
            results.append(job)

    await asyncio.gather(*(one(job) for job in jobs))
    return results


def build_jobs(round_dir: Path, combos: list[tuple[str, str, str, int]]) -> list[dict]:
    jobs = []
    for word, voice, output_format, take in combos:
        cid = clip_id(word, voice, output_format, take)
        jobs.append({
            "clip_id": cid,
            "word": word,
            "voice": voice,
            "format": output_format,
            "take": take,
            "master": str(round_dir / "master" / (cid + extension(output_format))),
            "final": str(round_dir / "final" / (cid + ".ogg")),
        })
    return jobs


def synthesize_round(name: str, combos: list[tuple[str, str, str, int]], encode: bool = True) -> None:
    round_dir = BENCH / name
    jobs = build_jobs(round_dir, combos)
    results = asyncio.run(_synth_all(jobs))
    results.sort(key=lambda job: job["clip_id"])
    encoded, failed = 0, 0
    for job in results:
        if not job.get("ok"):
            failed += 1
            continue
        if encode:
            final = Path(job["final"])
            if not final.exists():
                try:
                    audio_encode.encode(Path(job["master"]), final)
                except Exception as error:  # noqa: BLE001
                    job["encode_error"] = str(error)
                    failed += 1
                    continue
            encoded += 1
    index = round_dir / "index.jsonl"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("\n".join(json.dumps(job) for job in results) + "\n", encoding="utf-8")
    print(f"{name}: {len(results)} clips, {encoded} encoded, {failed} failed -> {index}")


def analyze_round(name: str, asr: bool = True, model_size: str = "small.en") -> None:
    round_dir = BENCH / name
    lines = (round_dir / "index.jsonl").read_text(encoding="utf-8").splitlines()
    jobs = [json.loads(line) for line in lines if line.strip()]
    jobs = [job for job in jobs if job.get("ok")]
    partial = round_dir / "metrics.partial.jsonl"
    done: dict[str, dict] = {}
    if partial.exists():
        for line in partial.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                done[record["clip_id"]] = record
        print(f"{name}: resuming with {len(done)} clips already measured")
    transcriber = None
    if asr and any(job["clip_id"] not in done for job in jobs):
        from faster_whisper import WhisperModel

        transcriber = WhisperModel(model_size, device="cpu", compute_type="int8")
    out = []
    handle = partial.open("a", encoding="utf-8")
    for job in jobs:
        if job["clip_id"] in done:
            out.append(done[job["clip_id"]])
            continue
        record = dict(job)
        final = Path(job["final"])
        target = final if final.exists() else Path(job["master"])
        record["analysed"] = str(target)
        try:
            record.update(audio_metrics.measure(target))
            record["probe_master"] = audio_metrics.probe(Path(job["master"]))
            if final.exists():
                record["probe_final"] = audio_metrics.probe(final)
        except Exception as error:  # noqa: BLE001
            record["error"] = f"{type(error).__name__}: {error}"
        if transcriber is not None and "error" not in record:
            audio = audio_metrics.decode(target, 16000).astype("float32")
            segments, _ = transcriber.transcribe(
                audio, language="en", beam_size=5, condition_on_previous_text=False,
                temperature=0.0, without_timestamps=True,
            )
            segments = list(segments)
            text = " ".join(segment.text for segment in segments).strip()
            record["asr_text"] = text
            record["asr_logprob"] = float(sum(s.avg_logprob for s in segments) / len(segments)) if segments else -9.0
            record["asr_no_speech"] = float(sum(s.no_speech_prob for s in segments) / len(segments)) if segments else 1.0
            normalized = "".join(c for c in text.lower() if c.isalnum() or c == " ").strip()
            record["asr_match"] = normalized == job["word"].lower()
        out.append(record)
        handle.write(json.dumps(record) + "\n")
        handle.flush()
    handle.close()
    path = round_dir / "metrics.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in out) + "\n", encoding="utf-8")
    print(f"{name}: wrote {len(out)} metric rows -> {path}")


def remeasure_round(name: str) -> None:
    """Refresh acoustic metrics in place, keeping the existing ASR results."""
    path = BENCH / name / "metrics.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for record in rows:
        target = Path(record["analysed"])
        record.pop("error", None)
        try:
            record.update(audio_metrics.measure(target))
        except Exception as error:  # noqa: BLE001
            record["error"] = f"{type(error).__name__}: {error}"
    path.write_text("\n".join(json.dumps(record) for record in rows) + "\n", encoding="utf-8")
    print(f"{name}: remeasured {len(rows)} rows")


def load_words(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--asr", default="small.en")
    parser.add_argument("--no-asr", action="store_true")
    parser.add_argument("--voices", default="")
    parser.add_argument("--formats", default="")
    parser.add_argument("--words", default="")
    parser.add_argument("--takes", type=int, default=1)
    parser.add_argument("--name", default="")
    args = parser.parse_args()

    if args.command == "round1":
        combos = [(w, v, BASELINE_FORMAT, 1) for v in ROUND1_VOICES for w in ROUND1_WORDS]
        synthesize_round("voices/round1", combos)
    elif args.command == "round2":
        words = load_words(BENCH / "wordsets" / "round2.txt")
        combos = [(w, v, BASELINE_FORMAT, 1) for v in ROUND2_VOICES for w in words]
        combos += [(w, v, BASELINE_FORMAT, 2) for v in ROUND2_VOICES for w in REPEAT_WORDS]
        synthesize_round("voices/round2", combos)
    elif args.command == "probe-formats":
        voices = args.voices.split(",") if args.voices else ROUND2_VOICES[:1]
        out = BENCH / "formats" / "round3" / "acceptance.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        results = {}
        for voice in voices:
            for output_format in CANDIDATE_FORMATS:
                destination = out.parent / "probe" / f"{short_voice(voice)}__{short_format(output_format)}{extension(output_format)}"
                try:
                    content_type = edge_synth.synthesize(
                        "world", voice, destination, output_format=output_format, rate=RATE, retries=2
                    )
                    results[f"{voice}|{output_format}"] = {"accepted": True, "content_type": content_type,
                                                          "bytes": destination.stat().st_size}
                except Exception as error:  # noqa: BLE001
                    results[f"{voice}|{output_format}"] = {"accepted": False, "error": str(error)[:160]}
                print(f"{voice:32s} {output_format:36s} "
                      f"{'ACCEPTED ' + str(results[f'{voice}|{output_format}'].get('content_type')) if results[f'{voice}|{output_format}']['accepted'] else 'REJECTED'}")
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"-> {out}")
    elif args.command == "round3":
        formats = args.formats.split(",")
        combos = [(w, args.voices, f, 1) for f in formats for w in FORMAT_WORDS]
        synthesize_round("formats/round3", combos)
    elif args.command == "round4":
        combos = [
            (w, v, f, 1)
            for v in args.voices.split(",") for f in args.formats.split(",") for w in INTERACTION_WORDS
        ]
        synthesize_round("interaction/round4", combos)
    elif args.command == "round5":
        words = load_words(BENCH / "wordsets" / "round5_holdout.txt")
        combos = [
            (w, v, f, 1)
            for v, f in (pair.split("@") for pair in args.voices.split(","))
            for w in words
        ]
        synthesize_round("holdout/round5", combos)
    elif args.command == "synth":
        voices = args.voices.split(",")
        formats = args.formats.split(",")
        words = load_words(Path(args.words))
        combos = [
            (w, v, f, t)
            for v in voices for f in formats for w in words
            for t in range(1, args.takes + 1)
        ]
        synthesize_round(args.name, combos)
    elif args.command.startswith("remeasure:"):
        remeasure_round(args.command.split(":", 1)[1])
    elif args.command.startswith("analyze:"):
        analyze_round(args.command.split(":", 1)[1], asr=not args.no_asr, model_size=args.asr)
    else:
        raise SystemExit(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
