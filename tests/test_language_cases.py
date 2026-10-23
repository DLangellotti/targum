"""A language's name inside a Russian sentence takes its case: «На иврите пока ничего
нет», not «На языке «Иврит» пока ничего нет» (targum-internal#524). English is untouched."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from targum import strings
from targum.serve import said_in

STRINGS_JS = Path(strings.__file__).parents[1] / "render" / "assets" / "strings.js"


def test_a_russian_sentence_says_the_name_in_its_case() -> None:
    assert (
        said_in("ru", "shelf.empty.language", "Nothing in {language} yet.", language="Иврит")
        == "На иврите пока ничего нет."
    )
    assert (
        said_in(
            "ru",
            "door.unreadable.language",
            "This looks like {language}, and we can't read that yet.",
            language="Latin",
        )
        == "Похоже, это латынь, а такие тексты мы пока не читаем."
    )
    # Russian has no adverb for Hebrew, so the prepositional form stands in for one.
    assert strings.case_form("Иврит", "adv", "ru") == "на иврите"
    assert strings.case_form("French", "adv", "ru") == "по-французски"


def test_english_says_what_it_always_said() -> None:
    assert (
        said_in("en", "shelf.empty.language", "Nothing in {language} yet.", language="Hebrew")
        == "Nothing in Hebrew yet."
    )
    english = strings.catalogue("en")
    assert not [key for key, value in english.items() if strings.CASED.search(value)], (
        "English names a language as it is filled"
    )


def test_a_name_with_no_forms_is_quoted_as_before() -> None:
    assert strings.case_form("Swahili", "in", "ru") == "на языке «Swahili»"
    assert strings.case_form("Swahili", "nom", "ru") == "язык «Swahili»"
    assert strings.case_form("Swahili", "In", "ru") == "На языке «Swahili»"


def test_every_language_targum_names_has_its_forms_in_russian() -> None:
    russian = strings.catalogue("ru")
    codes = [key.split(".", 1)[1] for key in russian if re.fullmatch(r"language\.\w+", key)]
    assert codes
    for code in codes:
        assert russian.get(f"language-in.{code}", "").startswith("на "), code
        assert russian.get(f"language-nom.{code}", "").islower(), code


def test_no_russian_sentence_still_quotes_a_language_name() -> None:
    quoted = re.compile(r"(?:на языке|язык) «\{language\}»")
    left = [
        key
        for key, value in strings.catalogue("ru").items()
        if quoted.search(value) and not key.endswith(".any")
    ]
    assert not left, f"still quoting the menu name: {left}"


def test_a_page_escapes_a_name_it_quotes() -> None:
    from targum.render.builder import page_words

    said = page_words("ru")(
        "subscribe.page.a-channel", "A YouTube channel in {language}.", language="<b>x</b>"
    )
    assert str(said) == "YouTube-канал на языке «&lt;b&gt;x&lt;/b&gt;»."


def test_a_russian_page_carries_the_forms_and_an_english_one_nothing() -> None:
    from targum.render.builder import library_page

    html = library_page("k", language="ru")
    at = re.search(r"window\.TARGUM_STRINGS\s*=\s*", html)
    assert at
    given = json.JSONDecoder().raw_decode(html, at.end())[0]
    assert given["strings"]["language-in.he"] == "на иврите"
    assert given["names"]["Иврит"] == "he"
    assert given["names"]["Hebrew"] == "he"
    assert not re.search(r"window\.TARGUM_STRINGS\s*=", library_page("k", language="en"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_scripts_say_the_name_in_its_case() -> None:
    russian = strings.catalogue("ru")
    given = {
        "language": "ru",
        "strings": {
            **{key: value for key, value in russian.items() if key.startswith("language-")},
            "shelf.empty.language": russian["shelf.empty.language"],
            "chat.ask-about-the-text": russian["chat.ask-about-the-text"],
            "add.words.many": russian["add.words.many"],
        },
        "names": strings.language_codes("ru"),
    }
    script = (
        "var window = {TARGUM_STRINGS: "
        + json.dumps(given)
        + "};\n"
        + STRINGS_JS.read_text(encoding="utf-8")
        + "\nvar s = window.TargumStrings;\n"
        "console.log(JSON.stringify(["
        's.t("shelf.empty.language", "Nothing in {language} yet.", {language: "Иврит"}),'
        's.t("chat.ask-about-the-text", "Ask, or write in {language}", {language: "Russian"}),'
        's.tn("add.words", 5, "a", "b", {language: "Идиш"}),'
        's.t("shelf.empty.language", "Nothing in {language} yet.", {language: "Klingon"})'
        "]));"
    )
    out = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60, check=True
    ).stdout
    assert json.loads(out) == [
        "На иврите пока ничего нет.",
        "Спросите о тексте или напишите по-русски",
        "Это 5 слов на идише.",
        "На языке «Klingon» пока ничего нет.",
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_an_english_page_fills_names_as_it_always_did() -> None:
    script = (
        "var window = {};\n"
        + STRINGS_JS.read_text(encoding="utf-8")
        + '\nconsole.log(window.TargumStrings.t("shelf.empty.language", '
        '"Nothing in {language} yet.", {language: "Hebrew"}));'
    )
    out = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60, check=True
    ).stdout
    assert out.strip() == "Nothing in Hebrew yet."
