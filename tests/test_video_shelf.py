"""The curated video shelf: a `video:` source the box resolves off its own disk.

The point of the shelf is one thing the import path cannot do. `Library.prepare` refuses
a YouTube address by name, so a catalogue row naming one would fail on the box every time
a reader pressed build — and a reader's own import is credited to nobody, because nobody
verified it. A curated video is fetched here, checked here, and carried there, and the
page states the licence because somebody read it before the fetch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.audio import manifest as manifest_module
from targum.errors import TargumError
from targum.models import Block, BlockKind, Document, Segment, SegmentedDocument, Translation
from targum.video import store

#: Real Hebrew, because the shelf's whole promise is that a document carried onto it and
#: re-segmented on the box comes back with the segment ids it was built with. Hebrew is
#: drawn by rule rather than by a model (targum#71), so segmenting here is fast, offline
#: and exactly what the box will do.
SAID = "ללב יש ארבעה חדרים. הדם חוצה אותו פעמיים. הצד השמאלי עובד קשה יותר."


def segments_of(document: Document) -> list[Segment]:
    from targum.segment import HebrewSegmenter, segment_document

    return list(segment_document(document, HebrewSegmenter()).segments)


def shelve(root: Path, identifier: str = "abc123", **record: object) -> Path:
    """One curated video on a shelf, complete enough to build from.

    The English and the spans are keyed to the ids the segmenter actually produces, not
    to ids chosen here — which is the thing the shelf is betting on, so a fixture that
    faked it would test nothing.
    """
    folder = root / identifier
    (folder / "audio" / "parts").mkdir(parents=True, exist_ok=True)
    (folder / "audio" / "parts" / "part-001.mp3").write_bytes(b"ID3sound")
    (folder / "audio" / "parts" / "part-001.mp4").write_bytes(b"ftypmp42film")

    document = Document(
        source=f"video:{identifier}",
        title="A Talk",
        language="he",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=SAID)],
    )
    document.content_hash = document.recompute_hash()
    document.write(folder / store.DOCUMENT)
    lines = segments_of(document)
    Translation(
        name="English (machine, natural)",
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="anthropic",
        segments={line.id: f"line {n}" for n, line in enumerate(lines)},
    ).write(folder / store.ENGLISH)
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(
            source="talk.mp4",
            home="https://www.youtube.com/watch?v=abc123",
            sha256="x",
            duration=10.0,
            language="he",
            parts=[
                manifest_module.ManifestPart(
                    number=1,
                    start=0.0,
                    end=10.0,
                    audio="audio/parts/part-001.mp3",
                    video="audio/parts/part-001.mp4",
                    spans={line.id: [0.0, 10.0] for line in lines},
                )
            ],
        ),
    )
    held: dict[str, object] = {
        "id": identifier,
        "title": "A Talk",
        "home": "https://www.youtube.com/watch?v=abc123",
        "credit": "Khan Academy Hebrew",
        "licence": "CC BY 3.0",
        "licence_url": "https://creativecommons.org/licenses/by/3.0/",
    }
    held.update(record)
    (folder / store.CURATED).write_text(json.dumps(held), encoding="utf-8")
    return folder


@pytest.fixture
def shelf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "videos"
    monkeypatch.setenv("TARGUM_VIDEO_DIR", str(root))
    from targum import spoken

    # Both are `@cache`d for a page's worth of reads, and a test that shelves a video
    # after one has been asked would otherwise see the answer from before it existed.
    spoken.sources.cache_clear()
    spoken.video_sources.cache_clear()
    return root


def test_a_curated_video_is_read_off_the_shelf(shelf: Path) -> None:
    shelve(shelf)
    from targum.ingest.fetch import FETCHERS, is_identifier

    assert is_identifier("video:abc123")
    document = FETCHERS["video"].load("abc123")
    assert document.source == "video:abc123"
    assert document.ingester == "video/1"


def test_a_video_that_is_not_on_the_shelf_says_where_it_looked(shelf: Path) -> None:
    """A missing shelf is the ordinary state of a fresh machine, and the sentence has to
    be actionable rather than a traceback."""
    from targum.ingest.fetch import FETCHERS

    with pytest.raises(TargumError) as caught:
        FETCHERS["video"].load("nothing-here")
    assert "nothing-here" in caught.value.message
    assert str(shelf) in (caught.value.hint or "")


def test_the_shelf_answers_for_the_chip(shelf: Path) -> None:
    """What puts "video" on a catalogue row. Asked of the disk, like every other claim
    about media, so a shelf that did not arrive shows no chip rather than a dead one."""
    from targum import spoken

    assert not spoken.is_video("video:abc123"), "nothing is on the shelf yet"
    shelve(shelf)
    spoken.sources.cache_clear()
    spoken.video_sources.cache_clear()
    assert spoken.is_video("video:abc123")
    assert spoken.is_spoken("video:abc123")
    assert not spoken.is_video("video:someone-elses")


def test_a_soundtrack_only_video_is_audio_and_not_video(shelf: Path) -> None:
    from targum import spoken

    folder = shelve(shelf, "quiet")
    kept = manifest_module.load(folder)
    assert kept is not None
    kept.parts[0].video = ""
    manifest_module.write(folder, kept)
    spoken.sources.cache_clear()
    spoken.video_sources.cache_clear()
    assert spoken.is_spoken("video:quiet")
    assert not spoken.is_video("video:quiet")


def test_the_page_states_the_licence_the_import_path_will_not(shelf: Path) -> None:
    """The whole difference between a curated video and somebody's upload.

    `_imported` prints no credit because a licence targum cannot verify is one it must
    not print. Here it was read off the video and written down before the fetch, so the
    page states it — which is the condition on which a CC BY video may be published.
    """
    from targum.render.builder import speech

    shelve(shelf)
    document = store.document("abc123")
    assert document is not None
    spoken = speech(document, segments_of(document))
    assert spoken.credit == "Khan Academy Hebrew"
    assert spoken.licence == "CC BY 3.0"
    assert spoken.licence_url.startswith("https://creativecommons.org/licenses/")
    # Nobody read this aloud, and the credit line has to say so.
    assert spoken.credited == "Video by"
    assert spoken.label == "the video"
    assert spoken.video.endswith("part-001.mp4")
    assert spoken.home == "https://www.youtube.com/watch?v=abc123"


def test_a_video_whose_record_is_gone_is_silent_rather_than_uncredited(shelf: Path) -> None:
    """A half-copied shelf is a thing that happens mid-rsync. The answer is no sound,
    never sound with the credit missing — the one outcome the licence forbids."""
    from targum.render.builder import speech

    folder = shelve(shelf)
    (folder / store.CURATED).unlink()
    document = store.document("abc123")
    assert document is not None
    assert speech(document, segments_of(document)).audio == ""


def test_the_english_arrives_with_the_video_and_still_says_it_is_machine(shelf: Path) -> None:
    """Bought once by the operator, so no box buys it again — and `kind` is untouched,
    because a machine translation that stops saying so at the shelf is the one thing
    this must not do."""
    from targum.pipeline import Build

    shelve(shelf)
    build = Build(source="video:abc123", target_language="en", provider_name="null")
    document = store.document("abc123")
    assert document is not None
    lines = segments_of(document)
    segmented = SegmentedDocument(
        document_hash="h2", language="he", segmenter="t/1", segments=lines
    )
    carried = build.authored(document, segmented)
    assert carried is not None
    assert carried.kind == "machine"
    assert carried.provider == "anthropic"
    assert carried.segments[lines[0].id] == "line 0"
    # Re-stamped to the document it is being served against, or the reader would refuse
    # a translation that fits it perfectly well.
    assert carried.document_hash == "h2"


def test_english_that_no_longer_fits_the_text_is_declined(shelf: Path) -> None:
    """A store whose text moved under its translation fits nothing. Better to buy an
    English than to pair the wrong one line by line."""
    from targum.pipeline import Build

    shelve(shelf)
    build = Build(source="video:abc123", target_language="en", provider_name="null")
    document = Document(source="video:abc123", title="A Talk", language="he", blocks=[])
    segmented = SegmentedDocument(
        document_hash="h2",
        language="he",
        segmenter="t/1",
        segments=[
            Segment(
                id="9999.999-zzz",
                block_id="b0",
                block_index=0,
                index=0,
                text="אחר",
                kind=BlockKind.paragraph,
            )
        ],
    )
    assert build.authored(document, segmented) is None


def test_a_curated_video_is_a_public_source(shelf: Path) -> None:
    """So its English keys the key everybody arrives at. Under an owner's key the same
    text would be a second copy nobody else can reach, and the shipped one would be
    bought again per reader."""
    from targum.pipeline import Build

    assert Build(source="video:abc123", target_language="en").shared_source()


def test_curation_refuses_a_video_that_names_nobody(tmp_path: Path) -> None:
    """The last place a licence breach can be caught before it is written down."""
    from targum.video.curate import curate

    built = tmp_path / "built"
    (built / "audio" / "parts").mkdir(parents=True)
    with pytest.raises(TargumError, match="who made it"):
        curate(built, credit="   ", into=tmp_path / "shelf")


def test_curation_refuses_an_import_that_kept_no_pictures(tmp_path: Path) -> None:
    from targum.video.curate import curate

    built = tmp_path / "built"
    (built / "translations").mkdir(parents=True)
    Document(source="talk.mp3", title="A Talk", language="he", blocks=[]).write(
        built / "document.json"
    )
    manifest_module.write(
        built,
        manifest_module.AudioManifest(
            source="talk.mp3",
            sha256="x",
            duration=10.0,
            language="he",
            parts=[manifest_module.ManifestPart(number=1, start=0.0, end=10.0, audio="a.mp3")],
        ),
    )
    with pytest.raises(TargumError, match="kept no pictures"):
        curate(built, credit="Somebody", into=tmp_path / "shelf")


def test_curation_carries_the_text_the_english_and_the_files(tmp_path: Path) -> None:
    """And rewrites exactly one thing: the source. The body is untouched, so the content
    hash and every segment id hung off it survive the move — which is what lets the
    shipped spans and the shipped English go on fitting a document re-segmented on the
    box."""
    from targum.video.curate import curate

    built = tmp_path / "built"
    (built / "audio" / "parts").mkdir(parents=True)
    (built / "translations").mkdir(parents=True)
    (built / "audio" / "parts" / "part-001.mp3").write_bytes(b"ID3sound")
    (built / "audio" / "parts" / "part-001.mp4").write_bytes(b"ftypmp42film")
    document = Document(
        source="/somewhere/on/a/laptop/source.mp4",
        title="A Talk",
        language="he",
        blocks=[],
    )
    document.content_hash = document.recompute_hash()
    document.write(built / "document.json")
    Translation(
        name="English (machine, natural)",
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="anthropic",
        segments={"0000.000-aaa": "peace"},
    ).write(built / "translations" / "anthropic.natural.en.json")
    manifest_module.write(
        built,
        manifest_module.AudioManifest(
            source="source.mp4",
            home="https://youtu.be/abc123",
            sha256="x",
            duration=10.0,
            language="he",
            parts=[
                manifest_module.ManifestPart(
                    number=1,
                    start=0.0,
                    end=10.0,
                    audio="audio/parts/part-001.mp3",
                    video="audio/parts/part-001.mp4",
                )
            ],
        ),
    )

    folder = curate(
        built,
        credit="Khan Academy Hebrew",
        licence="CC BY 3.0",
        licence_url="https://creativecommons.org/licenses/by/3.0/",
        into=tmp_path / "shelf",
    )
    assert folder.name == "abc123", "filed under the video's own id, from any spelling"
    carried = Document.model_validate_json((folder / store.DOCUMENT).read_text(encoding="utf-8"))
    assert carried.source == "video:abc123"
    assert carried.content_hash == document.content_hash, "the body did not move"
    assert (folder / "audio" / "parts" / "part-001.mp4").read_bytes() == b"ftypmp42film"
    held = json.loads((folder / store.CURATED).read_text(encoding="utf-8"))
    # One canonical shape whatever the curation was handed, because the page's one
    # outbound address is the prefix `test_render.OUTBOUND` pins.
    assert held["home"] == "https://www.youtube.com/watch?v=abc123"
    assert held["credit"] == "Khan Academy Hebrew"


def test_the_server_prices_a_curated_video_at_nothing_with_no_key(
    shelf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same gate the command line has, in the place a reader actually meets it.

    Without a key the estimate falls back to a character count, so the page would quote a
    plausible price, take the click and only then fail — which is why the block exists.
    It must not fire for a text whose English shipped with it: a box that has lost its
    key should still hand a reader the whole shelf that costs nothing.
    """
    from targum.serve import Job, Library

    shelve(shelf)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    library = Library(tmp_path / "out")
    job = Job(id="t1", source="video:abc123")
    library.prepare(job)

    assert job.error == ""
    assert job.blocked == ""
    assert job.stage == "ready"
    assert job.estimate == 0.0
