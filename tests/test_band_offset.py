"""The aim moves with what you finish (design.md §12, 2026-11-05; targum-internal#615).

A reader's aim inside the band is moved by an offset learned from what became of the
texts suggested to them: Thompson sampling over three aims, a draw a day seeded by the
reader and the day, under six outcomes the aim as it is. The floor never moves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from targum import choose
from targum.accounts import Store

DAY = "2026-11-05"
NOW = 1_762_300_000_000


def _person(store: Store, n: int = 1) -> Any:
    signed = store.finish_sign_in(store.start_sign_in(f"reader{n}@example.com"))
    assert signed is not None
    return signed[0]


def test_the_three_aims_move_inside_the_band_and_never_the_band() -> None:
    assert choose.aim() == choose.band().aim == (0.94, 0.97)
    assert choose.aim(offset=choose.OFFSETS[choose.HARDER]) == (0.92, 0.95)
    assert choose.aim(offset=choose.OFFSETS[choose.EASIER]) == (0.96, 0.99)
    for offset in choose.OFFSETS.values():
        low, high = choose.aim(offset=offset)
        assert choose.FLOOR < low and high < choose.TOO_EASY
    # Under the floor a text is still under it, whatever the offset.
    assert choose.key(0.89, offset=-0.02)[0] == 1


def test_an_offset_reorders_the_band_and_nothing_else() -> None:
    stretch, middle = 0.925, 0.955
    assert choose.key(middle) < choose.key(stretch), "as it is, 95.5% before 92.5%"
    harder = choose.OFFSETS[choose.HARDER]
    assert choose.key(stretch, offset=harder) < choose.key(middle, offset=harder)
    easier = choose.OFFSETS[choose.EASIER]
    assert choose.key(0.98, offset=easier) < choose.key(stretch, offset=easier)


def test_each_share_speaks_for_one_aim_and_only_inside_the_band() -> None:
    assert choose.arm(0.91) == choose.HARDER
    assert choose.arm(0.95) == choose.AS_IT_IS
    assert choose.arm(0.98) == choose.EASIER
    assert choose.arm(0.85) is None and choose.arm(0.999) is None and choose.arm(None) is None


def test_a_thin_record_keeps_the_aim_as_it_is() -> None:
    few = [(0.91, choose.FINISHED)] * (choose.LEAST_OUTCOMES - 1)
    assert all(choose.learned(few, f"1:he:{day}") == 0.0 for day in range(50))
    # Outcomes outside the band do not count towards the six.
    outside = few + [(0.85, choose.FINISHED), (0.999, choose.ASIDE)]
    assert choose.learned(outside, "1:he:x") == 0.0


def test_a_reader_who_finishes_stretches_is_mostly_given_the_harder_aim() -> None:
    record = [(0.915, choose.FINISHED)] * 8 + [(0.955, choose.ASIDE)] * 6
    drawn = [choose.learned(record, f"7:he:2026-11-{day:02d}") for day in range(1, 101)]
    assert drawn.count(choose.OFFSETS[choose.HARDER]) >= 80
    # The same reader on the same day draws the same: a reload never reshuffles.
    assert choose.learned(record, "7:he:2026-11-05") == choose.learned(record, "7:he:2026-11-05")


def test_a_reader_who_sets_aside_the_stretch_is_mostly_given_the_easier_aim() -> None:
    record = [(0.92, choose.ASIDE)] * 6 + [(0.95, choose.ASIDE)] * 4
    record += [(0.98, choose.FINISHED)] * 8
    drawn = [choose.learned(record, f"8:he:{day}") for day in range(100)]
    assert drawn.count(choose.OFFSETS[choose.EASIER]) >= 80


def test_a_record_that_agrees_with_the_research_keeps_the_aim_as_it_is() -> None:
    record = [(0.95, choose.FINISHED)] * 10 + [(0.915, choose.ASIDE), (0.98, choose.ASIDE)]
    drawn = [choose.learned(record, f"9:he:{day}") for day in range(100)]
    assert drawn.count(0.0) >= 80


def test_the_record_says_one_outcome_a_text(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    person = _person(store)

    def note(act: str, document: str, **more: Any) -> dict[str, Any]:
        return {
            "kind": "suggest",
            "day": DAY,
            "at": more.pop("at", NOW - 1000),
            "act": act,
            "origin": "shelf",
            "document": document,
            "language": more.pop("language", "he"),
            **more,
        }

    store.add_events(
        person,
        [
            note("shown", "a", coverage=0.92),
            note("opened", "a", coverage=0.93),
            note("finished", "a"),
            # Set aside, then opened another day and finished: it was finished.
            note("shown", "b", coverage=0.96),
            note("aside", "b", coverage=0.96),
            note("finished", "b"),
            note("shown", "c", coverage=0.98),
            note("aside", "c", coverage=0.98),
            # Only shown, or opened and not finished: says nothing yet.
            note("shown", "d", coverage=0.95),
            note("opened", "e", coverage=0.95),
            # A harder pick was asked for under the floor.
            note("aside", "f", coverage=0.88, harder=True),
            # Another language, and a suggestion older than the window.
            note("finished", "g", coverage=0.95, language="ru"),
            note("finished", "h", coverage=0.95, at=NOW - 91 * 86_400_000),
        ],
    )
    got = sorted(store.suggest_outcomes(person.id, "he", days=90, at=NOW))
    assert got == [(0.92, "finished"), (0.96, "finished"), (0.98, "aside")]
    assert store.suggest_outcomes(None, "he") == []


def test_the_offset_comes_from_the_record_and_goes_with_it(tmp_path: Path, monkeypatch) -> None:
    store = Store(tmp_path / "words.db")
    person = _person(store)
    monkeypatch.setattr(
        store,
        "suggest_outcomes",
        lambda person_id, language, *, days: [(0.915, "finished")] * 12 + [(0.955, "aside")] * 6,
    )
    harder = choose.OFFSETS[choose.HARDER]
    days = [f"2026-11-{day:02d}" for day in range(1, 31)]
    drawn = [choose.offset_for(store, person.id, "he", day) for day in days]
    assert drawn.count(harder) >= 24
    monkeypatch.undo()
    # The real, empty record: the aim as it is, and nobody has an offset.
    assert choose.offset_for(store, person.id, "he", DAY) == 0.0
    assert choose.offset_for(store, None, "he", DAY) == 0.0
    assert choose.offset_for(None, person.id, "he", DAY) == 0.0


def test_erasing_the_record_takes_the_offset_with_it(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    person = _person(store)
    store.add_events(
        person,
        [
            {"kind": "suggest", "day": DAY, "at": NOW, "act": "finished", "origin": "shelf",
             "document": f"t{n}", "language": "he", "coverage": 0.915}
            for n in range(10)
        ],
    )  # fmt: skip
    assert len(store.suggest_outcomes(person.id, "he", at=NOW)) == 10
    store.forget_events(person)
    assert store.suggest_outcomes(person.id, "he", at=NOW) == []
