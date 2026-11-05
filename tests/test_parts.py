"""A suggestion never drops a reader into the middle of a series (David, 2026-11-03;
design.md §12, "A suggestion never starts a series in the middle").

What a numbered part is (`parts.of_title`, `of_episode`, `of_entry`), who may be offered
it (`parts.allowed`), the pass every suggestion list goes through (`parts.gate`), and the
paths that use it: the pool's pick on home (`finds.button.ranked`), Read next
(`chat.tools.suggest_next`, over the catalogue and the finds), the podcast round, and the
schema that keeps a find's part. Nothing here reaches a network.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from test_finds import ctx_for, keep
from test_finds_podcasts import AT, FEED_BODY, SHOW, night

from targum import accounts, parts
from targum import catalogue as catalogue_module
from targum.accounts import Store
from targum.chat import tools
from targum.coverage import KNOWN
from targum.finds import button, pool, provider, score
from targum.weekly import feeds

#: The video David was offered on home's "One to try next" on 2026-11-03, part 2 of a
#: falafel tour, pooled by a live look for the "israel" chip the day before with no part 1
#: anywhere in the pool (find 2332 on the box).
FALAFEL_2 = "מצאתי את הפלאפלים הכי זולים בישראל חלק 2!!! (דרום הארץ)"
FALAFEL_KEY = "מצאתי את הפלאפלים הכי זולים בישראל"
CHANNEL = "עמית טרפוצ'ניק כפית - Amit Kapit"

# -- what a part is ------------------------------------------------------------------

#: Title, the number it is part of (None where it is no part), and part or episode.
#: Most are titles the pool held on 2026-11-03; the rest are the shapes they come in.
PARTS: list[tuple[str, int | None, str]] = [
    # Hebrew, part wording
    (FALAFEL_2, 2, parts.PART),
    ("״כולם גנבים״ – שיר אהבה או זלזול? (חלק 2)", 2, parts.PART),
    ("החזר משכנתה נמוך = יותר ריבית לבנק? כרית הביטחון שמשנה הכל | חלק 3", 3, parts.PART),
    ("איך לגדל בן מודע ואיך לגדל בת עוצמתית? חלק א' / הורות בריאה", 1, parts.PART),
    ("סיפור ארוך חלק ב׳", 2, parts.PART),
    ("סיפור ארוך - חלק ג:", 3, parts.PART),
    ("בייבי בלוז - חלק ראשון", 1, parts.PART),
    ("בייבי בלוז - חלק שני", 2, parts.PART),
    ("בייבי בלוז - חלק חמישי", 5, parts.PART),
    ("רשימת חיסול - החלק השני", 2, parts.PART),
    ("רשימת חיסול - החלק האחרון", parts.LATER, parts.PART),
    ("חלק 4 – המסע הביתה", 4, parts.PART),
    ("זוֹ הַהַתְחָלָה, חֵלֶק 2", 2, parts.PART),
    # Hebrew, episode wording
    ("חדשות האוכל עם ריטה גולדשטיין: עונה 3 פרק 14 - פודי", 14, parts.EPISODE),
    ("פרק 82: דודו אהרון פותח הכל, ניקי גולדשטיין מכוון לאירוויזיון", 82, parts.EPISODE),
    ("ראש כרוב: הפרק הראשון", 1, parts.EPISODE),
    ("הסדרה שלנו פרק ג'", 3, parts.EPISODE),
    # English
    ("The Kuzari, Part Two", 2, parts.PART),
    ("Electrostatics, part 1", 1, parts.PART),
    ("Optimal Angle for a Projectile, Pt. 2", 2, parts.PART),
    ("Making bread, Part II", 2, parts.PART),
    ("Мастер и Маргарита. Часть последняя", parts.LATER, parts.PART),
    ("The road north: Part 3 of 4", 3, parts.PART),
    ("How I did it (2/5)", 2, parts.PART),
    ("How I did it [3/3]", 3, parts.PART),
    ("Hebrew in a week, Episode 3", 3, parts.EPISODE),
    ("Hebrew in a week Ep. 4", 4, parts.EPISODE),
    ("Hebrew in a week ep5", 5, parts.EPISODE),
    ("Our show S02E03", 3, parts.EPISODE),
    ("Star Wars Episode IV: A New Hope", 4, parts.EPISODE),
    # Russian
    ("Мастер и Маргарита. Часть 2", 2, parts.PART),
    ("Мастер и Маргарита, часть вторая", 2, parts.PART),
    ("Мастер и Маргарита: вторая часть", 2, parts.PART),
    ("Мастер и Маргарита — 2-я часть", 2, parts.PART),
    ("Мастер и Маргарита. Часть II", 2, parts.PART),
    ("Дом у моря. Серия 3", 3, parts.EPISODE),
    ("Дом у моря, 2 сезон 5 серия", 5, parts.EPISODE),
    ("Дом у моря: третья серия", 3, parts.EPISODE),
    ("Дом у моря, эпизод 7", 7, parts.EPISODE),
    # Not parts: a number with no part wording, a year, a chapter, a date, a score
    ("Toy Story 2", None, ""),
    ("Bible in Hebrew - 2 Samuel 9 | תנך בעברית - שמואל ב  ט", None, ""),
    ("Tehilim 20 (Psalm 20) | Epic Hebrew Kids Choir | תהלים כ׳ לילדים", None, ""),
    ("• שאלה 20 בפסיכומטרי (דרגת קושי גבוהה) – הטריק של 25 ומאות שלמות", None, ""),
    ("ישראל שלו כנס מיקרוסופט 20.10.2026", None, ""),
    ("תשכחו ממפלגת שלטון: בבחירות 2026 החל עידן המפלגות הבינוניות", None, ""),
    ("נטפליקס בנובמבר 2026: הסדרות החדשות והעונות שאסור לפספס", None, ""),
    ('אחרי 20 עונות: "מחשבות פליליות" יורדת מהמסך', None, ""),
    ('הטרקטורון שנגנב מבית מפקד השב"כ שנפל ב-7/10 אותר ברהט', None, ""),
    ("סרט חדש (7/10)", None, ""),
    ("Childhood. Chapter I: Our Tutor, Karl Ivanych", None, ""),
    ("Детство. Глава I. Учитель Карл Иваныч", None, ""),
    ("ספר הכוזרי, מאמר שני", None, ""),
    ("I Samuel", None, ""),
    ("שמואל ב", None, ""),
    # Not parts: the word without a number, or a number that is not its own
    ("למה חלק מהציפורים לא מסוגלות לעוף? – Gillian Gibb", None, ""),
    ("מזרחי טפחות יחלק 10 מיליון שקל להורים", None, ""),
    ("בוי ג'ורג' להרצוג על החברים שאיבד: \"חלקם אפילו לא נפרדו\"", None, ""),
    ("חלק הארי של התקציב", None, ""),
    ("כל חלקי הגוף.", None, ""),
    ("לפנויים לכלל הגילאים רווקים ופרק ג ושנ", None, ""),
    ("הפרקליטות מערערת על עונשו של הרוצח", None, ""),
    ("Going part-time", None, ""),
    ("Part of the problem", None, ""),
    ("Le Parti socialiste", None, ""),
    ("Какая часть речи?", None, ""),
]


@pytest.mark.parametrize(("title", "number", "kind"), PARTS)
def test_a_part_is_said_in_words_and_a_bare_number_is_not_one(
    title: str, number: int | None, kind: str
) -> None:
    got = parts.of_title(title)
    if number is None:
        assert got is None, title
        return
    assert got is not None, title
    assert (got.number, got.kind) == (number, kind), title


def test_the_key_is_the_words_before_the_marker_else_the_publisher() -> None:
    got = parts.of_title(FALAFEL_2, CHANNEL)
    assert got is not None and got.key == FALAFEL_KEY and got.number == 2
    one = parts.of_title("מצאתי את הפלאפלים הכי זולים בישראל חלק 1 (מרכז הארץ)", CHANNEL)
    assert one is not None and one.key == got.key and one.first
    leading = parts.of_title("פרק 82: דודו אהרון פותח הכל", "התחלנו")
    assert leading is not None and leading.key == "התחלנו"
    season = parts.of_title("חדשות האוכל עם ריטה גולדשטיין: עונה 3 פרק 14 - פודי")
    assert season is not None and season.key == "חדשות האוכל עם ריטה גולדשטיין"
    assert (season.season, season.number) == (3, 14) and not season.first
    pointed = parts.of_title("זוֹ הַהַתְחָלָה, חֵלֶק 2")
    assert pointed is not None and pointed.key == "זו ההתחלה", "points folded away"
    nothing = parts.of_title("Часть 2")
    assert nothing is not None and nothing.key == "", "no words and no publisher match nothing"


def test_a_podcast_that_says_it_is_episodic_counts_episodes_and_a_serial_does_not() -> None:
    title = "פרק 189: 1+1 עם שי בן צור"
    assert parts.of_episode(title, "1+1", number=189, show_type="episodic") is None
    assert parts.of_episode("סיפור חלק 2", "show", number=40, show_type="episodic") == (
        parts.of_title("סיפור חלק 2", "show")
    ), "part wording still counts in an episodic show"
    serial = parts.of_episode("הרצח בכפר", "התעלומה", number=3, season=1, show_type="serial")
    assert serial is not None and (serial.key, serial.number) == ("התעלומה", 3)
    untyped = parts.of_episode(title, "1+1", number=189)
    assert untyped is not None and untyped.number == 189, "a feed that says nothing is held"
    by_title = parts.of_episode(title, "1+1")
    assert by_title is not None and by_title.number == 189
    assert parts.of_episode(title, "1+1", number=189, episode_type="trailer") is None
    assert parts.of_episode(title, "1+1", number=189, episode_type="bonus") is None
    first = parts.of_episode("פתיחה", "התעלומה", number=1, show_type="serial")
    assert first is not None and first.first


def test_a_catalogue_row_is_read_in_english_first() -> None:
    two = parts.of_entry("The Kuzari, Part Two", "ספר הכוזרי, מאמר שני", "The Kuzari")
    one = parts.of_entry("The Kuzari, Part One", "ספר הכוזרי, מאמר ראשון", "The Kuzari")
    assert two is not None and one is not None and two.key == one.key == "the kuzari"
    assert one.first and two.number == 2
    hebrew = parts.of_entry("", "זווית אופטימלית לקליע חלק 1")
    assert hebrew is not None and hebrew.first
    assert parts.of_entry("I Samuel", "שמואל א") is None


# -- who may be offered what -----------------------------------------------------------


def part(number: int, key: str = "k", season: int = 0, publisher: str = "") -> parts.Part:
    return parts.Part(key=key, number=number, season=season, publisher=publisher)


def test_part_n_waits_for_part_n_minus_one() -> None:
    assert parts.allowed(part(1), [])
    assert not parts.allowed(part(2), [])
    assert parts.allowed(part(2), [part(1)])
    assert not parts.allowed(part(3), [part(1)]), "two ahead is still the middle"
    assert not parts.allowed(part(2), [part(1, key="other")])
    assert not parts.allowed(part(parts.LATER), [part(1), part(2), part(3)])
    assert not parts.allowed(part(2, key=""), [part(1, key="")]), "no key matches nothing"
    assert parts.allowed(part(4, season=2), [part(3, season=2)])
    assert not parts.allowed(part(4, season=2), [part(3, season=1)])
    assert parts.allowed(part(1, season=2), [part(9, season=1)])
    assert not parts.allowed(part(1, season=3), [part(9, season=1)])
    assert parts.allowed(part(2, season=1), [part(1, season=0)]), "season 1 is no season"


def row(name: str, p: parts.Part | None = None, fit: str = "band") -> dict[str, Any]:
    out: dict[str, Any] = {"id": name, "fit": fit}
    if p is not None:
        out[parts.FIELD] = p.row()
    return out


def ids(rows: list[dict[str, Any]]) -> list[str]:
    return [one["id"] for one in rows]


def test_gate_puts_part_one_in_a_later_part_s_place_or_leaves_the_series_out() -> None:
    plain = row("plain")
    two, one = row("two", part(2)), row("one", part(1))
    assert ids(parts.gate([two, plain], [])) == ["plain"], "no part 1: the series is left out"
    assert ids(parts.gate([two, plain, one], [])) == ["one", "plain"], "part 1 in its place"
    assert ids(parts.gate([one, two, plain], [])) == ["one", "plain"], "never twice"
    assert ids(parts.gate([two, plain, one], [part(1)])) == ["two", "plain", "one"]
    three = row("three", part(3))
    assert ids(parts.gate([three, two, one], [])) == ["one"]
    under = row("one-under", part(1), fit="under")
    assert ids(parts.gate([two, plain, under], [])) == ["plain", "one-under"], (
        "a part 1 under the floor does not take a place in the band"
    )
    easy = row("two-easy", part(2), fit="easy")
    banded = row("one-band", part(1))
    assert ids(parts.gate([easy, banded], [])) == ["one-band"]
    other = row("one-other", parts.Part(key="k", number=1, publisher="b"))
    theirs = row("two-theirs", parts.Part(key="k", number=2, publisher="a"))
    assert ids(parts.gate([theirs, other], [])) == ["one-other"], (
        "another publisher's part 1 is not offered in its place, only at its own"
    )


# -- the pool, home's pick and Read next -------------------------------------------------

MARKED = {"בית": KNOWN}
BAG = {"בית": 95, "ספר": 5}


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setenv(score.ENV, str(tmp_path / "absent.json"))
    return Store(tmp_path / "targum.db")


def test_a_find_keeps_its_part_and_an_older_one_reads_it_off_its_title(store: Store) -> None:
    two = keep(
        store, "https://www.youtube.com/watch?v=two", BAG, title=FALAFEL_2, publisher=CHANNEL
    )
    found = pool.get(store, two)
    assert found is not None and found.part is not None
    assert (found.part.key, found.part.number) == (FALAFEL_KEY, 2)
    stored = store.db.execute("SELECT series, part, season FROM find WHERE id = ?", (two,))
    assert tuple(stored.fetchone()) == (FALAFEL_KEY, 2, 0)
    plain = keep(store, "https://n.example/plain", BAG, title="כותרת")
    assert store.db.execute("SELECT part FROM find WHERE id = ?", (plain,)).fetchone()[0] == 0
    store.db.execute("UPDATE find SET series = '', part = -1 WHERE id = ?", (two,))
    again = pool.get(store, two)
    assert again is not None and again.part is not None and again.part.number == 2
    assert [
        one.number for one in pool.parts_at(store, ["https://www.youtube.com/watch?v=two"])
    ] == [2]


def test_home_never_offers_part_two_of_the_falafel_video_alone(store: Store) -> None:
    """Why David got part 2 on 2026-11-03: the pool held it and nothing asked."""
    two_url = "https://www.youtube.com/watch?v=lTIVoa-PMNc"
    keep(store, two_url, BAG, title=FALAFEL_2, publisher=CHANNEL, rung=4)
    keep(store, "https://n.example/plain", {"בית": 96, "ספר": 4}, title="כתבה")
    got = button.ranked(store, button.Ask("he"), MARKED)
    assert [one["url"] for one in got] == ["https://n.example/plain"]
    one_url = "https://www.youtube.com/watch?v=part-one"
    keep(
        store,
        one_url,
        {"בית": 93, "ספר": 7},
        title="מצאתי את הפלאפלים הכי זולים בישראל חלק 1!!! (מרכז הארץ)",
        publisher=CHANNEL,
    )
    got = button.ranked(store, button.Ask("he"), MARKED)
    assert [one["url"] for one in got] == [one_url, "https://n.example/plain"], (
        "part 1 in part 2's place"
    )
    opened = button.ranked(store, button.Ask("he"), MARKED, built={one_url})
    assert [one["url"] for one in opened][0] == two_url, "part 1 built: part 2 is next"


def test_read_next_offers_part_one_of_a_find_and_part_two_after_it(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "CANDIDATE_SOURCES", [("shelf", lambda ctx: [])])
    monkeypatch.setattr(tools, "_collections", lambda: {})
    mine: list[dict[str, Any]] = []
    monkeypatch.setattr(tools, "_shelf", lambda ctx, measured=True: (mine, []))
    ctx = ctx_for(store, MARKED)
    keep(store, "https://v.example/2", BAG, title="Making bread, Part 2", publisher="Baker")
    assert tools.suggest_next(ctx, {"limit": 3, "finds": True})["suggestions"] == []
    keep(
        store,
        "https://v.example/1",
        {"בית": 92, "ספר": 8},
        title="Making bread, Part 1",
        publisher="Baker",
    )
    got = tools.suggest_next(ctx, {"limit": 3, "finds": True})["suggestions"]
    assert [one["url"] for one in got] == ["https://v.example/1"]
    mine.append(
        {"name": "bread-1", "title": "Making bread, Part 1", "source": "https://v.example/1"}
    )
    got = tools.suggest_next(ctx, {"limit": 3, "finds": True})["suggestions"]
    assert [one["url"] for one in got] == ["https://v.example/2"], (
        "part 1 is theirs now (Continue has it), and part 2 is next"
    )


KUZARI = ["One", "Two", "Three"]


def entry(entry_id: str) -> catalogue_module.Entry:
    """A Kuzari part as the catalogue writes it (`kuzari-1`… with "The Kuzari, Part One")."""
    number = int(entry_id.rsplit("-", 1)[1])
    return catalogue_module.Entry(
        id=entry_id,
        title=f"ספר הכוזרי, מאמר {number}",
        author="יהודה הלוי",
        language="he",
        source=f"sefaria:Kuzari.{number}",
        blurb="",
        words=1000,
        english=f"The Kuzari, Part {KUZARI[number - 1]}",
    )


def test_read_next_offers_the_kuzari_from_its_first_part(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "_shelf", lambda ctx, measured=True: ([], []))
    ctx = ctx_for(store, MARKED)
    later = [entry("kuzari-2"), entry("kuzari-3")]
    monkeypatch.setattr(tools, "CANDIDATE_SOURCES", [("shelf", lambda ctx: later)])
    assert tools.suggest_next(ctx, {"limit": 5})["suggestions"] == [], "no part 1 here"
    with_first = [*later, entry("kuzari-1")]
    monkeypatch.setattr(tools, "CANDIDATE_SOURCES", [("shelf", lambda ctx: with_first)])
    got = tools.suggest_next(ctx, {"limit": 5})["suggestions"]
    assert [one["id"] for one in got] == ["kuzari-1"]
    finished = tools.suggest_next(ctx, {"limit": 5, "skip": ["kuzari-1"]})["suggestions"]
    assert [one["id"] for one in finished] == ["kuzari-2"], "part 1 read: part 2, not part 3"


# -- the podcast round, and the schema ---------------------------------------------------


def with_episode(show_type: str, number: int) -> bytes:
    body = FEED_BODY.decode("utf-8")
    body = body.replace("<channel>", f"<channel>\n    <itunes:type>{show_type}</itunes:type>", 1)
    body = body.replace(
        "<guid>ep-transcript</guid>",
        f"<guid>ep-transcript</guid>\n      <itunes:episode>{number}</itunes:episode>"
        "\n      <itunes:season>1</itunes:season>"
        "\n      <itunes:episodeType>full</itunes:episodeType>",
        1,
    )
    return body.encode("utf-8")


def test_a_feed_states_the_episode_and_what_the_show_is() -> None:
    body = with_episode("serial", 4)
    assert feeds.show_type(body) == "serial" and feeds.show_type(FEED_BODY) == ""
    first = feeds.parse(body)[0]
    assert (first.episode, first.season, first.episode_type) == (4, 1, "full")
    assert feeds.parse(FEED_BODY)[0].episode == 0


def test_a_serial_s_later_episode_is_pooled_as_a_part_and_an_episodic_one_is_not(
    store: Store,
) -> None:
    url = "https://audio.example/show/ep-transcript.mp3"
    night(store, pull=lambda feed: with_episode("serial", 4))
    found = {one.url: one for one in pool.pick(store, "he", None, at=AT)}[url]
    assert found.part is not None and (found.part.key, found.part.number) == (
        parts.fold(SHOW.name),
        4,
    )
    assert parts.FIELD in provider.row(provider.Scored(found, 0.95))


def test_an_episodic_show_s_episode_is_no_part_and_an_older_row_learns_it(store: Store) -> None:
    url = "https://audio.example/show/ep-transcript.mp3"
    night(store, pull=lambda feed: with_episode("episodic", 4))
    found = {one.url: one for one in pool.pick(store, "he", None, at=AT)}[url]
    assert found.part is None
    store.db.execute("UPDATE find SET part = -1 WHERE url = ?", (url,))
    night(store, pull=lambda feed: with_episode("serial", 4), at=AT + 1)
    marked = store.db.execute("SELECT series, part FROM find WHERE url = ?", (url,)).fetchone()
    assert tuple(marked) == (parts.fold(SHOW.name), 4), "the feed read again says it"


def test_an_older_pool_gains_the_part_columns(tmp_path: Path) -> None:
    file = tmp_path / "old.db"
    old_schema = pool.SCHEMA.replace(
        ",\n  series     TEXT    NOT NULL DEFAULT '',\n  part       INTEGER NOT NULL DEFAULT -1,"
        "\n  season     INTEGER NOT NULL DEFAULT 0",
        "",
    )
    assert old_schema != pool.SCHEMA
    with sqlite3.connect(file) as old:
        old.executescript(old_schema + "PRAGMA user_version = 59;")
        old.execute(
            "INSERT INTO find (language, source, url, title, found, expires, rung)"
            " VALUES ('he', 'youtube', 'https://y.example/2', ?, 0, 99999999999999, 4)",
            (FALAFEL_2,),
        )
    opened = Store(file)
    columns = {one[1] for one in opened.db.execute("PRAGMA table_info(find)")}
    assert {"series", "part", "season"} <= columns
    assert opened.db.execute("SELECT part FROM find").fetchone()[0] == -1
    assert opened.db.execute("PRAGMA user_version").fetchone()[0] == accounts.SCHEMA_VERSION >= 60
    held = pool.parts_at(opened, ["https://y.example/2"])
    assert [(one.key, one.number) for one in held] == [(FALAFEL_KEY, 2)], "read off its title"
