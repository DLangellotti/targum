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


#: The points, so a lemma can be read as letters-with-vowels rather than a string.
_POINTS = frozenset(
    "\u05b0\u05b1\u05b2\u05b3\u05b4\u05b5\u05b6\u05b7\u05b8"
    "\u05b9\u05ba\u05bb\u05bc\u05bd\u05c1\u05c2\u05c7"
)
_SHVA, _HIRIQ, _TSERE, _PATACH, _QAMATS = "\u05b0", "\u05b4", "\u05b5", "\u05b7", "\u05b8"
#: Qubuts and qamats qatan, the two ways the passive binyanim point their first letter.
_QUBUTS, _QATAN = "\u05bb", "\u05c7"
_HE, _TAV, _NUN = "\u05d4", "\u05ea", "\u05e0"

#: How few of a lemma's letters may be pointed before it is not a pointed lemma. The
#: dump carries both — `הָלַךְ` and `אוחזר` sit side by side — and an unpointed one says
#: nothing about its binyan, so it is refused rather than read as פעל.
_LEAST_POINTED = 2


def _units(word: str) -> list[tuple[str, str]]:
    """Each Hebrew letter with the points that follow it, in order."""
    out: list[list[str]] = []
    for ch in word:
        if ch in _POINTS:
            if out:
                out[-1][1] += ch
        elif "\u05d0" <= ch <= "\u05ea":
            out.append([ch, ""])
    return [(letter, points) for letter, points in out]


def binyan_of(lemma: str) -> str | None:
    """Which binyan a *pointed* lemma is built in, or None where it cannot be read.

    Wikidata's Hebrew lexemes carry no binyan statement — checked against the dump — so
    the conjugation lookup had no way to tell `הָלַךְ` from `הִלֵּךְ` except by hoping the
    reader's own pointing matched one of them (targum-internal#307). This reads it off
    the lemma instead, which is owned outright and behind no licence door: the lemma is
    the third-person masculine singular past, and that is the form each binyan spells in
    its own pattern. It is `hebrew.root_of` run the other way.

    Only the prefix and the first two vowels are asked, because that is what the seven
    patterns differ in and the rest of the word is the root's business. A lemma with
    fewer than two points is not pointed, and says nothing; a pattern that is not one of
    the seven is None. Both refuse rather than guess, for the reason the card refuses a
    root it could not work out: a wrong conjugation table is worse than none.
    """
    units = _units(lemma)
    if len(units) < 2 or sum(1 for _, points in units if points) < _LEAST_POINTED:
        return None
    (first, points), (second, after) = units[0], units[1]
    # A prefix is a prefix only when the letter after it is quiescent. הִפְעִיל and
    # נִפְעַל both put a shva there, and it is the whole of what separates them from a
    # root whose own first letter is ה or נ: הִלֵּךְ is פיעל of ה־ל־ך and נִסָּה is פיעל
    # of נ־ס־ה, and both were read as prefixed until this asked.
    quiescent = _SHVA in after
    if first == _HE and _HIRIQ in points and quiescent:
        # הִתְפַּעֵל keeps its ת; הִפְעִיל has the root's own letter there.
        return "התפעל" if second == _TAV else "הפעיל"
    if first == _HE and _HIRIQ in points:
        # A weak root's הִפְעִיל has no shva to give — הִגִּיד, הִתִּיר — and neither has the
        # פיעל of a root beginning with ה. They part on the vowel the second letter
        # carries: הִפְעִיל's own hiriq, against פיעל's tsere.
        if _HIRIQ in after:
            return "הפעיל"
        if _TSERE in after:
            return "פיעל"
        return None
    if first == _HE and (_QUBUTS in points or _QATAN in points) and quiescent:
        return "הופעל"
    if first == _NUN and _HIRIQ in points and quiescent:
        # נִפְעַל, and not נָתַן — which is פעל and carries a qamats, not a hiriq.
        return "נפעל"
    if _QUBUTS in points or _QATAN in points:
        return "פועל"
    if _HIRIQ in points and (_TSERE in after or _PATACH in after):
        return "פיעל"
    if _QAMATS in points:
        return "פעל"
    return None


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

    def of(self, word: str, seen: str = "", binyan: str | None = None) -> Paradigm | None:
        """The paradigm for a lemma or any inflected form of it.

        `seen` is a pointed spelling the word actually wore in the text, and it is what
        makes this usable. Unpointed, the commonest verbs in the language are ambiguous —
        `הלך` is both `הָלַךְ` and `הִלֵּךְ`, `נתן` is `נָתַן` and `נִתַּן`, `דבר` is `דִּבֵּר` and
        `דֻּבַּר` — because Hebrew writes two binyanim of one root the same way without
        points. Refusing all of those would leave the table off most of the verbs a reader
        meets, which is not caution, it is uselessness.

        The points break the tie. A form the reader actually saw, spelled out, belongs to
        one of the candidates and not the other, and that is the one.

        `binyan` is the conjugation targum already worked out for the occurrence, and it
        is the stronger of the two signals (targum-internal#307). The source carries no
        binyan statement, so each candidate's is read off its own pointed lemma
        (`binyan_of`); the candidate whose binyan is the one in the text is the verb.
        Measured over 114,291 verb tokens on the built shelf, this is what takes the
        table from 55.4% of them to 72.4%.

        Where both signals decide and they disagree, neither is taken. That is 0.1% of
        tokens and they are real conflicts — a נִפְעַל lemma whose surface form is spelled
        the way its פָּעַל cousin spells one — so the honest answer is the one the card
        has always given for a root it could not work out.

        None where nothing matches at all, and None where nothing settles it: a wrong
        conjugation table is worse than no table, and the way out to Pealim is still on
        the card.
        """
        found = self.by_form.get(bare(word)) or ()
        if not found:
            return None
        if len(found) == 1:
            return self.verbs.get(found[0])
        pointed = []
        if seen:
            pointed = [
                lid
                for lid in found
                if (verb := self.verbs.get(lid))
                # The lemma as well as the forms: a source lists a verb's dictionary form
                # once, at the head, and not again among its own inflections. Checking
                # only the forms missed `הָלַךְ` — the very word that made this necessary.
                and (verb.lemma == seen or any(form.written == seen for form in verb.forms))
            ]
        built = []
        if binyan:
            built = [
                lid
                for lid in found
                if (verb := self.verbs.get(lid)) and binyan_of(verb.lemma) == binyan
            ]
        if len(pointed) == 1 and len(built) == 1:
            return self.verbs.get(pointed[0]) if pointed[0] == built[0] else None
        if len(built) == 1:
            return self.verbs.get(built[0])
        if len(pointed) == 1:
            return self.verbs.get(pointed[0])
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
