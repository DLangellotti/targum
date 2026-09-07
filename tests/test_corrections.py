"""The correction store, door 1 (targum-internal#164): every human judgement about a
word, kept with provenance. Today the author's hand on a gloss and a grounding at a
reader's tap; the editor's and the reader's doors come later."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum.accounts import Store
from targum.annotate import gloss as gloss_module
from targum.annotate.gloss import Sense, forget_gloss, gloss_one, set_gloss
from targum.cache import Cache
from targum.cli import app
from targum.serve import grounding_note


def test_a_judgement_is_written_down_with_its_provenance_and_read_back_newest_first(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "words.db")
    assert store.corrections() == []
    first = store.correct(
        "gloss",
        who="author",
        licence="targum",
        term="עם",
        language="he",
        target="en",
        before="people; nation",
        after="with",
        context="הלכתי עם אחי",
        reason="the preposition, not the noun",
    )
    second = store.correct("lemma", who="editor", term="שרוצים", before="רצה", after="רוצה")
    rows = store.corrections()
    assert [row["id"] for row in rows] == [second, first], "newest first"
    assert rows[1]["who"] == "author" and rows[1]["licence"] == "targum"
    assert rows[1]["before"] == "people; nation" and rows[1]["after"] == "with"
    assert rows[1]["context"] == "הלכתי עם אחי" and rows[1]["at"] > 0
    assert [row["stage"] for row in store.corrections(stage="lemma")] == ["lemma"]
    long = store.correct("gloss", who="reader", context="x" * 2000)
    assert len(store.corrections(stage="gloss", limit=1)[0]["context"]) == 500
    assert long > second


def test_the_authors_hand_on_a_gloss_applies_and_returns_what_stood(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    assert forget_gloss("עם", "he", "en", "test", cache=cache) is None, "nothing stood"
    stood = set_gloss("עם", "he", "en", "test", Sense("with"), cache=cache)
    assert stood is None
    key = cache.key("gloss", lemma="עם", source="he", target="en", provider="test")
    kept = cache.get("gloss", key)
    assert kept == {
        "gloss": "with",
        "part_of_speech": "",
        "citation": "",
        "plural": "",
        "grounded": True,
    }, "the author's gloss stands for good: grounded, so no sentence buys it again"
    was = forget_gloss("עם", "he", "en", "test", cache=cache)
    assert was is not None and was.gloss == "with" and was.grounded
    assert cache.get("gloss", key) is None and not cache.drop("gloss", key)


class Provider:
    name = "test"

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    def gloss(
        self,
        lemmas: list[str],
        source: str,
        target: str,
        _on: Any,
        contexts: dict[str, str] | None = None,
    ) -> dict[str, tuple[str, str, str, str]]:
        context = (contexts or {}).get(lemmas[0], "")
        self.asked.append((lemmas[0], context))
        return {lemmas[0]: (("with" if context else "people; nation"), "", "", "")}


def test_a_grounding_tells_the_store_what_stood_and_what_stands(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache")
    provider = Provider()
    told: list[tuple[Sense | None, Sense, str]] = []

    def note(before: Sense | None, after: Sense, context: str) -> None:
        told.append((before, after, context))

    bare = gloss_one("עם", "he", "en", provider, cache=cache, on_grounded=note)  # type: ignore[arg-type]
    assert bare is not None and bare.gloss == "people; nation" and not bare.grounded
    assert told == [], "bought bare: nobody decided anything"
    grounded = gloss_one(
        "עם",
        "he",
        "en",
        provider,
        cache=cache,
        context="הלכתי עם אחי",
        on_grounded=note,  # type: ignore[arg-type]
    )
    assert grounded is not None and grounded.grounded and grounded.gloss == "with"
    assert len(told) == 1
    before, after, context = told[0]
    assert before is not None and before.gloss == "people; nation"
    assert after.gloss == "with" and context == "הלכתי עם אחי"
    again = gloss_one(
        "עם",
        "he",
        "en",
        provider,
        cache=cache,
        context="עם ישראל",
        on_grounded=note,  # type: ignore[arg-type]
    )
    assert again == grounded and len(told) == 1, "grounded stands; nothing is bought or told"


def test_the_readers_grounding_row_names_a_role_and_never_fails_the_lookup(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    note = grounding_note(store, "עם", "he", "en")
    note(Sense("people; nation"), Sense("with", grounded=True), "הלכתי עם אחי")
    (row,) = store.corrections()
    assert row["who"] == "reader" and row["licence"] == ""
    assert row["before"] == "people; nation" and row["after"] == "with"
    assert row["context"] == "הלכתי עם אחי" and row["term"] == "עם"
    grounding_note(None, "עם", "he", "en")(None, Sense("with"), "x"), "no store, no row, no error"
    note(None, Sense("with", grounded=True), "y")
    assert store.corrections()[0]["before"] == "", "a word that had no gloss stood as nothing"


def test_the_command_applies_the_correction_and_keeps_the_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gloss_module, "Cache", lambda root=None: Cache(tmp_path / "cache"))
    db = tmp_path / "words.db"
    runner = CliRunner()
    said = runner.invoke(
        app,
        [
            "correct",
            "עם",
            "--meaning",
            "with",
            "--context",
            "הלכתי עם אחי",
            "--reason",
            "preposition",
            "--store",
            str(db),
        ],
    )
    assert said.exit_code == 0, said.output
    assert "Recorded #1" in said.output and "was not glossed" in said.output
    rows = Store(db).corrections()
    assert (
        rows[0]["who"] == "author" and rows[0]["after"] == "with" and rows[0]["licence"] == "targum"
    )

    gone = runner.invoke(app, ["correct", "עם", "--forget", "--store", str(db)])
    assert gone.exit_code == 0, gone.output
    assert "was 'with'" in gone.output and "forgotten" in gone.output
    assert (
        Store(db).corrections()[0]["after"] == "" and Store(db).corrections()[0]["before"] == "with"
    )

    neither = runner.invoke(app, ["correct", "עם", "--store", str(db)])
    assert neither.exit_code != 0
    both = runner.invoke(app, ["correct", "עם", "--meaning", "x", "--forget", "--store", str(db)])
    assert both.exit_code != 0

    listed = runner.invoke(app, ["corrections", "--store", str(db)])
    assert (
        listed.exit_code == 0
        and "#2 gloss author" in listed.output
        and "#1 gloss author" in listed.output
    )
    empty = runner.invoke(app, ["corrections", "--stage", "lemma", "--store", str(db)])
    assert "No corrections yet." in empty.output
