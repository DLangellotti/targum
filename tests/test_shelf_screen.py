"""The shelf-search questions asked of Jev (targum-internal#319). Offline throughout: the
model is never reached, and its answers are written in by hand the shape the API returns
them."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from targum import shelf_screen as ss
from targum.catalogue import Tag
from targum.licensing import Standing

#: Two kept rows, shaped as `catalogue.json` holds them. One is a translation by its own
#: note, one has an English made from it, and one says nothing about where it came from.
ROWS: list[dict[str, Any]] = [
    {
        "id": "sw-1",
        "title": "Ci vediamo domani!",
        "author": "Tanya Luther Agarwal",
        "language": "it",
        "source": "storyweaver:257052",
        "credit": "Ci vediamo domani!, translated by Silvia Bianchi",
        "licence": "CC BY 4.0",
        "blurb": "A child says see you tomorrow to eight animals.",
        "english": "See You Tomorrow",
        "tags": [],
        "kind": "story",
        "difficulty": 18,
        "translations": [
            {"note": "The English original. The Italian came to it through a Russian translation."}
        ],
    },
    {
        "id": "mumu",
        "title": "Муму",
        "author": "Тургенев",
        "language": "ru",
        "source": "wikisource:ru:Муму",
        "credit": "Wikisource",
        "licence": "Public Domain",
        "blurb": "A deaf porter and his dog.",
        "english": "Mumu",
        "tags": ["history"],
        "kind": "story",
        "difficulty": 27,
        "translations": [{"note": "Garnett's translation from her Torrents of Spring volume."}],
    },
    {
        "id": "talk",
        "title": "Субботний влог",
        "author": "Russian with Dasha",
        "language": "ru",
        "source": "video:iROK3v80nHs",
        "credit": "Russian with Dasha",
        "licence": "",
        "tags": ["language"],
        "kind": "talk",
        "difficulty": 0,
        "translations": [],
    },
]

SAMPLES = {"mumu": ["В одной из отдалённых улиц Москвы...", "", "Из числа всей её челяди..."]}


def answer(
    language: float, origin: str, subject: str, prose: float | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "language": {"type": "noul", "noul": language},
        "origin": {
            "type": "choice",
            "choice": origin,
            "confidence": 0.7,
            "probabilities": {origin: 0.85},
        },
        "subject": {"type": "choice", "choice": subject, "confidence": 0.5},
        "learner": {"type": "noul", "noul": 0.6},
    }
    if prose is not None:
        out["prose"] = {"type": "noul", "noul": prose}
    return out


def test_every_subject_door_is_an_option() -> None:
    assert set(ss.SUBJECTS) == {tag.value for tag in Tag}
    assert ss.NO_SUBJECT not in ss.SUBJECTS


def test_the_state_holds_only_what_a_candidate_said_before_it_was_taken() -> None:
    """A blurb, an English title, tags and a kind were written after the row was accepted;
    a screen that saw them would be reading the answer. The licence stays out too: it is
    read in code, never by the model."""
    candidate = ss.from_row(ROWS[0])
    body = json.dumps(ss.state(candidate), ensure_ascii=False)
    for leaked in ("eight animals", "See You Tomorrow", '"story"', "CC BY", "sw-1"):
        assert leaked not in body, leaked
    assert "Italian" in body and "Silvia Bianchi" in body


def test_the_credit_is_left_out_where_it_only_repeats_the_author() -> None:
    assert "credit" not in ss.state(ss.from_row(ROWS[2]))


def test_prose_is_asked_only_where_there_is_an_opening_to_read() -> None:
    bare = ss.from_row(ROWS[0])
    sampled = ss.from_row(ROWS[1], SAMPLES["mumu"])
    assert "prose" not in ss.questions(bare)
    assert "prose" in ss.questions(sampled)
    assert sampled.sample == ("В одной из отдалённых улиц Москвы...", "Из числа всей её челяди...")
    assert "opening" in ss.state(sampled)


def test_the_questions_are_the_shapes_the_api_takes() -> None:
    asked = ss.questions(ss.from_row(ROWS[1], SAMPLES["mumu"]))
    assert {q["type"] for q in asked.values()} <= {"noul", "choice", "score"}
    for question in asked.values():
        assert question["instructions"]
        if question["type"] == "choice":
            assert isinstance(question["criteria"], dict) and len(question["criteria"]) >= 2
    assert "Russian" in asked["language"]["instructions"]
    json.dumps(asked)


def test_an_answer_is_read_and_the_licence_is_read_in_code() -> None:
    candidate = ss.from_row(ROWS[1], SAMPLES["mumu"])
    got = ss.read(candidate, answer(0.97, "original", "history", prose=0.9))
    assert got.language == 0.97 and got.origin == "original" and got.subject == "history"
    assert got.prose == 0.9 and got.licence is Standing.free
    assert got.passes


def test_what_fails_the_triage() -> None:
    kept = ss.from_row(ROWS[1], SAMPLES["mumu"])
    assert not ss.read(kept, answer(0.2, "original", "history", prose=0.9)).passes
    assert not ss.read(kept, answer(0.9, "original", "history", prose=0.1)).passes
    # No licence line is not a free one: it goes to a person, whatever the model says.
    unlicensed = ss.read(ss.from_row(ROWS[2]), answer(0.99, "original", "language"))
    assert unlicensed.licence is Standing.unknown and not unlicensed.passes
    # NoDerivatives cannot be read beside anything; NonCommercial can, in a free reader.
    nd = ss.from_row({**ROWS[1], "licence": "CC BY-ND 4.0"})
    nc = ss.from_row({**ROWS[1], "licence": "CC BY-NC 4.0"})
    assert not ss.read(nd, answer(0.9, "original", "none")).passes
    assert ss.read(nc, answer(0.9, "original", "none")).passes


def test_a_missing_answer_is_nothing_rather_than_a_verdict() -> None:
    got = ss.read(ss.from_row(ROWS[1]), {"language": {"type": "noul"}})
    assert got.language is None and got.origin == "" and got.prose is None
    assert not got.passes


@pytest.mark.parametrize(
    ("note", "translated"),
    [
        ("The English original.", True),
        ("The Italian is a translation of this, not the other way round.", True),
        ("The English the Russian was translated from.", True),
        ("Not a translation but the text it was translated from.", True),
        ("Made from the Judeo-Arabic original rather than from the Hebrew beside it.", True),
        ("Garnett's complete translation.", False),
        ("A translation made for Sefaria, numbered to the Hebrew it was made from.", False),
        ("OVD-Info's own English translation of this Russian text.", False),
    ],
)
def test_the_owner_s_note_says_which_came_first(note: str, translated: bool) -> None:
    assert ss.said_translation({"translations": [{"note": note}]}) is translated


def test_a_row_with_no_english_carries_no_label() -> None:
    assert ss.said_translation({"translations": []}) is None


def test_agreement_skips_what_nobody_labelled() -> None:
    got = ss.agreement([(True, True), (False, True), (None, False)])
    assert (got.right, got.n) == (1, 2) and got.rate == 0.5
    assert ss.agreement([]).rate is None


def test_precision_is_not_a_number_without_a_rejected_row() -> None:
    """Every row on the shelf was accepted, so the one thing a set of accepts cannot say
    is how many rejects the screen would have let through."""
    only_accepts = ss.confusion([(True, True), (True, False), (True, True)])
    assert only_accepts.recall == pytest.approx(2 / 3)
    assert only_accepts.precision is None
    mixed = ss.confusion([(True, True), (False, True), (False, False)])
    assert mixed.precision == 0.5 and mixed.recall == 1.0


@pytest.fixture(scope="module")
def sweep():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "screen_shelf", Path(__file__).parent.parent / "scripts" / "screen_shelf.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_sweep_scores_each_question_on_its_own_labels(sweep, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    answers = tmp_path / "answers.jsonl"
    lines = [
        {"id": "sw-1", "tokens": 400, "answers": answer(0.97, "translation", "none")},
        {"id": "mumu", "tokens": 500, "answers": answer(0.99, "translation", "history", prose=0.9)},
        {"id": "talk", "tokens": 300, "answers": answer(0.9, "original", "travel")},
    ]
    answers.write_text("\n".join(json.dumps(one) for one in lines) + "\n{broken", encoding="utf-8")
    got, tokens = sweep.kept(answers)
    assert set(got) == {"sw-1", "mumu", "talk"} and tokens == 1200

    report = sweep.score(ROWS, SAMPLES, got)["all"]
    assert report["rows"] == 3
    assert report["language"] == {"right": 3, "n": 3}
    assert report["prose"] == {"right": 1, "n": 1}
    # sw-1 is a translation and was called one; Mumu has an English made from it and was
    # called a translation; the talk has no English and no label.
    assert report["origin"] == {"right": 1, "n": 2}
    assert report["subject"] == {"right": 1, "n": 2}
    # The talk has no licence line, so it is the one accepted row the screen holds back.
    assert report["accept_recall"] == pytest.approx(2 / 3)
    assert report["accept_precision"] is None
    assert report["licence_unknown"] == 1
