"""A small client for TypeSafe's System One API, which serves the Jev decision model.

Jev picks and never writes (targum-internal#309): state goes in, typed questions go in,
and each answer comes back as a probability over options the caller wrote. So it only
earns a place where targum already holds the candidates and is paying to choose among
them — and it never decides to spend. It is billed on input alone, $42 a billion tokens,
with a budget of about 32k tokens per request shared by the state and the questions.

`scripts/eval_hebrew_stress.py` spoke to the same endpoint with its own copy of this
(targum-internal#318); this is the shared one, with nothing in it about any one question.
The key is `TYPESAFE_API_KEY`, which lives in `.env` and is loaded by hand
(`set -a && . ./.env && set +a`) — nothing on the box has one, and nothing on the box
calls this.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
KEY = "TYPESAFE_API_KEY"

#: Pinned, because a stored answer is only comparable with answers from the same model.
MODEL = "jev-1.13.0"

#: Dollars per input token: $42 per billion in, and output is free.
PER_TOKEN = 42 / 1_000_000_000

#: The statuses worth waiting out. Anything else is a request that is wrong, and asking
#: again would pay for the same refusal.
RETRY = (429, 500, 502, 503, 504)


class Unset(RuntimeError):
    """No key in the environment — usually an `.env` nobody loaded, not a missing key."""


def key() -> str:
    found = os.environ.get(KEY, "").strip()
    if not found:
        raise Unset(f"{KEY} is not set; load it with `set -a && . ./.env && set +a`")
    return found


def ask(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    model: str = MODEL,
    token: str | None = None,
    retries: int = 4,
    timeout: float = 60,
) -> dict[str, Any]:
    """One request, answered whole: `answers` keyed as the questions were, `usage`, and
    the `model` that answered. Retries only what is worth retrying."""
    body = json.dumps(
        {"state": state, "model": model, "questions": questions}, ensure_ascii=False
    ).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {token or key()}",
            "Content-Type": "application/json",
        },
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as answer:
                got: dict[str, Any] = json.loads(answer.read())
                return got
        except urllib.error.HTTPError as error:
            if error.code not in RETRY or attempt == retries - 1:
                raise
            time.sleep(float(error.headers.get("retry-after") or 2**attempt))
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def spent(response: dict[str, Any]) -> int:
    """The input tokens a response was billed for."""
    return int((response.get("usage") or {}).get("input_tokens") or 0)
