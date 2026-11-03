"""A suggestion never drops a reader into the middle of a series (David, 2026-11-03;
design.md §12, "A suggestion never starts a series in the middle").

What is here: whether a title, a podcast episode or a catalogue row is a numbered part of
something (`of_title`, `of_episode`, `of_entry`), which part, and of what (`Part.key`);
whether a reader may be offered it (`allowed`: part 1 always, part N once they opened part
N−1); and the one pass every suggestion list goes through (`gate`), which puts part 1 in a
later part's place where part 1 is there to offer, and otherwise leaves the series out.

**Conservative and deterministic.** A part is said in words or in a structured field,
never guessed from a bare number: "חלק 2", "פרק 3", "Part 2", "Ep. 3", "S2E3", "(2/5)",
«Часть 2», «Серия 3», "החלק השני", "Part Two"; a podcast feed's `itunes:episode` and
`itunes:season`. A year, a chapter of a book ("Глава I", "2 Samuel 9"), "Toy Story 2",
"Psalm 20" or "שאלה 20" is not a part. A word that only might be a part ("חלק מהציפורים",
"part-time", "ופרק ג" in the middle of a sentence) is not one either.

**A podcast that says it is episodic** (`<itunes:type>episodic</itunes:type>`) numbers its
episodes as a counter, not a story: Apple's own definition is episodes "intended to be
consumed without any specific order". There "פרק 189" or `itunes:episode` 189 is not a
part; only part wording ("חלק 2") is. A serial feed, or one that says neither, is held to
its numbers. A trailer or a bonus episode is never a part.

**The key** is what the parts of one thing share: the title's words before the marker,
folded (no points, no case, no punctuation), or where the marker leads the title ("פרק 82:
…"), the publisher's name. Where neither is there, the key is empty and nothing ever
matches it, so a later part of it is never offered: every failure here leaves a part out,
never in.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

#: Said with part wording ("חלק", "Part", «Часть», "(2/5)"): a part of one thing.
PART = "part"
#: Said with episode wording ("פרק", "Episode", «Серия») or numbered by a feed.
EPISODE = "episode"

#: A later part whose number is not said ("החלק האחרון", "the final part"). Never part 1,
#: and nobody has opened the part before it, so it is never offered on its own.
LATER = 10_000

#: How a row carries its part for `gate`, as plain data the page can be handed.
FIELD = "series_part"


@dataclass(frozen=True)
class Part:
    """One numbered part of a series."""

    #: What the parts of one series share (`fold`); "" matches nothing.
    key: str
    #: 1, 2, 3…; `LATER` where it is a later part whose number is not said.
    number: int
    #: The season, where one is said with an episode; 0 where none is.
    season: int = 0
    kind: str = PART
    #: Who published it, folded, where that is known: part 1 is looked for only from the
    #: same publisher.
    publisher: str = ""

    @property
    def first(self) -> bool:
        """Whether this is where the series starts: part 1, of the first season."""
        return self.number == 1 and self.season <= 1

    def row(self) -> dict[str, Any]:
        """As a suggestion row carries it (`FIELD`)."""
        return {
            "key": self.key,
            "number": self.number,
            "season": self.season,
            "kind": self.kind,
            "publisher": self.publisher,
        }


def from_row(row: Mapping[str, Any]) -> Part | None:
    """The part a suggestion row carries, or None."""
    said = row.get(FIELD)
    if not isinstance(said, Mapping):
        return None
    try:
        return Part(
            key=str(said.get("key") or ""),
            number=int(said.get("number") or 0),
            season=int(said.get("season") or 0),
            kind=str(said.get("kind") or PART),
            publisher=str(said.get("publisher") or ""),
        )
    except (TypeError, ValueError):
        return None


# -- folding -------------------------------------------------------------------------

#: Hebrew points and cantillation, which a title may or may not carry.
_MARKS = re.compile(r"[֑-ׇֽֿׁׂׅׄ]")
_NOT_WORD = re.compile(r"[\W_]+")


def fold(text: str) -> str:
    """A title's words as a key: no points, no case, no punctuation, one space between."""
    plain = _MARKS.sub("", unicodedata.normalize("NFKC", text or ""))
    return " ".join(_NOT_WORD.sub(" ", plain.casefold()).split())


# -- numbers in words ----------------------------------------------------------------

_HE_LETTERS = {"א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9, "י": 10}
_HE_ORDINALS = {
    "ראשון": 1,
    "ראשונה": 1,
    "שני": 2,
    "שנייה": 2,
    "שניה": 2,
    "שלישי": 3,
    "שלישית": 3,
    "רביעי": 4,
    "רביעית": 4,
    "חמישי": 5,
    "חמישית": 5,
    "שישי": 6,
    "שישית": 6,
    "שביעי": 7,
    "שביעית": 7,
    "שמיני": 8,
    "שמינית": 8,
    "תשיעי": 9,
    "תשיעית": 9,
    "עשירי": 10,
    "עשירית": 10,
    "אחרון": LATER,
    "אחרונה": LATER,
}
_EN_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "last": LATER,
    "final": LATER,
}
_ROMAN = {
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "vii": 7,
    "viii": 8,
    "ix": 9,
    "x": 10,
}
_RU_WORDS = {
    "первая": 1,
    "первый": 1,
    "вторая": 2,
    "второй": 2,
    "третья": 3,
    "третий": 3,
    "четвертая": 4,
    "четвёртая": 4,
    "четвертый": 4,
    "четвёртый": 4,
    "пятая": 5,
    "пятый": 5,
    "шестая": 6,
    "шестой": 6,
    "седьмая": 7,
    "седьмой": 7,
    "восьмая": 8,
    "восьмой": 8,
    "девятая": 9,
    "девятый": 9,
    "десятая": 10,
    "десятый": 10,
    "последняя": LATER,
    "последний": LATER,
}

_GERESH = "'’׳\"״"
#: A Hebrew letter as a number: with a geresh ("א'"), or standing alone before the end or
#: punctuation ("חלק ב:"), never before another word ("חלק ב והאחרון" is not said).
_HE_LETTER = rf"(?P<letter>[א-י])(?:[{_GERESH}]|(?=\s*(?:$|[^\w\s])))"
_DIGITS = r"(?P<digits>\d{1,3})(?!\d)"
_HE_WORD = r"ה?(?P<heword>" + "|".join(sorted(_HE_ORDINALS, key=len, reverse=True)) + r")(?!\w)"
_EN_WORD = r"(?P<enword>" + "|".join(sorted(_EN_WORDS, key=len, reverse=True)) + r")(?!\w)"
_EN_ROMAN = r"(?P<roman>" + "|".join(sorted(_ROMAN, key=len, reverse=True)) + r")(?![\w'’])"
_RU_WORD = r"(?P<ruword>" + "|".join(sorted(_RU_WORDS, key=len, reverse=True)) + r")(?!\w)"

#: Between a noun and its number: anything for digits ("חלק2", "Pt.2", "Part #2"), but at
#: least a space or a dash before a word or a letter, so "חלקי" or "Parti" is no part.
_TO_DIGITS = r"\s*[-–#:]?\s*"
_TO_WORD = r"(?:\s+|\s*[-–:]\s*)"


def _after(noun: str, *words: str) -> str:
    """A noun followed by its number, in digits or in one of `words`."""
    return rf"(?<!\w){noun}(?:{_TO_DIGITS}{_DIGITS}|{_TO_WORD}(?:{'|'.join(words)}))"


def _before(noun: str, word: str) -> str:
    """A number, in digits or in `word`, then its noun: «2 часть», «2-я серия»."""
    return rf"(?<!\w)(?:{_DIGITS}(?:-?[яйе])?|{word})\s+{noun}(?!\w)"


#: S2E3, S02 E03: a season and an episode.
_SXE = r"(?<!\w)(?P<sxe>s(?P<s>\d{1,2})\s*e(?P<e>\d{1,3}))(?!\w)"

#: Each way a part is said, and whether it is part or episode wording. Only ה may stand
#: before a Hebrew noun: "ופרק ג" is "and chapter three" in the middle of a sentence.
_SAID: tuple[tuple[re.Pattern[str], str], ...] = (
    # Hebrew: חלק 2, חלק א', החלק השני, החלק האחרון; פרק 3, הפרק הראשון.
    (re.compile(_after("ה?חלק", _HE_WORD, _HE_LETTER)), PART),
    (re.compile(_after("ה?פרק", _HE_WORD, _HE_LETTER)), EPISODE),
    # English: Part 2, Pt. 2, Part Two, Part II; Episode 3, Ep. 3, Ep3; S2E3, S02 E03.
    (re.compile(_after(r"(?:part|pt\.?)", _EN_WORD, _EN_ROMAN), re.IGNORECASE), PART),
    (re.compile(_after(r"(?:episode|ep\.?)", _EN_WORD, _EN_ROMAN), re.IGNORECASE), EPISODE),
    (re.compile(_SXE, re.IGNORECASE), EPISODE),
    # Russian: Часть 2, часть вторая, Часть II, 2 часть, 2-я часть, вторая часть; Серия 3,
    # Эпизод 3, третья серия.
    (re.compile(_after("часть", _RU_WORD, _EN_ROMAN), re.IGNORECASE), PART),
    (re.compile(_before("часть", _RU_WORD), re.IGNORECASE), PART),
    (re.compile(_after("(?:серия|эпизод)", _RU_WORD), re.IGNORECASE), EPISODE),
    (re.compile(_before("(?:серия|эпизод)", _RU_WORD), re.IGNORECASE), EPISODE),
    # Any language: (2/5), [2/5] — bracketed, the part no more than the whole, at most 30
    # and never out of ten.
    (re.compile(r"[(\[]\s*(?P<of>\d{1,2})\s*/\s*(?P<whole>\d{1,2})\s*[)\]]"), PART),
)

#: A season said beside an episode: עונה 3, Season 3, Сезон 3. Alone it says nothing.
_SEASON = re.compile(
    r"(?<!\w)(?:ה?עונה|season|сезон)\s*[-–]?\s*(?P<n>\d{1,2})(?!\d)|(?<!\w)(?P<m>\d{1,2})\s+сезон(?!\w)",
    re.IGNORECASE,
)


def _number(match: re.Match[str]) -> int | None:
    found = match.groupdict()
    if found.get("digits"):
        return int(found["digits"])
    if found.get("letter"):
        return _HE_LETTERS[found["letter"]]
    if found.get("heword"):
        return _HE_ORDINALS[found["heword"]]
    if found.get("enword"):
        return _EN_WORDS[found["enword"].lower()]
    if found.get("roman"):
        return _ROMAN[found["roman"].lower()]
    if found.get("ruword"):
        return _RU_WORDS[found["ruword"].lower()]
    if found.get("sxe"):
        return int(found["e"])
    if found.get("of"):
        of, whole = int(found["of"]), int(found["whole"])
        # Out of ten reads as a score ("(7/10)") more often than a ten-part series.
        if 1 <= of <= whole and 2 <= whole <= 30 and whole != 10:
            return of
    return None


def _stem(title: str, start: int, end: int, publisher: str) -> str:
    """The key: the words before the marker, else the publisher, else the words after."""
    before = _SEASON.sub(" ", title[:start])
    folded = fold(before)
    if folded:
        return folded
    if publisher:
        return fold(publisher)
    return fold(_SEASON.sub(" ", title[end:]))


@lru_cache(maxsize=8192)
def of_title(title: str, publisher: str = "") -> Part | None:
    """The part a title says it is, or None: the first marker that names a number. Part 2
    of the falafel video is `Part("מצאתי את הפלאפלים הכי זולים בישראל", 2)`."""
    text = _MARKS.sub("", unicodedata.normalize("NFKC", title or ""))
    if not text.strip():
        return None
    for pattern, kind in _SAID:
        for match in pattern.finditer(text):
            number = _number(match)
            if not number:
                continue
            season = 0
            if match.groupdict().get("sxe"):
                season = int(match.group("s"))
            elif kind == EPISODE:
                said = _SEASON.search(text)
                if said:
                    season = int(said.group("n") or said.group("m"))
            return Part(
                key=_stem(text, match.start(), match.end(), publisher),
                number=number,
                season=season,
                kind=kind,
                publisher=fold(publisher),
            )
    return None


#: A feed's `itunes:type`.
EPISODIC = "episodic"
SERIAL = "serial"


def of_episode(
    title: str,
    publisher: str,
    *,
    number: int = 0,
    season: int = 0,
    episode_type: str = "",
    show_type: str = "",
) -> Part | None:
    """A podcast episode's part, from its feed's own fields where it gives them.

    A trailer or a bonus is never a part. In a feed that says it is episodic, episode
    numbers are a counter, so only part wording in the title counts. Otherwise the feed's
    `itunes:episode` (and season) numbers it, on the show's own key; and without one, the
    title does."""
    if episode_type.strip().lower() in {"trailer", "bonus"}:
        return None
    said = of_title(title, publisher)
    if show_type.strip().lower() == EPISODIC:
        return said if said is not None and said.kind == PART else None
    if number > 0:
        return Part(
            key=fold(publisher) or (said.key if said else ""),
            number=number,
            season=max(0, season),
            kind=EPISODE,
            publisher=fold(publisher),
        )
    return said


def of_entry(english: str, title: str, collection: str = "") -> Part | None:
    """A catalogue row's part: said in its English title ("The Kuzari, Part Two"), else in
    its own ("זווית אופטימלית לקליע חלק 1"), within its collection."""
    return of_title(english or "", collection) or of_title(title or "", collection)


# -- who may be offered what ---------------------------------------------------------


def allowed(part: Part, started: Iterable[Part]) -> bool:
    """Whether a reader who opened `started` may be offered `part`: part 1 always; part N
    once they opened part N−1 of the same series; the first episode of season S once they
    opened an episode of season S−1. A later part whose number is not said, never."""
    if part.first:
        return True
    if not part.key or part.number >= LATER:
        return False
    for one in started:
        if one.key != part.key:
            continue
        if part.number > 1:
            if max(one.season, 1) == max(part.season, 1) and one.number == part.number - 1:
                return True
        elif part.season > 1 and max(one.season, 1) == part.season - 1:
            return True
    return False


def _same_publisher(a: Part, b: Part) -> bool:
    return not a.publisher or not b.publisher or a.publisher == b.publisher


def gate(
    rows: Sequence[dict[str, Any]],
    started: Iterable[Part],
    *,
    part_of: Callable[[Mapping[str, Any]], Part | None] = from_row,
    fits: str = "fit",
    band: str = "band",
) -> list[dict[str, Any]]:
    """`rows`, best first, with every later part the reader may not be offered taken out.

    Where part 1 of that series is among `rows` (so it cleared every rule the list was
    made by) it takes the later part's place, if it fits as well (`fits`, the same fit or
    in the band) and is not placed already; otherwise the series is simply left out.
    Rows that are no part of anything pass through untouched, in order."""
    opened = list(started)
    parts = [part_of(row) for row in rows]
    firsts: dict[str, list[tuple[Part, dict[str, Any]]]] = {}
    for part, row in zip(parts, rows, strict=True):
        if part is not None and part.first and part.key:
            firsts.setdefault(part.key, []).append((part, row))
    out: list[dict[str, Any]] = []
    placed: set[int] = set()

    def place(row: dict[str, Any]) -> None:
        if id(row) not in placed:
            placed.add(id(row))
            out.append(row)

    for part, row in zip(parts, rows, strict=True):
        if part is None or allowed(part, opened):
            place(row)
            continue
        for first, candidate in firsts.get(part.key, []):
            if not _same_publisher(first, part) or id(candidate) in placed:
                continue
            if candidate.get(fits) in (row.get(fits), band):
                place(candidate)
                break
    return out
