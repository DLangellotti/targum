"""Aramaic's emphatic state, read off the pointing (design.md §12, "Aramaic has a hard-spot
list" and "Aramaic's lenses", 2026-10-25): the ending that says "the"."""

from __future__ import annotations

import pytest

from targum.annotate.aramaic_state import absolute, construct, emphatic, state
from targum.models import Token
from targum.render.builder import _state_line


@pytest.mark.parametrize(
    "word",
    [
        "אַרְעָא",  # the earth: ־ָא
        "מַיָּא",  # the water, its yod doubled
        "שְׁמַיָּא",  # the heavens
        "כּוֹכְבַיָּא",  # the stars: the plural's ־יָּא
        "גִּינְתָא",  # the garden: the feminine's ־תָא
        "דִּשְׁמַיָּא",  # of the heavens, with ד on the front
        "וְאַרְעָא",  # and the earth
        "מַלְכָּ֗א",  # the king, with an accent: the dagesh between the qamats and the א
        "זִמְנָא",  # the time
    ],
)
def test_the_emphatic_is_read_off_the_qamats_before_its_alef(word: str) -> None:
    assert emphatic(word)


@pytest.mark.parametrize(
    "word",
    [
        "לָא",  # not
        "וְלָא",  # and not
        "הֲדָא",  # this, feminine
        "חֲדָא",  # one, feminine
        "דִּילְמָא",  # lest
        "קְרָא",  # he called: a verb the hand table knows
        "וַחֲזָא",  # and he saw
        "בְּרָא",  # he created: CְCָא, the perfect of a weak verb
        "וּרְמָא",  # and he cast, the same behind ו
        "הֲוָא",  # he was, which the table files under the pronoun הוּא
        "אַרְעָה",  # ends in ה: Onkelos does not write the emphatic so
        "מַלְכִּין",  # absolute plural
        "ארעא",  # unpointed: nothing to read, so no
        "",
    ],
)
def test_particles_verbs_and_unpointed_words_are_not(word: str) -> None:
    assert not emphatic(word)


def _token(text: str, pos: str | None = None, entity: str | None = None) -> Token:
    return Token(start=0, end=len(text), surface=text, lemma=text, band=0, pos=pos, entity=entity)


def test_the_build_marks_it_on_aramaic_alone_and_never_on_a_name() -> None:
    word = "אַרְעָא"
    assert _state_line(True, _token(word), word) == "State=Emph"
    assert _state_line(False, _token(word), word) == "", "a Hebrew word ending ־ָא is not this"
    assert _state_line(True, _token("עֶזְרָא", pos="PROPN"), "עֶזְרָא") == ""


@pytest.mark.parametrize(
    "word",
    [
        "שְׁנִין",  # years
        "בְּנִין",  # sons
        "חַכִּימִין",  # wise men
        "וּשְׁנִין",  # and years
        "לִנְהוֹרִין",  # for lights
    ],
)
def test_the_absolute_plural_is_read_off_its_hiriq_yod_nun(word: str) -> None:
    assert absolute(word)
    assert state(word) == "Abs"


@pytest.mark.parametrize(
    "word",
    [
        "פָּלְחִין",  # serving: a participle, CָCְCִין
        "דָּיְרִין",  # dwelling: the hollow participle
        "מְהַלְּכִין",  # walking: a derived stem's מְ־
        "מִתְכַּנְּשִׁין",  # gathering
        "מַלְכָּא",  # the king: emphatic
        "מֶלֶךְ",  # a king: the singular says nothing
        "שנין",  # unpointed
    ],
)
def test_participles_and_singulars_are_not_absolute(word: str) -> None:
    assert not absolute(word)


@pytest.mark.parametrize(
    "word",
    [
        "בְּנֵי",  # sons of: the plural's ־ֵי
        "יוֹמֵי",  # days of
        "אַפֵּי",  # the face of
        "בִּמְצִיעוּת",  # in the midst of: ־וּת
        "כָּל",  # all of
        "וּבְכָל",  # and in all of
        "בֵּית",  # house of
    ],
)
def test_the_construct_is_read_off_its_form(word: str) -> None:
    assert construct(word)
    assert state(word) == "Cstr"


@pytest.mark.parametrize(
    "word",
    [
        "אֲרֵי",  # for: a particle
        "לְוַת",  # to: a preposition
        "יְהֵי",  # let there be: the imperfect
        "לְמֶחֱזֵי",  # to see: the infinitive
        "אַסְגֵּי",  # he multiplied: the afel
        "גָּלֵי",  # he reveals: a weak participle
        "יָדְעֵי",  # knowing: the participle's plural
        "מוּת",  # die: too short for ־וּת
        "בני",  # unpointed
        "גַּלֵּי",  # he revealed: the pael, glossed "revealed; to reveal"
        "שֵׁיצֵי",  # he finished: the shafel
        "אַסֵּי",  # he healed
        "וְאֶמְחֵי",  # and I will strike: the imperfect behind ו
        "תֶּחֱזֵי",  # you will see
        "דְיִמְחֵי",  # who strikes: the imperfect behind ד
        "וְתֵיתֵי",  # and you will bring
        "אִתְגְּלֵי",  # he was revealed: the ithpeel
        "וִימוּת",  # and he will die: an imperfect, not ־וּת
        "מִצְרָאֵי",  # the Egyptians: a people's plural, with "the"
        "דְּכֵי",  # clean
        "עֶסְרֵי",  # twenty
    ],
)
def test_verbs_and_particles_ending_alike_are_not_construct(word: str) -> None:
    assert not construct(word)


@pytest.mark.parametrize(
    ("word", "after"),
    [
        ("כַּד", "דְּחִילָא"),  # when: a particle
        ("סַגִּי", "לַחֲדָא"),  # very many: לַחֲדָא is "very"
        ("שְׁבִיעָאָה", "חַגָּא"),  # the seventh: an ordinal
        ("בִּסְרָא", "דְתוֹרָא"),  # the flesh: it is emphatic, and ד says "of"
        ("דְּכֵי", "קֻדְשָׁא"),  # pure, holy
    ],
)
def test_a_word_before_the_emphatic_is_not_always_bound_to_it(word: str, after: str) -> None:
    assert not construct(word, after)


@pytest.mark.parametrize("word", ["אֲרִיחֵי", "אֲרָמוּת", "חַיֵּי", "אַפֵּי"])
def test_a_noun_with_an_imperfect_s_letter_in_front_is_still_construct(word: str) -> None:
    assert construct(word)  # the poles of, the raising of, the life of, the face of


def test_a_singular_is_construct_before_the_emphatic_or_a_name_and_nothing_else() -> None:
    """A noun with no ending of its own says its state by what follows it."""
    assert construct("קַל", "מֵימְרָא")  # the voice of the Word
    assert construct("אִתַּת", "אַבְרָם", after_is_name=True)  # the wife of Abram
    assert not construct("קַל"), "alone, nothing says which"
    assert not construct("דְּכַר", "וְנוּקְבָא"), "male and female: the next word has its own ו"
    assert not construct("יָת", "שְׁמַיָּא"), "the object marker"
    assert not construct("כָּל", "קֳבֵל"), "כָּל־קֳבֵל is because"


def test_the_build_writes_each_state_and_reads_the_next_word() -> None:
    text = "בְּנֵי שְׁנִין קַל מֵימְרָא"
    tokens = []
    for word in text.split():
        start = text.index(word)
        tokens.append(Token(start=start, end=start + len(word), surface=word, lemma=word, band=0))
    assert _state_line(True, tokens[0], text, tokens[1]) == "State=Cstr"
    assert _state_line(True, tokens[1], text, tokens[2]) == "State=Abs"
    assert _state_line(True, tokens[2], text, tokens[3]) == "State=Cstr"
    assert _state_line(True, tokens[2], text) == "", "without the next word, nothing"
    assert _state_line(True, tokens[3], text) == "State=Emph"
