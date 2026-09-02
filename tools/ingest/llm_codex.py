from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATCH_SCHEMA = ROOT / "tools/schemas/vocabulary_batch.schema.json"
CRITIC_SCHEMA = ROOT / "tools/schemas/vocabulary_critique.schema.json"
GENERATOR_MODEL = "gpt-5.6-sol"
CRITIC_MODEL = "gpt-5.6-sol"

GENERATOR_INSTRUCTIONS = """You are the semantic card generator for Lexium. Create exactly one independently authored learner card for each supplied official Oxford curriculum record. Preserve sourceKey, sourceIndex, partOfSpeech, and cefr exactly. For display word, remove only a trailing parenthetical sense label such as '(money)'. Use General American IPA in /.../. Choose the most common sense matching the supplied POS and any parenthetical disambiguator. Vietnamese must be concise, natural, and sense-specific. The English definition must be original, accurate, concise, and learner-friendly. Meaning example must make the meaning obvious. Usage example must teach a real collocation, grammar pattern, preposition, countability, transitivity, or register fact; its note must name that pattern briefly. Both Vietnamese translations must be natural and faithful. acceptedAnswers must include the displayed headword. In extras, use empty arrays or strings unless genuinely useful. Do not copy Oxford wording. Return only schema-compliant JSON."""

CRITIC_INSTRUCTIONS = """You are the independent quality critic for Lexium in a fresh context. Review every card separately against its exact source metadata. Critical checks: intended common sense and supplied POS align; concise original English definition; natural sense-specific Vietnamese; Example 1 makes meaning obvious; Example 2 teaches a real usage, collocation, grammar, countability, transitivity, preposition, or register property rather than merely repeating meaning; translations are faithful; the note is accurate; General American IPA is credible. Any critical doubt is a failure. pass may be true only when every boolean is true and overall >= 9.3. Give precise minimum-field repair instructions for failures. Do not rewrite cards. Return only schema-compliant JSON."""

REPAIR_INSTRUCTIONS = """Repair only the fields identified by the independent critic, plus the minimum dependent fields needed for consistency. Preserve all source metadata exactly and retain fields that already passed. The result must meet the Lexium card rules: independently authored prose, sense-specific natural Vietnamese, accurate learner definition, distinct meaning and usage examples, faithful translations, a useful usage note, and credible General American IPA. Return the complete repaired cards only as schema-compliant JSON."""


def _codex_binary() -> str:
    found = shutil.which("codex.cmd") or shutil.which("codex")
    if not found:
        raise RuntimeError("Authenticated Codex CLI is not installed")
    return found


def _run(prompt: str, schema: Path, model: str, label: str, retries: int = 3) -> dict:
    env = os.environ.copy()
    env.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "NO_COLOR": "1"})
    last_error = ""
    for attempt in range(1, retries + 1):
        with tempfile.TemporaryDirectory(prefix="lexium-codex-") as temporary:
            output = Path(temporary) / "result.json"
            command = [
                _codex_binary(), "exec", "-m", model, "-c", 'model_reasoning_effort="low"',
                "--sandbox", "read-only", "--ephemeral", "--ignore-rules", "--color", "never",
                "--output-schema", str(schema), "--output-last-message", str(output), "-",
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=600,
            )
            if completed.returncode == 0 and output.exists():
                try:
                    return json.loads(output.read_text(encoding="utf-8"))
                except json.JSONDecodeError as error:
                    last_error = f"invalid structured output: {error}"
            else:
                tail = (completed.stderr or completed.stdout)[-2000:]
                last_error = f"Codex {label} exited {completed.returncode}: {tail}"
        if attempt < retries:
            time.sleep(min(30, 2 ** attempt) + random.random())
    raise RuntimeError(last_error or f"Codex {label} failed")


def generate_cards(source_records: list[dict]) -> list[dict]:
    prompt = f"{GENERATOR_INSTRUCTIONS}\n\nSOURCE RECORDS:\n{json.dumps(source_records, ensure_ascii=False)}"
    return _run(prompt, BATCH_SCHEMA, GENERATOR_MODEL, "generator")["cards"]


def critique_cards(source_records: list[dict], cards: list[dict]) -> list[dict]:
    payload = {"sourceRecords": source_records, "cards": cards}
    prompt = f"{CRITIC_INSTRUCTIONS}\n\nINPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    return _run(prompt, CRITIC_SCHEMA, CRITIC_MODEL, "critic")["reviews"]


def repair_cards(source_records: list[dict], cards: list[dict], reviews: list[dict]) -> list[dict]:
    payload = {"sourceRecords": source_records, "cards": cards, "criticReviews": reviews}
    prompt = f"{REPAIR_INSTRUCTIONS}\n\nINPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    return _run(prompt, BATCH_SCHEMA, GENERATOR_MODEL, "repair")["cards"]
