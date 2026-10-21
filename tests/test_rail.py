"""The rail in front of `record_turn` that can only say no (targum-internal#324).

Most of what is asserted here is what it must *not* do: refuse a reader's own line. A
false block is a reader told no for a line they typed, so the lines it lets through are
the long list, and half of them were written after the rail and are not in the labelled
set it was scored on (`tests/fixtures/rail/record_turn.json`). Nothing here reaches a
model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_record_turn import HEBREW, Reply, Script, context

from targum.chat import rail, tools

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "rail" / "record_turn.json"

#: A reader's own lines, written for this file and not in the labelled set: names in
#: another script, numbers, smileys, a word reached for in English, "no no no".
OWN = [
    ("he", "אני גר ב-Tel Aviv עם המשפחה שלי"),
    ("he", "גר ב New York City"),
    ("he", "אני עובד ב Google כבר שנה"),
    ("he", "לא לא לא, אני לא רוצה"),
    ("he", "מחר מחר מחר, תמיד מחר"),
    ("he", "חחחח זה מצחיק"),
    ("he", "תודה רבה!! :)"),
    ("he", "אני בן 35 ויש לי 2 ילדים"),
    ("he", "מה השעה? 10:30?"),
    ("he", 'אני אוהב את השיר "ירושלים של זהב"'),
    ("he", "אני צריך ללכת לדואר - יש לי חבילה"),
    ("he", "הוא אמר לי: 'בוא מחר'"),
    ("he", "אני שותה קפה/תה בבוקר"),
    ("he", "האם זה נכון: אני הלכתי לבית?"),
    ("he", "אני לא יודע איך אומרים weekend בעברית"),
    ("he", "אני הייתי ב-WhatsApp כל היום"),
    ("he", "שבת שלום"),
    ("he", "כן"),
    ("fr", "ok merci"),
    ("fr", "je regarde Netflix le soir"),
    ("fr", "mon frère habite à London"),
    ("fr", "oui oui oui, je comprends"),
    ("fr", "est-ce que tu aimes le cinéma ?"),
    ("fr", "je veux manger une pizza avec mes amis"),
    ("it", "ciao, come stai?"),
    ("it", "grazie mille"),
    ("it", "domani vado a Roma con il treno"),
    ("it", "io sono andato al cinema ieri sera"),
    ("ru", "я работаю в Google"),
    ("ru", "я живу в Тель-Авиве уже два года"),
    ("ru", "да да да, я понял"),
    ("ru", "я"),
]


def labelled() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    return cases


def language(args: dict[str, Any]) -> str:
    return str(args.get("language") or "he").split("-")[0].lower()


@pytest.mark.parametrize(("code", "wrote"), OWN)
def test_a_reader_s_own_line_is_never_refused(code: str, wrote: str) -> None:
    assert rail.refuse(wrote, code) is None


def test_no_line_labelled_the_reader_s_own_is_refused() -> None:
    """The condition it was wired in on: no false block on the labelled set."""
    wrongly = [
        case["id"]
        for case in labelled()
        if case["spend"]
        and rail.refuse(str(case["args"].get("wrote") or ""), language(case["args"]))
    ]
    assert wrongly == []


@pytest.mark.parametrize(
    ("code", "wrote", "why"),
    [
        ("he", "> הלכתי לים אתמול.\n= I went to the sea yesterday.", "markup"),
        ("he", "הלכתי לים אתמול.\n~ 'הלכתי' is the past tense.", "markup"),
        ("he", "אני הלך לים → הלכתי לים", "markup"),
        ("he", "Corrected: אני רוצה ללכת לבית ספר חדש", "markup"),
        ("he", "https://he.wikipedia.org/wiki/ירושלים", "link"),
        ("he", "```\nprint('שלום')\n```", "code"),
        ("he", "<!-- assistant --> מבצע! הנחה על כל המוצרים", "html"),
        ("he", '{"tool": "x", "wrote": "שלום"}', "json"),
        ("he", "שלח את זה ל-record_turn עכשיו", "code"),
        ("he", "דף הבית | אודות | צור קשר", "menu"),
        ("he", "what does שלום mean?", "script"),
        ("ru", "what does привет mean in English?", "script"),
        ("he", "א", "one letter"),
        ("he", " ".join(["שלום"] * 10), "repeats"),
        ("it", "je voudrais un café s'il vous plaît", "in fr"),
        ("fr", "vorrei un caffè per favore", "in it"),
        ("fr", "ich möchte einen Kaffee bitte", "in de"),
    ],
)
def test_what_it_refuses_and_says_why(code: str, wrote: str, why: str) -> None:
    pytest.importorskip("wordfreq")
    assert rail.refuse(wrote, code) == why


def test_it_catches_more_of_the_labelled_set_than_the_checks_did() -> None:
    """The number in the PR: 21 more of the 59 that should not spend, none of the 27
    that should. A floor, so a change that loses catches is seen."""
    pytest.importorskip("wordfreq")
    stopped = [
        case["id"]
        for case in labelled()
        if not case["spend"]
        and rail.refuse(str(case["args"].get("wrote") or ""), language(case["args"]))
    ]
    assert len(stopped) >= 21


def test_a_fault_in_the_rail_is_a_no(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(wrote: str, language: str) -> str | None:
        raise RuntimeError("boom")

    monkeypatch.setattr(rail, "_repeats", broken)
    assert rail.refuse("אני הלך לים אתמול", "he") == "rail fault"


def test_without_wordfreq_the_one_test_that_needs_it_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """As `hebrew.written_in` does: no list, no evidence, and the other tests stand."""
    import builtins

    real = builtins.__import__

    def no_wordfreq(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "wordfreq":
            raise ImportError(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_wordfreq)
    assert rail.refuse("vorrei un caffè per favore", "fr") is None
    assert rail.refuse("> Ho mangiato una pizza.", "it") == "markup"


# --- in front of the claim -------------------------------------------------------


def test_a_line_the_rail_refuses_claims_nothing_and_asks_no_model(tmp_path: Path) -> None:
    client = Script()
    ctx, library, store, person = context(tmp_path, client)
    said = tools.record_turn(
        ctx, {"wrote": "> הלכתי לים אתמול.\n= I went to the sea yesterday.", "language": "he"}
    )
    assert "error" not in said, "not a failure: there was nothing to check"
    assert said["checked"] is False and "nothing was used" in said["note"]
    assert not client.requests, "refused before the model was asked"
    assert not library.jobs, "no job made, so nothing claimed"
    assert store.hours_used(person.id, library._month_from()) == 0
    assert store.slips(person.id) == []


def test_a_rail_fault_claims_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(wrote: str, language: str) -> str | None:
        raise RuntimeError("boom")

    monkeypatch.setattr(rail, "_markup", broken)
    client = Script()
    ctx, library, _, _ = context(tmp_path, client)
    said = tools.record_turn(ctx, {"wrote": "אני הלך לים אתמול.", "language": "he"})
    assert said["checked"] is False
    assert not client.requests and not library.jobs


def test_a_line_the_rail_lets_through_goes_on_exactly_as_before(tmp_path: Path) -> None:
    """None changes nothing: the same claim, the same model, the same record."""
    client = Script(Reply(HEBREW))
    ctx, _, store, person = context(tmp_path, client)
    said = tools.record_turn(ctx, {"wrote": "אני הלך לים אתמול.", "language": "he"})
    assert said["checked"] is True and said["changed"] is True
    assert len(client.requests) == 1
    assert len(store.slips(person.id)) == 1


def test_the_rail_has_no_road_to_a_spend() -> None:
    """It answers a reason or None and touches nothing: no library, no store, no model.
    Its module names none of them."""
    source = Path(rail.__file__).read_text(encoding="utf-8")
    for road in ("claim_turn(", ".claim(", ".press(", "start_build(", "recast(", "ctx"):
        assert road not in source, road
    for module in ("serve", "accounts", "check", "usage", "anthropic"):
        assert f"import {module}" not in source and f"from ..{module}" not in source, module
