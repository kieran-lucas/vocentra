from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path

VOICE = "en-US-AriaNeural"
PROVIDER = "Microsoft Edge Neural"


def synthesize(card: dict, destination: Path, retries: int = 5) -> None:
    import edge_tts

    text = card["word"].replace(",", ".")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        try:
            asyncio.run(edge_tts.Communicate(text=text, voice=VOICE, rate="-5%").save(str(destination)))
            if destination.stat().st_size <= 0:
                raise RuntimeError("Microsoft speech returned an empty file")
            return
        except Exception:
            destination.unlink(missing_ok=True)
            if attempt == retries:
                raise
            time.sleep(min(20, 2 ** attempt) + random.random())
