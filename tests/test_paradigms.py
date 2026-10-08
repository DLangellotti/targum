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
from typing import Any

import pytest

from targum.annotate.paradigms import (
    BINYAN_ORDER,
    READINGS,
    SIBLINGS,
    TABLE,
    Form,
    Paradigm,
    Table,
    bare,
    binyan_from_forms,
    binyan_of,
    binyan_unpointed,
    family_of,
    opening_of,
    pointed_form,
    present_wanted,
    readings,
    table,
    written_form,
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
        # The guttural and weak patterns, which read as nothing until 2026-09-27.
        ("נֶאֱמַר", "נפעל"),
        ("נַעֲשָׂה", "נפעל"),
        ("נוֹלַד", "נפעל"),
        ("הֵבִיא", "הפעיל"),
        ("הֶעֱמִיד", "הפעיל"),
        ("הוֹלִיךְ", "הפעיל"),
        ("הוּצָא", "הופעל"),
        ("הָחְלַט", "הופעל"),
        ("צִוָּה", "פיעל"),
        ("בֵּרֵךְ", "פיעל"),
        ("בֹּרַךְ", "פועל"),
        # And three the rule had wrong: a ת that is the root's, and a ת that has traded
        # places with the root's first letter.
        ("הִתְקִין", "הפעיל"),
        ("הִסְתַּכֵּל", "התפעל"),
        ("הִשְׁתּוֹלֵל", "התפעל"),
        ("הִסְתִּיר", "הפעיל"),
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


@pytest.mark.parametrize("lemma", ["נִסָּה", "נִתַּן", "נִכָּה", "הֵפֵר", "נוֹפֵף"])
def test_a_pattern_that_is_not_one_of_the_seven_is_refused(lemma: str) -> None:
    """נִסָּה is the פיעל of נ־ס־ה and not a נפעל: its second letter carries no shva, so
    the נ is a radical and not a prefix. But נִתַּן is the נפעל of נ־ת־ן, spelled point
    for point the same way, and was read as a פיעל until 2026-09-27 — so the shape is
    refused rather than guessed. הֵפֵר is a doubled root's הפעיל wearing a פיעל's two
    tseres, and נוֹפֵף is not the נפעל its first two letters look like. Where the shape
    does not settle it, nothing is claimed — the same guard every rule in `hebrew.py`
    ends at."""
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


# -- how targum's own tagging reads a written form (targum-internal#307, 2026-09-27) --


def said() -> Table:
    """`אומר` as the Mishnah writes it: a form of the פעל `אָמַר` and of the הופעל
    `הוּמַר`, which the source cannot tell apart and the annotator tags no binyan on."""
    paal = Paradigm(
        lemma="אָמַר",
        forms=(
            Form(written="אוֹמֵר", features=("participle",)),
            Form(written="אוֹמְרִים", features=("participle",)),
            Form(written="נֹאמַר", features=("future", "1st")),
        ),
    )
    hufal = Paradigm(
        lemma="הוּמַר",
        forms=(
            Form(written="אוּמַר", features=("future", "1st")),
            Form(written="נוּמַר", features=("future", "1st")),
        ),
    )
    return Table(
        verbs={"a": paal, "h": hufal},
        by_form={"אומר": ("a", "h")},
        readings={"אומר": ("אמר", "פעל"), "אומרים": ("אמר", "פעל")},
    )


def test_how_the_shelf_reads_a_form_settles_a_word_with_no_binyan() -> None:
    """Everywhere the annotator did tag `אומר`, it was the פעל of `אמר`; so where it did
    not, the table is `אָמַר`'s."""
    shelf = said()
    assert shelf.of("אומר") is None, "nothing on the page to go on"
    found = shelf.of("אומר", written=("אוֹמֵר", "אוֹמְרִים"))
    assert found is not None and found.lemma == "אָמַר"


def test_a_word_s_own_binyan_is_asked_before_the_shelf() -> None:
    """The reading settles a word with no binyan. One that has its own is settled by it,
    and the reading can only refuse — never overrule it into the other verb."""
    shelf = said()
    found = shelf.of("אומר", binyan="פעל", written=("אוֹמֵר",))
    assert found is not None and found.lemma == "אָמַר"
    assert shelf.of("אומר", binyan="הופעל") is not None, "nothing on the page says otherwise"
    assert shelf.of("אומר", binyan="הופעל", written=("אוֹמֵר",)) is None


def test_a_reading_that_names_no_candidate_refuses() -> None:
    """`אוֹכֵל` "eats" is read as `אכל`. The word's candidates were `יָכֹל` and others,
    and a reading that points outside them is not a reason to take the nearest."""
    shelf = Table(
        verbs=said().verbs,
        by_form={"אומר": ("a", "h")},
        readings={"אומר": ("אכל", "פעל")},
    )
    assert shelf.of("אומר", written=("אומר",)) is None


def test_every_form_on_the_page_has_a_say() -> None:
    """One table is drawn per word per page, so it must be right for all of them: a form
    read as the other verb refuses it, and a form with no reading that the other verb
    also spells refuses it too."""
    shelf = said()
    both = Table(
        verbs=shelf.verbs,
        by_form=shelf.by_form,
        readings={**shelf.readings, "אומר": ("הומר", "הופעל")},
    )
    assert both.of("אומר", written=("אומר", "אומרים")) is None, "read two ways"
    # `נומר` is a form of the הופעל and not of the פעל: it cannot ride along.
    assert shelf.of("אומר", written=("אומר", "נוּמַר")) is None
    # `אומרים` belongs to the פעל alone and has its own reading; `נאמר` is spelled by the
    # פעל alone and has none, so it may ride along.
    found = shelf.of("אומר", written=("אומרים", "נֹאמַר"))
    assert found is not None and found.lemma == "אָמַר"


def test_a_form_read_as_the_other_verb_refuses_what_the_binyan_settled() -> None:
    """The first occurrence's binyan decides for the page, and the annotator files more
    than one verb under one lemma. Where another form of the word on the page is read as
    the other candidate, the table is refused rather than drawn over it."""
    shelf = two_candidates()
    read = Table(
        verbs=shelf.verbs,
        by_form=shelf.by_form,
        readings={"הלכתי": ("הלך", "פיעל")},
    )
    assert read.of("הלך", binyan="פעל") is not None, "nothing on the page says otherwise"
    assert read.of("הלך", binyan="פעל", written=("הִלַּכְתִּי",)) is None
    found = read.of("הלך", binyan="פיעל", written=("הִלַּכְתִּי",))
    assert found is not None and found.lemma == "הִלֵּךְ"


def test_the_form_is_the_verb_without_what_clings_to_it() -> None:
    """Keyed on letters, and on the verb alone: `built` says how a word is put together,
    and the clitics carry their gloss while a suffix is said in English."""
    assert written_form("וַיֹּ֨אמֶר", "ו and + יֹּאמֶר") == "יאמר"
    assert written_form("שנצטרף", "ש that + נצטרף") == "נצטרף"
    assert written_form("וּלְבֵיתוֹ", "ו and + ל to + בית + his") == "בית"
    assert written_form("אוֹמֵר") == "אומר"
    assert written_form("כָּל־אֲשֶׁ֥ר") == "כלאשר", "maqaf and cantillation are not letters"


def test_without_the_readings_the_card_draws_what_it_drew_before(tmp_path: Path) -> None:
    """The readings are private (decided 2026-09-27): gitignored, packed into the wheel,
    and absent from CI's checkout and from every worktree. There, nothing is read and
    nothing fails — the binyan and the pointing settle what they settled before #307."""
    assert readings(tmp_path / "not-here.json") == {}
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    assert readings(broken) == {}
    bare_shelf = Table(verbs=said().verbs, by_form=said().by_form)
    assert bare_shelf.of("אומר", written=("אוֹמֵר", "אוֹמְרִים")) is None
    found = bare_shelf.of("אומר", binyan="פעל", written=("אוֹמֵר",))
    assert found is not None and found.lemma == "אָמַר"


needs_readings = pytest.mark.skipif(
    not READINGS.is_file(),
    reason="binyans.json is private and lives only in the main checkout and the wheel",
)


@needs_readings
def test_the_readings_say_what_they_were_counted_over() -> None:
    """Where the private file is present: counted only over texts that may leave targum
    (#161), and every one of them names exactly one verb in the shipped table — one that
    named none could never settle anything."""
    loaded = json.loads(READINGS.read_text(encoding="utf-8"))
    assert "exportable" in loaded["counted"]["over"]
    assert loaded["least"] >= 20 and loaded["share"] >= 0.95
    lemmas = [(bare(verb.lemma), binyan_of(verb.lemma)) for verb in table().verbs.values()]
    for form, (lemma, binyan, agree, tagged) in loaded["forms"].items():
        assert tagged >= loaded["least"] and agree / tagged >= loaded["share"], form
        assert lemmas.count((lemma, binyan)) == 1, form


@needs_readings
def test_the_readings_lift_the_mishnah_s_commonest_verb(shipped: Table) -> None:
    """`אוֹמֵר` drew no table before #307 took the shelf's own reading of it."""
    assert shipped.of("אומר") is None
    found = shipped.of("אומר", written=("אוֹמֵר", "אוֹמְרִים"))
    assert found is not None and found.lemma == "אָמַר"


def read_as_said(shelf: Table) -> Table:
    """The shipped verbs with the one reading these tests need, so they run the same on
    a checkout that has the private file and one that has not."""
    return Table(
        verbs=shelf.verbs,
        by_form=shelf.by_form,
        readings={"אומר": ("אמר", "פעל"), "אומרים": ("אמר", "פעל")},
    )


def load_script(name: str) -> object:
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parent.parent / "scripts" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_readings_are_counted_once_per_text_and_only_where_it_may_leave(
    tmp_path: Path,
) -> None:
    """The same text is built on several shelves, some by an older annotator; one build
    stands for it, the one with the most tagged verbs. And a text whose licence does not
    let derived data leave is not counted at all."""
    count_binyans: Any = load_script("count_binyans")

    def build(folder: str, source: str, digest: str, tokens: list[dict[str, object]]) -> None:
        path = tmp_path / folder
        path.mkdir(parents=True)
        (path / "document.json").write_text(json.dumps({"source": source}), encoding="utf-8")
        (path / "annotation.json").write_text(
            json.dumps(
                {"language": "he", "document_hash": digest, "tokens": {"s": tokens}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    said_it = {"pos": "VERB", "lemma": "אמר", "binyan": "פעל", "surface": "אוֹמֵר"}
    untagged = {"pos": "VERB", "lemma": "אומר", "surface": "אוֹמֵר"}
    build("new", "sefaria:Mishnah Berakhot", "h1", [said_it, said_it])
    build("old", "sefaria:Mishnah Berakhot", "h1", [said_it, untagged])
    build("closed", "https://news.example/1", "h2", [said_it] * 5)

    counts, tally = count_binyans.count(tmp_path, may_leave=lambda source: "sefaria" in source)
    assert counts["אומר"][("אמר", "פעל")] == 2, "one build of h1, and none of h2"
    assert tally["documents"] == 1 and tally["builds left out: licence"] == 1

    decided = count_binyans.decided(counts, table(), least=2, share=0.95)
    assert decided["אומר"] == ["אמר", "פעל", 2, 2]
    assert count_binyans.decided(counts, table(), least=3) == {}, "too few to believe"


def test_the_coverage_measurement_counts_what_the_readings_settle(tmp_path: Path) -> None:
    """The measurement asks what the builder asks: every form a word takes in the text,
    read the way the shelf reads it. Measured over a whole document rather than a page,
    so a word has more forms to agree on than the builder gives it — a lower bound."""
    measure_conjugations: Any = load_script("measure_conjugations")
    path = tmp_path / "mishnah"
    path.mkdir()
    # Unpointed, as a news page is: pointed, `אוֹמֵר` is settled by its own vowel first.
    tokens = [
        {"pos": "VERB", "lemma": "אומר", "surface": surface} for surface in ("אומר", "אומרים")
    ]
    (path / "annotation.json").write_text(
        json.dumps({"language": "he", "tokens": {"s": tokens}}, ensure_ascii=False),
        encoding="utf-8",
    )
    shelf = read_as_said(table())
    measure_conjugations.table = lambda: shelf
    tally, _lemmas, _skipped = measure_conjugations.measure(tmp_path)
    assert tally["settled by reading"] == 2
    assert "settled by reading" in measure_conjugations.COVERED


# -- a participle, by the tense it was tagged with (targum-internal#307, 2026-09-27) --

#: How the annotator tags a participle: every person at once, and no tense.
PRESENT = "UPOS=VERB|Person=1,2,3|Gender=Masc|Number=Sing"
PRESENT_PLURAL = "UPOS=VERB|Person=1,2,3|Gender=Masc|Number=Plur"
PAST = "UPOS=VERB|Person=3|Gender=Masc|Number=Sing|Tense=Past"


def standing() -> Table:
    """`עומד` as the source has it: the present of the פעל `עָמַד`, and the past of the
    פּוּעַל `עוּמַּד` written in full, whose own present is `מעומד`."""
    paal = Paradigm(
        lemma="עָמַד",
        forms=(
            Form(written="עומד", features=("masculine", "present", "singular")),
            Form(written="עומדים", features=("masculine", "plural", "present")),
            Form(written="עמדתי", features=("1st", "past", "singular")),
        ),
    )
    pual = Paradigm(
        lemma="עומד",
        forms=(
            Form(written="עומד", features=("3rd", "masculine", "past", "singular")),
            Form(written="מעומד", features=("masculine", "present", "singular")),
            Form(written="יעומד", features=("3rd", "future", "masculine", "singular")),
        ),
    )
    return Table(verbs={"a": paal, "p": pual}, by_form={"עומד": ("a", "p")})


@pytest.mark.parametrize(
    ("feats", "wanted"),
    [
        (PRESENT, {"gender": "masculine", "number": "singular"}),
        (
            "UPOS=VERB|Person=3|Gender=Fem|Number=Plur|Tense=Pres",
            {"gender": "feminine", "number": "plural"},
        ),
        ("UPOS=VERB|Gender=Masc,Fem|Number=Sing|Tense=Pres|VerbForm=Part", {"number": "singular"}),
        (PAST, None),
        ("UPOS=VERB|VerbForm=Inf", None),
        ("UPOS=VERB|Person=3|Gender=Masc|Number=Sing", None),
        ("", None),
    ],
)
def test_the_present_is_what_the_annotator_said_it_is(
    feats: str, wanted: dict[str, str] | None
) -> None:
    """Three ways of saying present, and nothing else is taken for one: an occurrence
    whose tense was not said is not guessed to be a participle."""
    assert present_wanted(feats) == wanted


def test_a_participle_takes_the_verb_whose_present_it_is() -> None:
    """The ambiguity #454 left: a participle filed under itself, spelled like another
    verb's past. Tagged present, it is the one whose present it is."""
    shelf = standing()
    assert shelf.of("עומד") is None, "nothing to go on"
    found = shelf.of("עומד", said=(("עומד", PRESENT, "עוֹמֵד"),))
    assert found is not None and found.lemma == "עָמַד"


def test_a_form_tagged_past_or_nothing_names_no_verb() -> None:
    """Only the present is asked. In the past and the future the full and thin
    spellings of different binyanim collide too often to be read on letters."""
    shelf = standing()
    assert shelf.of("עומד", said=(("עומד", PAST, "עומד"),)) is None
    assert shelf.of("עומד", said=(("עומד", "UPOS=VERB", "עומד"),)) is None


def test_a_present_two_verbs_could_spell_refuses() -> None:
    """The Bible writes `נֹתֵן` without its ו, which is letter for letter the נִפְעַל's
    `נִתָּן`. The table writes the פעל's present in full, `נותן`, so on exact letters
    only the נִפְעַל matches — and it is the wrong verb. A present that the other could
    be, spelled fuller or thinner, refuses."""
    paal = Paradigm(
        lemma="נָתַן", forms=(Form(written="נותן", features=("masculine", "present", "singular")),)
    )
    nifal = Paradigm(
        lemma="נִתַּן", forms=(Form(written="נתן", features=("masculine", "present", "singular")),)
    )
    shelf = Table(verbs={"a": paal, "n": nifal}, by_form={"נתן": ("a", "n")})
    assert shelf.of("נתן", said=(("נתן", PRESENT, "נֹתֵן"),)) is None


def test_a_present_another_verb_in_the_table_writes_refuses() -> None:
    """Asked of the whole table, not only of the word's candidates: the verb the reader
    is looking at may be filed elsewhere, and its present spelled the same way is
    reason enough not to choose."""
    shelf = standing()
    stranger = Paradigm(
        lemma="עִמֵּד", forms=(Form(written="עומד", features=("masculine", "present", "singular")),)
    )
    wider = Table(verbs={**shelf.verbs, "x": stranger}, by_form=shelf.by_form)
    assert wider.of("עומד", said=(("עומד", PRESENT, "עומד"),)) is None


def test_every_other_form_of_the_word_on_the_page_must_be_that_verb_s() -> None:
    """One table for the word on the page. A form the present did not settle rides
    along only if the chosen verb writes it and the others do not."""
    shelf = standing()
    ok = shelf.of("עומד", said=(("עומד", PRESENT, "עוֹמֵד"), ("עמדתי", "", "עָמַדְתִּי")))
    assert ok is not None and ok.lemma == "עָמַד"
    # `יעומד` is the פּוּעַל's.
    assert shelf.of("עומד", said=(("עומד", PRESENT, "עוֹמֵד"), ("יעומד", "", "יעומד"))) is None
    # A form neither writes is a word this table knows nothing about.
    assert shelf.of("עומד", said=(("עומד", PRESENT, "עוֹמֵד"), ("עמדנו", "", "עמדנו"))) is None
    # The same letters, where their tense was not said, are the same word.
    same = shelf.of("עומד", said=(("עומד", PRESENT, "עוֹמֵד"), ("עומד", "UPOS=VERB", "עומד")))
    assert same is not None and same.lemma == "עָמַד"


def test_the_mishnah_s_plural_is_the_table_s() -> None:
    """`עוֹמְדִין` is the `עומדים` the table writes."""
    found = standing().of("עומד", said=(("עומדין", PRESENT_PLURAL, "עוֹמְדִין"),))
    assert found is not None and found.lemma == "עָמַד"


def test_a_candidate_with_no_present_in_the_table_cannot_be_ruled_out() -> None:
    """The source's lexemes are not all whole. A candidate with no present at all might
    have had this one, so its silence proves nothing."""
    shelf = standing()
    thin = Paradigm(lemma="עומד", forms=(Form(written="עומד", features=("past",)),))
    assert (
        Table(verbs={**shelf.verbs, "p": thin}, by_form=shelf.by_form).of(
            "עומד", said=(("עומד", PRESENT, "עוֹמֵד"),)
        )
        is None
    )


def test_shin_and_sin_are_two_letters() -> None:
    """`הַפּוֹרֵשׁ` "who parts from" has the letters of `פּוֹרֵשׂ` "who spreads", and the
    source has only the second. The dot says they are different verbs."""
    spread = Paradigm(
        lemma="פָּרַשׂ",
        forms=(Form(written="פורש", features=("masculine", "present", "singular")),),
    )
    pual = Paradigm(
        lemma="פורש",
        forms=(
            Form(written="פורש", features=("3rd", "masculine", "past", "singular")),
            Form(written="מפורש", features=("masculine", "present", "singular")),
        ),
    )
    shelf = Table(verbs={"s": spread, "p": pual}, by_form={"פורש": ("s", "p")})
    assert shelf.of("פורש", said=(("פורש", PRESENT, "פּוֹרֵשׁ"),)) is None
    found = shelf.of("פורש", said=(("פורש", PRESENT, "פּוֹרֵשׂ"),))
    assert found is not None and found.lemma == "פָּרַשׂ"


def test_the_present_refuses_what_another_signal_settled_on_another_verb() -> None:
    """`חוֹשֵׁב` "thinks" is tagged פּוּעַל often enough to settle the wrong table. Where
    the present names one verb and the binyan another, neither is taken."""
    # The unpointed `עומד` is read as a פֻּעַל by its shape (`binyan_unpointed`), which
    # every signal asks since 2026-10-08, and the present still refuses it.
    shelf = standing()
    assert (found := shelf.of("עומד", binyan="פועל")) is not None and found.lemma == "עומד"
    assert shelf.of("עומד", binyan="פועל", said=(("עומד", PRESENT, "עוֹמֵד"),)) is None
    two = Table(
        verbs={
            "a": standing().verbs["a"],
            "p": Paradigm(lemma="עֻמַּד", forms=standing().verbs["p"].forms),
        },
        by_form={"עומד": ("a", "p")},
    )
    assert (found := two.of("עומד", binyan="פועל")) is not None and found.lemma == "עֻמַּד"
    assert two.of("עומד", binyan="פועל", said=(("עומד", PRESENT, "עוֹמֵד"),)) is None


def test_the_present_settles_participles_on_the_shipped_table(shipped: Table) -> None:
    """The measure in miniature, on the real table and with no readings at all — so it
    holds in CI's checkout, where the private readings are absent."""
    bare_shelf = Table(verbs=shipped.verbs, by_form=shipped.by_form)
    for lemma, surface, verb in (("עומד", "עוֹמֵד", "עָמַד"), ("יוצא", "יוֹצֵא", "יָצָא")):
        assert bare_shelf.of(lemma) is None, f"{lemma} was already settled"
        found = bare_shelf.of(lemma, said=((bare(surface), PRESENT, surface),))
        assert found is not None and found.lemma == verb


def test_the_coverage_measurement_counts_what_the_present_settles(tmp_path: Path) -> None:
    """The measurement asks the builder's question with the grammar each form carries."""
    measure_conjugations: Any = load_script("measure_conjugations")
    path = tmp_path / "mishnah"
    path.mkdir()
    # Unpointed: pointed, `עוֹמֵד` is settled by its own vowel before its tense is asked.
    tokens = [
        {"pos": "VERB", "lemma": "עומד", "surface": "עומד", "feats": PRESENT},
        {"pos": "VERB", "lemma": "עומד", "surface": "עומדים", "feats": PRESENT_PLURAL},
    ]
    (path / "annotation.json").write_text(
        json.dumps({"language": "he", "tokens": {"s": tokens}}, ensure_ascii=False),
        encoding="utf-8",
    )
    measure_conjugations.table = standing
    tally, _lemmas, _skipped = measure_conjugations.measure(tmp_path)
    assert tally["settled by the present"] == 2
    assert "settled by the present" in measure_conjugations.COVERED


# -- the pointing, per occurrence (targum-internal#307, decided 2026-10-03) ------------


@pytest.mark.parametrize(
    ("pointed", "opens"),
    [
        ("אוֹכֵל", "vo"),
        ("אֹכַל", "o"),
        ("אוּכַל", "u"),
        ("יִכְתֹּב", "hiriq"),
        ("יִכָּתֵב", "hiriq-dagesh"),
        ("יִיכָּתֵב", "hiriq-dagesh"),
        ("טִהֵר", "hiriq-open"),
        ("יֵאָכֵל", "tsere-qamats"),
        ("יֵשֵׁב", "tsere"),
        ("מְשֻׁלָּח", "shva-u"),
        ("מְשַׁלֵּחַ", "shva"),
        ("קָם", "qamats"),
        ("אוכל", None),
        ("", None),
    ],
)
def test_a_word_opens_on_the_vowel_its_pointing_says(pointed: str, opens: str | None) -> None:
    """The one place the pointing tells apart what the letters cannot: `אוֹכֵל` and `אוּכַל`
    are the same four letters, and a present and a future."""
    assert opening_of(pointed) == opens


def test_the_pointed_form_is_the_verb_without_its_clitics() -> None:
    assert pointed_form("וְאוֹכֵל", "ו and + אוכל") == "אוֹכֵל"
    assert pointed_form("הָאוֹכֵל", "ה the + אוכל") == "אוֹכֵל"
    assert pointed_form("וַיֹּ֨אמֶר", "ו and + יֹּאמֶר") == "יֹּאמֶר", "cantillation is not a point"
    assert pointed_form("אוכל") == "אוכל"
    assert pointed_form("") == ""


@pytest.mark.parametrize(
    ("lemma", "binyan"),
    [("אוכל", "פועל"), ("הוכל", "הופעל"), ("הוסף", "הופעל"), ("התלבש", "התפעל")],
)
def test_an_unpointed_lemma_s_shape_can_say_its_binyan(lemma: str, binyan: str) -> None:
    assert binyan_unpointed(lemma) == binyan


@pytest.mark.parametrize("lemma", ["אכל", "הוליד", "הודה", "קומם", "התקין", "אָכַל", ""])
def test_a_shape_two_binyanim_share_says_nothing(lemma: str) -> None:
    """`הוליד` and `הודה` are הִפְעִיל, `קומם` a פּוֹלֵל, `התקין` the הִפְעִיל of ת־ק־ן; a
    pointed lemma is `binyan_of`'s to read."""
    assert binyan_unpointed(lemma) is None


def eats() -> Table:
    """`אוכל` as the source spells it: `אָכַל`'s present and the past of the פֻּעַל `אוכל`."""
    paal = Paradigm(
        lemma="אָכַל",
        forms=(
            Form(written="אכל", features=("3rd", "masculine", "past", "singular")),
            Form(written="אוכל", features=("masculine", "present", "singular")),
        ),
    )
    pual = Paradigm(
        lemma="אוכל",
        forms=(Form(written="אוכל", features=("3rd", "masculine", "past", "singular")),),
    )
    return Table(verbs={"a": paal, "u": pual}, by_form={"אוכל": ("a", "u"), "אכל": ("a",)})


def test_the_vowel_the_word_opens_on_picks_the_verb() -> None:
    """targum-internal#307: unpointed, `אוכל` is both, and nothing on the page says which.
    The occurrence's own pointing does: a holam on the ו is the פעל's present, and a
    shuruk is the פֻּעַל's past."""
    shelf = eats()
    assert shelf.of("אוכל") is None
    assert (found := shelf.of("אוכל", seen="אוֹכֵל")) is not None and found.lemma == "אָכַל"
    assert (found := shelf.of("אוכל", seen="אוּכַּל")) is not None and found.lemma == "אוכל"
    assert shelf.of("אוכל", seen="אוכל") is None, "unpointed, it says nothing new"
    assert shelf.of("אוכל", seen="אִכֵּל") is None, "a vowel neither opens on"


def test_where_the_vowel_and_the_binyan_disagree_neither_is_taken() -> None:
    """Refuse-on-conflict, kept: the pointing names the פעל and the word was tagged פֻּעַל,
    so no table — though either alone would have drawn one."""
    shelf = eats()
    assert shelf.of("אוכל", seen="אוֹכֵל", binyan="פועל") is None
    assert (found := shelf.of("אוכל", seen="אוֹכֵל", binyan="פעל")) is not None
    assert found.lemma == "אָכַל"


def test_a_verb_outside_the_candidates_spelled_alike_refuses() -> None:
    """The verb the word is may not be one the lemma reaches. `נִכְתֹּב` "we shall write",
    filed under `נכתב`, reaches only `נִכְתַּב`, whose past opens the same way — but
    `כָּתַב` writes `נכתוב`, and that is a rival."""
    nifal = Paradigm(
        lemma="נִכְתַּב",
        forms=(Form(written="נכתב", features=("3rd", "masculine", "past", "singular")),),
    )
    paal = Paradigm(
        lemma="כָּתַב",
        forms=(Form(written="נכתוב", features=("1st", "future", "plural")),),
    )
    alone = Table(verbs={"n": nifal}, by_form={"נכתב": ("n",)})
    assert alone.of("נכתב", seen="נִכְתַּב") is not None
    both = Table(verbs={"n": nifal, "p": paal}, by_form={"נכתב": ("n",), "נכתוב": ("p",)})
    two_lemmas = Table(verbs=both.verbs, by_form={"נכתב": ("n", "x"), "נכתוב": ("p",)})
    assert two_lemmas.of("נכתב", seen="נִכְתֹּב") is None


def test_a_verb_whose_binyan_cannot_be_read_is_never_the_one_left() -> None:
    """An unpointed lemma of no telling shape could be any binyan. It is not ruled out,
    so nothing is chosen while it stands, and it is never chosen for being left."""
    paal = eats().verbs["a"]
    unread = Paradigm(
        lemma="אכל",
        forms=(Form(written="אוכל", features=("1st", "future", "singular")),),
    )
    shelf = Table(verbs={"a": paal, "x": unread}, by_form={"אוכל": ("a", "x")})
    assert shelf.of("אוכל", seen="אוֹכֵל") is None


def test_the_pointing_settles_the_commonest_stub_on_the_shipped_table(shipped: Table) -> None:
    """The measure in miniature, on the real table and with no readings: `אוֹכֵל` is
    `אָכַל`'s, and `אוּכַל` — `יָכֹל`'s "I can" and the הֻפְעַל `הוכל` alike — is nobody's."""
    bare_shelf = Table(verbs=shipped.verbs, by_form=shipped.by_form)
    assert bare_shelf.of("אוכל") is None
    found = bare_shelf.of("אוכל", seen="אוֹכֵל")
    assert found is not None and found.lemma == "אָכַל"
    assert bare_shelf.of("אוכל", seen="אוּכַל") is None


def test_the_coverage_measurement_counts_what_the_pointing_settles(tmp_path: Path) -> None:
    """The measurement passes each occurrence its own pointing, as the page now does, and
    refuses the one whose binyan says otherwise."""
    measure_conjugations: Any = load_script("measure_conjugations")
    path = tmp_path / "mishnah"
    path.mkdir()
    tokens = [
        {"pos": "VERB", "lemma": "אוכל", "surface": "וְאוֹכֵל", "built": "ו and + אוכל"},
        {"pos": "VERB", "lemma": "אוכל", "surface": "אוֹכֵל", "binyan": "פועל"},
        {"pos": "VERB", "lemma": "אוכל", "surface": "אוכל"},
    ]
    (path / "annotation.json").write_text(
        json.dumps({"language": "he", "tokens": {"s": tokens}}, ensure_ascii=False),
        encoding="utf-8",
    )
    measure_conjugations.table = eats
    tally, _lemmas, _skipped = measure_conjugations.measure(tmp_path)
    assert tally["settled by pointing"] == 1
    assert tally["refused: conflict"] == 1
    assert tally["still ambiguous"] == 1


# -- a binyan from the verb's own forms (targum-internal#307, 2026-10-08) --------------

PAST_3MS = ("3rd", "masculine", "past", "singular")
PRESENT_MS = ("masculine", "present", "singular")
IMPERATIVE = ("2nd", "imperative", "masculine", "singular")


def forms(past: str, present: str, *more: tuple[str, tuple[str, ...]]) -> tuple[Form, ...]:
    """A verb's past and present as the source writes them: letters only."""
    return (
        Form(written=past, features=PAST_3MS),
        Form(written=present, features=PRESENT_MS),
        *(Form(written=written, features=features) for written, features in more),
    )


@pytest.mark.parametrize(
    ("lemma", "past", "present", "imperative", "binyan"),
    [
        ("ילד", "ילד", "יולד", "", "פעל"),
        ("חטא", "חטא", "חוטא", "", "פעל"),
        # A stative: its present is its past.
        ("קרב", "קרב", "קרב", "", "פעל"),
        ("רָץ", "רץ", "רץ", "", "פעל"),
        ("נִתַּן", "ניתן", "ניתן", "", "נפעל"),
        ("הִכָּה", "הכה", "מכה", "הכה", "הפעיל"),
        ("איפשר", "איפשר", "מאפשר", "אפשר", "פיעל"),
        ("נִכָּה", "ניכה", "מנכה", "נכה", "פיעל"),
    ],
)
def test_a_verb_s_past_and_present_say_its_binyan(
    lemma: str, past: str, present: str, imperative: str, binyan: str
) -> None:
    """The source stores `ילד` and `קרב` unpointed, and `binyan_of` reads nothing off bare
    letters. The past against the present is each binyan's own frame around the root."""
    more = ((imperative, IMPERATIVE),) if imperative else ()
    assert binyan_from_forms(lemma, forms(past, present, *more)) == binyan


@pytest.mark.parametrize(
    ("lemma", "past", "present"),
    [
        # A הִפְעִיל of a root beginning with י, or the הֻפְעַל of one: `הוליד`, `הולד`.
        ("הוליד", "הוליד", "מוליד"),
        # A הִפְעִיל of a root beginning with ת, or a הִתְפַּעֵל.
        ("התקין", "התקין", "מתקין"),
        ("הסתדר", "הסתדר", "מסתדר"),
        # A פֻּעַל written full, or a פִּיעֵל of a root with a ו second.
        ("צווה", "צווה", "מצווה"),
        # Nothing a binyan frames.
        ("ילד", "ילד", "מולדת"),
    ],
)
def test_a_past_and_present_two_binyanim_share_say_nothing(
    lemma: str, past: str, present: str
) -> None:
    assert binyan_from_forms(lemma, forms(past, present, ("x", IMPERATIVE))) is None


def test_a_passive_spelled_like_an_active_is_refused() -> None:
    """Unpointed, the הֻפְעַל `הקנה` is letter for letter the הִפְעִיל, and the פֻּעַל `ארגן`
    the פִּיעֵל. Only an imperative, which a passive has none of, tells them apart."""
    assert binyan_from_forms("הֻקְנָה", forms("הקנה", "מקנה")) is None
    assert binyan_from_forms("אֻרְגַּן", forms("ארגן", "מארגן")) is None
    assert binyan_from_forms("הִקְנָה", forms("הקנה", "מקנה", ("הקנה", IMPERATIVE))) == "הפעיל"


def test_forms_that_do_not_agree_say_nothing() -> None:
    # Two pasts.
    two = (*forms("ילד", "יולד"), Form(written="יילד", features=PAST_3MS))
    assert binyan_from_forms("יִלֵּד", two) is None
    # Two presents that frame two binyanim.
    both = (*forms("ילד", "יולד"), Form(written="מילד", features=PRESENT_MS))
    assert binyan_from_forms("ילד", both) is None
    # An unpointed lemma that is not its own past.
    assert binyan_from_forms("ילדה", forms("ילד", "יולד")) is None
    # A pointed lemma that is another word than the past.
    assert binyan_from_forms("כָּתַב", forms("ילד", "יולד")) is None
    # No present at all.
    assert binyan_from_forms("ילד", (Form(written="ילד", features=PAST_3MS),)) is None


def test_what_the_rule_filled_in_is_not_asked() -> None:
    """A stub's present filled by `conjugate` came from a pattern the binyan was guessed
    for. Reading the binyan back off it would be the guess vouching for itself."""
    filled = (
        Form(written="ילד", features=PAST_3MS),
        Form(written="יולד", features=PRESENT_MS, ruled=True),
    )
    assert binyan_from_forms("ילד", filled) is None


def born() -> Table:
    """`ילד` as the shipped table has it: an unpointed פעל beside a pointed פִּיעֵל."""
    paal = Paradigm(lemma="ילד", forms=forms("ילד", "יולד", ("לד", IMPERATIVE)))
    piel = Paradigm(lemma="יִלֵּד", forms=forms("יילד", "מיילד", ("ילד", IMPERATIVE)))
    return Table(verbs={"a": paal, "i": piel}, by_form={"ילד": ("a", "i")})


def test_an_unpointed_paal_is_the_verb_its_binyan_names() -> None:
    """targum-internal#307: `ילד` tagged פעל was 510 tokens with no table, because the
    only פעל among its candidates was stored unpointed."""
    shelf = born()
    assert shelf.binyan_of("a") == "פעל"
    assert (found := shelf.of("ילד", binyan="פעל")) is not None and found.lemma == "ילד"
    assert (found := shelf.of("ילד", binyan="פיעל")) is not None and found.lemma == "יִלֵּד"
    assert shelf.of("ילד", binyan="הפעיל") is None


def test_the_lemma_s_letters_and_the_forms_disagreeing_say_nothing() -> None:
    """`אוכל` is a פֻּעַל by its shape (`binyan_unpointed`); a table whose present is its
    past is a פעל by its forms. Two answers is none."""
    odd = Paradigm(lemma="אוכל", forms=forms("אוכל", "אוכל"))
    shelf = Table(verbs={"x": odd, "a": eats().verbs["a"]}, by_form={"אוכל": ("x", "a")})
    assert binyan_unpointed("אוכל") == "פועל"
    assert binyan_from_forms("אוכל", odd.forms) == "פעל"
    assert shelf.binyan_of("x") is None


def test_a_pointed_lemma_is_never_overruled_by_its_forms() -> None:
    """Wikidata's `קִבֵּל` is conjugated `קובל`, the פעל "complained". The lemma says
    פִּיעֵל, and the lemma is asked first."""
    odd = Paradigm(lemma="קִבֵּל", forms=forms("קבל", "קובל"))
    assert binyan_from_forms(odd.lemma, odd.forms) == "פעל"
    shelf = Table(verbs={"k": odd}, by_form={"קבל": ("k",)})
    assert shelf.binyan_of("k") == "פיעל"


def test_a_shin_where_the_word_has_a_sin_is_another_verb() -> None:
    """`שָׂטִית` "you went astray" has the letters of a form of `שָׁט` "roamed". Once `שָׁט`'s
    binyan could be read, its binyan matched; the dot is what says it is not the word."""
    roam = Paradigm(lemma="שָׁט", forms=forms("שט", "שט", ("שטית", ("2nd", "feminine", "past"))))
    other = Paradigm(lemma="שיטה", forms=forms("שיטה", "משטה", ("שטה", IMPERATIVE)))
    shelf = Table(verbs={"r": roam, "o": other}, by_form={"שטה": ("r", "o")})
    assert shelf.of("שטה", seen="שָׂטִית", binyan="פעל") is None
    assert (found := shelf.of("שטה", seen="שָׁטִית", binyan="פעל")) is not None
    assert found.lemma == "שָׁט"


def test_the_forms_agree_with_every_lemma_that_can_be_read(shipped: Table) -> None:
    """The rule checked against the lemmas `binyan_of` *can* read: on 2026-10-08 it
    agreed on 1,990 of the 2,015 it decided, and the 25 it did not were the lemma's
    reading at fault — quadriliteral פִּיעֵלים read as נִפְעָלִים — or a lexeme conjugated
    as another verb. A rule that agrees less than this has changed."""
    agree = decided = 0
    for verb in shipped.verbs.values():
        said = binyan_of(verb.lemma)
        if said is None or (forms_say := binyan_from_forms(verb.lemma, verb.forms)) is None:
            continue
        decided += 1
        agree += forms_say == said
    assert decided > 1500
    assert agree / decided > 0.98


def test_the_unpointed_paal_lifts_coverage_on_the_shipped_table(shipped: Table) -> None:
    """The measure in miniature, with no readings: the commonest verbs whose פעל the
    source stores unpointed now draw it, and `הִכָּה` its הִפְעִיל."""
    bare_shelf = Table(verbs=shipped.verbs, by_form=shipped.by_form)
    for lemma, binyan, expected in (
        ("ילד", "פעל", "ילד"),
        ("קרב", "פעל", "קרב"),
        ("חטא", "פעל", "חטא"),
        ("נכה", "הפעיל", "הִכָּה"),
    ):
        found = bare_shelf.of(lemma, binyan=binyan)
        assert found is not None and found.lemma == expected, lemma
