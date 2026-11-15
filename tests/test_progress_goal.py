"""A daily goal counts days, never a run (targum-internal#537; design.md §12, 2026-11-14).

A threshold the reader chose, laid over the record Your Progress already draws: the days
of the last 7 or 30 whose words read, or minutes listening, reached it. Stored as a
setting per language on the person and nothing else — no goal history and no "met" row —
so the page reads the same record again when the goal changes. Today is not judged, a
day under the goal is quiet, practice is not counted, and nothing is ever sent to the
reader because of it. `test_brand.py` is unchanged and still passes; what it cannot see
about this card is held here.

The page runs in the stub harness (`tests/js/progress.js`), as `test_progress_js.py`
runs the rest of the page; the browser half is `test_progress_goal_browser.py`.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import test_serve
from test_progress_js import _ago, _row, draw, vocab
from test_serve import Postbox, call, sign_in

from targum.accounts import SCHEMA_VERSION, Store

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "targum" / "render" / "assets"
STRINGS = ROOT / "src" / "targum" / "strings"

served = test_serve.served
postbox = test_serve.postbox

node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _store(tmp_path: Path) -> tuple[Store, Any]:
    store = Store(tmp_path / "targum.db")
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    return store, person


# --- the words: nothing that reads as a run, a debt or a miss -----------------------


BANNED = ("streak", "in a row", "missed", "to go", "left today", "don't break", "keep your")
BANNED_RU = ("подряд", "пропущ", "осталось", "серия")


def _goal_strings(code: str) -> dict[str, str]:
    said = json.loads((STRINGS / f"{code}.json").read_text(encoding="utf-8"))
    return {
        key: text
        for key, text in said.items()
        if key.startswith("progress.goal.") or key.startswith("reader.foot.goal-")
    }


def test_the_goal_says_nothing_of_runs_debts_or_misses() -> None:
    english = _goal_strings("en")
    russian = _goal_strings("ru")
    assert len(english) >= 20
    bases = {re.sub(r"\.(one|other)$", "", key) for key in english}
    assert bases <= {re.sub(r"\.(one|few|many|other)$", "", key) for key in russian}
    for key, text in english.items():
        for banned in BANNED:
            assert banned not in text.lower(), f"{key} says {banned!r}"
        assert "!" not in text
    for key, text in russian.items():
        for banned in BANNED_RU:
            assert banned not in text.lower(), f"ru {key} says {banned!r}"
        assert "!" not in text


def test_nothing_walks_back_from_today_and_practice_still_says_no_goal() -> None:
    """No function in `progress.js` counts consecutive days or the gap since the last met
    day, and the goal never reaches the practice card, the chat, the connector or a mail."""
    progress = (ASSETS / "progress.js").read_text(encoding="utf-8")
    for banned in (
        "function run(",
        "consecutive",
        "since the last",
        "function current(",
        "function gap(",
    ):
        assert banned not in progress, banned
    charts = (ASSETS / "charts.js").read_text(encoding="utf-8")
    assert "function current(" not in charts and "function gap(" not in charts
    assert "goal" not in (ASSETS / "lists.js").read_text(encoding="utf-8").lower()
    for name in (
        "mail.py",
        "mail_samples.py",
        "weekly/mailout.py",
        "chat/tools.py",
        "chat/session.py",
    ):
        source = (ROOT / "src" / "targum" / name).read_text(encoding="utf-8")
        assert (
            "goals(" not in source and "set_goal" not in source and "person.goal" not in source
        ), name
    for template in (ROOT / "src" / "targum" / "render" / "templates").glob("*mail*"):
        assert "goal" not in template.read_text(encoding="utf-8").lower(), template.name


def test_the_goal_moves_nothing() -> None:
    """Typography only: no motion on the goal's squares or its foot line, no bright leaf,
    and never clay."""
    css = re.sub(
        r"/\*.*?\*/", " ", (ASSETS / "progress.css").read_text(encoding="utf-8"), flags=re.S
    )
    for selector, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
        if "goal" in selector or ".day" in selector:
            assert "animation" not in body and "transition" not in body, selector.strip()
            assert "--leaf-bright" not in body and "--clay" not in body, selector.strip()
    assert ".progress .day.under { background: var(--step-2); }" in css
    reader = re.sub(
        r"/\*.*?\*/", " ", (ASSETS / "reader.css").read_text(encoding="utf-8"), flags=re.S
    )
    for selector, body in re.findall(r"([^{}]+)\{([^}]*)\}", reader):
        if "finished-goal" in selector:
            assert "animation" not in body and "transition" not in body
            assert "--leaf-bright" not in body


# --- the account --------------------------------------------------------------------


def test_a_goal_is_kept_per_language_and_off_the_steps_is_refused(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    assert store.goals(person.id) == {}, "off by default"
    assert store.set_goal(person, "he", "words", 250) == {"unit": "words", "amount": 250}
    assert store.set_goal(person, "ru", "minutes", 15) == {"unit": "minutes", "amount": 15}
    assert store.goals(person.id) == {
        "he": {"unit": "words", "amount": 250},
        "ru": {"unit": "minutes", "amount": 15},
    }
    store.set_goal(person, "he", "minutes", 30)
    assert store.goals(person.id)["he"] == {"unit": "minutes", "amount": 30}, "one unit at a time"
    assert store.goals(person.id)["ru"] == {"unit": "minutes", "amount": 15}, "the others stay"
    for unit, amount in (("words", 300), ("words", 5000), ("minutes", 7), ("pages", 10), ("", 100)):
        with pytest.raises(ValueError, match="No such choice."):
            store.set_goal(person, "he", unit, amount)
    with pytest.raises(ValueError):
        store.set_goal(person, "../he", "words", 100)
    with pytest.raises(ValueError, match="No such choice."):
        store.set_goal(person, "zz", "words", 100)
    assert store.set_goal(person, "he", "words", 0) == {}, "0 removes"
    assert store.goals(person.id) == {"ru": {"unit": "minutes", "amount": 15}}
    store.set_goal(person, "ru", "", 0)
    assert store.goals(person.id) == {}
    assert (
        store.db.execute("SELECT goal FROM person WHERE id = ?", (person.id,)).fetchone()[0] == ""
    )
    assert store.goals(None) == {}


def test_an_older_database_gains_the_column_with_no_goal_on_every_row(tmp_path: Path) -> None:
    """The ALTER runs whatever the stamp says, so it lands whichever schema merges first."""
    path = tmp_path / "old.db"
    store, person = _store(tmp_path)
    store.db.close()
    (tmp_path / "targum.db").rename(path)
    raw = sqlite3.connect(path)
    raw.executescript("ALTER TABLE person DROP COLUMN goal; PRAGMA user_version = 66;")
    raw.close()
    opened = Store(path)
    columns = {row["name"] for row in opened.db.execute("PRAGMA table_info(person)")}
    assert "goal" in columns
    assert [row[0] for row in opened.db.execute("SELECT goal FROM person")] == [""]
    assert opened.db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 68
    assert opened.goals(person.id) == {}


def test_the_export_carries_the_goal_and_leaving_takes_it(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    store.set_goal(person, "he", "words", 500)
    assert store.everything(person)["settings"]["goals"] == {"he": {"unit": "words", "amount": 500}}
    store.forget(person)
    assert store.purge(days=-1) == [person.id]
    assert (
        store.db.execute("SELECT COUNT(*) FROM person WHERE id = ?", (person.id,)).fetchone()[0]
        == 0
    )


def test_a_test_account_wiped_has_no_goal(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    store.make_test_account("trying@example.com")
    person, _ = store.finish_sign_in(store.start_sign_in("trying@example.com"))  # type: ignore[misc]
    store.set_goal(person, "he", "words", 100)
    store.wipe(person)
    assert store.goals(person.id) == {}


def test_the_goal_is_set_through_the_door_and_handed_back_with_the_totals(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, _ = served
    status, said, _ = call(
        port, "POST", f"/account/goal?k={token}", {"language": "he", "unit": "words", "amount": 250}
    )
    assert status == 401 and said == {"signedIn": False}
    cookie = sign_in(port, postbox)
    status, said, _ = call(
        port,
        "POST",
        f"/account/goal?k={token}",
        {"language": "he", "unit": "hours", "amount": 1},
        cookie=cookie,
    )
    assert status == 400 and said["error"] == "No such choice."
    status, said, _ = call(
        port,
        "POST",
        f"/account/goal?k={token}",
        {"language": "he", "unit": "words", "amount": 250},
        cookie=cookie,
    )
    assert status == 200 and said["goal"] == {"unit": "words", "amount": 250}
    status, said, _ = call(port, "GET", f"/account/totals?k={token}&tz=UTC", cookie=cookie)
    assert status == 200 and said["goals"] == {"he": {"unit": "words", "amount": 250}}
    # The reader's foot asks the goals alone, then the goals and the record, and never
    # the words of each day (qa on #1246).
    status, said, _ = call(port, "GET", f"/account/totals?k={token}&only=goals", cookie=cookie)
    assert status == 200 and said["goals"] == {"he": {"unit": "words", "amount": 250}}
    assert "words" not in said and "totals" not in said
    status, said, _ = call(port, "GET", f"/account/totals?k={token}&only=goal", cookie=cookie)
    assert status == 200 and "totals" in said and "words" not in said
    status, said, _ = call(
        port,
        "POST",
        f"/account/goal?k={token}",
        {"language": "xx", "unit": "words", "amount": 250},
        cookie=cookie,
    )
    assert status == 400, "only a language targum reads"
    status, said, _ = call(
        port,
        "POST",
        f"/account/goal?k={token}",
        {"language": "he", "unit": "words", "amount": 0},
        cookie=cookie,
    )
    assert status == 200 and said["goals"] == {}


# --- the page -----------------------------------------------------------------------


WORDS_250 = {"he": {"unit": "words", "amount": 250}}


def _effort(totals: list[dict[str, Any]], **options: Any) -> dict[str, Any]:
    stored = options.pop("stored", {"targum:vocab:he": vocab(known=3)})
    return draw(stored, totals=totals, **options)["effort"]


@node
def test_no_goal_is_the_days_block_as_it_was_and_one_quiet_link() -> None:
    drawn = _effort([_row(_ago(0), words=5)])
    assert drawn["days"]["title"] == "Days active · 1 of 30"
    assert drawn["days"]["kinds"][-1] == "day on"
    goal = drawn["goal"]
    assert goal["set"] and not goal["head"] and not goal["form"]


@node
def test_squares_carry_both_counts_and_the_sentence_says_both() -> None:
    """Leaf where the goal was met, the lighter step where the reader was active under it,
    resting where nothing; today under the goal is drawn like any day under it."""
    drawn = _effort(
        [
            _row(_ago(0), words=40),  # today, under: no half square, no "to go"
            _row(_ago(1), words=250),  # met exactly
            _row(_ago(2), words=100),
            _row(_ago(2), words=160, language="he"),  # two rows of one day add up
            _row(_ago(3), listened=3600),  # active, and words are the goal: under
            _row(_ago(9), words=900, language="ru"),  # another language's
            _row(_ago(40), words=999),  # outside the month
        ],
        goals=WORDS_250,
    )
    days = drawn["days"]
    assert days["title"] == "Days active · 4 of 30"
    assert drawn["goal"]["title"] == "Daily goal · 2 of 30"
    assert drawn["goal"]["said"] == "250 words read a day"
    assert days["label"] == (
        "You were active on 4 of the last 30 days, and reached your goal on 2 of them."
    )
    kinds = days["kinds"]
    assert kinds[-1] == "day under", "today is a day like any other"
    assert kinds[-2] == "day on" and kinds[-3] == "day on" and kinds[-4] == "day under"
    assert kinds.count("day") == 26
    assert set(kinds) == {"day", "day on", "day under"}
    assert drawn["goal"]["head"] and not drawn["goal"]["set"]
    assert sum(days["squares"]) == 2, "leaf is the goal met, not every active day"


@node
def test_a_week_counts_out_of_seven_and_all_time_draws_neither() -> None:
    rows = [_row(_ago(0), words=300), _row(_ago(8), words=300)]
    week = _effort(rows, goals=WORDS_250, period="7")
    assert week["goal"]["title"] == "Daily goal · 1 of 7"
    ever = _effort(rows, goals=WORDS_250, period="")
    assert ever["days"] is None and not ever["goal"]["head"] and not ever["goal"]["set"]


@node
def test_minutes_are_listening_and_watching_and_aramaic_reads_watching() -> None:
    rows = [_row(_ago(1), listened=400, watched=200), _row(_ago(2), listened=500)]
    drawn = _effort(rows, goals={"he": {"unit": "minutes", "amount": 10}})
    assert drawn["goal"]["title"] == "Daily goal · 1 of 30"
    assert drawn["goal"]["said"] == "10 minutes listening a day"
    arc = _effort(
        [_row(_ago(1), listened=900, language="arc"), _row(_ago(2), watched=600, language="arc")],
        stored={"targum:vocab:arc": vocab(known=3)},
        chosen="arc",
        goals={"arc": {"unit": "minutes", "amount": 10}},
    )
    assert arc["goal"]["title"] == "Daily goal · 1 of 30", "watched seconds only"
    assert arc["goal"]["said"] == "10 minutes watching a day"


@node
def test_recording_stopped_says_the_goal_and_counts_nothing() -> None:
    drawn = draw(
        {"targum:vocab:he": vocab(known=3)},
        totals=[_row(_ago(1), words=500)],
        record_off=True,
        goals=WORDS_250,
    )["effort"]
    assert drawn["off"]
    assert drawn["goal"]["head"] and drawn["goal"]["title"] == "", "said, never counted"
    assert drawn["goal"]["said"] == "250 words read a day"
    assert drawn["days"] is not None and not drawn["days"]["drawn"], "no squares"
    unset = draw(
        {"targum:vocab:he": vocab(known=3)}, totals=[_row(_ago(1), words=5)], record_off=True
    )["effort"]
    assert unset["goal"]["set"], "a goal can still be set"


@node
def test_setting_a_goal_reads_the_same_squares_again() -> None:
    rows = [_row(_ago(1), words=600), _row(_ago(2), words=300), _row(_ago(3), words=120)]
    drawn = _effort(rows, goal_steps=[["open"]])
    goal = drawn["goal"]
    assert goal["form"] and not goal["set"] and not goal["remove"]
    assert goal["unit"] == "words" and goal["steps"] == ["100", "250", "500", "1,000", "2,500"]
    assert goal["minutesLabel"] == "Minutes listening"
    saved = _effort(rows, goal_steps=[["open"], ["amount", "250"], ["save"]])
    assert saved["goal"]["posted"] == [{"language": "he", "unit": "words", "amount": 250}]
    assert not saved["goal"]["form"] and saved["goal"]["title"] == "Daily goal · 2 of 30"
    changed = _effort(rows, goals=WORDS_250, goal_steps=[["change"], ["amount", "100"], ["save"]])
    assert changed["goal"]["title"] == "Daily goal · 3 of 30", "the same record, read again"
    assert changed["days"]["title"] == "Days active · 3 of 30"
    minutes = _effort(rows, goal_steps=[["open"], ["unit", "minutes"]])
    assert minutes["goal"]["steps"] == ["5", "10", "15", "30", "60"]
    removed = _effort(rows, goals=WORDS_250, goal_steps=[["change"], ["remove"]])
    assert removed["goal"]["posted"][-1]["amount"] == 0
    assert removed["goal"]["set"] and not removed["goal"]["head"]
    assert removed["days"]["title"] == "Days active · 3 of 30"
    assert set(removed["days"]["kinds"]) == {"day", "day on"}


@node
def test_a_refused_goal_says_so_and_keeps_the_form() -> None:
    drawn = _effort([_row(_ago(1), words=5)], goal_steps=[["open"], ["save"]], goal_refused=True)
    assert drawn["goal"]["form"] and drawn["goal"]["refused"] == "No such choice."


def test_a_session_ended_mid_page_is_a_failed_save_not_a_refusal() -> None:
    drawn = _effort([_row(_ago(1), words=5)], goal_steps=[["open"], ["save"]], goal_signed_out=True)
    assert drawn["goal"]["form"] and drawn["goal"]["refused"] == "We couldn't save that. Try again."


def _russian() -> dict[str, Any]:
    from targum import strings

    said = {
        key: text
        for key, text in strings.catalogue("ru").items()
        if key.startswith(("progress.", "charts.", "lang."))
    }
    return {"strings": said, "language": "ru"}


@node
@pytest.mark.parametrize(
    ("amount", "said"),
    [
        (100, "100 прочитанных слов в день"),
        (1000, "1000 прочитанных слов в день"),
    ],
)
def test_russian_says_the_goal_with_its_own_plurals(amount: int, said: str) -> None:
    drawn = _effort(
        [_row(_ago(1), words=5000)],
        goals={"he": {"unit": "words", "amount": amount}},
        strings=_russian(),
    )
    plain = re.sub(r"[\s,\u00a0\u202f]", "", drawn["goal"]["said"])
    assert plain == said.replace(" ", "")
    assert drawn["goal"]["title"] == "Цель на день · 1 из 30"


@node
@pytest.mark.parametrize(
    ("minutes", "said"),
    [
        (5, "5 минут аудио и видео в день"),
        (15, "15 минут аудио и видео в день"),
        (30, "30 минут аудио и видео в день"),
    ],
)
def test_russian_minutes(minutes: int, said: str) -> None:
    drawn = _effort(
        [_row(_ago(1), listened=99999)],
        goals={"he": {"unit": "minutes", "amount": minutes}},
        strings=_russian(),
    )
    assert drawn["goal"]["said"] == said


def test_russian_plural_forms_at_1_3_5_and_21() -> None:
    """The steps never land on 1, 3 or 21, but the foot's count does: the forms are there."""
    from targum import strings

    ru = strings.catalogue("ru")
    cases = {1: "one", 3: "few", 5: "many", 21: "one"}
    for n, form in cases.items():
        assert strings.plural_form(n, "ru") == form
        for key in ("reader.foot.goal-words", "reader.foot.goal-minutes", "progress.goal.words"):
            assert f"{key}.{form}" in ru, f"{key}.{form}"
    assert (
        ru["reader.foot.goal-words.one"].format(n=21)
        == "Цель на сегодня выполнена: прочитано 21 слово."
    )
    assert (
        ru["reader.foot.goal-words.few"].format(n=3)
        == "Цель на сегодня выполнена: прочитано 3 слова."
    )
    assert (
        ru["reader.foot.goal-words.many"].format(n=5)
        == "Цель на сегодня выполнена: прочитано 5 слов."
    )


# --- the foot ------------------------------------------------------------------------


def test_the_foot_says_the_goal_once_a_day_and_only_good_news() -> None:
    """Decision 3: one line in the finished block, the day the goal is first met, kept in
    this browser by language so it is said once. Nothing on a day it is not met."""
    reader = (ASSETS / "reader.js").read_text(encoding="utf-8")
    start = reader.index("  function goalFoot() {")
    foot = reader[start : reader.index("\n  }\n", start)]
    assert "said[language] === today" in foot, "once a day"
    assert "if (sum < " in foot and "return;" in foot, "nothing on a day under the goal"
    for banned in ("to go", "left", "streak", "missed", "%", "score", "point", "level"):
        assert banned not in foot.lower(), banned
    assert "if (on) goalFoot();" in reader
    # Off the disk, signed out or with no goal it asks nothing and says nothing.
    assert "if (!served" in foot and "TargumSync.who" in foot and "if (!goal" in foot
    # The goals are asked alone first, and a finish with no goal in the language stops
    # there: before the events are flushed and before the record is read (qa on #1246).
    assert "/account/totals?only=" in foot and '"/account/totals"' not in foot
    goals_at = foot.index('asked("goals")')
    stop_at = foot.index("if (!goal || !finishedAt()) return null;")
    assert goals_at < stop_at < foot.index("happenings.flush") < foot.index('asked("goal")')
