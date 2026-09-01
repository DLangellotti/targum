"""The reading calendar: which portion, which schedule, and when it turns over.

Every payload here is a real answer from Hebcal, trimmed to the weeks under test. The
network is never touched: `year()` reads the cache, and the cache is these files copied
into the corpus root the test owns.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from targum.errors import TargumError
from targum.parasha import calendar as cal

FIXTURES = Path(__file__).parent / "fixtures" / "parasha"


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A corpus root with the fixture calendars already cached in it."""
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path))
    (tmp_path / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "calendar" / one.name)
    return tmp_path


def test_a_doubled_week_is_one_reading_of_two_portions(corpus: Path) -> None:
    """Nitzavim-Vayeilech is read whole, and says so in its numbers."""
    reading = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    assert reading is not None
    assert reading.name == "Nitzavim-Vayeilech"
    assert reading.doubled
    assert reading.numbers == (51, 52)
    assert reading.slug == "nitzavim-vayeilech"


def test_a_single_portion_carries_one_number(corpus: Path) -> None:
    """Hebcal sends one portion's number bare and a doubled week's as a list, and both
    have to end up as a tuple or `doubled` lies."""
    reading = cal.for_shabbat(date(2026, 1, 3), cal.Schedule.diaspora)
    assert reading is not None
    assert reading.numbers == (12,)
    assert not reading.doubled


def test_a_festival_on_shabbat_displaces_the_portion(corpus: Path) -> None:
    """The congregation reads the festival, so the page must too."""
    reading = cal.for_shabbat(date(2026, 5, 23), cal.Schedule.diaspora)
    assert reading is not None
    assert reading.kind is cal.ReadingKind.festival
    assert reading.name.startswith("Shavuot")
    assert reading.numbers == ()


def test_israel_and_the_diaspora_diverge_and_close_again(corpus: Path) -> None:
    """The real 2026 window: Israel is a portion ahead for six weeks, and a doubled
    reading in the diaspora is what puts them back in step."""
    apart = date(2026, 5, 30)
    here = cal.for_shabbat(apart, cal.Schedule.diaspora)
    there = cal.for_shabbat(apart, cal.Schedule.israel)
    assert here is not None and there is not None
    assert here.name == "Nasso"
    assert there.name == "Beha'alotcha"
    assert here.name != there.name

    closed = date(2026, 6, 27)
    here = cal.for_shabbat(closed, cal.Schedule.diaspora)
    there = cal.for_shabbat(closed, cal.Schedule.israel)
    assert here is not None and there is not None
    assert here.name == "Chukat-Balak"
    assert there.name == "Balak"
    # Israel has caught up inside the diaspora's doubled reading.
    assert set(there.numbers) <= set(here.numbers)


def test_the_aliyot_are_seven_and_in_order(corpus: Path) -> None:
    reading = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    assert reading is not None
    assert [one.number for one in reading.aliyot] == [1, 2, 3, 4, 5, 6, 7]
    assert all(one.book in cal.TORAH_BOOKS for one in reading.aliyot)
    # The maftir is dropped: on a portion it only repeats the seventh aliyah.
    assert len(reading.aliyot) == 7


def test_the_maftir_and_anything_outside_the_torah_are_left_out(corpus: Path) -> None:
    """A festival reading names its additional offering from Numbers under "M" and its
    megillah in a field of its own. Neither is this page's reading."""
    reading = cal.for_shabbat(date(2026, 5, 23), cal.Schedule.diaspora)
    assert reading is not None
    assert all(str(one.number).isdigit() for one in reading.aliyot)
    assert all(one.book in cal.TORAH_BOOKS for one in reading.aliyot)


# -- when the portion turns over ---------------------------------------------


def moment(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=ZoneInfo(cal.FLIP_ZONE))


@pytest.mark.parametrize(
    ("when", "expected", "why"),
    [
        ("2026-09-02T12:00", date(2026, 9, 5), "midweek looks ahead to the coming Shabbat"),
        ("2026-09-05T09:00", date(2026, 9, 5), "Shabbat morning is still this week's"),
        ("2026-09-05T23:30", date(2026, 9, 5), "Saturday night, before the turn"),
        ("2026-09-06T01:59", date(2026, 9, 5), "one minute before the turn"),
        ("2026-09-06T02:00", date(2026, 9, 12), "the turn itself"),
        ("2026-09-06T12:00", date(2026, 9, 12), "Sunday is the new week"),
    ],
)
def test_the_portion_turns_over_after_shabbat(when: str, expected: date, why: str) -> None:
    assert cal.pointing_at(moment(when)) == expected, why


def test_the_turn_never_lands_inside_shabbat_anywhere_in_the_states() -> None:
    """The reason `FLIP_AT` is 02:00 and not an hour that reads better.

    Nightfall in the Pacific timezone in June is about 22:30 local. The turn has to come
    after that, or a reader in California is shown next week's portion while it is still
    Shabbat where they are.
    """
    turn = moment("2026-09-06T02:00")
    pacific = turn.astimezone(ZoneInfo("America/Los_Angeles"))
    assert pacific.hour >= 22, "the turn falls before nightfall on the west coast"
    assert pacific.day == 5, "the turn should still be Saturday night out west"


# -- the cache ---------------------------------------------------------------


def test_a_missing_year_is_empty_rather_than_fetched_when_serving(corpus: Path) -> None:
    """What a server passes. A page being drawn must never wait on somebody's website."""
    assert cal.year(2099, cal.Schedule.diaspora, allow_fetch=False) == []
    assert cal.for_shabbat(date(2099, 1, 2), cal.Schedule.diaspora, allow_fetch=False) is None


def test_a_corrupt_cache_is_refetched_rather_than_trusted(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (corpus / "calendar" / "2026-diaspora.json").write_text("{ not json", encoding="utf-8")
    called: list[int] = []

    def refuse(year: int, schedule: cal.Schedule) -> dict:
        called.append(year)
        raise TargumError("no network")

    monkeypatch.setattr(cal, "fetch", refuse)
    with pytest.raises(TargumError):
        cal.year(2026, cal.Schedule.diaspora)
    assert called == [2026]


def test_a_fetch_that_fails_leaves_the_cache_alone(
    corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A year already on disk keeps building when the network goes away."""
    before = (corpus / "calendar" / "2026-diaspora.json").read_text(encoding="utf-8")

    def refuse(year: int, schedule: cal.Schedule) -> dict:
        raise TargumError("no network")

    monkeypatch.setattr(cal, "fetch", refuse)
    assert cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora) is not None
    assert (corpus / "calendar" / "2026-diaspora.json").read_text(encoding="utf-8") == before


def test_an_empty_answer_is_refused(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hebcal answering 200 with nothing in it must not overwrite a good cache."""
    import httpx

    class Answer:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"items": []}

    class Client:
        def __init__(self, **kw: object) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def get(self, *a: object, **kw: object) -> Answer:
            return Answer()

    monkeypatch.setattr(httpx, "Client", Client)
    with pytest.raises(TargumError):
        cal.refresh(2031, cal.Schedule.diaspora)
    assert not (corpus / "calendar" / "2031-diaspora.json").exists()


def test_a_year_is_fetched_in_windows(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint silently clamps a range to six months and says so only in a field
    nobody reads, so a year asked for in one call comes back missing its autumn."""
    import httpx

    asked: list[tuple[str, str]] = []

    class Answer:
        def __init__(self, first: str) -> None:
            self.first = first

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"items": [{"date": self.first, "type": "weekday", "name": {"en": "x"}}]}

    class Client:
        def __init__(self, **kw: object) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def get(self, url: str, params: dict[str, str], **kw: object) -> Answer:
            asked.append((params["start"], params["end"]))
            return Answer(params["start"])

    monkeypatch.setattr(httpx, "Client", Client)
    cal.fetch(2026, cal.Schedule.diaspora)
    assert len(asked) == 4, "a year must be asked for in windows under the cap"
    assert asked[0][0] == "2026-01-01"
    assert asked[-1][1] == "2026-12-31"
    for first, last in asked:
        span = date.fromisoformat(last) - date.fromisoformat(first)
        assert span.days < 180, "a window has to stay under the six-month clamp"


def test_israel_is_asked_for_as_israel(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    seen: list[dict[str, str]] = []

    class Answer:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"items": [{"date": "2026-01-03", "type": "weekday", "name": {"en": "x"}}]}

    class Client:
        def __init__(self, **kw: object) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def get(self, url: str, params: dict[str, str], **kw: object) -> Answer:
            seen.append(params)
            return Answer()

    monkeypatch.setattr(httpx, "Client", Client)
    cal.fetch(2026, cal.Schedule.israel)
    assert all(one.get("i") == "on" for one in seen)
    seen.clear()
    cal.fetch(2026, cal.Schedule.diaspora)
    assert all("i" not in one for one in seen)


# -- the reading the cycle never produces ------------------------------------


def test_vzot_haberachah_is_carried_because_no_shabbat_ever_reads_it() -> None:
    """Read on Simchat Torah and on no ordinary Shabbat, so a calendar walked for a
    century would never hand it over and Deuteronomy would end at 32."""
    always = cal.always()
    assert [one.name for one in always] == ["V'Zot HaBerachah"]
    one = always[0]
    assert one.numbers == (54,)
    assert len(one.aliyot) == 7
    assert one.aliyot[0].book == "Deuteronomy"
    assert one.aliyot[-1].end == "34:12"


def test_a_two_year_walk_cannot_see_every_portion(corpus: Path) -> None:
    """The bug behind the corpus window, stated as a fact about the calendar.

    Matot, Masei, Nitzavim and Vayeilech are doubled on both schedules for years at a
    stretch. A walk that only sees those years never meets them on their own, so they
    are never cut and have no address — which is how four of the fifty-four went missing
    from a corpus that called itself fixed and finite.
    """
    from targum.parasha.build import distinct

    near = distinct([2026], [cal.Schedule.diaspora], allow_fetch=False)

    assert "nitzavim-vayeilech" in near, "2026 reads the pair"
    for half in ("nitzavim", "vayeilech", "matot", "masei"):
        assert half not in near, f"{half} is not read on its own in 2026"


def test_a_wide_enough_walk_meets_every_half_on_its_own(corpus: Path) -> None:
    """And the fix, on real Hebcal answers: 2029 splits Nitzavim from Vayeilech and 2035
    splits Matot from Masei, so a span that reaches them cuts all four. `CORPUS_YEARS` is
    nineteen — the Metonic cycle — because no smaller number is safe: walking 2026 onward,
    four years recovers the first pair and only ten recovers the second.

    Those two years live in `split-years/` rather than beside 2026, because the fixtures
    beside 2026 are copied wholesale into every corpus a test builds — dropping two more
    years in there silently changed what unrelated tests were reading, which is how this
    comment came to be written."""
    from targum.parasha.build import CORPUS_YEARS, distinct

    for one in (FIXTURES / "split-years").glob("*.json"):
        shutil.copy(one, corpus / "calendar" / one.name)
    wide = distinct([2026, 2029, 2035], [cal.Schedule.diaspora], allow_fetch=False)

    for half in ("nitzavim", "vayeilech", "matot", "masei"):
        assert half in wide, f"{half} is read on its own somewhere in the span"
    assert "nitzavim-vayeilech" in wide, "and the doubled reading is still its own entry"
    assert CORPUS_YEARS >= 10, "ten is the measured floor; nineteen is the honest one"


def test_the_corpus_is_walked_wider_than_the_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two windows, and the whole point is that they are not the same one.

    The pointer only has to reach as far as a box might go without Hebcal. The corpus has
    to reach far enough to meet every portion on its own. Sharing one window is what cost
    the shelf four portions.
    """
    from targum.parasha import build as build_module

    # `build()` writes its index to `root()`, which is the real corpus directory unless
    # this is set. Without it a test that builds an empty index overwrites the corpus on
    # disk — which is exactly what the first draft of this test did.
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))

    asked: dict[str, list[int]] = {}

    def fake_distinct(years, schedules, **kw):  # type: ignore[no-untyped-def]
        asked.setdefault("corpus", []).extend(years)
        return {}

    def fake_readings_for(one, schedule, **kw):  # type: ignore[no-untyped-def]
        asked.setdefault("pointer", []).append(one)
        return []

    monkeypatch.setattr(build_module, "distinct", fake_distinct)
    monkeypatch.setattr(build_module, "readings_for", fake_readings_for)

    build_module.build(schedules=[cal.Schedule.diaspora])

    this = date.today().year
    assert sorted(set(asked["corpus"])) == list(range(this, this + build_module.CORPUS_YEARS))
    assert sorted(set(asked["pointer"])) == list(range(this, this + build_module.YEARS_AHEAD))
    assert len(set(asked["corpus"])) > len(set(asked["pointer"])), "the corpus is the wider one"


def test_naming_the_corpus_span_narrows_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wide sweep is the default because production always names its pointer years —
    a default that only widened when they were absent would have been right in the tests
    and inert on the box, which is what the first draft of this was.

    So the escape hatch is the other way round: a caller with one year in its cache names
    `corpus_years` and gets exactly that. Every parasha test does, which is what keeps the
    suite off the network.
    """
    from targum.parasha import build as build_module

    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    asked: list[int] = []

    def fake_distinct(years, schedules, **kw):  # type: ignore[no-untyped-def]
        asked.extend(years)
        return {}

    monkeypatch.setattr(build_module, "distinct", fake_distinct)
    monkeypatch.setattr(build_module, "readings_for", lambda *a, **k: [])

    build_module.build(years=[2026], corpus_years=[2026], schedules=[cal.Schedule.diaspora])
    assert asked == [2026], "one year named is one year walked"

    asked.clear()
    build_module.build(years=[2026], schedules=[cal.Schedule.diaspora])
    assert len(set(asked)) == build_module.CORPUS_YEARS, "unnamed, it widens to the cycle"


def test_slugs_are_urls() -> None:
    assert cal.slug("Nitzavim-Vayeilech") == "nitzavim-vayeilech"
    assert cal.slug("Sh'lach") == "shlach"
    assert cal.slug("Achrei Mot-Kedoshim") == "achrei-mot-kedoshim"
    assert cal.slug("Pesach Shabbat Chol ha-Moed") == "pesach-shabbat-chol-ha-moed"
    assert cal.slug("V'Zot HaBerachah") == "vzot-haberachah"


def test_parsing_is_not_confused_by_a_weekday_reading(corpus: Path) -> None:
    """Monday and Thursday readings are a shortened form of the coming Shabbat's portion
    and would otherwise arrive as duplicates of it."""
    payload = json.loads((FIXTURES / "2026-diaspora.json").read_text(encoding="utf-8"))
    payload["items"].append(
        {
            "date": "2026-09-03",
            "type": "weekday",
            "name": {"en": "Nitzavim-Vayeilech", "he": ""},
            "fullkriyah": {"1": {"k": "Deuteronomy", "b": "29:9", "e": "29:11", "v": 3}},
        }
    )
    readings = cal.parse(payload, cal.Schedule.diaspora)
    assert all(one.day.weekday() == 5 for one in readings), "only Shabbat readings"
