"""Hebrew verb paradigms out of the Wikidata lexeme dump (targum-internal#300).

The front door promises "Conjugations on the card: the full table for any verb, with the
form in front of you picked out." The card links out to Pealim instead, which is an
outbound link §11 allows and is not the table the page sells — and it sends the reader
off the page at the moment they were learning.

**Wikidata's Hebrew lexemes are CC0**, which is the whole reason this is the source. No
attribution, no ShareAlike, no terms of service: it can be baked into a reader page, which
is what §11 requires of anything a reader sees. The hosted DICTA tools are NonCommercial
and Hebrew Wiktionary is ShareAlike; both are doors this does not have to open.

**Measured before it was built** (2026-09-16, `~/.targum/research/conjugations-2026-09-16`).
Matching targum's own verb lemmas against Wikidata lemma-to-lemma looks poor — 20.7% —
and that is a trap: DICTA lemmatizes `בוא`, `מות`, `קום`, `אמר` where Wikidata's lemma is
the 3ms past `בא`, `מת`, `קם`, `אמר`. Twelve of twelve tested went the same way. Matching
on **any inflected form** instead covers 51.1% of distinct verb lemmas and **89.4% of
running verb occurrences**. What is left over is biblical, where the Open Scriptures
morphology targum already holds is the better source anyway.

**Why the dump and not the query service.** The Wikidata Query Service times out on this
query and pages of it inconsistently — two of six failed on the night this was measured.
The dump is one file, reproducible, and dated in its own header.

Streamed, never loaded. The file is 795 MB gzipped and this machine has been OOM-killed
running less. Forms follow their lexeme in the dump, so one pass suffices: a Hebrew verb
lexeme is noted, and the `wd:L<n>-F<m>` blocks after it are its own.

    uv run python scripts/hebrew_paradigms.py ~/.targum/research/.../latest-lexemes.ttl.gz
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

#: Wikidata's own ids for what this is looking for.
HEBREW = "wd:Q9288"
VERB = "wd:Q24905"

#: A subject line at column 0 opens a block: `wd:L7396 a ontolex:LexicalEntry ;`
SUBJECT = re.compile(r"^(wd:L\d+(?:-[FS]\d+)?)\s")
LEXEME = re.compile(r"^wd:L(\d+)$")
FORM = re.compile(r"^wd:L(\d+)-F(\d+)$")

#: `wikibase:lemma "הָלַךְ"@he-x-Q21283070` — the language tag says whether it is pointed.
#: The bare `@he` is the spelling as it is written; the `-x-` variant carries the nikkud,
#: which is what a learner's card wants.
TAGGED = re.compile(r'"((?:[^"\\]|\\.)*)"@(he(?:-x-[A-Za-z0-9]+)?)')
FEATURE = re.compile(r"wd:(Q\d+)")

#: The grammatical features that make a Hebrew verb table, by Wikidata id. Anything not
#: here is carried through as its raw id rather than dropped: a feature nobody has named
#: is still a distinction between two forms, and naming it is a later job than having it.
FEATURES = {
    "Q192613": "present",
    "Q1994301": "past",
    "Q501405": "future",
    "Q22716": "imperative",
    "Q179230": "infinitive",
    "Q814722": "1st",
    "Q51929049": "2nd",
    "Q51929074": "3rd",
    "Q499327": "masculine",
    "Q1775415": "feminine",
    "Q110786": "singular",
    "Q146786": "plural",
    "Q1230649": "construct",
    "Q53997851": "definite",
    "Q1641446": "participle",
    # The person feature Hebrew verbs actually carry — 19,735 forms use this and not
    # Q814722, which is why every first-person form came through as a bare id.
    "Q21714344": "1st",
    # Forms carrying a pronominal object suffix: אֲמַרְתִּיו, "I said it". Real Hebrew and
    # not the table a learner came for, so they are named rather than dropped and the
    # card folds them away. `possessive` on a form is the flag that says so.
    "Q71470598": "possessive-1st",
    "Q71470837": "possessive-2nd",
    "Q71470909": "possessive-3rd",
    "Q69761633": "possessive-masculine",
    "Q69761768": "possessive-feminine",
    "Q71469738": "possessive-either",
    "Q78191294": "possessive-singular",
    "Q78191289": "possessive-plural",
}

#: A form whose features include one of these carries a pronominal object suffix.
SUFFIXED = tuple(name for name in FEATURES.values() if name.startswith("possessive"))


def bare(text: str) -> str:
    """The letters, without the pointing: how a lemma is compared everywhere in targum."""
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch))


def readings(line: str) -> tuple[str, str]:
    """A line's plain and pointed Hebrew, either of which may be empty."""
    plain = pointed = ""
    for text, tag in TAGGED.findall(line):
        if tag == "he":
            plain = plain or text
        elif not pointed:
            pointed = text
    return plain, pointed


def harvest(path: Path) -> dict[str, dict[str, object]]:
    """Every Hebrew verb lexeme in the dump, with its forms. One streaming pass."""
    verbs: dict[str, dict[str, object]] = {}
    #: Lexemes seen to be Hebrew verbs, so their forms are recognised as they arrive.
    wanted: set[str] = set()
    subject = ""
    #: What the block being read has said so far.
    block: dict[str, object] = {}
    #: Whether a multi-line `grammaticalFeature` list is still running.
    collecting = False

    def close() -> None:
        if not subject or not block:
            return
        found = LEXEME.match(subject)
        if found:
            if block.get("language") == HEBREW and block.get("category") == VERB:
                wanted.add(found.group(1))
                verbs[found.group(1)] = {
                    "lemma": block.get("pointed") or block.get("plain") or "",
                    "plain": block.get("plain") or "",
                    "forms": [],
                }
            return
        found = FORM.match(subject)
        if found and found.group(1) in wanted:
            plain = str(block.get("plain") or "")
            if plain:
                forms = verbs[found.group(1)]["forms"]
                assert isinstance(forms, list)
                forms.append(
                    {
                        "plain": plain,
                        "pointed": str(block.get("pointed") or ""),
                        "features": list(block.get("features") or []),
                    }
                )

    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as dump:
        for line in dump:
            opening = SUBJECT.match(line)
            if opening:
                close()
                subject = opening.group(1)
                block = {}
            if not subject:
                continue
            if "dct:language" in line:
                found = FEATURE.search(line)
                block["language"] = f"wd:{found.group(1)}" if found else ""
            if "wikibase:lexicalCategory" in line:
                found = FEATURE.search(line)
                block["category"] = f"wd:{found.group(1)}" if found else ""
            if "wikibase:lemma" in line or "ontolex:representation" in line:
                plain, pointed = readings(line)
                if plain and not block.get("plain"):
                    block["plain"] = plain
                if pointed and not block.get("pointed"):
                    block["pointed"] = pointed
            # A feature list runs over as many lines as it has features:
            #
            #     wikibase:grammaticalFeature wd:Q192613,
            #             wd:Q442485,
            #             wd:Q625420 .
            #
            # Reading only the line the predicate is on takes the first and drops the
            # rest, which is how every form came out tagged `singular` and nothing else —
            # no tense, no person, no gender, and a table that cannot be laid out.
            if "wikibase:grammaticalFeature" in line:
                collecting = True
            if collecting:
                block.setdefault("features", []).extend(  # type: ignore[union-attr]
                    FEATURES.get(q, q) for q in FEATURE.findall(line)
                )
                if line.rstrip().endswith((";", ".")):
                    collecting = False
            if line.rstrip().endswith("."):
                close()
                subject = ""
                block = {}
                collecting = False
    close()
    return verbs


def index(verbs: dict[str, dict[str, object]]) -> dict[str, object]:
    """The shape a build reads: every bare form to the lexemes it belongs to.

    Bare, because that is the only spelling two sources agree on — DICTA's lemma is
    unpointed and Wikidata's may or may not be. A form belonging to two lexemes keeps
    both; picking one here would be guessing at a homograph without the sentence.
    """
    by_form: dict[str, set[str]] = defaultdict(set)
    for lid, verb in verbs.items():
        forms = verb["forms"]
        assert isinstance(forms, list)
        for form in forms:
            by_form[bare(str(form["plain"]))].add(lid)
        by_form[bare(str(verb["plain"]))].add(lid)
    return {
        "source": "wikidata-lexemes",
        "licence": "CC0-1.0",
        "verbs": verbs,
        "by_form": {form: sorted(ids) for form, ids in by_form.items() if form},
    }


def compact(verbs: dict[str, dict[str, object]]) -> dict[str, object]:
    """The shape the package ships: small enough to live in the wheel.

    Three economies, in order of what they save.

    **The object-suffix forms go** — אֲמַרְתִּיו, "I said it" — which is 14% of the forms
    and none of the table a learner came for. A reader who meets one still gets the right
    card: the lemmatizer files it under the bare verb, which is what the lookup is on.

    **Features become numbers** into one list at the head. There are a few dozen of them
    over 145,000 forms, and spelling `masculine` out each time is most of the file.

    **The unpointed spelling goes**, because it is the pointed one with the marks taken
    off, and `bare()` takes them off at read time for nothing.

    20 MB becomes 6.8, and 0.9 gzipped, which is what goes in the wheel.
    """
    vocabulary: dict[str, int] = {}

    def code(feature: str) -> int:
        if feature not in vocabulary:
            vocabulary[feature] = len(vocabulary)
        return vocabulary[feature]

    kept: dict[str, list[object]] = {}
    for lid, verb in verbs.items():
        forms = verb["forms"]
        assert isinstance(forms, list)
        rows: list[list[object]] = []
        for form in forms:
            features = [str(f) for f in form["features"]]
            if any(f.startswith("possessive") for f in features):
                continue
            rows.append(
                [str(form["pointed"] or form["plain"]), [code(f) for f in sorted(features)]]
            )
        if rows:
            kept[lid] = [str(verb["lemma"]), rows]

    by_form: dict[str, set[str]] = defaultdict(set)
    for lid, (lemma, rows) in kept.items():  # type: ignore[misc]
        for pointed, _ in rows:  # type: ignore[misc]
            by_form[bare(str(pointed))].add(lid)
        by_form[bare(str(lemma))].add(lid)
    return {
        "source": "wikidata-lexemes",
        "licence": "CC0-1.0",
        "features": list(vocabulary),
        "verbs": kept,
        "by_form": {form: sorted(ids) for form, ids in by_form.items() if form},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path, help="latest-lexemes.ttl.gz")
    parser.add_argument("--out", type=Path, default=Path("hebrew-paradigms.json"))
    parser.add_argument(
        "--compact", action="store_true", help="The shape the package ships. A .gz out is gzipped."
    )
    args = parser.parse_args()

    verbs = harvest(args.dump)
    built = compact(verbs) if args.compact else index(verbs)
    written = json.dumps(built, ensure_ascii=False, separators=(",", ":"))
    if args.out.suffix == ".gz":
        # `mtime=0`, so the same dump makes the same bytes. gzip stamps the time it was
        # written into its own header by default, which would make this file differ from
        # itself on every regeneration and churn a 900 KB blob through git for nothing.
        with args.out.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as out:
            out.write(written.encode("utf-8"))
    else:
        args.out.write_text(written, encoding="utf-8")
    forms = sum(len(v["forms"]) for v in verbs.values())  # type: ignore[arg-type]
    print(
        f"{len(verbs):,} Hebrew verb lexemes, {forms:,} forms, "
        f"{len(built['by_form']):,} distinct bare forms → {args.out}",  # type: ignore[arg-type]
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
