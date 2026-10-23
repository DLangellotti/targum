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
    assert page["posted"] == []


def test_the_page_fills_itself_in_for_whoever_is_signed_in() -> None:
    """Board AccountDesk (2026-10-09): the address on the Account card. The name is no
    longer asked here."""
    page = run()
    assert page["stranger"] is True
    assert not any(page["panels"].values())
    assert page["email"] == "yosef@example.com"


def test_each_language_learned_is_a_row_and_the_rest_are_started_from_a_list() -> None:
    """Board AccountDesk: a row each language being learned, with Remove where it may go
    (Hebrew stays on, and the server holds the same line), and Start another offering the
    rest."""
    page = run(who={**SIGNED_IN, "learning": ["he", "yi"], "reads": ["en"]})
    assert page["learning"] == [
        {"code": "he", "removable": False},
        {"code": "yi", "removable": True},
    ]
    assert [one["value"] for one in page["start"]] == ["", "arc"]
    assert page["start"][0]["label"] == "Choose…" and page["start"][0]["on"]


def test_starting_a_language_sends_the_whole_answer() -> None:
    """The account is told what the set is, not what changed."""
    saved = {**SIGNED_IN, "learning": ["he", "arc"], "reads": ["en"]}
    page = run(
        do=[{"type": "pick", "id": "you-start", "value": "arc"}],
        answers={"/account/languages": saved},
    )
    asked = [post for post in page["posted"] if post["path"] == "/account/languages"]
    assert asked == [
        {"path": "/account/languages", "body": {"learning": ["he", "arc"], "reads": ["en"]}}
    ]
    assert page["languagesSaid"] == {"text": "Saved.", "hidden": False}
    assert [row["code"] for row in page["learning"]] == ["he", "arc"], "drawn from the answer"
    assert page["restarted"]["count"] > run()["restarted"]["count"], "sync is asked again"


def test_removing_a_language_sends_the_rest() -> None:
    saved = {**SIGNED_IN, "learning": ["he"], "reads": ["en"]}
    page = run(
        who={**SIGNED_IN, "learning": ["he", "yi"]},
        do=[{"type": "remove", "code": "yi"}],
        answers={"/account/languages": saved},
    )
    asked = [post["body"] for post in page["posted"] if post["path"] == "/account/languages"]
    assert asked == [{"learning": ["he"], "reads": ["en"]}]
    assert [row["code"] for row in page["learning"]] == ["he"]


def test_a_refused_change_puts_its_rows_back() -> None:
    """The server has the last word. Its answer carries what still stands, and the rows
    are drawn from that rather than from what was asked."""
    page = run(
        do=[{"type": "pick", "id": "you-start", "value": "yi"}],
        answers={
            "/account/languages": {
                "error": "targum does not have Yiddish.",
                "learning": ["he"],
                "reads": ["en"],
            }
        },
    )
    assert page["languagesSaid"] == {"text": "targum does not have Yiddish.", "hidden": False}
    assert [row["code"] for row in page["learning"]] == ["he"]


def test_the_language_read_into_is_one_choice() -> None:
    """Meanings, translations and the menus are one setting on the account
    (`strings.reading_language`), so they are one control; an account that reads into
    both keeps that answer as a choice of its own."""
    page = run()
    assert [(one["value"], one["on"]) for one in page["reads"]] == [("en", True), ("ru", False)]
    both = run(who={**SIGNED_IN, "reads": ["en", "ru"]})
    assert both["reads"][-1] == {"value": "en ru", "label": "English and Russian", "on": True}
    picked = run(
        do=[{"type": "pick", "id": "you-reads", "value": "ru"}],
        answers={"/account/languages": {**SIGNED_IN, "reads": ["ru"]}},
    )
    asked = [post["body"] for post in picked["posted"] if post["path"] == "/account/languages"]
    assert asked == [{"learning": ["he"], "reads": ["ru"]}]


def test_deleting_an_account_asks_twice() -> None:
    once = run(do=[{"type": "press", "id": "you-forget"}])
    assert once["posted"] == [], "the first press asks; it does not delete"
    assert once["forget"]["label"] == "Yes, delete my account"
    assert once["forget"]["disabled"] is False

    twice = run(
        do=[{"type": "press", "id": "you-forget"}, {"type": "press", "id": "you-forget"}],
        answers={"/account/forget": {"message": "Your account is closing."}},
    )
    assert [post["path"] for post in twice["posted"]] == ["/account/forget"]
    assert twice["forget"]["disabled"] is True, "and cannot be pressed a third time"
    # Said on the closing card, not a line under the press (targum-internal#469, B5).
    assert twice["closed"] == {"text": "Your account is closing.", "hidden": False}


def test_signing_out_goes_through_sync_rather_than_the_endpoint() -> None:
    """Signing out empties this browser's word store as well as ending the session, and
    only sync knows how to do both."""
    page = run(do=[{"type": "press", "id": "you-out"}])
    assert page["restarted"]["signedOut"] == 1
    assert [post["path"] for post in page["posted"]] == []


def test_the_page_says_its_words_in_the_readers_language() -> None:
    """A Russian reader's rows are Russian (targum-internal#184)."""
    page = run(
        strings={
            "language": "ru",
            "strings": {"you.choose": "Выбрать…"},
        },
        who={**SIGNED_IN, "reads": ["ru"]},
    )
    assert page["start"][0]["label"] == "Выбрать…"


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


def test_nothing_connected_says_so_with_a_way_to_connect() -> None:
    """design's §14 pass (targum-internal#469, polish 1): with no card at all, the account
    never said apps could be connected. One quiet line and "Connect an app" instead."""
    page = run()
    assert page["connectionsPanel"] is False, "drawn"
    assert page["connections"] == []
    assert page["connectionsNone"] is False and page["connectionsSays"] is True
    assert page["connectLink"] == "Connect an app"


def test_something_connected_keeps_its_note_and_connect_another() -> None:
    page = run(who=CONNECTED)
    assert page["connectionsNone"] is True and page["connectionsSays"] is False
    assert page["connectLink"] == "Connect another app"


def test_a_date_is_the_day_and_the_month_in_full_unbroken() -> None:
    """Polish 3 and 4: one form of date on the page, as credits say "November 1", with
    the year only when it isn't this one, and a no-break space so it never splits."""
    import time

    now = int(time.time() * 1000)
    page = run(
        who={
            **SIGNED_IN,
            "connections": [{"client": "a", "name": "Claude", "scopes": "library", "made": now}],
        }
    )
    when = page["connections"][0]["when"]
    year = time.strftime("%Y")
    month = time.strftime("%B")
    assert when.startswith("Connected " + month + "\u00a0"), when
    assert year not in when and " " not in when.removeprefix("Connected ")


def test_each_connector_says_what_it_may_do_in_the_approval_page_s_words() -> None:
    """Board ConnYou: "It may:" and a line each, in the sentences the approval page used,
    so what is shown here is what was agreed to."""
    page = run(who=CONNECTED)
    assert page["connectionsPanel"] is False
    assert [one["name"] for one in page["connections"]] == ["Claude", "ChatGPT"]
    assert page["connections"][0]["may"] == [
        "Search the library and look up what is at a link",
        "Read your words, your mistakes and your progress",
    ]
    assert page["connections"][1]["may"] == ["Search the library and look up what is at a link"]
    assert page["connections"][0]["press"] == "Disconnect"


def test_the_chat_scope_says_chatting_is_included() -> None:
    """design.md §12, 2026-09-24: this is the page they come to when they want to know
    what they agreed to, and what it says is what the approval page said — chatting is
    included, with no credits or hours in the line.

    Both spellings, because a grant stores the words the reader approved and those
    outlive a rename: `check` became `chat` on 2026-09-23, and every connector authorised
    before then still holds the old one.
    """
    for held in ("library record chat", "library record check"):
        page = run(
            who={
                **SIGNED_IN,
                "connections": [{"client": "c", "name": "Claude", "scopes": held}],
            }
        )
        said = page["connections"][0]["may"][-1]
        assert said.endswith("Chatting is included."), f"{held!r} lost its spending scope"
        assert "credits" not in said and "hours" not in said


def test_one_app_connected_twice_is_one_row_with_both_dates() -> None:
    """Claude registers itself afresh on every reconnect, and removing it in Claude does
    not reach us, so two grants called "Claude" are one app connected twice (board
    ConnYou: "Connected 22 September, again 6 October")."""
    made = 1758700800000  # 2025-09-24, noon or so anywhere
    page = run(
        who={
            **SIGNED_IN,
            "connections": [
                {"client": "a", "name": "Claude", "scopes": "library", "made": made, "seen": 0},
                {
                    "client": "b",
                    "name": "Claude",
                    "scopes": "library",
                    "made": made + 12 * 86400000,
                    "seen": made + 13 * 86400000,
                },
            ],
        }
    )
    assert len(page["connections"]) == 1
    when = page["connections"][0]["when"]
    assert when.startswith("Connected ") and ", reconnected " in when and ", last used " in when
    assert "2025" in when


def test_a_connector_with_no_name_is_still_a_row() -> None:
    page = run(who={**SIGNED_IN, "connections": [{"client": "c", "name": "", "scopes": "library"}]})
    assert page["connections"][0]["name"] == "An app"


def test_disconnecting_takes_every_grant_the_app_holds_and_redraws() -> None:
    twice = {
        **SIGNED_IN,
        "connections": [
            {"client": "c-1", "name": "Claude", "scopes": "library", "made": 1, "seen": 2},
            {"client": "c-2", "name": "Claude", "scopes": "library", "made": 3, "seen": 4},
            CONNECTED["connections"][1],
        ],
    }
    page = run(
        who=twice,
        do=[{"type": "press", "id": "connection-rows:0:2"}],
        answers={
            "/account/disconnect": {
                "disconnected": 2,
                "connections": [CONNECTED["connections"][1]],
            }
        },
    )
    posted = [one["body"] for one in page["posted"] if one["path"] == "/account/disconnect"]
    assert posted == [{"client": "c-1"}, {"client": "c-2"}]
    assert [one["name"] for one in page["connections"]] == ["ChatGPT"], "redrawn from the answer"
    assert page["connectionsSaid"] == {
        "text": "Disconnected. Claude can't reach your account any more.",
        "hidden": False,
    }


def test_disconnecting_the_last_app_keeps_saying_so() -> None:
    """The panel is drawn only while something is connected, and the last Disconnect
    used to take the panel, and what it said, away with it."""
    one = {**SIGNED_IN, "connections": CONNECTED["connections"][:1]}
    page = run(
        who=one,
        do=[{"type": "press", "id": "connection-rows:0:2"}],
        answers={"/account/disconnect": {"disconnected": 2, "connections": []}},
    )
    assert page["connections"] == []
    assert page["connectionsPanel"] is False, "still drawn"
    assert page["connectionsSaid"]["text"].startswith("Disconnected.")


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


def test_a_prompt_and_a_telegram_chat_are_rows_like_the_languages() -> None:
    """Polish 6: they were bare items, the name in plain body and the text a size up in
    ink. Now a `.row` with its name over a quiet line, the prompt's held to two lines."""
    page = run(
        who={
            **CONNECTED,
            "prompts": [{"id": 1, "name": "my-verbs", "says": "Drill my verbs.", "made": 1}],
            "telegram": {"chats": [{"chat": 7, "linked": 1758700800000}]},
        }
    )
    assert page["promptRows"] == [{"className": "row", "clamped": True, "press": "Remove"}]
    assert page["telegram"][0]["className"] == "row"
    assert page["telegram"][0]["name"] == "A Telegram chat"
    assert page["telegram"][0]["says"].startswith("Linked September")


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
        do=[{"type": "press", "id": "prompt-rows:0:1:0"}],
        answers={"/account/prompts": {"prompts": []}},
    )
    posted = [one for one in page["posted"] if one["path"] == "/account/prompts"]
    assert posted[0]["body"] == {"name": "my-verbs", "gone": True}
    assert page["prompts"] == []
    assert page["promptsSaid"]["text"] == "Removed."


def test_a_remove_that_fails_says_remove() -> None:
    page = run(
        who={
            **CONNECTED,
            "prompts": [{"id": 1, "name": "my-verbs", "says": "Drill my verbs."}],
        },
        do=[{"type": "press", "id": "prompt-rows:0:1:0"}],
        answers={"/account/prompts": "fail"},
    )
    assert page["promptsSaid"]["text"] == "We couldn't remove that. Try again."


# -- your Hebrew: the rung named on arrival, changed here (design.md §12, 2026-10-07) ----


def test_the_page_shows_the_rung_they_named_in_their_own_words() -> None:
    """The arrival's eight answers and "Not said", the one they gave chosen, and never a
    letter: "nothing anywhere says 'you said gimel'" still holds."""
    page = run(who={**SIGNED_IN, "declared": "dalet"})
    level = page["level"]
    assert [one["value"] for one in level] == [
        "",
        "aleph",
        "aleph-plus",
        "bet",
        "bet-plus",
        "gimel",
        "dalet",
        "hey",
        "vav",
    ]
    assert [one["value"] for one in level if one["on"]] == ["dalet"]
    assert level[6]["label"] == "I follow most things comfortably"
    assert not any("ד" in one["label"] or "dalet" in one["label"] for one in level)
    assert [one["value"] for one in run()["level"] if one["on"]] == [""], "none named"


def test_a_new_rung_is_kept_on_the_account_and_in_the_browser() -> None:
    """The reader page reads the browser's copy, so a change reaches the next page at once."""
    page = run(
        who={**SIGNED_IN, "declared": "aleph"},
        do=[{"type": "pick", "id": "you-level", "value": "hey"}],
        answers={"/account/level": {"signedIn": True, "declared": "hey"}},
    )
    assert {"path": "/account/level", "body": {"level": "hey"}} in page["posted"]
    assert page["declaredHere"] == "hey"
    assert page["languagesSaid"] == {"text": "Saved.", "hidden": False}


def test_not_said_takes_the_browsers_copy_back_too() -> None:
    page = run(
        who={**SIGNED_IN, "declared": "gimel"},
        do=[{"type": "pick", "id": "you-level", "value": ""}],
        answers={"/account/level": {"signedIn": True, "declared": ""}},
    )
    assert page["declaredHere"] is None


def test_the_hebrew_form_of_address_is_a_row_while_hebrew_is_learned() -> None:
    """#695 took the setting off the page while the conversation went on reading it. It is
    back as a row of Your languages, marked from what the account keeps, and only where
    Hebrew is being learned."""
    page = run(who={**SIGNED_IN, "address": "f"})
    assert page["address"] == {"hidden": False, "m": "false", "f": "true"}
    unsaid = run(who={**SIGNED_IN, "address": ""})
    assert unsaid["address"] == {"hidden": False, "m": "false", "f": "false"}
    elsewhere = run(who={**SIGNED_IN, "learning": ["yi"]})
    assert elsewhere["address"]["hidden"] is True


def test_pressing_a_form_of_address_saves_it_where_it_was_always_kept() -> None:
    page = run(
        do=[{"type": "press", "id": "address-m"}],
        answers={"/account/address": {"signedIn": True, "address": "m"}},
    )
    asked = [post["body"] for post in page["posted"] if post["path"] == "/account/address"]
    assert asked == [{"address": "m"}]
    assert page["address"] == {"hidden": False, "m": "true", "f": "false"}
    assert page["languagesSaid"] == {"text": "Saved.", "hidden": False}


def test_a_refused_form_of_address_keeps_what_was_marked() -> None:
    page = run(
        who={**SIGNED_IN, "address": "f"},
        do=[{"type": "press", "id": "address-m"}],
        answers={"/account/address": {"signedIn": False}},
    )
    assert page["address"]["f"] == "true" and page["address"]["m"] == "false"
    assert page["languagesSaid"]["hidden"] is False


def test_off_the_plan_card_is_left_alone() -> None:
    """With `TARGUM_PLANS` off the server says `{"on": false}`, and the page draws no plan
    of its own: the early-access card stays the plan, as it was before the switch."""
    page = run(who={**SIGNED_IN, "plan": {"on": False}})
    # The stub document starts every element shown; the card is hidden in the template,
    # and the page never touches it.
    assert page["plan"]["freeSays"] == "" and page["plan"]["paidSays"] == ""
    assert page["plan"]["offer"] == "" and page["plan"]["topUps"] == []


def test_on_free_says_what_it_holds_and_what_a_plan_gives() -> None:
    """Board PlanAccount, On Free (design.md §12, "Free and Plan, behind a switch")."""
    plan = {"on": True, "plan": "free", "credits": 60, "planCredits": 480, "words": 300}
    page = run(who={**SIGNED_IN, "plan": {**plan, "listed": 120, "topUps": []}})
    drawn = page["plan"]
    assert drawn["on"] is False and drawn["free"] is False and drawn["paid"] is True
    assert drawn["freeSays"] == (
        "The library, word cards and your text uploads, with 60 credits a month"
    )
    assert "A plan gives you 480 credits a month, which is 8 hours" in drawn["offer"]
    assert drawn["words"].startswith("120 of 300 saved words") and drawn["wordsHidden"] is False
    assert drawn["wordsMore"] is True, "far from the cap, no See plans in the row"
    assert drawn["see"] is False, "the head's See plans instead"


@pytest.mark.parametrize(
    ("listed", "said"),
    [
        (287, "287 of 300 saved words. You can save 13 more on Free"),
        (300, "300 of 300 saved words, as many as Free keeps."),
    ],
)
def test_near_the_free_word_cap_says_how_many_are_left(listed: int, said: str) -> None:
    """Polish 10: past nine in ten of the cap, the row says how many more fit and points
    to See plans; 287 of 300 used to read like 12 of 300."""
    plan = {"on": True, "plan": "free", "credits": 60, "planCredits": 480, "words": 300}
    page = run(who={**SIGNED_IN, "plan": {**plan, "listed": listed, "topUps": []}})
    assert page["plan"]["words"].startswith(said)
    assert page["plan"]["wordsMore"] is False, "See plans shown"
    # Once (qa-claude on #871): the row's link says why, so the head's goes.
    assert page["plan"]["see"] is True, "See plans twice"


def test_on_the_plan_says_its_month_and_offers_top_up() -> None:
    """Board PlanAccount, On the plan, and PlanTopUp from Your account: every press greyed."""
    plan = {"on": True, "plan": "plan", "credits": 480, "planCredits": 480, "words": None}
    who = {**SIGNED_IN, "hours": {"used": 0, "allowed": 8, "ends": "November 1"}}
    page = run(who={**who, "plan": {**plan, "listed": 0, "topUps": [60, 180, 300]}})
    drawn = page["plan"]
    assert drawn["paid"] is False and drawn["free"] is True
    assert drawn["paidSays"] == "480 credits a month, which is 8 hours of audio or video"
    assert drawn["back"] == "Your credits reset on November 1"
    assert drawn["topUps"] == ["60 credits", "180 credits", "300 credits"]
    assert drawn["see"] is False, "on the plan, the head's See plans"
