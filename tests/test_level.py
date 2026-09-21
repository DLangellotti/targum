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
    words = [(int(w["status"]), str(w["band"])) for w in given["words"]]  # type: ignore[index]
    assert theirs["common"] == level.common(words), "the same count of common words"


def test_the_cefr_is_climbed_by_known_words_among_the_commonest() -> None:
    """Measured for French (Milton and Alexiou 2009), borrowed for Russian and Italian. A
    hard word is not among the commonest five thousand, so it does not count here, and a
    name or a number never counts anywhere."""
    words = [(level.KNOWN, "easy")] * 1500 + [(level.KNOWN, "moderate")] * 499
    words += [(level.KNOWN, "hard")] * 800 + [(level.KNOWN, "name")] * 50 + [(2, "easy")] * 40
    assert level.common(words) == 1999
    here, following = level.standing(level.common(words), level.CEFR)
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
    assert "12 days read" in told and "streak of 3" in told
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

    worst = 0.0
    for _ in range(5):
        started = time.perf_counter()
        level.known_share(page, forms)
        worst = max(worst, (time.perf_counter() - started) * 1000)
    assert worst < 50.0, f"known_share took {worst:.1f} ms on a 500-word page"


def test_the_share_is_said_in_words_never_a_percentage() -> None:
    assert level.words_in_ten(0.72) == "You know about 7 words in 10 here."
    assert level.words_in_ten(0.12) == "You know about 1 word in 10 here."
    assert level.words_in_ten(0.97) == "You know nearly every word here."
    assert level.words_in_ten(0.02) == "You know almost none of the words here yet."
    assert level.words_in_ten(None) == ""
    assert "%" not in level.words_in_ten(0.5)


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


def test_the_chat_grades_to_the_seed_and_never_quotes_it() -> None:
    told = level.describe(
        level.Level("he", 0, 0, 0.0, None, level.ULPAN[0], 0, 0, 0, 0, 0, declared="gimel")
    )
    assert "'gimel' rung" in told and "no measured rung yet" in told
    assert "never quote it back" in told
    # The state a page is handed carries no trace of it: nothing can print it.
    shown = level.Level("he", 0, 0, 0.0, None, level.ULPAN[0], 0, 0, 0, 0, 0, declared="gimel")
    assert "gimel" not in json.dumps(shown.state())
