"""Count which French noun endings tell the gender (targum-internal#263).

A French noun's gender is about 80% predictable from its ending (Lyster 2006), and
teaching the endings is the one instruction that has been tested (Lyster 2004). The card
says so where it is true of the word in front of the reader: "f · like most nouns in
-tion". This script measures which endings earn that sentence.

The nouns are Grammalecte's lexicon (`lexicons/French.lex`, the Dicollecte dictionary's
successor, MPL-2.0), pinned to one commit of its GitHub mirror. Only a noun that is
nothing but a noun and has one gender counts: *national* is an adjective as well, and
*livre* is both genders. An ending is kept where at least `LEAST` nouns end in it and
`SHARE` or more of them share a gender. A longer ending is dropped where a shorter one of
three letters or more already says the same gender within `SETTLED` of it, so the card
names the ending a teacher would (*-tion*, *-age*) wherever the longer one is the more
reliable, and the shorter wherever it is as good; two-letter endings are kept for the nouns
nothing longer covers, and the card reads the longest ending a word has.

    python scripts/french_endings.py

Writes `src/targum/annotate/french_endings.json`: the endings, their gender, the share
and the count, with the source and its licence. What ships is that table of facts about
endings, never the lexicon; LICENSING.md records the reading.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

COMMIT = "08511c222029b3be20bf547563315d10fb48d44b"
SOURCE = f"https://raw.githubusercontent.com/Pofilo/grammalecte/{COMMIT}/lexicons/French.lex"
CACHE = Path.home() / ".targum" / "cache" / "grammalecte" / f"French-{COMMIT[:12]}.lex"
OUT = Path(__file__).resolve().parents[1] / "src" / "targum" / "annotate" / "french_endings.json"

LEAST = 50
SHARE = 0.9
SETTLED = 0.005
LENGTHS = range(2, 6)


def lexicon() -> list[str]:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(SOURCE, timeout=300) as answer:  # noqa: S310 - pinned
            CACHE.write_bytes(answer.read())
    return CACHE.read_text(encoding="utf-8").splitlines()


def nouns(lines: list[str]) -> dict[str, str]:
    """Every plain noun with one gender, by its dictionary form."""
    genders: dict[str, set[str]] = defaultdict(set)
    adjectives: set[str] = set()
    for line in lines:
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        form, lemma, tags = parts[0], parts[1], parts[2]
        if form != lemma or not form.isalpha() or not form.islower():
            continue
        if ":A" in tags or ":W" in tags:
            adjectives.add(form)
        found = re.search(r":N:([mfe]):", tags)
        if found and tags.startswith(":N"):
            genders[form].add(found.group(1))
    return {
        form: next(iter(said))
        for form, said in genders.items()
        if len(said) == 1 and next(iter(said)) in "mf" and form not in adjectives
    }


def endings(kept: dict[str, str]) -> list[dict[str, object]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for form, gender in kept.items():
        for length in LENGTHS:
            if len(form) > length + 1:
                counts[form[-length:]][gender] += 1
    measured = {}
    for ending, said in counts.items():
        total = said["m"] + said["f"]
        if total < LEAST:
            continue
        gender, most = said.most_common(1)[0]
        if most / total >= SHARE:
            measured[ending] = (gender, most / total, total)
    table = []
    for ending, (gender, share, total) in sorted(measured.items()):
        settled = any(
            ending.endswith(shorter)
            and measured[shorter][0] == gender
            and measured[shorter][1] >= share - SETTLED
            for shorter in measured
            if 3 <= len(shorter) < len(ending)
        )
        if not settled:
            table.append(
                {"ending": ending, "gender": gender, "share": round(share, 3), "nouns": total}
            )
    return table


def main() -> None:
    kept = nouns(lexicon())
    table = endings(kept)
    OUT.write_text(
        json.dumps(
            {
                "source": SOURCE,
                "licence": "MPL-2.0",
                "counted": len(kept),
                "least": LEAST,
                "share": SHARE,
                "endings": table,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(kept)} nouns, {len(table)} endings -> {OUT}")


if __name__ == "__main__":
    main()
