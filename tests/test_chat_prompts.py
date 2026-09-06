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
