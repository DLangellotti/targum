"""What the chat is told about how to write, checked where it is written.

`design.md` §6 governs every English sentence the chat produces, and `test_brand.py`
cannot see a model's output: it scans stylesheets, scripts and templates, and a reply
is in none of them. So the rules live in `chat/prompts.py`, and this file holds them
there — if a rule is taken out of the prompt, this is the test that says so.
"""

from __future__ import annotations

from targum.chat import prompts
from targum.chat.tools import REGISTRY


def test_the_voice_rules_are_in_the_prompt() -> None:
    said = prompts.SYSTEM
    assert "always lowercase: targum" in said
    assert "No emoji" in said and "No exclamation marks" in said
    assert "No invented currency" in said and "not a placement" in said
    assert "Short." in said
    assert "Plain text only" in said and "no markdown" in said
    assert "Second person" in said


def test_the_prompt_keeps_its_own_rules() -> None:
    """A prompt that broke §6 while teaching it would be the one place nobody checked."""
    assert "!" not in prompts.SYSTEM
    assert "Targum" not in prompts.SYSTEM.replace("targum", "")


def test_the_prompt_says_it_cannot_spend() -> None:
    assert "cannot spend" in prompts.SYSTEM and "start a build" in prompts.SYSTEM


def test_the_prompt_says_it_cannot_open_a_text_and_must_give_its_path() -> None:
    """A reader asked to read a text and was told it was open and ready, with no way in."""
    assert "cannot open a text" in prompts.SYSTEM
    assert "on a line of its own" in prompts.SYSTEM
    assert "draws that line as a door" in prompts.SYSTEM
    assert "Never say a text is open" in prompts.SYSTEM


def test_hebrew_is_content_and_graded() -> None:
    assert "Hebrew is content" in prompts.SYSTEM
    assert "one new word at most" in prompts.SYSTEM


def test_no_tool_in_this_slice_spends() -> None:
    """The seam is drawn before the first tool needs it: every tool that spends will need
    a consent row, and nothing here has one to give."""
    assert not [tool.name for tool in REGISTRY if tool.spends or tool.needs_consent]


def test_a_question_from_a_word_s_card_is_answered_in_english_about_the_text() -> None:
    """A word tapped is a question half-asked (2026-09-06): the card's Ask sends the
    text, the sentence and the word along, and the model is told what to do with them —
    and told that on scripture it writes no Hebrew of its own."""
    said = prompts.SYSTEM
    assert "the word they tapped" in said
    assert "answered in English, about the text" in said
    assert "on scripture write no Hebrew of" in said


def test_the_ladder_a_reader_may_name_is_in_the_prompt_from_the_one_table() -> None:
    """A reader asked for "a bet plus level" and was not understood (2026-09-06). The
    rungs are written into the prompt from `level.ULPAN`, with what each is reckoned to
    want, so the model can turn a name into a search — and is still told never to hand
    the reader's own rung back as a placement."""
    from targum import level

    said = prompts.SYSTEM
    for rung in level.ULPAN:
        assert f"{rung.name} ({rung.letter}, about {rung.at:,} words)" in said
    assert "bet plus" in said and "RUNGS" not in said
    assert "max_looked_up_percent" in said
    assert "Never tell them which rung they are at" in said


def test_a_text_sent_with_a_line_is_never_asked_for_again() -> None:
    """A reader sent a picture with "open this and help me learn it" and was asked for a
    link. The prompt now says what a brought text's note means and what not to do."""
    from targum.chat.prompts import SYSTEM

    assert "never ask for it, for a link, or for its words again" in SYSTEM
    assert "You cannot open it yourself" in SYSTEM
