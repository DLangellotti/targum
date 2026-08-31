"""A recording as a Document: growth that never moves what is already paid for."""

from __future__ import annotations

from pathlib import Path

from targum.audio import parts as parts_module
from targum.audio import probe as probe_module
from targum.ingest import load
from targum.ingest.audio import AudioIngester, refined_path
from targum.ingest.subtitles import parse
from targum.models import BlockKind
from targum.segment import segment_document
from targum.transcribe.models import Refined, RefinedParagraph, Word, write
from targum.transcribe.refine.rules import RuleRefiner


class SplitsOnFullStops:
    """The conftest FakeSegmenter, redeclared: tests never import each other, since a
    cross-module test import resolves only when the repo root happens to be on
    sys.path — it passed every run and stopped a deploy."""

    name = "fake/1"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        return [[part.strip() + "." for part in text.split(".") if part.strip()] for text in texts]


def workspace_with(tmp_path: Path, fake, language: str = "en") -> Path:
    """An adopted recording: the file, its probe and its part plan, on disk."""
    workspace = tmp_path / "talk-en" / "audio"
    workspace.mkdir(parents=True)
    recording = workspace / "source.mp3"
    recording.write_bytes(b"audio")
    probe_module.adopt(recording, workspace)
    found = probe_module.load(workspace)
    assert found is not None
    drafted = parts_module.plan(found, language=language)
    parts_module.write(workspace, drafted)
    return workspace


def heard(workspace: Path, number: int, text: str, speaker: str = "") -> None:
    words = [
        Word(text=piece, start=float(n), end=float(n) + 0.9, speaker=speaker)
        for n, piece in enumerate(text.split())
    ]
    write(
        refined_path(workspace, number),
        Refined(
            refiner="rules/1",
            provider="null",
            language="en",
            paragraphs=[RefinedParagraph(text=text, speaker=speaker, words=words)],
        ),
    )


def test_an_untranscribed_part_is_a_heading_and_a_placeholder_so_the_contents_page_counts_it(
    fake_audio, tmp_path: Path
) -> None:
    """split_sections opens a section only past body text, so a waiting part carries
    some: its own clock range, which is at least true."""
    fake_audio.duration = 1440.0
    workspace = workspace_with(tmp_path, fake_audio)
    document = AudioIngester().load(str(workspace / "source.mp3"))
    kinds = [(block.kind, block.ref) for block in document.blocks]
    assert (BlockKind.heading, "part 1") in kinds
    assert (BlockKind.paragraph, "part 1:waiting") in kinds
    waiting = next(block for block in document.blocks if block.ref == "part 1:waiting")
    assert "–" in waiting.text  # a clock range, not prose


def test_block_ids_are_reserved_per_part_so_transcribing_part_two_moves_no_id_in_part_nine(
    fake_audio, tmp_path: Path
) -> None:
    """Positional ids would shift every later part when an earlier one grows, taking
    every translation keyed to a segment with them."""
    fake_audio.duration = 7200.0  # ten parts
    workspace = workspace_with(tmp_path, fake_audio)
    heard(workspace, 9, "nine alpha. nine beta.")
    before = AudioIngester().load(str(workspace / "source.mp3"))
    nine_before = {b.id for b in before.blocks if b.ref.startswith("part 9")}
    lines = segment_document(before, SplitsOnFullStops()).segments
    ids_before = {line.id for line in lines if line.ref.startswith("part 9")}

    heard(workspace, 2, "two arrives later with much more text than part nine ever had.")
    after = AudioIngester().load(str(workspace / "source.mp3"))
    nine_after = {b.id for b in after.blocks if b.ref.startswith("part 9")}
    lines = segment_document(after, SplitsOnFullStops()).segments
    ids_after = {line.id for line in lines if line.ref.startswith("part 9")}
    assert nine_before == nine_after
    assert ids_before == ids_after


def test_the_segmenter_reads_block_index_from_the_id_and_every_existing_document_is_unchanged(
    document, fake_segmenter
) -> None:
    """For every document already on disk the derived index equals the position, byte
    for byte — this must never re-key a text somebody paid to translate."""
    segments = segment_document(document, fake_segmenter).segments
    assert [s.id.split(".")[0] for s in segments] == ["0000", "0001", "0001", "0002"]


def test_growth_changes_the_source_hash_so_it_is_never_mistaken_for_a_hand_edit(
    fake_audio, tmp_path: Path
) -> None:
    """`Build.ingest` preserves a hand-edited document over a fresh ingest when the
    source hash is unchanged. A transcript arriving must read as the file changing."""
    fake_audio.duration = 1440.0
    workspace = workspace_with(tmp_path, fake_audio)
    empty = AudioIngester().load(str(workspace / "source.mp3"))
    heard(workspace, 1, "now there are words.")
    grown = AudioIngester().load(str(workspace / "source.mp3"))
    assert empty.source_hash != grown.source_hash


def test_ingest_load_keeps_a_source_hash_the_ingester_set(fake_audio, tmp_path: Path) -> None:
    """The dispatcher hashes local files as UTF-8 text, which for a recording is both
    wasteful and wrong; the ingester's own claim wins."""
    fake_audio.duration = 1440.0
    workspace = workspace_with(tmp_path, fake_audio)
    direct = AudioIngester().load(str(workspace / "source.mp3"))
    routed = load(str(workspace / "source.mp3"))
    assert routed.source_hash == direct.source_hash
    # The version half of the name moves; what matters here is which ingester spoke.
    assert routed.ingester.startswith("audio/")


def test_two_speakers_become_paragraphs_that_name_their_speaker() -> None:
    """A podcast turn is a monologue, and a `turn` block is never split — so diarized
    speech is paragraphs carrying their speaker instead."""
    from targum.transcribe.models import Transcript

    words = [
        Word(text="hello", start=0.0, end=0.4, speaker="1"),
        Word(text="there", start=0.5, end=0.9, speaker="1"),
        Word(text="hi", start=1.0, end=1.3, speaker="2"),
    ]
    refined = RuleRefiner().refine(
        Transcript(provider="null", language="en", duration=2.0, words=words)
    )
    assert [(p.text, p.speaker) for p in refined.paragraphs] == [("hello there", "1"), ("hi", "2")]


def test_the_artist_tag_is_the_byline_and_the_title_tag_is_the_title(
    fake_audio, tmp_path: Path
) -> None:
    """The credit a page can stand behind is the file's own claim about its author —
    shown as a byline, translated like one, never asserted as a licence."""
    fake_audio.duration = 600.0
    fake_audio.title = "A Winter Talk"
    fake_audio.artist = "Somebody Famous"
    workspace = workspace_with(tmp_path, fake_audio)
    document = AudioIngester().load(str(workspace / "source.mp3"))
    assert document.title == "A Winter Talk"
    assert document.author == "Somebody Famous"
    assert any(
        block.kind is BlockKind.byline and block.text == "Somebody Famous"
        for block in document.blocks
    )


def test_an_srt_with_overlapping_cues_out_of_order_is_read_in_order() -> None:
    """Subtitle files are exported by tools that disagree about everything."""
    srt = (
        "2\n00:00:05,000 --> 00:00:08,000\nsecond cue\n\n"
        "1\n00:00:01,000 --> 00:00:06,000\nfirst cue\n"
    )
    cues = parse(srt)
    assert [cue.text for cue in cues] == ["first cue second cue"]
    assert cues[0].start == 1.0
    assert cues[0].end == 8.0


def test_vtt_styling_tags_are_dropped_and_the_voice_tag_names_the_speaker() -> None:
    vtt = (
        "WEBVTT\n\nNOTE a comment\n\n"
        "00:01.000 --> 00:03.000 align:start\n<v Rivka><i>שלום</i> לכם</v>\n\n"
        "00:04.500 --> 00:06.000\n<c.yellow>ברוכים</c> הבאים\n"
    )
    cues = parse(vtt)
    assert [(cue.text, cue.speaker) for cue in cues] == [
        ("שלום לכם", "Rivka"),
        ("ברוכים הבאים", ""),
    ]


def test_a_part_heading_leads_with_its_name_in_the_texts_own_language(
    fake_audio, tmp_path: Path
) -> None:
    """A bare clock range reads as data; a chapter deserves a name — in the language
    of the text, so it is translated like any heading."""
    fake_audio.duration = 1440.0
    workspace = workspace_with(tmp_path, fake_audio, language="he")
    document = AudioIngester().load(str(workspace / "source.mp3"))
    headings = [b.text for b in document.blocks if b.ref == "part 1"]
    assert headings == ["חלק 1 · 0:00–12:00"]


def test_a_chapter_marks_own_title_outranks_the_invented_name(fake_audio, tmp_path: Path) -> None:
    fake_audio.duration = 900.0
    fake_audio.chapters = [(0.0, 900.0, "פרק ראשון")]
    workspace = workspace_with(tmp_path, fake_audio, language="he")
    document = AudioIngester().load(str(workspace / "source.mp3"))
    headings = [b.text for b in document.blocks if b.ref == "part 1"]
    assert headings == ["פרק ראשון"]


def test_a_corrected_title_tag_reaches_the_page_rather_than_reading_as_a_hand_edit(
    fake_audio, tmp_path: Path
) -> None:
    """The tags shape the document, so they ride in the source hash: without that, a
    fixed title loses to the reconciliation rule that protects hand edits."""
    import json

    fake_audio.duration = 600.0
    workspace = workspace_with(tmp_path, fake_audio)
    before = AudioIngester().load(str(workspace / "source.mp3"))
    probe = workspace / "probe.json"
    data = json.loads(probe.read_text())
    data["title"] = "A Proper Name"
    probe.write_text(json.dumps(data))
    after = AudioIngester().load(str(workspace / "source.mp3"))
    assert after.title == "A Proper Name"
    assert after.source_hash != before.source_hash
