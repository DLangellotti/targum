"""Count the Tanakh band table from the Tanakh, once per thing that reads it (targum-internal#156).

`annotate/tanakh.json` is the lemma → band table behind the Tanakh levels (`tanakh/2`)
and the register line (`register/2`). It answers "how much of the Tanakh can I read if I
know this much", and it can only answer that for a word it has under the spelling the
reader will be shown. The first table was counted with Stanza, on the argument that the
same lemmatizer read the book. Within a fortnight nothing read Hebrew with Stanza — the
Open Scriptures tagging read scripture, through `ScriptureLemmatizer`, and DICTA read
everything else — and half the headwords in the Tanakh missed the table. Every miss was
"modern · not in the Tanakh".

**Two keyings, because two things file words.** The tagging names a word by its lexeme
— `בוא` for הֵבִיא, `אלהים` spelled the Masoretic way — and DICTA names it by a modern
dictionary form — `הביא`, `אלוהים`. Those are not spelling variants a table could fold;
they are two vocabularies for one corpus, and a reader meets both: the tagging's on a
Tanakh the lookup lined up, DICTA's on a verse it could not and on every text that is not
scripture. So the Tanakh is counted twice, once through each, each keying banded by its
own coverage, and the two are merged by taking the easier band wherever a spelling is
in both. A word is then in the table under whichever name whatever read it will use, by
construction rather than by guess, and `test_scripture.py` pins the tagging's half.

    python scripts/count_tanakh.py

Writes `src/targum/annotate/tanakh.json` beside the module that reads it. The tagging
half needs the morphology on disk (`targum models fetch scripture`) and takes seconds.
The DICTA half reads three hundred thousand words through a BERT model, which on a
laptop with no GPU is a couple of hours; it is cached one book at a time under
`--cache`, so an interrupted run resumes where it stopped and a recount that changed
only the tagging half does not pay for the model again (`--fresh` to make it). Rename
`tanakh/2` and `register/2` together whenever this is run, because the name is what
re-annotates the shelf, and on the box that is the two-hour rebuild `CLAUDE.md` warns
about.

What is counted, and what is not. Names are in: they are running text, and the question
is how much of a page is familiar. Prefixes are not: the tagging divides `בְּ/רֵאשִׁית` and
the headword is the content piece's, and DICTA reports a prefix as a piece rather than a
lemma. Paragraph markers are out, the way `_verse` leaves them out. The band rule is
`biblical.bands_from_counts`, kept beside the reader so the rule that produced the file
is the rule the module documents.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from targum.annotate import oshb
from targum.annotate.biblical import COVERAGE, bands_from_counts
from targum.annotate.scripture import headword_of, is_section
from targum.models import Segment
from targum.paths import cache_dir
from targum.vocalize.base import strip_nikkud

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "src" / "targum" / "annotate" / "tanakh.json"
DEFAULT_CACHE = cache_dir() / "tanakh-count"

#: What DICTA reports that is not a word to count: punctuation, and what it declines to
#: read at all. Names and numbers stay, as they do in the tagging's half.
NOT_COUNTED = {"PUNCT", "SYM", "X"}


def count_tagging() -> tuple[collections.Counter[str], int]:
    """Headword counts over every tagged book, through the function the lookup uses."""
    counts: collections.Counter[str] = collections.Counter()
    books = 0
    for code in oshb.BOOKS.values():
        seen = False
        for _ref, words in oshb.verses(code):
            seen = True
            for word in words:
                if is_section(word):
                    continue
                headword = headword_of(word)
                if headword:
                    counts[headword] += 1
        books += seen
    return counts, books


def _verses(code: str) -> list[Segment]:
    """One book as DICTA will be handed it: bare text, one verse to a segment, the read
    form where the Masoretes wrote another, which is what the shelf carries too."""
    out: list[Segment] = []
    for index, (ref, words) in enumerate(oshb.verses(code)):
        text = " ".join(word.text for word in words if not is_section(word))
        bare, _ = strip_nikkud(text)
        out.append(
            Segment(
                id=f"{code}-{index:05d}",
                text=bare,
                ref=ref,
                kind="paragraph",
                block_id=code,
                block_index=index,
                index=0,
            )
        )
    return out


def count_dicta(
    cache: Path, fresh: bool, say: Callable[[str], None]
) -> tuple[collections.Counter[str], int, str]:
    """Lemma counts over every book as DICTA reads it, one cached file per book."""
    from targum.annotate.dicta import DictaLemmatizer

    cache.mkdir(parents=True, exist_ok=True)
    lemmatizer = DictaLemmatizer(other=None)
    counts: collections.Counter[str] = collections.Counter()
    books = 0
    for name, code in oshb.BOOKS.items():
        held = cache / f"{code}.json"
        if held.is_file() and not fresh:
            book = json.loads(held.read_text(encoding="utf-8"))
        else:
            verses = _verses(code)
            if not verses:
                continue
            started = time.monotonic()
            read = lemmatizer.lemmas(verses, "he")
            book = collections.Counter(
                token.lemma
                for tokens in read.values()
                for token in tokens
                if token.lemma and token.pos not in NOT_COUNTED
            )
            held.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
            say(f"  {name}: {len(verses)} verses in {time.monotonic() - started:.0f}s")
        counts.update(book)
        books += 1
    return counts, books, lemmatizer.name


def merge(*keyings: dict[str, int]) -> dict[str, int]:
    """One table from several, the easier band standing where a spelling is in more
    than one. Each keying is banded by its own coverage first, so a name the tagging
    files often and DICTA never is not pushed into the tail by the other's silence."""
    out: dict[str, int] = {}
    for bands in keyings:
        for lemma, band in bands.items():
            out[lemma] = min(band, out.get(lemma, band))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--fresh", action="store_true", help="read every book again")
    parser.add_argument(
        "--tagging-only", action="store_true", help="skip the DICTA half (a check, not a table)"
    )
    args = parser.parse_args(argv)

    if not oshb.available():
        print(
            f"The Hebrew Bible tagging is not at {oshb.root()}. "
            "Run `targum models fetch scripture` first.",
            file=sys.stderr,
        )
        return 1

    say = lambda line: print(line, flush=True)  # noqa: E731

    tagged, tagged_books = count_tagging()
    tagged_bands = bands_from_counts(tagged)
    say(f"tagging: {sum(tagged.values())} tokens, {len(tagged)} headwords, {tagged_books} books")

    counted: dict[str, dict[str, object]] = {
        "oshb": {
            "by": f"{oshb.CREDIT}, {oshb.LICENCE}, through ScriptureLemmatizer.headword_of",
            "tokens": sum(tagged.values()),
            "lemmas": len(tagged),
            "books": tagged_books,
        }
    }
    keyings = [tagged_bands]
    if not args.tagging_only:
        read, read_books, annotator = count_dicta(args.cache, args.fresh, say)
        read_bands = bands_from_counts(read)
        say(f"dicta: {sum(read.values())} tokens, {len(read)} lemmas, {read_books} books")
        counted["dicta"] = {
            "by": annotator,
            "tokens": sum(read.values()),
            "lemmas": len(read),
            "books": read_books,
        }
        keyings.append(read_bands)

    bands = merge(*keyings)
    # Stable on disk: by band, then by the word — so a recount that moves nothing changes
    # nothing, and a diff shows the words that moved.
    ordered = sorted(bands.items(), key=lambda pair: (pair[1], pair[0]))
    table = {
        "corpus": (
            f"Tanakh, {tagged_books} books, from the Open Scriptures Hebrew Bible morphology "
            f"({oshb.LICENCE}): counted under the headwords ScriptureLemmatizer files by"
            + (", and again under the lemmas DICTA reads, merged" if "dicta" in counted else "")
        ),
        "tokens": sum(tagged.values()),
        "lemmas": len(bands),
        "coverage": list(COVERAGE),
        "counted": counted,
        "bands": dict(ordered),
    }
    args.out.write_text(json.dumps(table, ensure_ascii=False) + "\n", encoding="utf-8")

    by_band = collections.Counter(bands.values())
    say(f"{len(bands)} entries → {args.out}")
    for band in sorted(by_band):
        say(f"  band {band}: {by_band[band]:>5} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
