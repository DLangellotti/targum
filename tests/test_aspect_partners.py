"""targum's own Russian aspect partner list, and the line a card draws from it (2026-10-30)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from targum.annotate import aspect_partners, openrussian

ACUTE = "́"
VOWELS = set("аеёиоуыэюя")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_aspect_partners.py"


def rows() -> list[dict[str, object]]:
    loaded = json.loads(aspect_partners._TABLE.read_text(encoding="utf-8"))
    entries: list[dict[str, object]] = loaded["entries"]
    return entries


def test_the_list_covers_three_hundred_verbs_once_each() -> None:
    verbs = [aspect_partners.fold(str(row["verb"])) for row in rows()]
    assert len(verbs) == 300 and len(set(verbs)) == 300
    assert all(int(str(row["tokens"])) > 0 for row in rows())


def test_every_word_is_stressed_as_print_stresses_it() -> None:
    """One acute on a word of more than one vowel, none on ё or a word of one; never the
    tables' apostrophe."""
    for row in rows():
        named = [str(word) for word in row["partners"]]  # type: ignore[attr-defined]
        named += [str(verb) for verb, _ in row.get("related", [])]  # type: ignore[attr-defined]
        for word in named:
            bare = word.replace(ACUTE, "")
            vowels = sum(char in VOWELS for char in bare)
            assert "'" not in word, word
            if vowels <= 1 or "ё" in bare:
                assert ACUTE not in word, word
            else:
                assert word.count(ACUTE) == 1, word
                assert word[word.index(ACUTE) - 1] in VOWELS, word


def test_a_related_verb_is_never_a_partner_and_says_what_it_adds() -> None:
    for row in rows():
        partners = {aspect_partners.fold(str(p)) for p in row["partners"]}  # type: ignore[attr-defined]
        verb = aspect_partners.fold(str(row["verb"]))
        assert verb not in partners
        for related, kind in row.get("related", []):  # type: ignore[attr-defined]
            assert kind in aspect_partners.KINDS, kind
            assert aspect_partners.fold(related) not in partners | {verb}


def test_the_common_mistakes_are_fixed() -> None:
    """The leads OpenRussian got wrong on the commonest verbs (ling-ru, 2026-10-30)."""
    partners = aspect_partners.partners_of
    assert partners("видеть") == ("уви́деть",)
    assert partners("знать") == (), "узнать is find out, partner of узнавать"
    assert partners("узнать") == ("узнава́ть",)
    assert partners("ходить") == ()
    assert partners("помнить") == ()
    assert partners("Стоять") == ()
    assert partners("взять") == ("брать",)
    assert partners("идёт") is None, "a word off the list is OpenRussian's to answer"
    assert aspect_partners.related_of("стоять") == (("постоя́ть", "while"),)
    assert aspect_partners.related_line("плакать") == "запла́кать:start · попла́кать:while"
    assert aspect_partners.related_line("постоять") == "стоя́ть:from"
    assert aspect_partners.related_line("быть") == ""


def test_the_list_wins_and_openrussian_answers_the_rest() -> None:
    lexicon = openrussian.Lexicon()
    lexicon.entries = {
        "стоять": [openrussian.Entry("verb", "стоя'ть", "imperfective", ("постоять",))],
        "трогать": [openrussian.Entry("verb", "тро'гать", "imperfective", ("тронуть",))],
    }
    line = aspect_partners.partner_line
    assert line("стоять", lexicon, 2) == ([], False), "a none on the list is still a none"
    assert line("трогать", lexicon, 2) == (["тронуть"], True)
    assert line("трогать", None, 2) == ([], False)
    assert line("видеть", None, 2) == (["уви́деть"], False), "the list needs no tables"


def test_the_precision_check_scores_a_line_against_the_list() -> None:
    spec = importlib.util.spec_from_file_location("eval_aspect_partners", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_aspect_partners"] = module
    spec.loader.exec_module(module)
    verbs = [("знать", 6, set()), ("видеть", 4, {"увидеть"})]
    wrong = module.score(verbs, {"знать": ["узна́ть"], "видеть": ["зави́деть", "уви́деть"]})
    assert wrong["partner_precision"] == (0.2, 10)
    assert wrong["partner_line_right"] == (0.0, 10)
    right = module.score(verbs, {"видеть": ["уви́деть"]})
    assert right == {"partner_precision": (1.0, 4), "partner_line_right": (1.0, 10)}
    top = module.gold(100)
    drawn = {lemma: aspect_partners.partner_line(lemma, None, 2)[0] for lemma, _, _ in top}
    assert module.score(top, drawn)["partner_line_right"][0] == 1.0
