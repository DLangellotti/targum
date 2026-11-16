"""French's subjunctive practice (targum-internal#644; design.md §12, "The French
subjunctive is practised after que", 2026-11-16): subjunctive or present for a verb
after the conjunction *que*, each as the card names it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import test_serve
from test_meetings import text
from test_reading_line import ms
from test_serve import Postbox, call, sign_in

from targum import practices, stages

served = test_serve.served
postbox = test_serve.postbox


def que(surface: str = "que", pos: str = "SCONJ") -> dict[str, Any]:
    return {"surface": surface, "lemma": "que", "pos": pos, "feats": f"UPOS={pos}"}


def verb(surface: str, lemma: str, mood: str, person: str = "3", number: str = "Sing") -> dict:
    return {
        "surface": surface,
        "lemma": lemma,
        "pos": "VERB",
        "feats": f"UPOS=VERB|Number={number}|Tense=Pres|Person={person}|VerbForm=Fin|Mood={mood}",
    }


def other(surface: str, pos: str = "PRON") -> dict[str, Any]:
    return {"surface": surface, "lemma": surface.lower(), "pos": pos, "feats": f"UPOS={pos}"}


def placed(line: str, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, at = [], 0
    for one in words:
        start = line.index(one["surface"], at)
        out.append({"start": start, "end": start + len(one["surface"]), **one})
        at = start + len(one["surface"])
    return out


def asked(line: str, words: list[dict[str, Any]]) -> list[tuple[str, str, bool, str]]:
    found = practices.mood_candidates(line, placed(line, words), "s")
    return [(c.answer, c.contrast, c.hard, line[c.start : c.end]) for c in found]


def test_the_subjunctive_spot_is_registered() -> None:
    assert stages._practices("fr")["subjunctive"] is True
    assert practices.KEYS["subjunctive"] == "mood"


def test_a_verb_after_the_conjunction_que_is_asked_its_mood() -> None:
    line = "Il faut que tu viennes."
    words = [other("Il"), verb("faut", "falloir", "Ind"), que(), other("tu"),
             verb("viennes", "venir", "Sub", "2")]  # fmt: skip
    assert asked(line, words) == [("Sub", "Ind", False, "viennes")]
    line = "Je pense qu'il vient."
    words = [other("Je"), verb("pense", "penser", "Ind", "1"), que("qu'"), other("il"),
             verb("vient", "venir", "Ind")]  # fmt: skip
    assert asked(line, words) == [("Ind", "Sub", False, "vient")]


def test_a_form_both_moods_spell_alike_is_the_hard_kind() -> None:
    line = "Je veux qu'il parle."
    words = [other("Je"), verb("veux", "vouloir", "Ind", "1"), que("qu'"), other("il"),
             verb("parle", "parler", "Sub")]  # fmt: skip
    assert asked(line, words) == [("Sub", "Ind", True, "parle")]
    # *Nous parlions* is spelled otherwise in the present, and *aller* is irregular.
    line = "Il faut que nous parlions."
    words = [other("Il"), verb("faut", "falloir", "Ind"), que(), other("nous"),
             verb("parlions", "parler", "Sub", "1", "Plur")]  # fmt: skip
    assert asked(line, words)[0][2] is False
    line = "Il faut qu'il aille."
    words = [other("Il"), verb("faut", "falloir", "Ind"), que("qu'"), other("il"),
             verb("aille", "aller", "Sub")]  # fmt: skip
    assert asked(line, words)[0][2] is False


def test_what_the_card_names_otherwise_is_not_asked() -> None:
    # The relative que: le livre que je lis.
    line = "Le livre que je lis."
    words = [other("Le", "DET"), other("livre", "NOUN"), que(pos="PRON"), other("je"),
             verb("lis", "lire", "Ind", "1")]  # fmt: skip
    assert asked(line, words) == []
    # No que at all; the conditional; an auxiliary; a verb before the que.
    line = "Il vient."
    assert asked(line, [other("Il"), verb("vient", "venir", "Ind")]) == []
    line = "Je crois qu'il viendrait."
    cnd = {**verb("viendrait", "venir", "Cnd"), "feats": "UPOS=VERB|Tense=Pres|Mood=Cnd"}
    assert asked(line, [other("Je"), verb("crois", "croire", "Ind", "1"), que("qu'"),
                        other("il"), cnd]) == []  # fmt: skip
    line = "Je doute qu'il ait fini."
    ait = {**verb("ait", "avoir", "Sub"), "pos": "AUX"}
    part = {"surface": "fini", "lemma": "finir", "pos": "VERB",
            "feats": "UPOS=VERB|Tense=Past|VerbForm=Part"}  # fmt: skip
    assert asked(line, [other("Je"), verb("doute", "douter", "Ind", "1"), que("qu'"),
                        other("il"), ait, part]) == []  # fmt: skip


@pytest.mark.parametrize("ui", ["en", "ru"])
def test_the_mood_is_said_in_the_cards_words(ui: str) -> None:
    from targum import strings

    assert practices.said("mood", "Sub", ui) == strings.text("reader.grammar.subjunctive", ui)
    assert practices.said("mood", "Ind", ui) == strings.text("reader.grammar.present", ui)
    assert practices.rule("mood", "Sub", ui) != practices.rule("mood", "Ind", ui)


def _moods(name: str) -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        (
            f"Il faut que tu viennes, {name}.",
            [que(), verb("viennes", "venir", "Sub", "2")],
        ),
        (
            f"Je veux qu'il parle, {name}.",
            [que("qu'"), verb("parle", "parler", "Sub")],
        ),
        (
            f"Je pense qu'il vient, {name}.",
            [que("qu'"), verb("vient", "venir", "Ind")],
        ),
        (
            f"Je sais qu'il chante, {name}.",
            [que("qu'"), verb("chante", "chanter", "Ind")],
        ),
    ]


def test_the_subjunctive_is_offered_on_the_grammar_tab(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    for name in ("un", "deux"):
        text(out / "shared" / name, {1: _moods(name)}, language="fr", content_hash=name)
    cookie = sign_in(port, postbox)
    sections = [
        {"hash": name, "section": "1", "at": ms(2026, 11), "seen": ms(2026, 11)}
        for name in ("un", "deux")
    ]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"sections": sections}, cookie=cookie
    )
    assert status == 200, answer
    status, said, _ = call(
        port, "GET", f"/account/practice?language=fr&spot=mood&k={token}", cookie=cookie
    )
    assert status == 200, said
    spot = {one["key"]: one for one in said["spots"]}["mood"]
    assert spot["encounters"] == 8 and spot["ready"]
    items = said["round"]["items"]
    assert said["round"]["spot"] == "mood" and len(items) == practices.ROUND + 1
    for item in items:
        assert item["ask"] == "Subjunctive, or present?"
        assert sorted(item["options"]) == ["present", "subjunctive"]
        assert item["options"][item["answer"]] == item["said"]
        assert item["contrast"] and item["contrast"]["said"] != item["said"]
