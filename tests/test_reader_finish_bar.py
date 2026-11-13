"""The reader's §14 finish bar, at the build (targum-internal#703, design's pass of
2026-11-13): Hebrew runs in the head and the forms table say their own language, and a
Latin name in a Hebrew line is not a word to learn."""

from __future__ import annotations

import re
from pathlib import Path

from targum.render import builder

ASSETS = Path(builder.__file__).parent / "assets"
TEMPLATES = Path(builder.__file__).parent / "templates"


def test_a_head_names_the_language_of_a_hebrew_run_only() -> None:
    """P2-5: the show, the presenter and the maker in a podcast's or a video's head may be
    Hebrew or Latin ("עושים פוליטיקה", "Yair Lapid"); a Hebrew one under the page's
    `lang="en"` was read in the English voice."""
    assert builder._lang_if_written("עושים פוליטיקה", "he") == ' lang="he"'
    assert builder._lang_if_written("כאן", "he") == ' lang="he"'
    assert builder._lang_if_written("Yair Lapid", "he") == ""
    assert builder._lang_if_written("", "he") == ""


def test_every_name_in_a_head_is_given_its_language() -> None:
    page = (TEMPLATES / "reader.html.j2").read_text(encoding="utf-8")
    for field in ("post.name", "heard_from.show", "heard_from.presenter", "heard_from.by"):
        assert re.search(
            r"<bdi class=\"post-(?:name|handle)[^\"]*\" dir=\"auto\"\{\{ "
            + re.escape(field)
            + r"\|lang_if_written\(source_language\) \}\}>",
            page,
        ), field


def test_the_forms_table_says_its_language_and_direction() -> None:
    """P2-6: "All forms of …" listed each form in a `span.he` with no `lang`, inside a card
    whose chrome is English."""
    script = (ASSETS / "reader.js").read_text(encoding="utf-8")
    at = script.index('written.className = "he";')
    near = script[at : at + 400]
    assert 'written.setAttribute("lang", language);' in near
    assert 'written.setAttribute("dir", "rtl");' in near


def test_only_another_alphabet_is_foreign_in_a_hebrew_line() -> None:
    """P2-14: a Latin or Cyrillic run with no Hebrew letter is not a word to learn; a
    number, a mark or a Hebrew word with a Latin letter in it still is what it was."""
    foreign = builder._foreign_letters_only
    assert foreign("Yair") and foreign("Lapid") and foreign("Москва")
    assert not foreign("שלום") and not foreign("2008") and not foreign("—")
    assert not foreign("B-שלום")
