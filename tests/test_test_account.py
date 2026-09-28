"""Test accounts, wiped at every sign-out (David, 2026-09-28: "a testing account that you
and I can use, and whose memory is wiped each time it logs out").

The danger in this is a real reader's account being emptied, so most of what is pinned
here is what does *not* happen: a real account signing out keeps everything, a real
account cannot be made a test account, and the wipe touches nobody else.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import test_serve
from test_serve import Postbox, call, sign_in
from typer.testing import CliRunner

from targum import accounts
from targum.accounts import Store
from targum.cli import app

served = test_serve.served
postbox = test_serve.postbox

WORD = {"language": "he", "lemma": "ספר", "status": 9, "at": 1, "seen": 1}


def person_tables(path: Path) -> set[str]:
    db = sqlite3.connect(path)
    names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {
        name
        for name in names
        if "person" in {row[1] for row in db.execute(f"PRAGMA table_info({name})")}
    }


def test_every_table_that_holds_a_reader_is_emptied_by_the_wipe(tmp_path: Path) -> None:
    """A table added tomorrow with a `person` column fails here until the wipe names it,
    so a test account never carries something into its next first visit."""
    Store(tmp_path / "words.db")
    held = person_tables(tmp_path / "words.db")
    named = set(accounts.WIPED) | set(accounts.WIPE_BY_HAND)
    assert held - named == set(), f"not wiped: {sorted(held - named)}"


def test_a_real_account_cannot_become_a_test_account(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    store.start_sign_in("reader@example.com")
    try:
        store.make_test_account("reader@example.com")
    except ValueError as error:
        assert "already has an account" in str(error)
    else:
        raise AssertionError("a real account was made a test account")
    assert not store.is_test_account_email("reader@example.com")
    made = store.make_test_account("tester@example.com")
    assert store.make_test_account(made) == made, "marking a test account again is harmless"
    assert "tester@example.com" in store.invitations()


def test_only_a_test_account_is_wiped_or_handed_a_link(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    token = store.start_sign_in("reader@example.com")
    signed = store.finish_sign_in(token)
    assert signed is not None
    person = signed[0]
    for act in (lambda: store.wipe(person), lambda: store.test_sign_in("reader@example.com")):
        try:
            act()
        except ValueError:
            continue
        raise AssertionError("a real account was wiped or handed a link")


def test_a_real_reader_signing_out_keeps_everything(
    served: tuple[int, str, Path], postbox: Postbox, tmp_path: Path
) -> None:
    port, token, _ = served
    cookie = sign_in(port, postbox, "reader@example.com")
    call(port, "POST", f"/sync?k={token}", {"words": [WORD]}, cookie=cookie)
    call(port, "POST", "/account/sign-out", {}, cookie=cookie)
    again = sign_in(port, postbox, "reader@example.com")
    _, pulled, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=again)
    assert [w["lemma"] for w in pulled["words"]] == ["ספר"]


def test_a_test_account_signing_out_is_a_first_visit_next_time(
    served: tuple[int, str, Path], postbox: Postbox, tmp_path: Path
) -> None:
    """Its words, what it said on arrival and its texts go; the account and its
    invitation stay; and another reader's words are not touched."""
    port, token, out = served
    store = Store(tmp_path / "words.db")
    store.make_test_account("tester@example.com")

    other = sign_in(port, postbox, "reader@example.com")
    call(port, "POST", f"/sync?k={token}", {"words": [WORD]}, cookie=other)

    cookie = sign_in(port, postbox, "tester@example.com")
    call(port, "POST", f"/sync?k={token}", {"words": [WORD]}, cookie=cookie)
    call(port, "POST", f"/account/interest?k={token}", {"interest": ["sport"]}, cookie=cookie)
    person = store.person_by_email("tester@example.com")
    assert person is not None
    home = out / f"p{person.id}"
    home.mkdir(parents=True, exist_ok=True)
    (home / "a-text").mkdir()

    status, _, _ = call(port, "POST", "/account/sign-out", {}, cookie=cookie)
    assert status == 200
    assert not home.exists(), "the texts it built go with it"
    assert store.is_test_account_email("tester@example.com")
    assert "tester@example.com" in store.invitations()

    fresh = sign_in(port, postbox, "tester@example.com")
    _, pulled, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=fresh)
    assert pulled["words"] == []
    _, me, _ = call(port, "GET", f"/account/me?k={token}", cookie=fresh)
    assert not me.get("interest"), "asked the arrival's questions again"

    _, theirs, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=other)
    assert [w["lemma"] for w in theirs["words"]] == ["ספר"], "nobody else is touched"


def test_the_command_makes_one_and_prints_a_link(tmp_path: Path) -> None:
    db = tmp_path / "words.db"
    run = CliRunner().invoke(
        app,
        ["test-account", "tester@example.com", "--link", "--address", "https://targum.test",
         "--store", str(db)],
    )  # fmt: skip
    assert run.exit_code == 0, run.output
    assert "https://targum.test/account/enter?t=" in run.output
    Store(db).start_sign_in("reader@example.com")
    refused = CliRunner().invoke(app, ["test-account", "reader@example.com", "--store", str(db)])
    assert refused.exit_code != 0
