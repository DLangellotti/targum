"""What a licence lets the corpus do.

The verdicts are the ones targum-internal #115 argues for, and the two that are easy to
get backwards have tests of their own: ShareAlike constrains exclusivity rather than
revenue, and NonCommercial is the term that actually closes a door.
"""

from __future__ import annotations

import pytest

from targum.licensing import Standing, exportable, verdict


@pytest.mark.parametrize(
    "licence",
    ["public domain", "Public Domain", "CC0 1.0", "PD", "no known copyright"],
    ids=["plain", "cased", "cc0", "abbreviated", "phrased"],
)
def test_public_domain_owes_nothing(licence: str) -> None:
    """Credited anyway — that is a choice this product makes, not a term it is under."""
    call = verdict(licence)
    assert call.standing is Standing.free
    assert call.exportable and not call.attribution and not call.sharealike


def test_sharealike_is_sellable_and_not_keepable() -> None:
    """The one most likely to be treated as a blocker, and it is not one.

    BY-SA permits commercial use outright; what it forbids is keeping the derivative to
    yourself. Reading it as "cannot be used in a business" would give up most of the
    freely licensed Hebrew there is — 32 of the 41 recordings on the shelf are BY-SA.
    """
    call = verdict("CC BY-SA 3.0")
    assert call.standing is Standing.owed
    assert call.exportable, "ShareAlike does not block a business"
    assert call.sharealike and call.attribution


def test_noncommercial_is_the_one_that_closes_the_door() -> None:
    """It bites on the character of the offering, not on which reader paid."""
    for licence in ("CC BY-NC 4.0", "CC BY-NC-SA 4.0", "cc-by-nc-nd-4.0", "NonCommercial"):
        call = verdict(licence)
        assert call.standing is Standing.closed, licence
        assert not call.exportable, licence


def test_noncommercial_is_read_before_the_letters_it_contains() -> None:
    """ "CC BY-NC-SA" holds BY and SA. Answering on those would read the most restrictive
    licence in the set as one of the friendliest, which is the failure that matters."""
    assert not exportable("CC BY-NC-SA 4.0")
    assert exportable("CC BY-SA 4.0")


def test_noderivatives_is_refused_outright() -> None:
    """Cutting, aligning, pointing and glossing are all derivative. There is no price at
    which ND becomes usable here."""
    call = verdict("CC BY-ND 4.0")
    assert call.standing is Standing.closed and not call.exportable


def test_attribution_alone_travels_with_a_credit() -> None:
    call = verdict("CC BY 4.0")
    assert call.standing is Standing.owed
    assert call.exportable and call.attribution and not call.sharealike


def test_nothing_recorded_is_unknown_and_not_free() -> None:
    """The distinction the whole issue rests on. A source with no licence written down is
    not a source with no terms — it is one nobody has checked, and treating the two alike
    is how a corpus acquires an obligation it cannot see."""
    for blank in ("", "   ", None):  # type: ignore[arg-type]
        call = verdict(blank)  # type: ignore[arg-type]
        assert call.standing is Standing.unknown
        assert not call.exportable


def test_an_unrecognised_licence_says_so_rather_than_guessing() -> None:
    """A licence nobody here recognises is one nobody here has read. It quotes the string
    back, so the report names what to go and check."""
    call = verdict("Ben-Yehuda Project terms of use")
    assert call.standing is Standing.unknown
    assert not call.exportable
    assert "Ben-Yehuda" in call.because
