"""The word list refuses a prefix letter (design.md §12, "A prefix or a function word
has a meaning and no stage", 2026-10-30)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from targum.accounts import Person, Store


def a_reader(tmp_path: Path) -> tuple[Store, Person]:
    store = Store(tmp_path / "targum.db")
    store.finish_sign_in(store.start_sign_in("a@example.com"))
    me = store.person_by_email("a@example.com")
    assert me is not None
    return store, me


def row(lemma: str, status: int, seen: int) -> dict[str, Any]:
    return {"language": "he", "lemma": lemma, "surface": lemma, "status": status, "seen": seen}


def held(store: Store, me: Person) -> dict[str, int]:
    return {r["lemma"]: r["status"] for r in store.pull(me)["words"] if not r.get("gone")}


def test_a_page_cached_from_before_cannot_put_a_prefix_on_the_list(tmp_path: Path) -> None:
    store, me = a_reader(tmp_path)
    store.push(me, {"words": [row("כ", 1, 10), row("כְּ", 2, 10), row("ספר", 1, 10)]})
    assert held(store, me) == {"ספר": 1}, "one letter, points or none, is not a word to learn"
    # Known and ignored are not the list, and stay the reader's to say.
    store.push(me, {"words": [row("ב", 9, 20), row("ל", 0, 20)]})
    assert held(store, me) == {"ספר": 1, "ב": 9, "ל": 0}
    # And known is not a way onto the list either.
    store.push(me, {"words": [row("ב", 1, 30)]})
    assert held(store, me)["ב"] == 9


def test_a_prefix_already_on_the_list_stays_and_can_come_off(tmp_path: Path) -> None:
    store, me = a_reader(tmp_path)
    # Kept before the refusal: written as an old sync wrote it.
    with store.write() as db:
        db.execute(
            "INSERT INTO word (person, language, lemma, surface, status, at, seen, revision)"
            " VALUES (?, 'he', 'כ', 'כ', 1, 1, 1, 1)",
            (me.id,),
        )
    assert held(store, me) == {"כ": 1}
    store.push(me, {"words": [row("כ", 3, 10)]})
    assert held(store, me) == {"כ": 3}, "it moves between stages as before"
    store.push(me, {"words": [{**row("כ", 3, 20), "gone": 1}]})
    assert held(store, me) == {}, "and the reader may take it off"
