"""What a licence lets the corpus do, decided once and asked rather than remembered.

Every text targum ingests leaves sentence-aligned pairs, lemma annotations, vowelling
with its guesses marked, and where a recording is attached, word-level timings. That
exhaust is the asset. It is only an asset if its terms are known, and terms that live in
somebody's memory of where each piece came from are not known — they are reconstructible,
expensively, later.

So the licence string each source already carries is turned into a verdict here, and the
verdict is computed rather than typed. A licence recorded once and read by a function is
a question anybody can ask; a verdict typed into a field is one more thing to keep true.

**The distinction that matters, and it is easy to get backwards.**

*ShareAlike does not block a business.* CC BY-SA permits commercial use outright. What it
requires is that derivatives go out under the same terms, so a corpus built on BY-SA
sources can be sold and cannot be kept secret. That is a constraint on exclusivity, not
on revenue, and treating it as a blocker gives up most of the free Hebrew there is.

*NonCommercial is the one that closes doors.* It bites on the commercial character of the
offering rather than on which individual paid, so it is the term that has to be found
before a paid tier exists rather than after.

*NoDerivatives closes them harder.* Everything this product does to a text — cutting,
aligning, pointing, glossing — is derivative by construction, so ND is not a licence
targum can build on at all, at any price.

Not every artefact inherits its source's terms. A list of word offsets is close to an
uncopyrightable fact about a recording; a cut audio segment is unambiguously a derivative
work and carries the licence onward. `Verdict.derivatives` is about the second kind,
which is the kind this product makes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Standing(StrEnum):
    """What a source's terms allow, in the one dimension that decides anything."""

    #: No rights reserved, or none that survive. Nothing is owed.
    free = "free"
    #: Usable commercially, and something is owed — a credit, or sharing alike.
    owed = "owed"
    #: Not usable in a commercial offering. NonCommercial, and anything ND touches.
    closed = "closed"
    #: Nothing was recorded. Not the same as free, and deliberately not treated as it.
    unknown = "unknown"


@dataclass(frozen=True)
class Verdict:
    """What one licence string means, in the terms a decision actually needs."""

    standing: Standing
    #: May derived data — aligned pairs, cut audio, annotations — leave targum inside a
    #: commercial offering. The question #115 asks the corpus to be able to answer.
    exportable: bool
    #: A credit must travel with it.
    attribution: bool
    #: Derivatives must go out under the same terms. Sellable, not keepable.
    sharealike: bool
    #: Why, in a phrase, for a report somebody reads rather than parses.
    because: str


#: Matched on the normalised string rather than parsed, because a licence is written the
#: way its source writes it — "CC BY-SA 3.0", "cc-by-sa-4.0", "public domain" — and the
#: whole point of keeping it verbatim is that it can be re-checked against the page it
#: was read from. Normalising for the match and keeping the original is how both stay true.
def _flat(licence: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (licence or "").lower()).strip()


_PUBLIC = ("public domain", "publicdomain", "cc0", "pd", "no known copyright")


def verdict(licence: str) -> Verdict:
    """What this licence string allows.

    Order matters: NonCommercial and NoDerivatives are checked before the permissive
    families, because "CC BY-NC-SA" contains "BY" and "SA" and answering on those would
    read the most restrictive licence in the set as one of the friendliest.
    """
    flat = _flat(licence)
    if not flat:
        return Verdict(
            Standing.unknown,
            exportable=False,
            attribution=False,
            sharealike=False,
            because="no licence recorded",
        )

    # Refused first, and both are refusals rather than obligations.
    if re.search(r"\bnc\b|noncommercial|non commercial", flat):
        return Verdict(
            Standing.closed,
            exportable=False,
            attribution=True,
            sharealike="sa" in flat.split(),
            because="NonCommercial: bites on the offering, not on who paid",
        )
    if re.search(r"\bnd\b|noderiv|no derivatives", flat):
        return Verdict(
            Standing.closed,
            exportable=False,
            attribution=True,
            sharealike=False,
            because="NoDerivatives: everything targum makes is a derivative",
        )

    if any(word in flat for word in _PUBLIC):
        return Verdict(
            Standing.free,
            exportable=True,
            attribution=False,
            sharealike=False,
            because="public domain: nothing is owed, and it is credited anyway",
        )

    parts = flat.split()
    if "sa" in parts or "sharealike" in flat:
        return Verdict(
            Standing.owed,
            exportable=True,
            attribution=True,
            sharealike=True,
            because="ShareAlike: sellable, not keepable — derivatives go out the same way",
        )
    if "by" in parts or "attribution" in flat:
        return Verdict(
            Standing.owed,
            exportable=True,
            attribution=True,
            sharealike=False,
            because="Attribution: a credit travels with it",
        )
    if "mit" in parts or "apache" in flat or "bsd" in parts:
        return Verdict(
            Standing.owed,
            exportable=True,
            attribution=True,
            sharealike=False,
            because="permissive: a notice travels with it",
        )

    # Something is written down and it is not one of the shapes above. Unknown rather
    # than free: a licence nobody here recognises is a licence nobody here has read.
    return Verdict(
        Standing.unknown,
        exportable=False,
        attribution=True,
        sharealike=False,
        because=f"unrecognised terms: {licence.strip()!r}",
    )


def exportable(licence: str) -> bool:
    """Whether derived data may leave targum inside a commercial offering."""
    return verdict(licence).exportable
