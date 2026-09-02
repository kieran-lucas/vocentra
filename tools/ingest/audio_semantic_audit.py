# /// script
# requires-python = ">=3.11"
# dependencies = ["faster-whisper==1.2.1"]
# ///
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ingest.audio_encode import find_binary

SENSITIVE_INDICES = {1, 10, 47, 48, 58, 97, 123, 124, 132, 151, 152}


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def main() -> None:
    cards = json.loads((ROOT / "tools/prompts/authored_cards.json").read_text(encoding="utf-8"))
    quality_path = ROOT / "reports/oxford_a1_pilot_quality.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    selected_indices = {sample["sourceIndex"] for sample in quality["samples"]} | SENSITIVE_INDICES
    selected = [card for card in cards if card["sourceIndex"] in selected_indices]
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    results: list[dict] = []
    for card in selected:
        audio_path = ROOT / "data/audio-final/en-US" / f"{card['sourceKey'].replace(':', '_')}.ogg"
        segments, _ = model.transcribe(
            str(audio_path),
            beam_size=5,
            language="en",
            condition_on_previous_text=False,
            vad_filter=False,
        )
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        expected = normalize(card["word"])
        heard = normalize(transcript)
        tokens = set(heard.split())
        expected_tokens = expected.split()
        matched = bool(heard) and (expected in heard or all(token in tokens for token in expected_tokens))
        results.append({
            "sourceIndex": card["sourceIndex"],
            "word": card["word"],
            "ipa": card["ipa"],
            "transcript": transcript,
            "asrMatched": matched,
            "pronunciationSensitive": card["sourceIndex"] in SENSITIVE_INDICES,
        })
        print(f"#{card['sourceIndex']:03d} {card['word']}: {transcript!r} {'PASS' if matched else 'REVIEW'}")
    review_items = [item for item in results if not item["asrMatched"]]
    if review_items:
        review_model = WhisperModel("base.en", device="cpu", compute_type="int8")
        cards_by_index = {card["sourceIndex"]: card for card in cards}
        for item in review_items:
            card = cards_by_index[item["sourceIndex"]]
            audio_path = ROOT / "data/audio-final/en-US" / f"{card['sourceKey'].replace(':', '_')}.ogg"
            segments, _ = review_model.transcribe(
                str(audio_path), beam_size=5, language="en", condition_on_previous_text=False, vad_filter=False
            )
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
            expected = normalize(card["word"])
            heard = normalize(transcript)
            tokens = set(heard.split())
            matched = bool(heard) and (expected in heard or all(token in tokens for token in expected.split()))
            item["reviewTranscript"] = transcript
            item["reviewAsrMatched"] = matched
            print(f"REVIEW #{card['sourceIndex']:03d} {card['word']}: {transcript!r} {'PASS' if matched else 'MANUAL'}")

            if not matched:
                with tempfile.TemporaryDirectory() as temporary:
                    repeated = Path(temporary) / "repeated.wav"
                    subprocess.run([
                        find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                        "-stream_loop", "4", "-i", str(audio_path), "-c:a", "pcm_s16le", str(repeated),
                    ], check=True)
                    segments, _ = review_model.transcribe(
                        str(repeated), beam_size=5, language="en", condition_on_previous_text=False, vad_filter=False,
                        initial_prompt="One English vocabulary word is repeated several times.",
                    )
                    repeated_transcript = " ".join(segment.text.strip() for segment in segments).strip()
                repeated_heard = normalize(repeated_transcript)
                repeated_tokens = set(repeated_heard.split())
                repeated_match = bool(repeated_heard) and (
                    expected in repeated_heard or all(token in repeated_tokens for token in expected.split())
                )
                item["repeatedTranscript"] = repeated_transcript
                item["repeatedAsrMatched"] = repeated_match
                print(f"REPEAT #{card['sourceIndex']:03d} {card['word']}: {repeated_transcript!r} {'PASS' if repeated_match else 'MANUAL'}")

    output = {
        "models": ["faster-whisper tiny.en", "faster-whisper base.en"],
        "sampleCount": len(results),
        "matched": sum(item["asrMatched"] for item in results),
        "matchedAfterReview": sum(
            item["asrMatched"] or item.get("reviewAsrMatched", False) or item.get("repeatedAsrMatched", False)
            for item in results
        ),
        "manualInterpretationNeeded": sum(
            not item["asrMatched"] and not item.get("reviewAsrMatched", False) and not item.get("repeatedAsrMatched", False)
            for item in results
        ),
        "results": results,
        "note": "ASR is an auxiliary pronunciation sanity check; isolated function words may require manual interpretation.",
    }
    (ROOT / "reports/oxford_a1_pilot_audio_semantic.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
