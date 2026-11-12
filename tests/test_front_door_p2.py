"""Design's §14 finish bar on the front door, 2026-11-12: the P2s that a page's markup
can show without a browser (targum-internal#477). The ones a browser has to measure are in
`test_front_door_p2_browser.py`.

The wording is ling-en's and ling-ru's (the 2026-11-12 comment on #477).
"""

from __future__ import annotations

import re
from html import unescape

import pytest

from targum.render.builder import (
    _shelf_rows,
    aliyah_page,
    connect_page,
    front_page,
    hebrew_shelf_size,
    shelf_page,
    signin_page,
    text_page,
    weekly_note,
)

ADDRESS = "https://targum.page"


def words(html: str) -> str:
    """What a reader sees: the body, its tags, scripts and styles taken out."""
    body = html.split("<body", 1)[1]
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return unescape(" ".join(body.split()))


# -- P2-7: one figure for the library ---------------------------------------------------


def test_the_hebrew_shelf_is_counted_as_the_library_heads_it() -> None:
    """The figure the landing sells is the one /library's Hebrew heading says."""
    n = hebrew_shelf_size()
    assert n > 0, n
    shelf = words(shelf_page(ADDRESS))
    assert f"Hebrew · {n:,} texts" in shelf, "the Library's Hebrew heading says another number"


def test_the_landing_aliyah_and_connect_sell_one_exact_figure_in_english() -> None:
    n = f"{hebrew_shelf_size():,}"
    landing = words(front_page("en", ADDRESS))
    assert f"{n} free Hebrew texts and videos" in landing
    assert f"{n} Hebrew texts and videos to learn from, all free." in landing
    assert f"{n} free Hebrew texts and videos" in words(aliyah_page("en", ADDRESS))
    assert (
        f"{n} Hebrew texts and videos, sorted by the words you know. Or paste a link to your own."
    ) in words(connect_page("en", ADDRESS))
    for page in (landing, words(connect_page("en", ADDRESS)), words(aliyah_page("en", ADDRESS))):
        assert "Hundreds of" not in page and "More than 700" not in page


def test_the_figure_is_grouped_and_declined_in_russian() -> None:
    from targum.strings import plural_form

    n = hebrew_shelf_size()
    grouped = f"{n:,}".replace(",", " ")
    form = plural_form(n, "ru")
    texts = {"one": "текст", "few": "текста", "many": "текстов", "other": "текста"}[form]
    landing = words(front_page("ru", ADDRESS))
    assert f"{grouped} {texts} и видео на иврите для учёбы, и всё бесплатно." in landing
    assert grouped in words(aliyah_page("ru", ADDRESS))
    assert f"{grouped} {texts} и видео на иврите" in words(connect_page("ru", ADDRESS))
    assert "Больше 700" not in landing and "Сотни" not in landing


# -- P2-11: /connect's demo says whose percentage it is ---------------------------------


@pytest.mark.parametrize(
    ("language", "said", "not_said"),
    [
        ("en", "this learner knows 91% of the words", "You know 91%"),
        ("ru", "этот ученик знает 91% слов", "Вы знаете 91%"),
    ],
)
def test_connect_s_demo_says_the_learner_knows(language: str, said: str, not_said: str) -> None:
    """§12, 2026-11-03: a percentage on a front door is somebody's."""
    page = words(connect_page(language, ADDRESS))
    assert said in page
    assert not_said not in page


# -- P2-10: no English gloss where the title is already the page's language -------------


def test_a_title_in_the_page_s_language_draws_no_gloss_under_it() -> None:
    from targum.catalogue import Entry

    russian = Entry(
        id="v-kafe",
        title="В кафе",
        author="",
        language="ru",
        source="scene:v-kafe",
        blurb="Two friends order coffee.",
        words=100,
        english="In a café",
    )
    hebrew = Entry(
        id="be-beit-kafe",
        title="בבית קפה",
        author="",
        language="he",
        source="scene:be-beit-kafe",
        blurb="Two friends order coffee.",
        words=100,
        english="In a café",
    )
    assert _shelf_rows([russian], "ru")[0].named == ""
    assert _shelf_rows([russian], "en")[0].named == "In a café"
    assert _shelf_rows([hebrew], "ru")[0].named == "In a café"


NOTE = "A linear translation, made to be read beside the Hebrew."


def a_noted_row(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """A Torah book whose only translation carries an English note, its sample's
    Russian ours, so a Russian page credits the English it was made from."""
    from dataclasses import replace

    from targum import catalogue
    from targum.catalogue import CATALOGUE, Line, Rendering

    entry = replace(
        CATALOGUE[0],
        id="a-noted-book",
        translations=[
            Rendering(
                name="The Metsudah test Chumash",
                source="sefaria:en:Genesis",
                publisher="Metsudah Publications",
                licence="CC-BY",
                note=NOTE,
            )
        ],
    )
    lines = [
        Line(
            source="בְּרֵאשִׁית בָּרָא אֱלֹהִים",
            target="In the beginning Elohim created",
            said={"ru": "В начале сотворил Бог"},
        )
    ]
    monkeypatch.setattr(catalogue, "sample_for", lambda entry_id: lines)
    return entry


def test_a_translation_note_is_said_only_on_a_page_in_its_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = a_noted_row(monkeypatch)
    russian = words(text_page(entry, ADDRESS, language="ru"))
    assert "Metsudah Publications" in russian, "the credit still names the work"
    assert NOTE not in russian
    assert NOTE in words(text_page(entry, ADDRESS, language="en"))


# -- P2-13: sign-in wears the public head -----------------------------------------------


@pytest.mark.parametrize("language", ["en", "ru"])
def test_sign_in_carries_a_description_and_the_link_picture(language: str) -> None:
    from targum.strings import text

    page = signin_page(language=language, address=ADDRESS)
    head = page.split("</head>", 1)[0]
    described = re.search(r'<meta name="description" content="([^"]+)"', head)
    assert described and unescape(described.group(1)) == text("landing.head.description", language)
    assert f'<meta property="og:image" content="{ADDRESS}/' in head
    assert f'<link rel="canonical" href="{ADDRESS}/account/signin">' in head
    assert head.count("<title>") == 1 and "<title>targum</title>" in head


def test_an_expired_link_keeps_the_desk_s_head() -> None:
    page = signin_page(expired=True)
    head = page.split("</head>", 1)[0]
    assert "viewport-fit=cover" in head
    assert "og:image" not in head


# -- P2-14: a note does not ask somebody who just joined to join ------------------------


def test_a_note_page_s_foot_does_not_ask_to_join(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    note = weekly_note(
        "We've sent you a link. Open it to confirm your place on the list.",
        address=ADDRESS,
        heading="Check your email",
        home="/",
        title="targum",
    )
    assert 'class="sf-join"' not in note
    assert 'class="sf-signin"' in note, "Sign in stays"
    assert 'class="sf-join"' in shelf_page(ADDRESS), "the other public pages still ask"
