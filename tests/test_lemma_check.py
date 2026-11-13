"""A lemma the word does not spell, put right at page-build and count time
(`annotate.lemma_check`; David, 2026-10-31: נשתיק on התקין's card).

Single words only, never a sentence of any text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.annotate.lemma_check import Mend, checked, mend_row, mended, refused
from targum.models import Annotation, BlockKind, Segment, SegmentedDocument, Syntax, Token
from targum.occurrences import count_text

DICTA = "dicta/dicta-il/dictabert-joint/roots+everyword+entities+syntax+grammar/8"


def test_a_lemma_the_word_does_not_spell_takes_the_table_verb() -> None:
    # התקין's ת־ק־ן with its nun let go is ת־ק, which נשתיק spells; the nun is the
    # root's last letter and no ת follows it, so it stays a letter to spell.
    assert refused("התקין", "נשתיק")
    assert checked("התקין", "נשתיק", 0, "VERB") == Mend("השתיק", "שתק", "הפעיל")


def test_a_pointed_word_is_checked_on_its_letters() -> None:
    assert checked("התקין", "נַשְׁתִּיק", 0, "VERB") == Mend("השתיק", "שתק", "הפעיל")


def test_prefixes_are_cut_before_the_table_is_asked() -> None:
    # והלכו under הלכנו: the ו is the conjunction (lead 1), and הלכו is הלך's.
    found = checked("הלכנו", "והלכו", 1, "VERB")
    assert found is not None and found.lemma == "הלך"


@pytest.mark.parametrize(
    ("lemma", "word"),
    [
        ("נתן", "נתתי"),  # a last nun taken into the suffix's ת
        ("נתן", "תן"),  # a first nun that assimilated
        ("נתן", "לתת"),  # both nuns: לָתֵת
        ("נתן", "תת"),  # and under an infinitive's ל cut off as a prefix
        ("נפל", "יפול"),
        ("לקח", "קח"),  # suppletive
        ("התקין", "התקנו"),  # the root's nun written once before נו
        ("התקין", "נתקין"),  # the right verb
        ("השתיק", "נשתיק"),
        ("משתיק", "השתקתי"),  # a participle's מ left on the lemma
        ("שמר", "שומרים"),
    ],
)
def test_a_lemma_the_word_spells_stands(lemma: str, word: str) -> None:
    assert not refused(lemma, word)
    assert checked(lemma, word, 0, "VERB") is None


def test_with_no_one_verb_in_the_table_the_card_gets_a_gap() -> None:
    # נפדה under נקנה: wrong, and the table holds more than one verb for נפדה.
    assert checked("נקנה", "נפדה", 0, "VERB") == Mend("נפדה", "", "")
    # A noun is never given a verb; a wrong one becomes the word itself.
    assert checked("שמן", "שמו", 0, "NOUN") == Mend("שמו", "", "")


def test_a_gap_stays_a_gap_and_other_words_are_not_checked() -> None:
    assert checked("נשתיק", "נשתיק", 0, "VERB") is None
    assert checked("התקין", "נשתיק", 0, "ADV") is None
    assert checked("התקין", "נשתיק", 0, None) is None


def _annotation(annotator: str, token: Token) -> Annotation:
    return Annotation(
        document_hash="h",
        language="he",
        annotator=annotator,
        method="frequency",
        method_note="",
        tokens={"s1": [token]},
    )


def _word(lemma: str) -> Token:
    return Token(
        start=0,
        end=5,
        surface="נשתיק",
        lemma=lemma,
        band=3,
        pos="VERB",
        root="תקן",
        binyan="הפעיל",
        headword="הִתְקִין",
        syntax=Syntax(head=-1, relation="root"),
    )


def test_a_dicta_annotation_is_mended_and_its_root_follows() -> None:
    fixed = mended(_annotation(DICTA, _word("התקין"))).tokens["s1"][0]
    assert (fixed.lemma, fixed.root, fixed.binyan) == ("השתיק", "שתק", "הפעיל")
    assert fixed.headword is None
    assert fixed.band == 3


def test_an_annotation_with_nothing_to_mend_is_the_same_object() -> None:
    right = _annotation(DICTA, _word("השתיק"))
    assert mended(right) is right


def test_scripture_tagging_is_never_overruled() -> None:
    tagged = _annotation("oshb/8+" + DICTA, _word("התקין"))
    assert mended(tagged) is tagged


def test_a_stored_row_is_mended_for_the_counts() -> None:
    row = {"surface": "נשתיק", "lemma": "התקין", "pos": "VERB", "root": "תקן"}
    assert mend_row(row)["lemma"] == "השתיק"
    assert mend_row(row)["root"] == "שתק"
    kept = {"surface": "נשתיק", "lemma": "השתיק", "pos": "VERB"}
    assert mend_row(kept) is kept


def test_the_count_files_the_word_under_the_lemma_the_page_shows(tmp_path: Path) -> None:
    folder = tmp_path / "text"
    folder.mkdir()
    segment = Segment(
        id="s1", block_id="b1", block_index=0, index=0, kind=BlockKind.paragraph, text="נשתיק"
    )
    document = SegmentedDocument(
        document_hash="h", language="he", segmenter="test", segments=[segment]
    )
    (folder / "segments.json").write_text(document.model_dump_json(), encoding="utf-8")
    row = {"start": 0, "end": 5, "surface": "נשתיק", "lemma": "התקין", "pos": "VERB"}
    (folder / "annotation.json").write_text(
        json.dumps({"annotator": DICTA, "language": "he", "tokens": {"s1": [row]}}),
        encoding="utf-8",
    )
    counted = count_text(folder)
    assert counted is not None
    assert counted.count("השתיק") == 1
    assert counted.count("התקין") == 0


# -- an inflected verb standing as its own lemma (targum-internal#660) ----------------

FUTURE_PLURAL = "Person=3|Gender=Masc|Number=Plur|Tense=Fut"


def test_a_future_with_the_hifil_tsere_takes_its_verb() -> None:
    # תָּרֵעוּ is תָּרִיעוּ written short, and the table spells only the long form (ling-he
    # on targum#1131); the shelf's copy is pointed with the tsere alone.
    for written in ("תָּרֵעוּ", "תרֵעו"):
        found = checked("תרעו", written, 0, "VERB", FUTURE_PLURAL)
        assert found is not None and (found.lemma, found.binyan) == ("הריע", "הפעיל")


def test_an_inflected_verb_the_table_knows_takes_its_verb() -> None:
    past = "Person=3|Gender=Fem|Number=Sing|Tense=Past"
    # Not הלכה, which unpointed is halakha (ling-he): הלכו is only the verb.
    plural = "Person=3|Number=Plur|Tense=Past"
    assert checked("הלכו", "הלכו", 0, "VERB", plural) == Mend("הלך", "הלך", "")
    found = checked("אמרה", "אמרה", 0, "VERB", past)
    assert found is not None and found.lemma == "אמר"
    found = checked("ילכו", "ילכו", 0, "VERB", FUTURE_PLURAL)
    assert found is not None and found.lemma == "הלך"


def test_the_tables_form_must_say_what_dicta_said() -> None:
    # Mishnaic יבאו, "they will come": the table's יבאו is יבא's past, so it stays a gap.
    assert checked("יבאו", "יבאו", 0, "VERB", FUTURE_PLURAL) is None


def test_a_gap_with_no_tense_a_citation_form_or_another_word_stays() -> None:
    assert checked("הלכה", "הלכה", 0, "VERB") is None, "no tense said, nothing to match"
    past = "Person=3|Gender=Masc|Number=Sing|Tense=Past"
    assert checked("הלך", "הלך", 0, "VERB", past) is None, "already the verb"
    assert checked("הלכה", "הלכה", 0, "NOUN", "Number=Sing") is None, "only verbs"


def test_a_prefixs_own_tsere_is_not_the_hifils() -> None:
    from targum.annotate.lemma_check import _plene

    assert _plene("תָּרֵעוּ", 0) == "תריעו"
    assert _plene("וַתָּרֵעוּ", 1) == "תריעו", "cut under its prefixes"
    assert _plene("תרֵעו", 0) == "תריעו", "as the shelf has it: the tsere alone"
    # A nif'al: its prefix's tsere, and its own tsere before the last letter, are no
    # hiriq-yod written short, so it is never האמיר "soared".
    assert _plene("יֵאָמֵר", 0) is None
    assert checked("יאמר", "יֵאָמֵר", 0, "VERB", "Number=Sing|Tense=Fut") is None, (
        "nor אָמַר's: a nif'al future stays a gap"
    )
    assert checked("יכנס", "יִכָּנֵס", 0, "VERB", "Number=Sing|Tense=Fut") is None


def test_a_stored_inflected_row_is_mended_for_the_counts() -> None:
    row = {"lemma": "תרעו", "surface": "תָּרֵעוּ", "pos": "VERB", "feats": FUTURE_PLURAL}
    assert mend_row(row)["lemma"] == "הריע"


# -- ling-he's read of targum#1135 (2026-11-08) -----------------------------------------

PAST_FEM = "Person=3|Gender=Fem|Number=Sing|Tense=Past"


@pytest.mark.parametrize("letters", ["עבדה", "שאלה", "נשמה", "ילדה", "הלכה", "נקבה"])
def test_a_noun_homograph_unpointed_keeps_its_gap(letters: str) -> None:
    assert checked(letters, letters, 0, "VERB", PAST_FEM) is None


@pytest.mark.parametrize("pointed", ["עֻבְדָּה", "שְׁאֵלָה", "נְשָׁמָה", "יַלְדָּה", "הֲלָכָה", "נְקֵבָה"])
def test_a_noun_homograph_pointed_as_the_noun_keeps_its_gap(pointed: str) -> None:
    bare = "".join(char for char in pointed if "א" <= char <= "ת")
    assert checked(bare, pointed, 0, "VERB", PAST_FEM) is None


def test_a_noun_homograph_pointed_as_the_verb_moves() -> None:
    assert checked("ילדה", "יָלְדָה", 0, "VERB", PAST_FEM) == Mend("ילד", "ילד", "")
    found = checked("הלכה", "וְהָלְכָה", 1, "VERB", PAST_FEM)
    assert found is not None and found.lemma == "הלך"
    found = checked("שאלה", "שָׁאֲלָה", 0, "VERB", PAST_FEM)
    assert found is not None and found.lemma == "שאל"


@pytest.mark.parametrize(
    ("letters", "written", "feats"),
    [
        ("משנה", "מְשַׁנֶּה", "Number=Sing|Tense=Pres"),
        ("משנה", "משנה", "Number=Sing|Tense=Pres"),
        ("מקדש", "הַמְקַדֵּשׁ", "Number=Sing|Tense=Pres"),
        ("הוקרן", "הוקרן", "Person=3|Number=Sing|Tense=Past"),
        ("הוברר", "הוברר", "Person=3|Number=Sing|Tense=Past"),
    ],
)
def test_the_reviewed_gaps_stay_gaps(letters: str, written: str, feats: str) -> None:
    lead = 1 if written.startswith("הַ") else 0
    assert checked(letters, written, lead, "VERB", feats) is None


def test_naase_moves_only_pointed_as_we_will_do() -> None:
    plural = "Person=1|Number=Plur|Tense=Fut"
    assert checked("נעשה", "נעשה", 0, "VERB", plural) is None
    assert checked("נעשה", "נַעֲשָׂה", 0, "VERB", plural) is None
    found = checked("נעשה", "נַעֲשֶׂה", 0, "VERB", plural)
    assert found is not None and found.lemma == "עשה"


@pytest.mark.parametrize(
    ("pointed", "written"),
    [
        ("הִתְכַּוֵּן", "התכוון"),
        ("קִיֵּם", "קיים"),
        ("בִּקֵּשׁ", "ביקש"),
        ("דִּבֵּר", "דיבר"),
        ("הֻקְדַּשׁ", "הוקדש"),
        ("צִוָּה", "ציווה"),
        ("סִוֵּג", "סיווג"),
        ("הִרְוָה", "הרווה"),
        ("הָיָה", "היה"),
        ("הֶחֱיָה", "החיה"),
        ("שֻׁיַּךְ", "שויך"),
        ("שִׁיֵּךְ", "שייך"),
        ("יִסֵּד", "ייסד"),
        ("סֻנְוַר", "סונוור"),
        ("הִתְקַיֵּם", "התקיים"),
        ("הֵרִיעַ", "הריע"),
        ("הִגִּיעַ", "הגיע"),
        ("הִשְׁתִּיק", "השתיק"),
        ("הָלַךְ", "הלך"),
        ("שׁוּב", "שוב"),
    ],
)
def test_a_lemma_is_written_in_ktiv_male(pointed: str, written: str) -> None:
    from targum.annotate.lemma_check import male

    assert male(pointed) == written


# -- ling-he's analyser read of 2026-11-13 (targum-internal#697) ------------------------
#
# Each row is a token exactly as DICTA stored it in the laptop's targum-out: surface,
# lemma, part of speech, binyan, root, built, feats, lead and prefixes.

Row = tuple[str, str, str, str | None, str | None, str | None, str, int, list[str]]


def _sentence(*rows: Row) -> list[Token]:
    """A segment's tokens as DICTA stored them, mended for the page."""
    tokens = [
        Token(
            start=0,
            end=len(surface),
            surface=surface,
            lemma=lemma,
            band=3,
            split=built is not None,
            pos=pos,
            binyan=binyan,
            root=root,
            built=built,
            feats=feats,
            syntax=Syntax(head=-1, relation="root", lead=lead, prefixes=tuple(prefixes)),
        )
        for surface, lemma, pos, binyan, root, built, feats, lead, prefixes in rows
    ]
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator=DICTA,
        method="frequency",
        method_note="",
        tokens={"s1": tokens},
    )
    return mended(annotation).tokens["s1"]


def _rows(*rows: Row) -> list[dict[str, object]]:
    """The same tokens as `annotation.json` stores them, mended for the counts."""
    from targum.annotate.lemma_check import mend_rows

    return mend_rows(
        [
            {
                "surface": surface,
                "lemma": lemma,
                "pos": pos,
                "binyan": binyan,
                "root": root,
                "built": built,
                "feats": feats,
                "syntax": {"lead": lead, "prefixes": prefixes},
            }
            for surface, lemma, pos, binyan, root, built, feats, lead, prefixes in rows
        ]
    )


PAST_3MS = "UPOS=VERB|Person=3|Gender=Masc|Number=Sing|Tense=Past"
PAST_3MP = "UPOS=VERB|Person=3|Gender=Masc|Number=Plur|Tense=Past"
FUT_3MS = "UPOS=VERB|Person=3|Gender=Masc|Number=Sing|Tense=Fut"
FUT_1MS = "UPOS=VERB|Person=1|Gender=Masc|Number=Sing|Tense=Fut"


# a. A lemma of one strong letter is checked like any other.


@pytest.mark.parametrize(
    ("lemma", "word", "pos", "feats", "wanted"),
    [
        ("הביא", "היה", "VERB", PAST_3MS, Mend("היה", "היה", "פעל")),
        ("אין", "היה", "AUX", PAST_3MS, Mend("היה", "", "")),
        ("יש", "היו", "AUX", PAST_3MP, Mend("היה", "", "")),
        ("בא", "טוֹב", "ADJ", "UPOS=ADJ|Gender=Masc|Number=Sing", Mend("טוב", "", "")),
    ],
)
def test_a_lemma_of_one_strong_letter_is_checked(
    lemma: str, word: str, pos: str, feats: str, wanted: Mend
) -> None:
    assert refused(lemma, word, pos)
    assert checked(lemma, word, 0, pos, feats) == wanted


@pytest.mark.parametrize(
    ("lemma", "word", "lead", "pos"),
    [
        ("בא", "הבאה", 1, "ADJ"),  # "the next"
        ("בא", "תבוא", 0, "VERB"),
        ("הביא", "אביא", 0, "VERB"),  # the hif'il's he, gone in the future
        ("הביא", "להביא", 0, "VERB"),
        ("היה", "יהיה", 0, "AUX"),
        ("היה", "הייתי", 0, "AUX"),
        ("היה", "להיות", 0, "AUX"),
        ("ראה", "לראות", 0, "VERB"),
        ("יצא", "לצאת", 0, "VERB"),
        ("הודה", "מודה", 0, "VERB"),
        ("איש", "אנשים", 0, "NOUN"),
        ("יום", "ימים", 0, "NOUN"),
        ("אח", "אחיו", 0, "NOUN"),
        ("פה", "פי", 0, "NOUN"),
        ("חי", "לחיות", 0, "VERB"),
    ],
)
def test_a_lemma_of_one_strong_letter_the_word_spells_stands(
    lemma: str, word: str, lead: int, pos: str
) -> None:
    base = word[lead:]
    assert not refused(lemma, base, pos)


def test_haya_is_not_brought_in_its_sentences() -> None:
    # "היה כאן מישהו", סימן טוב: היה came back as הביא, "brought".
    was, here, someone = _sentence(
        ("היה", "הביא", "VERB", "הפעיל", "בוא", None, PAST_3MS, 0, []),
        ("כאן", "כאן", "ADV", None, None, None, "UPOS=ADV", 0, []),
        ("מישהו", "מישהו", "NOUN", None, None, None, "UPOS=NOUN|Number=Sing", 0, []),
    )
    assert (was.lemma, was.binyan, was.root) == ("היה", "פעל", "היה")
    assert (here.lemma, someone.lemma) == ("כאן", "מישהו")


def test_there_were_is_haya_not_there_is_not() -> None:
    # "והיו ספסלים" under אין, "there is not"; "היו עצים" under יש.
    were, benches = _sentence(
        ("והיו", "אין", "AUX", "פעל", "אין", "ו and + היו", PAST_3MP, 1, ["CCONJ"]),
        ("ספסלים", "ספסל", "NOUN", None, None, None, "UPOS=NOUN|Number=Plur", 0, []),
    )
    assert (were.lemma, were.binyan, were.root, were.pos) == ("היה", None, None, "AUX")
    assert were.built == "ו and + היו", "the conjunction stays cut"
    assert benches.lemma == "ספסל"
    (were,) = _sentence(("היו", "יש", "AUX", None, None, None, PAST_3MP, 0, []))
    assert were.lemma == "היה"


def test_good_morning_is_not_come() -> None:
    # "בּוֹקֶר טוֹב", בבית-קפה: טוֹב under בא, "come; arrive", whose ב is in it.
    morning, good = _sentence(
        ("בּוֹקֶר", "בוקר", "NOUN", None, None, None, "UPOS=NOUN|Number=Sing", 0, []),
        ("טוֹב", "בא", "ADJ", None, None, None, "UPOS=ADJ|Gender=Masc|Number=Sing", 0, []),
    )
    assert (morning.lemma, good.lemma) == ("בוקר", "טוב")


# b. An unpointed qal future filed under its nif'al.


def test_an_unpointed_future_without_the_nifals_yod_is_the_qal() -> None:
    # Ktiv male writes a nif'al future's yod after ת, י and נ: תישכח. תשכח is שכח's.
    found = checked("נשכח", "תשכח", 0, "VERB", FUT_3MS)
    assert found == Mend("שכח", "שכח", "פעל")


def test_a_first_person_future_needs_its_object() -> None:
    # After א the nif'al writes no yod: אשכח is both, and an object settles it.
    assert checked("נשכח", "אשכח", 0, "VERB", FUT_1MS) is None
    found = checked("נשכח", "אשכח", 0, "VERB", FUT_1MS, objected=True)
    assert found is not None and found.lemma == "שכח"


def test_a_pointed_nifal_future_stays_the_nifal() -> None:
    assert checked("נשכח", "תִּשָּׁכַח", 0, "VERB", FUT_3MS) is None


def test_i_will_not_forget_you() -> None:
    # "לא אשכח אותך", סימון התנין: under נשכח, "be forgotten".
    _, forget, you = _sentence(
        ("לא", "לא", "ADV", None, None, None, "UPOS=ADV", 0, []),
        ("אשכח", "נשכח", "VERB", None, None, None, FUT_1MS, 0, []),
        ("אותך", "את", "ADP", None, None, "אותך + with a pronoun on the end", "UPOS=ADP", 0, []),
    )
    assert (forget.lemma, forget.binyan, forget.root) == ("שכח", "פעל", "שכח")
    assert you.lemma == "את"


def test_do_not_forget_me() -> None:
    # "אל תשכח אותי", סימון התנין.
    _, forget, _ = _sentence(
        ("אל", "אל", "ADV", None, None, None, "UPOS=ADV", 0, []),
        ("תשכח", "נשכח", "VERB", None, None, None, FUT_3MS, 0, []),
        ("אותי", "את", "ADP", None, None, "אותי + with a pronoun on the end", "UPOS=ADP", 0, []),
    )
    assert forget.lemma == "שכח"


def test_i_will_find_you_a_room() -> None:
    # "אני אמצא לך חדר", סימן טוב: under נמצא, "is located". A dative and a noun after.
    rows: tuple[Row, ...] = (
        ("אני", "אני", "PRON", None, None, None, "UPOS=PRON|Person=1", 0, []),
        ("אמצא", "נמצא", "VERB", "נפעל", "מצא", None, FUT_3MS, 0, []),
        ("לך", "ל", "ADP", None, None, "לך + with a pronoun on the end", "UPOS=ADP", 0, ["ADP"]),
        ("חדר", "חדר", "NOUN", None, None, None, "UPOS=NOUN|Number=Sing", 0, []),
    )
    find = _sentence(*rows)[1]
    assert (find.lemma, find.binyan, find.root) == ("מצא", "פעל", "מצא")
    assert _rows(*rows)[1]["lemma"] == "מצא", "and the count files it the same"


def test_a_first_person_future_alone_keeps_the_nifal() -> None:
    # "אשכח אבוא": no object, and אשכח is the nif'al's too.
    forget, _ = _sentence(
        ("אשכח", "נשכח", "VERB", None, None, None, FUT_1MS, 0, []),
        ("אבוא", "בא", "VERB", None, None, None, FUT_1MS, 0, []),
    )
    assert forget.lemma == "נשכח"


def test_we_will_not_be_friends() -> None:
    # "לא נהיה חברים", ארי האריה: נהיה, "we will be", stood as its own lemma, which is
    # the nif'al "became". DICTA read the future; the nif'al's would be ניהיה.
    _, be, friends = _sentence(
        ("לא", "לא", "ADV", None, None, None, "UPOS=ADV", 0, []),
        ("נהיה", "נהיה", "AUX", None, None, None, "UPOS=AUX|Person=1|Number=Plur|Tense=Fut", 0, []),
        ("חברים", "חבר", "NOUN", None, None, None, "UPOS=NOUN|Number=Plur", 0, []),
    )
    assert (be.lemma, be.pos, be.binyan) == ("היה", "AUX", None)
    assert friends.lemma == "חבר"


# c. Closed-class words filed under another word of the same letters.


def test_able_is_not_ability() -> None:
    (able,) = _sentence(("יָכוֹל", "יכולת", "AUX", None, None, None, "UPOS=AUX|Number=Sing", 0, []))
    assert able.lemma == "יכול"
    (able,) = _sentence(("יְכוֹלָה", "יכולת", "AUX", None, None, None, "UPOS=AUX|Number=Sing", 0, []))
    assert able.lemma == "יכול"


def test_we_will_be_able_is_not_a_swindler() -> None:
    # "וְלֹא נוּכַל לְפַרְסֵם", במערכת: under נוכל, "swindler, con artist".
    _, able, _ = _sentence(
        ("וְלֹא", "לא", "ADV", None, None, "ו and + לא", "UPOS=ADV", 1, ["CCONJ"]),
        ("נוּכַל", "נוכל", "AUX", None, None, None, "UPOS=AUX|Person=1|Number=Plur|Tense=Fut", 0, []),
        ("לְפַרְסֵם", "פרסם", "VERB", "פיעל", "פרסם", None, "UPOS=VERB", 0, []),
    )
    assert (able.lemma, able.pos) == ("יכול", "AUX")


def test_beside_is_not_hand() -> None:
    # "לְיַד הַדּוּכָן", ילד בחוף: "ל to + יד", "hand".
    (beside,) = _sentence(("לְיַד", "יד", "ADP", None, None, "ל to + יד", "UPOS=ADP", 1, []))
    assert (beside.lemma, beside.built, beside.split) == ("ליד", None, False)
    assert beside.syntax is not None and beside.syntax.lead == 0
    (beside,) = _sentence(("לְיַד", "יד", "ADP", None, None, None, "UPOS=ADP", 0, []))
    assert beside.lemma == "ליד"


def test_between_us_is_between() -> None:
    (between,) = _sentence(
        (
            "בינינו",
            "ביניים",
            "ADP",
            None,
            None,
            "בינינו + with a pronoun on the end",
            "UPOS=ADP",
            0,
            [],
        )
    )
    assert between.lemma == "בין"


def test_the_same_question_is_not_you() -> None:
    # "לֹא אוֹתָהּ שָׁאֵלָה", עורך הדין: under את, "you (feminine)".
    _, same, question = _sentence(
        ("לֹא", "לא", "ADV", None, None, None, "UPOS=ADV", 0, []),
        ("אוֹתָהּ", "את", "PRON", None, None, None, "UPOS=PRON|Person=3|Gender=Fem", 0, []),
        ("שָׁאֵלָה", "שאלה", "NOUN", None, None, None, "UPOS=NOUN|Number=Sing", 0, []),
    )
    assert (same.lemma, same.pos, question.lemma) == ("אותו", "PRON", "שאלה")


def test_her_after_a_verb_stays_the_object_marker() -> None:
    (her,) = _sentence(
        ("אוֹתָהּ", "את", "ADP", None, None, "אותה + with a pronoun on the end", "UPOS=ADP", 0, [])
    )
    assert her.lemma == "את"


def test_possible_is_not_enabled() -> None:
    # "אפשר לומר", סימון התנין: אפשר, "possible", under the pi'el "enabled".
    possible, say = _sentence(
        ("אפשר", "אפשר", "VERB", "פיעל", "פשר", None, "UPOS=VERB", 0, []),
        ("לומר", "אומר", "VERB", None, None, None, "UPOS=VERB", 0, []),
    )
    assert (possible.lemma, possible.pos, possible.binyan, possible.root) == (
        "אפשר",
        "AUX",
        None,
        None,
    )
    assert possible.glossed_as == "אפשר"
    assert (say.lemma, say.binyan) == ("אמר", "פעל")


def test_enabled_with_its_tense_or_its_hiriq_stays_the_verb() -> None:
    (enabled,) = _sentence(("אפשר", "אפשר", "VERB", "פיעל", "פשר", None, PAST_3MS, 0, []))
    assert enabled.pos == "VERB"
    (enabled,) = _sentence(("אִפְשֵׁר", "אפשר", "VERB", "פיעל", "פשר", None, "UPOS=VERB", 0, []))
    assert enabled.pos == "VERB"


# d. A verb whose lemma is another of its forms.


@pytest.mark.parametrize(
    ("lemma", "word", "feats", "verb"),
    [
        ("שואל", "תֵּשְׁאֲלִי", "UPOS=VERB|Person=3|Number=Plur|Tense=Fut", "שאל"),
        ("רוצה", "רָצִיתִי", "UPOS=VERB|Person=1|Number=Sing|Tense=Past", "רצה"),
        ("אומר", "לומר", "UPOS=VERB", "אמר"),
        ("מכין", "להכין", "UPOS=VERB", "הכין"),
        ("יבדוק", "אֶבְדּוֹק", "UPOS=VERB|Person=1|Number=Sing|Tense=Fut", "בדק"),
    ],
)
def test_a_verb_under_another_of_its_forms_takes_its_verb(
    lemma: str, word: str, feats: str, verb: str
) -> None:
    found = checked(lemma, word, 0, "VERB", feats)
    assert found is not None and found.lemma == verb


def test_a_present_keeps_its_participle() -> None:
    # The wrong headword with the right meaning, and the word's own tense (#490).
    present = "UPOS=VERB|Person=1|Number=Sing|Tense=Pres"
    assert checked("רוצה", "רוֹצִים", 0, "VERB", present) is None
    assert checked("רוצה", "רָצִיתִי", 0, "VERB") is None, "no tense said"


def test_a_verb_under_its_own_lemma_stands() -> None:
    assert checked("רצה", "רָצִיתִי", 0, "VERB", "UPOS=VERB|Person=1|Tense=Past") is None
    assert checked("אמר", "לומר", 0, "VERB", "UPOS=VERB") is None
    assert checked("שמר", "לשמור", 0, "VERB", "UPOS=VERB") is None


@pytest.mark.parametrize("able", ["תּוּכַל", "יוּכַל", "יָכְלָה", "יָכוֹלְתִּי"])
def test_every_form_of_able_is_able(able: str) -> None:
    (word,) = _sentence((able, "יכולת", "AUX", None, None, None, "UPOS=AUX", 0, []))
    assert (word.lemma, word.pos) == ("יכול", "AUX")


# -- ling-he's analyser read of 2026-11-13 (targum-internal#698, #700, #702) -----------


def test_the_lemma_drops_a_prefix_the_line_already_shows() -> None:
    # "ה the + שיניים" over the lemma השיניים: the card had no meaning to give.
    (teeth,) = _sentence(
        ("השיניים", "השיניים", "NOUN", None, None, "ה the + שיניים", "UPOS=NOUN", 1, ["DET"])
    )
    assert (teeth.lemma, teeth.built) == ("שיניים", "ה the + שיניים")
    (tiger,) = _sentence(
        (
            "והנמר",
            "והנמר",
            "NOUN",
            None,
            None,
            "ו and + ה the + נמר",
            "UPOS=NOUN",
            2,
            ["DET", "CCONJ"],
        )
    )
    assert tiger.lemma == "נמר"
    (other,) = _sentence(
        ("הזולת", "הזולת", "NOUN", None, None, "ה the + זולת", "UPOS=NOUN", 1, ["DET"])
    )
    assert other.lemma == "זולת"


def test_a_verb_under_its_prefix_takes_its_verb() -> None:
    # שֶׁתֵּלְכִי under שתלכי: the ש comes off. Pointed, the prefix's tsere is a nif'al's
    # to `_nifal_future`, so it stays the gap תלכי; unpointed, תלכי is הלך's.
    fut = "UPOS=VERB|Person=3|Gender=Fem|Number=Sing|Tense=Fut"
    (go,) = _sentence(("שֶׁתֵּלְכִי", "שתלכי", "VERB", None, None, "ש that + תלכי", fut, 1, ["SCONJ"]))
    assert (go.lemma, go.built) == ("תלכי", "ש that + תלכי")
    (go,) = _sentence(("שתלכי", "שתלכי", "VERB", None, None, "ש that + תלכי", fut, 1, ["SCONJ"]))
    assert go.lemma == "הלך"


@pytest.mark.parametrize(
    ("surface", "lemma", "pos", "built", "lead"),
    [
        ("הַיּוֹם", "יום", "ADV", "ה the + יום", 1),  # "today", not "the day"
        ("היום", "יום", "ADV", None, 0),
        ("הֲכִי", "הכי", "ADV", "ה the + כי", 1),  # "most"
        ("למשל", "משל", "CCONJ", "ל to + משל", 1),  # "for example", not "proverb"
        ("בִּכְלָל", "כלל", "ADV", None, 0),  # "at all"
    ],
)
def test_a_fixed_word_stays_whole(
    surface: str, lemma: str, pos: str, built: str | None, lead: int
) -> None:
    (word,) = _sentence((surface, lemma, pos, None, None, built, f"UPOS={pos}", lead, []))
    bare = "".join(char for char in surface if "א" <= char <= "ת")
    assert (word.lemma, word.built, word.split) == (bare, None, False)
    assert word.syntax is not None and word.syntax.lead == 0


def test_the_day_as_a_noun_keeps_its_article() -> None:
    (day,) = _sentence(("הַיּוֹם", "יום", "NOUN", None, None, "ה the + יום", "UPOS=NOUN", 1, ["DET"]))
    assert (day.lemma, day.built) == ("יום", "ה the + יום")


def test_yours_is_of_with_a_pronoun_not_that_to() -> None:
    # שלכן came back "ש that + ל to + כן + with a pronoun on the end".
    built = "ש that + ל to + כן + with a pronoun on the end"
    (yours,) = _sentence(("שלכן", "של", "ADP", None, None, built, "UPOS=ADP", 2, []))
    assert (yours.lemma, yours.built) == ("של", "שלכן + with a pronoun on the end")
    assert yours.syntax is not None and yours.syntax.lead == 0


def test_there_is_not_has_no_root_or_binyan() -> None:
    # Every existential אין drew pa'al and א־י־ן, and "All forms of" a verb that is none.
    (none,) = _sentence(("אֵין", "אין", "AUX", "פעל", "אין", None, "UPOS=VERB", 0, []))
    assert (none.lemma, none.root, none.binyan) == ("אין", None, None)
    _, none = _sentence(
        ("לא", "לא", "ADV", None, None, None, "UPOS=ADV", 0, []),
        ("ואין", "אין", "AUX", "פעל", "אין", "ו and + אין", "UPOS=VERB", 1, ["CCONJ"]),
    )
    assert (none.root, none.binyan) == (None, None)
    rows = _rows(("שֶׁאֵין", "אין", "AUX", "פעל", "אין", "ש that + אין", "UPOS=VERB", 1, ["SCONJ"]))
    assert (rows[0]["root"], rows[0]["binyan"]) == (None, None), "and the counts the same"


def test_offering_is_of_y_ts_a() -> None:
    # "אז מה את מציעה?": מציע drew י־ע־ץ, "advise".
    (offer,) = _sentence(
        ("מַצִּיעָה", "מציע", "VERB", "הפעיל", "יעץ", None, "UPOS=VERB|Tense=Pres", 0, [])
    )
    assert (offer.lemma, offer.root, offer.binyan) == ("הציע", "יצע", "הפעיל")
    from targum.annotate.verb_roots import root_for

    assert root_for("הציע", "יעץ", "VERB") == ""


def test_a_names_lemma_that_is_another_word_goes_back_to_the_name() -> None:
    # ללאו, "to Leo", under ללא "without"; קירשנבל under היפוגליקמיה.
    (leo,) = _sentence(("ללאו", "ללא", "PROPN", None, None, "ל to + לאו", "UPOS=PROPN", 1, ["ADP"]))
    assert (leo.lemma, leo.built) == ("לאו", "ל to + לאו")
    (name,) = _sentence(("קירשנבל", "היפוגליקמיה", "PROPN", None, None, None, "UPOS=PROPN", 0, []))
    assert name.lemma == "קירשנבל"


def test_a_names_lemma_the_word_spells_stands() -> None:
    assert checked('ד"ר', "ד", 0, "PROPN") is None, "an abbreviation's lemma"
    assert checked("משה", "למשה", 1, "PROPN") is None


def test_doctors_resh_is_the_doctors() -> None:
    # "אמרה ד״ר עינת": ד״ר came back ד, lemma ד"ר, and ר, which the card called the letter.
    dr, resh, name = _sentence(
        ("ד", 'ד"ר', "PROPN", None, None, None, "UPOS=PROPN", 0, []),
        ("ר", "ר", "PROPN", None, None, None, "UPOS=PROPN", 0, []),
        ("עינת", "עינת", "PROPN", None, None, None, "UPOS=PROPN", 0, []),
    )
    assert (dr.lemma, resh.lemma, name.lemma) == ('ד"ר', 'ד"ר', "עינת")
    _, resh = _sentence(
        ("אני", "אני", "PRON", None, None, None, "UPOS=PRON", 0, []),
        ("ר", "ר", "PROPN", None, None, None, "UPOS=PROPN", 0, []),
    )
    assert resh.lemma == "ר", "only after the title's first letter"


@pytest.mark.parametrize(
    ("surface", "built", "prefixes"),
    [
        ("בְּסֵדֶר", "ב in + סדר", ["ADP"]),  # "okay": a preposition in front, a fixed phrase
        ("בבקשה", "ב in + בקשה", ["ADP"]),  # "please"
        ("הֲפָרָה", "ה the + פרה", ["DET"]),  # "breach", not "the cow": a hataf, no article
        ("וַעַד", "ו and + עד", ["CCONJ"]),  # "committee": a patach, no conjunction
        ("הרגל", "ה the + רגל", ["DET"]),  # "habit", as the scenes point it wrongly
        ("כשהשכן", "כ as + ש that + ה the + שכן", []),  # cut, but nothing tagged
    ],
)
def test_a_whole_word_dicta_meant_stays_the_lemma(
    surface: str, built: str, prefixes: list[str]
) -> None:
    bare = "".join(char for char in surface if "א" <= char <= "ת")
    lead = built.count(" + ")
    (word,) = _sentence((surface, bare, "NOUN", None, None, built, "UPOS=NOUN", lead, prefixes))
    assert word.lemma == bare
