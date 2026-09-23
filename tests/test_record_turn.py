"""The one tool that spends: checking a line the reader wrote somewhere else.

`record_turn` is what makes the connector fill the record rather than only read it
(targum-internal#80), and it is the first tool in the registry with `spends` set. So
most of what is asserted here is a refusal — the wrong language, the wrong scope, a
paragraph, no hours left — and the one thing that has to be exactly right: a line that
was already right writes nothing.

Nothing here reaches a model. The client is a script, which is the same seam
`test_chat_session.py` uses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from targum import level
from targum.accounts import Person, Store
from targum.chat import check as check_module
from targum.chat import tools
from targum.serve import Library


class Reply:
    """What the SDK hands back from `messages.create`."""

    def __init__(self, text: str, tokens: int = 40) -> None:
        self.content = [type("Block", (), {"type": "text", "text": text})()]
        self.usage = type("Usage", (), {"input_tokens": tokens, "output_tokens": tokens})()


class Script:
    """A client that answers each call with the next reply and keeps what it was sent."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **request: Any) -> Any:
        self.requests.append(request)
        if not self.replies:
            raise AssertionError("the script ran out, which a test should not let happen")
        got = self.replies.pop(0)
        if isinstance(got, Exception):
            raise got
        return got


HEBREW = "> אני הלכתי לים אתמול.\n= I went to the sea yesterday.\n~ הלכתי is the form."
SAME = "> אני הולך לים.\n= I am going to the sea."


def world(tmp_path: Path) -> tuple[Library, Store, Person]:
    store = Store(tmp_path / "words.db")
    out = tmp_path / "out"
    out.mkdir()
    person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
    return Library(out, store=store), store, person


def context(
    tmp_path: Path, client: Any = None, learning: set[str] | None = None
) -> tuple[tools.Ctx, Library, Store, Person]:
    library, store, person = world(tmp_path)
    ctx = tools.Ctx(
        person=person,
        home=library.home(person),
        library=library,
        store=store,
        chat_id="",
        level=level.EMPTY,
        learning=learning if learning is not None else {"he"},
        reads={"en"},
        said_reads={"en"},
        ask=(lambda: client) if client is not None else None,
    )
    return ctx, library, store, person


# --- what it does when it works --------------------------------------------------


def test_a_changed_line_is_recast_and_kept(tmp_path: Path) -> None:
    client = Script(Reply(HEBREW))
    ctx, _, store, person = context(tmp_path, client)
    said = tools.record_turn(ctx, {"wrote": "אני הלך לים אתמול.", "language": "he"})
    assert said["recast"] == "אני הלכתי לים אתמול."
    assert said["meaning"] == "I went to the sea yesterday."
    assert said["why"] == "הלכתי is the form."
    assert said["changed"] is True
    kept = store.slips(person.id)
    assert len(kept) == 1
    assert kept[0]["wrote"] == "אני הלך לים אתמול."
    assert kept[0]["source"] == "connector", "one judge, and still worth being able to tell"


def test_a_line_that_was_right_keeps_nothing(tmp_path: Path) -> None:
    """What makes `slip` a record of mistakes rather than a log of turns."""
    client = Script(Reply(SAME))
    ctx, _, store, person = context(tmp_path, client)
    said = tools.record_turn(ctx, {"wrote": "אני הולך לים.", "language": "he"})
    assert said["changed"] is False
    assert "already right" in said["note"]
    assert store.slips(person.id) == []


def test_the_reader_s_own_line_is_what_is_sent_and_nothing_else(tmp_path: Path) -> None:
    """Never the host's correction: targum judges, so the record has one judge."""
    client = Script(Reply(HEBREW))
    ctx, _, _, _ = context(tmp_path, client)
    tools.record_turn(ctx, {"wrote": "אני הלך לים אתמול.", "language": "he"})
    sent = client.requests[0]
    assert sent["messages"] == [{"role": "user", "content": "אני הלך לים אתמול."}]
    assert "This conversation is in Hebrew" in sent["system"]
    assert "checking one line" in sent["system"]
    assert "must not start one" in sent["system"], "it is not a conversation"


def test_it_is_metered_on_the_reader_s_line_alone(tmp_path: Path) -> None:
    """An in-app turn adds a reply's worth because targum writes the reply. Here the
    host wrote it, and charging for it would be charging for something nobody bought."""
    from targum.chat import hebrew

    client = Script(Reply(HEBREW))
    ctx, library, store, person = context(tmp_path, client)
    wrote = "אחת שתיים שלוש ארבע חמש שש שבע שמונה תשע עשר"
    tools.record_turn(ctx, {"wrote": wrote, "language": "he"})
    job = next(one for one in library.jobs.values() if one.kind == "chat")
    assert job.seconds == pytest.approx(hebrew.seconds_for(10))
    assert job.seconds < hebrew.seconds_for(10 + hebrew.ASSUMED_REPLY_WORDS)
    used = store.hours_used(person.id, library._month_from())
    assert used > 0, "and it does come out of the hours"


def test_it_settles_to_what_the_model_actually_charged(tmp_path: Path) -> None:
    client = Script(Reply(HEBREW, tokens=1000))
    ctx, library, _, _ = context(tmp_path, client)
    tools.record_turn(ctx, {"wrote": "אני הלך לים.", "language": "he"})
    job = next(one for one in library.jobs.values() if one.kind == "chat")
    assert 0 < job.spent < check_module.MOST_PER_LINE, "reserved high, settled to the receipt"


# --- the refusals ----------------------------------------------------------------


def test_a_language_with_no_contract_is_refused_by_name(tmp_path: Path) -> None:
    """#284: Aramaic holds no conversation, so there is nothing to check it against."""
    ctx, _, _, _ = context(tmp_path, Script(), learning={"he", "arc"})
    said = tools.record_turn(ctx, {"wrote": "מילתא", "language": "arc"})
    assert "coming" in said["error"] and "Aramaic" in said["error"]


def test_a_language_the_reader_is_not_learning_is_refused(tmp_path: Path) -> None:
    ctx, _, _, _ = context(tmp_path, Script(), learning={"he"})
    said = tools.record_turn(ctx, {"wrote": "je suis allé", "language": "fr"})
    assert "not learning" in said["error"]


#: A recast in each language's own script, because `hebrew.pairs` tells a line from its
#: translation by the letters where the letters settle it — Yiddish is in Hebrew ones.
RECASTS = {
    "he": HEBREW,
    "it": "> Sono andato al mare.\n= I went to the sea.",
    "fr": "> Je suis allé à la mer.\n= I went to the sea.",
    "ru": "> Я ходил на море.\n= I went to the sea.",
    "yi": "> איך בין געגאַנגען צום ים.\n= I went to the sea.",
}


@pytest.mark.parametrize("code", ["he", "it", "fr", "ru"])
def test_every_language_that_talks_can_be_checked(tmp_path: Path, code: str) -> None:
    client = Script(Reply(RECASTS[code]))
    ctx, _, _, _ = context(tmp_path, client, learning={code})
    said = tools.record_turn(ctx, {"wrote": "something they wrote", "language": code})
    assert "error" not in said, said
    assert said["recast"]


@pytest.mark.parametrize("code", ["yi", "arc"])
def test_a_language_that_does_not_talk_is_refused_without_buying_a_turn(
    tmp_path: Path, code: str
) -> None:
    """Yiddish is held (#359, #360) and Aramaic is decided (#284). Either way there is
    no conversation to record, and the refusal comes before a token is bought."""
    client = Script()
    ctx, _, store, person = context(tmp_path, client, learning={code})
    said = tools.record_turn(ctx, {"wrote": "something they wrote", "language": code})
    assert "coming" in said["error"]
    assert not client.requests, "refused before the model was asked"
    assert store.slips(person.id) == []


def test_a_paragraph_is_refused_rather_than_recast_as_a_sentence(tmp_path: Path) -> None:
    ctx, _, _, _ = context(tmp_path, Script())
    said = tools.record_turn(ctx, {"wrote": "מילה " * 200, "language": "he"})
    assert "one line at a time" in said["error"]


def test_an_empty_line_is_refused(tmp_path: Path) -> None:
    ctx, _, _, _ = context(tmp_path, Script())
    assert "error" in tools.record_turn(ctx, {"wrote": "   ", "language": "he"})


def test_nobody_signed_in_checks_nothing(tmp_path: Path) -> None:
    library, store, _ = world(tmp_path)
    ctx = tools.Ctx(
        person=None,
        home=library.home(None),
        library=library,
        store=store,
        chat_id="",
        level=level.EMPTY,
        learning={"he"},
        ask=lambda: Script(),
    )
    assert "account" in tools.record_turn(ctx, {"wrote": "x", "language": "he"})["error"]


def test_a_box_with_no_model_says_so_rather_than_failing_inside(tmp_path: Path) -> None:
    ctx, _, _, _ = context(tmp_path, client=None)
    said = tools.record_turn(ctx, {"wrote": "אני הלך לים.", "language": "he"})
    assert "cannot check" in said["error"]


def test_a_model_that_breaks_hands_the_hours_back(tmp_path: Path) -> None:
    """Releasing is the difference between a failed check and a charged one."""
    ctx, library, store, person = context(tmp_path, Script(RuntimeError("no")))
    said = tools.record_turn(ctx, {"wrote": "אני הלך לים.", "language": "he"})
    assert "could not check" in said["error"]
    assert store.hours_used(person.id, library._month_from()) == 0
    assert store.slips(person.id) == []


def test_a_reply_that_is_not_a_recast_keeps_nothing(tmp_path: Path) -> None:
    ctx, _, store, person = context(tmp_path, Script(Reply("I think that looks fine!")))
    said = tools.record_turn(ctx, {"wrote": "אני הלך לים.", "language": "he"})
    assert "could not read that line back" in said["error"]
    assert store.slips(person.id) == []


def test_it_is_refused_when_the_hours_are_gone(tmp_path: Path) -> None:
    client = Script(Reply(HEBREW))
    ctx, library, _, _ = context(tmp_path, client)
    library.upload_seconds = 0.0
    said = tools.record_turn(ctx, {"wrote": "אני הלך לים.", "language": "he"})
    assert "error" in said
    assert not client.requests, "refused before a token was bought"


# --- the seam it sits in ---------------------------------------------------------


def test_it_is_the_only_tool_that_spends_and_it_wears_the_scope(tmp_path: Path) -> None:
    """design.md §12: one scope may say otherwise, and it is the only thing that may."""
    from targum import oauth

    spending = [one for one in tools.REGISTRY if one.spends]
    assert [one.name for one in spending] == ["record_turn"]
    assert spending[0].scope == oauth.SPENDING_SCOPE
    assert spending[0].needs_account is True


def test_it_is_not_offered_without_the_scope_that_consented(tmp_path: Path) -> None:
    from targum import connector

    for scopes in ("", "library", "library record"):
        assert "record_turn" not in {one.name for one in connector.exposed(scopes)}
    assert "record_turn" in {
        one.name
        for one in connector.exposed("library record check", person=object())  # type: ignore[arg-type]
    }


def test_the_stdio_connector_never_offers_it(tmp_path: Path) -> None:
    """No token means nobody consented to anything, whatever else stdio can reach."""
    from targum import connector

    assert "record_turn" not in {one.name for one in connector.exposed()}


def test_the_in_app_chat_is_never_offered_it(tmp_path: Path) -> None:
    """targum already recasts every line of its own conversation and writes the slip
    itself, so offering this there would record the same mistake twice and charge for
    it twice. `anthropic_tools` is the list the chat's model is given."""
    offered = {one["name"] for one in tools.anthropic_tools()}
    assert "record_turn" not in offered
    by_name = {one.name: one for one in tools.REGISTRY}
    assert not [name for name in offered if by_name[name].spends]


def test_the_chat_never_hands_a_tool_the_way_to_a_model(tmp_path: Path) -> None:
    """`Ctx.ask` is how the one spending tool reaches targum's own model, and a turn of
    conversation has a client already — a second would be a second connection pool."""
    from targum.chat import session as session_module

    library, store, _ = world(tmp_path)
    chats = session_module.Chats(library, store, client_factory=lambda: Script())
    ctx = chats.context(None, library.home(None), "", admin=False)
    assert ctx.ask is None
