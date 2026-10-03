"""Whether scripture reads harder or only older (targum-internal#320): the matched sample
`scripts/sentence_bias.py` draws, and the second wording it asks in. Offline throughout —
the model is never reached, and the shelf is a fixture written here."""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path
from types import ModuleType

import pytest

from targum import sentence_level
from targum.level import ULPAN

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sentence_bias.py"


@pytest.fixture(scope="module")
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sentence_bias", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: A frequency list of four words: two common enough for aleph, one only gimel reaches,
#: and one past every rung.
RANKS = {"בית": 10, "ילד": 20, "ממשלה": 4000, "תהום": 50_000}


def sentence(script: ModuleType, key: str, entry: str, register: str, words: str) -> object:
    return script.Sentence(key, entry, register, key, "folder", tuple(words.split()))


def test_names_and_numbers_are_not_running_words(script: ModuleType) -> None:
    tokens = [
        {"lemma": "ילד", "pos": "NOUN"},
        {"lemma": "דוד", "pos": "PROPN"},
        {"lemma": "שלוש", "pos": "NUM"},
        {"lemma": "משה", "pos": "NOUN", "entity": "B-PER"},
        {"lemma": "", "pos": "NOUN"},
    ]
    assert script.running_words(tokens) == ("ילד",)


def test_a_rung_knows_the_words_its_figure_reaches_and_no_others(script: ModuleType) -> None:
    words = ("בַּיִת", "ילד", "ממשלה", "תהום")
    # Pointed or not, a form is looked up bare, as `frequency.rank` looks it up.
    assert script.share_at(words, RANKS, 0) == 0.5
    gimel = [rung.name for rung in ULPAN].index("gimel")
    assert script.share_at(words, RANKS, gimel) == 0.75
    assert script.share_at((), RANKS, 0) == 0.0
    assert script.profile(words, RANKS)[-1] == 0.75


def test_strata_are_coverage_at_gimel_and_length(script: ModuleType) -> None:
    short_easy = sentence(script, "a", "t", "modern", "בית ילד")
    long_hard = sentence(script, "b", "t", "modern", " ".join(["תהום"] * 30))
    assert script.stratum(short_easy, RANKS) == (len(script.COVERAGE_EDGES), 0)
    assert script.stratum(long_hard, RANKS) == (0, len(script.LENGTH_EDGES))


def test_allotment_follows_capacity_and_never_exceeds_it(script: ModuleType) -> None:
    got = script.allot({"x": 30, "y": 10, "z": 0}, 20)
    assert got == {"x": 15, "y": 5}
    assert script.allot({"x": 3, "y": 2}, 20) == {"x": 3, "y": 2}
    assert script.allot({}, 5) == {}
    odd = script.allot({"x": 1, "y": 1, "z": 1}, 2)
    assert sum(odd.values()) == 2 and all(n <= 1 for n in odd.values())


def test_a_stratum_is_spread_across_texts(script: ModuleType) -> None:
    rows = [sentence(script, f"long{i}", "long", "biblical", "בית") for i in range(20)]
    rows += [sentence(script, f"short{i}", f"t{i}", "biblical", "בית") for i in range(3)]
    got = script.spread(rows, 6, random.Random(1))
    # Three of the long book at most: the three short texts each give one first.
    assert sum(one.entry == "long" for one in got) == 3
    assert len({one.key for one in got}) == 6


def shelf(script: ModuleType) -> list[object]:
    """Scripture that is mostly hard and modern prose that is mostly easy, overlapping
    in two strata, plus a register neither side draws from."""
    rows = []
    for i in range(40):
        rows.append(sentence(script, f"bh{i}", f"gen{i % 4}", "biblical", "תהום תהום בית"))
    for i in range(10):
        rows.append(sentence(script, f"be{i}", f"gen{i % 4}", "biblical", "בית ילד בית"))
    for i in range(5):
        rows.append(sentence(script, f"bm{i}", f"gen{i % 4}", "biblical", "ילד תהום בית"))
    for i in range(30):
        rows.append(sentence(script, f"me{i}", f"news{i % 6}", "modern", "בית ילד ילד"))
    for i in range(5):
        rows.append(sentence(script, f"mh{i}", "essay", "modern", "תהום בית ילד"))
    for i in range(10):
        rows.append(sentence(script, f"r{i}", "mishnah", "rabbinic", "בית ילד בית"))
    return rows


def test_the_groups_are_drawn_even_in_every_stratum_both_reach(script: ModuleType) -> None:
    rows = shelf(script)
    got = script.draw(rows, RANKS, per_group=12, seed=7)
    by_group: dict[str, list[tuple[int, int]]] = {"biblical": [], "modern": []}
    for one in got:
        by_group[one.register].append(script.stratum(one, RANKS))
    # Same count on each side, stratum by stratum.
    assert sorted(by_group["biblical"]) == sorted(by_group["modern"])
    # The all-easy stratum can give 10 a side and the hard-ish one 5: 12 split 8 and 4.
    assert len(by_group["biblical"]) == 12
    # The hard scripture has no modern partner, so none of it is drawn; and the rabbinic
    # register belongs to neither side.
    assert not any(one.key.startswith(("bh", "r")) for one in got)
    # And the same seed draws the same sample.
    assert [one.key for one in script.draw(rows, RANKS, 12, 7)] == [one.key for one in got]
    assert [one.key for one in script.draw(rows, RANKS, 12, 8)] != [one.key for one in got]


def test_a_sample_larger_than_the_overlap_takes_the_overlap(script: ModuleType) -> None:
    got = script.draw(shelf(script), RANKS, per_group=1000)
    assert len(got) == 2 * (10 + 5)


def built(tmp_path: Path) -> Path:
    """One built text: a heading, two paragraphs, and a sentence of names alone."""
    folder = tmp_path / "text"
    folder.mkdir()
    segments = [
        {"id": "h", "block_id": "b0", "kind": "heading", "text": "כותרת"},
        {"id": "s1", "block_id": "b1", "kind": "paragraph", "text": "הילד בבית."},
        {"id": "s2", "block_id": "b1", "kind": "paragraph", "text": "דוד."},
        {"id": "s3", "block_id": "b2", "kind": "paragraph", "text": "הממשלה."},
    ]
    tokens = {
        "h": [{"lemma": "כותרת", "pos": "NOUN"}],
        "s1": [{"lemma": "ילד", "pos": "NOUN"}, {"lemma": "בית", "pos": "NOUN"}],
        "s2": [{"lemma": "דוד", "pos": "PROPN"}],
        "s3": [{"lemma": "ממשלה", "pos": "NOUN"}],
    }
    (folder / "segments.json").write_text(json.dumps({"segments": segments}), "utf-8")
    (folder / "annotation.json").write_text(json.dumps({"tokens": tokens}), "utf-8")
    return folder


def test_a_built_text_gives_its_sentences_keyed_as_the_library_run_keys_them(
    script: ModuleType, tmp_path: Path
) -> None:
    folder = built(tmp_path)
    got = list(script.from_folder(folder, "e", "modern"))
    assert [one.text for one in got] == ["הילד בבית.", "הממשלה."]
    assert got[0].key == sentence_level.key("הילד בבית.")
    assert got[0].words == ("ילד", "בית")
    assert script.blocks_of(folder) == [["הילד בבית.", "דוד."], ["הממשלה."]]


def test_only_the_sampled_sentences_are_asked_against_their_own_passage(
    script: ModuleType, tmp_path: Path
) -> None:
    folder = built(tmp_path)
    wanted = sentence_level.key("הממשלה.")
    sample = [{"key": wanted, "folder": str(folder)}]
    (one,) = script.asks(sample, set())
    _, chunk, asking = one
    assert asking == {wanted}
    assert wanted in chunk.keys
    # An answered sentence is not asked again.
    assert list(script.asks(sample, {wanted})) == []


def test_spearman_reads_order_and_ties(script: ModuleType) -> None:
    assert script.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert script.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert script.ranked([5.0, 1.0, 5.0]) == [2.5, 1.0, 2.5]
    assert script.distribution([0, 0, 8]) == [2, 0, 0, 0, 0, 0, 0, 0, 1]


def test_the_second_wording_takes_the_register_off_the_top_and_nothing_else() -> None:
    plain = sentence_level.PROMPTS["without-register"]
    assert [name for name, _ in plain] == [name for name, _ in sentence_level.LEVELS]
    assert plain[:6] == sentence_level.LEVELS[:6]
    for _, description in plain[6:]:
        lowered = description.lower()
        for word in ("archaic", "rabbinic", "classical", "poetic", "literary", "modern"):
            assert word not in lowered, (word, description)
        for word in ("easier", "harder", "previous", "next level", "than the"):
            assert word not in lowered, (word, description)


def test_the_wording_without_register_is_the_default() -> None:
    assert sentence_level.PROMPT == "without-register"
    assert sentence_level.PROMPTS["without-register"] is sentence_level.WITHOUT_REGISTER
    assert sentence_level.PROMPTS["situations"] is sentence_level.LEVELS
    (chunk,) = sentence_level.chunks([["שלום."]])
    _, questions = sentence_level.request(chunk)
    _, old = sentence_level.request(chunk, prompt="situations")
    (default,) = questions.values()
    (other,) = old.values()
    assert default["criteria"] == [text for _, text in sentence_level.WITHOUT_REGISTER]
    assert other["criteria"] == [text for _, text in sentence_level.LEVELS]


def test_the_compiled_file_says_which_wording_it_holds(tmp_path: Path) -> None:
    to = tmp_path / "levels.json"
    sentence_level.write({"k": sentence_level.Level(1, 1.2, 0.5)}, to, "m")
    assert json.loads(to.read_text("utf-8"))["prompt"] == "without-register"
    sentence_level.write({}, to, "m", "situations")
    assert json.loads(to.read_text("utf-8"))["prompt"] == "situations"
