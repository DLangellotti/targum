"""Next Shabbat's portion, on the portion page (targum-internal#416).

What follows a reading is the calendar's to say, on the reader's own schedule, with the
cycle's order behind it where the calendar is silent; and the next portion's words are
kept beside its reader so the page can count them against a reader's word list.

The reader's own last aliyah asked for this once, at `/parasha/next/<folder>`; it reads
on in the order of the book now (targum-internal#446, `test_parasha_page`), and the route
is gone.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from test_parasha_page import built  # noqa: F401  (the real build, as a fixture)

from targum.models import Token
from targum.parasha import build as corpus
from targum.parasha import calendar as cal
from targum.parasha.models import Haftarah, Index, Portion, Week

DIASPORA = cal.Schedule.diaspora
ISRAEL = cal.Schedule.israel

#: A Wednesday in the week of Bereshit 5787, read on Shabbat 10 October 2026.
BERESHIT_WEEK = datetime(2026, 10, 7, 12, tzinfo=ZoneInfo(cal.FLIP_ZONE))


def portion(slug: str, number: int | None, *, haftarah: str = "") -> Portion:
    return Portion(
        slug=slug,
        name=slug.capitalize(),
        hebrew=f"he-{slug}",
        kind=cal.ReadingKind.parasha if number else cal.ReadingKind.festival,
        numbers=[number] if number else [],
        summary=f"{slug} 1:1-2:2",
        folder=slug,
        haftarah=haftarah,
    )


def week(day: str, slug: str, schedule: cal.Schedule = DIASPORA, haftarah: str = "") -> Week:
    return Week(day=day, schedule=schedule, slug=slug, haftarah=haftarah)


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    return tmp_path / "parasha"


def on_disk(root: Path, index: Index, *, unbuilt: tuple[str, ...] = ()) -> Index:
    """Give every folder in the index a reader, so `readable` counts it, and write the
    index where the server reads it."""
    folders = [one.folder for one in index.portions.values()]
    folders += [one.folder for one in index.haftarot.values() if one.folder]
    for folder in folders:
        if folder in unbuilt:
            continue
        reader = root / "read" / folder / "reader"
        reader.mkdir(parents=True, exist_ok=True)
        (reader / "index.html").write_text("<html></html>", encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.json").write_text(index.model_dump_json(), encoding="utf-8")
    return index


def cycle() -> Index:
    """Bereshit to Lech-Lecha, the end of the year, and the weeks around Bereshit."""
    index = Index()
    for slug, number in [
        ("bereshit", 1),
        ("noach", 2),
        ("lech-lecha", 3),
        ("haazinu", 53),
        ("vezot-haberakhah", 54),
    ]:
        index.portions[slug] = portion(slug, number, haftarah=f"h-{slug}")
    index.portions["sukkot-shabbat-chol-ha-moed"] = portion("sukkot-shabbat-chol-ha-moed", None)
    index.haftarot["h-bereshit"] = Haftarah(
        key="h-bereshit", summary="Isaiah 42:5-43:10", folder="haftarah-h-bereshit"
    )
    for schedule in (DIASPORA, ISRAEL):
        index.weeks += [
            week("2026-09-26", "haazinu", schedule),
            week("2026-10-03", "sukkot-shabbat-chol-ha-moed", schedule),
            week("2026-10-10", "bereshit", schedule),
            week("2026-10-17", "noach", schedule),
            week("2026-10-24", "lech-lecha", schedule),
            # And Bereshit again a year on, which is further from this week.
            week("2027-10-02", "bereshit", schedule),
            week("2027-10-09", "noach", schedule),
        ]
    return index


def test_the_portion_after_bereshit_is_noach(root: Path) -> None:
    index = on_disk(root, cycle())
    after = corpus.following("bereshit", DIASPORA, BERESHIT_WEEK, index)
    assert after is not None and after.slug == "noach"


def test_the_week_after_is_the_calendars_so_a_festival_shabbat_comes_as_it_is_read(
    root: Path,
) -> None:
    """Ha'azinu is followed by the Shabbat of Sukkot, not by וזאת הברכה, which no
    Shabbat reads."""
    index = on_disk(root, cycle())
    after = corpus.following("haazinu", DIASPORA, BERESHIT_WEEK, index)
    assert after is not None and after.slug == "sukkot-shabbat-chol-ha-moed"


def test_the_nearest_occurrence_answers_so_last_weeks_portion_read_late_still_leads_on(
    root: Path,
) -> None:
    index = cycle()
    # Noach a year on is followed by nothing the index holds; this year's by Lech-Lecha.
    on_disk(root, index)
    late = datetime(2026, 10, 21, 12, tzinfo=ZoneInfo(cal.FLIP_ZONE))
    after = corpus.following("noach", DIASPORA, late, index)
    assert after is not None and after.slug == "lech-lecha"


def test_israel_and_the_diaspora_each_get_their_own_next_shabbat(root: Path) -> None:
    """The weeks after Pesach, when Israel reads a portion the diaspora reads a week
    later."""
    index = Index()
    for slug, number in [("shemini", 26), ("tazria", 27), ("metzora", 28)]:
        index.portions[slug] = portion(slug, number)
    index.portions["pesach-viii"] = portion("pesach-viii", None)
    index.weeks = [
        week("2027-04-24", "shemini", ISRAEL),
        week("2027-05-01", "tazria", ISRAEL),
        week("2027-04-17", "shemini", DIASPORA),
        week("2027-04-24", "pesach-viii", DIASPORA),
        week("2027-05-01", "metzora", DIASPORA),
    ]
    on_disk(root, index)
    moment = datetime(2027, 4, 21, 12, tzinfo=ZoneInfo(cal.FLIP_ZONE))
    israel = corpus.following("shemini", ISRAEL, moment, index)
    diaspora = corpus.following("shemini", DIASPORA, moment, index)
    assert israel is not None and israel.slug == "tazria"
    assert diaspora is not None and diaspora.slug == "pesach-viii"


def test_where_the_calendar_is_silent_the_cycle_answers_and_the_year_wraps(root: Path) -> None:
    index = on_disk(root, cycle())
    # No Shabbat reads וזאת הברכה: after it, on Simchat Torah, comes בראשית.
    after = corpus.following("vezot-haberakhah", DIASPORA, BERESHIT_WEEK, index)
    assert after is not None and after.slug == "bereshit"
    # The last week the index holds has nothing after it in the calendar.
    index.weeks = [one for one in index.weeks if one.day < "2027-10-09"]
    on_disk(root, index)
    late = datetime(2027, 9, 29, 12, tzinfo=ZoneInfo(cal.FLIP_ZONE))
    after = corpus.following("bereshit", DIASPORA, late, index)
    assert after is not None and after.slug == "noach"


def test_only_somewhere_a_reader_can_go(root: Path) -> None:
    index = on_disk(root, cycle(), unbuilt=("noach",))
    # Noach has no reader, so neither the calendar nor the cycle may offer it: the cycle
    # goes on to the next built one.
    after = corpus.following("bereshit", DIASPORA, BERESHIT_WEEK, index)
    assert after is not None and after.slug == "lech-lecha"
    assert corpus.following("no-such-folder", DIASPORA, BERESHIT_WEEK, index) is None


def test_a_haftarah_leads_to_the_shabbat_after_the_one_that_reads_it(root: Path) -> None:
    index = on_disk(root, cycle())
    after = corpus.following("haftarah-h-bereshit", DIASPORA, BERESHIT_WEEK, index)
    assert after is not None and after.slug == "noach"
    # And with no week reading it, the portion it belongs to and the cycle after that.
    index.weeks = []
    on_disk(root, index)
    after = corpus.following("haftarah-h-bereshit", DIASPORA, BERESHIT_WEEK, index)
    assert after is not None and after.slug == "noach"


def test_a_portions_words_are_counted_the_way_the_reader_counts_them() -> None:
    """Each word once by its dictionary form; names and numbers are not vocabulary."""

    def token(lemma: str, pos: str = "NOUN", entity: str | None = None) -> Token:
        return Token(start=0, end=1, surface=lemma, lemma=lemma, band=2, pos=pos, entity=entity)

    cut = SimpleNamespace(
        annotation=SimpleNamespace(
            tokens={
                "s1": [token("ארץ"), token("שמים"), token("ארץ")],
                "s2": [token("שבעה", pos="NUM"), token("נח", pos="PROPN"), token("ברא", "VERB")],
            }
        )
    )
    assert corpus.vocabulary(cut) == sorted(["ארץ", "שמים", "ברא"])  # type: ignore[arg-type]
    assert corpus.vocabulary(SimpleNamespace(annotation=None)) == []  # type: ignore[arg-type]


def test_a_corpus_built_before_the_words_file_has_no_count_rather_than_none(root: Path) -> None:
    index = on_disk(root, cycle())
    noach = index.portions["noach"]
    assert corpus.lemmas_of(noach) is None
    (root / "read" / "noach" / corpus.LEMMAS).write_text('["ארץ", "תבה"]', encoding="utf-8")
    assert corpus.lemmas_of(noach) == ["ארץ", "תבה"]


def test_the_build_writes_each_portions_words_beside_its_reader(built: Index) -> None:  # noqa: F811
    assert built.portions
    for one in built.portions.values():
        words = json.loads((cal.root() / "read" / one.folder / corpus.LEMMAS).read_text("utf-8"))
        assert words == sorted(set(words)), one.slug
        assert corpus.lemmas_of(one) == words
    # The fixture's book has one word, אתם, on every verse it has.
    assert corpus.lemmas_of(built.portions["nitzavim-vayeilech"]) == ["אתם"]


def test_the_reader_asks_nobody_what_next_shabbat_is() -> None:
    """targum-internal#446: next Shabbat is the portion page's alone, so the reader has no
    question to put and the server no route to answer it."""
    from targum import serve

    assets = Path(serve.__file__).parent / "render" / "assets" / "reader.js"
    script = assets.read_text("utf-8")
    assert "/parasha/next/" not in script and "next-shabbat" not in script
    assert not hasattr(serve, "PARASHA_NEXT")
