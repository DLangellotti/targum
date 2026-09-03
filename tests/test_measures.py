"""The six beta measures, counted off a store rather than remembered.

What can be held here is that each question is answered from the records the reader
actually sends — a text opened, a text finished, a day read, a person joined — and that
the three the store cannot answer are said to be missing rather than stood in for.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from targum.accounts import Person, Store
from targum.cli import app
from targum.measures import as_state, measure, measure_store, report, shelf, spread

DAY = 24 * 60 * 60 * 1000


def stamp(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)


def join(store: Store, email: str, made: int) -> Person:
    token = store.start_sign_in(email)
    signed = store.finish_sign_in(token)
    assert signed is not None
    person, _ = signed
    with store.write() as db:
        db.execute("UPDATE person SET made = ? WHERE id = ?", (made, person.id))
    return person


def opened(store: Store, person: Person, hash_: str, title: str, when: int, done: int = 0) -> None:
    store.push(
        person,
        {
            "docs": [
                {
                    "hash": hash_,
                    "title": title,
                    "language": "he",
                    "updated": when,
                    "opened": when,
                    "done": done,
                    "seen": max(when, done),
                }
            ]
        },
    )


def read_on(store: Store, person: Person, *days: str) -> None:
    store.push(person, {"days": [{"day": day, "count": 1, "seen": stamp(day)} for day in days]})


REGISTERS = {"gen": "biblical", "ruth": "biblical", "brenner": "revival", "news": "modern"}


def seeded(tmp_path: Path) -> Store:
    store = Store(tmp_path / "targum.db")
    # Week 36: one reader who came back for a second text and crossed shelves, one who
    # opened one text and stopped. Week 37: one who reads the Tanakh only.
    ruth = join(store, "ruth@example.com", stamp("2026-08-31"))
    opened(store, ruth, "gen", "בראשית", stamp("2026-08-31"), done=stamp("2026-09-03"))
    opened(store, ruth, "brenner", "מכאן ומכאן", stamp("2026-09-04"))
    read_on(store, ruth, "2026-08-31", "2026-09-01", "2026-09-03", "2026-09-04")
    once = join(store, "once@example.com", stamp("2026-09-02"))
    opened(store, once, "news", "חדשות", stamp("2026-09-02"))
    read_on(store, once, "2026-09-02")
    tanakh = join(store, "tanakh@example.com", stamp("2026-09-08"))
    opened(store, tanakh, "ruth", "רות", stamp("2026-09-08"), done=stamp("2026-09-09"))
    opened(store, tanakh, "gen", "בראשית", stamp("2026-09-10"))
    read_on(store, tanakh, "2026-09-08", "2026-09-09", "2026-09-10")
    return store


def test_a_second_text_is_counted_by_the_week_they_joined(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    found = measure(store.db, REGISTERS, stamp("2026-09-14"))
    assert found.readers == 3
    assert found.returned == [("2026-w36", 2, 1), ("2026-w37", 1, 1)]


def test_the_first_text_is_the_earliest_open_and_says_only_finished_or_not(
    tmp_path: Path,
) -> None:
    """The place in a text never reaches the store, so "how far" is finished or open."""
    store = seeded(tmp_path)
    found = measure(store.db, REGISTERS, stamp("2026-09-14"))
    assert sorted(found.first) == [
        ("2026-08-31", "בראשית", True),
        ("2026-09-02", "חדשות", False),
        ("2026-09-08", "רות", True),
    ]
    assert "never synced" in found.not_recorded["how far into the first text"]


def test_the_two_shelves_and_who_crosses_them(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    found = measure(store.db, REGISTERS, stamp("2026-09-14"))
    assert found.shelves == {"both": 1, "not biblical": 1, "biblical only": 1}
    assert found.biblical_readers == 2
    assert found.biblical_who_crossed == 1


def test_a_text_the_shelf_cannot_place_is_not_guessed(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    found = measure(store.db, {}, stamp("2026-09-14"))
    assert found.shelves == {}
    assert found.biblical_readers == 0


def test_age_is_days_since_joining_and_device_is_said_to_be_missing(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    found = measure(store.db, REGISTERS, stamp("2026-09-14"))
    assert sorted(found.ages) == [6, 12, 14]
    assert "no device" in found.not_recorded["device"]


def test_plays_are_not_stood_in_for(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    found = measure(store.db, REGISTERS, stamp("2026-09-14"))
    assert "no play reaches the store" in found.not_recorded["plays per verse"]
    assert "not measured" in report(found)


def test_a_month_holds_texts_finished_and_days_read_per_reader(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    found = measure(store.db, REGISTERS, stamp("2026-09-14"))
    assert found.finished_by_month == {"2026-09": [1, 1]}
    assert found.days_by_month == {"2026-08": [1], "2026-09": [3, 1, 3]}


def test_someone_leaving_is_not_a_reader(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    gone = store.person_by_email("once@example.com")
    assert gone is not None
    store.forget(gone)
    found = measure(store.db, REGISTERS, stamp("2026-09-14"))
    assert found.readers == 2


def test_a_spread_is_one_line() -> None:
    assert spread([]) == "nobody"
    assert spread([3, 1, 2, 10]) == "1–10, median 2.5, over 4"


def test_the_report_names_nobody(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    found = measure(store.db, REGISTERS, stamp("2026-09-14"))
    text = report(found)
    assert "@example.com" not in text
    for heading in ("1. a second text", "2. the first text", "3. the two shelves"):
        assert heading in text
    for heading in ("4. plays per verse", "5. age and device", "6. per reader per month"):
        assert heading in text
    assert "2026-w36  joined   2  opened a second text   1" in text
    state = as_state(found)
    assert state["biblical"] == {"readers": 2, "crossed": 1}
    json.dumps(state)


def test_the_shelf_is_read_from_the_documents_beside_the_readers(tmp_path: Path) -> None:
    """A hash meets its source in `document.json` and nowhere else."""
    out = tmp_path / "out"
    for home, name, source, language in (
        ("reader", "ruth", "sefaria:Ruth", "he"),
        ("reader", "own", "/somewhere/mine.md", "he"),
        ("reader", "tolstoy", "https://www.gutenberg.org/ebooks/1", "ru"),
    ):
        folder = out / home / name
        folder.mkdir(parents=True)
        (folder / "document.json").write_text(
            json.dumps(
                {
                    "content_hash": name + "-hash",
                    "source": source,
                    "language": language,
                    "blocks": [],
                }
            ),
            encoding="utf-8",
        )
    (out / "reader" / "broken").mkdir()
    (out / "reader" / "broken" / "document.json").write_text("{", encoding="utf-8")
    placed = shelf(out)
    assert placed["ruth-hash"] == "biblical"
    assert placed["own-hash"] == "modern"
    assert placed["tolstoy-hash"] == "other"
    assert "broken" not in "".join(placed)
    assert shelf(tmp_path / "nowhere") == {}


def test_the_command_reads_the_store_it_is_given(tmp_path: Path) -> None:
    store = seeded(tmp_path)
    store.close()
    found = measure_store(tmp_path / "targum.db", tmp_path / "no-readers")
    assert found.readers == 3

    result = CliRunner().invoke(
        app,
        ["measures", "--store", str(tmp_path / "targum.db"), "--out", str(tmp_path / "none")],
    )
    assert result.exit_code == 0, result.output
    assert "readers: 3" in result.output
    assert "5. age and device" in result.output

    result = CliRunner().invoke(
        app,
        ["measures", "--store", str(tmp_path / "targum.db"), "--out", str(tmp_path), "--json"],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["readers"] == 3
