"""The words check on arrival (design.md §12, "The arrival asks which words you know",
2026-11-01; targum-internal#613).

A new Hebrew reader is shown Hebrew words in two rounds and taps the ones they know.
Round one is the same 18 real words for everybody, three from each of six frequency
bands, and four made-up words. Round two is fifteen more from the three bands around
where round one's yeses ran out, and four more made-up words. Nothing is scored or
shown back: the ticks are evidence for `estimate.py`, and the made-up words ticked
measure how often this reader ticks a word they cannot know.

**Both rounds follow from the ticks alone.** Round one is fixed and round two is a
function of round one's ticks, so what the reader was shown, and so what they left
unticked, is worked out again from what they ticked. That is all an account keeps of
the check: the words the reader marked, and when (privacy notice clause 3.2, "words and
phrases marked by the Data Subject"). A word ticked here is never put on the reader's
list. `VERSION` names these lists; a change to any of them is a new version, and a
check taken against an older one is read by the lists it was taken against or not at
all, never by today's.

**The words are fixed rather than drawn**, and the made-up ones were vetted one by one
by the Hebrew linguistics seat (ling-he, 2026-11-01): none is in wordfreq's 592,000
Hebrew forms, in the 104,000 verb forms of `annotate/paradigms.json.gz` or in the Tanakh;
none becomes a word by restoring a ו or a י (which is how מרגזת is מרוגזת, "annoyed",
written short), by losing a prefix letter or by losing an ending; none is one letter from
a word in wordfreq's commonest 30,000 that a learner would confuse it with; and none has
the shape מ+root+ת, the feminine participle written short, which is how the check before
this let מסגפת, a real word, through. Each is a real pattern on a real root (taCCuCa as
in תחבורה, taCCoCet as in תלבושת) that Hebrew does not happen to use. The real words
include four of the same shape, so a ת at the start gives nothing away.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: The lists' name. A check is kept with it and read back only by the lists it names.
VERSION = "2026-11-01"

#: The language the check is in. The words are Hebrew and the estimate's difficulty is
#: Hebrew's frequency list; every other language's arrival has no check.
LANGUAGE = "he"

#: Six bands, commonest first, by place in wordfreq's Hebrew list: about 50–160,
#: 200–470, 800–1,200, 1,700–3,500, 5,000–10,000 and 12,000–19,000. Each word is the
#: commonest spelling of its dictionary form, unpointed, with no prefix letter, and not a
#: name. The first three of each band are round one; the other five are round two's.
BANDS: tuple[tuple[str, ...], ...] = (
    ("עכשיו", "תמיד", "דרך", "יום", "בית", "זמן", "מקום", "גדול"),
    ("יפה", "כסף", "לילה", "עבודה", "חשוב", "קטן", "מים", "ערב"),
    ("תקופה", "חדר", "טעות", "שבוע", "שמחה", "סיבה", "שחור", "רחוק"),
    ("תחבורה", "רכבת", "חלום", "מתנה", "זקן", "כוכב", "מכתב", "חשמל"),
    ("תערוכה", "נשימה", "ויכוח", "עוצמה", "בושה", "אזהרה", "דמיון", "מצור"),
    ("עיירה", "ספסל", "הפוגה", "זעיר", "מחסן", "אכזבה", "רציף", "נזיר"),
)

#: How many of each band round one shows.
FIRST = 3

#: How many bands round two draws from, and how many of each.
WINDOW = 3
SECOND = 5

#: Made-up words, vetted (see above and ling-he's note of 2026-11-01). The first four are
#: round one's; round two takes four of the other twelve, by where its bands start, so
#: no reader sees one twice.
MADE_UP: tuple[str, ...] = (
    "תלבוטה",
    "תכסומת",
    "תצרובה",
    "תזלוגת",
    "תקמוטה",
    "תשגורת",
    "תגלושה",
    "תקדוחת",
    "תרפודה",
    "תגרוסת",
    "תדגורה",
    "תצבוטת",
    "תפלוטה",
    "תדרוסת",
    "תזרוקה",
    "תבלומת",
)

#: How many made-up words each round shows.
MADE_UP_EACH = 4

#: The guess rate before the made-up words say anything: `estimate.CLAIM_GUESS`, worth
#: this many made-up words. Eight answers move it most of the way.
GUESS_PRIOR = 0.15
GUESS_PRIOR_WEIGHT = 2.0


def first_round() -> tuple[list[str], list[str]]:
    """Round one: (real words, made-up words), the same for everybody."""
    real = [word for band in BANDS for word in band[:FIRST]]
    return real, list(MADE_UP[:MADE_UP_EACH])


def edge(ticked: Iterable[str]) -> int:
    """The band where round one's yeses ran out: the last band in which the reader ticked
    at least half of round one's words. Nought where they ticked none anywhere."""
    said = set(ticked)
    out = 0
    for at, band in enumerate(BANDS):
        yes = sum(1 for word in band[:FIRST] if word in said)
        if yes * 2 >= FIRST:
            out = at
    return out


def window(at: int) -> int:
    """The first of the `WINDOW` bands round two draws from: the edge and one each side,
    kept inside the six."""
    return max(0, min(at - 1, len(BANDS) - WINDOW))


def second_round(ticked: Iterable[str]) -> tuple[list[str], list[str]]:
    """Round two, given round one's ticks: (real words, made-up words)."""
    start = window(edge(ticked))
    real = [word for band in BANDS[start : start + WINDOW] for word in band[FIRST : FIRST + SECOND]]
    rest = MADE_UP[MADE_UP_EACH:]
    made = [rest[(start * 3 + k) % len(rest)] for k in range(MADE_UP_EACH)]
    return real, made


def every_word() -> frozenset[str]:
    """Every word either round can show."""
    return frozenset([*(word for band in BANDS for word in band), *MADE_UP])


def band_of(word: str) -> int:
    """A real word's band, or -1 for a made-up word or a word not in the check."""
    for at, band in enumerate(BANDS):
        if word in band:
            return at
    return -1


def shown(ticked: Iterable[str]) -> tuple[list[str], list[str]]:
    """Everything both rounds showed a reader who ticked these: (real, made-up)."""
    said = list(ticked)
    one_real, one_made = first_round()
    first = set(one_real) | set(one_made)
    two_real, two_made = second_round(word for word in said if word in first)
    return [*one_real, *two_real], [*one_made, *two_made]


def kept(ticked: Iterable[str]) -> list[str]:
    """What an account keeps of a check: the ticked words the two rounds could have
    shown this reader, in the order they were shown, each once. A word round two would
    not have shown, or no round has, is dropped rather than refused: the page and this
    agree, and anything else did not come from the page."""
    said = set(ticked)
    real, made = shown(said)
    return [word for word in [*real, *made] if word in said]


def guess(made_ticked: int, made_shown: int) -> float:
    """How often this reader ticks a word they do not know: the made-up words they ticked,
    pulled towards `GUESS_PRIOR` by `GUESS_PRIOR_WEIGHT` made-up words' worth."""
    return (made_ticked + GUESS_PRIOR * GUESS_PRIOR_WEIGHT) / (made_shown + GUESS_PRIOR_WEIGHT)


def answers(ticked: Iterable[str]) -> tuple[list[str], list[str], float]:
    """What a kept check says: (real words known, real words not known, guess rate)."""
    said = set(ticked)
    real, made = shown(said)
    known = [word for word in real if word in said]
    unknown = [word for word in real if word not in said]
    return known, unknown, guess(sum(1 for word in made if word in said), len(made))


def page_data() -> dict[str, Any]:
    """What `/welcome` needs to draw both rounds and work out round two itself, by the
    same rules as `second_round` (`tests/test_check.py` holds the two together)."""
    return {
        "version": VERSION,
        "language": LANGUAGE,
        "bands": [list(band) for band in BANDS],
        "first": FIRST,
        "window": WINDOW,
        "second": SECOND,
        "madeUp": list(MADE_UP),
        "madeUpEach": MADE_UP_EACH,
    }
