"""The profile page's script, run rather than read.

The two things on this page that matter are a name that has to actually save and a
delete button that has no second chance. Same harness as `test_learn_js.py` — a stub
document under node, not a browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "you.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

SIGNED_IN = {
    "signedIn": True,
    "email": "yosef@example.com",
    "name": "Yosef Cohen",
    "picture": "",
    "initials": "YC",
    "counts": {"words": 512, "phrases": 24, "docs": 3, "days": 12},
    "learning": ["he"],
    "reads": ["en"],
}


def run(
    who: dict[str, Any] | None = None,
    do: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
    strings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "answers": {"/account/me": who if who is not None else SIGNED_IN, **(answers or {})},
        "do": do or [],
        "strings": strings,
    }
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_stranger_is_told_rather_than_shown_an_empty_form() -> None:
    page = run(who={"signedIn": False})
    assert page["stranger"] is False, "the one thing a signed-out visitor sees"
    assert all(page["panels"].values()), "and nothing else"
    assert page["name"] == "" and page["posted"] == []


def test_the_page_fills_itself_in_for_whoever_is_signed_in() -> None:
    page = run()
    assert page["stranger"] is True
    assert not any(page["panels"].values())
    assert page["name"] == "Yosef Cohen"
    assert page["email"] == "yosef@example.com"
    assert page["avatar"] == "YC"
    assert page["kept"] == "512 words and 24 phrases, across all your languages."


def test_typing_a_name_is_one_request_and_not_one_per_keystroke() -> None:
    """A field that posted per keystroke would post nine times for one name."""
    typed = [{"type": "name", "value": "Yosef Cohe" + "n" * n} for n in range(1, 10)]
    page = run(
        do=typed,
        answers={"/account/name": {**SIGNED_IN, "name": "Yosef Cohennnnnnnnn", "initials": "YC"}},
    )
    names = [post for post in page["posted"] if post["path"] == "/account/name"]
    assert len(names) == 1, names
    assert names[0]["body"]["name"] == "Yosef Cohennnnnnnnn", "the last thing typed, not the first"
    assert page["said"] == {"text": "Saved.", "hidden": False}


def test_a_refused_name_says_so_rather_than_claiming_it_saved() -> None:
    page = run(
        do=[{"type": "name", "value": "x" * 200}],
        answers={"/account/name": {"error": "That name is too long."}},
    )
    assert page["said"] == {"text": "That name is too long.", "hidden": False}


def test_every_language_is_drawn_with_its_stage_and_the_account_ticked() -> None:
    """This is the page where somebody says what they read, so a language missing from
    it would be a question they had no way to answer. Hebrew is drawn on and cannot be
    pressed off in this version. Which are experimental is said once, in the note under
    the lists, rather than on five boxes of six (2026-09-14)."""
    page = run(who={**SIGNED_IN, "learning": ["he", "yi"], "reads": ["en", "ru"]})
    assert page["learning"] == [
        {"code": "he", "on": True, "fixed": True, "experimental": False},
        {"code": "arc", "on": False, "fixed": False, "experimental": False},
        {"code": "yi", "on": True, "fixed": False, "experimental": False},
    ]
    assert page["reads"] == [
        {"code": "en", "on": True, "fixed": False, "experimental": False},
        {"code": "ru", "on": True, "fixed": False, "experimental": False},
    ]


def test_ticking_two_boxes_is_one_request_carrying_the_whole_answer() -> None:
    """A form that submits a set of ticks is saying what the set is, not what changed —
    and two boxes pressed together are one change, not two requests."""
    saved = {**SIGNED_IN, "learning": ["he", "yi"], "reads": ["en", "ru"]}
    page = run(
        do=[
            {"type": "tick", "list": "you-learning", "code": "yi"},
            {"type": "tick", "list": "you-reads", "code": "ru"},
        ],
        answers={"/account/languages": saved},
    )
    asked = [post for post in page["posted"] if post["path"] == "/account/languages"]
    assert asked == [
        {"path": "/account/languages", "body": {"learning": ["he", "yi"], "reads": ["en", "ru"]}}
    ]
    assert page["languagesSaid"] == {"text": "Saved.", "hidden": False}
    assert [t["on"] for t in page["reads"]] == [True, True]
    assert page["restarted"]["count"] > run()["restarted"]["count"], "sync is asked again"


def test_the_last_language_cannot_be_unticked() -> None:
    """Nobody can untick everything: a reader with no language to read into has no
    reader. The box goes back on its own, nothing is sent, and the page says why."""
    page = run(do=[{"type": "tick", "list": "you-reads", "code": "en"}])
    assert [post["path"] for post in page["posted"]] == []
    assert page["reads"][0]["on"] is True
    assert page["languagesSaid"] == {"text": "Keep at least one.", "hidden": False}


def test_a_refused_profile_puts_its_boxes_back() -> None:
    """The server has the last word. Its answer carries what still stands, and the boxes
    are drawn from that rather than from what was asked."""
    page = run(
        do=[{"type": "tick", "list": "you-reads", "code": "ru"}],
        answers={
            "/account/languages": {
                "error": "targum does not have Russian.",
                "learning": ["he"],
                "reads": ["en"],
            }
        },
    )
    assert page["languagesSaid"] == {"text": "targum does not have Russian.", "hidden": False}
    assert [t["on"] for t in page["reads"]] == [True, False]


def test_the_corner_is_told_when_the_name_changes() -> None:
    """The initials in the corner come from /account/me, so the corner has to be asked
    again or it goes on showing the initials of a name nobody has any more."""
    quiet = run()
    page = run(
        do=[{"type": "name", "value": "Dov"}],
        answers={"/account/name": {**SIGNED_IN, "name": "Dov", "initials": "D"}},
    )
    assert page["restarted"]["count"] > quiet["restarted"]["count"]


def test_deleting_an_account_asks_twice() -> None:
    once = run(do=[{"type": "press", "id": "you-forget"}])
    assert once["posted"] == [], "the first press asks; it does not delete"
    assert once["forget"]["label"] == "Delete my account and words"
    assert once["forget"]["disabled"] is False

    twice = run(
        do=[{"type": "press", "id": "you-forget"}, {"type": "press", "id": "you-forget"}],
        answers={"/account/forget": {"message": "Your account is closing."}},
    )
    assert [post["path"] for post in twice["posted"]] == ["/account/forget"]
    assert twice["forget"]["disabled"] is True, "and cannot be pressed a third time"
    assert twice["ending"]["text"] == "Your account is closing."


def test_signing_out_goes_through_sync_rather_than_the_endpoint() -> None:
    """Signing out empties this browser's word store as well as ending the session, and
    only sync knows how to do both."""
    page = run(do=[{"type": "press", "id": "you-out"}])
    assert page["restarted"]["signedOut"] == 1
    assert [post["path"] for post in page["posted"]] == []


def test_the_page_says_its_words_in_the_readers_language() -> None:
    """A Russian reader's count of what they kept is Russian, each figure taking the
    plural Russian's rules give it (targum-internal#184)."""
    page = run(
        strings={
            "language": "ru",
            "strings": {
                "you.kept": "{words} и {phrases} во всех ваших языках.",
                "you.kept.words.many": "{n} слов",
                "you.kept.words.other": "{n} слова",
                "you.kept.phrases.few": "{n} фразы",
                "you.kept.phrases.other": "{n} фразы",
            },
        }
    )
    assert page["kept"] == "512 слов и 24 фразы во всех ваших языках."


# --- what's connected, and taking it back (targum-internal#80) --------------------

CONNECTED = {
    **SIGNED_IN,
    "connections": [
        {
            "client": "c-claude",
            "name": "Claude",
            "scopes": "library record",
            "made": 1,
            "seen": 2,
        },
        {"client": "c-gpt", "name": "ChatGPT", "scopes": "library", "made": 1, "seen": 2},
    ],
}


def test_nothing_connected_draws_no_panel() -> None:
    """A panel saying "nothing is connected" would be a panel advertising connecting."""
    page = run()
    assert page["connectionsPanel"] is True, "hidden"
    assert page["connections"] == []


def test_each_connector_says_what_it_may_do_in_the_reader_s_words() -> None:
    page = run(who=CONNECTED)
    assert page["connectionsPanel"] is False
    assert [one["name"] for one in page["connections"]] == ["Claude", "ChatGPT"]
    assert page["connections"][0]["says"] == "the library, your words and mistakes"
    assert page["connections"][1]["says"] == "the library"


def test_the_scope_that_uses_credits_says_so_here_too() -> None:
    """design.md §12: this is the page they come to when they want to know what they
    agreed to, so it says what the standing grant costs.

    Both spellings, because a grant stores the words the reader approved and those
    outlive a rename: `check` became `chat` on 2026-09-23, and every connector authorised
    before then still holds the old one. A reader shown one fewer scope here than they
    actually agreed to is the failure this guards.
    """
    for held in ("library record chat", "library record check"):
        page = run(
            who={
                **SIGNED_IN,
                "connections": [{"client": "c", "name": "Claude", "scopes": held}],
            }
        )
        says = page["connections"][0]["says"]
        assert "uses your credits" in says, f"{held!r} lost its spending scope"
        assert "hours" not in says


def test_a_connector_with_no_name_is_still_a_row() -> None:
    page = run(who={**SIGNED_IN, "connections": [{"client": "c", "name": "", "scopes": "library"}]})
    assert page["connections"][0]["name"] == "An app"


def test_disconnecting_posts_the_client_and_redraws() -> None:
    page = run(
        who=CONNECTED,
        do=[{"type": "press", "id": "connection-rows:0:2"}],
        answers={
            "/account/disconnect": {
                "disconnected": 2,
                "connections": [CONNECTED["connections"][1]],
            }
        },
    )
    posted = [one for one in page["posted"] if one["path"] == "/account/disconnect"]
    assert posted and posted[0]["body"] == {"client": "c-claude"}
    assert [one["name"] for one in page["connections"]] == ["ChatGPT"], "redrawn from the answer"
    assert page["connectionsSaid"] == {"text": "Disconnected.", "hidden": False}


# --- a reader's own asks (targum-internal#80, note 17) ----------------------------


def test_no_connector_no_box_to_write_one() -> None:
    """A control for writing prompts, shown to somebody with nothing to show them in,
    is a control without a job."""
    page = run(who={**SIGNED_IN, "prompts": []})
    assert page["promptsPanel"] is True, "hidden"


def test_what_a_reader_wrote_is_listed_with_a_way_to_remove_it() -> None:
    page = run(
        who={
            **CONNECTED,
            "prompts": [{"id": 1, "name": "my-verbs", "says": "Drill my verbs.", "made": 1}],
        }
    )
    assert page["promptsPanel"] is False
    assert page["prompts"] == [{"name": "my-verbs", "says": "Drill my verbs."}]


def test_saving_one_posts_both_fields_and_says_what_it_was_called() -> None:
    """The server narrows the name; the page says what it actually saved rather than
    what was typed."""
    page = run(
        who=CONNECTED,
        do=[
            {"type": "write", "id": "prompt-name", "value": "My Verbs"},
            {"type": "write", "id": "prompt-says", "value": "Drill my verbs."},
            {"type": "press", "id": "prompt-save"},
        ],
        answers={
            "/account/prompts": {
                "written": {"id": 1, "name": "my-verbs", "says": "Drill my verbs."},
                "prompts": [{"id": 1, "name": "my-verbs", "says": "Drill my verbs."}],
            }
        },
    )
    posted = [one for one in page["posted"] if one["path"] == "/account/prompts"]
    assert posted and posted[0]["body"] == {"name": "My Verbs", "says": "Drill my verbs."}
    assert page["prompts"] == [{"name": "my-verbs", "says": "Drill my verbs."}]
    assert page["promptsSaid"]["text"] == "Saved as my-verbs. It's in your apps now."


def test_a_refusal_is_said_rather_than_claiming_it_saved() -> None:
    page = run(
        who=CONNECTED,
        do=[{"type": "press", "id": "prompt-save"}],
        answers={"/account/prompts": {"error": "Give it a name.", "prompts": []}},
    )
    assert page["promptsSaid"] == {"text": "Give it a name.", "hidden": False}
    assert page["prompts"] == []


def test_removing_one_posts_its_name_and_redraws() -> None:
    page = run(
        who={
            **CONNECTED,
            "prompts": [{"id": 1, "name": "my-verbs", "says": "Drill my verbs."}],
        },
        do=[{"type": "press", "id": "prompt-rows:0:2"}],
        answers={"/account/prompts": {"prompts": []}},
    )
    posted = [one for one in page["posted"] if one["path"] == "/account/prompts"]
    assert posted[0]["body"] == {"name": "my-verbs", "gone": True}
    assert page["prompts"] == []
    assert page["promptsSaid"]["text"] == "Removed."
