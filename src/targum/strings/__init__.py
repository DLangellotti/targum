"""Words targum says to a person, in the language they read (targum-internal#184).

One file a language beside this module, `<code>.json`, a flat map from a key to the text.
English is the catalogue every other language is measured against: a key English does not
have is a bug and raises, and a key another language has not filled yet is said in
English. That fallback is the correct behaviour while a translation is partial — a Russian
reader shown one English button is a reader who can still press it — and a key's name
reaching a reader never is.

Placeholders are `str.format` fields, `{link}`, and every language must use exactly the
fields English does: a translation that drops `{link}` from the sign-in email sends a
sign-in email with no link in it. `tests/test_strings.py` holds both rules over every file.

Nothing here decides *which* language a person reads: that is `accounts.Store.reads` and
the page's own `targum:into`. This only answers what a key says in the one it is given.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

#: The language every key is written in first, and what is said where another is silent.
SOURCE = "en"

_HERE = Path(__file__).parent


@cache
def catalogue(language: str) -> dict[str, str]:
    """Every key a language has filled, or nothing for a language with no file."""
    code = (language or "").split("-")[0].lower()
    path = _HERE / f"{code}.json"
    if not code.isalpha() or not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in loaded.items()}


def languages() -> list[str]:
    """The languages with a catalogue, English first."""
    found = sorted(path.stem for path in _HERE.glob("*.json") if path.stem != SOURCE)
    return [SOURCE, *found]


def text(key: str, language: str = SOURCE, **fill: str) -> str:
    """What `key` says in `language`, in English where that language has not said it yet.

    Raises `KeyError` for a key English does not have: that is a typo or a string nobody
    wrote, and the place to find it is a test, not a reader's screen.
    """
    english = catalogue(SOURCE)
    if key not in english:
        raise KeyError(f"no string {key!r} in the English catalogue")
    said = catalogue(language).get(key) or english[key]
    return said.format(**fill) if fill else said
