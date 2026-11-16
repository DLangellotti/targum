"""French's passé composé against imparfait practice (targum-internal#644; design.md §12,
"French past tenses are practised as the card names them", 2026-11-16): which past the
card names on a word, asked only where the card names it."""

from __future__ import annotations

import json
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

APART = "model-lemma/claude-haiku-4-5/3+wordfreq+register/2"


def word(surface: str, lemma: str, feats: str, pos: str = "VERB") -> dict[str, Any]:
    return {"surface": surface, "lemma": lemma, "pos": pos, "feats": feats}


def aux(surface: str, lemma: str = "avoir", tense: str = "Pres") -> dict[str, Any]:
    return word(surface, lemma, f"UPOS=AUX|Tense={tense}|VerbForm=Fin|Mood=Ind", "AUX")


def part(surface: str, lemma: str) -> dict[str, Any]:
    return word(surface, lemma, "UPOS=VERB|Tense=Past|VerbForm=Part")


def imp(surface: str, lemma: str) -> dict[str, Any]:
    return word(surface, lemma, "UPOS=VERB|Tense=Imp|VerbForm=Fin|Mood=Ind")


def placed(line: str, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, at = [], 0
    for one in words:
        start = line.index(one["surface"], at)
        out.append({"start": start, "end": start + len(one["surface"]), **one})
        at = start + len(one["surface"])
    return out


def asked(line: str, words: list[dict[str, Any]]) -> list[tuple[str, str, bool, str]]:
    found = practices.past_candidates(line, placed(line, words), "s")
    return [(c.answer, c.contrast, c.hard, line[c.start : c.end]) for c in found]


def test_the_past_spot_is_registered() -> None:
    assert stages._practices("fr")["passé composé against imparfait"] is True
    assert practices.KEYS["passé composé against imparfait"] == "past"


def test_a_participle_with_avoir_or_etre_in_the_present_is_the_passe_compose() -> None:
    line = "Il a mangé une pomme."
    assert asked(line, [aux("a"), part("mangé", "manger")]) == [("PC", "Imp", False, "mangé")]
    line = "Elle est partie hier."
    assert asked(line, [aux("est", "être"), part("partie", "partir")]) == [
        ("PC", "Imp", False, "partie")
    ]
    # A negation between them is in reach; a verb of knowing is the hard kind.
    line = "Je n'ai pas su quoi dire."
    assert asked(line, [aux("ai"), part("su", "savoir")]) == [("PC", "Imp", True, "su")]
    # Reflexive with être is the passé composé too.
    line = "Elle s'est levée tôt."
    reflexive = word("s'", "se", "UPOS=PRON|Role=Refl", "PRON")
    assert asked(line, [reflexive, aux("est", "être"), part("levée", "lever")]) == [
        ("PC", "Imp", False, "levée")
    ]


def test_what_the_card_names_otherwise_is_not_asked_as_the_passe_compose() -> None:
    # The passive: être with a verb that does not take it.
    line = "La lettre est écrite."
    assert asked(line, [aux("est", "être"), part("écrite", "écrire")]) == []
    # The pluperfect: the auxiliary in the imparfait, which is not asked as an imparfait.
    line = "Il avait mangé."
    assert asked(line, [aux("avait", tense="Imp"), part("mangé", "manger")]) == []
    # A stop between them, or no auxiliary at all.
    line = "Il a, mangé."
    assert asked(line, [aux("a"), part("mangé", "manger")]) == []
    assert asked("Mangé, il part.", [part("Mangé", "manger")]) == []
    # The past subjunctive and the conditional past are their own tenses.
    sub = word("ait", "avoir", "UPOS=AUX|Tense=Pres|VerbForm=Fin|Mood=Sub", "AUX")
    assert asked("Qu'il ait mangé.", [sub, part("mangé", "manger")]) == []


def test_a_finite_imparfait_is_asked_and_a_state_verb_is_the_hard_kind() -> None:
    line = "Il pleuvait et elle était triste."
    assert asked(line, [imp("pleuvait", "pleuvoir"), imp("était", "être")]) == [
        ("Imp", "PC", False, "pleuvait"),
        ("Imp", "PC", True, "était"),
    ]


def test_a_text_whose_tenses_are_not_apart_asks_nothing(tmp_path: Path) -> None:
    """Prompt 2 read the imparfait as a plain past (`model_lemma.tenses_apart`): its
    'Imp' is not there to be asked, so the spot asks nothing of such a text."""
    line = "Il pleuvait quand il a mangé."
    words = [imp("pleuvait", "pleuvoir"), aux("a"), part("mangé", "manger")]
    folder = text(tmp_path / "t", {1: [(line, words)]}, language="fr")
    annotation = folder / "annotation.json"
    loaded = json.loads(annotation.read_text(encoding="utf-8"))
    for annotator, expected in (
        ("model-lemma/claude-haiku-4-5/2+wordfreq", []),
        ("model-lemma/claude-haiku-4-5/3/with-2+wordfreq", []),
        (APART, ["Imp", "PC"]),
    ):
        annotation.write_text(json.dumps({**loaded, "annotator": annotator}), encoding="utf-8")
        found = practices.count_text(folder)
        assert found is not None
        assert sorted(c.answer for c in found.by_section[1] if c.spot == "past") == expected


@pytest.mark.parametrize("ui", ["en", "ru"])
def test_the_past_is_said_in_the_cards_words(ui: str) -> None:
    from targum import strings

    assert practices.said("past", "PC", ui) == strings.text("reader.grammar.passe-compose", ui)
    assert practices.said("past", "Imp", ui) == strings.text("reader.grammar.imperfect", ui)
    assert practices.rule("past", "PC", ui) != practices.rule("past", "Imp", ui)
    assert "{" not in practices.rule("past", "PC", ui)


def _pasts(name: str) -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        (f"Il a mangé chez {name}.", [aux("a"), part("mangé", "manger")]),
        (f"Elle est partie chez {name}.", [aux("est", "être"), part("partie", "partir")]),
        (f"Il pleuvait chez {name}.", [imp("pleuvait", "pleuvoir")]),
        (f"Elle était chez {name}.", [imp("était", "être")]),
    ]


def test_the_past_is_offered_on_the_grammar_tab(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    for name in ("un", "deux"):
        folder = text(out / "shared" / name, {1: _pasts(name)}, language="fr", content_hash=name)
        annotation = folder / "annotation.json"
        loaded = json.loads(annotation.read_text(encoding="utf-8"))
        annotation.write_text(json.dumps({**loaded, "annotator": APART}), encoding="utf-8")
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
        port, "GET", f"/account/practice?language=fr&spot=past&k={token}", cookie=cookie
    )
    assert status == 200, said
    spot = {one["key"]: one for one in said["spots"]}["past"]
    assert spot["encounters"] == 8 and spot["ready"]
    items = said["round"]["items"]
    assert said["round"]["spot"] == "past" and len(items) == practices.ROUND + 1
    for item in items:
        assert item["ask"] == "Which past is it?"
        assert sorted(item["options"]) == ["imperfect", "passé composé"]
        assert item["options"][item["answer"]] == item["said"]
        assert item["line"][item["start"] : item["end"]] == item["word"]
        assert item["contrast"] and item["contrast"]["said"] != item["said"]
