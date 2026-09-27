"""Count every chapter of the Tanakh for the map (targum-internal#144).

The map shades 929 squares by how much of each chapter a reader would understand, and
the test beside it estimates that from thirty words. Both ask the same thing of every
chapter — which dictionary forms it is made of, and how often each comes round — and the
answer is fixed, because the Tanakh is. So it is counted once, here, and shipped.

    python scripts/tanakh_map.py

Writes `src/targum/annotate/tanakh_chapters.json`, which `coverage.chapter_map` and
`coverage.chapter_estimate` read. Needs the morphology on disk (`targum models fetch
scripture`) and takes seconds. No model is asked anything and nothing is bought.

**Counted from the Open Scriptures tagging alone, so the file is public.** Every lemma
in it is `headword_of` a hand-tagged word — the same function the scripture lookup files
a reader's words under, so a word marked known while reading Genesis is the key it is
looked up by here. That tagging is CC BY 4.0 and credited in the file and in
`LICENSING.md`, as `tanakh.json`'s own half of it is. Nothing is read off the built
shelf, which is private: the shelf would add nothing but the ~0.7% of verses the lookup
could not line up and DICTA read instead, and the price of those would be a file that
could not sit in the repository.

**What a running word is.** The words a learner has to know, as `coverage.lemmas` counts
them: a name is not one (`Np`, which `part_of` reads as `PROPN`), and a paragraph marker
is typography. Everything else is — prefixes are not separate words, because the tagging
files a word under its content piece.

**The Aramaic is counted as Aramaic.** Daniel 2:4b–7:28, Ezra 4:8–6:18 and 7:12–26,
Jeremiah 10:11 and two words of Genesis 31:47 are not Hebrew, and a Hebrew list must not
be credited or blamed for them. Each word is filed under its language, each language has
its own frequency ranking, and a chapter's language is whichever carries most of its
running words — so Daniel 2 and Ezra 4 and 7 are Aramaic chapters and Jeremiah 10 is a
Hebrew one with a verse left out of its Hebrew count. (Ezra 7 is 245 Aramaic words to
129 Hebrew; Daniel 2 is 760 to 38.) The spans are a fixed table until
language per block exists (#66); the file carries the language as data, so the map need
not know which books have any.

**The bands are ranks, as the card draws them.** Ranks 1–100, 101–300, 301–600, 601–1,000,
1,001–1,500, 1,501–2,500, 2,501–4,000 and the rest, over each language's own count. A
chapter's profile is its running words in each band — eight small numbers — which is all
the test needs to shade it from a result, with no request.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from bisect import bisect_right
from collections.abc import Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.annotate import oshb  # noqa: E402
from targum.annotate.scripture import headword_of, is_section, part_of  # noqa: E402

DEFAULT_OUT = (
    Path(__file__).resolve().parents[1] / "src" / "targum" / "annotate" / "tanakh_chapters.json"
)

#: The file's shape. `coverage.read_map` refuses any other.
VERSION = 1

#: Where each band ends, as a frequency rank: band 1 is ranks 1–100 and the last band is
#: everything past 4,000. The card's cuts (targum-internal#144, "the two modes").
CUTS = (100, 300, 600, 1000, 1500, 2500, 4000)

#: The Hebrew order and the three parts, which is how the map lays the books out. The
#: names are the shelf's, the ones `oshb.BOOKS` is keyed by and a verse ref carries.
ORDER: tuple[tuple[str, str], ...] = (
    *((name, "torah") for name in ("Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy")),
    *(
        (name, "prophets")
        for name in (
            "Joshua",
            "Judges",
            "I Samuel",
            "II Samuel",
            "I Kings",
            "II Kings",
            "Isaiah",
            "Jeremiah",
            "Ezekiel",
            "Hosea",
            "Joel",
            "Amos",
            "Obadiah",
            "Jonah",
            "Micah",
            "Nahum",
            "Habakkuk",
            "Zephaniah",
            "Haggai",
            "Zechariah",
            "Malachi",
        )
    ),
    *(
        (name, "writings")
        for name in (
            "Psalms",
            "Proverbs",
            "Job",
            "Song of Songs",
            "Ruth",
            "Lamentations",
            "Ecclesiastes",
            "Esther",
            "Daniel",
            "Ezra",
            "Nehemiah",
            "I Chronicles",
            "II Chronicles",
        )
    ),
)

#: The Aramaic of the Hebrew Bible, as (book code, chapter, first verse, first word, last
#: verse): from that word of the first verse through the end of the last. A first word
#: other than 0 is a switch mid-verse — Daniel 2:4 turns to Aramaic after "in Aramaic",
#: its fifth word. Genesis 31:47 is two words inside a verse, so it has a span of its own
#: that ends where it does (`_LAST_WORD`). Those two, יְגַר שָׂהֲדוּתָא, are a place name the
#: tagging marks `Np`, so they are not running words in either language and the span
#: changes no count today; it is here so the table is the whole of the Aramaic.
ARAMAIC: tuple[tuple[str, int, int, int, int], ...] = (
    ("Gen", 31, 47, 3, 47),
    ("Jer", 10, 11, 0, 11),
    ("Dan", 2, 4, 4, 49),
    ("Dan", 3, 1, 0, 999),
    ("Dan", 4, 1, 0, 999),
    ("Dan", 5, 1, 0, 999),
    ("Dan", 6, 1, 0, 999),
    ("Dan", 7, 1, 0, 28),
    ("Ezra", 4, 8, 0, 999),
    ("Ezra", 5, 1, 0, 999),
    ("Ezra", 6, 1, 0, 18),
    ("Ezra", 7, 12, 0, 26),
)

#: Where a span stops before its last verse ends: יְגַר שָׂהֲדוּתָא, and back to Hebrew.
_LAST_WORD = {("Gen", 31, 47): 4}


def language_of(osis: str, position: int) -> str:
    """`he` or `arc` for one word, by where it sits: `Dan.2.4` and its index in the verse."""
    code, chapter, verse = osis.split(".")
    c, v = int(chapter), int(verse)
    for book, at, first, word, last in ARAMAIC:
        if book != code or at != c or not first <= v <= last:
            continue
        if v == first and position < word:
            continue
        stop = _LAST_WORD.get((book, at, v))
        if stop is not None and position > stop:
            continue
        return "arc"
    return "he"


def running(words: Iterable[oshb.Word]) -> Iterable[tuple[int, str]]:
    """The running words of one verse as (position, dictionary form): what a learner has
    to know, with names and paragraph markers left out. The position is the word's index
    in the tagged verse, which is what the Aramaic table counts in."""
    for position, word in enumerate(words):
        if is_section(word) or part_of(word.code) == "PROPN":
            continue
        lemma = headword_of(word)
        if lemma:
            yield position, lemma


def band(rank: int) -> int:
    """The band of a zero-based frequency rank, 0 to `len(CUTS)`."""
    return bisect_right(CUTS, rank)


def build(verses: Iterable[tuple[str, tuple[oshb.Word, ...]]]) -> dict[str, object]:
    """The map's file from tagged verses, `(osis, words)` in any order.

    Pure, so a test can hand it three verses: the reading from disk is `main`'s.
    """
    names = {code: name for name, code in oshb.BOOKS.items()}
    # chapter ref -> language -> lemma -> running count
    counted: dict[str, dict[str, collections.Counter[str]]] = {}
    verse_count: collections.Counter[str] = collections.Counter()
    totals: dict[str, collections.Counter[str]] = {}
    for osis, words in verses:
        code, chapter, _verse = osis.split(".")
        name = names.get(code)
        if name is None:
            continue
        ref = f"{name} {int(chapter)}"
        verse_count[ref] += 1
        held = counted.setdefault(ref, {})
        for position, lemma in running(words):
            language = language_of(osis, position)
            held.setdefault(language, collections.Counter())[lemma] += 1
            totals.setdefault(language, collections.Counter())[lemma] += 1

    # Each language ranked by its own count, commonest first and ties by spelling, so a
    # recount that moves nothing writes the same file.
    ranked = {
        language: [lemma for lemma, _ in sorted(count.items(), key=lambda p: (-p[1], p[0]))]
        for language, count in sorted(totals.items())
    }
    rank = {
        language: {lemma: n for n, lemma in enumerate(table)} for language, table in ranked.items()
    }

    def chapter_order(ref: str) -> tuple[int, int]:
        book, _, number = ref.rpartition(" ")
        return next(i for i, (name, _) in enumerate(ORDER) if name == book), int(number)

    chapters: dict[str, dict[str, object]] = {}
    for ref in sorted(counted, key=chapter_order):
        parts = counted[ref]
        tokens = {language: sum(count.values()) for language, count in parts.items()}
        entry: dict[str, object] = {
            "verses": verse_count[ref],
            # Whichever carries most of the chapter; Hebrew where they tie or it is empty.
            "language": max(sorted(tokens), key=lambda lang: (tokens[lang], lang == "he"))
            if tokens
            else "he",
        }
        for language in sorted(parts):
            at = rank[language]
            by_band = [0] * (len(CUTS) + 1)
            flat: list[int] = []
            for lemma, count in sorted(parts[language].items(), key=lambda p: at[p[0]]):
                by_band[band(at[lemma])] += count
                flat += [at[lemma], count]
            entry[language] = {"tokens": tokens[language], "bands": by_band, "words": flat}
        chapters[ref] = entry

    present = collections.Counter(ref.rpartition(" ")[0] for ref in chapters)
    return {
        "version": VERSION,
        "corpus": (
            "Tanakh, every chapter, from the Open Scriptures Hebrew Bible morphology "
            f"({oshb.LICENCE}): running words under the headwords ScriptureLemmatizer files "
            "by, names left out, Aramaic counted apart"
        ),
        "credit": oshb.CREDIT,
        "licence": oshb.LICENCE,
        "cuts": list(CUTS),
        "words": ranked,
        "books": [[name, part, present[name]] for name, part in ORDER if present[name]],
        "chapters": chapters,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not oshb.available():
        print(
            f"The Hebrew Bible tagging is not at {oshb.root()}. "
            "Run `targum models fetch scripture` first.",
            file=sys.stderr,
        )
        return 1

    made = build(
        (osis, words)
        for code in dict.fromkeys(oshb.BOOKS.values())
        for osis, words in oshb.verses(code)
    )
    # One line: the file is read by a machine, and a diff of it is a diff of numbers.
    args.out.write_text(
        json.dumps(made, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    chapters = made["chapters"]
    assert isinstance(chapters, dict)
    languages = collections.Counter(entry["language"] for entry in chapters.values())
    words = made["words"]
    assert isinstance(words, dict)
    print(f"{len(chapters)} chapters → {args.out} ({args.out.stat().st_size:,} bytes)")
    for language, table in words.items():
        print(f"  {language}: {languages[language]} chapters, {len(table)} dictionary forms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
