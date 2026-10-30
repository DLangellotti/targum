"""The bible register's backfill (targum-internal#578): the Tanakh's counts, which
`scripts/count_tanakh.py` used to work out and throw away, kept as contributions.

Both keyings go in, each under its own table so the bible register's `words` total is
one count of the book and not two:

- **`words`**, the DICTA lemmas, read from the per-book cache `count_tanakh.py` already
  keeps. These are the reader's own word identity, the key every other register's
  `words` rows are filed under, and so the keying a yardstick reads. The cache holds a
  lemma and a count and nothing else, so the variant is empty: no part of speech was
  kept, and none is guessed here.
- **`lexemes`**, the Open Scriptures headwords, through `scripture.headword_of`, the
  function the lookup files a word by. The variant is a Universal POS worked out from the
  tagging's own code, which people made, so it is the better answer where it exists.

The Aramaic chapters (`ARAMAIC_VERSES`) are counted under the variant `ARAMAIC`, so the
yardstick can leave them out and the totals still add up to the whole book. The DICTA
cache holds a book and not its verses, so its Aramaic share is the Aramaic verses read
once more on their own (`count_tanakh.py` caches it beside the books); what that read
gives is taken out of the book's count, never more than the book held.

Nothing here writes `tanakh.json`: `tanakh/2` and `register/2` keep their names, and no
text is re-annotated. A row holds a lemma, a variant and a count, never a verse.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from .registers import BIBLE
from .store import Contribution, Store

if TYPE_CHECKING:
    from ..annotate.oshb import Word

#: Where the counts came from, on every row.
SOURCE = "oshb-wlc"
LICENCE = "CC BY 4.0 (morphology); WLC public domain"

#: DICTA's lemmas go in `words`, beside every other register's.
WORDS = "words"
#: The Open Scriptures headwords, a table of their own so no total counts the book twice.
LEXEMES = "lexemes"
TABLES = (WORDS, LEXEMES)

#: The variant an Aramaic word is counted under, whichever keying counted it.
ARAMAIC = "arc"

#: The version of this counting rule. A change to what is counted is a new number.
RULE = "bible/1"

#: A chapter's last verse, whatever it is: the Masoretic and English numberings of
#: Daniel 3–6 differ, and what is meant is the whole chapter in either.
_END = 999

#: The Aramaic of the Hebrew Bible, verse by verse, as (book, chapter, first, last) with
#: a range running across chapters given chapter by chapter. Daniel 2:4 opens in Hebrew
#: ("and the Chaldeans spoke to the king in Aramaic") and is counted Aramaic whole, as is
#: Genesis 31:47 for its two words: a verse is the smallest thing the tagging addresses.
_ARAMAIC_RANGES: tuple[tuple[str, int, int, int], ...] = (
    ("Gen", 31, 47, 47),
    ("Jer", 10, 11, 11),
    ("Dan", 2, 4, _END),
    ("Dan", 3, 1, _END),
    ("Dan", 4, 1, _END),
    ("Dan", 5, 1, _END),
    ("Dan", 6, 1, _END),
    ("Dan", 7, 1, _END),
    ("Ezra", 4, 8, _END),
    ("Ezra", 5, 1, _END),
    ("Ezra", 6, 1, 18),
    ("Ezra", 7, 12, 26),
)

_REF = re.compile(r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)$")


def is_aramaic(ref: str) -> bool:
    """Whether an OSIS reference (`Dan.2.4`) is one of the Aramaic verses."""
    found = _REF.match(ref.strip())
    if found is None:
        return False
    book, chapter, verse = found.group(1), int(found.group(2)), int(found.group(3))
    return any(
        book == b and chapter == c and first <= verse <= last
        for b, c, first, last in _ARAMAIC_RANGES
    )


#: The tagging's part-of-speech letter (its code with the language letter taken off) as
#: Universal POS, the variant every other register's `words` rows carry. Particles split
#: by their second letter, where the code says which.
_UPOS = {
    "A": "ADJ",
    "C": "CCONJ",
    "D": "ADV",
    "N": "NOUN",
    "P": "PRON",
    "R": "ADP",
    "S": "PRON",
    "T": "PART",
    "V": "VERB",
}
_PARTICLES = {"Td": "DET", "Tj": "INTJ", "Tn": "PART", "To": "PART"}


def upos(code: str) -> str:
    """A Universal POS for one piece's code: `Np…` is a name, `Td` the article."""
    if code.startswith("Np"):
        return "PROPN"
    if code[:2] in _PARTICLES:
        return _PARTICLES[code[:2]]
    return _UPOS.get(code[:1], "")


def count_lexemes(verses: Iterable[tuple[str, Iterable[Word]]]) -> Counter[tuple[str, str]]:
    """One book's headwords, keyed (headword, variant), the way `count_tanakh.py`'s
    tagging half counts them: paragraph markers out, a word with no headword out."""
    from ..annotate.scripture import headword_of, is_section

    counts: Counter[tuple[str, str]] = Counter()
    for ref, words in verses:
        aramaic = is_aramaic(ref)
        for word in words:
            if is_section(word):
                continue
            headword = headword_of(word)
            if headword:
                counts[(headword, ARAMAIC if aramaic else upos(word.code))] += 1
    return counts


def split_lemmas(
    book: Mapping[str, int], aramaic: Mapping[str, int] | None
) -> Counter[tuple[str, str]]:
    """One book's DICTA lemmas, keyed (lemma, variant): what the Aramaic read gave under
    `ARAMAIC`, the rest under the empty variant. Never more Aramaic than the book held,
    so the two always add up to the book's own count."""
    out: Counter[tuple[str, str]] = Counter()
    for lemma, n in book.items():
        taken = min(int(n), int((aramaic or {}).get(lemma, 0)))
        if n - taken:
            out[(lemma, "")] = int(n) - taken
        if taken:
            out[(lemma, ARAMAIC)] = taken
    return out


def contribution(table: str, code: str, tool: str) -> Contribution:
    """What one book's count in one keying is filed as."""
    return Contribution(
        table=table,
        register=BIBLE,
        unit=f"{SOURCE}:{code}",
        source=SOURCE,
        licence=LICENCE,
        tool=tool,
        rule=RULE,
    )


def write(store: Store, table: str, code: str, tool: str, counts: Counter[tuple[str, str]]) -> bool:
    """Write one book's count in one keying; False where it is already current."""
    if table not in TABLES:
        raise ValueError(f"the bible backfill writes {TABLES}, not {table}")
    return store.write(contribution(table, code, tool), counts)
