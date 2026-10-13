"""Russian verbs of motion (`annotate/motion.py`), a hard spot in `stages.HARD_SPOTS`."""

from __future__ import annotations

from targum.annotate.motion import PAIRS, motion_of


def test_each_verb_of_a_pair_names_the_way_it_goes_and_the_other() -> None:
    assert motion_of("идти") == "one:ходить"
    assert motion_of("ходить") == "both:идти"
    assert motion_of("е́хать") == "one:ездить", "a stressed dictionary form is the same verb"
    assert motion_of("Возить") == "both:везти"


def test_a_prefixed_verb_and_every_other_word_carry_nothing() -> None:
    """A prefix makes an ordinary aspect pair, which the partner line already names."""
    for lemma in ("прийти", "приходить", "уехать", "читать", "дом", ""):
        assert motion_of(lemma) == ""


def test_the_pairs_are_fourteen_and_no_verb_is_in_two() -> None:
    verbs = [verb for pair in PAIRS for verb in pair]
    assert len(PAIRS) == 14 and len(set(verbs)) == 28
