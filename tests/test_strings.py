"""The string catalogue: English is the measure, a gap is said in English, and a key's
name never reaches a reader (targum-internal#184)."""

from __future__ import annotations

import json
import re
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


def test_a_translation_is_not_left_behind_when_its_english_changes() -> None:
    """targum-internal#337. `text()` says a key in English only where a language has not
    filled it; a key it *has* filled is said in that language whatever the English has
    since become. So an English sentence that changed while its Russian stayed was served
    stale, and nothing said so — found while changing sixty strings that assumed a reader
    was there to read.

    `strings/from/<code>.json` records, for every translated key, a fingerprint of the
    English it was made from. When the English moves, this fails until somebody has
    looked at the translation and stamped it again.
    """
    import hashlib

    here = Path(strings.__file__).resolve().parent
    english = json.loads((here / "en.json").read_text(encoding="utf-8"))
    for code in strings.languages():
        if code == strings.SOURCE:
            continue
        said = json.loads((here / f"{code}.json").read_text(encoding="utf-8"))
        stamps_file = here / "from" / f"{code}.json"
        assert stamps_file.is_file(), f"{code}: run scripts/stamp_strings.py"
        stamps = json.loads(stamps_file.read_text(encoding="utf-8"))
        stale = []
        for key in said:
            source = key if key in english else key.rsplit(".", 1)[0] + ".other"
            if source not in english:
                continue
            now = hashlib.sha256(english[source].encode("utf-8")).hexdigest()[:10]
            if stamps.get(key) != now:
                stale.append(key)
        assert not stale, (
            f"{code}: the English of {len(stale)} translated keys has changed since they were "
            f"translated ({', '.join(stale[:5])}…). Bring the translation up to date, then run "
            "`uv run python scripts/stamp_strings.py`."
        )


# -- a refusal in the reader's language (targum-internal#348) -------------------------


def test_a_refusal_with_a_key_is_said_in_the_readers_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `TargumError` is raised where the trouble is — the fetch door, an ingester, a
    video host — and none of those know who is reading. So it travels in English with a
    key, and the language is chosen where it reaches a reader."""
    from targum.errors import TargumError
    from targum.serve import refused_in

    (tmp_path / "en.json").write_text(
        json.dumps(
            {
                "fetch.private-network": "{host} is on a private network.",
                "fetch.private-network.hint": "Paste a public address.",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "ru.json").write_text(
        json.dumps(
            {
                "fetch.private-network": "{host} — частная сеть.",
                "fetch.private-network.hint": "Вставьте публичный адрес.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(strings, "_HERE", tmp_path)
    strings.catalogue.cache_clear()
    try:
        refusal = TargumError(
            "10.0.0.1 is on a private network.",
            "Paste a public address.",
            key="fetch.private-network",
            host="10.0.0.1",
        )
        assert refused_in("ru", refusal) == "10.0.0.1 — частная сеть. Вставьте публичный адрес."
        assert (
            refused_in("en", refusal) == "10.0.0.1 is on a private network. Paste a public address."
        )
    finally:
        strings.catalogue.cache_clear()


def test_a_refusal_with_no_key_is_said_as_it_always_was() -> None:
    """Most refusals have none, and every one only an operator meets. The command line
    is English by design."""
    from targum.errors import TargumError
    from targum.serve import refused_in

    plain = TargumError("We couldn't open that PDF.", "Try another file.")
    assert refused_in("ru", plain) == "We couldn't open that PDF. Try another file."
    assert refused_in("ru", TargumError("No hint here.")) == "No hint here."


def test_the_english_is_never_formatted_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The English is interpolated already — it was an f-string where the trouble was.
    Formatting it a second time takes the whole refusal down on an address with a brace
    in it, which is a legal thing for a URL to contain."""
    from targum.errors import TargumError
    from targum.serve import refused_in

    (tmp_path / "en.json").write_text(json.dumps({"a.key": "x"}), encoding="utf-8")
    monkeypatch.setattr(strings, "_HERE", tmp_path)
    strings.catalogue.cache_clear()
    try:
        awkward = "https://example.com/a{b}c"
        refusal = TargumError(
            f"We only read web pages, and {awkward} isn't one.",
            key="fetch.not-a-web-page",
            url=awkward,
        )
        assert awkward in refused_in("ru", refusal), "no catalogue entry, so the English stands"
    finally:
        strings.catalogue.cache_clear()


def test_a_translation_whose_blanks_do_not_match_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A translated sentence naming something the refusal does not carry would raise on
    formatting. The English still says the true thing, which is what matters."""
    from targum.errors import TargumError
    from targum.serve import refused_in

    (tmp_path / "en.json").write_text(json.dumps({"a.key": "x"}), encoding="utf-8")
    (tmp_path / "ru.json").write_text(
        json.dumps({"fetch.no-such-site": "Не нашли {site}."}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(strings, "_HERE", tmp_path)
    strings.catalogue.cache_clear()
    try:
        refusal = TargumError("We couldn't find x.com.", key="fetch.no-such-site", host="x.com")
        assert refused_in("ru", refusal) == "We couldn't find x.com."
    finally:
        strings.catalogue.cache_clear()


def test_every_refusal_that_names_a_key_has_one_in_the_catalogue() -> None:
    """A `TargumError` with a key nothing answers is a refusal that silently stays
    English — which is the bug this whole mechanism exists to fix, reintroduced
    (targum-internal#348).

    Asked of the tree rather than of a list, so the 104 refusals still to be converted
    are covered the day each one is.
    """
    english = strings.catalogue("en")
    here = Path(strings.__file__).resolve().parent.parent
    missing = []
    for path in sorted(here.rglob("*.py")):
        for key in re.findall(r'key="([a-z0-9.\-]+)"', path.read_text(encoding="utf-8")):
            if key not in english:
                missing.append(f"{path.relative_to(here)}: {key}")
    assert not missing, "keys with nothing to say them:\n  " + "\n  ".join(missing)


def test_every_refusal_that_names_a_key_is_answered_in_every_language() -> None:
    """A key is what makes a refusal reader-facing: the ones only an operator meets carry
    none, and are said in English for ever by design. So a refusal that has earned a key
    and has no translation is half-converted — it reaches a Russian reader on a page that
    is otherwise entirely in Russian, and says nothing in Russian.

    That state was invisible and real. On 2026-09-22 all 31 keyed refusals were in
    `en.json` and none was in `ru.json`, with this file green: the mechanism test proves
    the machinery on a fixture catalogue of its own, so it cannot see that the real one is
    empty. This asks the real catalogue.

    Asked of the tree rather than of a list, so the refusals still to be converted are
    covered the day each one is — and converting one now means translating it, which is
    the whole of what a key promises.
    """
    here = Path(strings.__file__).resolve().parent.parent
    keyed = {
        key
        for path in sorted(here.rglob("*.py"))
        for key in re.findall(r'key="([a-z0-9.\-]+)"', path.read_text(encoding="utf-8"))
    }
    english = strings.catalogue("en")
    wanted = sorted(key for key in keyed | {f"{key}.hint" for key in keyed} if key in english)
    for code in strings.languages():
        if code == strings.SOURCE:
            continue
        said = strings.catalogue(code)
        silent = [key for key in wanted if key not in said]
        assert not silent, (
            f"{code}: {len(silent)} keyed refusals fall back to English "
            f"({', '.join(silent[:5])}…). A refusal with a key is one a reader meets."
        )


def test_a_refusals_hint_is_said_where_it_has_one() -> None:
    """The hint rides at `<key>.hint` by convention. A key whose English carries a hint
    and whose catalogue does not would say the sentence and drop the way out of it."""
    english = strings.catalogue("en")
    here = Path(strings.__file__).resolve().parent.parent
    for path in sorted(here.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"TargumError\(\s*\n?\s*(.{0,400}?)\)\s*(?:from|\n)", text, re.S):
            body = match.group(1)
            key = re.search(r'key="([a-z0-9.\-]+)"', body)
            if not key:
                continue
            # Two strings before the key means a message and a hint.
            strings_in = re.findall(r'"[^"]*"|f"[^"]*"', body.split("key=")[0])
            if len(strings_in) >= 2:
                assert f"{key.group(1)}.hint" in english, (
                    f"{path.name}: {key.group(1)} has a hint and the catalogue has no "
                    f"{key.group(1)}.hint"
                )


def test_a_host_that_would_not_answer_can_be_said_in_the_readers_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Unreachable` dropped `key` and `fill` on the floor, so the commonest refusal the
    fetch door raises — a 4xx, a bot check, a timeout, too many redirects — was the one
    the mechanism could not reach (targum-internal#348)."""
    from targum.errors import Unreachable
    from targum.serve import refused_in

    (tmp_path / "en.json").write_text(
        json.dumps({"fetch.would-not-open": "We couldn't open {url}."}), encoding="utf-8"
    )
    (tmp_path / "ru.json").write_text(
        json.dumps({"fetch.would-not-open": "Не удалось открыть {url}."}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(strings, "_HERE", tmp_path)
    strings.catalogue.cache_clear()
    try:
        shut = Unreachable(
            "We couldn't open https://x.test/a.",
            "HTTP 403",
            status=403,
            host="x.test",
            key="fetch.would-not-open",
            url="https://x.test/a",
        )
        # What Unreachable is for is untouched: the status and the host still travel.
        assert shut.status == 403 and shut.host == "x.test"
        assert refused_in("ru", shut) == "Не удалось открыть https://x.test/a. HTTP 403"
    finally:
        strings.catalogue.cache_clear()


def test_a_keyword_with_no_key_behind_it_is_a_mistake() -> None:
    """Taking `**fill` is what stopped the signature catching a mistyped `hint`, and
    mypy cannot catch it either. `fill` is only ever read against a key, so a keyword
    with no key is certainly a mistake and is refused outright."""
    from targum.errors import TargumError, Unreachable

    with pytest.raises(TypeError, match="hnt"):
        TargumError("We couldn't open it.", hnt="try again")
    with pytest.raises(TypeError, match="url"):
        Unreachable("We couldn't open it.", url="https://x.test")

    # And the legitimate shapes still stand.
    assert TargumError("plain").fill == {}
    assert TargumError("named", key="a.key", url="u").fill == {"url": "u"}


def test_the_sign_in_refusal_really_interpolates_in_russian() -> None:
    """targum-internal#252's sign-in wall, against the **real** catalogue rather than a
    fixture one.

    Every other refusal test here writes its own `en.json`/`ru.json` into `tmp_path`,
    which proves the machinery and cannot prove the shipped sentences. This one has to
    ask the real catalogue, because the bug it guards is invisible to a fixture: the
    blanks are filled from `error.fill`, and `Unreachable` eats `host`, `status`,
    `challenge` and `via` as fields of its own. A translation naming `{host}` would raise
    `KeyError` inside `say()`, get caught, and **fall back to English without a word** —
    a Russian reader would simply never see Russian, and nothing would fail.
    """
    from targum.errors import Unreachable
    from targum.serve import refused_in

    wall = Unreachable(
        "paywall.example asks you to sign in, so we can't open it.",
        "Open it yourself and paste the text into the box instead.",
        status=401,
        host="paywall.example",
        key="fetch.needs-a-sign-in",
        site="paywall.example",
    )
    said = refused_in("ru", wall)
    assert "paywall.example" in said, "the site is named, so the blank was really filled"
    assert "{" not in said, "and no blank was left standing in the page"
    assert said != refused_in("en", wall), "a Russian reader is not handed the English"
    assert "войти" in said
