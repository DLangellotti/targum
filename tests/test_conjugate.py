"""Filling a stub verb table by rule from its root and binyan (targum-internal#307).

A wrong conjugation table is worse than none, so most of this is about what the rule
refuses: a pattern that would spell a form the source already has differently, cells the
agreeing patterns disagree on, and verbs with too little to go on.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
from typing import Any

from targum.annotate.conjugate import (
    CELLS,
    LEMMA_CELL,
    Patterns,
    fill,
    finished,
    learn,
    plain,
    shape,
)
from targum.annotate.paradigms import TABLE, from_shipped, table

#: A strong פָּעַל in full spelling, cell by cell, with 1, 2 and 3 for the root's letters.
#: `future` is the vowel a dictionary has to tell you: יכתוב against ילמד.
_PAST = ["123תי", "123נו", "123ת", "123ת", "123תם", "123תן", "123", "123ה", "123ו", "123ו"]
_PRESENT = ["1ו23", "1ו23ת", "1ו23ים", "1ו23ות", "1ו23", "1ו23ת", "1ו23י", "1ו23ות"]
_FUTURE_O = ["א12ו3", "נ12ו3", "ת12ו3", "ת123י", "ת123ו", "ת12ו3נה"]
_FUTURE_O += ["י12ו3", "ת12ו3", "י123ו", "ת12ו3נה"]
_FUTURE_A = ["א123", "נ123", "ת123", "ת123י", "ת123ו", "ת123נה", "י123", "ת123", "י123ו", "ת123נה"]
_IMPERATIVE = ["12ו3", "123י", "123ו", "12ו3נה"]


def paal(root: str, future: list[str] = _FUTURE_O) -> list[tuple[str, tuple[str, ...]]]:
    """Every cell of a strong פָּעַל of this root, as the shipped table writes them."""
    spelled = _PAST + _PRESENT + future + _IMPERATIVE
    assert len(spelled) == len(CELLS)
    out = []
    for template, cell in zip(spelled, CELLS, strict=True):
        letters = "".join({"1": root[0], "2": root[1], "3": root[2]}.get(c, c) for c in template)
        out.append((finished(letters), cell))
    return out


def cell(forms: list[tuple[str, tuple[str, ...]]], *features: str) -> str:
    wanted = tuple(sorted(features))
    return next(written for written, at in forms if at == wanted)


def taught() -> Patterns:
    """Three tables with the o future and one with the a, all of one class."""
    return learn(
        [
            ("כָּתַב", "פעל", "כתב", paal("כתב")),
            ("פָּקַד", "פעל", "פקד", paal("פקד")),
            ("בָּדַק", "פעל", "בדק", paal("בדק")),
            ("שָׁכַב", "פעל", "שכב", paal("שכב", _FUTURE_A)),
        ]
    )


def some(root: str, *cells: tuple[str, ...], future: list[str] = _FUTURE_O) -> list[Any]:
    whole = paal(root, future)
    wanted = {tuple(sorted(one)) for one in cells}
    return [(written, at) for written, at in whole if at in wanted]


PAST_3MP = ("3rd", "masculine", "past", "plural")
PAST_1S = ("1st", "past", "singular")
PAST_2MP = ("2nd", "masculine", "past", "plural")
FUTURE_3MS = ("3rd", "future", "masculine", "singular")


def test_a_class_is_the_root_with_its_weak_letters_said_out_loud() -> None:
    assert shape("כתב", "פעל") == ("פעל:123", {"1": "כ", "2": "ת", "3": "ב"})
    assert shape("אכל", "פעל") == ("פעל:א23", {"2": "כ", "3": "ל"})
    assert shape("סבב", "פעל") == ("פעל:122", {"1": "ס", "2": "ב"})
    # A ס first only matters where it trades places with the ת.
    assert shape("סכל", "התפעל") == ("התפעל:ס23", {"2": "כ", "3": "ל"})
    assert shape("סכל", "פעל") is not None and shape("סכל", "פעל")[0] == "פעל:123"  # type: ignore[index]


def test_the_patterns_are_learned_from_complete_tables() -> None:
    learned = taught()
    assert set(learned) == {"פעל:123"}
    assert sum(learned["פעל:123"].values()) == 4
    assert len(learned["פעל:123"]) == 2, "one pattern for each future vowel"


def test_a_stub_is_filled_from_its_root() -> None:
    stub = some("דלק", PAST_1S, PAST_2MP, PAST_3MP, FUTURE_3MS)
    done = fill("דָּלַק", stub, taught(), "פעל")
    assert not done.refused
    added = list(done.forms)
    assert cell(added, "masculine", "present", "singular") == "דולק"
    assert cell(added, "masculine", "plural", "present") == "דולקים"
    assert cell(added, "3rd", "masculine", "past", "singular") == "דלק"
    assert cell(added, "1st", "future", "singular") == "אדלוק"
    assert cell(added, "2nd", "feminine", "imperative", "plural") == "דלוקנה"
    assert len(added) == len(CELLS) - 4, "everything it lacked, and nothing it had"


def test_what_the_source_has_is_never_spelled_again() -> None:
    stub = some("דלק", PAST_1S, PAST_2MP, PAST_3MP)
    done = fill("דָּלַק", stub, taught(), "פעל")
    have = {at for _, at in stub}
    assert not have & {at for _, at in done.forms}


def test_a_cell_the_agreeing_patterns_disagree_on_is_left_empty() -> None:
    """With only its past, דלק could be יִדְלֹק or יִדְלַק: the future is not guessed."""
    stub = some("דלק", PAST_1S, PAST_2MP, PAST_3MP)
    done = fill("דָּלַק", stub, taught(), "פעל")
    added = dict((at, written) for written, at in done.forms)
    assert tuple(sorted(FUTURE_3MS)) not in added
    assert done.withheld > 0
    # Where both futures spell it alike, it is filled: תדלקי either way.
    assert added[tuple(sorted(("2nd", "feminine", "future", "singular")))] == "תדלקי"
    # And the present, which no future vowel touches.
    assert added[tuple(sorted(("masculine", "present", "singular")))] == "דולק"


def test_a_form_no_pattern_spells_refuses_the_whole_verb() -> None:
    """The conflict case: the source writes a form the rule would write differently, so
    the rule is not this verb's and fills nothing at all."""
    stub = some("דלק", PAST_1S, PAST_2MP, PAST_3MP)
    stub.append(("ידלוקק", tuple(sorted(FUTURE_3MS))))
    done = fill("דָּלַק", stub, taught(), "פעל")
    assert done.forms == ()
    assert done.refused == "no pattern spells its forms"


def test_an_attested_form_picks_between_the_patterns() -> None:
    stub = some("דלק", PAST_1S, PAST_2MP, PAST_3MP, FUTURE_3MS)
    done = fill("דָּלַק", stub, taught(), "פעל")
    added = dict((at, written) for written, at in done.forms)
    assert added[tuple(sorted(("1st", "future", "singular")))] == "אדלוק"
    assert done.withheld == 0


def test_a_pointed_lemma_asks_only_its_own_binyan() -> None:
    stub = some("דלק", PAST_1S, PAST_2MP, PAST_3MP, FUTURE_3MS)
    done = fill("דִּלֵּק", stub, taught(), "פיעל")
    assert done.forms == ()
    assert done.refused == "no pattern spells its forms"


def test_an_unpointed_lemma_is_one_of_its_own_forms() -> None:
    stub = some("דלק", PAST_1S, PAST_2MP, FUTURE_3MS)
    done = fill("דלק", stub, taught())
    assert not done.refused
    assert tuple(sorted(("3rd", "masculine", "past", "singular"))) not in {
        at for _, at in done.forms
    }, "the lemma is the third person masculine singular past, and already there"


def test_too_little_to_go_on_is_refused() -> None:
    done = fill("דָּלַק", some("דלק", PAST_1S), taught(), "פעל")
    assert done.refused == "too few forms"
    thin = learn([("כָּתַב", "פעל", "כתב", paal("כתב"))])
    done = fill("דָּלַק", some("דלק", PAST_1S, PAST_2MP, PAST_3MP), thin, "פעל")
    assert done.refused == "too few tables behind it"


def test_a_root_of_another_class_is_not_read_into_this_one() -> None:
    """A root whose letters the class keeps literal is that other class's business: אכל
    is not filled from the patterns of כתב."""
    stub = some("אכל", PAST_1S, PAST_2MP, PAST_3MP, FUTURE_3MS)
    done = fill("אָכַל", stub, taught(), "פעל")
    assert done.refused == "no pattern spells its forms"


def test_plain_letters_and_final_forms() -> None:
    assert plain("כָּתַבְתֶּם") == "כתבתמ"
    assert finished("כתבתמ") == "כתבתם"
    assert LEMMA_CELL == CELLS.index(("3rd", "masculine", "past", "singular"))


# --- the shipped table ---------------------------------------------------------------


def shipped_raw() -> dict[str, Any]:
    with gzip.open(TABLE, "rt", encoding="utf-8") as raw:
        loaded: dict[str, Any] = json.load(raw)
    return loaded


def test_the_stub_for_eat_has_its_present_now() -> None:
    """`אָכַל` came through with ten forms and no `אוכל`, so the shelf's 819 tokens of it
    had no verb that eats among their candidates."""
    found = table().verbs["491557"]
    assert found.lemma == "אָכַל"
    written = {form.written: form for form in found.forms}
    assert "אוכל" in written and written["אוכל"].ruled
    assert "491557" in table().by_form["אוכל"]
    # Its future is יֹאכַל, not the יִכְתֹּב every other א-first verb would suggest, and
    # nothing the source has says which: so it is not drawn.
    assert "יאכל" not in written and "יאכול" not in written


def test_what_the_rule_added_is_kept_apart_from_the_source() -> None:
    loaded = shipped_raw()
    assert loaded["filled"], "the shipped table carries what was filled"
    source = from_shipped(loaded, ruled=False)
    assert not any(form.ruled for verb in source.verbs.values() for form in verb.forms)
    assert "491557" not in source.by_form.get("אוכל", ())
    ruled = from_shipped(loaded)
    for lid in loaded["filled"]:
        assert len(ruled.verbs[lid].forms) > len(source.verbs[lid].forms)
        # Every form the source has is still there, as the source wrote it.
        assert {f.written for f in source.verbs[lid].forms} <= {
            f.written for f in ruled.verbs[lid].forms
        }


def test_a_filled_table_reads_in_a_grammar_s_order() -> None:
    forms = table().verbs["491557"].forms
    order = [
        CELLS.index(tuple(sorted(f.features))) for f in forms if tuple(sorted(f.features)) in CELLS
    ]
    assert order == sorted(order)


def test_the_shipped_fills_are_what_the_rule_gives_now() -> None:
    """The file and the code cannot drift: rerunning the script changes nothing."""
    where = Path(__file__).resolve().parents[1] / "scripts" / "fill_paradigms.py"
    spec = importlib.util.spec_from_file_location("fill_paradigms", where)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    loaded = shipped_raw()
    again, _ = module.filled(loaded)
    assert again["filled"] == loaded["filled"]
    assert again["features"] == loaded["features"]
