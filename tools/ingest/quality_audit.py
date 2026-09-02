from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

from tools.ingest import db
from tools.ingest.audio_encode import verify
from tools.ingest.validator import validate_card

ROOT = Path(__file__).resolve().parents[2]
SEED = 180_2026
SAMPLE_SIZE = 20


def audio_name(source_key: str) -> str:
    return source_key.replace(":", "_") + ".ogg"


def main() -> None:
    cards = json.loads((ROOT / "tools/prompts/authored_cards.json").read_text(encoding="utf-8"))
    selected = sorted(random.Random(SEED).sample(cards, SAMPLE_SIZE), key=lambda card: card["sourceIndex"])
    connection = db.connect()
    rows = connection.execute(
        """SELECT source_key, status, audio_verified, audio_path, audio_voice
           FROM ingestion_items ORDER BY source_index"""
    ).fetchall()
    connection.close()
    state = {row["source_key"]: dict(row) for row in rows}

    all_audio_errors: list[str] = []
    for card in cards:
        path = ROOT / "data/audio-final/en-US" / audio_name(card["sourceKey"])
        try:
            verify(path)
        except Exception as error:
            all_audio_errors.append(f"{card['sourceKey']}: {error}")

    samples: list[dict] = []
    for card in selected:
        item = state.get(card["sourceKey"], {})
        deterministic_errors = validate_card(card)
        usage_note = card.get("exampleUsage", {}).get("note", "").strip()
        sample = {
            "sourceIndex": card["sourceIndex"],
            "sourceKey": card["sourceKey"],
            "word": card["word"],
            "ipa": card["ipa"],
            "partOfSpeech": card["partOfSpeech"],
            "viMeaning": card["viMeaning"],
            "enDefinition": card["enDefinition"],
            "exampleMeaning": card["exampleMeaning"],
            "exampleUsage": card["exampleUsage"],
            "checks": {
                "deterministicCard": not deterministic_errors,
                "distinctExampleRoles": card["exampleMeaning"]["en"] != card["exampleUsage"]["en"] and bool(usage_note),
                "imported": item.get("status") == "IMPORTED",
                "audioVerified": item.get("audio_verified") == 1,
                "fixedVoice": item.get("audio_voice") == "en-US-AriaNeural",
            },
            "errors": deterministic_errors,
        }
        sample["automaticPass"] = all(sample["checks"].values()) and not sample["errors"]
        samples.append(sample)

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "targetCount": len(cards),
        "sampleSize": len(samples),
        "automaticSamplePass": sum(sample["automaticPass"] for sample in samples),
        "allAudioVerified": len(cards) - len(all_audio_errors),
        "audioErrors": all_audio_errors,
        "samples": samples,
    }
    json_path = ROOT / "reports/oxford_a1_pilot_quality.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    sample_lines = [
        f"- #{sample['sourceIndex']:03d} `{sample['word']}` — {'PASS' if sample['automaticPass'] else 'FAIL'}"
        for sample in samples
    ]
    markdown = "\n".join([
        "# Oxford A1 Pilot Quality Audit",
        "",
        f"- Deterministic seed: `{SEED}`",
        f"- Random card sample: {report['automaticSamplePass']}/{report['sampleSize']} PASS",
        f"- Full audio technical verification: {report['allAudioVerified']}/{report['targetCount']} PASS",
        "- Manual semantic review: pending agent review",
        "- Audio semantic review: fixed source text plus technical verification; listening/ASR review pending",
        "",
        "## Sample",
        *sample_lines,
        "",
        "Detailed bilingual fields and checks are stored in `reports/oxford_a1_pilot_quality.json`.",
        "",
    ])
    (ROOT / "reports/oxford_a1_pilot_quality.md").write_text(markdown, encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("seed", "sampleSize", "automaticSamplePass", "allAudioVerified", "audioErrors")}, indent=2))


if __name__ == "__main__":
    main()
