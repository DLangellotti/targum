"""File targum's Onkelos starter: a week of Onkelos for a reader with Hebrew and no Aramaic
(targum-internal#530, part 1).

One of targum's own playlists (`"swipe": true`, design.md §12, "A playlist is swiped,
and one press takes the set", 2026-09-23), seven rows long, one a day. Every row is a
short passage of Genesis in Hebrew, with Onkelos under each verse and the Metsudah
English beside it, the same three editions the `genesis` row carries. Nothing is
written: every Aramaic word is a word of the public-domain Onkelos already on the shelf
(design.md §12, "Aramaic is never written by a model", 2026-10-25), and the passages are
chosen, never edited. A row costs nothing to build, because all three sides are
published and pair by their verse numbers, and `targum seed` builds every member of a
swipe set on the shared shelf.

What each day is for comes from ling-arc's plan of 2026-10-25 (rung 0): the ־א ending,
the sound shifts ש→ת, ז→ד and צ→ע, each on a real pair, and the forty function words met
in the lines rather than as a list. The last day is Joseph's dreams, read whole, and its
line hands the reader on to the week's portion, where Onkelos already stands beside every
verse. Each claim a line makes about a word is pinned to a verse below, and
`tests/test_onkelos_starter.py` reads each one in that verse of the saved edition.

The catalogue is private data, so this runs on the machine that holds it. Rows go
through `promote.merge_into_catalogue`, the one door the catalogue grows through, and the
collection is written beside them the way `parasha entries --write` writes its own. It
prints what it would do unless given `--write`, and running it twice changes nothing.

    PYTHONPATH=src python scripts/file_onkelos_starter.py
    PYTHONPATH=src python scripts/file_onkelos_starter.py --write

`--fixture PATH` fetches the passages from Sefaria (free) and saves both sides of every
verse, which is how `tests/fixtures/sefaria/onkelos-starter.json` was made.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

#: The set's id in the catalogue file.
SET = "onkelos-starter"


@dataclass(frozen=True)
class Day:
    """One row of the set: a passage of Genesis, and the one line it is read with."""

    number: int
    #: As Sefaria takes it, so it is the row's source and both renderings' too.
    ref: str
    #: The Hebrew citation, which is what the row shows.
    title: str
    blurb: str
    #: The pairs this day's line names, as (verse, Aramaic, Hebrew), each word spelled
    #: as that verse spells it, with its vowels and without its accents.
    pairs: tuple[tuple[str, str, str], ...] = ()

    @property
    def id(self) -> str:
        return f"{SET}-{self.number}"

    @property
    def english(self) -> str:
        return f"Day {self.number} · {self.ref.replace('-', '–')}"


DAYS: tuple[Day, ...] = (
    Day(
        1,
        "Genesis 1:1-5",
        "בראשית א, א-ה",
        "Most nouns end in ־א, and the ־א means “the”, so אַרְעָא is הָאָרֶץ. יָת does the work of אֶת.",
        (
            ("Genesis 1:1", "אַרְעָא", "הָאָרֶץ"),
            ("Genesis 1:1", "שְׁמַיָּא", "הַשָּׁמַיִם"),
            ("Genesis 1:1", "יָת", "אֵת"),
        ),
    ),
    Day(
        2,
        "Genesis 1:6-19",
        "בראשית א, ו-יט",
        "A plural noun ends in ־יָּא, so the stars are כּוֹכְבַיָּא. "
        "Hebrew ש is often ת in Aramaic, and the second day is יוֹם תִּנְיָן.",
        (
            ("Genesis 1:16", "כּוֹכְבַיָּא", "הַכּוֹכָבִים"),
            ("Genesis 1:8", "תִּנְיָן", "שֵׁנִי"),
        ),
    ),
    Day(
        3,
        "Genesis 1:20-2:3",
        "בראשית א, כ - ב, ג",
        "דִּי does the work of אֲשֶׁר. From here on you'll meet it every day.",
        (("Genesis 1:21", "דִּי", "אֲשֶׁר"),),
    ),
    Day(
        4,
        "Genesis 2:4-14",
        "בראשית ב, ד-יד",
        "The four rivers of Eden. Hebrew ז is often ד, so the gold of Havilah is דַּהֲבָא.",
        (("Genesis 2:11", "דַּהֲבָא", "הַזָּהָב"),),
    ),
    Day(
        5,
        "Genesis 3:1-13",
        "בראשית ג, א-יג",
        "The serpent and the woman talk. לָא is לֹא, and אֲרֵי is כִּי, for “because” and for “that”.",
        (
            ("Genesis 3:1", "לָא", "לֹא"),
            ("Genesis 3:5", "אֲרֵי", "כִּי"),
        ),
    ),
    Day(
        6,
        "Genesis 6:9-22",
        "בראשית ו, ט-כב",
        "Noah builds the ark. Hebrew ש is ת again, as in his three sons, תְּלָתָא בְנִין. "
        "And Hebrew צ can be ע, so the ark's wood is אָעִין.",
        (
            ("Genesis 6:10", "תְּלָתָא", "שְׁלֹשָׁה"),
            ("Genesis 6:14", "אָעִין", "עֲצֵי"),
        ),
    ),
    Day(
        7,
        "Genesis 37:1-11",
        "בראשית לז, א-יא",
        "Joseph's dreams, read whole with the Hebrew beside them. "
        "Next, read this week's portion. Onkelos is under every verse there too.",
    ),
)

#: The sound shifts the set teaches, each on the real pair it first meets it in, as
#: (Hebrew letter, Aramaic letter, verse, Aramaic word, Hebrew word). Only these three:
#: no passage here has a clean צ→ט pair, and none is made up to show one.
SHIFTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("צ", "ע", "Genesis 1:1", "אַרְעָא", "הָאָרֶץ"),
    ("ש", "ת", "Genesis 1:8", "תִּנְיָן", "שֵׁנִי"),
    ("ש", "ת", "Genesis 1:13", "תְּלִיתָאִי", "שְׁלִישִׁי"),
    ("ז", "ד", "Genesis 1:27", "דְּכַר", "זָכָר"),
    ("ז", "ד", "Genesis 2:11", "דַּהֲבָא", "הַזָּהָב"),
    ("ש", "ת", "Genesis 6:10", "תְּלָתָא", "שְׁלֹשָׁה"),
    ("צ", "ע", "Genesis 6:14", "אָעִין", "עֲצֵי"),
    ("ש", "ת", "Genesis 6:15", "תְּלַת", "שְׁלֹשׁ"),
    ("ז", "ד", "Genesis 6:19", "דְּכַר", "זָכָר"),
)

#: The forty function words a reader meets in the set's lines, each by the name the
#: frequency list counts it under (`annotate.aramaic_frequency`, targum#936): the hand
#: table's headword with its points off. Chosen from the top of that list, and only words
#: that are not nouns of the story.
FUNCTION_WORDS: tuple[str, ...] = (
    "ית", "על", "לא", "אמר", "מן", "כל", "הוה", "קדם", "די", "עם",
    "ארי", "עבד", "הוא", "עד", "אנא", "חד", "יהב", "הא", "לות", "תמן",
    "תרין", "הדין", "כד", "דין", "לית", "את", "מה", "כן", "כען", "אף",
    "אלין", "היא", "גו", "או", "דא", "בין", "בדיל", "עוד", "אינון", "אנחנא",
)  # fmt: skip

#: The set's name and line.
TITLE = "שבוע ראשון באונקלוס"
ENGLISH = "A first week of Onkelos"
BLURB = (
    "Read Onkelos under the Hebrew, one short passage a day for a week. "
    "You need Hebrew and no Aramaic."
)

#: The editions every row carries beside its Hebrew: the `genesis` row's English and
#: Onkelos, by the same names, so a row reads as part of that book.
METSUDAH = "Metsudah Chumash, Metsudah Publications, 2009"


def row(day: Day) -> dict[str, Any]:
    """A catalogue row for one day."""
    return {
        "id": day.id,
        "title": day.title,
        "english": day.english,
        "author": "בראשית",
        "language": "he",
        "source": f"sefaria:{day.ref}",
        "blurb": day.blurb,
        "tags": ["tanakh"],
        "kind": "prose",
        "register": "biblical",
        "translations": [
            {
                "name": METSUDAH,
                "source": f"sefaria:en:{day.ref}",
                "note": "A linear translation, made to be read beside the Hebrew.",
                "publisher": "Metsudah Publications",
                "licence": "CC-BY",
            },
            {
                "name": "Targum Onkelos",
                "source": f"sefaria:arc:{day.ref}",
                "note": "The Aramaic translation read beside the Torah, verse for verse.",
                "publisher": "Sefaria",
                "licence": "Public Domain",
            },
        ],
        "licence": "Public Domain",
        "credit": "Tanach with Ta'amei Hamikra, via Sefaria",
        "licence_url": "http://www.tanach.us/Tanach.xml",
    }


def collection() -> dict[str, Any]:
    """The set itself, in reading order, behind the Aramaic door."""
    return {
        "id": SET,
        "title": TITLE,
        "english": ENGLISH,
        "blurb": BLURB,
        "members": [day.id for day in DAYS],
        "ordered": True,
        "door": "targum",
        "swipe": True,
    }


#: Genesis by chapter, as many verses as each has in the Hebrew and in Onkelos (the same
#: in all fifty, `sefaria.ONKELOS`), for the chapters the set reads.
LENGTHS = {1: 31, 2: 25, 3: 24, 6: 22, 37: 36}


def verses(ref: str) -> list[str]:
    """Every verse a reference covers, as `Genesis 1:20` … `Genesis 2:3`."""
    from targum.parasha.cut import parse_place

    book, _, span = ref.rpartition(" ")
    first, _, last = span.partition("-")
    start = parse_place(first)
    end = parse_place(last if ":" in last else f"{first.split(':')[0]}:{last}")
    if start is None or end is None:
        raise ValueError(f"not a verse range: {ref}")
    out: list[str] = []
    chapter, verse = start.chapter, start.verse
    while (chapter, verse) <= (end.chapter, end.verse):
        out.append(f"{book} {chapter}:{verse}")
        verse += 1
        if verse > LENGTHS[chapter]:
            chapter, verse = chapter + 1, 1
    return out


def fixture(path: Path) -> None:
    """Fetch every verse of the set from Sefaria, both sides, and save them."""
    from targum.ingest.fetch import sefaria

    saved: dict[str, dict[str, str]] = {}
    for day in DAYS:
        for language in ("he", "arc"):
            document = sefaria.document_from_payload(
                sefaria._payload(day.ref, language), day.ref, language
            )
            for block in document.blocks:
                if block.ref:
                    ref = block.ref.removeprefix("Onkelos ")
                    saved.setdefault(ref, {})[language] = block.text
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(saved)} verses saved to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--write", action="store_true", help="merge into the catalogue")
    parser.add_argument("--fixture", type=Path, help="save the passages from Sefaria here")
    args = parser.parse_args()
    if args.fixture:
        fixture(args.fixture)
        return

    from targum import catalogue as catalogue_module
    from targum.paths import write_atomic
    from targum.promote import merge_into_catalogue

    path = catalogue_module.catalogue_path()
    if path is None:
        raise SystemExit("No catalogue: set TARGUM_CATALOGUE or put one at ~/.targum.")
    rows = [row(day) for day in DAYS]
    group = collection()
    print(f"{len(rows)} rows and the {SET!r} set, {sum(len(verses(d.ref)) for d in DAYS)} verses")
    for one in rows:
        print(f"  {one['id']}  {one['source']}")
    if not args.write:
        print("Nothing written. Add --write to merge into", path)
        return
    for one in rows:
        merge_into_catalogue(one)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    groups = [g for g in loaded.get("collections") or [] if g.get("id") != SET]
    held: dict[str, Any] = next(
        (g for g in loaded.get("collections") or [] if g.get("id") == SET), {}
    )
    # A name or a line somebody later wrote on the set stays; the members are this file's.
    groups.append({**group, **held, "members": group["members"], "swipe": True})
    loaded["collections"] = groups
    write_atomic(path, json.dumps(loaded, ensure_ascii=False, indent=2) + "\n")
    print(f"Merged {len(rows)} rows and the set into {path}.")


if __name__ == "__main__":
    main()
