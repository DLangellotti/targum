"""A Russian weekly every issue (David, 2026-09-27, targum-internal#288).

The same Hebrew, built a second time with Russian beside it, into folders of its own;
recorded on the issue only once every level has it; served to a Russian page where it
finished and never where it did not; and mailed to whoever asked in Russian, in Russian.

Nothing here spends: the build is a stand-in, and no model is asked for anything.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum import serve
from targum.accounts import Store
from targum.weekly import index as weekly_index
from targum.weekly.mailout import announce, letter
from targum.weekly.models import (
    LEVELS,
    Edition,
    Index,
    Issue,
    Level,
    State,
    entry_id,
    folder,
    label_in,
)

FIXTURES = Path(__file__).parent / "fixtures"
PUBLIC = "https://targum.page"
HOST = "targum.page"
WEEK = "2026-w36"


def _issue(week: str = WEEK, languages: list[str] | None = None) -> Issue:
    return Issue(
        id=week,
        dated="2026-08-31",
        title="השבוע בעברית",
        state=State.published,
        editions=[
            Edition(
                level=level, entry_id=entry_id(week, level), folder=folder(week, level), ok=True
            )
            for level in Level
        ],
        languages=languages or ["en"],
    )


def _stub(root: Path, week: str, level: Level, language: str = "en", mark: str = "") -> None:
    reader = root / folder(week, level, language) / "reader"
    reader.mkdir(parents=True, exist_ok=True)
    (reader / "index.html").write_text(f"<!doctype html>{mark}", encoding="utf-8")


@pytest.fixture
def weekly_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_index, "_cached", None)
    return tmp_path


# -- what an edition in another language is called -----------------------------------


def test_english_keeps_the_folder_it_always_had() -> None:
    """Every issue already on the box is addressed by this name, and so is the private
    half's `Edition(folder=...)`."""
    assert folder(WEEK, Level.bet) == "weekly-2026-w36-bet-he"
    assert folder(WEEK, Level.bet, "en") == "weekly-2026-w36-bet-he"


def test_another_language_is_a_folder_of_its_own() -> None:
    """Not the English folder with a second translation in it: a reader is drawn in its
    first translation's language, so one folder would be Russian for everybody."""
    assert folder(WEEK, Level.bet, "ru") == "weekly-2026-w36-bet-he-ru"
    # The rule ship-weekly.sh applies without importing targum.
    assert folder(WEEK, Level.gimel, "ru") == folder(WEEK, Level.gimel) + "-ru"


def test_a_level_is_named_in_the_readers_language() -> None:
    assert label_in(Level.aleph, "en") == LEVELS[Level.aleph].label == "Easy · 1,000 words"
    russian = label_in(Level.aleph, "ru")
    assert russian.startswith("Лёгкий · ")
    # A comma in a Russian thousand reads as a decimal point.
    assert "1\u00a0000 слов" in russian and "," not in russian
    assert label_in(Level.gimel, "ru").endswith("5\u00a0000+ слов")


def test_an_issue_written_before_this_was_english_alone() -> None:
    old = Issue.model_validate({"id": WEEK, "dated": "2026-08-31", "title": "x"})
    assert old.languages == ["en"]


# -- finished, or not offered ----------------------------------------------------------


def test_a_language_is_spoken_only_when_listed_and_on_disk(weekly_dir: Path) -> None:
    listed = _issue(languages=["en", "ru"])
    for level in Level:
        _stub(weekly_dir, WEEK, level)
    # Listed, but the Russian never arrived: English, not a 404.
    assert not weekly_index.speaks(listed, "ru")
    assert weekly_index.reading_in(listed, "ru") == "en"

    for level in Level:
        _stub(weekly_dir, WEEK, level, "ru")
    assert weekly_index.speaks(listed, "ru")
    assert weekly_index.reading_in(listed, "ru-RU") == "ru"
    assert weekly_index.reading_in(listed, "fr") == "en"

    # On disk, but never listed: a build that stopped on its third level.
    unlisted = _issue()
    assert not weekly_index.speaks(unlisted, "ru")


def test_only_a_finished_language_can_be_fetched(weekly_dir: Path) -> None:
    weekly_index.save(Index(issues=[_issue(languages=["en", "ru"]), _issue("2026-w35")]))
    weekly_index._cached = None
    for week in (WEEK, "2026-w35"):
        for level in Level:
            _stub(weekly_dir, week, level)
            _stub(weekly_dir, week, level, "ru")
    served = weekly_index.servable()
    assert folder(WEEK, Level.bet, "ru") in served
    assert folder(WEEK, Level.bet) in served
    assert folder("2026-w35", Level.bet) in served
    assert folder("2026-w35", Level.bet, "ru") not in served, "built but never listed"


# -- building it -------------------------------------------------------------------------


class StandIn:
    """A `Build` that spends nothing: it writes the reader a real build would, and
    remembers what it was asked for."""

    made: list[dict[str, Any]] = []
    refuse: Level | None = None

    def __init__(self, **asked: Any) -> None:
        self.asked = asked
        StandIn.made.append(asked)

    def run(self) -> Any:
        if StandIn.refuse is not None and self.asked["source"].endswith(StandIn.refuse.value):
            raise RuntimeError("the translation stopped")
        out: Path = self.asked["out"]
        (out / "reader").mkdir(parents=True, exist_ok=True)
        (out / "reader" / "index.html").write_text("<!doctype html>", encoding="utf-8")
        return SimpleNamespace(out_dir=out)


@pytest.fixture
def stand_in(monkeypatch: pytest.MonkeyPatch) -> type[StandIn]:
    import targum.pipeline

    StandIn.made = []
    StandIn.refuse = None
    monkeypatch.setattr(targum.pipeline, "Build", StandIn)
    return StandIn


def test_a_russian_build_goes_beside_the_english_and_is_recorded(
    weekly_dir: Path, stand_in: type[StandIn]
) -> None:
    from targum.cli import weekly_build

    drafted = _issue()
    drafted.state = State.draft
    weekly_index.save(Index(issues=[drafted]))
    weekly_index._cached = None

    weekly_build(WEEK, out=None, to="ru")

    outs = [asked["out"].name for asked in stand_in.made]
    assert outs == [folder(WEEK, level, "ru") for level in Level]
    assert all(asked["target_language"] == "ru" for asked in stand_in.made)
    # The level switch inside the reader, in the reader's language and pointing at the
    # Russian siblings rather than at the English ones.
    switch = stand_in.made[0]["siblings"]
    assert [one["name"] for one in switch] == ["Лёгкий", "Упрощённый", "Оригинал"]
    assert switch[0]["figure"] == "1\u00a0000 слов"
    assert all(one["folder"].endswith("-he-ru") for one in switch)

    weekly_index._cached = None
    recorded = weekly_index.by_week(WEEK)
    assert recorded is not None and recorded.languages == ["en", "ru"]
    assert recorded.state is State.draft, "a translation publishes nothing"


def test_the_english_build_is_what_it_was(weekly_dir: Path, stand_in: type[StandIn]) -> None:
    from targum.cli import weekly_build

    weekly_index.save(Index(issues=[_issue()]))
    weekly_index._cached = None
    weekly_build(WEEK, out=None, to="en")
    assert [asked["out"].name for asked in stand_in.made] == [
        folder(WEEK, level) for level in Level
    ]
    assert [one["name"] for one in stand_in.made[0]["siblings"]] == [
        "Easy",
        "Simplified",
        "Native",
    ]
    assert stand_in.made[0]["siblings"][0]["figure"] == "1,000 words"
    weekly_index._cached = None
    found = weekly_index.by_week(WEEK)
    assert found is not None and found.languages == ["en"]


def test_a_russian_build_that_stops_is_not_recorded(
    weekly_dir: Path, stand_in: type[StandIn]
) -> None:
    """Two levels built and the third refused: nothing may offer a Russian issue whose
    level switch leads to a folder that is not there."""
    from targum.cli import weekly_build

    weekly_index.save(Index(issues=[_issue()]))
    weekly_index._cached = None
    stand_in.refuse = Level.gimel
    with pytest.raises(RuntimeError):
        weekly_build(WEEK, out=None, to="ru")
    weekly_index._cached = None
    found = weekly_index.by_week(WEEK)
    assert found is not None and found.languages == ["en"]
    assert found.state is State.published, "the English issue is untouched"


# -- the run and the ship ----------------------------------------------------------------


ROOT = Path(__file__).resolve().parent.parent


def test_the_run_builds_russian_after_publish_and_never_waves_it_through() -> None:
    script = (ROOT / "deploy" / "weekly-run.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
    assert "--anyway" not in code
    publish = code.index('"$TARGUM" weekly publish')
    russian = code.index('weekly build "$WEEK" --to "$language"')
    announce_at = code.index("targum weekly announce")
    assert publish < russian < announce_at, "guards first, then Russian, then the mail"
    # A Russian that stops is carried to the end, not fatal where it happens.
    tail = code[russian : russian + 400]
    assert "die" not in tail.split("done", 1)[0]
    assert 'MISSING="$MISSING $language"' in code


def test_the_ship_carries_every_listed_language(tmp_path: Path) -> None:
    """The folder list, run the way ship-weekly.sh runs it: the index alone, no targum."""
    import re
    import subprocess

    script = (ROOT / "deploy" / "ship-weekly.sh").read_text(encoding="utf-8")
    program = re.search(r"python3 - <<'PY'\n(.*?)\nPY", script, re.S)
    assert program is not None
    index = tmp_path / "index.json"
    listed = _issue(languages=["en", "ru"])
    index.write_text(Index(issues=[listed, _issue("2026-w35")]).model_dump_json())

    def folders(week: str) -> list[str]:
        return subprocess.run(
            ["python3", "-c", program.group(1)],
            env={"WEEK": week, "INDEX": str(index)},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()

    assert folders(WEEK) == [
        name for level in Level for name in (folder(WEEK, level), folder(WEEK, level, "ru"))
    ]
    assert folders("2026-w35") == [folder("2026-w35", level) for level in Level]


# -- the subscriber's language -------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def test_a_subscriber_keeps_the_language_they_asked_in(store: Store) -> None:
    token = store.subscribe("ru@example.com", "ru-RU")
    assert token is not None
    assert store.subscription_language(token) == "ru"
    store.confirm_subscription(token)
    store.follow("en@example.com")
    store.follow("signed-in@example.com", language="ru")
    said = {email: language for email, _, language in store.subscribers(not_sent=WEEK)}
    assert said == {"ru@example.com": "ru", "en@example.com": "en", "signed-in@example.com": "ru"}
    assert store.subscription_language("made-up") == "en"


def test_a_database_from_before_gains_the_column(tmp_path: Path) -> None:
    """The subscriber table is on every box already, so the column is a migration and
    every row before it reads as English."""
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE subscriber (email TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT "
        "'pending', confirm TEXT, stop TEXT NOT NULL, asked INTEGER NOT NULL, joined "
        "INTEGER NOT NULL DEFAULT 0, ended INTEGER NOT NULL DEFAULT 0, sent INTEGER NOT "
        "NULL DEFAULT 0, issue TEXT NOT NULL DEFAULT '', bounces INTEGER NOT NULL DEFAULT 0)"
    )
    db.execute("INSERT INTO subscriber (email, state, stop, asked) VALUES ('a@b.c', 'on', 's', 1)")
    db.commit()
    db.close()
    store = Store(path)
    assert store.subscribers(not_sent=WEEK) == [("a@b.c", "s", "en")]


def test_a_russian_letter_is_russian_and_points_at_the_russian_edition() -> None:
    mail = letter(_issue(), PUBLIC, "tok", "ru")
    subject, body = mail.subject, mail.text
    assert subject.startswith("Недельный обзор новостей")
    assert "Лёгкий (1\u00a0000 слов)" in body
    assert f"{PUBLIC}/weekly/{WEEK}/aleph?lang=ru" in body
    assert "/weekly/stop?t=tok&lang=ru" in body
    assert "Easy" not in body and "Read this week" not in body


def test_an_english_letter_is_the_letter_it_was() -> None:
    mail = letter(_issue(), PUBLIC, "tok")
    subject, body = mail.subject, mail.text
    assert subject == "Weekly News Digest · Monday, August 31, 2026"
    assert "Easy (1,000 words)" in body
    assert "lang=" not in body
    assert f"Unsubscribe: {PUBLIC}/weekly/stop?t=tok\n" in body


def test_each_subscriber_is_written_to_in_their_own_language(store: Store) -> None:
    class Keeping:
        def __init__(self) -> None:
            self.sent: dict[str, str] = {}

        def send(self, to: str, link: str, language: str = "en") -> None: ...

        def notify(
            self, to: str, subject: str, body: str, headers: object = None, html: object = None
        ) -> None:
            self.sent[to] = subject

    store.follow("ru@example.com", language="ru")
    store.follow("en@example.com")
    mailer = Keeping()
    report = announce(store, mailer, _issue(), PUBLIC, pause=0)  # type: ignore[arg-type]
    assert sorted(report.sent) == ["en@example.com", "ru@example.com"]
    assert mailer.sent["ru@example.com"].startswith("Недельный обзор новостей")
    assert mailer.sent["en@example.com"].startswith("Weekly News Digest")


def test_a_russian_shelf_is_told_the_level_in_russian() -> None:
    from targum.weekly.entries import entries_for

    rows = {row.id: row for row in entries_for(_issue())}
    row = rows[entry_id(WEEK, Level.bet)]
    assert row.name_in("ru").startswith("Упрощённый · ")
    assert row.name_in("en") == "", "English already has it in the title"
    assert row.title.endswith("Simplified · 3,000 words"), "the title names the folder"


# -- the pages -------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def russian_server(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, Path, Path]:
    tmp = tmp_path_factory.mktemp("weekly-russian")
    out = tmp / "out"
    out.mkdir()
    shutil.copytree(FIXTURES / "weekly", out / "weekly")
    weekly = out / "weekly"
    listing = json.loads((weekly / "index.json").read_text(encoding="utf-8"))
    for issue in listing["issues"]:
        if issue["id"] == WEEK:
            issue["languages"] = ["en", "ru"]
    (weekly / "index.json").write_text(json.dumps(listing, ensure_ascii=False))
    for level in Level:
        _stub(weekly, WEEK, level, "ru", "RUSSIAN-EDITION")
        # Built for the week before and never listed: must not be served.
        _stub(weekly, "2026-w35", level, "ru", "UNLISTED")
    store_path = tmp / "targum.db"
    Store(store_path)
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=out,
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address=PUBLIC,
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        try:
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    return port, weekly, store_path


@pytest.fixture
def site(
    russian_server: tuple[int, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> tuple[int, Store]:
    port, weekly, store_path = russian_server
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(weekly))
    monkeypatch.setattr(weekly_index, "_cached", None)
    return port, Store(store_path)


def _ask(port: int, path: str, form: str | None = None) -> tuple[int, str, str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET" if form is None else "POST", path, skip_host=True)
    conn.putheader("Host", HOST)
    if form is not None:
        conn.putheader("Content-Type", "application/x-www-form-urlencoded")
        conn.putheader("Content-Length", str(len(form.encode())))
    conn.endheaders()
    if form is not None:
        conn.send(form.encode())
    response = conn.getresponse()
    body = response.read().decode("utf-8", "replace")
    where = response.getheader("Location") or ""
    conn.close()
    return response.status, body, where


def test_a_russian_page_frames_the_russian_edition(site: tuple[int, Store]) -> None:
    port, _ = site
    status, page, _ = _ask(port, f"/weekly/{WEEK}/bet?lang=ru")
    assert status == 200
    assert f"/weekly/read/{folder(WEEK, Level.bet, 'ru')}/reader/index.html" in page
    assert "Упрощённый · 3\u00a0000 слов" in page.split("</title>")[0]
    assert "5\u00a0000+ слов" in page, "the ladder writes a Russian thousand too"

    english = _ask(port, f"/weekly/{WEEK}/bet")[1]
    assert f"/weekly/read/{folder(WEEK, Level.bet)}/reader/index.html" in english


def test_an_issue_with_no_russian_frames_the_english(site: tuple[int, Store]) -> None:
    port, _ = site
    page = _ask(port, "/weekly/2026-w35/bet?lang=ru")[1]
    assert f"/weekly/read/{folder('2026-w35', Level.bet)}/reader/index.html" in page
    assert "-he-ru/" not in page


def test_the_russian_reader_is_served_and_an_unlisted_one_is_not(site: tuple[int, Store]) -> None:
    port, _ = site
    status, body, _ = _ask(port, f"/weekly/read/{folder(WEEK, Level.aleph, 'ru')}/reader/")
    assert status == 200 and "RUSSIAN-EDITION" in body
    assert _ask(port, f"/weekly/read/{folder('2026-w35', Level.aleph, 'ru')}/reader/")[0] == 404


def test_the_redirects_keep_the_language(site: tuple[int, Store]) -> None:
    port, _ = site
    assert _ask(port, "/weekly?lang=ru")[2] == f"/weekly/{WEEK}/bet?lang=ru"
    assert _ask(port, f"/weekly/{WEEK}?lang=ru")[2] == f"/weekly/{WEEK}/bet?lang=ru"
    assert _ask(port, "/weekly")[2] == f"/weekly/{WEEK}/bet"


def test_asking_in_russian_is_answered_and_remembered_in_russian(site: tuple[int, Store]) -> None:
    port, store = site
    status, page, _ = _ask(port, "/weekly/subscribe?lang=ru", "email=asks-ru@example.com")
    assert status == 200
    assert "Проверьте почту" in page and 'lang="ru"' in page
    row = store.db.execute(
        "SELECT language FROM subscriber WHERE email = ?", ("asks-ru@example.com",)
    ).fetchone()
    assert row["language"] == "ru"


def test_the_confirm_door_speaks_the_rows_language(site: tuple[int, Store]) -> None:
    port, store = site
    token = store.subscribe("confirm-ru@example.com", "ru")
    assert token is not None
    page = _ask(port, f"/weekly/confirm?t={token}")[1]
    assert "Присылать «Недельный обзор новостей» на confirm-ru@example.com" in page
    assert 'action="/weekly/confirm?lang=ru"' in page
    done = _ask(port, "/weekly/confirm?lang=ru", f"t={token}")[1]
    assert "каждый понедельник" in done
    assert store.following("confirm-ru@example.com")


def test_the_stop_door_says_the_same_for_a_real_token_and_a_made_up_one(
    site: tuple[int, Store],
) -> None:
    """Drawn in the row's language it would answer Russian for a real token and English
    for a fake one — which is whether an address is on the list, answered."""
    port, store = site
    store.follow("stop-ru@example.com", language="ru")
    real = store.db.execute(
        "SELECT stop FROM subscriber WHERE email = ?", ("stop-ru@example.com",)
    ).fetchone()["stop"]

    def page(token: str, lang: str = "") -> str:
        text = _ask(port, f"/weekly/stop?t={token}" + (f"&lang={lang}" if lang else ""))[1]
        return text.replace(token, "TOKEN")

    assert page(real) == page("made-up-token")
    assert "Больше не присылать" in page(real, "ru")
    assert page(real, "ru") == page("made-up-token", "ru")
    assert "Should we stop" in page(real)

    pressed = _ask(port, "/weekly/stop?lang=ru", f"t={real}")[1]
    fake = _ask(port, "/weekly/stop?lang=ru", "t=made-up-token")[1]
    assert pressed == fake and "больше не будем" in pressed
    assert not store.following("stop-ru@example.com")


def test_the_mail_goes_out_from_the_box_after_the_ship() -> None:
    """targum-internal#346, David 2026-09-27: the site's subscribers are rows in the box's
    database, and the laptop's announce never saw them. The mail is sent on the box, from
    the database the service serves, and only once the issue it links to is there."""
    script = (ROOT / "deploy" / "weekly-run.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
    assert '"$TARGUM" weekly announce' not in code, "never from the laptop's store"
    ship = code.index("./deploy/ship-weekly.sh")
    announce_at = code.index("targum weekly announce")
    assert ship < announce_at, "shipped first, so every letter's link is live"
    line = code[announce_at : announce_at + 120]
    assert "--store /var/lib/targum/targum.db" in line, "the service's database, named"
    assert "grep -q ship" in code, "a failed ship tells nobody"
