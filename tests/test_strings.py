"""The string catalogue: English is the measure, a gap is said in English, and a key's
name never reaches a reader (targum-internal#184)."""

from __future__ import annotations

import json
import string
from pathlib import Path

import pytest

from targum import strings

#: The forms `Intl.PluralRules` can choose, which is what `tn` looks a count's key up by.
PLURAL_FORMS = {"zero", "one", "two", "few", "many", "other"}


def fields(value: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(value) if name}


def test_every_language_says_only_what_english_says_with_the_same_blanks() -> None:
    """A translated key English lacks is dead, and one that drops `{link}` sends a sign-in
    email with no link in it."""
    english = strings.catalogue("en")
    assert english, "the English catalogue is empty or missing from the package"
    for language in strings.languages():
        for key, value in strings.catalogue(language).items():
            base, _, form = key.rpartition(".")
            if form in PLURAL_FORMS and f"{base}.one" in english and f"{base}.other" in english:
                # A count's forms: a language has its own (Russian's few and many), and
                # every one of them says what English's other form says — Russian's one
                # also counts 21 and 31, where English's "yesterday" has no number.
                assert fields(value) <= fields(english[f"{base}.other"]), (
                    f"{language}: {key} changes its blanks"
                )
                continue
            assert key in english, f"{language}.json has {key!r}, which English does not"
            assert fields(value) == fields(english[key]), f"{language}: {key} changes its blanks"
            if not key.startswith("mail."):
                # Pages put these in attributes unescaped, the way they put English.
                assert not set(value) & set('"<>'), (
                    f"{language}: {key} cannot stand in an attribute"
                )


def test_every_catalogue_is_a_flat_map_of_text() -> None:
    for path in Path(strings.__file__).parent.glob("*.json"):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict), path.name
        assert all(isinstance(v, str) and v for v in loaded.values()), path.name


def test_a_gap_is_said_in_english_and_a_missing_key_is_loud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "en.json").write_text(
        json.dumps({"a.greeting": "Hello {name}.", "a.leave": "Goodbye."}), encoding="utf-8"
    )
    (tmp_path / "ru.json").write_text(
        json.dumps({"a.greeting": "Привет, {name}."}), encoding="utf-8"
    )
    monkeypatch.setattr(strings, "_HERE", tmp_path)
    strings.catalogue.cache_clear()
    try:
        assert strings.languages() == ["en", "ru"]
        assert strings.text("a.greeting", "ru", name="Дина") == "Привет, Дина."
        assert strings.text("a.leave", "ru") == "Goodbye.", "a gap is English, not the key"
        assert strings.text("a.leave", "ru-RU") == "Goodbye."
        assert strings.text("a.greeting", "xx", name="Dina") == "Hello Dina."
        assert strings.text("a.greeting", "../en", name="Dina") == "Hello Dina."
        with pytest.raises(KeyError):
            strings.text("a.nobody-wrote-this", "ru")
    finally:
        strings.catalogue.cache_clear()


def _calls(path: Path) -> dict[str, str]:
    """Every `t("key", "English")` and `tn("key", n, "one", "other")` in a script, as
    catalogue keys and their English; a key said twice must say the same thing."""
    import re

    source = path.read_text(encoding="utf-8")
    literal = r'"((?:[^"\\\\]|\\\\.)*)"'
    found: dict[str, str] = {}

    def put(key: str, text: str) -> None:
        # A paragraph of the page keeps its own line breaks, so control characters pass.
        text = json.loads(f'"{text}"', strict=False)
        assert found.setdefault(key, text) == text, f"{key} says two things"

    # `gt` is the reader card's grammar words, which say their English to the chat's ask.
    for match in re.finditer(r'\bg?t\(\s*"([a-z]+\.[\w.-]+)",\s*' + literal, source):
        put(match.group(1), match.group(2))
    for match in re.finditer(
        r'\btn\(\s*"([a-z]+\.[\w.-]+)",\s*[^,]+,\s*' + literal + r",\s*" + literal, source
    ):
        put(match.group(1) + ".one", match.group(2))
        put(match.group(1) + ".other", match.group(3))
    return found


def test_every_sentence_the_reader_says_is_in_the_english_catalogue() -> None:
    """The English stands in `reader.js` and `reader.html.j2` as the fallback and in
    `en.json` as what a translation is made from; this is what keeps them the same text
    (targum-internal#184)."""
    render = Path(strings.__file__).parents[1] / "render"
    calls = _calls(render / "assets" / "reader.js")
    assert len(calls) > 100, "the reader's sentences are said through the catalogue"
    page = _calls(render / "templates" / "reader.html.j2")
    assert len(page) > 100, "and so are the page's own"
    # Every other template that says something through the catalogue: the bar every desk
    # page carries, and the pages converted so far.
    for template in sorted((render / "templates").glob("*.j2")):
        if template.name != "reader.html.j2":
            page.update(_calls(template))
    # And every other script, which says its words through `strings.js`.
    scripts = sorted((render / "assets").glob("*.js"))
    for script in scripts:
        if script.name != "reader.js":
            page.update(_calls(script))
    for name in (
        "library.js",
        "progress.js",
        "charts.js",
        "lang.js",
        "learn.js",
        "you.js",
        "add.js",
        "building.js",
        "account.js",
        "shelf.js",
        "follow.js",
        "bring.js",
        "vocab.js",
        "lists.js",
        "claim.js",
        "yours.js",
        "palette.js",
        "chat.js",
        "speak.js",
        "signin.js",
        "parasha.js",
        "weekly.js",
    ):
        assert _calls(render / "assets" / name), f"{name} says its words through the catalogue"
    for key, text in page.items():
        assert not set(text) & set('"<>'), f"{key} could not stand in an attribute: {text!r}"
    calls.update(page)
    english = strings.catalogue("en")
    for key, text in calls.items():
        assert english.get(key) == text, (
            f"{key}: reader.js says {text!r}, en.json {english.get(key)!r}"
        )


def test_a_desk_script_is_handed_only_its_own_keys_and_english_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.render import builder

    said = {
        "library.column.title": "Текст",
        "library.page.heading": "Библиотека",
        "reader.close": "Закрыть",
        "lang.menu.more": "Ваши языки",
    }
    monkeypatch.setattr(strings, "catalogue", lambda code: said if code == "ru" else {})
    assert builder.script_strings("en", "library.") == {}
    assert builder.script_strings("ru-RU", "library.") == {
        "strings": {"library.column.title": "Текст", "lang.menu.more": "Ваши языки"},
        "language": "ru",
    }
    assert builder.script_strings("fr", "library.") == {}


def test_every_sentence_the_server_says_is_in_the_english_catalogue() -> None:
    """`Handler._say("key", "English")` and `said_in(ui, "key", "English")`: the English
    written at the call is the one in `en.json`, the same promise the scripts make
    (targum-internal#184)."""
    import ast

    from targum.chat import TURN_TOO_LONG
    from targum.serve import NO_KEY

    english = strings.catalogue("en")
    said = 0
    for name in ("serve.py", "chat/session.py", "chat/tools.py"):
        source = Path(strings.__file__).parents[1] / name
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            args = {"_say": node.args[:2], "said_in": node.args[1:3]}.get(str(called))
            if not args or not all(isinstance(arg, ast.Constant) for arg in args):
                continue
            key, text = (arg.value for arg in args)  # type: ignore[attr-defined]
            assert english.get(key) == text, (
                f"{key}: {name} says {text!r}, en.json {english.get(key)!r}"
            )
            said += 1
    assert said > 40, "the server's sentences go through the catalogue"
    # Said through a constant, which the walk above cannot read.
    assert english["job.no-key"] == NO_KEY
    assert english["chat.too-long"] == TURN_TOO_LONG


def test_a_suggestions_reason_is_said_in_the_readers_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The English `because` stays for the model; the reader is told in theirs, and a row
    with no reason keeps what it had (targum-internal#287)."""
    from targum.chat.tools import because_in

    real = strings.catalogue
    said = {
        "suggest.known": "Вы знаете {share}% его слов.",
        "suggest.modern-hebrew": "Современный иврит.",
    }
    monkeypatch.setattr(strings, "catalogue", lambda code: said if code == "ru" else real(code))
    known = {
        "because": "You know 70% of its words.",
        "reason": {"key": "suggest.known", "share": 70},
    }
    assert because_in(known, "ru") == "Вы знаете 70% его слов."
    assert because_in(known, "en") == "You know 70% of its words."
    looked = {"reason": {"key": "suggest.looked-up", "share": 12, "register": "modern"}}
    assert because_in(looked, "en") == "A learner looks up 12% of its words. Modern Hebrew."
    assert because_in({"because": "old"}, "ru") == "old"
