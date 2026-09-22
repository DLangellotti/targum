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
from datetime import date
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


def plural_form(count: int, language: str = SOURCE) -> str:
    """Which plural form `count` takes in `language`, by CLDR's names.

    The pages say counted things — "3 verses in 7 aliyot" — and a server-rendered page
    cannot ask `Intl.PluralRules` the way the scripts do (targum-internal#348). English
    has two forms and Russian has three, and getting Russian wrong is visibly wrong: it
    is 1 стих, 2 стиха, 5 стихов, and a page that says "5 стиха" reads as broken rather
    than as foreign.

    Only the languages the catalogue actually holds are worth writing down; anything else
    falls back to English's rule, which is also what a missing translation does.
    """
    n = abs(int(count))
    if language.split("-")[0].lower() == "ru":
        # CLDR's Russian rule. The teens are the exception that catches people out: 11
        # and 21 differ, and so do 12 and 22.
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            return "few"
        return "many"
    return "one" if n == 1 else "other"


def counted(key: str, count: int, language: str, fallback: dict[str, str]) -> str:
    """One counted string, in the form `count` takes in `language`.

    `fallback` is what the template wrote — `{"one": …, "other": …}` — used where the
    catalogue has not got the key, exactly as `t` falls back to the English beside it.
    A language whose form the catalogue lacks falls back to `other`, then to `one`: a
    Russian page missing `few` says the `many` string rather than nothing.
    """
    said = catalogue(language.split("-")[0].lower())
    form = plural_form(count, language)
    for tried in (form, "other", "one"):
        found = said.get(f"{key}.{tried}")
        if found:
            return found
    return fallback.get(form) or fallback.get("other") or fallback.get("one") or ""


#: A day and a month as each language writes them. Written down rather than taken from
#: the C library, whose `%A` and `%B` follow the process locale — which on a server is
#: whatever the box was installed with, and is the same for every reader on it.
#:
#: Russian names a date in the genitive: «30 мая», not «30 май». That is why these are a
#: table of forms and not a translation of twelve nouns (targum-internal#348).
_DAYS = {
    "ru": ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"),
}
_MONTHS = {
    "ru": (
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ),
}


def said_date(when: date, language: str = SOURCE) -> str:
    """A date as `language` writes it.

    English keeps what it always said — "Saturday, May 30, 2026" — so nothing already on
    a page moves. Russian puts the day before the month and the month in the genitive,
    which is the half a translated sentence around an English date gets wrong most
    visibly.
    """
    code = language.split("-")[0].lower()
    days, months = _DAYS.get(code), _MONTHS.get(code)
    if days is None or months is None:
        return when.strftime("%A, %B %-d, %Y")
    return f"{days[when.weekday()]}, {when.day} {months[when.month - 1]} {when.year}"


#: "on Saturday" in each language. Russian takes the accusative after «в» — «в субботу»,
#: not «в суббота» — and Tuesday takes «во» rather than «в», so the preposition travels
#: with the day rather than being glued on in a template. The whole phrase is the unit.
_ON_DAY = {
    "ru": (
        "в понедельник",
        "во вторник",
        "в среду",
        "в четверг",
        "в пятницу",
        "в субботу",
        "в воскресенье",
    ),
}


def said_on(when: date, language: str = SOURCE) -> str:
    """A date as the thing something happens *on*, in `language`.

    English writes the same phrase either way, so this is `said_date` there. Russian does
    not: a sentence that reads «читают суббота» is not foreign, it is wrong, and it is
    the sort of wrong that tells a reader the page was assembled rather than written.
    """
    code = language.split("-")[0].lower()
    days = _ON_DAY.get(code)
    if days is None:
        return said_date(when, language)
    months = _MONTHS[code]
    return f"{days[when.weekday()]}, {when.day} {months[when.month - 1]} {when.year}"
