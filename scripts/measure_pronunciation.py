"""How many words on the French shelf Morphalou says how to pronounce (targum-internal#266).

The card that shows how a French word is said takes its transcriptions from Morphalou 3.1
(LGPL-LR), as a lookup. A word Morphalou lacks shows no IPA. So the first step, before any
card is drawn, is to count how many of the words a reader of the shelf actually meets
have one. Below about 95% of tokens, espeak-ng is reconsidered, and that is the owner's
call rather than this script's.

**What a word is.** The reader's own tokens where a built text is on disk: the words the
French annotator split out (`annotate/model_lemma.py`), punctuation and symbols left out.
Where a text is not built here, which on a laptop is every French one, the text is fetched
from its source (`ingest.load`, which spends nothing) and split by the rules that
annotator is given:

- a word is a run of letters or digits, joined inside by an apostrophe or a hyphen;
- an elided word is split after its apostrophe, which stays on the first part: `l'homme`
  is `l'` and `homme`, `qu'il` is `qu'` and `il`, `jusqu'à` is `jusqu'` and `à`;
- a pronoun joined to a verb by a hyphen is its own word: `dit-il` is `dit` and `il`, and
  the `t` of `a-t-il` is no word at all; so is the `-là` and `-ci` of `ce jour-là`;
- any other compound is one word (`aujourd'hui`, `peut-être`, `là-bas`), unless Morphalou
  transcribes it whole, in which case it is one word whatever it looks like;
- a number written in digits is a word, and so is `M.` for monsieur, without its point.

**What covered means.** A token is covered when Morphalou has a transcription for its
spelling, tried as written, then in lower case, then with `œ` spelled `oe` (the table
files `oeil` with a transcription and `œil` without one). A type is a spelling in lower
case. A covered token whose spelling has two ways of being said (`est`, `couvent`) is
counted as ambiguous; where the reader's tokens carry a lemma, a part of speech and
features, those are used first to choose, and only what they leave undecided is counted.

**What a miss is.** Each uncovered token is put in the first of these that fits: a
number (digits or a Roman numeral), an abbreviation (`M.`, `Mme`), an elision (`l'`,
`qu'`), a capitalised word Morphalou does not list in any case (a name, mostly, or a rare
word at the start of a sentence), a hyphenated compound, a form Morphalou lists without a
transcription, and anything else. A hyphenated miss whose parts Morphalou each transcribes
(`là-bas`, `peut-être`) is counted too, since a card could say it by its parts.

    python scripts/measure_pronunciation.py [--out targum-out] [--only <id>] [--misses 40]

Calls no model and spends nothing. Morphalou must be fetched first:
`targum models fetch morphalou`.

**Measured 2026-09-28, the 14 French texts of the catalogue, none built on the laptop, so
all split by the rules.** 23,643 of 24,151 tokens covered, 97.90%; 4,574 of 4,760 types,
96.09%. Every text is above 95%, the lowest La Chèvre de monsieur Seguin at 95.61% (Seguin
is 29 of its misses). Of the 508 missed tokens, 216 are capitalised words, nearly all
names; 48 are `M.`; 103 are hyphenated compounds Morphalou lists without a transcription
(`là-bas`, `mère-grand`, `peut-être`), 98 of them made of parts it does transcribe; 86 are
other forms it lists bare, among them `dix`, `douze`, `parce`, `tandis`, `afin`,
`aujourd'hui` and the English of Allais's Americans. Without names, numbers and
abbreviations, 98.99%. Two things a card will have to answer that coverage does not:
501 covered tokens are said two ways that nothing here decides, 335 of them `un`, whose
numeral row reads `y n @`, a feminine copied onto it; and `c'`, 114 tokens, is
transcribed `k`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import ingest  # noqa: E402
from targum.annotate import morphalou  # noqa: E402
from targum.models import Annotation, read_artifact  # noqa: E402

#: Letters or digits, joined inside by an apostrophe or a hyphen, perhaps ending on an
#: apostrophe (`jusqu'` before a line break).
WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*['’]?")

#: What a French word elides to before a vowel, the apostrophe left off. Anything ending
#: in `qu` elides the same way: `lorsqu'`, `puisqu'`, `quoiqu'`, `presqu'`.
ELIDED = frozenset("l d j m n s t c".split()) | {"qu", "jusqu"}

#: What a hyphen joins onto the end of a word and is a word of its own: the pronouns after
#: a verb (`dit-il`, `donnez-le-moi`, `allons-y`) and the particles after a noun
#: (`ce jour-là`, `celui-ci`).
CLITICS = frozenset(
    "je tu il elle on nous vous ils elles le la les lui leur moi toi y en ce là ci".split()
)

#: A chapter's number. `M` alone is monsieur, not a thousand.
ROMAN = re.compile(r"^(?:[IVX]|[IVXLCDM]{2,})$")
ABBREVIATIONS = frozenset({"M", "MM", "Mme", "Mmes", "Mlle", "Mlles", "Dr", "St", "Ste"})
DIGITS = re.compile(r"^\d+$")

#: The parts of speech the reader's tokens carry that are not words to be said.
NOT_WORDS = frozenset({"PUNCT", "SYM"})

KINDS = (
    "number",
    "abbreviation",
    "elision",
    "capitalised",
    "hyphenated",
    "listed, no transcription",
    "not listed",
)


@dataclass(frozen=True)
class Word:
    surface: str
    lemma: str = ""
    pos: str = ""
    feats: str = ""


def split(word: str, lexicon: morphalou.Lexicon) -> list[str]:
    """One run of `WORD` as the reader's tokens would have it."""
    word = word.replace("’", "'")
    if len(word) == 1 or lexicon.lookup(word):
        return [word]
    if "'" in word[:-1]:
        head, rest = word.split("'", 1)
        if head.lower() in ELIDED or head.lower().endswith("qu"):
            return [f"{head}'", *split(rest, lexicon)] if rest else [f"{head}'"]
    if "-" in word:
        parts = word.split("-")
        tail: list[str] = []
        while len(parts) > 1 and (parts[-1].lower() in CLITICS or parts[-1].lower() == "t"):
            last = parts.pop()
            if last.lower() != "t":
                tail.insert(0, last)
        if len(parts) < word.count("-") + 1:
            return [*split("-".join(parts), lexicon), *tail]
    return [word]


def words(text: str, lexicon: morphalou.Lexicon) -> list[Word]:
    return [Word(piece) for found in WORD.findall(text) for piece in split(found, lexicon)]


def kind(surface: str, lexicon: morphalou.Lexicon) -> str:
    """Which kind of miss an uncovered token is. The first that fits."""
    surface = surface.replace("’", "'")
    if DIGITS.match(surface) or ROMAN.match(surface):
        return "number"
    if surface in ABBREVIATIONS:
        return "abbreviation"
    if surface.endswith("'"):
        return "elision"
    if surface[:1].isupper() and not lexicon.listed(surface):
        return "capitalised"
    if "-" in surface:
        return "hyphenated"
    if lexicon.listed(surface):
        return "listed, no transcription"
    return "not listed"


def by_parts(surface: str, lexicon: morphalou.Lexicon) -> bool:
    """Whether a hyphenated word's every part has a transcription of its own."""
    parts = surface.split("-")
    return len(parts) > 1 and all(part and lexicon.lookup(part) for part in parts)


@dataclass
class Tally:
    tokens: int = 0
    covered: int = 0
    ambiguous: int = 0
    resolved: int = 0
    #: Missed hyphenated tokens whose parts are each covered.
    parts_covered: int = 0
    types: set[str] = field(default_factory=set)
    covered_types: set[str] = field(default_factory=set)
    misses: Counter[str] = field(default_factory=Counter)
    kinds: Counter[str] = field(default_factory=Counter)
    #: The covered types said two ways that nothing decided, by how often.
    undecided: Counter[str] = field(default_factory=Counter)
    #: Each missed type's kind, as its first token had it.
    kind_of: dict[str, str] = field(default_factory=dict)

    def add(self, word: Word, lexicon: morphalou.Lexicon) -> None:
        key = word.surface.replace("’", "'").lower()
        self.tokens += 1
        self.types.add(key)
        said = lexicon.transcriptions(word.surface)
        if not said:
            self.misses[key] += 1
            self.kinds[self.kind_of.setdefault(key, kind(word.surface, lexicon))] += 1
            self.parts_covered += by_parts(word.surface, lexicon)
            return
        self.covered += 1
        self.covered_types.add(key)
        if len(said) > 1:
            chosen = lexicon.transcriptions(word.surface, word.lemma, word.pos, word.feats)
            if len(chosen) == 1:
                self.resolved += 1
            else:
                self.ambiguous += 1
                self.undecided[key] += 1

    def merge(self, other: Tally) -> None:
        self.tokens += other.tokens
        self.covered += other.covered
        self.ambiguous += other.ambiguous
        self.resolved += other.resolved
        self.parts_covered += other.parts_covered
        self.types |= other.types
        self.covered_types |= other.covered_types
        self.misses.update(other.misses)
        self.undecided.update(other.undecided)
        self.kinds.update(other.kinds)
        self.kind_of = {**other.kind_of, **self.kind_of}

    def token_share(self) -> float:
        return self.covered / self.tokens if self.tokens else 0.0

    def type_share(self) -> float:
        return len(self.covered_types) / len(self.types) if self.types else 0.0


def tally(found: Iterable[Word], lexicon: morphalou.Lexicon) -> Tally:
    out = Tally()
    for word in found:
        out.add(word, lexicon)
    return out


def built(root: Path, source: str) -> Annotation | None:
    """The annotation a build already wrote for this source, if one is on disk."""
    for document in sorted(root.glob("**/document.json")):
        try:
            if json.loads(document.read_text(encoding="utf-8")).get("source") != source:
                continue
        except (OSError, json.JSONDecodeError):
            continue
        annotation = read_artifact(Annotation, document.parent / "annotation.json")
        if annotation is not None and any(annotation.tokens.values()):
            return annotation
    return None


def reader_words(annotation: Annotation) -> Iterator[Word]:
    for tokens in annotation.tokens.values():
        for token in tokens:
            if (token.pos or "") in NOT_WORDS or not WORD.search(token.surface):
                continue
            yield Word(token.surface, token.lemma, token.pos or "", token.feats or "")


def text_words(source: str, lexicon: morphalou.Lexicon) -> list[Word]:
    document = ingest.load(source, language="fr")
    return [word for block in document.blocks for word in words(block.text, lexicon)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--only", default="", help="One entry id, for a quick check.")
    parser.add_argument("--misses", type=int, default=40, help="How many missed words to list.")
    args = parser.parse_args()

    from targum.catalogue import CATALOGUE

    lexicon = morphalou.load()
    shelf = Tally()
    print(f"{'text':42} {'how':6} {'tokens':>7} {'tokens %':>9} {'types':>6} {'types %':>8}")
    for entry in CATALOGUE:
        if entry.language != "fr" or (args.only and entry.id != args.only):
            continue
        annotation = built(args.out, entry.source) if args.out.is_dir() else None
        if annotation is not None:
            found, how = list(reader_words(annotation)), "built"
        else:
            found, how = text_words(entry.source, lexicon), "rules"
        one = tally(found, lexicon)
        shelf.merge(one)
        print(
            f"{entry.id:42} {how:6} {one.tokens:7,} {one.token_share():9.2%} "
            f"{len(one.types):6,} {one.type_share():8.2%}",
            flush=True,
        )

    missed = shelf.tokens - shelf.covered
    print()
    print(
        f"shelf: {shelf.covered:,} of {shelf.tokens:,} tokens covered ({shelf.token_share():.2%}); "
        f"{len(shelf.covered_types):,} of {len(shelf.types):,} types ({shelf.type_share():.2%})"
    )
    names = sum(shelf.kinds[name] for name in ("capitalised", "number", "abbreviation"))
    if shelf.tokens > names:
        print(
            f"without capitalised words, numbers and abbreviations: "
            f"{shelf.covered / (shelf.tokens - names):.2%} of {shelf.tokens - names:,} tokens"
        )
    print(
        f"covered but said two ways: {shelf.ambiguous:,} tokens undecided, "
        f"{shelf.resolved:,} decided by lemma and features "
        f"({(shelf.ambiguous + shelf.resolved) / max(shelf.covered, 1):.2%} of covered)"
    )
    print(f"\nmissed tokens by kind ({missed:,}):")
    for name in KINDS:
        count = shelf.kinds[name]
        print(f"  {name:26} {count:6,}  {count / max(missed, 1):6.1%}")
    print(f"  of which hyphenated with every part covered: {shelf.parts_covered:,}")
    print(
        "\ncommonest said two ways: "
        + ", ".join(f"{key} {count}" for key, count in shelf.undecided.most_common(12))
    )
    print(f"\ncommonest misses ({len(shelf.misses):,} types):")
    for key, count in shelf.misses.most_common(args.misses):
        print(f"  {count:5}  {key:24} {shelf.kind_of[key]}")


if __name__ == "__main__":
    main()
