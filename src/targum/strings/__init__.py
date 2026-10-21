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
import re
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


def said_day(when: date, language: str = SOURCE, year: bool = False) -> str:
    """A day and its month as `language` writes them, with the year where it is asked for.

    For a list of days, where the weekday is noise and the year is the same all the way
    down: "28 September", «28 сентября». English puts the day first here, as /about's own
    count does, because a column of dates is read down its numbers.
    """
    code = language.split("-")[0].lower()
    months = _MONTHS.get(code)
    said = f"{when.day} {months[when.month - 1]}" if months else when.strftime("%-d %B")
    return f"{said} {when.year}" if year else said


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


# -- the names a calendar spells (targum-internal#188) -----------------------------------
#
# Hebcal writes a reading as "Numbers 4:21-7:89" and a Hebrew date as "19 Elul 5786", in
# English whatever page they land on. The numbers are the same in every language and the
# names are not: a Russian reader knows the book as «Числа» and the month as «элуля».
# So the names are catalogue keys — `reference.*` for a book, `hebrew-month.*` for a
# month — and these swap them in, leaving the numbers, and every name the catalogue has
# no key for (a Mishnah tractate, a special Shabbat), exactly as the calendar wrote them.


@cache
def _names(prefix: str, language: str) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    """The English names under `prefix` as one pattern, and what each is in `language`."""
    english = catalogue(SOURCE)
    said = catalogue(language)
    swap = {
        english[key]: said[key]
        for key in english
        if key.startswith(prefix) and said.get(key) and said[key] != english[key]
    }
    if not swap:
        return None, {}
    # Longest first, so "Song of Songs" is one name rather than "Song" and a leftover,
    # and "II Kings" is not read as "I" stuck to "I Kings". A name is whole words on both
    # sides, which is also what keeps "Av" out of "Avot".
    ordered = sorted(swap, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w'])(" + "|".join(map(re.escape, ordered)) + r")(?![\w'])")
    return pattern, swap


def _said_names(prefix: str, said: str, language: str) -> str:
    code = (language or SOURCE).split("-")[0].lower()
    if code == SOURCE or not said:
        return said
    pattern, swap = _names(prefix, code)
    if pattern is None:
        return said
    return pattern.sub(lambda found: swap[found.group(1)], said)


def said_reference(reference: str, language: str = SOURCE) -> str:
    """A reading as `language` names its books: «Числа 4:21-7:89» for "Numbers 4:21-7:89".

    English is returned untouched, so nothing already on an English page moves.
    """
    return _said_names("reference.", reference, language)


def said_portion(slug: str, name: str, language: str = SOURCE) -> str:
    """A Torah portion's name as `language` writes it: «Берешит» for Bereshit (QA,
    2026-10-05).

    Keyed by the portion's slug, `portion.name.<slug>`, because the name is the calendar's
    and the slug is what does not move. English is the name the calendar wrote, untouched,
    so nothing on an English page moves; a language with no key for a reading says that
    name too.
    """
    code = (language or SOURCE).split("-")[0].lower()
    if code == SOURCE:
        return name
    return catalogue(code).get(f"portion.name.{slug}") or name


def said_hebrew_date(hdate: str, language: str = SOURCE) -> str:
    """A Hebrew date as `language` names its month: «19 элуля 5786» for "19 Elul 5786".

    Russian puts the month in the genitive, as `said_date` does for the Gregorian one.
    """
    return _said_names("hebrew-month.", hdate, language)


# -- which language a reader is read to in (targum-internal#286, item 1) -----------------
#
# One rule, in one place, because there were two and they disagreed. The interface
# picked the reader's other language and the conversation picked English whenever
# English was read, so the common Russian account — `{"en", "ru"}`, since an account
# starts at `{"en"}` and Russian is added to it — got Russian buttons with English
# meanings under them, an English `= ` line and an English "Save as targum".

#: The key prefixes that make a language one a desk page can be drawn in. A catalogue
#: with nothing under any of them has been started and not yet used.
DESK_KEYS = (
    "nav.",
    "progress.",
    "learn.",
    "library.",
    "you.",
    "add.",
    "charts.",
    "lang.",
    "building.",
    "account.",
    "shelf.",
    "follow.",
    "bring.",
    "yours.",
    "lists.",
    "vocab.",
    "claim.",
    "palette.",
    "chat.",
    "speak.",
)


def desk_languages() -> list[str]:
    """The languages besides English with a catalogue that says something on a desk page."""
    return [
        code
        for code in languages()
        if code != SOURCE and any(key.startswith(DESK_KEYS) for key in catalogue(code))
    ]


def reading_language(reads: set[str] | None) -> str:
    """The language targum speaks to a reader in: the meanings, the `= ` line, the name
    a build is given, and the chrome where there are words for it.

    The one language their account reads other than English: reading Russian is the
    choice that says so, English beside it or not. English otherwise — for a reader who
    reads only English, and for one who reads two other languages, where nothing says
    which of them is meant.

    There is deliberately no desk gate here. Whether targum has *interface strings* in a
    language is a fact about targum; whether a reader wants their meanings in it is a
    fact about the reader, and a French reader had French meanings before any of the
    chrome was French. `drawn_in` is where the interface admits what it cannot draw.
    """
    if not reads:
        return SOURCE
    others = sorted(code for code in reads if code != SOURCE)
    return others[0] if len(others) == 1 else SOURCE


def drawn_in(reads: set[str] | None) -> str:
    """`reading_language`, narrowed to what the chrome can actually be drawn in.

    The interface falls back to English where nothing has been written for a language;
    the meanings do not, because they are bought per language rather than written here.
    """
    said = reading_language(reads)
    return said if said in desk_languages() else SOURCE
