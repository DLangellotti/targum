"""A text the reader brought, rewritten at their level (targum-internal#535).

What has to hold: the level is at or under the reader's rung; nothing is asked of a model
until the reader presses, and the press goes through `Library.press`; a library text and
a licence that forbids derivatives are refused; and the rewrite is a new text of the
reader's, built by the ordinary build and linked to its original both ways.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import test_correct

from targum import level, rewrite
from targum.models import Document
from targum.weekly.models import Level as Written

# #533's text, its server and its client: a rewrite is offered on the same texts.
made = test_correct.made
ask = test_correct.ask
serving = test_correct.serving

# -- the level --------------------------------------------------------------------------


def rung(name: str) -> level.Rung:
    return next(one for one in (*level.ULPAN, *level.CEFR) if one.name == name)


@pytest.mark.parametrize(
    ("name", "written"),
    [
        ("aleph", Written.aleph),
        ("aleph plus", Written.aleph),
        ("bet", Written.aleph),
        ("bet plus", Written.bet),
        ("gimel", Written.bet),
        ("vav", Written.bet),
        ("A2", Written.aleph),
        ("B1", Written.bet),
        ("C2", Written.bet),
    ],
)
def test_a_rewrite_is_written_at_or_under_the_reader(name: str, written: Written) -> None:
    assert rewrite.for_rung(rung(name)) is written


def test_nothing_known_is_easy_and_a_named_rung_counts_until_words_do() -> None:
    assert rewrite.for_reader(level.EMPTY) is Written.aleph
    said = level.Level("he", 0, 0, 0.0, None, level.ULPAN[0], 0, 0, 0, 0, 0, declared="gimel")
    assert rewrite.for_reader(said) is Written.bet


def test_only_easy_and_simplified_are_offered() -> None:
    assert rewrite.named("aleph") is Written.aleph
    assert rewrite.named("bet") is Written.bet
    assert rewrite.named("gimel") is None, "Native is not simplified"
    assert rewrite.named("../x") is None


# -- licences ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("licence", "refused"),
    [("", False), ("CC BY-SA 4.0", False), ("CC BY-NC 4.0", False), ("CC BY-ND 4.0", True)],
)
def test_only_no_derivatives_refuses(licence: str, refused: bool) -> None:
    assert bool(rewrite.refused(licence)) is refused


def test_a_recordings_licence_is_read_from_its_manifest(tmp_path: Path) -> None:
    folder = tmp_path / "talk-he"
    made(folder)
    assert rewrite.licence_of(folder) == ""
    (folder / "audio.json").write_text(json.dumps({"licence": "CC BY-ND 4.0"}), encoding="utf-8")
    assert rewrite.licence_of(folder) == "CC BY-ND 4.0"


# -- the prompt and the answer ----------------------------------------------------------


def test_the_prompt_asks_for_the_levels_words_and_sentences() -> None:
    asked = rewrite.prompt("he", Written.aleph, "טקסט", title="כותרת")
    assert "1,000 commonest words" in asked and "4 to 10 words" in asked
    assert "without niqqud" in asked and "never translate" in asked
    assert "<title>כותרת</title>" in asked
    more = rewrite.prompt("fr", Written.bet, "texte")
    assert "3,000" in more and "<title>" not in more and "niqqud" not in more


def test_long_texts_go_in_several_requests_and_keep_their_paragraphs() -> None:
    paragraphs = ["מילה " * 700, "מילה " * 700, "קצר"]
    assert len(rewrite.chunks(paragraphs)) == 2


def document(paragraphs: list[str], title: str = "סיפור") -> Document:
    from targum.models import Block, BlockKind

    blocks = [Block(id="b0", kind=BlockKind.heading, level=1, text=title)] + [
        Block(id=f"b{n + 1}", text=one) for n, one in enumerate(paragraphs)
    ]
    return Document(source="https://example.com/x", title=title, language="he", blocks=blocks)


def test_the_answer_gives_a_title_and_paragraphs_and_counts_what_it_cost() -> None:
    asked: list[str] = []

    def model(prompt: str) -> tuple[str, int, int]:
        asked.append(prompt)
        return "# סיפור קל\n\nפסקה אחת.\n\nפסקה שתיים.", 1000, 500

    done = rewrite.Rewriter(ask=model).rewrite(document(["משפט קשה.", "עוד משפט."]), Written.aleph)

    assert done.title == "סיפור קל"
    assert done.paragraphs == ["פסקה אחת.", "פסקה שתיים."]
    assert "<title>סיפור</title>" in asked[0] and "סיפור\n\nמשפט" not in asked[0], (
        "the heading that repeats the title is asked as the title, not as text"
    )
    assert done.spent.cost() > 0
    file = done.file("he")
    assert file.startswith('---\ntitle: "סיפור קל"\nlanguage: he\n---\n\n')


def test_an_empty_answer_is_not_a_rewrite() -> None:
    from targum.errors import TargumError

    with pytest.raises(TargumError):
        rewrite.Rewriter(ask=lambda prompt: ("", 10, 0)).rewrite(document(["משפט."]), Written.aleph)


def test_the_estimate_grows_with_the_text() -> None:
    rewriter = rewrite.Rewriter()
    assert 0 < rewriter.estimate(100) < rewriter.estimate(5000)


# -- the pair ---------------------------------------------------------------------------


def test_a_rewrite_and_its_original_point_at_each_other(tmp_path: Path) -> None:
    original = tmp_path / "story-he"
    original.mkdir()
    assert rewrite.stem(original, Written.aleph) == "story-he-aleph"
    first = tmp_path / "story-he-aleph"
    first.mkdir()
    rewrite.link(first, original, Written.aleph)
    assert rewrite.stem(original, Written.aleph) == "story-he-aleph-2", "never written over"
    second = tmp_path / "story-he-bet"
    second.mkdir()
    rewrite.link(second, original, Written.bet)
    rewrite.link(second, original, Written.bet)

    assert rewrite.made_from(first) == {"name": "story-he", "level": "aleph"}
    assert rewrite.made_from(original) is None
    assert rewrite.made_of(original) == [
        {"name": "story-he-aleph", "level": "aleph"},
        {"name": "story-he-bet", "level": "bet"},
    ]


# -- the press --------------------------------------------------------------------------


@pytest.fixture
def priced(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.translate import anthropic_provider

    monkeypatch.setattr(anthropic_provider.AnthropicProvider, "available", lambda self: (True, ""))
    monkeypatch.setattr(
        anthropic_provider.AnthropicProvider,
        "estimate",
        lambda self, segments, source, target, style: 0.01 * len(segments),
    )
    monkeypatch.setattr(rewrite.Rewriter, "available", lambda self: (True, ""))


def test_the_page_is_offered_a_level_for_the_readers_own_text(serving: tuple[int, Any]) -> None:
    port, library = serving
    made(library.home(None) / "story-he")

    status, asked = ask(port, "/text/edit?name=story-he")

    assert status == 200
    offer = asked["rewrite"]
    assert offer["offered"] is True and offer["level"] == "aleph"
    assert [one["id"] for one in offer["levels"]] == ["aleph", "bet"]
    assert offer["levels"][0]["label"] == "Easy · 1,000 words"
    assert offer["from"] is None and offer["made"] == []


def test_a_library_text_is_never_rewritten(serving: tuple[int, Any], priced: None) -> None:
    port, library = serving
    made(library.home(None) / "genesis-he", source="sefaria:Genesis")

    assert ask(port, "/text/edit?name=genesis-he")[1] == {"editable": False}
    assert ask(port, "/text/rewrite", {"name": "genesis-he"})[0] == 404


def test_rewriting_is_a_press_through_the_rails(
    serving: tuple[int, Any], priced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, library = serving
    home = library.home(None)
    made(home / "story-he")

    def forbidden(*_: object) -> tuple[str, int, int]:
        raise AssertionError("nothing is asked of a model before the press is worked")

    monkeypatch.setattr(rewrite.Rewriter, "_request", forbidden)
    pressed: list[Any] = []
    monkeypatch.setattr(library, "press", lambda job: pressed.append(job) or "")

    status, answer = ask(port, "/text/rewrite", {"name": "story-he", "level": "bet", "to": "en"})

    assert status == 200 and len(pressed) == 1, "one press, claimed by `Library.press`"
    job = pressed[0]
    assert answer["id"] == job.id and job.stage == "ready"
    assert job.options["rewrite"] == {"from": "story-he", "level": "bet"}
    assert job.options["from"] == "he" and job.options["to"] == "en"
    source = Path(job.source)
    assert source.parent.parent == home / "uploads" and source.name == "story-he-bet.txt"
    assert not source.exists(), "written only once the press is worked"
    translating = 0.01 * 4 * rewrite.LONGER
    assert job.estimate > translating, "the rewriting and the build are on one receipt"


def test_a_press_refused_by_the_rails_says_so(
    serving: tuple[int, Any], priced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, library = serving
    made(library.home(None) / "story-he")
    monkeypatch.setattr(library, "max_cost", 0.000001)

    status, answer = ask(port, "/text/rewrite", {"name": "story-he"})

    assert status == 402 and answer["stage"] == "blocked"


def test_a_licence_that_forbids_derivatives_is_said_plainly(
    serving: tuple[int, Any], priced: None
) -> None:
    port, library = serving
    folder = library.home(None) / "talk-he"
    made(folder)
    (folder / "audio.json").write_text(json.dumps({"licence": "CC BY-ND 4.0"}), encoding="utf-8")

    assert ask(port, "/text/edit?name=talk-he")[1]["rewrite"]["offered"] is False
    status, answer = ask(port, "/text/rewrite", {"name": "talk-he"})

    assert status == 400
    assert answer["error"] == (
        "This text's licence doesn't allow changing it, so we can't rewrite it."
    )


def test_a_text_too_long_is_refused(
    serving: tuple[int, Any], priced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, library = serving
    made(library.home(None) / "story-he")
    monkeypatch.setattr(rewrite, "LONGEST", 3)

    status, answer = ask(port, "/text/rewrite", {"name": "story-he"})

    assert status == 400 and "up to 3 words" in answer["error"]


def test_the_pressed_job_rewrites_then_builds_then_links(
    tmp_path: Path, priced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from targum.serve import Library
    from targum.usage import Usage

    library = Library(tmp_path / "out")
    home = library.home(None)
    original = home / "story-he"
    made(original)
    job = library.quote_rewrite(
        original, Written.aleph, owner=None, admin=False, home=home, target="en"
    )
    assert job.stage == "ready"

    monkeypatch.setattr(
        rewrite.Rewriter,
        "_request",
        lambda self, prompt: ("סיפור קל\n\nשלום.\n\nזה הסוף.", 1000, 400),
    )
    built: list[str] = []

    class Built:
        notify: Any = None

        def run(self, on_progress: Any, on_ready: Any, chapters: Any) -> Any:
            built.append(Path(job.source).read_text(encoding="utf-8"))
            out = home / "story-he-aleph"
            (out / "reader").mkdir(parents=True)
            spent = Usage()
            spent.add("claude-sonnet-5", 100, 100)
            result = SimpleNamespace(out_dir=out, spent=spent)
            on_ready(result)
            return result

    monkeypatch.setattr(library, "_builder", lambda job: Built())
    monkeypatch.setattr(library, "propose", lambda job: None)

    library.run(job)

    assert job.stage == "done" and job.reader == "story-he-aleph/reader/index.html"
    assert built and built[0].startswith('---\ntitle: "סיפור קל"\nlanguage: he\n---')
    assert "שלום.\n\nזה הסוף." in built[0]
    assert job.title == "סיפור קל" and job.options["rewritten"] is True
    assert job.reading > 0 and job.spent > job.reading, "both halves on the receipt"
    assert rewrite.made_from(home / "story-he-aleph") == {"name": "story-he", "level": "aleph"}
    assert rewrite.made_of(original) == [{"name": "story-he-aleph", "level": "aleph"}]
    assert not (original / "rewrite.json").exists(), "the original is never touched"


def test_a_failed_rewrite_builds_nothing(
    tmp_path: Path, priced: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.serve import Library

    library = Library(tmp_path / "out")
    home = library.home(None)
    made(home / "story-he")
    job = library.quote_rewrite(
        home / "story-he", Written.aleph, owner=None, admin=False, home=home
    )
    monkeypatch.setattr(rewrite.Rewriter, "_request", lambda self, prompt: ("", 10, 0))

    def forbidden(job: Any) -> Any:
        raise AssertionError("nothing to build")

    monkeypatch.setattr(library, "_builder", forbidden)
    library.run(job)

    assert job.stage == "failed" and "couldn't rewrite" in job.error
    assert not Path(job.source).exists()


def test_the_rewrite_and_its_original_are_linked_on_the_page(serving: tuple[int, Any]) -> None:
    port, library = serving
    home = library.home(None)
    made(home / "story-he")
    made(home / "story-he-aleph", source=str(home / "uploads" / "x" / "story-he-aleph.txt"))
    rewrite.link(home / "story-he-aleph", home / "story-he", Written.aleph)

    rewritten = ask(port, "/text/edit?name=story-he-aleph")[1]["rewrite"]
    original = ask(port, "/text/edit?name=story-he")[1]["rewrite"]

    assert rewritten["from"] == {
        "reader": "/reader/story-he/reader/index.html",
        "title": "A story",
        "level": "Easy · 1,000 words",
    }
    assert original["made"][0]["reader"] == "/reader/story-he-aleph/reader/index.html"


# -- the chat and the connector ---------------------------------------------------------


def test_the_chat_offers_a_link_and_never_a_press(tmp_path: Path, monkeypatch) -> None:
    from test_chat_tools import context, signed_in

    from targum.accounts import Store
    from targum.chat import tools
    from targum.serve import Library

    store = Store(tmp_path / "words.db")
    library = Library(tmp_path / "out", store=store)
    person = signed_in(store, "reader@example.com")
    home = library.home(person)
    made(home / "story-he")
    made(home / "genesis-he", source="sefaria:Genesis")

    def forbidden(*_: object, **__: object) -> str:
        raise AssertionError("a quote must not spend")

    monkeypatch.setattr(library, "claim", forbidden)
    monkeypatch.setattr(library, "press", forbidden)
    monkeypatch.setattr(library, "enqueue", forbidden)
    ctx = context(library, store, person, home)
    ctx.press_at = "https://targum.test"

    got = tools.quote_rewrite(ctx, {"text": "story-he"})["rewrite"]
    assert got == {
        "title": "A story",
        "level": "Easy · 1,000 words",
        "credits": 0,
        "open": "https://targum.test/reader/story-he/reader/index.html?rewrite=1",
    }
    assert library.jobs == {}, "nothing made"
    assert "own texts" in tools.quote_rewrite(ctx, {"text": "genesis-he"})["error"]
    nobody = context(library, store, None, library.home(None))
    assert "account" in tools.quote_rewrite(nobody, {"text": "story-he"})["error"]


@pytest.mark.parametrize(
    ("source", "drawn"), [("https://example.com/story", True), ("sefaria:Ruth", False)]
)
def test_only_a_text_somebody_brought_carries_the_row_and_its_script(
    tmp_path: Path, source: str, drawn: bool
) -> None:
    from targum.cli import rebuild_one

    folder = tmp_path / "story-he"
    made(folder, source=source)
    rebuild_one(folder, reads=None, covers=tmp_path / "thumbs")

    page = (folder / "reader" / "index.html").read_text(encoding="utf-8")
    assert ('id="rewrite-open"' in page) is drawn
    assert ("TargumRewrite" in page) is drawn
