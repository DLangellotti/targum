"""The string catalogue: English is the measure, a gap is said in English, and a key's
name never reaches a reader (targum-internal#184)."""

from __future__ import annotations

import json
import string
from pathlib import Path

import pytest

from targum import strings


def fields(value: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(value) if name}


def test_every_language_says_only_what_english_says_with_the_same_blanks() -> None:
    """A translated key English lacks is dead, and one that drops `{link}` sends a sign-in
    email with no link in it."""
    english = strings.catalogue("en")
    assert english, "the English catalogue is empty or missing from the package"
    for language in strings.languages():
        for key, value in strings.catalogue(language).items():
            assert key in english, f"{language}.json has {key!r}, which English does not"
            assert fields(value) == fields(english[key]), f"{language}: {key} changes its blanks"


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
        text = json.loads(f'"{text}"')
        assert found.setdefault(key, text) == text, f"{key} says two things"

    for match in re.finditer(r'\bt\(\s*"(reader\.[\w.-]+)",\s*' + literal, source):
        put(match.group(1), match.group(2))
    for match in re.finditer(
        r'\btn\(\s*"(reader\.[\w.-]+)",\s*[^,]+,\s*' + literal + r",\s*" + literal, source
    ):
        put(match.group(1) + ".one", match.group(2))
        put(match.group(1) + ".other", match.group(3))
    return found


def test_every_sentence_the_reader_says_is_in_the_english_catalogue() -> None:
    """The English stands in `reader.js` as the fallback and in `en.json` as what a
    translation is made from; this is what keeps them the same text (targum-internal#184)."""
    script = Path(strings.__file__).parents[1] / "render" / "assets" / "reader.js"
    calls = _calls(script)
    assert len(calls) > 100, "the reader's sentences are said through the catalogue"
    english = strings.catalogue("en")
    for key, text in calls.items():
        assert english.get(key) == text, (
            f"{key}: reader.js says {text!r}, en.json {english.get(key)!r}"
        )
