"""A language pressed at the front door is still the language a page later.

The landing page had a switcher and the choice made there was dropped at the next link:
the sign-in page answered in the browser's language, and the phone of an olah who reads
Russian is as often set to Hebrew or English (design.md §12, 2026-09-20). And an account
that has said nothing reads English by default, which the arrival has to be able to tell
from an account that said so.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_landing import get, served  # noqa: F401

from targum.accounts import Store
from targum.render.builder import front_page, signin_page

ADDRESS = "https://targum.example"


def form_of(html: str) -> str:
    """The sign-in form's own tag. The page inlines its script, and the script names the
    attribute it reads, so the attribute is looked for where it would be set."""
    found = re.search(r'<form[^>]*id="ask"[^>]*>', html)
    assert found is not None, "the sign-in form"
    return found.group(0)


def test_the_sign_in_link_carries_a_language_that_was_pressed() -> None:
    assert 'href="/account/signin?lang=ru"' in front_page("ru", ADDRESS, asked="ru")
    # Pressed back to English from a Russian browser: that is a choice too.
    assert 'href="/account/signin?lang=en"' in front_page("en", ADDRESS, asked="en")


def test_a_language_the_browser_merely_suggested_is_not_carried() -> None:
    """Used, and not kept: only a press is a choice."""
    html = front_page("ru", ADDRESS)
    assert 'href="/account/signin"' in html and "signin?lang=" not in html


def test_the_sign_in_page_holds_what_was_pressed_for_its_script() -> None:
    pressed = signin_page(language="ru", asked="ru")
    assert '<html lang="ru"' in pressed
    assert 'data-asked="ru"' in form_of(pressed)
    assert "data-asked" not in form_of(signin_page(language="ru")), "nothing pressed"


def test_the_served_sign_in_page_answers_in_the_language_asked_for(
    served,  # noqa: F811
) -> None:
    port, _store, _posted = served
    status, russian = get(port, "/account/signin?lang=ru")
    assert status == 200
    assert '<html lang="ru"' in russian and 'data-asked="ru"' in form_of(russian)
    status, plain = get(port, "/account/signin")
    assert status == 200 and "data-asked" not in form_of(plain)
    # Not a way to ask for a language there is no catalogue for.
    status, odd = get(port, "/account/signin?lang=zz")
    assert status == 200 and "data-asked" not in form_of(odd)


def test_an_account_that_has_said_nothing_reads_english_and_has_not_said(
    tmp_path: Path,
) -> None:
    store = Store(tmp_path / "words.db")
    person, _ = store.finish_sign_in(store.start_sign_in("new@example.com"))  # type: ignore[misc]
    assert store.reads(person.id) == {"en"}
    assert store.said_reading(person.id) is False
    assert store.said_reading(None) is False


@pytest.mark.parametrize("said", [["en"], ["ru"], ["en", "ru"]])
def test_an_account_that_said_so_has_said_whatever_it_said(tmp_path: Path, said: list[str]) -> None:
    """English because they chose it is an answer; English because nobody asked is not."""
    store = Store(tmp_path / "words.db")
    person, _ = store.finish_sign_in(store.start_sign_in("new@example.com"))  # type: ignore[misc]
    store.choose(person, "reading", said)
    assert store.said_reading(person.id) is True
