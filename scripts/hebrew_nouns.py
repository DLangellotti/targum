"""Hebrew nouns and adjectives out of the Wikidata lexeme dump (targum-internal#697e).

DICTA sometimes gives a plural or a feminine as the lemma: עצים for עצים, לירות for לירות,
צעירה for צעירות. The card then looks up a meaning under a word no dictionary files, and
says it has none. Taking the ending off by rule is not safe, because a great many Hebrew
singulars end the way plurals do: חנות, מלכות, חיים, מים. What settles it is a list of
which spellings are a noun's or an adjective's other forms, and of what their headword
is. That list is what this writes.

**CC0, the same source as the verb tables** (`hebrew_paradigms.py`): Wikidata's lexemes
carry no attribution requirement, no ShareAlike and no terms of service, so the table can
ride in the wheel and in a reader page.

**What ships is a map and nothing else:** each part of speech's forms to their headword,
bare (`hebrew_paradigms.bare`), since DICTA's lemma is unpointed. A form is kept only where:
- it belongs to exactly one headword of that part of speech, since two would be a
  homograph that needs the sentence;
- it is no Hebrew headword of any part of speech, so חנות and לחיים, words of their own,
  are never "reduced";
- it carries no possessive suffix, which a lemmatizer has already taken off, and is no
  construct form, which is more often a fixed phrase's word (על גבי) than a mistake;
- for a noun, it is a plural ending ים, ות or יים. A noun's feminine singular is often a
  word of its own that Wikidata has no lexeme for: חברה, "society", is more than חבר's;
- for an adjective, it is a feminine or a plural with an inflection's ending, of a
  headword that is not itself plural-shaped (אמריקאי is not אמריקה's).

    uv run python scripts/hebrew_nouns.py ~/.targum/research/.../latest-lexemes.ttl.gz \
        --out src/targum/annotate/nouns.json.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hebrew_paradigms import bare, harvest  # noqa: E402

NOUN = "wd:Q1084"
ADJECTIVE = "wd:Q34698"
#: What the shipped map calls each part of speech: the tagger's own names.
NAMES = {NOUN: "NOUN", ADJECTIVE: "ADJ"}


def hebrew_letters(word: str) -> bool:
    """Whether a spelling is Hebrew letters alone: no spaces, no punctuation, nothing
    Latin, as a lemma the annotator gives is."""
    return bool(word) and all("א" <= ch <= "ת" for ch in word)


#: The endings an inflected noun or adjective adds to its headword: a noun's plurals and
#: dual, and an adjective's feminine and plurals. A form ending otherwise is no inflection
#: of the headword, whatever the lexeme says (אמריקאי filed under אמריקה).
PLURAL_ENDINGS = ("ים", "ות", "יים")
ADJECTIVE_ENDINGS = ("ה", "ת", "ית", "ים", "ות", "יות", "יים")


def kept(spelled: str, lemma: str, pos: str, features: list[str]) -> bool:
    """Whether one form of one headword is a sure inflection of it."""
    if any(one.startswith("possessive") for one in features) or "construct" in features:
        # A construct form is more often a fixed phrase's word (על גבי, מיני, ימות
        # המשיח) than an annotator's mistake, and a suffix is already taken off.
        return False
    if not hebrew_letters(spelled) or spelled == lemma:
        return False
    if pos == "NOUN":
        # A noun's feminine singular is often a word of its own that Wikidata has no
        # lexeme for (חברה "society" is more than חבר's feminine), so only its plurals.
        return "plural" in features and spelled.endswith(PLURAL_ENDINGS)
    return (
        ("feminine" in features or "plural" in features)
        and spelled.endswith(ADJECTIVE_ENDINGS)
        and not lemma.endswith(("ים", "ות"))
    )


def mapped(lexemes: dict[str, dict[str, object]]) -> dict[str, object]:
    """Each part of speech's other forms to their headword, kept only where it is sure."""
    # Every Hebrew headword of any part of speech: a spelling that is one is a word of its
    # own, and never reduced (לחיים, "cheers", is not only לחי's plural).
    headwords = {
        bare(str(lexeme.get("plain") or lexeme.get("lemma") or "")) for lexeme in lexemes.values()
    }
    owners: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for lexeme in lexemes.values():
        pos = NAMES.get(str(lexeme.get("category") or ""))
        lemma = bare(str(lexeme.get("plain") or lexeme.get("lemma") or ""))
        if pos is None or not hebrew_letters(lemma):
            continue
        forms = lexeme.get("forms")
        assert isinstance(forms, list)
        for form in forms:
            features = [str(one) for one in form.get("features") or []]
            spelled = bare(str(form.get("plain") or ""))
            if kept(spelled, lemma, pos, features):
                owners[pos][spelled].add(lemma)
    out: dict[str, dict[str, str]] = {}
    for pos, forms in owners.items():
        out[pos] = {
            form: next(iter(lemmas))
            for form, lemmas in sorted(forms.items())
            if len(lemmas) == 1 and form not in headwords
        }
    return {
        "source": "wikidata-lexemes",
        "licence": "CC0-1.0",
        "forms": out,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path, help="latest-lexemes.ttl.gz")
    parser.add_argument("--out", type=Path, default=Path("nouns.json.gz"))
    args = parser.parse_args()

    lexemes = harvest(args.dump, None)
    built = mapped(lexemes)
    written = json.dumps(built, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    # `mtime=0`, so the same dump makes the same bytes (as `hebrew_paradigms.py` does).
    with args.out.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as out:
        out.write(written.encode("utf-8"))
    forms = built["forms"]
    assert isinstance(forms, dict)
    counts = ", ".join(f"{pos} {len(table)}" for pos, table in sorted(forms.items()))
    print(f"{len(lexemes)} lexemes; forms kept: {counts}; {args.out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
