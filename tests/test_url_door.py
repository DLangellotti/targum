"""The fetch door: a browser's handshake, a way out when refused, and manners.

Nothing here touches the network. `_session` is the seam: every test hands the door a
fake client that answers from a script, so what is pinned is the door's own conduct —
which knocks it makes, in what order, through which exit, and what it says when refused.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from targum import level
from targum.accounts import Store
from targum.chat import tools
from targum.errors import TargumError, Unreachable
from targum.ingest import url as door


class Answer:
    """One scripted response, shaped like the client's."""

    def __init__(
        self,
        status: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        charset: str | None = None,
    ) -> None:
        self.status_code = status
        self._headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.charset = charset
        self.encoding = None
        self.closed = False

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    def iter_content(self, chunk_size: int | None = None) -> Any:
        yield self._body

    def close(self) -> None:
        self.closed = True


class Client:
    """A scripted client. Records every knock, and which exit it was made from."""

    def __init__(self, script: list[Answer], proxy: str = "") -> None:
        self.script = list(script)
        self.proxy = proxy
        self.knocks: list[dict[str, Any]] = []

    def get(self, url: str, **kw: Any) -> Answer:
        self.knocks.append({"url": url, "proxy": self.proxy, **kw})
        if not self.script:
            raise AssertionError(f"unscripted knock on {url}")
        answer = self.script.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Doors:
    """Hands out clients per exit, so a test can see the direct one and the proxied one."""

    def __init__(self, direct: list[Any], proxied: list[Any] | None = None) -> None:
        self.direct = Client(direct)
        self.proxied = Client(proxied or [], proxy="set-later")
        self.made: list[str] = []

    def __call__(self, proxy: str = "") -> Client:
        self.made.append(proxy)
        if proxy:
            self.proxied.proxy = proxy
            return self.proxied
        return self.direct


@pytest.fixture(autouse=True)
def _no_dns_no_waiting(monkeypatch: Any) -> None:
    """Fake hosts do not resolve and a test does not wait a second and a half."""
    monkeypatch.setattr(door, "POLITE_S", 0.0)
    monkeypatch.setattr(door, "_reachable", lambda url: None)
    monkeypatch.delenv(door.FETCH_PROXY_ENV, raising=False)
    monkeypatch.delenv("TARGUM_YTDLP_PROXY", raising=False)


def test_a_page_is_fetched_as_a_browser_and_says_so(monkeypatch: Any) -> None:
    doors = Doors([Answer(200, {"content-type": "text/html"}, "<p>שלום</p>".encode())])
    monkeypatch.setattr(door, "_session", doors)
    got = door.fetch("https://site.example/a")
    assert got.text == "<p>שלום</p>" and got.is_html and got.via == "direct"
    (knock,) = doors.direct.knocks
    assert knock["impersonate"] == door.BROWSER, "the handshake is a browser's"
    assert knock["allow_redirects"] is False, "redirects are walked by hand, past the guard"
    assert knock["stream"] is True
    assert "headers" not in knock, "the client sends the User-Agent that matches its handshake"
    assert doors.made == [""], "no proxy was asked for"


def test_redirects_are_walked_by_hand_and_every_hop_is_checked(monkeypatch: Any) -> None:
    hops: list[str] = []
    monkeypatch.setattr(door, "_reachable", hops.append)
    doors = Doors(
        [
            Answer(302, {"location": "/b"}),
            Answer(301, {"location": "https://other.example/c"}),
            Answer(200, body=b"ok"),
        ]
    )
    monkeypatch.setattr(door, "_session", doors)
    assert door.fetch("https://site.example/a").text == "ok"
    assert hops == ["https://site.example/a", "https://site.example/b", "https://other.example/c"]


def test_a_bot_check_is_named_as_one_and_is_a_shut_door(monkeypatch: Any) -> None:
    """Cloudflare answers a non-browser with `cf-mitigated: challenge` and a 403. Told
    apart from a host that never answered, because a reader's browser passes it."""
    doors = Doors([Answer(403, {"cf-mitigated": "challenge", "server": "cloudflare"})])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(Unreachable) as caught:
        door.fetch("https://site.example/a")
    error = caught.value
    assert error.status == 403 and error.challenge is True and error.via == "direct"
    assert error.host == "site.example"
    assert door.shut(error)
    assert "bot check" in (error.hint or "")


def test_a_sign_in_wall_is_named_and_says_to_paste_the_text(monkeypatch: Any) -> None:
    """targum-internal#252: a refusal says what to do instead. A 401 means exactly one
    thing — the page wants an account — and the way in is the reader's own hands, so here
    the hint is a sentence rather than a status code.

    `site` rather than `host` in the blanks: `Unreachable` takes `host` as a field of its
    own, so it never reaches `fill`, and a translation naming `{host}` would fall back to
    English without saying so.
    """
    doors = Doors([Answer(401, {"www-authenticate": "Basic"})])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(Unreachable) as caught:
        door.fetch("https://paywall.example/a")
    error = caught.value
    assert error.key == "fetch.needs-a-sign-in"
    assert error.fill == {"site": "paywall.example"}
    assert "sign in" in error.message
    assert "paste the text" in (error.hint or "")
    # What Unreachable is for is untouched: still a shut door, with its status.
    assert error.status == 401 and error.host == "paywall.example" and door.shut(error)


def test_a_403_is_not_called_a_sign_in_wall(monkeypatch: Any) -> None:
    """403 is what a geo-block, a permissions rule and a bot check all answer with — and
    what an Israeli site returns to any address outside Israel (measured 2026-09-07). So
    only 401 is named as a sign-in wall: telling a blocked reader to sign in would send
    them after a door that is not there."""
    doors = Doors([Answer(403)])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(Unreachable) as caught:
        door.fetch("https://blocked.example/a")
    assert caught.value.key == "fetch.would-not-open"
    assert caught.value.hint == "HTTP 403"


def test_a_refused_knock_is_retried_once_through_the_proxy(monkeypatch: Any) -> None:
    monkeypatch.setenv(door.FETCH_PROXY_ENV, "http://u:p@exit.example:823")
    doors = Doors(
        direct=[Answer(403, {"cf-mitigated": "challenge"})],
        proxied=[Answer(200, {"content-type": "text/html"}, b"<p>hi</p>")],
    )
    monkeypatch.setattr(door, "_session", doors)
    got = door.fetch("https://site.example/a")
    assert got.text == "<p>hi</p>" and got.via == "proxy"
    assert doors.made == ["", "http://u:p@exit.example:823"], "direct first, then the proxy"
    assert doors.proxied.proxy == "http://u:p@exit.example:823"


def test_plain_http_is_never_retried_through_the_proxy(monkeypatch: Any) -> None:
    """Without TLS end to end, a hostile exit could serve anything for any address."""
    monkeypatch.setenv(door.FETCH_PROXY_ENV, "http://u:p@exit.example:823")
    doors = Doors(direct=[Answer(403)], proxied=[Answer(200, body=b"never")])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(Unreachable) as caught:
        door.fetch("http://site.example/a")
    assert caught.value.via == "direct"
    assert doors.made == [""], "the proxy was never asked for"


def test_a_missing_page_is_not_a_shut_door_and_is_not_retried(monkeypatch: Any) -> None:
    monkeypatch.setenv(door.FETCH_PROXY_ENV, "http://u:p@exit.example:823")
    doors = Doors(direct=[Answer(404)], proxied=[Answer(200, body=b"never")])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(Unreachable) as caught:
        door.fetch("https://site.example/gone")
    assert caught.value.status == 404 and not door.shut(caught.value)
    assert doors.made == [""]


def test_a_proxy_that_is_also_refused_says_it_was_the_proxy(monkeypatch: Any) -> None:
    monkeypatch.setenv(door.FETCH_PROXY_ENV, "http://u:p@exit.example:823")
    doors = Doors(direct=[Answer(403)], proxied=[Answer(403, {"cf-mitigated": "challenge"})])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(Unreachable) as caught:
        door.fetch("https://site.example/a")
    assert caught.value.via == "proxy" and caught.value.challenge is True
    assert doors.made == ["", "http://u:p@exit.example:823"], "once, not again"


def test_no_answer_at_all_is_a_shut_door_with_no_status(monkeypatch: Any) -> None:
    doors = Doors([TimeoutError("timed out")])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(Unreachable) as caught:
        door.fetch("https://site.example/a")
    assert caught.value.status is None and door.shut(caught.value)


def test_the_fetch_proxy_wins_over_the_youtube_one_and_absent_means_nowhere(
    monkeypatch: Any,
) -> None:
    assert door.egress() == ""
    monkeypatch.setenv("TARGUM_YTDLP_PROXY", "http://yt.example:1")
    assert door.egress() == "http://yt.example:1", "one proxy, one knob"
    monkeypatch.setenv(door.FETCH_PROXY_ENV, "http://articles.example:2")
    assert door.egress() == "http://articles.example:2", "articles may take their own exit"


def test_a_private_address_is_refused_before_any_knock(monkeypatch: Any) -> None:
    monkeypatch.undo()  # the real `_reachable`, which is the point
    doors = Doors([Answer(200, body=b"never")])
    monkeypatch.setattr(door, "_session", doors)
    monkeypatch.setattr(door, "POLITE_S", 0.0)
    with pytest.raises(TargumError) as caught:
        door.fetch("https://127.0.0.1/metadata")
    assert "private network" in caught.value.message
    assert doors.direct.knocks == [], "refused at our end, never sent"
    assert not isinstance(caught.value, Unreachable), "so it is never recorded as a shut door"


def test_two_knocks_on_one_host_wait_and_on_two_hosts_do_not(monkeypatch: Any) -> None:
    monkeypatch.setattr(door, "POLITE_S", 5.0)
    monkeypatch.setattr(door, "_last_knock", {})
    slept: list[float] = []
    monkeypatch.setattr(door.time, "sleep", slept.append)
    clock = iter([100.0, 100.0, 100.0, 100.0, 101.0, 101.0])
    monkeypatch.setattr(door.time, "monotonic", lambda: next(clock))
    door._polite("a.example")
    door._polite("b.example")
    door._polite("a.example")
    assert slept == [pytest.approx(4.0)], "only the second knock on the same host waits"


def test_the_size_cap_still_holds(monkeypatch: Any) -> None:
    doors = Doors([Answer(200, {"content-length": str(door.MAX_BYTES + 1)})])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(TargumError, match="too big"):
        door.fetch("https://site.example/huge")


def test_a_recording_is_pulled_to_disk_and_retried_the_same_way(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setenv(door.FETCH_PROXY_ENV, "http://u:p@exit.example:823")
    doors = Doors(
        direct=[Answer(403)],
        proxied=[Answer(200, {"content-type": "audio/mpeg"}, b"\x00" * 10)],
    )
    monkeypatch.setattr(door, "_session", doors)
    got = door.download("https://site.example/ep.mp3", tmp_path / "ep.mp3")
    assert got.path.read_bytes() == b"\x00" * 10 and got.via == "proxy"
    assert got.content_type == "audio/mpeg" and got.final_url == "https://site.example/ep.mp3"


def test_a_refused_recording_leaves_nothing_on_disk(monkeypatch: Any, tmp_path: Path) -> None:
    doors = Doors([Answer(403)])
    monkeypatch.setattr(door, "_session", doors)
    with pytest.raises(Unreachable):
        door.download("https://site.example/ep.mp3", tmp_path / "ep.mp3")
    assert not (tmp_path / "ep.mp3").exists()


# -- what the record keeps --------------------------------------------------------------


def test_the_memory_of_a_door_says_which_way_out_it_went(tmp_path: Path) -> None:
    store = Store(tmp_path / "t.db")
    store.reach("a.example", False, "bot check", egress="direct")
    store.reach("a.example", True, egress="proxy")
    row = store.db.execute(
        "SELECT open, egress, tries FROM reached WHERE host='a.example'"
    ).fetchone()
    assert (row["open"], row["egress"], row["tries"]) == (1, "proxy", 2)
    assert store.closed() == []


def test_a_database_from_before_the_column_gains_it_on_open(tmp_path: Path) -> None:
    """`reached` was a new table at 14 and needed no migration; a column on it does."""
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE reached (host TEXT NOT NULL PRIMARY KEY, open INTEGER NOT NULL DEFAULT 0,"
        " why TEXT NOT NULL DEFAULT '', tries INTEGER NOT NULL DEFAULT 0,"
        " first INTEGER NOT NULL DEFAULT 0, last INTEGER NOT NULL DEFAULT 0);"
        "INSERT INTO reached (host, open) VALUES ('old.example', 0);"
        "PRAGMA user_version = 14;"
    )
    raw.close()
    store = Store(path)
    columns = {row["name"] for row in store.db.execute("PRAGMA table_info(reached)")}
    assert "egress" in columns
    row = store.db.execute("SELECT egress FROM reached WHERE host='old.example'").fetchone()
    assert row["egress"] == "direct", "what every row written before the column meant"
    from targum.accounts import SCHEMA_VERSION

    assert store.db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_a_bot_check_is_said_as_one_to_the_model(tmp_path: Path) -> None:
    store = Store(tmp_path / "t.db")
    ctx = tools.Ctx(
        person=None, home=tmp_path, library=None, store=store, chat_id="c", level=level.EMPTY
    )
    told = tools.refused(
        ctx, "site.example", Unreachable("no", status=403, host="site.example", challenge=True)
    )
    assert told is not None and told["host_shut"] and told["challenge"]
    assert "bot check" in told["error"] and "own browser" in told["error"]
    row = store.db.execute("SELECT why, egress FROM reached WHERE host='site.example'").fetchone()
    assert (row["why"], row["egress"]) == ("bot check", "direct")


def test_a_door_opened_through_the_proxy_is_remembered_as_such(tmp_path: Path) -> None:
    store = Store(tmp_path / "t.db")
    ctx = tools.Ctx(
        person=None, home=tmp_path, library=None, store=store, chat_id="c", level=level.EMPTY
    )
    told = tools.refused(
        ctx, "site.example", Unreachable("no", status=403, host="site.example", via="proxy")
    )
    assert told is not None and "does not answer" in told["error"]
    row = store.db.execute("SELECT egress FROM reached WHERE host='site.example'").fetchone()
    assert row["egress"] == "proxy"


# -- the deploy-time knock ---------------------------------------------------------------


def test_preflight_is_silent_with_no_exit_and_never_prints_a_credential(monkeypatch: Any) -> None:
    from targum import preflight

    monkeypatch.delenv(door.FETCH_PROXY_ENV, raising=False)
    monkeypatch.delenv("TARGUM_YTDLP_PROXY", raising=False)
    quiet = preflight.check_fetch_egress(connect=False)
    assert quiet.ok and "not retried" in str(vars(quiet))

    monkeypatch.setenv(door.FETCH_PROXY_ENV, "http://user:s3cret@127.0.0.1:9")
    loud = preflight.check_fetch_egress(connect=True)
    assert not loud.ok, "set and not listening is the loud case"
    assert "s3cret" not in str(vars(loud)) and "user:" not in str(vars(loud))
    assert "127.0.0.1:9" in str(vars(loud))


# -- the front of a file, without the file (targum-internal#256) ----------------------


class Streamed(Answer):
    """A response whose body arrives in pieces, so a test can see where reading stopped."""

    def __init__(self, headers: dict[str, str], chunks: list[bytes]) -> None:
        super().__init__(200, headers, b"".join(chunks))
        self.chunks = chunks
        self.given = 0

    def iter_content(self, chunk_size: int | None = None) -> Any:
        for chunk in self.chunks:
            self.given += len(chunk)
            yield chunk


def test_the_front_of_a_file_is_read_and_the_rest_is_never_pulled(monkeypatch: Any) -> None:
    """A reader pastes a direct link to an hour of audio; the page should be able to say
    what it is without a gigabyte moving. The connection is closed as soon as enough has
    been read, so a server that would have streamed the rest never does."""
    answer = Streamed(
        {"content-type": "audio/mpeg", "content-length": "60000000"},
        [b"x" * 512, b"y" * 512, b"z" * 512],
    )
    doors = Doors([answer])
    monkeypatch.setattr(door, "_session", doors)

    front = door.opening("https://example.com/talk.mp3", most=1024)

    assert front.content_type == "audio/mpeg"
    assert front.length == 60_000_000, "what the whole file weighs, from the header"
    assert len(front.head) == 1024, "no more than was asked for"
    assert answer.given == 1024, "and the third piece was never taken"
    assert answer.closed, "the connection is let go"


def test_a_host_that_will_not_say_how_big_a_file_is_is_still_opened(monkeypatch: Any) -> None:
    doors = Doors([Answer(200, {"content-type": "audio/mpeg"}, b"short")])
    monkeypatch.setattr(door, "_session", doors)

    front = door.opening("https://example.com/talk.mp3")
    assert front.length == 0 and front.head == b"short"


def test_opening_a_file_goes_through_the_proxy_when_the_direct_knock_is_refused(
    monkeypatch: Any,
) -> None:
    """The same fallback every fetch has: direct first, and the proxy only after a
    refusal — so a link that works direct never leaves through a metered exit."""
    doors = Doors(
        [Unreachable("refused", "")],
        [Answer(200, {"content-type": "audio/mpeg", "content-length": "9"}, b"123456789")],
    )
    monkeypatch.setattr(door, "_session", doors)
    monkeypatch.setenv(door.FETCH_PROXY_ENV, "http://proxy.example:8080")

    front = door.opening("https://example.com/talk.mp3")
    assert front.length == 9 and doors.made == ["", "http://proxy.example:8080"]


def test_a_truncated_file_s_own_duration_is_never_taken(monkeypatch: Any) -> None:
    """The trap this is built around. ffprobe hands back the length of whatever it was
    given, so the front of an hour-long recording reads as four seconds — confidently,
    with nothing to say anything is missing. The bit rate against the declared size is
    the honest answer instead (targum-internal#256)."""
    from targum.audio import probe
    from targum.audio import tools as audio_tools

    # 128 kbit/s, and a front that is 4 seconds of a 60-minute file.
    monkeypatch.setattr(
        audio_tools,
        "ffprobe_json",
        lambda path: {"format": {"duration": "4.0", "bit_rate": "128000", "size": "64000"}},
    )
    whole = 128_000 // 8 * 3600
    assert round(probe.timed(b"front", whole)) == 3600, "the whole file, not the front"


def test_a_front_that_held_the_whole_file_is_read_as_it_is(monkeypatch: Any) -> None:
    """Where the container puts its index first and the file is small enough to have
    arrived entire, ffprobe's own duration is the answer."""
    from targum.audio import probe
    from targum.audio import tools as audio_tools

    monkeypatch.setattr(
        audio_tools,
        "ffprobe_json",
        lambda path: {"format": {"duration": "12.5", "bit_rate": "64000", "size": "100000"}},
    )
    assert probe.timed(b"front", 100_000) == 12.5


def test_a_length_that_cannot_be_had_is_nothing_rather_than_a_guess(monkeypatch: Any) -> None:
    """No ffprobe, an unreadable front, or a host that would not say how big the file is:
    a recording of unknown length is still a recording, and 0 says so."""
    from targum.audio import probe
    from targum.audio import tools as audio_tools
    from targum.errors import TargumError

    monkeypatch.setattr(
        audio_tools, "ffprobe_json", lambda path: {"format": {"bit_rate": "128000"}}
    )
    assert probe.timed(b"front", 0) == 0.0, "nothing said how big it is"

    def unreadable(path: object) -> dict[str, Any]:
        raise TargumError("unreadable")

    monkeypatch.setattr(audio_tools, "ffprobe_json", unreadable)
    assert probe.timed(b"front", 5_000_000) == 0.0
    assert probe.timed(b"", 5_000_000) == 0.0, "nothing was read"


def test_a_bit_rate_on_the_stream_rather_than_the_format_is_still_a_bit_rate(
    monkeypatch: Any,
) -> None:
    """Some containers declare it per stream and not for the file."""
    from targum.audio import probe
    from targum.audio import tools as audio_tools

    monkeypatch.setattr(
        audio_tools,
        "ffprobe_json",
        lambda path: {"format": {"size": "1000"}, "streams": [{"bit_rate": "8000"}]},
    )
    assert probe.timed(b"front", 8_000) == 8.0
