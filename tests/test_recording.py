"""Recordings: what they are, and how a section finds the one it wants.

The audio itself is content and never in the repository, so what is tested here is the
addressing — which is where a recording goes wrong. A wrong file plays the wrong chapter
and says nothing about it, and a reader who does not know the book cannot tell.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from targum.recording import Part, Recording
from targum.recording import index as recording_index


def spans(chapter: int, verses: int) -> dict[str, list[float]]:
    return {f"Ruth {chapter}:{n}": [float(n), float(n + 1)] for n in range(1, verses + 1)}


def made(**over: object) -> Recording:
    fields: dict[str, object] = {
        "source": "sefaria:Ruth",
        "credit": "Somebody",
        "licence": "CC BY-SA 3.0",
        "parts": [
            Part(ref="Ruth 1", audio="ruth-1.mp3", spans=spans(1, 22)),
            Part(ref="Ruth 2", audio="ruth-2.mp3", spans=spans(2, 23)),
        ],
    }
    fields.update(over)
    return Recording.model_validate(fields)


def test_a_section_finds_its_part_by_the_verses_it_holds() -> None:
    found = made().part_for(["Ruth 2:1", "Ruth 2:2"])
    assert found is not None
    assert found.audio == "ruth-2.mp3"


def test_the_second_chapter_of_a_range_is_not_the_second_part() -> None:
    """The bug this addressing exists to prevent.

    A reader built for Ruth 2 alone holds one section, and by position that section is
    the first — which by position is chapter one's audio. Asked by ref it is chapter two,
    which is what the reader is actually showing.
    """
    found = made().part_for(["Ruth 2:5"])
    assert found is not None and found.ref == "Ruth 2"


def test_a_section_with_no_recording_gets_none_rather_than_the_nearest() -> None:
    assert made().part_for(["Ruth 4:1"]) is None
    assert made().part_for([]) is None
    assert made().part_for(["", ""]) is None


def test_a_text_with_no_recording_is_silent_rather_than_an_error(tmp_path, monkeypatch) -> None:
    """Most texts have no recording. A library where adding audio to one book breaks
    every other is not a library."""
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    assert recording_index.load("sefaria:Job") is None


def test_a_recording_that_will_not_read_is_silent_too(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    folder = tmp_path / recording_index.slug("sefaria:Ruth")
    folder.mkdir()
    (folder / recording_index.MANIFEST).write_text("{not json", encoding="utf-8")
    assert recording_index.load("sefaria:Ruth") is None


def test_a_recording_is_read_back_as_it_was_written(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    folder = tmp_path / recording_index.slug("sefaria:Ruth")
    folder.mkdir()
    (folder / recording_index.MANIFEST).write_text(
        json.dumps(made().model_dump()), encoding="utf-8"
    )
    back = recording_index.load("sefaria:Ruth")
    assert back is not None
    assert back.credit == "Somebody"
    assert [part.ref for part in back.parts] == ["Ruth 1", "Ruth 2"]


@pytest.mark.parametrize(
    ("source", "want"),
    [
        ("sefaria:Ruth", "sefaria-ruth"),
        ("sefaria:he:Job", "sefaria-he-job"),
        ("sefaria:I Samuel", "sefaria-i-samuel"),
    ],
)
def test_a_source_keys_the_same_folder_on_any_disk(source: str, want: str) -> None:
    """Lowercase and hyphens only: a folder that resolves on a case-insensitive laptop
    and not on the box is a reader that is silent in production and fine in testing."""
    assert recording_index.slug(source) == want


def test_the_credit_is_required(tmp_path) -> None:
    """Every recording the library can use is used under a licence that names its reader.
    A model that lets the credit be forgotten is how it comes to be forgotten."""
    with pytest.raises(ValidationError):
        Recording.model_validate({"source": "sefaria:Ruth", "licence": "CC BY-SA 3.0"})


def test_a_verse_carries_its_ref_from_ingest_to_segment() -> None:
    """The whole mapping rests on this: the recording is aligned to verses, so a verse
    has to be addressable after segmentation and not only before it."""
    import json
    from pathlib import Path

    from targum.ingest.fetch import sefaria
    from targum.segment.base import segment_document

    # Read here rather than imported from `test_sefaria`. One test module importing
    # another only resolves while the repository root happens to be on `sys.path`, which
    # is true of one way of running pytest and not of the way the deploy runs it — so it
    # passed every time I ran it and stopped the deploy the first time that mattered.
    body = json.loads(
        (Path(__file__).parent / "fixtures" / "sefaria" / "ruth.he.json").read_text(
            encoding="utf-8"
        )
    )
    document = sefaria.document_from_payload(
        {"edition": body["versions"][0], "body": body}, "Ruth", "he"
    )

    class Whole:
        name = "test/1"

        def split(self, texts: list[str], language: str) -> list[list[str]]:
            return [[text] for text in texts]

    segmented = segment_document(document, Whole())
    verses = [s for s in segmented.segments if s.kind.value == "verse"]
    assert len(verses) == 85
    assert verses[0].ref == "Ruth 1:1"
    assert verses[-1].ref == "Ruth 4:22"
    assert all(segment.ref == "" for segment in segmented.segments if segment.kind.value != "verse")


# -- prose read-alongs --------------------------------------------------------


def prose(**over: object) -> Recording:
    """A two-part prose recording: blocks 0-2 in the first file, 3-4 in the second."""
    fields: dict[str, object] = {
        "source": "https://example.org/story.txt",
        "credit": "Somebody (LibriVox)",
        "licence": "public domain",
        "parts": [
            Part(ref="פרק א", audio="part-001.mp3", words="words-001.json", blocks=[0, 2]),
            Part(ref="פרק ב", audio="part-002.mp3", words="words-002.json", blocks=[3, 4]),
        ],
    }
    fields.update(over)
    return Recording.model_validate(fields)


def test_a_prose_section_finds_its_part_by_the_blocks_it_holds() -> None:
    found = prose().part_reading([3, 4])
    assert found is not None
    assert found.audio == "part-002.mp3"


def test_a_straddling_section_keeps_the_part_it_starts_in() -> None:
    """Its last lines go without a control rather than pointing at sound the page is
    not carrying — the same rule a missing span follows."""
    found = prose().part_reading([2, 3])
    assert found is not None and found.ref == "פרק א"


def test_blocks_no_part_reads_get_none() -> None:
    assert prose().part_reading([9]) is None
    assert prose().part_reading([]) is None
    assert prose().part_reading([-1]) is None


def test_a_scripture_part_answers_no_block_question() -> None:
    """The two addressings never cross: a verse part has no block range, and asking it
    for blocks must not hand back the wrong chapter's audio."""
    assert made().part_reading([0, 1]) is None


def _prose_document_and_segments():
    from targum.models import Block, BlockKind, Document, Segment

    blocks = [
        Block(id="b0000", kind=BlockKind.heading, level=2, text="פרק א"),
        Block(id="b0001", text="שלום עולם טוב"),
        Block(id="b0002", text="עוד משפט אחד"),
    ]
    document = Document(
        source="https://example.org/story.txt",
        title="סיפור",
        author="",
        language="he",
        blocks=blocks,
        content_hash="x",
        source_hash="y",
        ingester="test/1",
    )
    segments = [
        Segment(id="s1", block_id="b0001", block_index=1, index=0, text="שלום עולם טוב"),
        Segment(id="s2", block_id="b0002", block_index=2, index=1, text="עוד משפט אחד"),
    ]
    return document, segments


def test_a_prose_recording_reaches_the_page_with_spans_and_credit(tmp_path, monkeypatch) -> None:
    """The whole path a LibriVox book takes: manifest in the recordings folder, word
    clocks beside the audio, spans derived at build time, and the reader named."""
    from targum.render.builder import speech

    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    document, segments = _prose_document_and_segments()
    folder = tmp_path / recording_index.slug(document.source)
    folder.mkdir()
    rows = [
        ["פרק", 0.0, 0.4, -0.1],
        ["א", 0.5, 0.7, -0.1],
        ["שלום", 1.0, 1.5, -0.2],
        ["עולם", 1.6, 2.0, -0.2],
        ["טוב", 2.1, 2.4, -0.2],
        ["עוד", 3.0, 3.3, -0.3],
        ["משפט", 3.4, 3.9, -0.3],
        ["אחד", 4.0, 4.4, -0.3],
    ]
    (folder / "words-001.json").write_text(json.dumps(rows), encoding="utf-8")
    (folder / "part-001.mp3").write_bytes(b"ID3not-really-audio")
    recording = prose(
        source=document.source,
        parts=[Part(ref="פרק א", audio="part-001.mp3", words="words-001.json", blocks=[0, 2])],
    )
    (folder / recording_index.MANIFEST).write_text(recording.model_dump_json(), encoding="utf-8")

    spoken = speech(document, segments)
    assert spoken.spans["s1"] == [1.0, 2.4]
    assert spoken.spans["s2"] == [3.0, 4.4]
    assert spoken.words["s1"][0][2:] == [1.0, 1.5]
    assert spoken.credit == "Somebody (LibriVox)"
    assert spoken.licence == "public domain"
    assert spoken.label == "the reading"
    assert spoken.audio.startswith("data:audio/mpeg;base64,")


def test_a_section_past_the_recording_is_silent(tmp_path, monkeypatch) -> None:
    from targum.models import Segment
    from targum.render.builder import SILENT, speech

    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    document, _ = _prose_document_and_segments()
    folder = tmp_path / recording_index.slug(document.source)
    folder.mkdir()
    recording = prose(
        source=document.source,
        parts=[Part(ref="פרק א", audio="part-001.mp3", words="words-001.json", blocks=[0, 2])],
    )
    (folder / recording_index.MANIFEST).write_text(recording.model_dump_json(), encoding="utf-8")
    beyond = [Segment(id="s9", block_id="b0009", block_index=9, index=0, text="אין")]
    assert speech(document, beyond) is SILENT


def test_a_corrupt_words_file_leaves_the_page_silent(tmp_path, monkeypatch) -> None:
    """Rows of the wrong shape are a section without sound, not an aborted build —
    the same answer as a missing file or a wrong slug."""
    from targum.render.builder import SILENT, speech

    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    document, segments = _prose_document_and_segments()
    folder = tmp_path / recording_index.slug(document.source)
    folder.mkdir()
    (folder / "words-001.json").write_text('[["מלה", 0.0]]', encoding="utf-8")
    (folder / "part-001.mp3").write_bytes(b"x")
    recording = prose(
        source=document.source,
        parts=[Part(ref="פרק א", audio="part-001.mp3", words="words-001.json", blocks=[0, 2])],
    )
    (folder / recording_index.MANIFEST).write_text(recording.model_dump_json(), encoding="utf-8")
    assert speech(document, segments) is SILENT


def test_a_missing_part_file_leaves_the_page_silent(tmp_path, monkeypatch) -> None:
    """Word clocks without their audio: the spans derive, the file does not inline,
    and the page reads in silence rather than carrying a player with nothing in it."""
    from targum.render.builder import SILENT, speech

    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    document, segments = _prose_document_and_segments()
    folder = tmp_path / recording_index.slug(document.source)
    folder.mkdir()
    rows = [
        ["שלום", 1.0, 1.5, -0.2],
        ["עולם", 1.6, 2.0, -0.2],
        ["טוב", 2.1, 2.4, -0.2],
    ]
    (folder / "words-001.json").write_text(json.dumps(rows), encoding="utf-8")
    recording = prose(
        source=document.source,
        parts=[Part(ref="פרק א", audio="part-001.mp3", words="words-001.json", blocks=[0, 2])],
    )
    (folder / recording_index.MANIFEST).write_text(recording.model_dump_json(), encoding="utf-8")
    assert speech(document, segments) is SILENT


def test_an_ascii_source_with_an_underscore_keeps_its_folder() -> None:
    """The hash suffix is for what the reduction loses — a Hebrew title — not for an
    underscore. Half the wikisource URLs carry one, and their folders are already on
    the box under the plain names."""
    assert recording_index.slug("https://example.org/my_story.txt") == (
        "https-example-org-my-story-txt"
    )


def test_badly_scored_edges_are_trimmed_and_the_middle_is_kept() -> None:
    """A read-aloud edition opens with words the text never had; the aligner scores
    them below the floor and the trim takes them off — but only at the edges."""
    from targum.audio.align import SCORE_FLOOR
    from targum.recording.models import trimmed

    low = SCORE_FLOOR - 1
    rows = [
        ["this", 0.0, 0.1, low],
        ["is", 0.1, 0.2, low],
        ["שלום", 1.0, 1.5, -0.2],
        ["רע", 1.6, 1.7, low],
        ["עולם", 2.0, 2.4, -0.2],
        ["end", 9.0, 9.1, low],
    ]
    kept = trimmed(rows)
    assert [row[0] for row in kept] == ["שלום", "רע", "עולם"]
    assert trimmed([["a", 0.0, 0.1, low]]) == []


def test_a_hebrew_titled_source_keeps_its_identity_in_the_slug() -> None:
    """`wikisource:he:<hebrew title>` loses the title to the ascii reduction, and every
    such text then keys the same folder. What the reduction drops, a hash puts back —
    while ascii-only sources keep the folders already on the box."""
    a = recording_index.slug("wikisource:he:מגילת העצמאות של מדינת ישראל")
    b = recording_index.slug("wikisource:he:הכרזת העצמאות של ארצות הברית")
    assert a != b
    assert a.startswith("wikisource-he-") and b.startswith("wikisource-he-")
    assert recording_index.slug("sefaria:Ruth") == "sefaria-ruth"


def test_a_folder_reached_by_the_wrong_slug_stays_silent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    folder = tmp_path / recording_index.slug("sefaria:Ruth")
    folder.mkdir()
    (folder / recording_index.MANIFEST).write_text(
        json.dumps(made(source="sefaria:Job").model_dump()), encoding="utf-8"
    )
    assert recording_index.load("sefaria:Ruth") is None


# Scripture's word clocks (targum-internal#329). Gen 1:1 and 1:5 as the Leningrad Codex
# writes them, the second with a paseq standing alone and a section mark after the stop:
# two tokens a trope reading skips and the aligner was still handed.
GEN_1_1 = "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃"
GEN_1_5 = "וַיִּקְרָ֨א אֱלֹהִ֤ים ׀ לָאוֹר֙ י֔וֹם וְלַחֹ֖שֶׁךְ קָ֣רָא לָ֑יְלָה וַֽיְהִי־עֶ֥רֶב וַֽיְהִי־בֹ֖קֶר י֥וֹם אֶחָֽד׃ פ"


def ticking(text: str) -> list[list[float]]:
    """A clock per spoken word: word n from n to n + 0.5 seconds."""
    from targum.recording.models import spoken_words

    return [[float(n), n + 0.5] for n in range(len(spoken_words(text)))]


def chanted(**clocks: str) -> Part:
    timed = {ref: ticking(text) for ref, text in clocks.items()}
    from targum.recording.models import verse_spans

    return Part(ref="Bereshit 1", audio="aliyah-01.mp3", spans=verse_spans(timed), clocks=timed)


def test_a_leyning_manifest_from_before_word_clocks_still_reads() -> None:
    """Every manifest attached before 2026-09-28 has verse spans and no `clocks` key.
    It loads, finds its part by ref as it always did, and simply offers no word."""
    old = {
        "source": "sefaria:Genesis 1:1-6:8",
        "credit": "PocketTorah, Avery-Binder trope",
        "licence": "CC BY-SA 3.0",
        "parts": [
            {"ref": "Bereshit 1", "audio": "aliyah-01.mp3", "spans": {"Genesis 1:1": [0.4, 6.1]}}
        ],
    }
    recording = Recording.model_validate(old)
    part = recording.part_for(["Genesis 1:1"])
    assert part is not None and part.clocks == {}
    assert part.word_clocks("Genesis 1:1", GEN_1_1) == []
    assert part.phrase_spans("Genesis 1:1", GEN_1_1) == []


def test_a_verse_span_is_its_first_word_and_its_last() -> None:
    from targum.recording.models import verse_spans

    assert verse_spans({"Genesis 1:1": [[0.4, 0.9], [1.0, 1.3], [5.5, 6.1]]}) == {
        "Genesis 1:1": [0.4, 6.1]
    }
    assert verse_spans({"Genesis 1:2": []}) == {}, "a verse with no words has no span"


def test_the_words_are_counted_the_way_the_aligner_heard_them() -> None:
    """A token that is all accent was never said; the paseq and the section mark were
    handed to the aligner, so they keep their places in the count."""
    from targum.recording.models import spoken_words
    from targum.vocalize import strip_taamim

    for text in (GEN_1_1, GEN_1_5, "בָּרָ֣א ֑ אֱלֹהִ֑ים"):
        heard = [strip_taamim(text[a:b]) for a, b in spoken_words(text)]
        assert heard == strip_taamim(text).split()
    assert len(spoken_words(GEN_1_5)) == 13


def test_a_word_on_the_page_finds_its_clock() -> None:
    """Offsets into the bare text, which is what the page's words carry in `data-bare`."""
    from targum.vocalize import strip_nikkud

    part = chanted(**{"Genesis 1:5": GEN_1_5})
    rows = part.word_clocks("Genesis 1:5", GEN_1_5)
    bare, _ = strip_nikkud(GEN_1_5)
    assert len(rows) == 13
    assert bare[int(rows[0][0]) : int(rows[0][1])] == "ויקרא"
    assert rows[0][2:] == [0.0, 0.5]
    assert bare[int(rows[8][0]) : int(rows[8][1])] == "ויהי־ערב", "maqaf holds one token"
    assert rows[8][2:] == [8.0, 8.5]


def test_a_verse_whose_words_moved_under_the_recording_offers_none() -> None:
    part = chanted(**{"Genesis 1:1": GEN_1_1})
    assert part.word_clocks("Genesis 1:1", GEN_1_1 + " עוד") == []
    assert part.phrase_spans("Genesis 1:1", GEN_1_1 + " עוד") == []
    assert part.word_clocks("Genesis 1:2", GEN_1_1) == [], "a verse never timed"


def test_a_trope_phrase_is_heard_from_its_first_word_to_its_last() -> None:
    """Gen 1:1 is tipcha | munach etnachta | mercha tipcha | mercha silluq."""
    part = chanted(**{"Genesis 1:1": GEN_1_1})
    assert part.phrase_spans("Genesis 1:1", GEN_1_1) == [
        [0.0, 0.5],
        [1.0, 2.5],
        [3.0, 4.5],
        [5.0, 6.5],
    ]


def test_a_phrase_skips_what_was_timed_but_never_chanted() -> None:
    """Gen 1:5's paseq and closing פ each hold a clock, and belong to no phrase: the
    phrases land on the words either side, by token, not by the trope reading's count."""
    part = chanted(**{"Genesis 1:5": GEN_1_5})
    phrases = part.phrase_spans("Genesis 1:5", GEN_1_5)
    # Kadma, mahpach, the paseq, and pashta on לָאוֹר֙ closing it: tokens 0 to 3.
    assert phrases[0] == [0.0, 3.5]
    # The verse ends on אֶחָֽד׃, token 11, and the פ after it is heard by nobody.
    assert phrases[-1][1] == 11.5


def test_a_psalm_has_no_prose_phrases() -> None:
    psalm = "אַ֥שְֽׁרֵי הָאִ֗ישׁ אֲשֶׁ֤ר לֹ֥א הָלַךְ֮ בַּעֲצַ֪ת רְשָׁ֫עִ֥ים"
    part = chanted(**{"Psalms 1:1": psalm})
    assert part.phrase_spans("Psalms 1:1", psalm) == []
    assert part.word_clocks("Psalms 1:1", psalm), "its words are still its words"


def test_a_chanted_reading_gives_the_card_its_ear(tmp_path, monkeypatch) -> None:
    """The whole path: a leyning manifest with word clocks reaches the page as the same
    rows prose has, keyed by segment id; one without them reaches it with verses only."""
    from targum.models import BlockKind, Document, Segment
    from targum.render.builder import speech

    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path))
    document = Document(
        source="sefaria:Genesis 1:1-6:8",
        title="Bereshit",
        language="he",
        blocks=[],
        content_hash="x",
    )
    segments = [
        Segment(
            id="v1",
            block_id="b0000",
            block_index=0,
            index=0,
            kind=BlockKind.verse,
            text=GEN_1_1,
            ref="Genesis 1:1",
        )
    ]
    folder = tmp_path / recording_index.slug(document.source)
    folder.mkdir()
    (folder / "aliyah-01.mp3").write_bytes(b"ID3not-really-audio")

    def attach(part: Part) -> None:
        recording = Recording(
            source=document.source, credit="PocketTorah", licence="CC BY-SA 3.0", parts=[part]
        )
        (folder / recording_index.MANIFEST).write_text(
            recording.model_dump_json(), encoding="utf-8"
        )

    attach(chanted(**{"Genesis 1:1": GEN_1_1}))
    spoken = speech(document, segments)
    assert spoken.spans == {"v1": [0.0, 6.5]}
    assert len(spoken.words["v1"]) == 7
    assert spoken.words["v1"][0][2:] == [0.0, 0.5]

    attach(Part(ref="Bereshit 1", audio="aliyah-01.mp3", spans={"Genesis 1:1": [0.0, 6.5]}))
    spoken = speech(document, segments)
    assert spoken.spans == {"v1": [0.0, 6.5]}
    assert spoken.words == {}
