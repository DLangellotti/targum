"""grammar/8, oshb/8 and phonikud/4: ling-he's gold tests, fix by fix.

The spec is targum-internal#509 (ling-he, 2026-10-24), with #307's hollow roots folded
in. Fix 1's render-time half shipped as targum#929 and is tested in `test_paradigms.py`;
everything here changes what an annotation says, which is why the three names moved.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.annotate import oshb
from targum.annotate.hebrew import WEAK_ROOTS, pattern_root, root_of
from targum.models import Segment, Token

# --- Fix 1b: the annotator's weak roots ---------------------------------------------


@pytest.mark.parametrize(
    ("lemma", "binyan", "root"),
    [
        ("הביא", "הפעיל", "בוא"),
        ("קם", "פעל", "קום"),
        ("שם", "פעל", "שים"),
        ("הגיש", "הפעיל", "נגש"),
        ("הציג", "הפעיל", "יצג"),
        ("מת", "פעל", "מות"),
        ("תם", "פעל", "תמם"),
        ("לן", "פעל", "לון"),
    ],
)
def test_a_weak_root_comes_from_the_reviewed_list(lemma: str, binyan: str, root: str) -> None:
    assert root_of(lemma, binyan) == root


@pytest.mark.parametrize("lemma", ["רב", "צר", "מל", "דן"])
def test_a_lemma_that_could_be_two_roots_keeps_none(lemma: str) -> None:
    assert lemma not in WEAK_ROOTS
    assert root_of(lemma, "פעל") is None


def test_the_list_answers_in_its_own_binyan_only() -> None:
    assert root_of("קם", "הפעיל") is None
    assert root_of("הקים", "פעל") is None


def test_the_patterns_alone_still_refuse_a_weak_root() -> None:
    """`paradigms.fill` learns from `pattern_root`, which a hollow root teaches nothing."""
    assert pattern_root("הביא", "הפעיל") is None
    assert pattern_root("קם", "פעל") is None
    assert pattern_root("כתב", "פעל") == "כתב"


def test_the_list_is_the_size_ling_he_reviewed() -> None:
    assert 90 <= len(WEAK_ROOTS) <= 100


def _said(*words: tuple[str, str, str, tuple[str, ...]], feats: dict[str, str] | None = None):
    return {
        "tokens": [
            {
                "token": token,
                "lex": lex,
                "seg": list(seg),
                "morph": {"pos": pos, "feats": dict(feats or {})},
            }
            for token, lex, pos, seg in words
        ]
    }


def test_a_modern_hollow_verb_gets_its_binyan_and_root() -> None:
    """A DICTA token מת, a verb with no Tense, is פעל of מ־ו־ת."""
    from targum.annotate.dicta import _tokens

    died, brought = _tokens(
        _said(("מת", "מת", "VERB", ("מת",)), ("הביא", "הביא", "VERB", ("הביא",)))
    )
    assert (died.binyan, died.root) == ("פעל", "מות")
    assert (brought.binyan, brought.root) == ("הפעיל", "בוא")


def test_a_hollow_verb_now_has_a_family_root() -> None:
    """`_families` reads the new roots, so the hollow families form (wanted, per the
    spec): הֵקִים is filed under ק־ו־ם, where before it had no root to be filed under."""
    from targum.annotate.paradigms import _families

    assert ("הֵקִים", "הפעיל") in _families().get("קום", ())


# --- Fix 2: the qal of a III-he root, filed under its hif'il --------------------------


@pytest.mark.parametrize(
    ("word", "lex", "lemma", "binyan", "root"),
    [
        ("ראיתי", "הראה", "ראה", "פעל", "ראה"),
        ("לראות", "הראה", "ראה", "פעל", "ראה"),
        ("הראה", "הראה", "הראה", None, None),
        ("מראה", "הראה", "הראה", None, None),
        ("קניתי", "הקנה", "קנה", "פעל", "קנה"),
        ("עלו", "העלה", "עלה", "פעל", "עלה"),
    ],
)
def test_a_hifil_lookalike_goes_back_to_the_qal(
    word: str, lex: str, lemma: str, binyan: str | None, root: str | None
) -> None:
    from targum.annotate.dicta import _tokens

    (token,) = _tokens(_said((word, lex, "VERB", (word,))))
    assert token.lemma == lemma
    if binyan is not None:
        assert (token.binyan, token.root) == (binyan, root)
    else:
        assert token.binyan != "פעל"


def test_halakha_is_not_on_the_list() -> None:
    """הלכה's ה is a root letter: the list is closed so that it never becomes לכה."""
    from targum.annotate.dicta import active

    assert active("הלכה", "לכה") == "הלכה"
    assert active("השקה", "שקה") == "השקה"


# --- Fix 3: presents with no Tense ---------------------------------------------------


@pytest.mark.parametrize(
    ("lemma", "pointed", "said"),
    [
        ("אומר", "אוֹמֵר", "אמר"),
        ("אומר", "אוֹמְרִים", "אמר"),
        ("אומר", "וְהָאוֹמֵר", "אמר"),
        ("אוכל", "אוֹכֵל", "אכל"),
        # A shuruq is not a holam: אוּכַל "I can", מוּצָג the hof'al.
        ("אוכל", "אוּכַל", "אוכל"),
        ("מוצג", "מוּצָג", "מוצג"),
        # A ה first is a hif'il past, a נ first a nif'al past.
        ("הודה", "הוֹדָה", "הודה"),
        ("נולד", "נוֹלַד", "נולד"),
    ],
)
def test_a_pointed_present_is_filed_under_its_past(lemma: str, pointed: str, said: str) -> None:
    from targum.annotate.dicta import mend_pointed

    assert mend_pointed(lemma, "VERB", pointed) == (said, "VERB")


@pytest.mark.parametrize(
    ("word", "lemma"),
    [
        ("הולכים", "הלך"),
        ("הולכות", "הלך"),
        ("אומרת", "אמר"),
        ("עושה", "עשה"),
        # Never these unpointed: "I can", "before", a blouse.
        ("אוכל", "אוכל"),
        ("קודם", "קודם"),
        ("חולצה", "חולצה"),
        # A ה first without a plural ending is a past: הוצגה "was presented".
        ("הוצגה", "הוצגה"),
    ],
)
def test_a_present_dicta_stood_its_surface_in_for(word: str, lemma: str) -> None:
    from targum.annotate.dicta import active

    assert active(word, word, tenseless=True) == lemma


def test_a_present_that_is_not_the_surface_is_left_to_dicta() -> None:
    from targum.annotate.dicta import active

    assert active("הולכים", "ההולכים", tenseless=True) == "הולכים"


def test_a_past_in_the_same_letters_is_left_to_dicta() -> None:
    """דובר is a pu'al past as well; DICTA's Tense=Past keeps it out."""
    from targum.annotate.dicta import _tokens

    (token,) = _tokens(_said(("דובר", "דובר", "VERB", ("דובר",)), feats={"Tense": "Past"}))
    assert token.lemma == "דובר"
    (token,) = _tokens(_said(("הולכים", "הולכים", "VERB", ("הולכים",))))
    assert token.lemma == "הלך"


# --- Fix 4: the qal passive participles ----------------------------------------------


@pytest.mark.parametrize(
    ("word", "lex", "root"),
    [("נתונה", "נתון", "נתן"), ("ידוע", "ידוע", "ידע"), ("פטור", "פטור", "פטר")],
)
def test_a_passive_participle_keeps_its_word_and_gets_its_root(
    word: str, lex: str, root: str
) -> None:
    from targum.annotate.dicta import _tokens

    (token,) = _tokens(_said((word, lex, "VERB", (word,))))
    assert (token.lemma, token.binyan, token.root) == (lex, "פעל", root)


def test_no_verb_is_filed_under_tun() -> None:
    from targum.annotate.dicta import _tokens

    (token,) = _tokens(_said(("נתון", "נתון", "VERB", ("נתון",))))
    assert token.root != "תון"


# --- Fix 5: ילך is הלך --------------------------------------------------------------


@pytest.fixture
def walking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    oshb.forget()
    home = tmp_path / "oshb"
    home.mkdir(parents=True)
    (home / "Gen.json").write_text("{}", encoding="utf-8")
    (home / oshb.LEXICON_FILE).write_text(
        json.dumps({"1980": "הָלַךְ", "3212": "יָלַךְ"}, ensure_ascii=False), encoding="utf-8"
    )
    words = {
        "Genesis 12:1": [
            oshb.Word(text="לֶךְ", pieces=("לֶךְ",), lexemes=("3212",), morph=("Vqv2ms",))
        ],
        "Genesis 12:4": [
            oshb.Word(
                text="וַיֵּלֶךְ",
                pieces=("וַ", "יֵּלֶךְ"),
                lexemes=("c", "3212"),
                morph=("C", "Vqw3ms"),
            )
        ],
    }
    monkeypatch.setattr(oshb, "words", lambda ref: words.get(ref))
    yield
    oshb.forget()


@pytest.mark.parametrize(("ref", "text"), [("Genesis 12:1", "לך"), ("Genesis 12:4", "וילך")])
def test_yelekh_is_filed_under_halakh(walking: None, ref: str, text: str) -> None:
    from targum.annotate.scripture import ScriptureLemmatizer

    class Stub:
        name = "stub/1"

        def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
            return {}

    segment = Segment(
        id="s1", text=text, ref=ref, kind="paragraph", block_id="b", block_index=0, index=0
    )
    (token,) = ScriptureLemmatizer(Stub()).lemmas([segment], "he")["s1"]
    assert (token.lemma, token.root, token.binyan, token.lexeme) == ("הלך", "הלך", "פעל", "1980")


def test_the_band_table_counts_yelekh_as_halakh(walking: None) -> None:
    from targum.annotate.scripture import headword_of

    word = oshb.Word(text="לֶךְ", pieces=("לֶךְ",), lexemes=("3212",), morph=("Vqv2ms",))
    assert headword_of(word) == "הלך"


def test_the_names_moved_together() -> None:
    from targum.annotate.dicta import FEATURES
    from targum.annotate.pronounce import PhonikudPronouncer
    from targum.annotate.scripture import ScriptureLemmatizer

    class Stub:
        name = "stub/1"

    assert FEATURES.endswith("grammar/8")
    assert PhonikudPronouncer.name == "phonikud/4"
    assert ScriptureLemmatizer(Stub()).name == "oshb/8+stub/1"


# --- Fixes 6-8: phonikud/4 -------------------------------------------------------------

phonikud = pytest.mark.skipif(
    not __import__("targum.annotate", fromlist=["PhonikudPronouncer"])
    .PhonikudPronouncer()
    .available()[0],
    reason="phonikud is not installed",
)


def _say(word: str, klass: str = "word") -> str:
    from targum.annotate import PhonikudPronouncer
    from targum.annotate.suffix_stress import GATE

    key = f"{word}{GATE}{klass}"
    return PhonikudPronouncer().say([key]).get(key, "")


@phonikud
@pytest.mark.parametrize(
    ("word", "reading"),
    [("לָ֫חֶם", "lˈaχem"), ("כָּ֫סֶף", "kˈasef"), ("לָ֫יְלָה", "lˈajla"), ("מִמֶּ֫ךָּ", "mimˈeχa")],
)
def test_a_pausal_word_reads_its_stress(word: str, reading: str) -> None:
    assert _say(word) == reading


@phonikud
@pytest.mark.parametrize(
    ("word", "reading"),
    [("לָֽחֶם", "lˈaχem"), ("כָּֽסֶף", "kˈasef"), ("לָֽיְלָה", "lˈajla"), ("מִמֶּֽךָּ", "mimˈeχa")],
)
def test_a_verse_final_silluq_is_the_stress(word: str, reading: str) -> None:
    from targum.annotate.pronounce import PAUSE

    assert _say(word, "word" + PAUSE) == reading


@phonikud
def test_geresh_muqdam_is_unplaced_and_ole_veyored_is_its_merkha() -> None:
    assert _say("לַ֝֗יְלָה") == "lˈajla"
    assert _say("מִ֫מֶּ֥ךָ") == "mimˈeχa"


@phonikud
def test_an_unplaceable_accent_falls_back_to_the_segolate_rule() -> None:
    # Pashta alone, postpositive: the segolate rule places כֶּסֶף where the default would not.
    assert _say("כֶּ֙סֶף֙") == "kˈesef"


def _verse(text: str) -> dict[str, str | None]:
    from targum.annotate import Annotator, PhonikudPronouncer
    from targum.models import SegmentedDocument, Vocalization

    class Spaces:
        name = "spaces/1"

        def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
            out: dict[str, list[Token]] = {}
            for segment in segments:
                tokens, at = [], 0
                for word in segment.text.split(" "):
                    tokens.append(
                        Token(start=at, end=at + len(word), surface=word, lemma=word, band=1)
                    )
                    at += len(word) + 1
                out[segment.id] = tokens
            return out

    class Flat:
        name, method, note = "flat/1", "frequency", "made up"

        def supports(self, language: str) -> bool:
            return True

        def band(self, lemma: str, language: str) -> int:
            return 1

    doc = SegmentedDocument(
        document_hash="h",
        language="he",
        segmenter="test",
        segments=[Segment(id="s0", block_id="b", block_index=0, index=0, text=text)],
    )
    vocalized = Vocalization(
        document_hash="h",
        language="he",
        vocalizer="test/1",
        model=None,
        segments={"s0": text},
        machine=[],
        rejected=[],
    )
    annotated = Annotator(lemmatizer=Spaces(), bands=Flat(), pronouncer=PhonikudPronouncer())
    tokens = annotated.annotate(doc, vocalized).tokens["s0"]
    return {token.surface: token.ipa for token in tokens}


@phonikud
def test_ruth_1_6_ends_on_lehem_stressed_where_its_silluq_is() -> None:
    said = _verse("לָתֵ֥ת לָהֶ֖ם לָֽחֶם")
    assert said["לָֽחֶם"] == "lˈaχem"


@phonikud
def test_mid_verse_the_same_word_keeps_its_accent() -> None:
    said = _verse("לֶ֣חֶם לָהֶ֖ם לָֽחֶם")
    assert said["לֶ֣חֶם"] == "lˈeχem"


@phonikud
def test_a_mishnah_meteg_is_not_a_silluq() -> None:
    """No accents in the segment, so U+05BD is a meteg and the word keeps its reading."""
    said = _verse("לָתֵת לָהֶם לָֽחֶם")
    assert said["לָֽחֶם"] == "laχˈem"


@pytest.mark.parametrize(
    ("word", "ok"),
    [
        ("פּתח", False),
        ("הִכּרתי", False),
        ("וַיֹּאמֶר", True),
        ("לֵאמֹר", True),
        ("יְרוּשָׁלַיִם", True),
        ("שׁוּב", True),
        ("דְּבָרָיו", True),
    ],
)
def test_a_partly_pointed_word_is_not_said(word: str, ok: bool) -> None:
    from targum.annotate.pronounce import sayable

    assert sayable(word) is ok


@phonikud
@pytest.mark.parametrize(
    ("word", "klass", "reading"),
    [
        ("לוֹקֵחַ", "word", "lokˈeaχ"),
        ("פָּתוּחַ", "word", "patˈuaχ"),
        ("רוּחַ", "word", "ʁˈuaχ"),
        ("שָׁתַלְתִּי", "VERB|Tense=Past|Person=3|Number=Sing", "ʃatˈalti"),
        ("וַיֹּאמֶר", "VERB|Tense=Past|Person=3|Number=Sing", "vajˈomeʁ"),
        ("לָאו", "word", "lˈav"),
    ],
)
def test_the_small_stress_fixes(word: str, klass: str, reading: str) -> None:
    assert _say(word, klass) == reading


def test_a_furtive_patah_is_the_segolate_rules_fifth() -> None:
    from targum.annotate.segolate import penult

    assert penult("יוֹדֵעַ") == 2
    assert penult("לוֹקֵחַ") == 2
    # Not a furtive patah: the patah under the letter before, and a bare guttural.
    assert penult("פָּתַח") is None
