"""A participle's מ and an infinitive's ל that DICTA cut off as a prefix, given back to the
word at page-build and count time (`annotate.own_letter`, targum-internal#689).

Each token is what DICTA said of the word, read back as the annotator stores it: the
Shoelace Seller's מֻשְׁפָּלוֹת and לִמְכֹּר came out exactly so. Single words only.
"""

from __future__ import annotations

import pytest

from targum.annotate.lemma_check import mend_row, mended
from targum.annotate.own_letter import _male, _marked, own_letter
from targum.models import Annotation, Syntax, Token

DICTA = "dicta/dicta-il/dictabert-joint/roots+everyword+entities+syntax+grammar/8"


def _token(
    surface: str,
    lemma: str,
    pos: str,
    built: str | None,
    feats: str,
    lead: int = 1,
    prefixes: tuple[str, ...] = (),
    binyan: str | None = None,
    root: str | None = None,
) -> Token:
    return Token(
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
        syntax=Syntax(head=-1, relation="root", prefixes=prefixes, lead=lead),
    )


def _mended(token: Token) -> Token:
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator=DICTA,
        method="frequency",
        method_note="",
        tokens={"s1": [token]},
    )
    return mended(annotation).tokens["s1"][0]


# DICTA on "ועיניו מֻשְׁפָּלוֹת", handed משפלות: the מ as "from", lemma שפל, read as a qal.
LOWERED = _token(
    "מֻשְׁפָּלוֹת",
    "שפל",
    "VERB",
    "מ from + שפלות",
    "UPOS=VERB|Gender=Fem|Number=Plur",
    binyan="פעל",
    root="שפל",
)
# DICTA on "אותי לִמְכֹּר", handed למכר: the ל as "to" and the noun מכר.
TO_SELL = _token("לִמְכֹּר", "מכר", "NOUN", "ל to + מכר", "UPOS=NOUN|Gender=Masc|Number=Sing")


def test_a_hufal_participles_mem_is_its_own() -> None:
    word = _mended(LOWERED)
    assert word.built is None
    assert not word.split
    assert word.syntax is not None and word.syntax.lead == 0
    # Huf'al הֻשְׁפַּל, "was lowered", of ש־פ־ל, in the ktiv male lemmas are filed in.
    assert (word.lemma, word.pos, word.binyan, word.root) == ("הושפל", "VERB", "הופעל", "שפל")
    assert word.feats == "UPOS=VERB|Gender=Fem|Number=Plur"


def test_an_infinitives_lamed_is_its_own() -> None:
    word = _mended(TO_SELL)
    # No "ל to" in front of a meaning that already says "to sell".
    assert word.built is None
    assert not word.split
    assert (word.lemma, word.pos, word.binyan, word.root) == ("מכר", "VERB", "פעל", "מכר")
    assert word.feats == "UPOS=VERB|Gender=Masc|Number=Sing"


def test_an_infinitive_dicta_read_as_one_keeps_its_lemma() -> None:
    # A verb with no person, gender or tense is an infinitive: לִכְתֹּב, "to write".
    word = _mended(_token("לִכְתֹּב", "כתב", "VERB", "ל to + כתב", "UPOS=VERB|Number=Sing"))
    assert (word.built, word.lemma, word.pos) == (None, "כתב", "VERB")


def test_the_counts_read_the_same_word() -> None:
    row = LOWERED.model_dump()
    counted = mend_row(row)
    assert (counted["lemma"], counted["pos"], counted["binyan"]) == ("הושפל", "VERB", "הופעל")
    assert counted["built"] is None
    assert counted["syntax"]["lead"] == 0
    assert mend_row(TO_SELL.model_dump())["pos"] == "VERB"


def test_a_conjunction_in_front_stays_on_the_line() -> None:
    word = _mended(
        _token(
            "וּמֻשְׁפָּלוֹת",
            "שפל",
            "VERB",
            "ו and + מ from + שפלות",
            "UPOS=VERB|Gender=Fem|Number=Plur",
            lead=2,
            prefixes=("CCONJ",),
        )
    )
    assert word.built == "ו and + משפלות"
    assert word.syntax is not None and word.syntax.lead == 1
    assert word.lemma == "הושפל"


def test_a_pronoun_on_the_end_stays_on_the_line() -> None:
    word = _mended(
        _token("לְהַעֲבִירוֹ", "העביר", "VERB", "ל to + העבירו + with a pronoun on the end", "UPOS=VERB")
    )
    assert word.built == "להעבירו + with a pronoun on the end"
    assert word.lemma == "העביר"


@pytest.mark.parametrize(
    ("pointed", "lemma", "binyan"),
    [
        ("לְדַבֵּר", "דבר", "פיעל"),  # "to speak": ל in place of יְדַבֵּר's prefix
        ("לְהַשְׁפִּיל", "השפיל", "הפעיל"),  # "to lower": לה in place of יַשְׁפִּיל's
        ("לְהִכָּנֵס", "נכנס", "נפעל"),  # "to enter"
    ],
)
def test_a_pointed_infinitive_is_read_beside_its_future(
    pointed: str, lemma: str, binyan: str
) -> None:
    own = own_letter(pointed, lemma, "NOUN", "ל to + x", 1, ())
    assert own is not None
    assert (own.pos, own.lemma, own.binyan, own.built) == ("VERB", lemma, binyan, None)


def test_a_hitpael_participles_hiriq_is_not_min() -> None:
    own = own_letter("מִתְלַבֵּשׁ", "לבש", "VERB", "מ from + תלבש", 1, (), "Gender=Masc")
    assert own is not None
    assert (own.lemma, own.binyan) == ("התלבש", "התפעל")


@pytest.mark.parametrize(
    ("surface", "lemma", "pos", "built", "prefixes"),
    [
        # Tagged a preposition by DICTA: "to a king".
        ("לְמֶלֶךְ", "מלך", "NOUN", "ל to + מלך", ("ADP",)),
        # Untagged, and pointed as the noun: "to a sale", "to a thing".
        ("לְמֶכֶר", "מכר", "NOUN", "ל to + מכר", ()),
        ("לְדָבָר", "דבר", "NOUN", "ל to + דבר", ()),
        # The article inside the ל: "to the king".
        ("לַמֶּלֶךְ", "מלך", "NOUN", "ל to + מלך", ()),
        # A noun's qamats-he, which no infinitive ends on: "for nothing".
        ("לְבַטָּלָה", "בטלה", "VERB", "ל to + בטלה", ()),
        # Unpointed, a noun keeps its ל: למכר is "to sell" and "to a sale" alike.
        ("למכר", "מכר", "NOUN", "ל to + מכר", ()),
        # "After", which DICTA tags a verb and files under איחר.
        ("לְאַחַר", "איחר", "VERB", "ל to + אחר", ()),
        # מִן under its hiriq: "from a house".
        ("מִבַּיִת", "בית", "NOUN", "מ from + בית", ()),
        # A noun cut after מ is the preposition, not a participle: "from between".
        ("מבינות", "בינה", "NOUN", "מ from + בינות", ()),
        # A pi'el's present, but pointed with a hif'il's patach: kept rather than guessed.
        ("מַחֲזֶקֶת", "חזק", "VERB", "מ from + חזקת", ()),
    ],
)
def test_a_real_preposition_stays_cut(
    surface: str, lemma: str, pos: str, built: str, prefixes: tuple[str, ...]
) -> None:
    assert own_letter(surface, lemma, pos, built, 1, prefixes, f"UPOS={pos}") is None
    token = _token(surface, lemma, pos, built, f"UPOS={pos}", prefixes=prefixes)
    assert _mended(token).built == built


def test_a_gap_lemma_keeps_its_cut_unless_the_marks_say_infinitive() -> None:
    # DICTA gave the word itself as the lemma: no verb to stand behind the ל.
    assert own_letter("ולעגלתי", "ולעגלתי", "VERB", "ו and + ל to + עגלתי", 2, ("CCONJ",)) is None


@pytest.mark.parametrize(
    ("pointed", "written"),
    [("מֻשְׁפָּלוֹת", "מושפלות"), ("לִמְכֹּר", "למכור"), ("לֶאֱכֹל", "לאכול")],
)
def test_the_table_is_asked_in_ktiv_male(pointed: str, written: str) -> None:
    assert _male(_marked(pointed)) == written


def test_forever_is_never_an_infinitive_and_to_win_is() -> None:
    # DICTA reads לנצח "forever" as an adverb and leaves it whole, so nothing here
    # reaches it (pm and ling-he on targum#1191; probed on three modern sentences).
    forever = _token("לנצח", "נצח", "ADV", "ל to + נצח", "UPOS=ADV")
    assert _mended(forever) is forever or _mended(forever).built == "ל to + נצח"
    # Read by DICTA as the verb, לְנַצֵּחַ "to win" (or unpointed, as in "מתאמצים לנצח איש
    # את חברו") keeps its ל.
    for written in ("לְנַצֵּחַ", "לנצח"):
        word = _mended(_token(written, "ניצח", "VERB", "ל to + נצח", "UPOS=VERB"))
        assert (word.pos, word.built, word.lemma) == ("VERB", None, "ניצח")


# -- ling-he's analyser read of 2026-11-13 (targum-internal#699) ------------------------

ADJ_MS = "UPOS=ADJ|Gender=Masc|Number=Sing"


def _sentence(*tokens: Token) -> list[Token]:
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator=DICTA,
        method="frequency",
        method_note="",
        tokens={"s1": list(tokens)},
    )
    return mended(annotation).tokens["s1"]


@pytest.mark.parametrize(
    ("surface", "lemma", "lead", "built", "adjective"),
    [
        ("ומכובד", "כובד", 1, "ו and + מכובד", "מכובד"),  # not כובד, "weight"
        ("מצוין", "צוין", 0, None, "מצוין"),  # not "was noted"
        ("מְצוּיָּן", "צוין", 0, None, "מצוין"),
        ("מוּכָּר", "הוכר", 0, None, "מוכר"),
        ("המיועד", "יועד", 1, "ה the + מיועד", "מיועד"),
        ("מסודרות", "סודר", 0, None, "מסודר"),  # not סודר, "scarf"
        ("מַצְחִיק", "הצחיק", 0, None, "מצחיק"),
    ],
)
def test_an_adjective_that_is_a_participle_is_filed_under_the_participle(
    surface: str, lemma: str, lead: int, built: str | None, adjective: str
) -> None:
    prefixes = ("CCONJ",) if lead and surface.startswith("ו") else ("DET",) if lead else ()
    word = _mended(_token(surface, lemma, "ADJ", built, ADJ_MS, lead=lead, prefixes=prefixes))
    assert (word.lemma, word.pos, word.binyan, word.root) == (adjective, "ADJ", None, None)
    assert word.built == built, "only the lemma moves"


def test_an_adjective_the_table_does_not_hold_keeps_its_lemma() -> None:
    # מְקוּבָּל under קובל: the table has no קובל, so nothing here can say which it is.
    word = _mended(_token("מְקוּבָּל", "קובל", "ADJ", None, ADJ_MS, lead=0))
    assert word.lemma == "קובל"


def test_one_alone_and_respected() -> None:
    # "אני אחד יחיד ומכובד", ארי האריה מחפש חבר.
    one, alone, respected = _sentence(
        _token("אחד", "אחד", "NUM", None, "UPOS=NUM", lead=0),
        _token("יחיד", "יחיד", "ADJ", None, ADJ_MS, lead=0),
        _token("ומכובד", "כובד", "ADJ", "ו and + מכובד", ADJ_MS, prefixes=("CCONJ",)),
    )
    assert (one.lemma, alone.lemma, respected.lemma) == ("אחד", "יחיד", "מכובד")
    assert respected.built == "ו and + מכובד"


def test_excellent_now_right() -> None:
    # "מצוין, עכשיו ימינה".
    excellent, now = _sentence(
        _token("מצוין", "צוין", "ADJ", None, "UPOS=ADJ", lead=0),
        _token("עכשיו", "עכשיו", "ADV", None, "UPOS=ADV", lead=0),
    )
    assert (excellent.lemma, now.lemma) == ("מצוין", "עכשיו")


@pytest.mark.parametrize(
    ("surface", "lemma", "verb", "binyan"),
    [
        ("להכין", "להכין", "הכין", ""),  # "החל להכין תוכנית עצלה"
        ("לשמור", "לשמור", "שמר", "פעל"),  # "לשמור על הילדים"
        ("למצוא", "ימצא", "מצא", "פעל"),  # "למצוא משהו זול"
    ],
)
def test_a_whole_infinitive_is_filed_under_its_verb(
    surface: str, lemma: str, verb: str, binyan: str
) -> None:
    word = _mended(_token(surface, lemma, "VERB", None, "UPOS=VERB", lead=0))
    assert (word.lemma, word.pos, word.binyan or "") == (verb, "VERB", binyan)
    assert word.built is None


def test_a_future_standing_as_the_lemma_takes_its_verb() -> None:
    # "אֶבְדּוֹק" under the future יבדוק.
    feats = "UPOS=VERB|Person=3|Number=Sing|Tense=Fut"
    word = _mended(_token("אֶבְדּוֹק", "יבדוק", "VERB", None, feats, lead=0))
    assert (word.lemma, word.binyan) == ("בדק", "פעל")


def test_to_patrol_is_not_to_plus_patrol() -> None:
    # "וחייך קייאה לסייר בלש", סימון התנין: DICTA tagged the ל a preposition.
    _, patrol, detective = _sentence(
        _token("קייאה", "קייאה", "VERB", None, "UPOS=VERB", lead=0),
        _token("לסייר", "סייר", "VERB", "ל to + סייר", "UPOS=VERB", prefixes=("ADP",)),
        _token("בלש", "בלש", "NOUN", None, "UPOS=NOUN", lead=0),
    )
    assert (patrol.built, patrol.split, patrol.lemma) == (None, False, "סייר")
    assert patrol.syntax is not None and patrol.syntax.lead == 0
    assert detective.lemma == "בלש"


def test_a_tagged_preposition_on_a_finite_verb_or_a_noun_stays_cut() -> None:
    past = "UPOS=VERB|Person=3|Number=Sing|Tense=Past"
    assert own_letter("לסייר", "סייר", "VERB", "ל to + סייר", 1, ("ADP",), past) is None
    assert own_letter("לסייר", "סייר", "NOUN", "ל to + סייר", 1, ("ADP",), "UPOS=NOUN") is None
