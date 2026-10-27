"""The owner of a text corrects its words and cuts it into parts (targum-internal#533).

What has to hold: the corrected line, and only it, gets a new id, so every other line
keeps the English, words and clock already paid for; nothing spends until Translate
again is pressed, and that press goes through `Library.press`; a library text is refused,
whoever's home holds a copy; and a recording read again from its transcript keeps the
correction and the cut.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from targum import correct
from targum.audio import manifest as manifest_module
from targum.ids import segment_id
from targum.models import (
    Annotation,
    Block,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
    Vocalization,
    read_artifact,
)
from targum.render.builder import split_sections

LINES = [
    ["שלום לכם.", "הגשם יורד היום."],
    ["אני הולך הביתה.", "זה סוף הסיפור."],
]
ENGLISH = ["Hello to you.", "The rain falls today.", "I'm going home.", "That's the end."]


def made(folder: Path, source: str = "https://example.com/story") -> SegmentedDocument:
    """A text of two paragraphs, two sentences each, translated, worded and pointed."""
    blocks = [Block(id=f"b{index:04d}", text=" ".join(pair)) for index, pair in enumerate(LINES)]
    document = Document(source=source, title="A story", language="he", blocks=blocks)
    document.content_hash = document.recompute_hash()
    segments = [
        Segment(
            id=segment_id(b, i, text),
            block_id=f"b{b:04d}",
            block_index=b,
            index=i,
            text=text,
        )
        for b, pair in enumerate(LINES)
        for i, text in enumerate(pair)
    ]
    segmented = SegmentedDocument(
        document_hash=document.content_hash, language="he", segmenter="rule", segments=segments
    )
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "reader").mkdir(exist_ok=True)
    (folder / "reader" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")
    Translation(
        name="Claude",
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="anthropic",
        segments={s.id: e for s, e in zip(segments, ENGLISH, strict=True)},
    ).write(folder / "translations" / "anthropic.natural.en.json")
    Annotation(
        document_hash=document.content_hash,
        language="he",
        annotator="test",
        method="m",
        method_note="",
        tokens={
            s.id: [Token(start=0, end=len(s.text.split()[0]), surface="w", lemma="w", band=1)]
            for s in segments
        },
    ).write(folder / "annotation.json")
    Vocalization(
        document_hash=document.content_hash,
        language="he",
        vocalizer="source",
        segments={s.id: s.text for s in segments},
    ).write(folder / "vocalization.json")
    return segmented


def ids(folder: Path) -> list[str]:
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    assert segmented is not None
    return [segment.id for segment in segmented.segments]


# -- whose text it is -------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    ["https://example.com/a", "/home/p1/uploads/x/story.txt", "targum-out/p1/x/audio/source.mp4"],
)
def test_a_text_somebody_brought_is_theirs_to_correct(source: str) -> None:
    assert correct.own_source(source)


@pytest.mark.parametrize(
    "source",
    ["sefaria:Genesis", "gutenberg:123", "wikisource:he:x", "weekly:2026-10-26", "dialogue:a", ""],
)
def test_a_library_text_is_not(source: str) -> None:
    assert not correct.own_source(source)


def test_a_link_the_catalogue_names_is_the_librarys(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import catalogue

    monkeypatch.setattr(
        catalogue, "matching", lambda source: object() if source.endswith("khan") else None
    )
    assert not correct.own_source("https://youtube.com/khan")
    assert not correct.own_source("targum-out/p1/x/audio/source.mp4", "https://youtube.com/khan")
    assert correct.own_source("https://youtube.com/mine")


# -- a line -----------------------------------------------------------------------------


def test_only_the_corrected_line_gets_a_new_id(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    before = ids(folder)

    done = correct.correct_line(folder, before[1], "  הגשם   ירד אתמול. ")

    after = ids(folder)
    assert done.now == "הגשם ירד אתמול.", "one line, tidied"
    assert after[0] == before[0] and after[2:] == before[2:], "every other line keeps its id"
    assert after[1] == done.new != before[1]
    document = read_artifact(Document, folder / "document.json")
    assert document is not None
    assert document.blocks[0].text == "שלום לכם. הגשם ירד אתמול."
    assert document.blocks[1].text == " ".join(LINES[1]), "the other block is untouched"


def test_every_artifact_agrees_on_the_new_text(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    line = ids(folder)[2]

    done = correct.correct_line(folder, line, "אני הולכת הביתה.")

    document = read_artifact(Document, folder / "document.json")
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    translation = read_artifact(Translation, folder / "translations" / "anthropic.natural.en.json")
    annotation = read_artifact(Annotation, folder / "annotation.json")
    vocalization = read_artifact(Vocalization, folder / "vocalization.json")
    assert document and segmented and translation and annotation and vocalization
    assert document.content_hash == document.recompute_hash()
    for artifact in (segmented, translation, annotation, vocalization):
        assert artifact.document_hash == document.content_hash
    # The English is kept, said to be from before; the words and pointing go, to be read
    # again here.
    assert translation.segments[done.new] == "I'm going home."
    assert line not in translation.segments
    assert done.new not in annotation.tokens and len(annotation.tokens) == 3
    assert done.new not in vocalization.segments and len(vocalization.segments) == 3
    assert correct.stale(folder) == {"en": [done.new]}
    assert correct.record(folder)["unread"] == [done.new]


def test_a_line_translated_since_is_no_longer_from_before(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    done = correct.correct_line(folder, ids(folder)[0], "שלום לכולם.")
    path = folder / "translations" / "anthropic.natural.en.json"
    translation = read_artifact(Translation, path)
    assert translation is not None
    translation.segments[done.new] = "Hello, everyone."
    translation.write(path)

    assert correct.stale(folder) == {}


def test_putting_a_line_back_leaves_no_correction(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    first = ids(folder)[3]

    one = correct.correct_line(folder, first, "זה הסוף.")
    two = correct.correct_line(folder, one.new, LINES[1][1])

    assert two.new == first, "the id is the text's, so the old id comes back"
    assert correct.record(folder)["lines"] == []


def test_a_line_corrected_twice_remembers_what_it_first_was(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    one = correct.correct_line(folder, ids(folder)[3], "זה הסוף.")
    correct.correct_line(folder, one.new, "וזה הסוף.")

    assert correct.record(folder)["lines"] == [
        {"block": "b0001", "was": LINES[1][1], "now": "וזה הסוף."}
    ]


@pytest.mark.parametrize(
    ("text", "key"),
    [("   ", "correct.empty"), ("א" * (correct.LONGEST + 1), "correct.too-long")],
)
def test_a_line_needs_words_and_not_too_many(tmp_path: Path, text: str, key: str) -> None:
    from targum.errors import TargumError

    folder = tmp_path / "story-he"
    made(folder)
    with pytest.raises(TargumError) as refused:
        correct.correct_line(folder, ids(folder)[0], text)
    assert refused.value.key == key


def test_a_line_that_is_not_there_is_refused(tmp_path: Path) -> None:
    from targum.errors import TargumError

    folder = tmp_path / "story-he"
    made(folder)
    with pytest.raises(TargumError):
        correct.correct_line(folder, "0009.000-nothing", "שלום")


# -- the recording ----------------------------------------------------------------------


def test_the_line_keeps_its_place_and_every_word_it_kept_keeps_its_clock(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    line = ids(folder)[1]
    text = LINES[0][1]  # הגשם יורד היום.
    words = [[0, 4, 1.0, 1.4], [5, 9, 1.5, 1.9], [10, 15, 2.0, 2.5]]
    assert [text[a:b] for a, b, _, _ in words] == ["הגשם", "יורד", "היום."]
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(
            source="x.mp3",
            sha256="0",
            duration=3.0,
            language="he",
            parts=[
                manifest_module.ManifestPart(
                    number=1,
                    start=0.0,
                    end=3.0,
                    audio="audio/part-001.mp3",
                    transcribed=True,
                    spans={line: [1.0, 2.5]},
                    words={line: [list(map(float, row)) for row in words]},
                )
            ],
        ),
    )

    done = correct.correct_line(folder, line, "הגשם ירד היום.")

    kept = manifest_module.load(folder)
    assert kept is not None
    part = kept.parts[0]
    assert part.spans == {done.new: [1.0, 2.5]}, "the line's span is the line's"
    rows = part.words[done.new]
    said = [done.now[int(a) : int(b)] for a, b, _, _ in rows]
    assert said == ["הגשם", "היום."], "the changed word has no clock: a gap, not a lie"
    assert [row[2:] for row in rows] == [[1.0, 1.4], [2.0, 2.5]]


def test_a_part_still_waiting_to_be_heard_cannot_be_corrected(tmp_path: Path) -> None:
    from targum.errors import TargumError

    folder = tmp_path / "story-he"
    segmented = made(folder)
    segmented.segments[3].ref = "part 2:waiting"
    segmented.write(folder / "segments.json")
    with pytest.raises(TargumError) as refused:
        correct.correct_line(folder, segmented.segments[3].id, "משהו")
    assert refused.value.key == "correct.waiting"


def test_a_transcript_read_again_keeps_the_correction(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    correct.correct_line(folder, ids(folder)[1], "הגשם ירד אתמול.")
    heard = Document(
        source="x",
        language="he",
        blocks=[Block(id=f"b{i:04d}", text=" ".join(pair)) for i, pair in enumerate(LINES)]
        + [Block(id="b0002", text="חלק חדש.")],
    )

    assert correct.replay_document(folder, heard)
    assert heard.blocks[0].text == "שלום לכם. הגשם ירד אתמול."
    assert not correct.replay_document(folder, heard), "and only once"


# -- a part -----------------------------------------------------------------------------


def test_a_cut_starts_a_part_and_moves_no_id(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    before = ids(folder)

    breaks = correct.cut(folder, before[2])

    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    assert segmented is not None
    assert breaks == [before[2]] and ids(folder) == before
    assert [s.segment_ids for s in split_sections(segmented)] == [before[:2], before[2:]]
    assert correct.page_of(folder, before[3]) == "sec-0002.html"

    assert correct.cut(folder, before[2], join=True) == []
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    assert segmented is not None
    assert len(split_sections(segmented)) == 1


def test_the_first_line_already_starts_the_text(tmp_path: Path) -> None:
    from targum.errors import TargumError

    folder = tmp_path / "story-he"
    made(folder)
    with pytest.raises(TargumError):
        correct.cut(folder, ids(folder)[0])


def test_a_cut_follows_its_line_through_a_correction(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    correct.cut(folder, ids(folder)[2])
    done = correct.correct_line(folder, ids(folder)[2], "אני הולכת הביתה.")

    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    assert segmented is not None
    assert segmented.breaks == [done.new]
    resegmented = segmented.model_copy(update={"breaks": []})
    correct.replay_breaks(folder, resegmented)
    assert resegmented.breaks == [done.new], "a re-segmented text keeps the cut"


def test_a_join_takes_away_the_page_of_the_part_that_went(tmp_path: Path) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    for name in ("sec-0001.html", "sec-0002.html"):
        (folder / "reader" / name).write_text("<p>x</p>", encoding="utf-8")
    correct.tidy_pages(folder)
    assert not list((folder / "reader").glob("sec-*.html")), "one part has no part pages"


# -- the words, again -------------------------------------------------------------------


class Reads:
    """An annotator that reads every line as one word, and says which lines it read."""

    def __init__(self) -> None:
        self.read: list[str] = []

    def annotate(self, run: SegmentedDocument, vocalization: Any = None) -> Annotation:
        self.read += [s.id for s in run.segments]
        return Annotation(
            document_hash=run.document_hash,
            language="he",
            annotator="test",
            method="m",
            method_note="",
            tokens={
                s.id: [Token(start=0, end=1, surface="x", lemma="x", band=1)] for s in run.segments
            },
        )


def test_only_the_corrected_lines_are_read_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "story-he"
    made(folder)
    reads = Reads()
    monkeypatch.setattr(correct, "_annotator", lambda folder, document: reads)
    done = correct.correct_line(folder, ids(folder)[1], "הַגֶּשֶׁם יָרַד.")

    assert correct.words_again(folder) == [done.new]

    assert reads.read == [done.new]
    annotation = read_artifact(Annotation, folder / "annotation.json")
    vocalization = read_artifact(Vocalization, folder / "vocalization.json")
    assert annotation is not None and vocalization is not None
    assert len(annotation.tokens) == 4 and done.new in annotation.tokens
    assert vocalization.segments[done.new] == done.now, "the line's own pointing, kept"
    assert correct.record(folder)["unread"] == []


def test_a_language_a_model_reads_waits_for_the_press(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.annotate import model_lemma

    folder = tmp_path / "story-he"
    made(folder)
    reads = Reads()
    monkeypatch.setattr(correct, "_annotator", lambda folder, document: reads)
    monkeypatch.setattr(model_lemma, "reads", lambda language: True)
    done = correct.correct_line(folder, ids(folder)[1], "הגשם ירד אתמול.")

    assert correct.words_again(folder) == []
    assert reads.read == [], "nothing a model reads is read for nothing"
    assert correct.record(folder)["unread"] == [done.new]


# -- the doors --------------------------------------------------------------------------


@pytest.fixture
def serving(tmp_path: Path) -> Iterator[tuple[int, Any]]:
    from targum.accounts import Store
    from targum.mail import ConsoleMailer
    from targum.serve import Handler, Library

    out = tmp_path / "targum-out"
    out.mkdir()
    library = Library(out)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": library,
            "token": "test-key",
            "welcome": "<html>start</html>",
            "shelf": "<html>library</html>",
            "store": Store(tmp_path / "words.db"),
            "mailer": ConsoleMailer(),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, library
    finally:
        server.shutdown()
        server.server_close()


def ask(port: int, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST" if body is not None else "GET",
        path,
        body=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Targum-Key": "test-key"},
    )
    answer = conn.getresponse()
    status, data = answer.status, json.loads(answer.read() or b"{}")
    conn.close()
    return status, data


def test_the_owner_corrects_and_the_words_are_read_again_for_nothing(
    serving: tuple[int, Any],
) -> None:
    port, library = serving
    folder = library.home(None) / "story-he"
    made(folder)
    line = ids(folder)[1]

    status, asked = ask(port, "/text/edit?name=story-he")
    assert status == 200 and asked["editable"] is True

    status, answer = ask(
        port, "/text/correct", {"name": "story-he", "line": line, "text": "הגשם ירד."}
    )
    assert status == 200
    assert answer["line"] != line and answer["before"] == ["en"]
    job = library.jobs[answer["job"]["id"]]
    assert job.kind == "words" and job.estimate == 0, "a correction claims nothing"
    assert job.options == {"words_again": True, "folder": "story-he"}

    # A second correction before the pass starts joins it.
    _, again = ask(
        port, "/text/correct", {"name": "story-he", "line": ids(folder)[0], "text": "שלום."}
    )
    assert again["job"]["id"] == job.id


def test_a_library_text_cannot_be_corrected_by_its_reader(serving: tuple[int, Any]) -> None:
    port, library = serving
    folder = library.home(None) / "genesis-he"
    made(folder, source="sefaria:Genesis")
    line = ids(folder)[0]

    assert ask(port, "/text/edit?name=genesis-he")[1] == {"editable": False}
    for path, body in (
        ("/text/correct", {"name": "genesis-he", "line": line, "text": "בראשית"}),
        ("/text/part", {"name": "genesis-he", "line": ids(folder)[2]}),
        ("/text/translate", {"name": "genesis-he"}),
    ):
        assert ask(port, path, body)[0] == 404, path
    assert ids(folder)[0] == line, "nothing changed"


def test_another_home_is_out_of_reach(serving: tuple[int, Any]) -> None:
    port, library = serving
    from targum.accounts import Person

    theirs = library.home(Person(7, "them@example.com")) / "story-he"
    made(theirs)
    status, _ = ask(
        port, "/text/correct", {"name": "../p7/story-he", "line": ids(theirs)[0], "text": "x"}
    )
    assert status == 404


def test_a_correction_waits_for_a_build_working_on_the_text(serving: tuple[int, Any]) -> None:
    from targum.serve import Job

    port, library = serving
    home = library.home(None)
    folder = home / "story-he"
    made(folder)
    library.jobs["b1"] = Job(
        id="b1", source="x", stage="working", home=home, options={"folder": "story-he"}
    )

    status, answer = ask(
        port, "/text/correct", {"name": "story-he", "line": ids(folder)[0], "text": "שלום."}
    )
    assert status == 409 and "still working" in answer["error"]


def test_translate_again_is_a_press_through_the_rails(
    serving: tuple[int, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.translate import anthropic_provider

    port, library = serving
    folder = library.home(None) / "story-he"
    made(folder)
    done = correct.correct_line(folder, ids(folder)[1], "הגשם ירד.")
    monkeypatch.setattr(anthropic_provider.AnthropicProvider, "available", lambda self: (True, ""))
    monkeypatch.setattr(
        anthropic_provider.AnthropicProvider,
        "estimate",
        lambda self, segments, source, target, style: 0.01 * len(segments),
    )
    pressed: list[Any] = []
    monkeypatch.setattr(library, "press", lambda job: pressed.append(job) or "")

    status, answer = ask(port, "/text/translate", {"name": "story-he"})

    assert status == 200
    assert len(pressed) == 1, "one press, claimed by `Library.press`"
    job = pressed[0]
    assert job.options == {"again": [done.new], "folder": "story-he", "to": "en"}
    assert job.estimate == pytest.approx(0.01), "priced for the corrected line alone"
    assert answer["id"] == job.id


def test_a_press_refused_by_the_rails_says_so(
    serving: tuple[int, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.translate import anthropic_provider

    port, library = serving
    folder = library.home(None) / "story-he"
    made(folder)
    correct.correct_line(folder, ids(folder)[1], "הגשם ירד.")
    monkeypatch.setattr(anthropic_provider.AnthropicProvider, "available", lambda self: (True, ""))
    monkeypatch.setattr(anthropic_provider.AnthropicProvider, "estimate", lambda self, *args: 0.01)
    monkeypatch.setattr(library, "max_cost", 0.001)

    status, answer = ask(port, "/text/translate", {"name": "story-he"})

    assert status == 402 and answer["stage"] == "blocked"


def test_a_cut_says_which_page_the_line_is_now_on(serving: tuple[int, Any]) -> None:
    port, library = serving
    folder = library.home(None) / "story-he"
    made(folder)
    line = ids(folder)[2]

    status, answer = ask(port, "/text/part", {"name": "story-he", "line": line})

    assert status == 200
    assert answer["breaks"] == [line] and answer["page"] == "sec-0002.html"
    assert library.jobs[answer["job"]["id"]].kind == "words"


def test_the_free_pass_redraws_the_reader_with_the_corrected_line(
    serving: tuple[int, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, library = serving
    folder = library.home(None) / "story-he"
    made(folder)
    monkeypatch.setattr(correct, "_annotator", lambda folder, document: Reads())
    _, answer = ask(
        port, "/text/correct", {"name": "story-he", "line": ids(folder)[1], "text": "הגשם ירד."}
    )
    job = library.jobs[answer["job"]["id"]]

    library.run(job)

    assert job.stage == "done", job.error
    page = (folder / "reader" / "index.html").read_text(encoding="utf-8")
    assert "הגשם ירד." in page and "הגשם יורד היום." not in page
    assert correct.record(folder)["unread"] == []


def test_translate_again_buys_the_corrected_line_and_nothing_else(
    serving: tuple[int, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.serve import Job
    from targum.translate import anthropic_provider

    port, library = serving
    folder = library.home(None) / "story-he"
    made(folder)
    done = correct.correct_line(folder, ids(folder)[1], "הגשם ירד.")
    bought: list[str] = []

    def translate(self: Any, segments: list[Segment], *args: Any, **kwargs: Any) -> dict[str, str]:
        bought.extend(segment.id for segment in segments)
        return {segment.id: "The rain fell." for segment in segments}

    monkeypatch.setattr(anthropic_provider.AnthropicProvider, "translate", translate)
    job = Job(
        id="again1",
        source="https://example.com/story",
        home=library.home(None),
        options={"again": [done.new], "folder": "story-he", "to": "en"},
    )
    library.jobs[job.id] = job

    library.run(job)

    assert job.stage == "done", job.error
    assert bought == [done.new]
    translation = read_artifact(Translation, folder / "translations" / "anthropic.natural.en.json")
    assert translation is not None
    assert translation.segments[done.new] == "The rain fell."
    assert [translation.segments[sid] for sid in ids(folder) if sid != done.new] == [
        e for i, e in enumerate(ENGLISH) if i != 1
    ]
    assert correct.stale(folder) == {}
    assert "The rain fell." in (folder / "reader" / "index.html").read_text(encoding="utf-8")


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
    assert ('id="correct-open"' in page) is drawn
    assert ("TargumCorrect" in page) is drawn, "a library text's page carries no correct.js"
