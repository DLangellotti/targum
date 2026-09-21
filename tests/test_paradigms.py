"""The conjugation table on the card (targum-internal#300).

Most of this is about what it refuses to draw. A wrong conjugation table is worse than
none — the reader has no way to tell it is wrong, and the way out to Pealim is still on
the card — so an ambiguous lookup answers nothing rather than guessing.

The interesting case is that Hebrew makes the commonest verbs ambiguous *unpointed*:
`הלך` is both `הָלַךְ` and `הִלֵּךְ`. Refusing all of those would have left the table off
most of the verbs a reader meets. The points break the tie.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

from targum.annotate.paradigms import (
    BINYAN_ORDER,
    SIBLINGS,
    TABLE,
    Form,
    Paradigm,
    Table,
    bare,
    binyan_of,
    family_of,
    table,
)


@pytest.fixture(scope="module")
def shipped() -> Table:
    """The real table, as the wheel carries it."""
    return table()


def test_the_table_ships_in_the_package() -> None:
    """A reader fetches nothing (§11), so the data has to be inside the wheel."""
    assert TABLE.is_file(), "paradigms.json.gz is missing from the package"
    with gzip.open(TABLE, "rt", encoding="utf-8") as raw:
        loaded = json.load(raw)
    assert loaded["licence"] == "CC0-1.0", "the licence is the reason this source was chosen"
    assert loaded["source"] == "wikidata-lexemes"


def test_a_verb_is_found_by_its_lemma(shipped: Table) -> None:
    found = shipped.of("אמר")
    assert found is not None
    assert found.lemma == "אָמַר"
    assert len(found.forms) > 20, "a Hebrew verb has about thirty-three forms"


def test_a_verb_is_found_though_the_two_sources_call_it_different_things(
    shipped: Table,
) -> None:
    """The measurement that made this source usable. DICTA lemmatizes `בוא`, `מות`,
    `קום`; Wikidata's lemma is the 3ms past `בא`, `מת`, `קם`. Matching lemma to lemma
    finds a fifth of the verbs; matching against any form finds most of them."""
    for dicta, wikidata in (("בוא", "בָּא"), ("מות", "מֵת"), ("קום", "קָם")):
        found = shipped.of(dicta)
        assert found is not None, f"{dicta} should reach {wikidata}"
        assert bare(found.lemma) == bare(wikidata)


def test_the_points_settle_a_verb_two_binyanim_share(shipped: Table) -> None:
    """Unpointed `הלך` is both `הָלַךְ` (went) and `הִלֵּךְ` (walked about)."""
    assert shipped.of("הלך") is None, "unpointed, it is genuinely two verbs"
    went = shipped.of("הלך", "הָלַךְ")
    about = shipped.of("הלך", "הִלֵּךְ")
    assert went is not None and about is not None
    assert went.lemma != about.lemma


def test_points_that_do_not_settle_it_draw_nothing(shipped: Table) -> None:
    """A spelling that matches neither candidate is not a reason to pick one."""
    assert shipped.of("הלך", "הָלְכָה־שֶׁלֹּא־קַיֶּמֶת") is None


def test_a_word_that_is_not_a_verb_has_no_table(shipped: Table) -> None:
    """`יש` is the existential particle. targum-internal#305 stops it being tagged a
    verb at all; this is the second line of defence."""
    assert shipped.of("יש") is None


def test_an_unknown_word_draws_nothing(shipped: Table) -> None:
    assert shipped.of("שאיןכזובמציאות") is None
    assert shipped.of("") is None


def test_the_form_in_front_of_the_reader_is_recognised() -> None:
    """Compared on letters: the reader's pointing and the source's need not agree."""
    form = Form(written="הָלַכְתִּי", features=("past", "1st", "singular"))
    assert form.matches("הלכתי")
    assert form.matches("הָלַכְתִּי")
    assert not form.matches("הָלְכוּ")
    assert not form.matches("")


def test_a_missing_or_broken_table_is_an_empty_one(tmp_path: Path) -> None:
    """The card draws the root, the binyan and the way out to Pealim exactly as before."""
    assert table(tmp_path / "not-here.json.gz").verbs == {}
    broken = tmp_path / "broken.json.gz"
    broken.write_bytes(b"not gzip at all")
    assert table(broken).verbs == {}


def test_a_lemma_belonging_to_no_verb_in_the_table_is_not_invented() -> None:
    made = Table(
        verbs={"1": Paradigm(lemma="א", forms=(Form(written="א", features=()),))},
        by_form={"ב": ("nothing-here",)},
    )
    assert made.of("ב") is None, "an index pointing at a verb that is not there"


def test_object_suffix_forms_are_not_in_the_shipped_table(shipped: Table) -> None:
    """אֲמַרְתִּיו, "I said it" — real Hebrew, 14% of the forms, and not the table a
    learner came for. Dropped so the wheel stays small and the card stays readable."""
    found = shipped.of("אמר")
    assert found is not None
    assert not any(
        any(name.startswith("possessive") for name in form.features) for form in found.forms
    )


# -- the binyan picks between two verbs spelled alike (targum-internal#307) -----------


@pytest.mark.parametrize(
    ("lemma", "expected"),
    [
        ("הָלַךְ", "פעל"),
        ("נָתַן", "פעל"),
        ("נִמְצָא", "נפעל"),
        ("נִכְנַס", "נפעל"),
        ("דִּבֵּר", "פיעל"),
        ("הִלֵּךְ", "פיעל"),
        ("דֻּבַּר", "פועל"),
        ("הִפְעִיל", "הפעיל"),
        ("הִגִּיד", "הפעיל"),
        ("הֻפְעַל", "הופעל"),
        ("הִתְלַבֵּשׁ", "התפעל"),
    ],
)
def test_a_pointed_lemma_says_which_binyan_it_is_built_in(lemma: str, expected: str) -> None:
    """Wikidata carries no binyan statement, so it is read off the lemma — the third
    person masculine singular past, which each binyan spells in its own pattern. This is
    `hebrew.root_of` run the other way, and it is owned outright."""
    assert binyan_of(lemma) == expected


@pytest.mark.parametrize("lemma", ["אוחזר", "שלח", "בא", "א", ""])
def test_an_unpointed_lemma_is_refused_rather_than_read_as_paal(lemma: str) -> None:
    """The dump carries pointed and unpointed lemmas side by side. An unpointed one says
    nothing about its binyan, and the pattern with no marks at all looks like פעל — which
    is exactly the wrong answer to give confidently."""
    assert binyan_of(lemma) is None


@pytest.mark.parametrize("lemma", ["נִסָּה", "הֵבִיא"])
def test_a_pattern_that_is_not_one_of_the_seven_is_refused(lemma: str) -> None:
    """נִסָּה is the פיעל of נ־ס־ה and not a נפעל: its second letter carries no shva, so
    the נ is a radical and not a prefix. Where the shape does not settle it, nothing is
    claimed — the same guard every rule in `hebrew.py` ends at."""
    assert binyan_of(lemma) is None


def two_candidates() -> Table:
    """One bare spelling, two verbs: the shape that made this necessary."""
    paal = Paradigm(lemma="הָלַךְ", forms=(Form(written="הָלַכְתִּי", features=("1st", "past")),))
    piel = Paradigm(lemma="הִלֵּךְ", forms=(Form(written="הִלַּכְתִּי", features=("1st", "past")),))
    return Table(verbs={"a": paal, "b": piel}, by_form={"הלך": ("a", "b")})


def test_the_binyan_picks_between_two_verbs_spelled_alike() -> None:
    """`הלך` is both הָלַךְ and הִלֵּךְ. The source cannot say which; the binyan targum
    worked out for the word can."""
    shelf = two_candidates()
    assert shelf.of("הלך") is None, "nothing to go on"
    assert (found := shelf.of("הלך", binyan="פעל")) is not None and found.lemma == "הָלַךְ"
    assert (found := shelf.of("הלך", binyan="פיעל")) is not None and found.lemma == "הִלֵּךְ"


def test_a_binyan_no_candidate_is_built_in_settles_nothing() -> None:
    """Neither of them is a הופעל, so neither is the answer. A binyan that matches none
    is not a reason to fall back on the other one."""
    assert two_candidates().of("הלך", binyan="הופעל") is None


def test_where_the_two_signals_disagree_neither_is_taken() -> None:
    """Measured over the built shelf, both signals decide for 971 verb tokens and they
    disagree on 126 of them — a נפעל lemma whose surface is spelled the way its פעל
    cousin spells one. The honest answer there is the one the card gives for a root it
    could not work out."""
    shelf = two_candidates()
    # The pointing names the פעל; the binyan says פיעל.
    assert shelf.of("הלך", seen="הָלַכְתִּי", binyan="פיעל") is None
    # And where they agree, the verb.
    found = shelf.of("הלך", seen="הָלַכְתִּי", binyan="פעל")
    assert found is not None and found.lemma == "הָלַךְ"


def test_the_binyan_lifts_coverage_on_the_shipped_table(shipped: Table) -> None:
    """#307's own measure, in miniature: the commonest ambiguous verbs on the shelf draw
    no table without a binyan and draw one with it. `scripts/measure_conjugations.py` is
    the whole measurement — 55.4% of verb tokens to 72.4%."""
    lifted = 0
    for lemma, binyan in (("נתן", "פעל"), ("דבר", "פיעל"), ("ישב", "פעל")):
        if shipped.of(lemma) is None and shipped.of(lemma, binyan=binyan) is not None:
            lifted += 1
    assert lifted, "none of the three commonest ambiguous verbs was settled by its binyan"


# -- the other verbs built on the same root (targum-internal#301) ---------------------


def test_a_verb_s_family_is_the_other_binyanim_of_its_root() -> None:
    """The front door's own specimen: tapping נִפְגַּשׁ should show פָּגַשׁ and הִפְגִּישׁ.

    Worked out from the same CC0 table the conjugations come from — the lemma gives its
    binyan, the two together give the root — so a family is two rules over a source
    targum may redistribute, and behind no licence door at all.
    """
    family = dict(family_of("נִפְגַּשׁ", "נפעל"))
    assert "פָּגַשׁ" in family and family["פָּגַשׁ"] == "פעל"
    assert "הִפְגִּישׁ" in family and family["הִפְגִּישׁ"] == "הפעיל"
    assert "נִפְגַּשׁ" not in family, "a verb is not its own sibling"


def test_a_family_is_read_in_the_order_a_grammar_teaches() -> None:
    """So it reads the same way every time, rather than in whatever order the dump
    happened to list it."""
    order = [binyan for _, binyan in family_of("כָּתַב", "פעל")]
    assert order == [name for name in BINYAN_ORDER if name in order]
    assert order[0] == "נפעל", "the one after פעל, which is the word itself"


def test_a_verb_spelled_like_its_own_sibling_keeps_it() -> None:
    """כָּתַב and כִּתֵּב are both written כתב. A family filtered on the bare spelling
    would throw away the פיעל for looking like the פעל — which is the very pair this is
    for — so the tapped verb is dropped by its binyan and not by how it is written."""
    family = dict(family_of("כָּתַב", "פעל"))
    assert family.get("כִּתֵּב") == "פיעל"
    assert "כָּתַב" not in family


def test_a_root_that_could_not_be_had_honestly_has_no_family() -> None:
    """The card already hides a root it could not work out, and a guessed family is
    worse than none: a hollow root keeps its middle letter nowhere in קָם."""
    assert family_of("קָם", "פעל") == ()
    assert family_of("אוחזר", "הופעל") == (), "an unpointed lemma says no binyan"
    assert family_of("הָלַךְ", None) == (), "and no binyan is no root"


def test_a_family_is_a_fact_about_a_verb_and_not_a_list() -> None:
    """A root with all seven binyanim exists — כתב has every one — and seven other words
    under a word is a list rather than something said about it."""
    for lemma, binyan in (("כָּתַב", "פעל"), ("הָלַךְ", "פעל"), ("נִפְגַּשׁ", "נפעל")):
        assert len(family_of(lemma, binyan)) <= SIBLINGS


def test_the_coverage_measurement_counts_only_the_language_the_table_is_for(
    tmp_path: Path,
) -> None:
    """`scripts/measure_conjugations.py` answers how many Hebrew verbs get a table, and
    the table is Hebrew's. Run over a directory holding anything else, every foreign verb
    falls into "no candidate" and the answer reads as terrible Hebrew coverage rather
    than as the wrong question having been asked.

    Measured on 2026-09-21 over a mixed video directory: **5.3%**, with `essere`, `avere`
    and `fare` among the commonest "missing Hebrew verbs". The same directory filtered to
    its Hebrew answers **70.2%**, which is the shelf's 72.4% to within two points.
    """
    spec = importlib.util.spec_from_file_location(
        "measure_conjugations",
        Path(__file__).parent.parent / "scripts" / "measure_conjugations.py",
    )
    assert spec is not None and spec.loader is not None
    measure_conjugations = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(measure_conjugations)

    def write(folder: str, language: str, lemma: str) -> None:
        path = tmp_path / folder
        path.mkdir(parents=True, exist_ok=True)
        (path / "annotation.json").write_text(
            json.dumps(
                {"language": language, "tokens": {"1": [{"pos": "VERB", "lemma": lemma}]}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    write("hebrew", "he", "כָּתַב")
    write("italian", "it", "essere")
    write("russian", "ru", "писать")

    tally, _lemmas, skipped = measure_conjugations.measure(tmp_path)
    assert skipped == 2, "the Italian and the Russian are left out, not counted as misses"
    assert sum(tally.values()) == 1
    assert tally["no candidate"] == 0, "and no foreign verb is reported as an unknown Hebrew one"
