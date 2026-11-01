"""The estimate of the words a reader has not marked, and the chooser that goes by it
(design.md §12, "The chooser estimates the words you have not marked", 2026-11-01;
targum-internal#613)."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from targum import catalogue as catalogue_module
from targum import coverage, touchstones
from targum import estimate as est
from targum import level as level_module
from targum.accounts import Person, Store
from targum.chat import tools
from targum.coverage import IGNORED, KNOWN, build_index, write_index

#: Hebrew words by how common they are: two of the commonest, one in the thousands, and
#: one wordfreq has never ranked.
COMMON = ("של", "זה")
MIDDLE = "מקלדת"
RARE = "קוואזר"


def signed_in(store: Store, email: str = "reader@example.com") -> Person:
    signed = store.finish_sign_in(store.start_sign_in(email))
    assert signed is not None
    return signed[0] if isinstance(signed, tuple) else signed


@pytest.fixture(autouse=True)
def fresh() -> None:
    est.forget()


def test_commoner_words_are_likelier_known() -> None:
    known = est.Estimate("he", est.prior(None), {})
    assert known.chance(COMMON[0]) > known.chance(MIDDLE) > known.chance(RARE)
    assert est.difficulty(RARE, "he") == pytest.approx(math.log(est.UNRANKED_AT))


def test_a_mark_always_wins() -> None:
    known = est.Estimate("he", 20.0, {"ים": KNOWN, "בית": 2, "דוד": IGNORED})
    assert known.p_known("ים") == 1.0
    assert known.p_known("בית") == 0.0, "a word being learned still costs the reader"
    assert known.p_known("דוד") is None, "an ignored word is out of every total"
    assert 0.9 < known.p_known(COMMON[0]) < 1.0  # type: ignore[operator]


def test_a_language_with_no_frequency_list_estimates_nothing() -> None:
    known = est.Estimate("yi", 20.0, {}, ranked=False)
    assert known.chance("של") == 0.0


def test_evidence_is_one_item_a_word_and_never_a_clitic() -> None:
    items = est.evidence(
        [
            ("ים", KNOWN, ""),
            ("בית", 1, ""),
            ("דוד", IGNORED, ""),
            ("כ", 1, ""),
            ("ספר", KNOWN, "claimed"),
        ],
        looked_up={"ים", "מקלדת", "ל"},
        met={"ים", "מקלדת", "שולחן"},
    )
    said = {item.lemma: item for item in items}
    assert set(said) == {"ים", "בית", "ספר", "מקלדת", "שולחן"}
    assert said["ים"].known and said["ים"].weight == 1.0, "a mark since a look-up wins"
    assert not said["בית"].known
    assert not said["מקלדת"].known, "looked up, never marked: not known, once"
    assert said["שולחן"].known and said["שולחן"].weight == est.SKIP_WEIGHT
    assert said["ספר"].guess == est.CLAIM_GUESS and said["ים"].guess == 0


def test_theta_rises_with_rarer_known_words_and_falls_with_look_ups() -> None:
    centre = est.prior(None)
    commonest = [est.Evidence(word, True) for word in COMMON]
    plus_middle = [*commonest, est.Evidence(MIDDLE, True)]
    looked = [*commonest, est.Evidence(MIDDLE, False), est.Evidence("שולחן", False)]
    assert est.fit(plus_middle, "he", centre) > est.fit(commonest, "he", centre)
    assert est.fit(looked, "he", centre) < est.fit(commonest, "he", centre)
    assert est.fit([], "he", centre) == pytest.approx(centre, abs=1e-3), "nothing: the prior"


def test_a_tick_on_the_claim_grid_counts_for_less_than_a_mark() -> None:
    """A tick costs nothing, so a rare word ticked is partly a guess."""
    centre = est.prior(None)
    marked = [est.Evidence(MIDDLE, True), est.Evidence(RARE, True)]
    ticked = [replace(item, guess=0.3) for item in marked]
    assert est.fit(ticked, "he", centre) < est.fit(marked, "he", centre)


def test_the_prior_is_the_rung_named_until_one_is_measured() -> None:
    named = replace(level_module.EMPTY, language="he", here=None, declared="gimel")
    assert est.prior(named) == pytest.approx(math.log(4500) + est.FORMS_PER_LEMMA)
    measured = replace(named, here=level_module.ULPAN[1])
    assert est.prior(measured) == pytest.approx(math.log(900) + est.FORMS_PER_LEMMA)
    assert est.prior(None) == pytest.approx(math.log(est.PRIOR_WORDS) + est.FORMS_PER_LEMMA)


def test_a_readers_estimate_is_fitted_again_after_a_sync_and_kept_between(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    person = signed_in(store)
    alone = est.for_reader(store, person.id, "he")
    assert alone.evidence == 0 and alone.theta == pytest.approx(est.prior(None))
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": word, "status": KNOWN, "at": 1, "seen": 1}
                for word in (*COMMON, MIDDLE)
            ]
        },
    )
    first = est.for_reader(store, person.id, "he")
    assert first.evidence == 3 and first.theta > alone.theta
    assert est.for_reader(store, person.id, "he") is first, "kept until something changes"
    with store.write() as db:
        db.execute(
            "INSERT INTO event (person, kind, day, at, language, word)"
            " VALUES (?, 'lookup', '2026-11-01', 1, 'he', ?)",
            (person.id, "שולחן"),
        )
    looked = est.for_reader(store, person.id, "he")
    assert looked is not first and looked.theta < first.theta
    assert est.for_reader(None, None, "he").evidence == 0, "no account: the prior alone"


def index_of(texts: dict[str, dict[str, int]]) -> Any:
    return build_index({entry: list(counts) for entry, counts in texts.items()}, texts)


def test_expected_coverage_counts_an_unmarked_word_at_its_chance() -> None:
    index = index_of({"t": {"ים": 8, "של": 1, "קוואזר": 1}})
    marked = {"ים": KNOWN}
    known = est.Estimate("he", est.prior(None), marked)
    chances = known.chances(index)
    statuses = index.statuses(marked)
    running = index.running("t", marked, statuses)
    assert running is not None and running.known == pytest.approx(0.8), "the page's number"
    expected = index.expected("t", statuses, chances)
    assert expected == pytest.approx(0.8 + 0.1 * known.chance("של") + 0.1 * known.chance(RARE))
    assert index.expected("missing", statuses, chances) is None


def test_another_languages_words_get_nought_from_a_hebrew_estimate() -> None:
    index = index_of({"t": {"ים": 1, "дом": 1}})
    chances = est.Estimate("he", 20.0, {}).chances(index)
    by_word = dict(zip(index.words, chances, strict=True))
    assert by_word["дом"] == 0.0 and by_word["ים"] > 0.99


# -- the chooser -------------------------------------------------------------------------


def entry(id_: str) -> catalogue_module.Entry:
    return catalogue_module._entry(
        {
            "id": id_,
            "title": id_,
            "language": "he",
            "source": f"test:{id_}",
            "kind": "story",
            "register": "modern",
            "words": 100,
            "difficulty": 10,
        }
    )


@pytest.fixture
def shelf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Two texts a reader has marked the same 80% of: one whose other words are mostly
    the commonest in the language, one whose other words nobody has ranked."""
    entries = [entry("rare-rest"), entry("common-rest")]
    lemmas = tmp_path / "lemmas.json"
    write_index(
        lemmas,
        index_of(
            {
                "rare-rest": {"ים": 16, "קוואזר": 2, "פלזמה": 2},
                "common-rest": {"ים": 16, "של": 3, "קוואזר": 1},
            }
        ),
    )
    monkeypatch.setattr(catalogue_module, "everything", lambda: list(entries))
    monkeypatch.setattr(catalogue_module, "lemmas_path", lambda: lemmas)
    monkeypatch.setattr(tools, "_collections", lambda: {})
    monkeypatch.setattr(tools, "_shelf", lambda ctx, measured=True: ([], []))
    store = Store(tmp_path / "words.db")
    person = signed_in(store)
    store.push(
        person, {"words": [{"language": "he", "lemma": "ים", "status": KNOWN, "at": 1, "seen": 1}]}
    )

    class Ctx:
        level = replace(level_module.EMPTY, language="he")

    ctx = Ctx()
    ctx.store = store  # type: ignore[attr-defined]
    ctx.person = person  # type: ignore[attr-defined]
    ctx.person_id = person.id  # type: ignore[attr-defined]
    return ctx, entries, lemmas


def test_the_chooser_goes_by_the_estimate_and_the_card_by_the_marks(shelf: Any) -> None:
    ctx, _, _ = shelf
    got = tools.suggest_next(ctx, {"limit": 2})["suggestions"]
    assert [row["id"] for row in got] == ["common-rest", "rare-rest"], (
        "the same marks, but its unmarked words are ones a reader very likely knows"
    )
    top = got[0]
    assert top["running_share"] == 0.8, "the page still says what was marked"
    assert top["because"] == "You know 80% of the words here."
    assert top["expected_share"] > 0.9 and top["fit"] == "band"
    assert got[1]["expected_share"] < 0.9 and got[1]["fit"] == "under"


def test_progress_chooses_on_the_estimate_and_says_the_marked_share(shelf: Any) -> None:
    ctx, entries, lemmas = shelf
    index = coverage.read_index(lemmas)
    marked = ctx.store.marked(ctx.person, "he")
    chances = est.for_reader(ctx.store, ctx.person_id, "he").chances(index)
    assert touchstones.at_level(entries, index, marked, "he") == [], "marks alone: none fits"
    listed = touchstones.at_level(entries, index, marked, "he", chances=chances)
    assert [(row["id"], row["known"]) for row in listed] == [("common-rest", 80)]


# -- a built text in running words -------------------------------------------------------


def built(folder: Path, lemmas: list[str]) -> Path:
    folder.mkdir(parents=True)
    tokens = [{"lemma": lemma, "pos": "NOUN"} for lemma in lemmas]
    (folder / coverage.ANNOTATION).write_text(
        json.dumps({"tokens": {"0001.001-a": tokens}}, ensure_ascii=False), encoding="utf-8"
    )
    return folder


def test_a_built_text_is_measured_in_running_words(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", ["ים"] * 9 + ["בית", "ו"])
    running = coverage.running_against(folder, {"ים": KNOWN})
    assert running is not None
    assert running.known == pytest.approx(0.9) and running.total == 10, "the clitic is out"
    distinct = coverage.against(folder, {"ים": KNOWN})
    assert distinct is not None and distinct.known == pytest.approx(1 / 3)
    assert coverage.running_against(tmp_path / "nothing", {}) is None


def test_a_cache_from_before_the_counts_is_read_again_once(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", ["ים", "ים", "בית"])
    assert coverage.lemmas(folder) == ["בית", "ים"]
    cached = json.loads((folder / coverage.LEMMAS).read_text(encoding="utf-8"))
    del cached["counts"]
    (folder / coverage.LEMMAS).write_text(json.dumps(cached), encoding="utf-8")
    assert coverage.lemmas(folder) == ["בית", "ים"], "still good for the forms"
    assert coverage.tally(folder) == {"ים": 2, "בית": 1}
    again = json.loads((folder / coverage.LEMMAS).read_text(encoding="utf-8"))
    assert again["counts"] == {"ים": 2, "בית": 1}
