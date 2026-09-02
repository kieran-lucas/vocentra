from __future__ import annotations

import asyncio
import functools
import inspect
import random
import time
from pathlib import Path

# Selected by the benchmark in data/audio-benchmark/report.md. Jenny carries
# fricatives and sibilants with 2-9x the energy above 4 kHz of the other
# finalists on sibilant-bearing words, which is what isolated vocabulary
# pronunciation depends on; it also had no unintelligible word on the unseen
# holdout and the steadiest pacing across the 34-word deeper test.
VOICE = "en-US-JennyNeural"

# The only source format the Edge Read Aloud endpoint returns that needs no
# protocol work: it is what edge-tts itself requests. Edge rejects every PCM and
# every higher-rate MP3 variant, and the 96 kbps MP3 it does accept was
# indistinguishable after the Opus encode (96 kbps won on 32 of 60 paired words,
# sign-test p = 0.70). Named here so the pipeline states its source format
# instead of inheriting an undocumented default.
SOURCE_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MASTER_SUFFIX = ".mp3"

RATE = "-5%"
PROVIDER = "Microsoft Edge Neural"


@functools.lru_cache(maxsize=1)
def assert_source_format() -> None:
    """Fail loudly if edge-tts stops requesting SOURCE_FORMAT.

    edge-tts hard-codes the outputFormat in its speech.config frame, so the
    constant above is only honest while the two agree.
    """
    import edge_tts.communicate

    if f'"outputFormat":"{SOURCE_FORMAT}"' not in inspect.getsource(edge_tts.communicate):
        raise RuntimeError(
            f"edge-tts no longer requests {SOURCE_FORMAT}; re-run the source-format benchmark "
            "before generating audio (tools/bench/bench.py probe-formats)."
        )


def card_synthesis_text(card: dict) -> str:
    """Spoken text for a legacy flat pilot card."""
    return card["word"].replace(",", ".")


def synthesize_text(text: str, destination: Path, retries: int = 5) -> None:
    """Write one Edge master for `text`. Callers go through audio_service."""
    import edge_tts

    assert_source_format()
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        try:
            asyncio.run(edge_tts.Communicate(text=text, voice=VOICE, rate=RATE).save(str(destination)))
            if destination.stat().st_size <= 0:
                raise RuntimeError("Microsoft speech returned an empty file")
            return
        except Exception:
            destination.unlink(missing_ok=True)
            if attempt == retries:
                raise
            time.sleep(min(20, 2 ** attempt) + random.random())


def synthesize(card: dict, destination: Path, retries: int = 5) -> None:
    synthesize_text(card_synthesis_text(card), destination, retries=retries)
