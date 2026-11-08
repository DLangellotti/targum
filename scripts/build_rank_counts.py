"""Build `src/targum/common_lemmas.json` and `src/targum/rank_counts.json`, the two
offline conversions the CEFR ladder reads (targum-internal#659).

**Which lemmas are common.** wordfreq ranks written forms, so a lemma looked up by its
dictionary form alone looks rarer than it is (мочь at Zipf 2.63, bastare 3.85, sembler
3.74). XLex, where the CEFR thresholds come from, counts the 5,000 most frequent
*lemmas*. So each lemma of a lexicon gets the sum of wordfreq's frequencies over its
forms, a form two lemmas own shared between them by how common each lemma's own
dictionary form is, and the `level.COMMON_TOP` highest are the language's commonest:
what `level.common` counts. The file holds four bytes of a hash per lemma
(`level._digest`), never the lemma.

**The rank-to-count table.** A text's level is the frequency rank R covering 90% of its
running words, a word's rank being its dictionary form's in wordfreq's list. C(R) is how
many of those commonest lemmas have a dictionary form at or below R: the count a reader
who knew exactly the words up to R would have. Both are conversions, not evidence about
learners.

usage (offline, free; the lexicons are lookups and never shipped):

    PYTHONPATH=$PWD/src .venv/bin/python scripts/build_rank_counts.py \
        --morph-it /path/to/morph-it_048.txt

French reads Morphalou 3.1 and Russian OpenRussian from the model directory
(`targum models fetch morphalou` / `openrussian`). Italian reads Morph-it! 0.48, downloaded
by hand from https://docs.sslmit.unibo.it/doku.php?id=resources:morph-it and deleted after.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import importlib.metadata
import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from wordfreq import get_frequency_dict

from targum import level
from targum.annotate import frequency, morphalou, openrussian
from targum.annotate.difficulty import _french_sums

#: Where the rank-to-count table is sampled: every STEP ranks, from 0 to the list's end.
STEP = 50
HERE = Path(__file__).resolve().parent.parent / "src" / "targum"
COUNTS = HERE / "rank_counts.json"
LEMMAS = HERE / "common_lemmas.json"

#: Morph-it! tags that are not a vocabulary word (names, punctuation, symbols), and the
#: articled prepositions, which the tagger splits into two words (della is di + il).
#: "NE" is the clitic ne, not a name, and is kept.
ITALIAN_SKIP = {"NPR", "PON", "SENT", "SYM", "ABL", "SMI", "ARTPRE"}

#: Morph-it! files each article by its own form (la, una); the tagger's lemmas are il and
#: uno, and the partitive del/della is di + il to it, so it is left out.
ITALIAN_ARTICLES = {"il": "il", "la": "il", "l'": "il", "un": "uno", "una": "uno", "un'": "uno"}

#: OpenRussian's "others" table has no inflections, so a pronoun's case forms are entries
#: of their own (мне, меня) that the tagger never gives as a lemma: they are counted
#: under the lemma it does give. targum's own list of a closed paradigm, not a lexicon's.
RUSSIAN_PRONOUNS = {
    "я": "меня мне мной мною",
    "ты": "тебя тебе тобой тобою",
    "мы": "нас нам нами",
    "вы": "вас вам вами",
    "он": "ему него нему ним нём нем",
    "она": "ей ею неё нее ней нею",
    "они": "их им ими них ним ними",
    "кто": "кого кому кем ком",
    "что": "чего чему чем чём",
    "себя": "себе собой собою",
}

LEXICONS = {
    "fr": "Morphalou 3.1 (ATILF/CNRS, LGPL-LR)",
    "ru": f"OpenRussian russian-dictionary {openrussian.COMMIT[:12]} (CC BY-SA 4.0)",
    "it": "Morph-it! 0.48 (Zanchetta and Baroni, CC BY-SA 2.0 / LGPL)",
}


def shared(
    blocks: Iterable[tuple[str, set[str]]], frequency_of: Mapping[str, float]
) -> dict[str, float]:
    """Each lemma's share of the frequency of every form it owns. A form two lemmas own
    goes to each in proportion to its own dictionary form's frequency, or evenly where
    wordfreq saw none of them, as `difficulty.french_sums` shares French."""
    owned: dict[str, set[str]] = {}
    for key, forms in blocks:
        owned.setdefault(key, set()).update(forms | {key})
    owners: dict[str, list[str]] = {}
    for key, forms in owned.items():
        for form in forms:
            owners.setdefault(form, []).append(key)
    sums = dict.fromkeys(owned, 0.0)
    for form, keys in owners.items():
        used = frequency_of.get(form, 0.0)
        if not used:
            continue
        weights = [frequency_of.get(key, 0.0) for key in keys]
        total = sum(weights)
        for key, weight in zip(keys, weights, strict=True):
            sums[key] += used * (weight / total if total else 1 / len(keys))
    return sums


def french() -> dict[str, float]:
    sums = _french_sums()
    if sums is None:
        raise SystemExit("Morphalou is not in the model directory: targum models fetch morphalou")
    out: dict[str, float] = {}
    for lemma, total in sums.items():
        key = level.lemma_key(lemma, "fr")
        if len(key) == 1 and key not in {"à", "y"}:
            continue  # a letter's name (le d, le l), which wordfreq's d' and l' inflate
        out[key] = out.get(key, 0.0) + total
    return out


def russian() -> dict[str, float]:
    folded: dict[str, float] = {}
    for word, used in get_frequency_dict("ru").items():
        key = word.replace("ё", "е")  # wordfreq keeps ё and е apart; running text folds
        folded[key] = folded.get(key, 0.0) + used
    case_forms = {
        form: lemma for lemma, forms in RUSSIAN_PRONOUNS.items() for form in forms.split()
    }
    blocks: list[tuple[str, set[str]]] = [
        (lemma, set(forms.split())) for lemma, forms in RUSSIAN_PRONOUNS.items()
    ]
    for word, entries in openrussian.load().entries.items():
        key = level.lemma_key(word, "ru")
        if key in case_forms:
            continue
        kept = [entry for entry in entries if not entry.written[:1].isupper()]
        if not kept:
            continue  # a name (Россия, Москва): never vocabulary, as XLex never asks one
        forms = {key}
        for entry in kept:
            forms.add(openrussian.fold(entry.written))
            forms.update(openrussian.fold(form) for vs in entry.forms.values() for form in vs)
        blocks.append((key, {form for form in forms if form and " " not in form}))
    return shared(blocks, folded)


def italian(path: Path) -> dict[str, float]:
    """Morph-it! files a pronoun by its own form (sua, tutte, altre): where the same form
    is also a determiner's or an adjective's (suo, tutto, altro), the form is counted
    under that lemma, which is the one the tagger gives, and the pronoun's is dropped."""
    rows: list[tuple[str, str, str]] = []
    with path.open(encoding="latin-1") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            form, lemma, tag = parts[0].lower(), parts[1].lower(), parts[2]
            head = tag.split(":")[0].split("-")[0]
            if head in ITALIAN_SKIP:
                continue
            if head == "ART":
                if lemma not in ITALIAN_ARTICLES:
                    continue
                lemma = ITALIAN_ARTICLES[lemma]
            if not lemma.replace("'", "").isalpha():
                continue
            rows.append((form, lemma, head))
    elsewhere = {form for form, lemma, head in rows if head in {"DET", "ADJ"} and lemma != form}
    forms_of: dict[str, set[str]] = {}
    for form, lemma, head in rows:
        if head == "PRO" and lemma == form and form in elsewhere:
            continue
        forms_of.setdefault(level.lemma_key(lemma, "it"), set()).add(form)
    return shared(forms_of.items(), get_frequency_dict("it"))


def commonest(sums: Mapping[str, float]) -> list[str]:
    """The `COMMON_TOP` lemmas with the highest sums, commonest first."""
    ranked = sorted((key for key, total in sums.items() if total > 0), key=lambda k: (-sums[k], k))
    return ranked[: level.COMMON_TOP]


def curve(language: str, top: set[str]) -> list[int]:
    """C(R) at R = 0, STEP, 2·STEP … up to the end of the frequency list."""
    first: dict[str, int] = {}
    for word, place in frequency.ranks(language).items():
        key = level.lemma_key(word, language)
        if key in top and place < first.get(key, frequency.RANKED + 1):
            first[key] = place
    counted = sorted(first.values())
    points: list[int] = []
    at = 0
    for edge in range(0, frequency.RANKED + 1, STEP):
        while at < len(counted) and counted[at] <= edge:
            at += 1
        points.append(at)
    while len(points) > 1 and points[-1] == points[-2]:
        points.pop()  # past the last countable lemma C(R) is flat: keep the ceiling once
    return points


def packed(top: Iterable[str]) -> str:
    digests = sorted({level._digest(key) for key in top})
    return base64.b64encode(b"".join(d.to_bytes(4, "big") for d in digests)).decode("ascii")


def one_line(text: str, rows: Iterable[list[int]]) -> str:
    for points in rows:  # one line a language, not one a number
        spread = json.dumps(points, indent=1).replace("\n", "\n  ")
        text = text.replace(spread, json.dumps(points, separators=(",", ":")))
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--morph-it", type=Path, required=True)
    args = parser.parse_args()
    if not morphalou.available():
        raise SystemExit("Morphalou is not in the model directory")
    sums = {"fr": french(), "ru": russian(), "it": italian(args.morph_it)}
    tops = {language: commonest(found) for language, found in sums.items()}
    built = datetime.date.today().isoformat()
    version = importlib.metadata.version("wordfreq")

    lemmas = {
        "about": (
            "A conversion, not evidence. Each language's commonest lemmas, as XLex counts "
            "them: the lemmas of a lexicon ranked by the sum of wordfreq's frequencies over "
            "their forms, a form two lemmas own shared by how common each one's dictionary "
            "form is, and the top `top` kept. level.common counts a known lemma among them "
            "(targum-internal#659). Each lemma is held as the first four bytes of BLAKE2b of "
            "level.lemma_key(lemma), sorted and base64-encoded: a lookup, and no word of any "
            "lexicon or of wordfreq is in this file. Built by scripts/build_rank_counts.py."
        ),
        "built": built,
        "wordfreq": version,
        "lexicons": LEXICONS,
        "top": level.COMMON_TOP,
        "lemmas": {language: packed(top) for language, top in tops.items()},
    }
    LEMMAS.write_text(json.dumps(lemmas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    tables = {language: curve(language, set(top)) for language, top in tops.items()}
    counts = {
        "about": (
            "A conversion, not evidence. C(R): how many of the lemmas level.common counts "
            "(common_lemmas.json, each language's commonest by summed form frequency) have "
            "a dictionary form at or below rank R in wordfreq's list, sampled every `step` "
            "ranks from 0; past the last point C(R) is the last value. It says nothing "
            "about learners: it puts a text's frequency rank on the same scale as the CEFR "
            "thresholds (targum-internal#659). Counts only; no word of any lexicon or of "
            "wordfreq is in this file. Built by scripts/build_rank_counts.py."
        ),
        "built": built,
        "wordfreq": version,
        "lexicons": LEXICONS,
        "step": STEP,
        "counts": tables,
    }
    text = json.dumps(counts, ensure_ascii=False, indent=1)
    COUNTS.write_text(one_line(text, tables.values()) + "\n", encoding="utf-8")

    for language, points in tables.items():
        print(
            language,
            "lemmas",
            len(sums[language]),
            "top",
            len(tops[language]),
            "C(R) ceiling",
            points[-1],
            "reached by rank",
            (len(points) - 1) * STEP,
        )


if __name__ == "__main__":
    main()
