"""Send to Anki, the server half (targum-internal#540; design.md §12, "Send to Anki talks
to the Anki on your own computer", 2026-11-14): `/account/anki/notes`, `/sound` and
`/line`, read-only and spending nothing, and the one page whose policy names the reader's
own AnkiConnect.

The server never calls AnkiConnect; nothing here touches a network.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
import test_serve
from test_meetings import text, w
from test_reading_line import ms
from test_sentences import recorded
from test_serve import Postbox, call, sign_in

from targum import anki_send, meetings
from targum.render.builder import LISTS, list_page
from targum.serve import ANKI_CONNECT, Handler

served = test_serve.served
postbox = test_serve.postbox

#: The real licence rule, before the fixture below stands in for it.
MAY_LEAVE = anki_send.shared_may_leave

TEMPLATES = Path(__file__).resolve().parent.parent / "src" / "targum" / "render" / "templates"


@pytest.fixture(autouse=True)
def leaving(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Shared texts here have no catalogue row, so they are let leave unless a test says
    otherwise; clips are kept in this test's own cache."""
    monkeypatch.setattr(anki_send, "shared_may_leave", lambda _folder: True)
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))


def policy(body: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for part in Handler._policy(body.encode("utf-8")).split(";"):
        name, *sources = part.split()
        out[name] = sources
    return out


# -- the policy ---------------------------------------------------------------------------


def test_the_words_page_policy_names_anki_and_nothing_else() -> None:
    page = policy(list_page("t", "words"))
    assert page["connect-src"] == ["'self'", ANKI_CONNECT] == ["'self'", "http://127.0.0.1:8765"]
    for directive, sources in page.items():
        if directive == "connect-src":
            continue
        for source in sources:
            assert source.startswith("'") or source in ("data:", "blob:"), (directive, source)


def test_no_other_page_names_anki() -> None:
    for which in LISTS:
        if which == "words":
            continue
        assert policy(list_page("t", which))["connect-src"] == ["'self'"], which
    # The press is drawn by one template, and only there does the policy widen.
    holding = [
        path.name
        for path in TEMPLATES.glob("*.j2")
        if re.search(r'<button\b[^>]*\bid="send-anki"', path.read_text(encoding="utf-8"))
    ]
    assert holding == ["yours.html.j2"]
    # A reader whose text quotes the id is a text, not the press.
    quoted = '<p>&lt;button id="send-anki"&gt;</p><script>var x = "id=\\"send-anki\\"";</script>'
    assert policy(quoted)["connect-src"] == ["'self'"]


# -- /account/anki/notes ----------------------------------------------------------------


def keep(
    port: int, token: str, cookie: str, words: list[tuple[str, int]], sections: list[Any] = ()
) -> None:
    rows = [
        {"language": "he", "lemma": lemma, "status": status, "at": n + 1, "seen": n + 1,
         "meaning": f"m-{lemma}"}
        for n, (lemma, status) in enumerate(words)
    ]  # fmt: skip
    finished = [
        {"hash": hash_, "section": str(section), "at": at, "seen": at}
        for hash_, section, at in sections
    ]
    status, said, _ = call(
        port, "POST", f"/sync?k={token}", {"words": rows, "sections": finished}, cookie=cookie
    )
    assert status == 200, said


def notes(port: int, token: str, cookie: str, page: int = 0) -> dict[str, Any]:
    status, said, _ = call(
        port, "GET", f"/account/anki/notes?language=he&page={page}&k={token}", cookie=cookie
    )
    assert status == 200, said
    return said


def by_key(said: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {one["key"]: one for one in said["words"]}


def test_anki_notes_is_signed_in(served: tuple[int, str, Path]) -> None:
    port, token, _ = served
    for route in ("notes?language=he", "sound?key=he%3Ax", "line?key=he%3Ax"):
        status, said, _ = call(port, "GET", f"/account/anki/{route}&k={token}")
        assert status in (401, 404), route
        assert status == 401 or route != "notes?language=he"


def test_anki_notes_are_the_accounts_learning_words(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, _ = served
    other = sign_in(port, postbox, "other@example.com")
    keep(port, token, other, [("זר", 2)])
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("ספר", 1), ("בית", 3), ("עיר", 9), ("משה", 0)])
    said = by_key(notes(port, token, cookie))
    assert set(said) == {"he:ספר", "he:בית", "he:עיר"}, "never ignored, never another's"
    assert said["he:ספר"]["add"] and said["he:בית"]["add"]
    assert said["he:עיר"]["add"] is False, "a known word is updated, never added"
    assert said["he:בית"]["meaning"] == "m-בית"
    assert said["he:בית"]["tags"] == "targum targum::he targum::level-3 targum::sent"


def test_anki_notes_page_two_hundred_at_a_time(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, _ = served
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [(f"מילה{n}", 2) for n in range(450)])
    first, second, third = (notes(port, token, cookie, n) for n in range(3))
    assert (len(first["words"]), len(second["words"]), len(third["words"])) == (200, 200, 50)
    assert (first["next"], second["next"], third["next"]) == (1, 2, None)
    assert first["total"] == 450


def test_anki_notes_spend_nothing(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import speech
    from targum.serve import Library

    def never(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Send to Anki spent")

    monkeypatch.setattr(speech, "render", never)
    for name in ("claim", "claim_turn", "press"):
        monkeypatch.setattr(Library, name, never)
    port, token, out = served
    folder = text(out / "shared" / "one", {1: [("הילד הלך אל הבית", [w("בית", "בית")])]},
                  content_hash="one")  # fmt: skip
    recorded(folder, {"s1-0": [1.0, 3.5]})
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("בית", 2), ("ספר", 2)], [("one", 1, ms(2026, 9))])
    said = notes(port, token, cookie)
    for one in said["words"]:
        for route in (one["sound"], one["line"]):
            if route:
                call(port, "GET", f"{route}&k={token}", cookie=cookie)
    assert jobs(out) == 0


def jobs(out: Path) -> int:
    """Job rows in the test server's store, which the fixture keeps beside `out`."""
    import sqlite3

    db = sqlite3.connect(out.parent / "words.db")
    try:
        return int(db.execute("SELECT COUNT(*) FROM job").fetchone()[0])
    finally:
        db.close()


def test_a_word_sound_only_where_one_is_kept(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    from targum.serve import said_clip

    port, token, _ = served
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("ספר", 2), ("בית", 2)])
    into, kept = said_clip("ספר", "he")
    assert kept is None
    into.parent.mkdir(parents=True, exist_ok=True)
    clip = into.with_suffix(".mp3")
    clip.write_bytes(b"ID3said")
    said = by_key(notes(port, token, cookie))
    assert said["he:ספר"]["sound"] == f"/account/anki/sound?key={quote('he:ספר')}"
    assert said["he:ספר"]["soundFile"].startswith("targum-") and said["he:ספר"][
        "soundFile"
    ].endswith(".mp3")
    assert said["he:בית"]["sound"] == "" and said["he:בית"]["soundFile"] == ""
    status, body, _ = call(port, "GET", f"{said['he:ספר']['sound']}&k={token}", cookie=cookie)
    assert status == 200 and body == b"ID3said"
    status, _, _ = call(port, "GET", f"/account/anki/sound?key={quote('he:בית')}&k={token}",
                        cookie=cookie)  # fmt: skip
    assert status == 404


def test_the_line_is_the_first_met_and_stable(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    early = text(out / "shared" / "early", {1: [("ספר ישן על המדף", [w("ספר", "ספר")])]},
                 content_hash="early", translation={"s1-0": "An old book on the shelf"},
                 pointed={"s1-0": "סֵפֶר יָשָׁן עַל הַמַּדָּף"})  # fmt: skip
    text(out / "shared" / "late", {1: [("ספר חדש", [w("ספר", "ספר")])]}, content_hash="late")
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("ספר", 2)],
         [("late", 1, ms(2026, 10)), ("early", 1, ms(2026, 8))])  # fmt: skip
    first = by_key(notes(port, token, cookie))["he:ספר"]
    again = by_key(notes(port, token, cookie))["he:ספר"]
    assert first == again, "two asks, one note"
    line = meetings.lines_met(["ספר"], [("early", "1", 1)], {"early": (early, "he")}.get, "he")
    card = meetings.card_line(line["ספר"], "en")
    assert card is not None
    assert first["gap"] == card["word"] == "סֵפֶר" == first["term"]
    assert first["before"] + first["gap"] + first["after"] == card["line"]
    assert len(first["before"]) == card["start"]
    assert first["translation"] == "An old book on the shelf"
    assert first["source"] == "A Book"


def test_a_word_met_in_no_finished_section_takes_its_line_from_the_reader_s_shelf(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("בית", 2)])
    home = served_home(out)
    text(home / "mine", {1: [("אל הבית", [w("בית", "בית")])]}, content_hash="mine")
    (home / "mine" / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    said = by_key(notes(port, token, cookie))["he:בית"]
    assert said["gap"] == "בית" and said["before"] == "אל ה"


def served_home(out: Path, email: str = "reader@example.com") -> Path:
    """A reader's own home on the test server: `Library.home`'s `p<id>`."""
    import sqlite3

    db = sqlite3.connect(out.parent / "words.db")
    try:
        (person,) = db.execute("SELECT id FROM person WHERE email = ?", (email,)).fetchone()
    finally:
        db.close()
    return out / f"p{person}"


def test_a_word_with_no_line_has_no_gap(served: tuple[int, str, Path], postbox: Postbox) -> None:
    port, token, _ = served
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("ספר", 2)])
    said = by_key(notes(port, token, cookie))["he:ספר"]
    assert (said["before"], said["gap"], said["after"], said["line"]) == ("", "", "", "")
    assert said["term"] == "ספר" and said["source"] == ""


def test_a_line_clip_is_cut_once_and_held_to_20_seconds(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    cuts: list[list[str]] = []

    def ffmpeg(command: list[str], **_kwargs: Any) -> Any:
        cuts.append(command)
        Path(command[-1]).write_bytes(b"ID3cut")
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setattr(anki_send.subprocess, "run", ffmpeg)
    port, token, out = served
    folder = text(
        out / "shared" / "one",
        {1: [("הילד הלך אל הבית", [w("בית", "בית")]), ("ספר ארוך מאוד", [w("ספר", "ספר")]),
             ("עיר גדולה", [w("עיר", "עיר")])]},
        content_hash="one",
    )  # fmt: skip
    recorded(folder, {"s1-0": [1.0, 3.5], "s1-1": [4.0, 4.0 + anki_send.LINE_MOST + 1]})
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("בית", 2), ("ספר", 2), ("עיר", 2)], [("one", 1, ms(2026, 9))])
    said = by_key(notes(port, token, cookie))
    assert said["he:ספר"]["line"] == "" and said["he:ספר"]["gap"] == "ספר", "too long to hold"
    assert said["he:עיר"]["line"] == "", "a line with no clock has no sound"
    line = said["he:בית"]
    assert line["line"] and line["lineFile"].startswith("targum-line-")
    for _ in range(2):
        status, body, _ = call(port, "GET", f"{line['line']}&k={token}", cookie=cookie)
        assert status == 200 and body == b"ID3cut"
    assert len(cuts) == 1, "cut once, then served from the cache"
    (command,) = cuts
    assert command[command.index("-ss") + 1] == "0.850"
    assert command[command.index("-t") + 1] == "2.800"
    assert "-ac" in command and command[command.index("-b:a") + 1] == "64k"


def test_a_line_clip_is_the_owners_only(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    def ffmpeg(command: list[str], **_kwargs: Any) -> Any:
        Path(command[-1]).write_bytes(b"ID3cut")
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setattr(anki_send.subprocess, "run", ffmpeg)
    port, token, out = served
    folder = text(out / "shared" / "one", {1: [("הילד הלך אל הבית", [w("בית", "בית")])]},
                  content_hash="one")  # fmt: skip
    recorded(folder, {"s1-0": [1.0, 3.5]})
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("בית", 2)], [("one", 1, ms(2026, 9))])
    line = by_key(notes(port, token, cookie))["he:בית"]["line"]
    assert line
    other = sign_in(port, postbox, "other@example.com")
    status, _, _ = call(port, "GET", f"{line}&k={token}", cookie=other)
    assert status == 404, "a key another account does not save is nobody's"
    keep(port, token, other, [("בית", 2)])
    status, _, _ = call(port, "GET", f"{line}&k={token}", cookie=other)
    assert status == 404, "and a line they never met is not theirs either"


def test_a_line_that_may_not_leave_is_not_sent(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, token, out = served
    folder = text(out / "shared" / "shut", {1: [("הילד הלך אל הבית", [w("בית", "בית")])]},
                  content_hash="shut")  # fmt: skip
    recorded(folder, {"s1-0": [1.0, 3.5]})
    monkeypatch.setattr(anki_send, "shared_may_leave", lambda one: one.name != "shut")
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("בית", 2)], [("shut", 1, ms(2026, 9))])
    said = by_key(notes(port, token, cookie))["he:בית"]
    assert (said["gap"], said["line"], said["source"]) == ("", "", ""), "no gap card"


def test_a_shared_text_the_catalogue_does_not_know_may_not_leave(tmp_path: Path) -> None:
    folder = text(tmp_path / "t", {1: [("שלום", [w("שלום", "שלום")])]})
    assert MAY_LEAVE(folder) is False


def test_a_recording_carries_its_credit_and_a_closed_one_stays() -> None:
    heard = anki_send.Heard(Path("/r.mp3"), 1.0, 3.0, "Read by Shmuel", "CC BY-SA 4.0")
    line = {"before": "אל ה", "gap": "בית", "after": "", "translation": "", "title": "Ruth"}
    row = {"lemma": "בית", "status": 2, "surface": "בית", "meaning": "house", "note": ""}
    said = anki_send.note(row, "he", line, heard, None)
    assert said["source"] == "Ruth · Read by Shmuel · CC BY-SA 4.0"
    assert anki_send.recording_may_leave(heard)
    assert not anki_send.recording_may_leave(
        anki_send.Heard(Path("/r.mp3"), 1.0, 3.0, "Read by X", "CC BY-NC-ND 4.0")
    )
    assert anki_send.recording_may_leave(anki_send.Heard(Path("/r.mp3"), 1.0, 3.0))


def test_the_hash_moves_with_what_targum_writes() -> None:
    line = {"before": "אל ה", "gap": "בית", "after": "", "translation": "home", "title": "T"}
    row = {"lemma": "בית", "status": 2, "surface": "בית", "meaning": "house", "note": ""}

    def stamp(**changes: Any) -> str:
        one = dict(row, **{k: v for k, v in changes.items() if k in row})
        said_line = changes.get("line", line)
        return str(anki_send.note(one, "he", said_line, None, None)["hash"])

    base = stamp()
    assert stamp() == base
    assert stamp(meaning="home") != base
    assert stamp(status=3) != base
    assert stamp(line=dict(line, before="על ה")) != base
    assert stamp(line=None) != base
    assert stamp(surface="הבית") == base, "the line's word is the face, not the surface"


def test_the_notes_answer_names_no_file_on_this_disk(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, out = served
    folder = text(out / "shared" / "one", {1: [("הילד הלך אל הבית", [w("בית", "בית")])]},
                  content_hash="one")  # fmt: skip
    recorded(folder, {"s1-0": [1.0, 3.5]})
    cookie = sign_in(port, postbox)
    keep(port, token, cookie, [("בית", 2)], [("one", 1, ms(2026, 9))])
    said = notes(port, token, cookie)
    assert str(out) not in str(said) and "part-001" not in str(said)
