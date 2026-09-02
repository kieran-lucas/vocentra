from __future__ import annotations

import json
from pathlib import Path


def load_authored_cards(path: Path) -> dict[str, dict]:
    cards = json.loads(path.read_text(encoding="utf-8"))
    return {card["sourceKey"]: card for card in cards}


def write_normalized(cards: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(card, ensure_ascii=False, sort_keys=True) + "\n" for card in sorted(cards, key=lambda value: value["sourceIndex"])), encoding="utf-8")
