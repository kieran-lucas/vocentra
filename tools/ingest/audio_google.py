from __future__ import annotations

import base64
import functools
import html
import random
import time
from pathlib import Path

VOICE = "en-US-Chirp3-HD-Leda"
ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"


class AuthenticationRequired(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def access_token() -> str:
    try:
        import google.auth
        from google.auth.transport.requests import Request
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(Request())
        return credentials.token
    except Exception as error:
        raise AuthenticationRequired(
            "Google Application Default Credentials are unavailable. Run: gcloud auth application-default login"
        ) from error


def synthesis_input(card: dict) -> dict[str, str]:
    word = card["word"]
    ipa = card["ipa"].strip("/")
    if all(mark not in word + ipa for mark in (",", ";")) and " " not in word:
        return {"ssml": f'<speak><phoneme alphabet="ipa" ph="{html.escape(ipa, quote=True)}">{html.escape(word)}</phoneme></speak>'}
    return {"text": word.replace(",", ".")}


def synthesize(card: dict, destination: Path, retries: int = 5) -> None:
    import requests
    token = access_token()
    request = {
        "input": synthesis_input(card),
        "voice": {"languageCode": "en-US", "name": VOICE},
        "audioConfig": {"audioEncoding": "LINEAR16"},
    }
    for attempt in range(1, retries + 1):
        response = requests.post(ENDPOINT, headers={"Authorization": f"Bearer {token}"}, json=request, timeout=60)
        if response.ok:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(base64.b64decode(response.json()["audioContent"]))
            return
        if response.status_code not in (429, 500, 502, 503, 504) or attempt == retries:
            raise RuntimeError(f"Google TTS returned HTTP {response.status_code}: {response.text[:500]}")
        time.sleep(min(20, 2 ** attempt) + random.random())
