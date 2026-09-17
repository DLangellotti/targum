"""The conjugations of a Hebrew verb, from a source targum may redistribute.

The front door promises "Conjugations on the card: the full table for any verb, with the
form in front of you picked out." The card showed the root and the binyan and then linked
out to Pealim — an outbound link §11 permits, and not the table the page sells. It also
sends the reader off the page at the moment they were learning.

**CC0, which is the whole reason this source and not another.** Wikidata's lexemes carry
no attribution requirement, no ShareAlike and no terms of service, so a table drawn from
them can be baked into a reader page. DICTA's hosted tools are NonCommercial and Hebrew
Wiktionary is ShareAlike; neither could ride inside a file a reader keeps.

**Looked up by any form, not by the lemma.** Measured on 2026-09-16: matching targum's
verb lemmas against Wikidata's lemma to lemma covers 20.7% of them, because the two
disagree about what a Hebrew verb is called — DICTA says `בוא`, `מות`, `קום`; Wikidata
says the 3ms past `בא`, `מת`, `קם`. Matching a lemma against *any* inflected form covers
51.1% of distinct lemmas and **89.4% of running verb occurrences**. The rest is mostly
biblical, where the Open Scriptures morphology is the better source anyway.

**Bare, always.** Nikkud is where two sources most easily disagree — the same verb is
written with and without points, and with different points by different editors — so
every comparison here is on letters alone. The pointed spelling is kept for showing, never
for matching.

The table is built by `scripts/hebrew_paradigms.py` out of the lexeme dump and ships
gzipped beside this file: 145,000 forms over 4,700 verbs, 0.9 MB in the wheel. Nothing
here reaches the network, and a build with no table draws no conjugations rather than
failing.
"""

from __future__ import annotations

import gzip
import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Beside this module, so the wheel carries it and a reader never fetches it.
TABLE = Path(__file__).parent / "paradigms.json.gz"

#: The most forms a card will draw for one verb. A Hebrew verb has about thirty-three,
#: and a lexeme with far more than that is carrying something a learner did not ask for.
MOST = 60


def bare(text: str) -> str:
    """The letters alone, which is the only spelling two sources agree on."""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(ch)
    )


@dataclass(frozen=True)
class Form:
    """One inflected form: how it is written, and what it is."""

    written: str
    features: tuple[str, ...]

    def matches(self, surface: str) -> bool:
        """Whether this is the form in front of the reader, compared on letters."""
        return bool(surface) and bare(self.written) == bare(surface)


@dataclass(frozen=True)
class Paradigm:
    """One verb's forms, in the order the source gives them."""

    lemma: str
    forms: tuple[Form, ...]


@dataclass(frozen=True)
class Table:
    """Every verb, and the index from a bare form to the verbs that spell it that way."""

    verbs: dict[str, Paradigm]
    by_form: dict[str, tuple[str, ...]]

    def of(self, word: str, seen: str = "") -> Paradigm | None:
        """The paradigm for a lemma or any inflected form of it.

        `seen` is a pointed spelling the word actually wore in the text, and it is what
        makes this usable. Unpointed, the commonest verbs in the language are ambiguous —
        `הלך` is both `הָלַךְ` and `הִלֵּךְ`, `נתן` is `נָתַן` and `נִתַּן`, `דבר` is `דִּבֵּר` and
        `דֻּבַּר` — because Hebrew writes two binyanim of one root the same way without
        points. Refusing all of those would leave the table off most of the verbs a reader
        meets, which is not caution, it is uselessness.

        The points break the tie. A form the reader actually saw, spelled out, belongs to
        one of the candidates and not the other, and that is the one.

        None where nothing matches at all, and None where the points do not settle it
        either: a wrong conjugation table is worse than no table, and the way out to
        Pealim is still on the card.
        """
        found = self.by_form.get(bare(word)) or ()
        if not found:
            return None
        if len(found) == 1:
            return self.verbs.get(found[0])
        if seen:
            exact = [
                lid
                for lid in found
                if (verb := self.verbs.get(lid))
                # The lemma as well as the forms: a source lists a verb's dictionary form
                # once, at the head, and not again among its own inflections. Checking
                # only the forms missed `הָלַךְ` — the very word that made this necessary.
                and (verb.lemma == seen or any(form.written == seen for form in verb.forms))
            ]
            if len(exact) == 1:
                return self.verbs.get(exact[0])
        return None


EMPTY = Table(verbs={}, by_form={})


@lru_cache(maxsize=1)
def table(path: Path | None = None) -> Table:
    """The shipped table, read once.

    An empty one where the file is absent or unreadable, which is a working state: the
    card draws the root, the binyan and the way out to Pealim exactly as it did before.
    """
    where = path or TABLE
    if not where.is_file():
        return EMPTY
    try:
        with gzip.open(where, "rt", encoding="utf-8") as raw:
            loaded = json.load(raw)
    except (OSError, json.JSONDecodeError, EOFError):
        return EMPTY
    if not isinstance(loaded, dict):
        return EMPTY
    names = [str(name) for name in loaded.get("features") or ()]
    verbs: dict[str, Paradigm] = {}
    for lid, row in (loaded.get("verbs") or {}).items():
        if not isinstance(row, list) or len(row) != 2:
            continue
        lemma, forms = row
        verbs[str(lid)] = Paradigm(
            lemma=str(lemma),
            forms=tuple(
                Form(
                    written=str(written),
                    features=tuple(names[at] for at in codes if 0 <= at < len(names)),
                )
                for written, codes in forms[:MOST]
            ),
        )
    by_form = {
        str(form): tuple(str(lid) for lid in ids)
        for form, ids in (loaded.get("by_form") or {}).items()
    }
    return Table(verbs=verbs, by_form=by_form)
