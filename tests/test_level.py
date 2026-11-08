"""The ulpan ladder, now in two places, and the fixture that keeps them one.

`level.py` is `charts.js` ported so the chat can read a rung on the server. A port is a
copy, and a copy drifts, so `tests/fixtures/level.json` holds one ledger with the answer
both must give — checked here in Python and, where node is installed, against the
browser's own code.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from targum import level
from targum.accounts import Store

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "level.json"
CHARTS = Path(__file__).resolve().parents[1] / "src" / "targum" / "render" / "assets" / "charts.js"


def fixture() -> dict[str, object]:
    return dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_the_python_ladder_gives_the_fixture_s_answer() -> None:
    given = fixture()
    words = [(int(w["status"]), str(w["band"])) for w in given["words"]]  # type: ignore[index]
    weighted, known = level.reach(words)
    assert weighted == pytest.approx(given["weighted"])
    assert known == given["known"]
    here, following = level.standing(weighted)
    assert (here.name if here else "") == given["here"]
    assert (following.name if following else "") == given["next"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_browser_s_ladder_gives_the_same_answer() -> None:
    """`charts.js` run under node against the same words. The ladder's weights, its
    rungs and its filter for names are all in that one file; if any of them moves, this
    is the test that says the server disagrees."""
    given = fixture()
    script = f"""
      global.window = {{}};
      global.document = {{ createElement: () => ({{ style: {{}}, setAttribute() {{}} }}) }};
      require({json.dumps(str(CHARTS))});
      const charts = window.TargumCharts;
      const words = {json.dumps(given["words"], ensure_ascii=False)};
      const got = charts.reach(words);
      const stood = charts.standingIn(got.weighted);
      console.log(JSON.stringify({{
        weighted: got.weighted, known: got.words,
        here: stood.here ? stood.here.name : "", next: stood.next ? stood.next.name : "",
        rungs: charts.ULPAN.map(r => [r.at, r.name]),
        cefr: charts.CEFR.map(r => [r.at, r.name]),
        equivalents: charts.ULPAN.map(r => r.cefr),
        ladders: Object.fromEntries(
          Object.entries(charts.LADDERS).map(([k, v]) => [k, [v.title, v.measure]])
        ),
        common: charts.common(words),
      }}));
    """
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    theirs = json.loads(done.stdout)
    assert theirs["weighted"] == pytest.approx(given["weighted"])
    assert theirs["known"] == given["known"]
    assert theirs["here"] == given["here"]
    assert theirs["next"] == given["next"]
    assert theirs["rungs"] == [[rung.at, rung.name] for rung in level.ULPAN], "the rungs"
    assert theirs["cefr"] == [[rung.at, rung.name] for rung in level.CEFR], "the CEFR levels"
    assert theirs["equivalents"] == [rung.cefr for rung in level.ULPAN]
    assert theirs["ladders"] == {
        code: [ladder.title, ladder.measure] for code, ladder in level.LADDERS.items()
    }
    words = [("", int(w["status"]), str(w["band"])) for w in given["words"]]  # type: ignore[index]
    # The browser counts by band, which is Hebrew's rule; French, Russian and Italian are
    # counted by lemma on the server (`common_lemmas.json`), which no page carries.
    assert theirs["common"] == level.common(words, "he"), "the same count of common words"


def test_the_cefr_is_climbed_by_known_words_among_the_commonest() -> None:
    """Measured for French (Milton and Alexiou 2009), borrowed for Russian and Italian. A
    hard word is not among the commonest five thousand, so it does not count here, and a
    name or a number never counts anywhere. By band where a language has no lemma
    table, as Hebrew has none."""
    words = [("", level.KNOWN, "easy")] * 1500 + [("", level.KNOWN, "moderate")] * 499
    words += [("", level.KNOWN, "hard")] * 800 + [("", level.KNOWN, "name")] * 50
    words += [("", 2, "easy")] * 40
    assert level.common(words, "he") == 1999
    here, following = level.standing(level.common(words, "he"), level.CEFR)
    assert here is not None and here.name == "A2" and following is not None
    assert following.name == "B1" and following.at == 2000
    here, _ = level.standing(2000, level.CEFR)
    assert here is not None and here.name == "B1"
    assert level.ladder_for("fr-FR") is level.CEFR_LADDER
    assert level.ladder_for("he") is level.ULPAN_LADDER
    assert level.ladder_for("yi") is None and level.ladder_for("arc") is None


def test_the_chat_is_told_the_reader_s_ladder_in_their_language() -> None:
    french = level.Level(
        "fr", 2100, 10, 2500.0, level.CEFR[2], level.CEFR[3], 3, 1, 2, 4, 1, "CEFR level", 2050
    )
    said = level.describe(french)
    assert said.startswith("The reader is learning French.")
    assert "about B1 on the CEFR" in said and "B2 wants about 2,400" in said
    assert "Never tell the reader they are 'at a level'" in said
    hebrew = level.Level("he", 400, 0, 400.0, level.ULPAN[0], level.ULPAN[1], 0, 0, 0, 0, 0)
    assert "'aleph' rung of the ulpan ladder (about A1 on the CEFR)" in level.describe(hebrew)
    yiddish = level.Level("yi", 10, 0, 10.0, None, None, 0, 0, 0, 0, 0, "", 0)
    assert "no level ladder" in level.describe(yiddish)


def test_a_streak_counts_back_from_today_or_from_yesterday() -> None:
    today = date(2026, 9, 5)
    assert level.streaks(["2026-09-03", "2026-09-04", "2026-09-05"], today) == (3, 3)
    assert level.streaks(["2026-09-03", "2026-09-04"], today) == (2, 2), "not yet today"
    assert level.streaks(["2026-09-01", "2026-09-02"], today) == (0, 2), "broken, but longest kept"
    assert level.streaks(["2026-09-05", "not a day"], today) == (1, 1)
    assert level.streaks([], today) == (0, 0)


def test_a_snapshot_reads_the_account(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    token = store.start_sign_in("reader@example.com")
    signed = store.finish_sign_in(token)
    assert signed is not None
    person = signed[0]
    store.push(
        person,
        {
            "words": [
                {
                    "language": "he",
                    "lemma": "שלום",
                    "status": 9,
                    "band": "easy",
                    "at": 5,
                    "seen": 5,
                },
                {"language": "he", "lemma": "רעב", "status": 2, "band": "hard", "at": 6, "seen": 6},
                {"language": "he", "lemma": "דוד", "status": 9, "band": "name", "at": 7, "seen": 7},
            ],
            "days": [
                {"day": "2026-09-04", "count": 1, "seen": 1},
                {"day": "2026-09-05", "count": 1, "seen": 1},
            ],
        },
    )
    got = level.snapshot(store, person.id, "he", today=date(2026, 9, 5))
    assert (got.known, got.learning) == (1, 1), "a name is neither known nor learned"
    assert got.days == 2 and got.streak == 2 and got.longest == 2
    assert got.here is None and got.next is not None and got.next.name == "aleph"
    assert level.snapshot(store, None, "he") == level.EMPTY


def test_the_description_quotes_counts_and_refuses_to_place() -> None:
    told = level.describe(
        level.Level("he", 1240, 87, 2000.0, level.ULPAN[2], level.ULPAN[3], 12, 3, 9, 31, 4)
    )
    assert "1,240 words marked known" in told
    assert "12 days read" in told and "longest run of days 9" in told
    # design.md §12: the current streak is refused, here as everywhere.
    assert "streak" not in told
    assert "'bet'" in told, "the rung is given, for grading"
    assert "not a placement" in told and "Never tell the reader" in told
    assert "!" not in told


# -- the cheap known-share estimate (targum-internal#244) ----------------------------


def test_known_share_counts_a_known_word_with_or_without_its_prefix() -> None:
    forms = {"ילד", "הלך", "בית", "ספר"}
    text = " ".join(["הילד הלך לבית ספר והספר טוב מאוד"] * 4)  # 28 tokens, over the floor
    share = level.known_share(text, forms)
    assert share is not None
    # הילד, הלך, לבית, ספר, והספר count; טוב and מאוד do not: five of seven.
    assert abs(share - 5 / 7) < 1e-9
    assert level.known_share("שָׁלוֹם " * 25, {"שלום"}) == 1.0, "points are stripped first"
    assert level.known_share("שלום עולם", {"שלום"}) is None, "too short to say"
    assert level.known_share("hello " * 40, {"שלום"}) is None, "no Hebrew, nothing measured"


def test_known_share_reads_russian_as_words_when_asked_to() -> None:
    """2026-10-06: Russian publishers' items are measured in Russian, where the Hebrew
    rule finds no token and answers "not measured"."""
    text = " ".join(["Ёлка стояла в парке, и дети пели"] * 4)  # 28 tokens
    forms = {"елка", "парке", "дети", "в"}
    assert level.known_share(text, forms) is None, "the Hebrew rule, as before"
    share = level.known_share(text, forms, "ru")
    # Ёлка (ё read as е, case folded), в, парке, дети count; стояла, и, пели do not.
    assert share is not None and abs(share - 4 / 7) < 1e-9
    assert level.known_share("дети в парке", forms, "ru") is None, "too short to say"


def test_known_share_answers_a_page_inside_its_budget() -> None:
    """targum-internal#244, acceptance criterion 2: `known_share` on a 500-word page runs
    under 50 ms.

    It is a budget rather than a benchmark, and it is asserted because of where this
    function is called: on the quote card a reader waits for, and on every row
    `suggest_next` ranks, so a slow one is felt several times in a turn rather than once.
    Nothing pinned it before.

    Measured 2026-09-21 on an 8 GB laptop under load: median 0.32 ms, worst of twenty
    0.36 ms — about 139× inside the budget. The assertion is the card's 50 ms and not the
    measurement, so an ordinarily busy machine cannot make this fail; a regression big
    enough to trip it is a real one.
    """
    import time

    draw = random.Random(1)
    words = [
        "".join(draw.choice("אבגדהוזחטיכלמנסעפצקרשת") for _ in range(draw.randint(2, 7)))
        for _ in range(500)
    ]
    page = " ".join(words)
    forms = set(words[:250]) | {word + "ים" for word in words[:100]}

    # The median of five, not the worst: a shared CI runner once stalled one call for
    # 774 ms (2026-11-03, targum-internal#649), and a stall is the runner, not the code.
    # Slow code is slow in every call, so the median still trips on a real regression.
    took = []
    for _ in range(5):
        started = time.perf_counter()
        level.known_share(page, forms)
        took.append((time.perf_counter() - started) * 1000)
    middle = sorted(took)[2]
    assert middle < 50.0, f"known_share took {middle:.1f} ms on a 500-word page: {took}"


def test_the_share_is_said_as_an_exact_percentage() -> None:
    """David, 2026-10-29 (targum-internal#560): "show exact percentages". No "about" and
    no count in ten."""
    assert level.known_line(0.72) == "You know 72% of the words here."
    assert level.known_line(0.123) == "You know 12% of the words here."
    assert level.known_line(1.0) == "You know 100% of the words here."
    assert level.known_line(0.0) == "You know 0% of the words here."
    assert level.known_line(None) == ""
    for share in (0.05, 0.5, 0.95):
        assert "about" not in level.known_line(share)
        assert " in 10" not in level.known_line(share)


def test_the_percentage_is_never_rounded_into_a_lie() -> None:
    """Under all of it never says 100%, and above none of it never says 0%."""
    assert level.known_percent(0.996) == 99
    assert level.known_percent(0.004) == 1
    assert level.known_percent(0.725) in (72, 73)
    assert level.known_percent(None) is None


def test_the_reader_s_own_ceiling_follows_the_ladder() -> None:
    assert level.ceiling_for(level.EMPTY) == 40
    high = level.Level("he", 4000, 0, 4000.0, None, None, 0, 0, 0, 0, 0)
    assert level.ceiling_for(high) is None
    middle = level.Level("he", 1000, 0, 1000.0, None, None, 0, 0, 0, 0, 0)
    assert level.ceiling_for(middle) == 25


def test_known_share_is_fast_enough_to_ask_at_quote_time() -> None:
    import time

    forms = {f"מילה{n}" for n in range(3000)}
    text = " ".join(f"ומילה{n % 5000}" for n in range(500))
    start = time.perf_counter()
    level.known_share(text, forms)
    assert time.perf_counter() - start < 0.05


def test_the_chat_is_told_how_to_address_the_reader_in_hebrew(tmp_path: Path) -> None:
    """A recast turned a man's unpointed רוצה into רוֹצָה and called it corrected, and the
    same reply called him אַתָּה (2026-09-14). Nothing had told the model either way: now
    the account says, and a reader who has not said is addressed without a guess."""
    store = Store(tmp_path / "words.db")
    store.start_sign_in("reader@example.com")
    person = store.person_by_email("reader@example.com")
    assert person is not None
    assert store.address(person.id) == ""
    assert "do not choose a gender" in level.describe(level.snapshot(store, person.id, "he"))
    store.set_address(person, "f")
    assert store.profile(person)["address"] == "f"
    said = level.describe(level.snapshot(store, person.id, "he"))
    assert "as a woman" in said and "אַתְּ" in said
    store.set_address(person, "m")
    assert "as a man" in level.describe(level.snapshot(store, person.id, "he"))
    with pytest.raises(ValueError):
        store.set_address(person, "x")


def test_the_rung_a_reader_said_is_a_seed_and_a_measured_one_outvotes_it(tmp_path: Path) -> None:
    """targum-internal#306, its fifth state (design.md §12, 2026-09-19).

    Asked on arrival and kept on the account. It stands in while nothing about the reader
    has been measured, and the first rung their own marked words reach retires it.
    """
    store = Store(tmp_path / "words.db")
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    person = signed[0]

    assert store.declared(person.id) == ""
    assert level.seed(level.snapshot(store, person.id, "he")) is None, (
        "nothing said, nothing seeded"
    )

    assert store.set_declared(person, "Bet-Plus ") == "bet-plus"
    got = level.snapshot(store, person.id, "he")
    seeded = level.seed(got)
    assert seeded is not None and seeded.name == "bet plus"
    assert got.here is None, "saying it measures nothing: the ledger's own rung is untouched"
    # Asked over the ulpan ladder, so it says nothing about another language.
    assert level.seed(level.snapshot(store, person.id, "fr")) is None

    with pytest.raises(ValueError):
        store.set_declared(person, "fluent")
    assert store.profile(person)["declared"] == "bet-plus", "handed back to a second browser"

    measured = level.Level(
        "he", 400, 0, 400.0, level.ULPAN[0], level.ULPAN[1], 3, 1, 1, 2, 1, declared="vav"
    )
    assert level.seed(measured) is None, "vav was said, and their words say aleph"

    assert store.set_declared(person, "") == "", "and it can be taken back"


def test_each_language_keeps_its_own_declared_rung(tmp_path: Path) -> None:
    """qa-claude on targum#1112 (targum-internal#631): one rung for every language let a
    Hebrew aleph reader who then named "I'm just starting" in Russian store a1 in its
    place, and lose Hebrew's seed and the scene card with it. Each language keeps its own
    rung now, on its own ladder, in the same column."""
    from dataclasses import replace

    from targum.chat import tools

    store = Store(tmp_path / "words.db")
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    person = signed[0]
    store.set_declared(person, "aleph")
    assert store.set_declared(person, "a1", "ru") == "a1"
    assert store.set_declared(person, "b1", "fr-FR") == "b1"
    assert store.declared(person.id) == "aleph", "Hebrew's is not replaced"
    assert store.declared(person.id, "ru") == "a1" and store.declared(person.id, "fr") == "b1"
    assert store.profile(person)["declaredBy"] == {"he": "aleph", "ru": "a1", "fr": "b1"}
    hebrew = level.snapshot(store, person.id, "he")
    assert hebrew.declared == "aleph" and tools.scene_reader(replace(hebrew, here=None))
    seeded = level.seed(level.snapshot(store, person.id, "ru"))
    assert seeded is not None and seeded.name == "A1"
    with pytest.raises(ValueError):
        store.set_declared(person, "a1")
    with pytest.raises(ValueError):
        store.set_declared(person, "gimel", "ru")
    with pytest.raises(ValueError):
        store.set_declared(person, "a1", "it")
    store.set_declared(person, "", "ru")
    assert store.declared_by(person.id) == {"he": "aleph", "fr": "b1"}
    store.set_declared(person, "", "fr")
    row = store.db.execute("SELECT declared FROM person WHERE id = ?", (person.id,)).fetchone()
    assert row["declared"] == "aleph", "a Hebrew-only column is what it always was"


def test_the_chat_grades_to_the_seed_and_never_quotes_it() -> None:
    told = level.describe(
        level.Level("he", 0, 0, 0.0, None, level.ULPAN[0], 0, 0, 0, 0, 0, declared="gimel")
    )
    assert "'gimel' rung" in told and "no measured rung yet" in told
    assert "never quote it back" in told
    # The state a page is handed carries no trace of it: nothing can print it.
    shown = level.Level("he", 0, 0, 0.0, None, level.ULPAN[0], 0, 0, 0, 0, 0, declared="gimel")
    assert "gimel" not in json.dumps(shown.state())


# --- the rung a text needs (design.md §12, 2026-09-24) -----------------------------


def test_a_text_of_the_commonest_words_is_aleph() -> None:
    from targum.level import ULPAN, ULPAN_LADDER, text_rung

    assert text_rung([1, 5, 12, 40, 200] * 20, ULPAN_LADDER) == ULPAN[0]


def test_a_text_full_of_rare_words_is_high() -> None:
    from targum.level import ULPAN, ULPAN_LADDER, text_rung

    assert text_rung([11_000] * 50, ULPAN_LADDER) == ULPAN[-1]
    assert text_rung([None] * 50, ULPAN_LADDER) == ULPAN[-1], "past the list is past every rung"


def test_the_rung_is_read_at_ninety_percent_of_the_running_words() -> None:
    """Ten rare words in a hundred are what the dictionary one tap away is for; eleven
    are not (targum-internal#372: at 95% nearly every text read Vav · C2)."""
    from targum.level import ULPAN_LADDER, text_rung

    easy = [100] * 90 + [8_000] * 10
    harder = [100] * 89 + [8_000] * 11
    assert text_rung(easy, ULPAN_LADDER).name == "aleph"  # type: ignore[union-attr]
    assert text_rung(harder, ULPAN_LADDER).name == "hey"  # type: ignore[union-attr]


def test_a_text_with_no_words_has_no_rung() -> None:
    from targum.level import ULPAN_LADDER, text_rung

    assert text_rung([], ULPAN_LADDER) is None


# -- a rank is not a count: the CEFR's conversion (targum-internal#659) ---------------
#
# The ranks are the ones builder-3 measured on the laptop's built texts (#659). "was" is
# what each read held as a rank against the thresholds; "now" what its count reads,
# C(R) counting the lemmas `common` counts (the commonest 5,000 by summed form
# frequency), against the unchanged thresholds.


@pytest.mark.parametrize(
    ("language", "rank", "was", "now"),
    [
        ("fr", 1_648, "B1", "A2"),  # gsb-asp-0276
        ("fr", 3_376, "C2", "B2"),  # gsb-sbc-0315, C1 under the band count
        ("fr", 5_898, "C2", "C2"),  # daudet-les-etoiles
        ("it", 2_395, "B2", "B1"),  # eu-easy-read
        ("it", 3_568, "C2", "B2"),  # 55347-un-libro-per-puchku
        ("it", 4_611, "C2", "C1"),  # ec-solidarity-norcia
        ("ru", 4_690, "C2", "B1"),  # gsb-lida-0022
    ],
)
def test_a_cefr_text_is_placed_by_count_not_by_rank(
    language: str, rank: int, was: str, now: str
) -> None:
    from targum.level import CEFR, CEFR_LADDER, text_rung

    held_as_rank = next((rung for rung in CEFR if rung.at >= rank), CEFR[-1])
    assert held_as_rank.name == was, "what it read before #659"
    assert text_rung([rank] * 20, CEFR_LADDER, language=language).name == now  # type: ignore[union-attr]


def test_every_cefr_level_can_be_reached_in_every_language() -> None:
    """Counted by lemma, every language's count reaches past C2: Russian's C1 and C2 sat
    above everything the band count could hold (2,663), and no longer do. A text past
    every rung reads C2."""
    from targum.level import CEFR, CEFR_LADDER, count_at, text_rung

    for language in ("fr", "ru", "it"):
        ceiling = count_at(10**9, language)
        assert ceiling is not None and ceiling > CEFR[-1].at
        for ranks in ([19_000] * 20, [None] * 20):
            assert text_rung(ranks, CEFR_LADDER, language=language).name == "C2"  # type: ignore[union-attr]


def test_the_count_rises_with_the_rank_and_stops_at_a_ceiling() -> None:
    from targum.level import COMMON_TOP, count_at

    for language in ("fr", "ru", "it"):
        counts = [count_at(rank, language) for rank in range(0, 21_000, 37)]
        assert counts[0] == 0
        assert all(a <= b for a, b in zip(counts, counts[1:], strict=False))  # type: ignore[operator]
        assert counts[-1] == count_at(10**9, language)
        assert counts[-1] <= COMMON_TOP  # type: ignore[operator]
        # a lemma ranked R in the form list is at worst one of the commonest R lemmas
        assert all(count_at(r, language) <= r for r in range(0, 21_000, 37))  # type: ignore[operator]
    assert count_at(1_000, "he") is None and count_at(1_000, "yi") is None


def test_a_cefr_text_with_no_table_has_no_rung() -> None:
    """No level is better than a made-up one: a rank held against a count is one."""
    from targum.level import CEFR_LADDER, text_rung

    assert text_rung([500] * 20, CEFR_LADDER) is None
    assert text_rung([500] * 20, CEFR_LADDER, language="yi") is None


def test_hebrew_is_held_against_ranks_as_before() -> None:
    """The ulpan's rungs are vocabulary sizes: the language changes nothing there."""
    from targum.level import ULPAN, ULPAN_LADDER, text_rung

    for ranks in ([100] * 90 + [8_000] * 10, [100] * 89 + [8_000] * 11, [11_000] * 50):
        assert text_rung(ranks, ULPAN_LADDER, language="he") == text_rung(ranks, ULPAN_LADDER)
    assert text_rung([1_000] * 20, ULPAN_LADDER, language="he") == ULPAN[2]
    assert text_rung([4_000] * 20, ULPAN_LADDER, language="he") == ULPAN[4]


def test_the_tables_say_they_are_a_conversion() -> None:
    from targum.level import COMMON_TOP, _common_lemmas, _common_table, _rank_counts

    for table in (_rank_counts(), _common_table()):
        assert table["about"].startswith("A conversion, not evidence.")
        assert table["wordfreq"] and table["built"]
        assert set(table["lexicons"]) == {"fr", "ru", "it"}
    assert _common_table()["built"] == _rank_counts()["built"], "built together, agreeing"
    assert set(_rank_counts()["counts"]) == set(_common_lemmas()) == {"fr", "ru", "it"}
    assert _common_table()["top"] == COMMON_TOP
    for language, digests in _common_lemmas().items():
        assert len(digests) >= COMMON_TOP - 2, language  # four bytes: a collision or two


# -- which lemmas are common: the commonest 5,000 by summed form frequency (#659) ------
#
# The words ling-it found the band count missing (2026-11-08), each with its dictionary
# form's Zipf: a lemma's use is spread over its forms, and wordfreq ranks forms.

MISSED_BY_THE_BAND = {
    "fr": ["sembler", "suffire", "préférer", "habiter", "falloir"],  # 3.74 3.63 3.80 3.90
    "it": ["bastare", "riguardare", "significare", "bisognare", "preferire", "abitare"],
    "ru": ["мочь", "хотеть", "должный", "являться", "нравиться"],  # 2.63 3.80 2.87 3.76 4.02
}


@pytest.mark.parametrize("language", ["fr", "it", "ru"])
def test_a_common_lemma_counts_whatever_its_dictionary_form_s_band(language: str) -> None:
    from targum.level import KNOWN, common, is_common

    for lemma in MISSED_BY_THE_BAND[language]:
        assert is_common(lemma, "hard", language), lemma
    words = [(lemma, KNOWN, "hard") for lemma in MISSED_BY_THE_BAND[language]]
    assert common(words, language) == len(words)


@pytest.mark.parametrize(
    ("language", "lemma"),
    [
        ("fr", "être"),
        ("fr", "avoir"),
        ("it", "essere"),
        ("it", "uno"),
        ("ru", "быть"),
        ("ru", "я"),
        ("ru", "он"),
    ],
)
def test_the_commonest_lemmas_are_common(language: str, lemma: str) -> None:
    assert level.is_common(lemma, "easy", language)


def test_a_rare_lemma_is_not_common_whatever_its_band() -> None:
    """The band stored at annotation no longer decides it: a form that is common as a
    form does not make a rare lemma common."""
    for language, lemma in (("fr", "abader"), ("it", "burattino"), ("ru", "барыня")):
        assert not level.is_common(lemma, "easy", language), lemma


def test_a_name_or_a_number_is_never_common() -> None:
    for band in ("name", "number"):
        assert not level.is_common("être", band, "fr")
        assert not level.is_common("שלום", band, "he")


def test_the_lemma_is_looked_up_as_the_table_was_built() -> None:
    """The case, a stress mark, ё, a French reflexive and a curly apostrophe are
    spellings of one key."""
    assert level.lemma_key("Мочь", "ru") == "мочь"
    assert level.lemma_key("ещё", "ru") == level.lemma_key("еще", "ru")
    assert level.lemma_key("хоте\u0301ть", "ru") == "хотеть"
    assert level.lemma_key("se taire", "fr") == level.lemma_key("taire", "fr") == "taire"
    assert level.lemma_key("s\u2019en aller", "fr") == "en aller"
    assert level.lemma_key("aujourd\u2019hui", "fr") == "aujourd'hui"
    assert level.is_common("Хотеть", "hard", "ru") and level.is_common("ещё", "hard", "ru")


def test_hebrew_is_still_counted_by_band() -> None:
    words = [("שלום", level.KNOWN, "easy"), ("מילה", level.KNOWN, "hard")]
    assert level.common(words, "he") == 1
    assert level.is_common("anything", "moderate", "he")


def test_a_reader_s_count_is_read_off_the_lemma(tmp_path: Path) -> None:
    """The account's band is left as it was stored: `snapshot` asks the lemma, so a
    reader's French count moves without re-annotating anything."""
    store = Store(tmp_path / "words.db")
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    person = signed[0]
    marked = [("sembler", "hard"), ("suffire", "hard"), ("abader", "easy"), ("être", "easy")]
    store.push(
        person,
        {
            "words": [
                {"language": "fr", "lemma": lemma, "status": 9, "band": band, "at": 5, "seen": 5}
                for lemma, band in marked
            ]
        },
    )
    found = level.snapshot(store, person.id, "fr")
    assert found.known == 4 and found.common == 3


# -- ktiv haser against known ktiv male (targum-internal#349) ------------------------


def _page(*words: str) -> str:
    return " ".join(list(words) * (level.MEASURABLE // len(words) + 1))


def test_a_haser_token_counts_when_a_known_male_form_gives_it() -> None:
    """Points off a pointed page leave ktiv haser; the known side is ktiv male."""
    assert level.known_share(_page("אֵרוּעִים"), {"אירועים"}) == 1.0
    assert level.known_share(_page("פִּתּוּחַ"), {"פיתוח"}) == 1.0
    assert level.known_share(_page("טְוִיטֶר"), {"טוויטר"}) == 1.0


def test_a_prefixed_haser_token_counts() -> None:
    assert level.known_share(_page("וְהָאֵרוּעִים"), {"אירועים"}) == 1.0
    assert level.known_share(_page("לְפִתּוּחַ"), {"פיתוח"}) == 1.0


def test_a_token_that_needs_a_letter_dropped_does_not_count() -> None:
    """Insertions only: the known form is never shortened to meet the token, and only
    vav and yod go in, never at the first or last letter."""
    # The token has a vav the known form lacks: dropping it is not allowed.
    assert level.known_share(_page("אִירוּעִים"), {"ארעים"}) == 0.0
    # A letter other than vav or yod is missing.
    assert level.known_share(_page("מֶלֶךְ"), {"מלאך"}) == 0.0
    # The first and last letters are the word's own.
    assert level.known_share(_page("אָח"), {"אחי"}) == 0.0
    assert level.known_share(_page("לֵד"), {"ילד"}) == 0.0
    # Same skeleton, but the order of what is left differs.
    assert level.known_share(_page("אֵרוּעִים"), {"אירעים"}) == 0.0


def test_the_haser_rule_is_a_subsequence_not_a_skeleton_match() -> None:
    assert level._haser_of("ארועים", "אירועים")
    assert not level._haser_of("איעים", "אירועים"), "a letter other than vav/yod is missing"
    assert not level._haser_of("אוריעים", "אירועים"), "the token's own vav and yod must fit"
    assert not level._haser_of("אירועים", "אירועים"), "equal is the direct match's job"


def test_the_unpointed_modern_figure_is_unchanged() -> None:
    """An unpointed page is written male already, so it is measured exactly as before:
    the rule is tried only on a token that came with points. Unpointed, קם would take
    credit for a known קיים and פחת for פחות."""
    forms = {"ילד", "הלך", "בית", "ספר"}
    text = " ".join(["הילד הלך לבית ספר והספר טוב מאוד"] * 4)
    assert level.known_share(text, forms) == pytest.approx(5 / 7)
    assert level.known_share(_page("ארועים"), {"אירועים"}) == 0.0
    assert level.known_share(_page("קם"), {"קיים"}) == 0.0


def test_the_declaration_measures_as_it_did() -> None:
    """The one real unpointed modern page in the fixtures, against the common words: the
    count of known tokens is the count the exact rule gives, token for token."""
    from targum.chat import hebrew

    forms = set(hebrew.common_words())
    text = (FIXTURE.parent / "texts" / "il-declaration-1948.he.md").read_text(encoding="utf-8")
    tokens = [t for t in (level._bare(w) for w in level._WORD.findall(text)) if t]
    exact = sum(1 for t in tokens if any(f in forms for f in level._forms_of(t)))
    assert level.known_share(text, forms) == pytest.approx(exact / len(tokens))


# -- words to go (design.md §12, "Your level, v3", 2026-10-29) ------------------------


def test_the_next_word_weighs_what_the_last_thirty_days_weighed() -> None:
    from targum.level import KNOWN, per_word

    day = 24 * 60 * 60 * 1000
    now = 100 * day
    words = [
        (KNOWN, "hard", now - day),  # 1.7, lately
        (KNOWN, "very hard", now - 2 * day),  # 2.2, lately
        (KNOWN, "easy", now - 40 * day),  # 0.8, too long ago to count
        (2, "extremely hard", now),  # still learning: not counted
        (KNOWN, "name", now),  # a name is no vocabulary
    ]
    assert per_word(words, now) == (1.7 + 2.2) / 2


def test_with_nothing_lately_the_next_word_is_the_band_above_most_known() -> None:
    from targum.level import KNOWN, per_word

    day = 24 * 60 * 60 * 1000
    old = [(KNOWN, "easy", 1)] * 5 + [(KNOWN, "fairly easy", 1)] * 2
    assert per_word(old, 100 * day) == 1.0, "most are easy, so fairly easy is next"
    assert per_word([(KNOWN, "extremely hard", 1)], 100 * day) == 2.8, "the top band stays"
    assert per_word([], 100 * day) == 0.8, "a reader with none starts at the commonest"


def test_words_to_go_are_exact_and_rounded_up_to_a_whole_word() -> None:
    """The card's "637 words to ה׳" and the C1 row are the one function: the weighted gap
    over what the next word weighs, never rounded to a figure that looks round."""
    from targum.level import ULPAN, Level, words_to

    dalet, hey = ULPAN[5], ULPAN[6]
    reader = Level("he", 0, 0, 8490.4, dalet, hey, 0, 0, 0, 0, 0, per_word=0.8)
    assert words_to(reader, hey.at) == 637, "509.6 / 0.8 is 637, not 637.0000001 → 638"
    assert words_to(Level("he", 0, 0, 8490.0, dalet, hey, 0, 0, 0, 0, 0, per_word=1.7), 9000) == 300
    assert words_to(reader, dalet.at) == 0, "reached"
    assert words_to(Level("he", 0, 0, 8999.9, dalet, hey, 0, 0, 0, 0, 0, per_word=2.8), 9000) == 1


def test_the_european_scale_counts_its_commonest_words_one_by_one() -> None:
    from targum.level import CEFR, Level, words_to

    reader = Level(
        "fr", 0, 0, 0.0, CEFR[2], CEFR[3], 0, 0, 0, 0, 0, ladder="CEFR level", common=2163
    )
    assert words_to(reader, 2400) == 237
    assert words_to(reader, 2750) == 587
    assert words_to(Level("yi", 0, 0, 0.0, None, None, 0, 0, 0, 0, 0), 250) == 0


def test_the_payload_share_is_the_shown_percentage() -> None:
    """qa on targum#993: rounded to two places, 0.996 reached a page as 1.0 and showed
    100%. The payload carries the percentage `known_percent` said, over a hundred."""
    assert level.page_share(0.996) == 0.99
    assert level.page_share(0.004) == 0.01
    assert level.page_share(1.0) == 1.0 and level.page_share(0.0) == 0.0
    assert level.page_share(None) is None
