"""The one description of how production pronunciation audio is produced.

Every ingestion path - the Oxford pilot and the external JSON importer alike -
resolves its voice, source format and encoder settings from here, and stamps the
resulting asset with FINGERPRINT. Audio whose stored fingerprint differs from the
current one is stale by definition, so a voice, rate or FFmpeg change is visible
in the data rather than silently baked into files nobody can tell apart.
"""

from __future__ import annotations

import hashlib

from tools.ingest import audio_encode, audio_microsoft

PROVIDER = "edge-readaloud"
VOICE = audio_microsoft.VOICE
SOURCE_FORMAT = audio_microsoft.SOURCE_FORMAT
RATE = audio_microsoft.RATE
MASTER_SUFFIX = audio_microsoft.MASTER_SUFFIX
FINAL_CODEC = "opus"
FINAL_CONTAINER = "ogg"
FINAL_TARGET_BPS = audio_encode.TARGET_BPS
FINAL_CHANNELS = 1
FINAL_SUFFIX = ".ogg"

# Minimum peak level a master must reach to count as speech. The voice benchmark
# found an Edge voice that returned -58.8 dBFS for "a"; without this guard the
# encoder turns that into an unplayable file and the pipeline calls it done.
MIN_MASTER_PEAK_DBFS = -45.0


def encoder_profile() -> str:
    """Short stable digest of the exact FFmpeg processing applied to a master."""
    recipe = audio_encode.FILTER_CHAIN + "|" + " ".join(audio_encode.CODEC_ARGS)
    return hashlib.sha256(recipe.encode("utf-8")).hexdigest()[:12]


def fingerprint() -> str:
    return "|".join((
        PROVIDER,
        VOICE,
        SOURCE_FORMAT,
        f"rate={RATE}",
        f"{FINAL_CODEC}-{FINAL_TARGET_BPS // 1000}k-mono-vbr",
        f"encoder-profile={encoder_profile()}",
    ))


FINGERPRINT = fingerprint()


def describe() -> dict[str, str | int]:
    return {
        "provider": PROVIDER,
        "voice": VOICE,
        "sourceFormat": SOURCE_FORMAT,
        "rate": RATE,
        "finalCodec": FINAL_CODEC,
        "finalContainer": FINAL_CONTAINER,
        "finalTargetBps": FINAL_TARGET_BPS,
        "finalChannels": FINAL_CHANNELS,
        "encoderProfile": encoder_profile(),
        "fingerprint": FINGERPRINT,
    }
