"""The pronoun on the end, named off what a stored token carries (targum-internal#450)."""

from __future__ import annotations

from targum.annotate.suffixes import FLAG, agrees, code_of, reading, said


def dicta(surface: str, lemma: str, pos: str, pointed: str = "") -> str:
    """A word as DICTA stores it: the suffix a flag on the pieces line."""
    built = f"{surface} + {FLAG}"
    return reading(surface=surface, built=built, pos=pos, lemma=lemma, pointed=pointed)


def test_a_modern_word_is_read_off_its_flag_and_its_ending() -> None:
    assert dicta("לפניהם", "לפני", "ADP") == "3mp"
    assert dicta("שלו", "של", "ADP") == "3ms"
    assert dicta("ספרו", "ספר", "NOUN") == "3ms"
    assert dicta("אותך", "את", "ADP") == "2cs", "unpointed, ־ך says neither gender"
    assert dicta("עליהן", "על", "ADP") == "3fp"
    assert dicta("ביתכם", "בית", "NOUN") == "2mp"
    assert dicta("ממנו", "מן", "ADP") == "3ms", "from him, the commoner"
    # The stem comes off first: זמנו is זמן and ו, "his", not "our".
    assert dicta("זמנו", "זמן", "NOUN") == "3ms"
    assert dicta("ביטחונו", "ביטחון", "NOUN") == "3ms"
    # מתוכם is מ, תוך and ם, "from among them", not "you".
    built = f"מ from + תוכם + {FLAG}"
    assert reading(surface="מתוכם", built=built, pos="NOUN", lemma="תוך") == "3mp"
    # And the pointing says which "you".
    assert dicta("לך", "ל", "ADP", pointed="לְךָ") == "2ms"
    assert dicta("לך", "ל", "ADP", pointed="לָךְ") == "2fs"


def test_a_word_with_no_flag_or_a_pronoun_of_its_own_has_none() -> None:
    assert reading(surface="ולבית", built="ו and + ל to + בית", pos="NOUN", lemma="בית") == ""
    # לכן is "therefore", and DICTA's pieces line says so by having no flag.
    assert reading(surface="לכן", built="ל to + כן", pos="ADV", lemma="לכן") == ""
    assert reading(surface="והן", built=f"ו and + הן + {FLAG}", pos="PRON", lemma="הן") == ""
    assert reading(surface="ספר", built=None, pos="NOUN", lemma="ספר") == ""


def oshb(built: str, lemma: str, pos: str, pointed: str) -> str:
    """A word as Open Scriptures' tagging stores it: the suffix a piece of its own."""
    bare = "".join(ch for ch in pointed if "א" <= ch <= "ת")
    return reading(surface=bare, built=built, pos=pos, lemma=lemma, pointed=pointed)


def test_a_biblical_word_is_read_off_its_last_piece() -> None:
    assert oshb("ל + פני + הם", "פנים", "NOUN", "לִפְנֵיהֶ֑ם") == "3mp"
    assert oshb("זרע + ו", "זרע", "NOUN", "זַרְעוֹ") == "3ms"
    assert oshb("ב + ו", "ב", "ADP", "ב֖וֹ") == "3ms"
    assert oshb("את + ם", "את", "PART", "אֹתָ֛ם") == "3mp"
    assert oshb("מ + כם", "מן", "PRON", "מִכֶּ֣ם") == "2mp"
    assert oshb("ב + הן", "הן", "PRON", "בָּהֵ֖ן") == "3fp", "in them, filed under the pronoun"
    assert oshb("ממ + נה", "מן", "ADP", "מִמֶּ֖נָּה") == "3fs", "a doubled nun is the third person"
    assert oshb("קרב + נה", "קרב", "NOUN", "קִרְבֶּ֗נָה") == "3fp"
    assert oshb("ממ + נו", "מן", "ADP", "מִמֶּנּוּ") == "3ms"
    assert oshb("צלמ + נו", "צלם", "NOUN", "צַלְמֵ֖נוּ") == "1cp"
    assert oshb("ידי + ך", "יד", "NOUN", "יָדֶ֫יךָ") == "2ms"
    assert oshb("אהל + ה", "אהל", "NOUN", "אָהֳלֹֽה") == "3ms", "the old spelling of his"


def test_a_biblical_word_with_no_pronoun_on_the_end_has_none() -> None:
    assert oshb("ו + הוא", "הוא", "PRON", "וְהֽוּא") == "", "and he"
    assert oshb("ו + המה", "הם", "PRON", "וְהֵמָּה") == ""
    assert oshb("ו + כה", "כה", "ADV", "וְכֹה") == "", "and thus"
    assert oshb("ל + כן", "כן", "ADV", "לָכֵן") == "", "therefore"
    assert oshb("ארצ + ה", "ארץ", "NOUN", "אַ֫רְצָה") == "", "to the land: the ה of direction"
    assert oshb("ישמעו + ן", "שמע", "VERB", "יִשְׁמְעוּן") == "", "the long ending"


def test_the_card_says_whose_or_whom() -> None:
    assert said("3mp", pos="NOUN", lemma="פנים", built="ל + פני + הם") == "before them"
    assert said("3mp", pos="ADP", lemma="לפני", built=f"לפניהם + {FLAG}") == "before them"
    assert said("3ms", pos="NOUN", lemma="ספר") == "his"
    assert said("3ms", pos="ADP", lemma="של") == "his"
    assert said("2ms", pos="ADP", lemma="ל") == "to you (m.)"
    assert said("2cs", pos="ADP", lemma="את") == "you"
    assert said("2ms", pos="PART", lemma="את", lexeme="854") == "with you (m.)"
    assert said("3ms", pos="VERB", lemma="שמר") == "him"
    assert said("3mp", pos="NOUN", lemma="פנים", built="ו + פני + הם") == "their"
    assert said("1cp", pos="NOUN", lemma="כל") == "all of us"
    assert said("", pos="NOUN", lemma="ספר") == ""


def test_a_reading_agrees_with_the_gold_on_person_number_and_any_gender_said() -> None:
    assert agrees("3mp", "3mp")
    assert agrees("2cs", "2ms"), "you, unpointed, is true of either"
    assert not agrees("2fs", "2ms")
    assert not agrees("3ms", "1cs")
    assert not agrees("", "3ms")
    assert code_of("3", "Masc", "Plur") == "3mp"
    assert code_of("1", "Fem,Masc", "Sing") == "1cs"
    assert code_of("2", "f", "s") == "2fs"
    assert code_of("", "Masc", "Sing") == ""
