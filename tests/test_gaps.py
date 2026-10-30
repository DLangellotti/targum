"""Your biggest grammar gap: the Grammar grid's arithmetic (design.md §12, "What next leads
with your biggest grammar gap", 2026-10-30; targum-internal#604).

The page is `test_progress_gap_browser.py`; the cache it is read from is
`test_occurrences.py`.
"""

from __future__ import annotations

from typing import Any

from targum import gaps
from targum.gaps import CELL_FLOOR, ROW_FLOOR, grid, tense_of, verb_form

KNOWN = 9
LEARNING = 2
IGNORED = 0


def test_a_verbs_tense_is_read_off_its_morphology() -> None:
    assert tense_of("UPOS=VERB|Person=1|Tense=Past") == "past"
    assert tense_of("UPOS=VERB|Tense=Pres|VerbForm=Part") == "present"
    assert tense_of("UPOS=VERB|Tense=Fut|VerbForm=Fin") == "future"
    assert tense_of("UPOS=VERB|Tense=Imp") == "imperative"
    assert tense_of("UPOS=VERB|VerbForm=Inf") == "infinitive"
    # A participle with no tense stands as a present verb.
    assert tense_of("UPOS=VERB|VerbForm=Part") == "present"
    assert tense_of("UPOS=VERB|VerbForm=Fin") is None
    assert tense_of(None) is None


def test_only_a_verb_with_a_binyan_and_a_tense_is_a_form() -> None:
    verb = {"pos": "VERB", "binyan": "התפעל", "feats": "UPOS=VERB|Tense=Past"}
    assert verb_form(verb) == ("hitpael", "past")
    assert verb_form({**verb, "binyan": None}) is None, "never guessed"
    assert verb_form({**verb, "feats": "UPOS=VERB"}) is None
    assert verb_form({**verb, "pos": "NOUN"}) is None
    assert {key for _name, key in gaps.BINYANIM} == {
        "paal",
        "nifal",
        "piel",
        "pual",
        "hifil",
        "hufal",
        "hitpael",
    }


def test_a_verb_the_annotation_named_no_binyan_takes_the_tables_where_it_is_sure() -> None:
    """Since the DICTA swap the annotation names only pa'al and hitpa'el; the CC0 table
    fills the rest where every verb it finds for the lemma agrees, and a gap otherwise."""
    past = "UPOS=VERB|Tense=Past"
    assert verb_form({"pos": "VERB", "lemma": "דיבר", "feats": past}) == ("piel", "past")
    assert verb_form({"pos": "VERB", "lemma": "הכניס", "feats": past}) == ("hifil", "past")
    # ספר is סָפַר, סִפֵּר and סֻפַּר: the table is not sure, so nothing is counted.
    assert verb_form({"pos": "VERB", "lemma": "ספר", "feats": past}) is None
    # The annotation's binyan is never overruled.
    assert verb_form({"pos": "VERB", "lemma": "דיבר", "binyan": "פעל", "feats": past}) == (
        "paal",
        "past",
    )


def forms(**cells: dict[str, int]) -> dict[tuple[str, str], dict[str, int]]:
    """`paal_past={"כתב": 12}` -> {("paal", "past"): {"כתב": 12}}."""
    return {tuple(name.split("_", 1)): words for name, words in cells.items()}  # type: ignore[misc]


def test_a_square_is_the_share_of_tokens_whose_word_is_known() -> None:
    said = grid(
        forms(paal_past={"כתב": 30, "הלך": 10}, hitpael_past={"התלבש": 20, "התקדם": 20}),
        {"כתב": KNOWN, "הלך": LEARNING, "התלבש": KNOWN},
    )
    assert said is not None
    rows = {row["binyan"]: row for row in said["rows"]}
    assert [row["binyan"] for row in said["rows"]] == [key for _name, key in gaps.BINYANIM]
    assert rows["paal"]["cells"]["past"]["known"] == 75, "tokens, not words: 30 of 40"
    assert rows["hitpael"]["cells"]["past"]["known"] == 50
    assert rows["paal"]["cells"]["future"] is None, "nothing met is no figure"
    words = rows["paal"]["cells"]["past"]["words"]
    assert words[0] == {"lemma": "כתב", "count": 30, "known": True}, "most met first"


def test_a_square_under_the_floor_says_nothing_and_its_tokens_still_count() -> None:
    few = {f"w{n}": 1 for n in range(CELL_FLOOR - 1)}
    said = grid(
        forms(paal_past={"כתב": ROW_FLOOR}, paal_future=few, nifal_past={"נכנס": ROW_FLOOR}),
        {"כתב": KNOWN},
    )
    assert said is not None
    paal = said["rows"][0]
    assert paal["cells"]["future"] is None
    assert paal["tokens"] == ROW_FLOOR + CELL_FLOOR - 1
    assert said["cellFloor"] == CELL_FLOOR and said["rowFloor"] == ROW_FLOOR


def test_the_gap_is_the_weakest_pattern_with_enough_forms() -> None:
    marked = {"כתב": KNOWN, "נכנס": KNOWN, "התלבש": LEARNING, "דיבר": LEARNING}
    said = grid(
        forms(
            paal_past={"כתב": 40},
            nifal_past={"נכנס": 30, "נשאר": 10},
            hitpael_past={"התלבש": 30, "התכתב": 5},
            # Weaker still, but under the row floor: never named.
            piel_past={"דיבר": ROW_FLOOR - 1},
        ),
        {**marked, "התכתב": KNOWN},
    )
    assert said is not None
    gap = said["gap"]
    assert gap["binyan"] == "hitpael"
    assert gap["known"] == 14, "5 of 35"
    # The others pooled: 40 + 30 known of 80 tokens.
    assert gap["others"] == 88
    assert gap["examples"] == ["התלבש", "התכתב"], "most met first"


def test_an_ignored_word_comes_out_of_the_count() -> None:
    said = grid(
        forms(paal_past={"כתב": 30, "שם": 100}, nifal_past={"נכנס": 30}),
        {"כתב": KNOWN, "שם": IGNORED},
    )
    assert said is not None
    assert said["rows"][0]["cells"]["past"]["known"] == 100
    assert all(word["lemma"] != "שם" for word in said["rows"][0]["cells"]["past"]["words"])


def test_percentages_never_round_into_a_lie() -> None:
    said = grid(
        forms(paal_past={"כתב": 999, "הלך": 1}, nifal_past={"נכנס": 1, "נשאר": 999}),
        {"כתב": KNOWN, "נכנס": KNOWN},
    )
    assert said is not None
    assert said["rows"][0]["cells"]["past"]["known"] == 99, "under all of it is never 100%"
    assert said["rows"][1]["cells"]["past"]["known"] == 1, "above none of it is never 0%"


def test_with_no_pattern_enough_there_is_no_grid() -> None:
    assert grid(forms(paal_past={"כתב": ROW_FLOOR - 1}), {"כתב": KNOWN}) is None
    assert grid({}, {}) is None


def test_one_pattern_enough_draws_the_grid_and_names_no_gap() -> None:
    said: Any = grid(forms(paal_past={"כתב": ROW_FLOOR}), {})
    assert said is not None and said["gap"] is None


def test_no_gap_where_the_weakest_is_as_strong_as_the_rest() -> None:
    said: Any = grid(
        forms(paal_past={"כתב": ROW_FLOOR}, nifal_past={"נכנס": ROW_FLOOR}),
        {"כתב": KNOWN, "נכנס": KNOWN},
    )
    assert said is not None and said["gap"] is None
