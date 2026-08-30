"""The two things that stop the weekly doing harm.

Both are public and both are tested here rather than beside the private compose loop,
because a licence boundary enforced by code CI never runs is a licence boundary enforced
by nothing.
"""

from __future__ import annotations

import pytest

from targum.errors import TargumError
from targum.weekly.models import Level, Part, Story
from targum.weekly.verify import (
    LIFT,
    Gauge,
    grams,
    in_band,
    lifted,
    missed,
    no_lifted_wording,
    words_of,
)

HEADLINE = "הקבוצה מתל אביב ניצחה במשחק החוץ שלה בתוצאה שתיים אפס"


def facts(headline: str = HEADLINE, tier: int = 2, excerpt: str = "") -> Story:
    return Story(section=Part.sport, headline=headline, tier=tier, excerpt=excerpt)


# -- what counts as somebody else's words --------------------------------------------


def test_points_do_not_hide_a_lift() -> None:
    """Nikkud is a difference no reader can see, and pointing a lifted sentence
    differently from the headline it came out of would otherwise walk it past."""
    assert words_of("שָׁלוֹם עֲלֵיכֶם") == words_of("שלום עליכם")


def test_the_same_facts_told_again_are_not_a_lift() -> None:
    """The whole feature depends on this being allowed. Facts are not somebody's
    property; the sentence they wrote around them is."""
    honest = "קבוצה מהעיר גברה על יריבתה בשתי מכות ללא מענה ועלתה לראש הטבלה"
    assert lifted(honest, [facts()]) == []


def test_a_lifted_clause_is_caught() -> None:
    found = lifted("הקבוצה מתל אביב ניצחה במשחק החוץ שלה אתמול", [facts()])
    assert found
    assert "ניצחה" in found[0].phrase


def test_a_licensed_source_may_be_drawn_on() -> None:
    """Tier 1 named a licence and the issue credits it at the foot. Overlap there is
    permitted rather than overlooked."""
    assert lifted(HEADLINE, [facts(tier=1)]) == []


def test_a_facts_only_story_cannot_hold_an_excerpt_at_all() -> None:
    """The strongest form the licence boundary takes: not a rule the gatherer follows,
    but a structure that cannot represent the violation.

    It matters that this lives on the model rather than in the private gatherer, which
    does not ship — enforced there, the one rule keeping somebody else's prose out of an
    issue would be enforced by code no other machine ever runs.
    """
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        facts(tier=2, excerpt="their own sentence, word for word")


def test_a_licensed_excerpt_is_still_checked_for_lifts_from_others() -> None:
    """Tier 1 may be quoted. That says nothing about the outlet next to it."""
    excerpt = "המשחק נגמר ברבע השלישי כשהקבוצה האורחת קבעה את התוצאה"
    quoted = facts(headline="משהו אחר לגמרי", tier=1, excerpt=excerpt)
    assert lifted(excerpt, [quoted]) == [], "its own licensed wording is allowed"
    assert lifted(excerpt, [facts(headline=excerpt)]), "the same run from a tier-2 source is not"


@pytest.mark.parametrize("length", [1, 2, 3, 4])
def test_a_short_shared_run_is_not_evidence(length: int) -> None:
    """Two writers reporting one event collide on a name, a number and a verb. Five
    words in a row is where that stops being a coincidence."""
    shared = " ".join(HEADLINE.split()[:length])
    assert lifted(shared, [facts()]) == []


def test_five_is_where_it_starts() -> None:
    shared = " ".join(HEADLINE.split()[:LIFT])
    assert lifted(shared, [facts()])


def test_a_run_that_is_mostly_a_figure_is_still_a_lift() -> None:
    """Digits are in the comparison, so five words containing a score cannot slip past
    by having only four ordinary words in them."""
    headline = "הקבוצה סיימה את המשחק בתוצאה 2 0 בחוץ"
    assert lifted(headline, [facts(headline=headline)])


def test_nothing_written_cannot_lift_anything() -> None:
    assert lifted("", [facts()]) == []
    assert grams("") == set()


# -- the guard itself -----------------------------------------------------------------


def test_the_guard_refuses_and_says_what_to_rewrite() -> None:
    with pytest.raises(TargumError) as raised:
        no_lifted_wording("הקבוצה מתל אביב ניצחה במשחק החוץ שלה אתמול", [facts()])
    assert "ניצחה" in str(raised.value.hint if hasattr(raised.value, "hint") else raised.value)


def test_the_guard_passes_honest_prose() -> None:
    no_lifted_wording("קבוצה מהעיר גברה על יריבתה ועלתה לראש הטבלה", [facts()])


# -- the band gate --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "difficulty", "sentence", "ok"),
    [
        (Level.aleph, 12, 7.0, True),
        (Level.aleph, 12, 15.0, False),  # right words, sentences of the wrong level
        (Level.aleph, 30, 7.0, False),  # right sentences, words of the wrong level
        (Level.bet, 15, 12.0, True),
        (Level.gimel, 22, 18.0, True),
        (Level.gimel, 40, 18.0, False),
    ],
)
def test_a_level_has_to_land_on_both_rulers(
    level: Level, difficulty: int, sentence: float, ok: bool
) -> None:
    """One was not enough. The word ruler cannot separate the first two levels — writing
    for a small vocabulary means explaining who everybody is, and an explanation is more
    words rather than commoner ones."""
    assert in_band(level, Gauge(difficulty=difficulty, sentence=sentence)) is ok


def test_a_miss_names_which_half_went_wrong() -> None:
    """A model asked to make something "easier" reaches for commoner words when the
    problem was the sentences, and the other way round. So the feedback says which."""
    assert missed(Level.bet, Gauge(difficulty=15, sentence=12.0)) == ""

    words_wrong = missed(Level.bet, Gauge(difficulty=30, sentence=12.0))
    assert "vocabulary" in words_wrong and "sentence" not in words_wrong.lower().split("words.")[0]

    sentences_wrong = missed(Level.aleph, Gauge(difficulty=12, sentence=20.0))
    assert "Sentences averaged 20.0" in sentences_wrong and "Shorter" in sentences_wrong

    both = missed(Level.aleph, Gauge(difficulty=40, sentence=20.0))
    assert "vocabulary" in both and "Sentences" in both


def test_the_bands_rise_with_the_levels() -> None:
    """They overlap, which is harmless — a level is only ever checked against its own,
    never used to classify a text into one. What matters is that they climb."""
    from targum.weekly.models import LEVELS

    for name in ("band", "sentence"):
        floors = [getattr(LEVELS[level], name)[0] for level in Level]
        ceilings = [getattr(LEVELS[level], name)[1] for level in Level]
        assert floors == sorted(floors), name
        assert ceilings == sorted(ceilings), name


# -- the measurement ------------------------------------------------------------------


@pytest.mark.stanza
def test_the_ruler_is_the_one_the_library_filters_on(needs_hebrew_model: None) -> None:
    """Segment, annotate, count — the same three steps a build runs, so the number here
    is the number the entry will carry rather than an approximation of it."""
    from targum.weekly.verify import measure

    easy = "הוועדה תבדוק את מחירי הדיור. היא תגיש דוח בעוד חצי שנה. השרים יקראו אותו."
    hard = (
        "הוועדה הציבורית שמינתה הממשלה תידרש לבחון את התייקרות מחירי הדיור "
        "ולגבש המלצות מחייבות בתוך שישה חודשים, לאחר התייעצות עם גורמי המקצוע."
    )
    assert measure(easy) < measure(hard), "the ruler orders these the way a reader would"


@pytest.mark.stanza
def test_the_section_headings_are_not_counted(needs_hebrew_model: None) -> None:
    """They are the same five words every week. Counting them would drag every issue's
    number toward every other issue's."""
    from targum.weekly.verify import measure

    body = "הוועדה תבדוק את מחירי הדיור. היא תגיש דוח בעוד חצי שנה."
    assert measure(body) == measure(f"# ישראל\n\n{body}\n\n# ספורט\n\n")


@pytest.mark.stanza
def test_nothing_to_measure_is_nought_rather_than_a_crash(needs_hebrew_model: None) -> None:
    from targum.weekly.verify import measure

    assert measure("") == 0
    assert measure("# ישראל\n\n# ספורט") == 0


@pytest.mark.stanza
def test_the_two_rulers_measure_different_things(needs_hebrew_model: None) -> None:
    """Why there are two, pinned with the case that made it necessary.

    Prose written for a small vocabulary explains who everybody is, and an explanation
    is more words rather than commoner ones — so the word ruler can rate it *harder*
    than the simplified version of the same news. Sentence length does not have that
    problem, and between them they place a level correctly.
    """
    from targum.weekly.verify import gauge

    explained = (
        "גל גדות היא שחקנית ישראלית ידועה. היא דיברה על התפקיד הגדול שלה. "
        "לדבריה, האולפנים לא עדכנו אותה."
    )
    dense = (
        "השחקנית גל גדות התייחסה בראיון שהעניקה השבוע להמשך גלגולה של הדמות שגילמה, "
        "ומסרה כי לא עודכנה בדבר על ידי האולפנים בשלב זה."
    )
    simple, complicated = gauge(explained), gauge(dense)
    assert simple.sentence < complicated.sentence, "sentence length orders them"


@pytest.mark.stanza
def test_a_headline_is_not_a_sentence(needs_hebrew_model: None) -> None:
    """Section headings are the same five words every week, and an item headline is
    not a sentence. Counted, they drag every issue's numbers toward every other
    issue's and flatten the mean that does most of the work here."""
    from targum.weekly.verify import gauge

    prose = 'השב"כ אמר שהיה איום ממשי. בגלל האיום החליטו להחזיר אותו לישראל מהר.'
    assert gauge(prose) == gauge(f"# ישראל\n\n### כותרת קצרה\n\n{prose}")


# -- prose that reads as machine-written ----------------------------------------------


def test_an_em_dash_is_the_giveaway() -> None:
    """It is not part of ordinary Hebrew punctuation, so its presence is close to proof
    on its own — which is why it is first on the list."""
    from targum.weekly.verify import tells

    assert tells("שבוע של אזהרות — ושתי שיבות") == ["an em-dash, which is not Hebrew punctuation"]
    assert tells("שבוע של אזהרות, ושתי שיבות") == []


@pytest.mark.parametrize(
    "phrase",
    ["חשוב לציין", "ראוי להדגיש", "לא רק", "יש הסבורים", "על פי דיווחים", "לסיכום"],
)
def test_the_formulaic_phrases_are_caught(phrase: str) -> None:
    from targum.weekly.verify import tells

    assert tells(f"הוועדה תבדוק את הנושא. {phrase} שהדוח יוגש בקרוב.")


def test_ordinary_reporting_passes() -> None:
    from targum.weekly.verify import tells

    filed = (
        'השב"כ אמר שהיה איום ממשי לפגוע ביאיר נתניהו. בגלל האיום החליטו להחזיר אותו '
        "לישראל מהר, בדרך שאינה הדרך הרגילה."
    )
    assert tells(filed) == []


def test_the_rewrite_is_told_what_to_take_out() -> None:
    """Named, not scolded: the model has to know which words to replace, and "write
    better" is not something it can act on."""
    from targum.weekly.verify import tell_note, tells

    note = tell_note(tells("הוועדה — לא רק בדקה"))
    assert "em-dash" in note and "לא רק" in note
    assert tell_note([]) == ""


def test_a_run_that_is_mostly_names_is_the_facts_not_the_prose() -> None:
    """A real issue was blocked on "באוגוסט הרוג בקפריסין הצפות בסוריה" — a month and
    two countries. There is no other way to say a death in Cyprus and flooding in Syria,
    so a run that is mostly named entities is the events themselves rather than
    anybody's sentence about them. Nobody owns a place name.

    And `--anyway` deliberately cannot publish through a lift, so a false positive here
    is a hard block rather than a warning, which is why it is worth getting right.
    """
    from targum.weekly.verify import lifted

    headline = "מזג אוויר קיצוני באוגוסט: הרוג בקפריסין, הצפות בסוריה וגשמים באזור"
    # Shares only the run of facts. Everything around it is the writer's own, which is
    # exactly the shape the real block had.
    written = "השבוע נרשמו באוגוסט הרוג בקפריסין הצפות בסוריה ורוחות עזות בכל האזור"
    named = frozenset({"בקפריסין", "בסוריה"})

    assert lifted(written, [facts(headline=headline)]), "without the exemption it fires"
    assert lifted(written, [facts(headline=headline)], names=named) == []


def test_a_headline_reproduced_whole_is_still_a_lift() -> None:
    """The exemption forgives a run of facts inside somebody's own sentence. It does not
    forgive copying the sentence: the runs that are not mostly names still fire."""
    from targum.weekly.verify import lifted

    headline = "מזג אוויר קיצוני באוגוסט: הרוג בקפריסין, הצפות בסוריה וגשמים באזור"
    named = frozenset({"בקפריסין", "בסוריה"})
    assert lifted(headline, [facts(headline=headline)], names=named)


def test_a_verb_means_somebody_composed_it() -> None:
    """The exemption is for a caption of events, not for any run containing a place.
    Two names and a verb is still a sentence, and the sentence is theirs."""
    from targum.weekly.verify import lifted

    headline = "המשטרה סבורה כי הירי ביפו קשור למאבק בין משפחות ברהט"
    assert lifted(
        headline,
        [facts(headline=headline)],
        names=frozenset({"ביפו", "ברהט"}),
        verbs=frozenset({"סבורה", "קשור"}),
    )
