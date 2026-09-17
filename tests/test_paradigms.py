"""The conjugation table on the card (targum-internal#300).

Most of this is about what it refuses to draw. A wrong conjugation table is worse than
none — the reader has no way to tell it is wrong, and the way out to Pealim is still on
the card — so an ambiguous lookup answers nothing rather than guessing.

The interesting case is that Hebrew makes the commonest verbs ambiguous *unpointed*:
`הלך` is both `הָלַךְ` and `הִלֵּךְ`. Refusing all of those would have left the table off
most of the verbs a reader meets. The points break the tie.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from targum.annotate.paradigms import TABLE, Form, Paradigm, Table, bare, table


@pytest.fixture(scope="module")
def shipped() -> Table:
    """The real table, as the wheel carries it."""
    return table()


def test_the_table_ships_in_the_package() -> None:
    """A reader fetches nothing (§11), so the data has to be inside the wheel."""
    assert TABLE.is_file(), "paradigms.json.gz is missing from the package"
    with gzip.open(TABLE, "rt", encoding="utf-8") as raw:
        loaded = json.load(raw)
    assert loaded["licence"] == "CC0-1.0", "the licence is the reason this source was chosen"
    assert loaded["source"] == "wikidata-lexemes"


def test_a_verb_is_found_by_its_lemma(shipped: Table) -> None:
    found = shipped.of("אמר")
    assert found is not None
    assert found.lemma == "אָמַר"
    assert len(found.forms) > 20, "a Hebrew verb has about thirty-three forms"


def test_a_verb_is_found_though_the_two_sources_call_it_different_things(
    shipped: Table,
) -> None:
    """The measurement that made this source usable. DICTA lemmatizes `בוא`, `מות`,
    `קום`; Wikidata's lemma is the 3ms past `בא`, `מת`, `קם`. Matching lemma to lemma
    finds a fifth of the verbs; matching against any form finds most of them."""
    for dicta, wikidata in (("בוא", "בָּא"), ("מות", "מֵת"), ("קום", "קָם")):
        found = shipped.of(dicta)
        assert found is not None, f"{dicta} should reach {wikidata}"
        assert bare(found.lemma) == bare(wikidata)


def test_the_points_settle_a_verb_two_binyanim_share(shipped: Table) -> None:
    """Unpointed `הלך` is both `הָלַךְ` (went) and `הִלֵּךְ` (walked about)."""
    assert shipped.of("הלך") is None, "unpointed, it is genuinely two verbs"
    went = shipped.of("הלך", "הָלַךְ")
    about = shipped.of("הלך", "הִלֵּךְ")
    assert went is not None and about is not None
    assert went.lemma != about.lemma


def test_points_that_do_not_settle_it_draw_nothing(shipped: Table) -> None:
    """A spelling that matches neither candidate is not a reason to pick one."""
    assert shipped.of("הלך", "הָלְכָה־שֶׁלֹּא־קַיֶּמֶת") is None


def test_a_word_that_is_not_a_verb_has_no_table(shipped: Table) -> None:
    """`יש` is the existential particle. targum-internal#305 stops it being tagged a
    verb at all; this is the second line of defence."""
    assert shipped.of("יש") is None


def test_an_unknown_word_draws_nothing(shipped: Table) -> None:
    assert shipped.of("שאיןכזובמציאות") is None
    assert shipped.of("") is None


def test_the_form_in_front_of_the_reader_is_recognised() -> None:
    """Compared on letters: the reader's pointing and the source's need not agree."""
    form = Form(written="הָלַכְתִּי", features=("past", "1st", "singular"))
    assert form.matches("הלכתי")
    assert form.matches("הָלַכְתִּי")
    assert not form.matches("הָלְכוּ")
    assert not form.matches("")


def test_a_missing_or_broken_table_is_an_empty_one(tmp_path: Path) -> None:
    """The card draws the root, the binyan and the way out to Pealim exactly as before."""
    assert table(tmp_path / "not-here.json.gz").verbs == {}
    broken = tmp_path / "broken.json.gz"
    broken.write_bytes(b"not gzip at all")
    assert table(broken).verbs == {}


def test_a_lemma_belonging_to_no_verb_in_the_table_is_not_invented() -> None:
    made = Table(
        verbs={"1": Paradigm(lemma="א", forms=(Form(written="א", features=()),))},
        by_form={"ב": ("nothing-here",)},
    )
    assert made.of("ב") is None, "an index pointing at a verb that is not there"


def test_object_suffix_forms_are_not_in_the_shipped_table(shipped: Table) -> None:
    """אֲמַרְתִּיו, "I said it" — real Hebrew, 14% of the forms, and not the table a
    learner came for. Dropped so the wheel stays small and the card stays readable."""
    found = shipped.of("אמר")
    assert found is not None
    assert not any(
        any(name.startswith("possessive") for name in form.features) for form in found.forms
    )
