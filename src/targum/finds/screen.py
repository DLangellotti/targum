"""What keeps a find off Home (plan §5.1; David, 2026-10-31: drop adult and graphic
content, keep hard news).

Read next puts a find in front of a reader unasked, which is a higher bar than a link
they chose to paste. Two cheap steps here, in order; the source's own filters
(YouTube's `safeSearch`, an age limit) come first in later slices, and a model's yes or
no only on the open web.

1. **The host.** A short seed list of adult, gambling and piracy hosts and the TLDs that
   only carry them, plus whatever the operator adds in `finds-deny.json` beside
   `sources.json` (one host a line in a JSON list). A subdomain of a listed host is
   listed too.
2. **The words.** A short list of explicit sexual and graphic-violence terms in Hebrew,
   Russian and English, matched at the start of a word on the title and the first 500
   words. A hit drops the find. ling-he owns the Hebrew list and refines it.

**Hard news stays.** War, crime, terror, politics and death are what the news is, and
none of their words are here: מלחמה, פיגוע, נהרג and רצח are not on the list. What is
dropped is pornography and the graphic: a beheading described, a body dismembered.

Every drop is counted by reason in the back office. A reader who meets something wrong
uses Tell us, and triage turns it into a host or a word here.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

#: Hosts never offered, whatever they carry. A seed; the operator's file adds to it.
DENIED_HOSTS = frozenset(
    {
        "pornhub.com",
        "xvideos.com",
        "xnxx.com",
        "xhamster.com",
        "redtube.com",
        "youporn.com",
        "onlyfans.com",
        "chaturbate.com",
        "livejasmin.com",
        "stripchat.com",
        "bet365.com",
        "pokerstars.com",
        "888casino.com",
        "1xbet.com",
        "thepiratebay.org",
        "rutracker.org",
        "1337x.to",
    }
)

#: Top-level domains that carry nothing a reader is offered unasked.
DENIED_TLDS = frozenset({"xxx", "porn", "sex", "adult", "casino", "bet", "poker"})

#: The terms, at the start of a word, in the three languages the shelf is read from. A
#: term matches a word that begins with it, so a stem catches its inflections; Hebrew
#: also after one or two prefix letters (`level.PREFIXES`).
TERMS: dict[str, tuple[str, ...]] = {
    "he": (
        "פורנו",
        "פורנוגרפ",
        "סרטון סקס",
        "סרטוני סקס",
        "סקס מפורש",
        "אתר סקס",
        "תמונות עירום",
        "סרטוני עירום",
        "זנות ילדים",
        "עריפת ראש",
        "ערף את ראש",
        "נערף ראשו",
        "גופה מבותרת",
        "גופות מבותרות",
        "ביתר את גופ",
    ),
    "ru": (
        "порно",
        "порнограф",
        "секс-видео",
        "эротическ",
        "интим-услуг",
        "обезглав",
        "расчленен",
        "расчленён",
    ),
    "en": (
        "porn",
        "xxx",
        "nsfw",
        "sex video",
        "sex tape",
        "nude photos",
        "nudes",
        "camgirl",
        "escort service",
        "beheading video",
        "beheaded on camera",
        "dismembered body",
        "gore video",
    ),
}

#: How much of a page the words are matched on (plan §5.1).
FIRST_WORDS = 500

DENY_FILE = "finds-deny.json"


def deny_path() -> Path | None:
    """The operator's own list, beside `sources.json` (`chat.sources.sources_path`)."""
    from ..chat.sources import sources_path

    named = os.environ.get("TARGUM_FINDS_DENY", "").strip()
    if named:
        return Path(named) if Path(named).is_file() else None
    beside = sources_path()
    if beside is None:
        return None
    file = beside.with_name(DENY_FILE)
    return file if file.is_file() else None


@lru_cache(maxsize=4)
def _read_denied(where: str, stamp: float) -> frozenset[str]:
    try:
        loaded = json.loads(Path(where).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    if not isinstance(loaded, list):
        return frozenset()
    return frozenset(str(one).strip().lower().lstrip(".") for one in loaded if str(one).strip())


def denied_hosts() -> frozenset[str]:
    file = deny_path()
    if file is None:
        return DENIED_HOSTS
    try:
        stamp = file.stat().st_mtime
    except OSError:
        return DENIED_HOSTS
    return DENIED_HOSTS | _read_denied(str(file), stamp)


def host_denied(host: str, also: Iterable[str] = ()) -> bool:
    """Whether a host is on the list: itself, any domain above it, or its TLD."""
    name = (host or "").strip().lower().rstrip(".")
    if not name:
        return True
    if name.rsplit(".", 1)[-1] in DENIED_TLDS:
        return True
    listed = denied_hosts() | frozenset(also)
    parts = name.split(".")
    return any(".".join(parts[at:]) in listed for at in range(len(parts) - 1))


def _pattern(terms: Iterable[str], hebrew: bool) -> re.Pattern[str]:
    escaped = "|".join(sorted((re.escape(term) for term in terms), key=len, reverse=True))
    if hebrew:
        # At the start of a word, or after one or two of the prefix letters.
        return re.compile(rf"(?<![א-ת])[והבלמשכ]{{0,2}}(?:{escaped})")
    return re.compile(rf"(?<!\w)(?:{escaped})", re.IGNORECASE)


_PATTERNS = {language: _pattern(terms, language == "he") for language, terms in TERMS.items()}

_WORDS = re.compile(r"\S+")


def first_words(text: str, most: int = FIRST_WORDS) -> str:
    words = _WORDS.findall(text or "")
    return " ".join(words[:most])


def term_in(text: str) -> str:
    """The first listed term in the text's opening, in any of the three languages, or
    "". Every language is tried on every text: a Hebrew page quotes English."""
    opening = first_words(text)
    for language in ("he", "ru", "en"):
        found = _PATTERNS[language].search(opening)
        if found:
            return found.group(0)
    return ""


def passes(host: str, title: str, text: str = "") -> str:
    """Why a find is dropped, or "" where it may be offered: `host` or `words`."""
    if host_denied(host):
        return "host"
    if term_in(f"{title}\n{text}"):
        return "words"
    return ""
