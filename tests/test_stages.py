"""A language's badge is a promise, checked (design.md §12, 2026-10-12; targum-internal#445).

The one table is `stages.DECLARED`. These tests hold every claim in it to the facts the
code, the committed evals and the shelf snapshot show, print the one kept exception's
shortfall so it is read on every run, and refuse a second table anywhere.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import warnings
from pathlib import Path

import pytest

from targum import evals, levelmap, stages
from targum.stages import DECLARED, HARD_SPOTS, KEPT, SHELF, Facts, Floor, Stage

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "targum" / "render" / "assets"


def test_the_three_words_are_in_order() -> None:
    assert list(stages.ORDER) == [Stage.experimental, Stage.alpha, Stage.beta]
    assert Stage.experimental < Stage.alpha < Stage.beta
    assert Stage.beta >= Stage.alpha


def test_every_language_targum_reads_wears_a_word_and_no_other_does() -> None:
    assert set(DECLARED) == stages.reading_codes()


def test_declared_is_earned_for_every_language_not_kept() -> None:
    """The gate. A claim that outruns the facts fails here, with the shortfall named; the
    way through is the facts, never the table."""
    for code, worn in DECLARED.items():
        if code in KEPT:
            continue
        known = stages.facts(code)
        short = stages.shortfall(known, worn)
        assert not short, f"{code} wears {worn.value} but is short: {short}"
        assert (stages.earned(known) or Stage.experimental) >= worn


def test_the_kept_exception_is_named_dated_and_its_shortfall_is_read() -> None:
    """Hebrew kept its Beta by decision from 2026-10-12 and earned it on 2026-10-14, so
    nothing is kept now. An entry has a date, a review date not yet passed, and a reason,
    and this prints what the kept word still owes so it is seen on every run. Past the
    review date the entry fails until renewed with a new date and a design.md line, or
    removed."""
    assert not set(KEPT), "a kept language needs a design.md entry first"
    for code, held in KEPT.items():
        assert held.stage == DECLARED[code]
        assert held.since <= dt.date.today(), code
        assert held.why.strip(), code
        assert held.review >= dt.date.today(), (
            f"{code}: the kept {held.stage.value} passed its review date {held.review}; "
            "renew it with a new date and a design.md line, or remove it"
        )
        short = stages.shortfall(stages.facts(code), held.stage)
        warnings.warn(
            f"{code} wears {held.stage.value}, kept until {held.review}; still owes: {short}",
            stacklevel=1,
        )


def test_hebrew_earns_the_beta_it_wears() -> None:
    """The exception came out on 2026-10-14: the read-through of ten and the reading for
    blockers went on record, and Hebrew is held to the facts like every other language."""
    assert DECLARED["he"] is Stage.beta
    assert stages.earned(stages.facts("he")) is Stage.beta


def test_a_claim_that_outruns_the_facts_is_refused_with_the_criterion_named() -> None:
    known = stages.facts("fr")
    short = stages.shortfall(known, Stage.alpha)
    assert any(line.startswith("hard spot not covered") for line in short), short
    assert "no read-through of 10 texts on record" in short
    assert stages.earned(known) is Stage.experimental


def _all_good(language: str = "ru") -> Facts:
    spots = HARD_SPOTS[language]
    return Facts(
        language=language,
        reads=True,
        lemmatiser=True,
        ladder=True,
        talk=True,
        voice=True,
        shelf={level: Floor(100, 40) for level in stages.CEFR_LEVELS},
        covered={spot.name: True for spot in spots},
        practices={spot.name: True for spot in spots},
        read_through=True,
        known_issues=True,
        builds_unattended=True,
        chat_evals=True,
        second_medium=True,
        growing=True,
        no_blocker=True,
    )


def test_every_criterion_holding_earns_beta() -> None:
    assert stages.earned(_all_good()) is Stage.beta
    assert stages.shortfall(_all_good(), Stage.beta) == []


@pytest.mark.parametrize(
    ("flip", "drops_to", "said"),
    [
        (dict(lemmatiser=False), Stage.experimental, "a lemma floor is breached"),
        (dict(lemmatiser=None), Stage.experimental, "no lemma floors named"),
        (dict(ladder=False), Stage.experimental, "no ladder"),
        (dict(talk=False), Stage.experimental, "does not talk it"),
        (dict(voice=False), Stage.experimental, "no voice"),
        (dict(shelf=None), Stage.experimental, "shelf not measured"),
        (dict(read_through=False), Stage.experimental, "no read-through"),
        (dict(known_issues=False), Stage.experimental, "no known-issues list"),
        (dict(builds_unattended=False), Stage.alpha, "unattended"),
        (dict(chat_evals=False), Stage.alpha, "no chat evals"),
        (dict(second_medium=False), Stage.alpha, "no second medium"),
        (dict(growing=False), Stage.alpha, "grows the shelf"),
        (dict(no_blocker=False), Stage.alpha, "blockers"),
    ],
)
def test_each_criterion_alone_decides(flip: dict[str, object], drops_to: Stage, said: str) -> None:
    known = _all_good()
    for name, value in flip.items():
        setattr(known, name, value)
    assert stages.earned(known) is drops_to, flip
    missing = stages.shortfall(known, Stage.beta)
    assert any(said in line for line in missing), (said, missing)


def test_one_uncovered_hard_spot_holds_a_language_at_experimental() -> None:
    known = _all_good()
    first = HARD_SPOTS["ru"][0].name
    known.covered[first] = False
    assert stages.earned(known) is Stage.experimental
    assert f"hard spot not covered: {first}" in stages.shortfall(known, Stage.alpha)


def test_one_missing_practice_holds_a_language_at_alpha() -> None:
    known = _all_good()
    last = HARD_SPOTS["ru"][-1].name
    known.practices[last] = False
    assert stages.earned(known) is Stage.alpha
    assert f"no practice for: {last}" in stages.shortfall(known, Stage.beta)


def test_a_shelf_short_at_one_level_is_said_by_level_and_kind() -> None:
    known = _all_good()
    assert known.shelf is not None
    known.shelf["B1"] = Floor(35, 14)
    assert stages.earned(known) is Stage.experimental
    short = stages.shortfall(known, Stage.alpha)
    assert "shelf at B1: 35 texts of 36" in short
    # Fourteen recordings meet Alpha's floor; Beta's floor of 35 is the next line.
    assert "shelf at B1: 14 recordings of 14" not in short
    assert "shelf at B1: 14 recordings of 35" in stages.shortfall(known, Stage.beta)


def test_alpha_floors_are_under_betas_at_every_level() -> None:
    for level, floor in SHELF[Stage.alpha].items():
        above = SHELF[Stage.beta][level]
        assert floor.texts < above.texts and floor.recordings < above.recordings, level


def test_every_hard_spot_list_is_five_to_eleven_or_empty_and_ranked_names_are_distinct() -> None:
    """Five to seven from the research of 2026-10-11, and up to eleven since design.md §12
    lengthened the list past Beta ("Past Beta, the badge drops", 2026-10-14: Hebrew's seven
    become eleven)."""
    for code, spots in HARD_SPOTS.items():
        assert len(spots) == 0 or 5 <= len(spots) <= 11, (code, len(spots))
        assert len({spot.name for spot in spots}) == len(spots), code
    assert HARD_SPOTS["yi"] == () and HARD_SPOTS["arc"] == ()


def test_a_covered_hard_spot_names_a_floor_that_exists() -> None:
    """Covered is computed, shown and measured with a floor. The floor a spot names must
    be in evals/floors.json, or the spot is drawn and not measured, which is not covered."""
    limits = evals.floors(stages.FLOORS)
    for code, spots in HARD_SPOTS.items():
        for spot in spots:
            covered = stages._covered(spot, limits)
            if spot.floor is None or not spot.computed_at_all or not spot.shown_at_all:
                assert not covered, (code, spot.name)
                continue
            assert covered, (
                f"{code}: {spot.name} names a floor {spot.floor} that is not in floors.json"
            )


def test_hebrews_hard_spots_are_all_covered() -> None:
    """All of Hebrew's are computed, shown and measured with a floor: six since
    2026-10-12, governed prepositions and et since 2026-10-13, read off the stored
    syntax and scored against the IAHLT treebank's case-marked arguments, and the
    vav-consecutive since 2026-10-21 (targum-internal#449)."""
    known = stages.facts("he")
    uncovered = [name for name, done in known.covered.items() if not done]
    assert uncovered == [], uncovered
    short = stages.shortfall(known, Stage.alpha)
    assert not any(line.startswith("hard spot not covered") for line in short), short


def test_the_cefr_mapping_counts_what_the_library_measures() -> None:
    """A1 is the Easy spec in full, A2 the rest of Easy, B1 Simplified, and Native is one
    level (David, 2026-10-12); recordings are audio and video."""
    shelf = levelmap.Shelf("xx")
    shelf.cells[("aleph", "text")] = 4
    shelf.cells[("aleph", "audio")] = 6
    shelf.cells[("bet", "video")] = 2
    shelf.cells[("gimel", "text")] = 10
    shelf.cells[("gimel", "audio")] = 1
    shelf.easy["audio"] = 5
    assert levelmap.cefr_rows(shelf) == {
        "A1": (5, 5),
        "A2": (5, 1),
        "B1": (2, 2),
        "B2+": (11, 1),
    }


def test_the_shelf_snapshot_round_trips(tmp_path: Path) -> None:
    counts = {"he": {"A1": Floor(84, 84), "B2+": Floor(102, 22)}}
    path = tmp_path / "shelf.json"
    stages.write_shelf(counts, measured=dt.date(2026, 10, 12), videos={"he": 88}, path=path)
    assert stages.read_shelf(path) == counts
    assert stages.read_videos(path) == {"he": 88}
    assert stages.read_videos(tmp_path / "none.json") == {}
    assert json.loads(path.read_text())["measured"] == "2026-10-12"
    assert stages.read_shelf(tmp_path / "none.json") == {}


def test_there_is_no_second_table() -> None:
    """`lang.js` carried its own list and `prompts.py` another, and they disagreed about
    Hebrew on the same day. The page's table is written from `stages.DECLARED`."""
    lang_js = (ASSETS / "lang.js").read_text(encoding="utf-8")
    assert "var STATUS" not in lang_js
    assert "window.TARGUM_STAGES" in lang_js
    prompts = (ROOT / "src" / "targum" / "translate" / "prompts.py").read_text(encoding="utf-8")
    assert "STAGE_LABELS =" not in prompts and "def stage_label" not in prompts
    assert '("arc", "R&D")' not in prompts and '("he", "alpha")' not in prompts
    nav = (ROOT / "src" / "targum" / "render" / "templates" / "_nav.html.j2").read_text()
    assert "window.TARGUM_STAGES = {{ stage_table()|safe }}" in nav


def test_every_desk_page_carries_the_table() -> None:
    from targum.render.builder import add_page, library_page, list_page, progress_page

    for html in (add_page("k"), list_page("k", "texts"), progress_page("k"), library_page("k")):
        found = re.search(r"window\.TARGUM_STAGES = (\{[^;]*\});", html)
        assert found, "the page does not carry the stage table"
        assert json.loads(found.group(1)) == {code: s.value for code, s in DECLARED.items()}


def test_the_shortfall_is_said_plainly() -> None:
    for code in DECLARED:
        for line in stages.shortfall(stages.facts(code), Stage.beta):
            assert "!" not in line and "—" not in line, line
            assert line == line.strip() and line[0].islower(), line


def test_the_report_row_says_kept_and_review(monkeypatch: pytest.MonkeyPatch) -> None:
    since, review = dt.date(2026, 10, 12), dt.date(2026, 12, 31)
    held = stages.Kept(Stage.beta, since=since, review=review, why="x")
    monkeypatch.setitem(stages.KEPT, "he", held)
    row = stages.report("he")
    assert row["declared"] == "beta" and row["kept"] is True and row["review"] == "2026-12-31"
    monkeypatch.delitem(stages.KEPT, "he")
    row = stages.report("he")
    assert row["declared"] == "beta" and row["kept"] is False and row["shortfall"] == []
    row = stages.report("fr")
    assert row["declared"] == "experimental" and row["kept"] is False and row["shortfall"] == []


TODAY = dt.date(2026, 10, 13)
TEN = tuple(f"text-{n}" for n in range(10))


def test_the_record_is_read_from_its_dated_entries() -> None:
    """The read-through, the list and the reading for blockers are facts once entered
    with their dates (2026-10-13); nothing at all is none of them."""
    whole = stages.Record(
        read=TEN,
        read_through=dt.date(2026, 10, 1),
        issues_listed=dt.date(2026, 10, 12),
        blockers_read=dt.date(2026, 10, 13),
        where="targum-internal abc1234",
    )
    known = stages.facts("ru", record=whole, today=TODAY)
    assert (known.read_through, known.known_issues, known.no_blocker) == (True, True, True)
    bare = stages.facts("ru", record=stages.Record(), today=TODAY)
    assert (bare.read_through, bare.known_issues, bare.no_blocker) == (False, False, False)


def test_a_read_through_names_ten_distinct_texts() -> None:
    nine = stages.Record(read=(*TEN[:9], TEN[0]), read_through=dt.date(2026, 10, 1))
    assert not stages.facts("ru", record=nine, today=TODAY).read_through


def test_a_reading_for_blockers_goes_stale() -> None:
    """A list read once is not a list read before the next stranger arrives."""
    read = stages.Record(issues_listed=dt.date(2026, 8, 1), blockers_read=dt.date(2026, 8, 1))
    assert not stages.facts("ru", record=read, today=TODAY).no_blocker
    days = dt.timedelta(days=stages.BLOCKERS_FRESH)
    assert stages.facts("ru", record=read, today=dt.date(2026, 8, 1) + days).no_blocker
    unlisted = stages.Record(blockers_read=TODAY)
    assert not stages.facts("ru", record=unlisted, today=TODAY).no_blocker


def test_every_record_is_a_declared_language_and_says_where_it_lives() -> None:
    for code, record in stages.RECORDED.items():
        assert code in DECLARED, code
        dated = (record.read_through, record.issues_listed, record.blockers_read)
        if any(dated):
            assert record.where.startswith("targum-internal "), (code, record.where)
        if record.read_through is not None:
            assert len(set(record.read)) >= stages.READ_THROUGH_TEXTS, code


def test_the_second_medium_is_video_and_not_a_text_read_aloud() -> None:
    """A text with a recording is the same text; the second medium is a video
    (design.md §12). A snapshot that never counted videos says nothing either way."""
    assert stages.facts("he", videos={"he": 3}).second_medium is True
    assert stages.facts("he", videos={"he": 0}).second_medium is False
    assert stages.facts("he", videos={}).second_medium is None


# -- registers (design.md §12, "Past Beta, the badge drops", 2026-10-14) ---------------


def _vav() -> stages.HardSpot:
    (spot,) = [one for one in HARD_SPOTS["he"] if one.name == "the vav-consecutive"]
    return spot


def test_the_vav_consecutive_is_covered_for_biblical_text_and_declared_out_of_modern() -> None:
    """targum-internal#449: ויאמר is past. Claimed in Biblical text, declared out of modern
    with the reason beside it, and covered: read off the pointing, on the card and a lens,
    with precision and recall floors against Open Scriptures' own tag."""
    spot = _vav()
    assert spot.registers == ("biblical",)
    ((register, why),) = spot.declared_out
    assert register == "modern" and "modern Hebrew does not use" in why
    assert spot.lens and spot.shown == "card"
    assert stages.facts("he").covered["the vav-consecutive"]
    limits = evals.floors(stages.FLOORS)
    for metric in ("vav_precision", "vav_recall"):
        assert any(
            f.system == "vav-rule/1" and f.corpus == "oshb-wlc" and f.metric == metric
            for f in limits
        ), metric
    held = evals.breaches(evals.read(stages.LEDGER), limits)
    assert not [b for b in held if b.floor.corpus == "oshb-wlc"], held


def test_governed_prepositions_are_covered_for_modern_text_and_declared_out_of_biblical() -> None:
    """targum-internal#454: the spot is read off the stored syntax, and Biblical text
    carries almost none. Claimed in modern text, declared out of Biblical with the reason,
    and still covered by its IAHLT floor."""
    (spot,) = [s for s in stages.HARD_SPOTS["he"] if s.name == "governed prepositions and et"]
    assert spot.registers == ("modern",)
    ((register, why),) = spot.declared_out
    assert register == "biblical" and "almost no syntax" in why
    assert stages.facts("he").covered["governed prepositions and et"]


def test_a_declaration_without_a_reason_or_out_of_every_register_is_not_covered() -> None:
    from dataclasses import replace

    limits = evals.floors(stages.FLOORS)
    spot = _vav()
    assert stages._covered(spot, limits)
    assert not stages._covered(replace(spot, declared_out=(("modern", " "),)), limits)
    everywhere = (("modern", "not here"), ("biblical", "nor here"))
    assert not stages._covered(replace(spot, declared_out=everywhere), limits)
    assert not stages._covered(replace(spot, declared_out=(("rabbinic", "a reason"),)), limits)
    assert replace(spot, declared_out=()).registers == stages.REGISTERS


def _suffixes() -> stages.HardSpot:
    (spot,) = [one for one in HARD_SPOTS["he"] if one.name == "pronoun suffixes"]
    return spot


def test_pronoun_suffixes_are_covered_in_both_registers_with_a_floor_each() -> None:
    """targum-internal#450: שלו, אותך, לפניהם. Claimed in modern and Biblical text, on the
    card and a lens, and measured in each against its own gold: IAHLT for modern, Open
    Scriptures for Biblical, precision and recall in floors.json."""
    spot = _suffixes()
    assert spot.registers == ("modern", "biblical")
    assert not spot.declared_out
    assert spot.lens and spot.shown == "card"
    assert dict(spot.floors).keys() == {"modern", "biblical"}
    assert stages.facts("he").covered["pronoun suffixes"]
    limits = evals.floors(stages.FLOORS)
    for system, corpus in (
        ("dicta/dicta-il/dictabert-joint", "iahltknesset"),
        ("suffix-rule/1", "oshb-wlc"),
    ):
        for metric in ("suffix_precision", "suffix_recall"):
            assert any(
                f.system == system and f.corpus == corpus and f.metric == metric for f in limits
            ), (corpus, metric)
    held = evals.breaches(evals.read(stages.LEDGER), limits)
    assert not [b for b in held if b.floor.metric.startswith("suffix_")], held


def test_a_spot_claimed_in_two_registers_needs_a_floor_in_each() -> None:
    from dataclasses import replace

    limits = evals.floors(stages.FLOORS)
    spot = _suffixes()
    modern = dict(spot.floors)["modern"]
    assert not stages._covered(replace(spot, floors=(("modern", modern),)), limits)
    nowhere = ("suffix-rule/1", "oshb-wlc", "no_such_metric")
    assert not stages._covered(
        replace(spot, floors=(("modern", modern), ("biblical", nowhere))), limits
    )
    # Declared out of Biblical, the modern floor would be enough.
    out = replace(spot, floors=(("modern", modern),), declared_out=(("biblical", "a reason"),))
    assert stages._covered(out, limits)


def test_targum_stages_prints_each_spot_and_where_it_is_claimed() -> None:
    from typer.testing import CliRunner

    from targum.cli import app

    result = CliRunner().invoke(app, ["stages"], env={"COLUMNS": "400"})
    assert result.exit_code == 0, result.output
    assert "he: hard spots" in result.output
    (line,) = [one for one in result.output.splitlines() if "the vav-consecutive" in one]
    assert "yes" in line
    assert "Biblical only, not modern: modern Hebrew does not use the form" in line
    (root,) = [one for one in result.output.splitlines() if "root and binyan" in one]
    assert "modern and Biblical" in root
    # Pronoun suffixes, covered in both (targum-internal#450).
    (suffix,) = [one for one in result.output.splitlines() if "pronoun suffixes" in one]
    assert "yes" in suffix and "modern and Biblical" in suffix and "only" not in suffix
    # Registers are Hebrew's; Russian's spots say none.
    (aspect,) = [one for one in result.output.splitlines() if "│ aspect " in one]
    assert "Biblical" not in aspect
