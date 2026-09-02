"""Turning artifacts into readable HTML.

The output is split into sections rather than written as one file. A full-length book
with several translations and, later, per-token annotation runs to tens of megabytes,
and a phone browser will not open it. Splitting is decided here, at the top of the
renderer, because it is not something that can be added later without a rewrite.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:  # imported for types only; the real import is inside each function,
    from ..catalogue import Entry  # because catalogue imports nothing from here
    from ..weekly.models import Issue as WeeklyIssue
    from ..weekly.models import Level as WeeklyLevel
from markupsafe import Markup, escape

from ..annotate.base import BAND_NAMES, KIND_COLUMN, method_label
from ..models import (
    Annotation,
    BlockKind,
    Document,
    Glossary,
    Segment,
    SegmentedDocument,
    Translation,
    Vocalization,
    direction_for,
    is_biblical,
)
from ..translate.prompts import language_name
from ..vocalize import has_taamim, map_span, strip_nikkud, strip_taamim

# A section beyond this many segments is split again. Sized so a section stays under a
# megabyte once M4 adds per-token annotation.
MAX_SEGMENTS_PER_SECTION = 400

TEMPLATES = Path(__file__).parent / "templates"
ASSETS = Path(__file__).parent / "assets"

# A run keeps its interior spaces, so "Magma Devs" isolates as one name rather than
# two words with a gap the bidi algorithm is free to reorder.
# The en dash is in the run: a range — a clock's 0:00–10:58, a year's 1897–1948 — is
# one thing to say, and split at the dash its halves are two isolates an RTL paragraph
# reorders, so every range read backwards.
_LATIN_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,:/'’&–-]*[A-Za-z0-9]|[A-Za-z0-9]")
_RTL_RUN = re.compile(r"[֐-׿؀-ۿ][֐-ۿ\s.,'\"־-]*[֐-׿؀-ۿ]|[֐-׿]")


@dataclass(slots=True)
class Section:
    number: int
    title: str
    segment_ids: list[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return f"sec-{self.number:04d}.html"


#: The address on the end of a ref: the "2:1" of "Ruth 2:1", the "1:3" of "Mishnah
#: Berakhot 1:3". Chapter and verse is how every learner of a Biblical text locates a
#: line, so it is the one part of a ref a link is allowed to name.
_VERSE_ADDRESS = re.compile(r"(?:^|\s)(\d+):(\d+)$")


def verse_address(ref: str) -> str:
    """The "2:1" of "Ruth 2:1", or nothing where a ref does not end in one.

    Nothing rather than a guess: an imported recording's `:waiting` part, or a prose
    block with no ref at all, is not a place a link can point to, and a number drawn
    beside it would be a number that meant nothing.
    """
    found = _VERSE_ADDRESS.search(ref.strip())
    return f"{found[1]}:{found[2]}" if found else ""


def isolate(text: str, direction: str) -> Markup:
    """Wrap opposite-direction runs in <bdi>.

    Without this, a year or a Latin name inside a Hebrew sentence drags its punctuation
    to the wrong end of the line. The browser's own bidi algorithm is correct and still
    produces this, because it has no way to know where the embedded run ends.
    """
    pattern = _LATIN_RUN if direction == "rtl" else _RTL_RUN
    parts: list[str] = []
    position = 0
    for match in pattern.finditer(text):
        parts.append(str(escape(text[position : match.start()])))
        parts.append(f"<bdi>{escape(match.group())}</bdi>")
        position = match.end()
    parts.append(str(escape(text[position:])))
    return Markup("".join(parts))


def embed_json(payload: object) -> Markup:
    r"""JSON safe to sit inside a <script> element.

    The HTML parser ends the element at the first "</script" it meets, even inside a
    JSON string, so a translation containing that sequence would break out into
    markup. Splitting every "</" across an escape closes the door; "<\/" is the same
    string once JSON-decoded.
    """
    return Markup(json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))


def split_sections(segmented: SegmentedDocument) -> list[Section]:
    """Break at top-level headings, then on length."""
    sections: list[Section] = []
    current: Section | None = None
    has_body = False

    # A heading only opens a new section once the current one holds actual prose.
    # Otherwise a title, or a title and byline, would each become a section of its own.
    front_matter = {BlockKind.heading, BlockKind.byline}

    for segment in segmented.segments:
        starts_section = (
            segment.kind is BlockKind.heading
            and (segment.level or 1) <= 2
            and current is not None
            and has_body
        )
        too_long = current is not None and len(current.segment_ids) >= MAX_SEGMENTS_PER_SECTION
        if current is None or starts_section or too_long:
            title = segment.text if segment.kind is BlockKind.heading else ""
            current = Section(number=len(sections) + 1, title=title)
            sections.append(current)
            has_body = False
        has_body = has_body or segment.kind not in front_matter
        if not current.title and segment.kind is BlockKind.heading:
            current.title = segment.text
        current.segment_ids.append(segment.id)

    for section in sections:
        if not section.title:
            section.title = f"Section {section.number}"
    return sections


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        # Unconditionally, not select_autoescape: that helper matches on the final
        # extension, and these templates end in .j2, so it silently escaped nothing.
        # Every template renders text that can come from a fetched web page.
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["isolate"] = isolate
    env.globals["asset"] = _asset
    env.globals["data_uri"] = _data_uri
    env.globals["hebrew_face"] = _hebrew_face
    env.globals["legal_is_public"] = legal_is_public
    return env


def _strip(name: str, text: str) -> str:
    """An asset with its comments taken out, for baking into a page.

    The comments in these files are for whoever reads them here, and a reader carries
    its whole stylesheet and script inlined — so every one of them is paid for again on
    every page, and a book of 151 chapters is 151 copies. Across the set they are 30% of
    what gets baked in: 129 kB a page before compression, and near a megabyte on disk
    per book. The source keeps them; the page does not need them.

    Whole lines only, and nothing is ever joined. Two things follow from that, and both
    are the reason this is thirty lines rather than a dependency:

    * A comment that opens a line cannot be inside a string, because no asset carries a
      template literal that spans a line — `test_render.py` holds that to be true rather
      than trusting it, since the day one appears this would quietly eat it.
    * Because every removal takes a whole line, nothing that stood on two lines ends up
      on one, so JavaScript's semicolon insertion sees exactly what it saw before.

    Trailing comments are left alone. Telling `//` in code from `//` inside a string or
    a regular expression needs a parser, and there are 78 bytes of them in the whole set.
    """
    js = name.endswith(".js")
    kept: list[str] = []
    inside = False
    for line in text.splitlines():
        bare = line.strip()
        if inside:
            if "*/" not in bare:
                continue
            inside = False
            rest = line.split("*/", 1)[1]
            if rest.strip():
                kept.append(rest)
            continue
        if not bare:
            continue
        if js and bare.startswith("//"):
            continue
        if bare.startswith("/*"):
            head = line.split("/*", 1)[1]
            if "*/" not in head:
                inside = True
                continue
            rest = head.split("*/", 1)[1]
            if rest.strip():
                kept.append(rest)
            continue
        kept.append(line)
    if inside:
        # Loud, because the alternative is a page missing the second half of its script.
        raise ValueError(f"{name}: a block comment is never closed")
    return "\n".join(kept) + "\n"


@cache
def _asset(name: str) -> Markup:
    """One stylesheet or script, ready to bake in.

    Cached like `_data_uri` and for the same reason: the same two files are asked for on
    every page of every section, and rewriting a book asks 151 times. The cost is that a
    running `targum serve` reads each asset once — editing one while it is up needs a
    restart to see it.
    """
    return Markup(_strip(name, (ASSETS / name).read_text(encoding="utf-8")))


# The Hebrew faces, one per register, and why they are in the page rather than named.
#
# The stack asked for "Frank Ruhl CLM" and "Taamey Frank CLM" and never got either: they
# are not on a stock machine, so every reader fell through to New Peninim MT — which has
# no accents at all, nor meteg, paseq, sof pasuq or qamats qatan. That was invisible while
# the Tanakh arrived stripped of its accents. The moment it did not, every letter carrying
# one was borrowed from whatever font the browser could find, and Safari substitutes the
# whole cluster, so the letter changed size too. A font a page merely asks for is a font
# some readers do not have; the only fix is to carry it.
#
# Two faces because the shelves read differently: Taamey Frank CLM is cut for pointed and
# accented scripture, and its accents are designed rather than tolerated — and its letters
# hold one size, which Taamey Ashkenaz beside it in the same collection does not: its shin,
# mem and final mem draw visibly larger than their neighbours, which on a page of verses
# reads as broken text. Frank Ruhl Libre
# is a modern cut of the Hebrew book serif, for a newspaper — and a serif, so a Hebrew
# column and the Latin one beside it still read as one document, which is what §5 asks.
# Taamey Frank CLM is Yoram Gnat's, GPL with the font-embedding exception that says a
# document carrying the font is not itself covered — which is exactly what a reader is.
# Frank Ruhl Libre is OFL, which permits the same thing outright. The exception is per
# author and not per project: Taamey David CLM sits in the same collection and does not
# carry it, because its glyphs are Maxim Iorsh's. Check before swapping either of these.
BIBLICAL_FACE = ("Taamey Frank CLM", "fonts/TaameyFrankCLM-Medium.woff2")
MODERN_FACE = ("Frank Ruhl Libre", "fonts/FrankRuhlLibre-Regular.woff2")

# What a page falls back through if it somehow carries no face of its own. Kept in step
# with `--reading-hebrew` in reader.css.
_FALLBACK = '"Taamey Frank CLM", "Frank Ruhl CLM", "SBL Hebrew", "New Peninim MT", David, serif'


@cache
def _hebrew_face(biblical: bool = False) -> Markup:
    """The page's own Hebrew face, carried rather than hoped for.

    Emitted per page instead of from the stylesheet because a page needs one of the two
    and paying for both would double the cost of the thing for no reader's benefit.
    """
    # `block`, not `swap`: the face is in the page, so there is nothing to wait for and
    # nothing to gain from painting a fallback first — and a fallback that is painted is
    # a fallback the page gets measured in. reader.js measures again when the font
    # arrives; this is what keeps there being nothing to measure twice.
    family, file = BIBLICAL_FACE if biblical else MODERN_FACE
    return Markup(
        "<style>"
        f'@font-face{{font-family:"{family}";'
        f'src:url({_data_uri(file)}) format("woff2");font-display:block}}'
        f':root{{--reading-hebrew:"{family}", {_FALLBACK}}}'
        "</style>"
    )


@cache
def _data_uri(name: str) -> str:
    """An asset as a `data:` URI, for the places only a URL will do.

    A built reader is one file in a folder of its own — there is nowhere to put a
    sibling icon and nothing serving it, so the icons ride inside the page. They are
    small enough (the whole set is under 3 kB) not to matter beside the inlined CSS.
    Cached because the same three icons are asked for on every page of every section.
    """
    path = ASSETS / name
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime == "image/svg+xml":
        mime += ";charset=utf-8"
    # Not every machine's mimetypes knows woff2, and a font served as octet-stream is a
    # font some browsers decline to use.
    if path.suffix == ".woff2":
        mime = "font/woff2"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


class Spoken(NamedTuple):
    """The sound of one section: who says each line, where each line is, and the file.

    `credit` and `licence` are not decoration. A dialogue is ours and needs neither; a
    recording is somebody else's reading, used under a licence that requires them to be
    named, and the page carries the naming because a credit kept in a spreadsheet is one
    the person listening never sees.
    """

    speakers: dict[str, str]
    spans: dict[str, list[float]]
    audio: str
    credit: str = ""
    licence: str = ""
    licence_url: str = ""
    #: What the page calls this sound, in the one place a reader reads it: "Listen to the
    #: scene", "play the reading". A dialogue is a scene and a recorded book is a reading,
    #: and calling a chapter of Ruth a scene is the kind of wrong word a reader notices
    #: and nothing else does.
    label: str = "the scene"
    #: Per segment, each written word's clock — [charStart, charEnd, start, end] — for
    #: the card's own ear. Everywhere else the card simply offers no sound, the way the
    #: phrase chip asks only where the page can.
    #:
    #: Only `_imported` and `_read_along` fill this, and not because the other branches
    #: forgot: a word clock exists only where something timed the audio word by word.
    #: ASR returns word timings for an upload, and `recording.attach` runs the forced
    #: aligner over a LibriVox reading. Scripture was attached verse by verse and no
    #: word-level pass was ever run over it, a dialogue's turns come back from the voice
    #: with turn boundaries and nothing finer, and the weekly is read straight through.
    #: So `_read_aloud`, `_scene` and `_read_through` have nothing to put here, and
    #: passing them an empty dict would be the same silence spelled longer. Giving the
    #: library's readers a card that speaks is a data pass, not an argument.
    words: dict[str, list[list[float]]] = {}
    #: The part's video cut on disk, or "". Never a data URI: the one file too heavy to
    #: inline rides beside the reader instead — `render()` copies it and writes the
    #: relative address the page carries.
    video: str = ""


SILENT = Spoken({}, {}, "")


def _inlined(path: Path) -> str:
    """An audio file as a data URI, or "" where it is not there.

    In the page rather than beside it, because a reader fetches nothing — the rule that
    decides the fonts and the icons decides this too.
    """
    if not path.exists():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _scene(document: Document, segments: list[Segment]) -> Spoken:
    """A dialogue: written here, voiced here, so the audio and the text are one thing."""
    from ..dialogue import index as dialogue_index

    try:
        scene = dialogue_index.load(document.source.split(":", 1)[1])
    except Exception:  # noqa: BLE001 - a missing scene must not stop a rebuild
        return SILENT
    by_block = {f"b{n:04d}": turn for n, turn in enumerate(scene.turns)}
    speakers: dict[str, str] = {}
    spans: dict[str, list[float]] = {}
    for segment in segments:
        turn = by_block.get(segment.block_id)
        if turn is None:
            continue
        speakers[segment.id] = getattr(scene.cast, turn.who).name or turn.who
        # Asked of the two values rather than through `Turn.voiced`, which says the same
        # thing and says it in a way a type checker cannot follow into the list below.
        if turn.start is not None and turn.end is not None:
            spans[segment.id] = [turn.start, turn.end]
    audio = _inlined(dialogue_index.root() / scene.audio) if scene.audio and spans else ""
    return Spoken(speakers, spans, audio)


def _read_aloud(document: Document, segments: list[Segment]) -> Spoken:
    """A recording of scripture, found by ref and never by position.

    The section decides which part of the recording it wants by naming the verses it
    holds. A reader built for one chapter, for a range, or for a whole book all ask the
    same question and all get the right answer — where a positional rule would hand a
    reader of Job 3 the sound of Job 1 and say nothing.
    """
    from ..recording import index as recording_index

    recording = recording_index.load(document.source)
    if recording is None:
        return SILENT
    part = recording.part_for([segment.ref for segment in segments])
    if part is None:
        return SILENT
    spans = {
        segment.id: list(part.spans[segment.ref])
        for segment in segments
        if segment.ref and segment.ref in part.spans
    }
    if not spans:
        return SILENT
    audio = _inlined(recording_index.folder(document.source) / part.audio)
    if not audio:
        return SILENT
    return Spoken(
        {},
        spans,
        audio,
        recording.credit,
        recording.licence,
        recording.licence_url,
        "the reading",
    )


def _read_along(document: Document, segments: list[Segment]) -> Spoken:
    """A recording of prose, following along line by line.

    Prose has no refs, so the section finds its part by the blocks it holds, and the
    spans are derived here at every build from the word timings the attach wrote down —
    the words and their clocks do not move, and everything keyed to them can. A section
    that straddles two files keeps the file it starts in; its last lines go without a
    control rather than pointing at sound the page is not carrying.
    """
    from ..audio.spans import spans_for, word_spans_for
    from ..recording import index as recording_index
    from ..transcribe.models import Word

    recording = recording_index.load(document.source)
    if recording is None:
        return SILENT
    part = recording.part_reading([segment.block_index for segment in segments])
    if part is None or not part.words:
        return SILENT
    home = recording_index.folder(document.source)
    try:
        rows = json.loads((home / part.words).read_text(encoding="utf-8"))
        words = [
            Word(text=str(text), start=float(start), end=float(end), confidence=float(score))
            for text, start, end, score in rows
        ]
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        # A words file that cannot be read is a section without sound, the same answer
        # as a missing file or a wrong slug — rows of the wrong shape included, or one
        # bad file aborts the build of a text that reads fine in silence.
        return SILENT
    mine = [
        segment
        for segment in segments
        if len(part.blocks) == 2 and part.blocks[0] <= segment.block_index <= part.blocks[1]
    ]
    spans = spans_for(mine, words)
    if not spans:
        return SILENT
    audio = _inlined(home / part.audio)
    if not audio:
        return SILENT
    return Spoken(
        {},
        spans,
        audio,
        recording.credit,
        recording.licence,
        recording.licence_url,
        "the reading",
        word_spans_for(mine, words),
    )


def _read_through(document: Document) -> Spoken:
    """A recording of prose, played straight through.

    No spans, and that is the point. A dialogue is turns and scripture is verses, and both
    are addressed unit by unit because both are read that way. An article is not: it is
    read from the top, and cutting it into sentences so a highlight can crawl down it
    would be answering a question nobody asked of prose.

    So the player plays and the text stays still. Everything else works — pausing where it
    stands, the clock, saving the file — because none of that ever needed a span.
    """
    from ..recording import index as recording_index

    recording = recording_index.load(document.source)
    if recording is None or not recording.parts:
        return SILENT
    part = recording.parts[0]
    audio = _inlined(recording_index.folder(document.source) / part.audio)
    if not audio:
        return SILENT
    return Spoken(
        {}, {}, audio, recording.credit, recording.licence, recording.licence_url, "the reading"
    )


def _imported(folder: Path, segments: list[Segment]) -> Spoken:
    """A recording somebody brought, found by the manifest beside the reader.

    No credit line and no licence link: the file is the reader's own, and a licence
    targum cannot verify is one it must not print. The artist tag became the byline at
    ingest, which is where a name a page can stand behind belongs.
    """
    from ..audio import manifest as manifest_module

    kept = manifest_module.load(folder)
    if kept is None:
        return SILENT
    part = kept.part_for([segment.id for segment in segments])
    if part is None or not part.audio:
        return SILENT
    spans = {
        segment.id: list(part.spans[segment.id]) for segment in segments if segment.id in part.spans
    }
    if not spans:
        return SILENT
    audio = _inlined(folder / part.audio)
    if not audio:
        return SILENT
    speakers = {
        segment.id: part.speakers[segment.id] for segment in segments if segment.id in part.speakers
    }
    word_clocks = {
        segment.id: [list(row) for row in part.words[segment.id]]
        for segment in segments
        if segment.id in part.words
    }
    reel = folder / part.video if part.video else None
    return Spoken(
        speakers,
        spans,
        audio,
        "",
        "",
        "",
        "the recording",
        word_clocks,
        str(reel) if reel is not None and reel.is_file() else "",
    )


def speech(document: Document, segments: list[Segment], folder: Path | None = None) -> Spoken:
    """Where in the audio each line of this section is said, and the audio itself.

    The spans are per line and the reader plays a slice of one file rather than fetching
    a clip for each — a folder of small files is not a thing a one-file reader can carry,
    and a reader fetches nothing.

    A line whose span is missing is simply left without a control. That is the same rule
    the rest of the build follows: a gap a reader can see past beats a button that lies.

    `folder` is the targum's own directory. An imported recording lives inside it and is
    found by the manifest beside the reader — asked of the disk, like `spoken.sources()`,
    but per text and per build, so new audio needs no restart to be seen.
    """
    from ..audio import manifest as manifest_module

    if folder is not None and (folder / manifest_module.MANIFEST).is_file():
        return _imported(folder, segments)
    if document.source.startswith("dialogue:"):
        return _scene(document, segments)
    if is_biblical(document.source):
        return _read_aloud(document, segments)
    if document.source.startswith("weekly:"):
        return _read_through(document)
    return _read_along(document, segments)


def _this_week() -> dict[str, Any] | None:
    """The newest readable issue of the weekly, as Learn needs it."""
    from ..weekly import index as weekly
    from ..weekly.models import LEVELS, folder

    issue = next(iter(weekly.readable()), None)
    if issue is None:
        return None
    return {
        "id": issue.id,
        "dated": issue.dated,
        "title": issue.title,
        "levels": [
            {
                "level": edition.level.value,
                "name": LEVELS[edition.level].name,
                "figure": LEVELS[edition.level].figure,
                "written_for": LEVELS[edition.level].written_for,
                "folder": folder(issue.id, edition.level),
            }
            for edition in issue.editions
        ],
    }


def next_after(document: Document) -> dict[str, str]:
    """What to read after this one, decided when the reader is written.

    A reader fetches nothing, so it cannot ask a library what else there is — the answer
    is baked in. That means it is the same suggestion for everybody, which rules out the
    one the learn page makes: that one is measured against a reader's own marked words,
    and this one can only know what is true of the texts themselves.

    So: the next step up. The nearest text harder than this one, in the same Hebrew,
    because somebody who has just finished a dialogue is not looking for Psalms — and the
    shorter of two at the same difficulty, because the step should be one thing at a time.
    """
    from ..catalogue import CATALOGUE, scene_number

    mine = next((entry for entry in CATALOGUE if entry.source == document.source), None)
    # A scene is one of a numbered sequence, and after scene 3 comes scene 4 — not the
    # nearest harder text, whose measured share is noise at twenty words. Past the last
    # scene the step-up below takes over.
    if mine is not None and scene_number(mine.id):
        following = next(
            (e for e in CATALOGUE if scene_number(e.id) == scene_number(mine.id) + 1), None
        )
        if following is not None:
            return {
                "id": following.id,
                "title": following.title,
                "english": following.english,
                "blurb": following.blurb,
                "minutes": str(following.minutes),
                "scene": f"Scene {scene_number(following.id)}",
            }
    here = mine.difficulty if mine else 0
    rest = [
        entry
        for entry in CATALOGUE
        if entry.language == document.language
        and entry.difficulty > 0
        and (mine is None or entry.id != mine.id)
    ]
    if not rest:
        return {}
    # Same register first. Falling back to any of them is better than offering nothing,
    # but a learner reading modern Hebrew should not be handed scripture by arithmetic.
    same = [entry for entry in rest if mine is not None and entry.register is mine.register]
    for pool in (same, rest):
        harder = [entry for entry in pool if entry.difficulty > here]
        if harder:
            pick = min(harder, key=lambda entry: (entry.difficulty, entry.words))
            break
    else:
        pick = min(rest, key=lambda entry: (abs(entry.difficulty - here), entry.words))
    return {
        "id": pick.id,
        "title": pick.title,
        "english": pick.english,
        "blurb": pick.blurb,
        "minutes": str(pick.minutes),
        "scene": "",
    }


def learn_page(token: str) -> str:
    """The page you land on: carry on, what you have, what you know.

    In that order on purpose. Most visits are somebody returning to a text rather than
    looking for a new one, and the brand rule is that the reader is a reader rather than
    a player — so the numbers sit under the thing you came to do, not over it.

    Nothing about the reader is baked in. The shelf comes from `/readers` and the words
    from the browser's own stores, which is what lets one rendered page serve everybody.
    """
    from ..catalogue import everything
    from ..translate.prompts import OFFERED, language_name

    return (
        _environment()
        .get_template("learn.html.j2")
        .render(
            token=token,
            languages=[(code, language_name(code)) for code in OFFERED],
            # The week's issue, if there is a readable one. Learn is the only surface
            # that knows who is reading, so it is the only one that can open the digest
            # at the reader's own rung rather than asking them to pick a level — see
            # `charts.levelFor`. Absent where no issue has been published and built.
            weekly=_this_week(),
            # Enough of the catalogue to suggest the next thing to read and then to
            # build it: a title and a line about it, the two numbers that say whether it
            # is the right size and the right difficulty for this reader, and what a
            # build is started from. The last two are here because the suggestion is
            # taken up on this page — it used to be a link to the catalogue, and a page
            # that can only point at a text has to send the reader somewhere to act.
            #
            # Sources rather than whole translation records: `/prepare` wants a list of
            # them and the page has no use for a publisher or a licence it never shows.
            catalogue=[
                {
                    "id": entry.id,
                    "title": entry.title,
                    "english": entry.english,
                    "language": entry.language,
                    "blurb": entry.blurb,
                    "difficulty": entry.difficulty,
                    "minutes": entry.minutes,
                    "source": entry.source,
                    "translations": [t.source for t in entry.translations],
                }
                for entry in everything()
            ],
        )
    )


#: What each of the three list pages is called, in the order Learn shows them. The route
#: names are code — "texts" rather than "targums" — and the heading is the copy.
LISTS = {"texts": "Your targums", "words": "Your Words", "phrases": "Your Phrases"}


def list_page(token: str, which: str) -> str:
    """One of Learn's three lists, whole.

    Learn caps every list it draws, because a page somebody lands on with four hundred
    rows on it is not a landing page. This is where the rest of a list is, and it is the
    same template three times rather than three templates: the difference between them is
    which section is rendered, and nothing else.
    """
    from ..translate.prompts import OFFERED, language_name

    if which not in LISTS:
        raise KeyError(which)
    return (
        _environment()
        .get_template("yours.html.j2")
        .render(
            token=token,
            which=which,
            heading=LISTS[which],
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


def add_page(token: str, no_key: str = "") -> str:
    """Bringing a text targum does not have.

    No longer the page anybody lands on — Learn is — so it introduces nothing and says
    what it is for. It is still the only place in the product with a file input, a free
    source field, a choice of language pair, and a price shown before anything is spent.

    `no_key` is the notice to show when nothing can be translated. It is passed in rather
    than worked out here, so the page states the same thing the builder would have
    refused with — and it matters more here than it used to, this now being the only page
    that spends anything.
    """
    from ..translate.prompts import INTO, OFFERED, READING, language_name

    return (
        _environment()
        .get_template("add.html.j2")
        .render(
            token=token,
            # What an upload may be, and what it may become. Narrower than `languages`
            # below, which is every language the rest of the app knows how to show.
            reading=_staged(READING),
            into=_staged(INTO),
            no_key=no_key,
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


def _staged(pairs: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    """A language list with its stage beside each, for a page to draw a picker from."""
    from ..translate.prompts import language_name, stage_label

    return [
        {"code": code, "name": language_name(code), "stage": stage, "label": stage_label(stage)}
        for code, stage in pairs
    ]


def about_page() -> str:
    """That targum is under construction, and how much has landed lately.

    Nothing here is written by hand: the count and the calendar both come from `git
    log`, and the rest of what this page used to say is on GitHub.
    """
    from ..about import DAYS, work

    def level(count: int, busiest: int) -> int:
        """Which of five shades a day gets. Zero stays zero rather than rounding up."""
        if not count or not busiest:
            return 0
        return min(4, 1 + int(3 * (count - 1) / max(1, busiest - 1)))

    return _environment().get_template("about.html.j2").render(work=work(), days=DAYS, level=level)


def holding_page() -> str:
    """What a stranger sees while the product is not open yet.

    Deliberately not the sign-in page: that is a door, and a door presented to somebody
    with no key is a wall that looks like a mistake. This says where things are, and
    keeps the door in the corner for the people who have one.
    """
    return _environment().get_template("holding.html.j2").render()


#: The date the four legal pages say they were last changed on. One line rather than
#: four, because the date is the sentence on those pages nobody would notice going stale.
LEGAL_CHANGED = "29 August 2026"

#: The four pages A7 owes a reader about their own data, and what a search engine is told
#: each one is. Keyed on the route so `serve` dispatches from this rather than from a
#: second list that would drift away from it.
LEGAL = {
    "privacy": (
        "Privacy Notice — targum",
        "The controller, the categories of personal data processed and the legal basis "
        "for each, the recipients, the transfers and the rights of the data subject.",
    ),
    "terms": (
        "Terms of Service — targum",
        "The terms governing access to and use of targum: accounts, user content, "
        "intellectual property, notice of infringement, and limitation of liability.",
    ),
    "retention": (
        "Data Retention Schedule — targum",
        "The period for which each category of personal data is retained, and the "
        "criteria where no fixed period applies.",
    ),
    "deletion": (
        "Erasure and Account Closure — targum",
        "The procedure for deleting a targum or closing an account, and the consequences of each.",
    ),
}


def legal_is_public() -> bool:
    """Whether the four legal documents are reachable. Off unless the deployment says so.

    Shut for the alpha the same way the catalogue is shut, and for the same reason it is
    written that way there: built, tested, and deliberately not open yet. Shut means shut
    all the way — the routes answer 404, nothing links to them, and neither robots nor
    the sitemap mentions them. `TARGUM_PUBLIC_LEGAL=1` opens them, which is the switch to
    throw at beta.

    Worth knowing while the switch is off: the documents describe processing that is
    happening now, to an account that exists now. Article 13 wants the notice available
    where the address is collected, and while this is off it is not. That is a decision
    rather than an oversight — David's, taken on 2026-08-30 with the position stated —
    and it stops being one the moment somebody who is not him signs up.
    """
    return os.environ.get("TARGUM_PUBLIC_LEGAL", "").strip().lower() in {"1", "true", "yes"}


def legal_page(which: str, address: str = "") -> str:
    """One of the four pages the alpha owes a reader about their own data.

    One template with four states rather than four files, which is the shape
    `signin_page` already uses: they differ in prose and in nothing else, and the three
    hand-written copies of the public footer are what four files cost.
    """
    title, description = LEGAL[which]
    return (
        _environment()
        .get_template("legal.html.j2")
        .render(
            which=which,
            title=title,
            description=description,
            canonical=f"{address}/{which}" if address else "",
            changed=LEGAL_CHANGED,
        )
    )


def signin_page(*, landing: str = "", token: str = "", expired: bool = False) -> str:
    """The door. Three states, one template.

    Empty is the sign-in form. `landing` is the page an emailed link opens, naming the
    account it would sign in without having spent anything to find out. `expired` is
    what a link that has been used or has aged out arrives at, which is a normal thing
    to hit rather than an error.
    """
    return (
        _environment()
        .get_template("signin.html.j2")
        .render(landing=landing, token=token, expired=expired)
    )


def progress_page(token: str) -> str:
    """Everything kept, with what it adds up to.

    Built from the browser's own store like the start page, because that is where a
    word list lives; the server only hands over the page.
    """
    from ..translate.prompts import OFFERED

    return (
        _environment()
        .get_template("progress.html.j2")
        .render(
            token=token,
            languages=[(code, language_name(code)) for code in OFFERED],
            # The week's issue, if there is a readable one. Learn is the only surface
            # that knows who is reading, so it is the only one that can open the digest
            # at the reader's own rung rather than asking them to pick a level — see
            # `charts.levelFor`. Absent where no issue has been published and built.
            weekly=_this_week(),
        )
    )


#: One catalogue, one name for it. There were two — a Library and a Beit Midrash — and
#: the split made the Tanakh harder to find rather than easier to avoid. What the Beit
#: Midrash was for is now a tag on the entries themselves.
#: What each level of the weekly is, for somebody choosing one before they can read any
#: of it. Short, second person, and about the Hebrew rather than about the reader: a
#: level named after the person reading it grades them, which the voice rules refuse.
WEEKLY_LEVELS: dict[str, str] = {
    "aleph": (
        "Short sentences, one clause each, present and past. Every place and person "
        "is said in a few words the first time it appears."
    ),
    "bet": (
        "Ordinary reporting: subordinate clauses, past and future, the register a "
        "news site writes in when it is not trying to be difficult."
    ),
    "gimel": (
        "Unsimplified. Officialese inside quotation marks, idiom, and the "
        "constructions a paper actually uses. The week's biggest story runs at length."
    ),
}


SHELF = (
    "Library",
    "Hebrew — Tanakh, novels, essays and speeches — each with a translation beside it, "
    "sentence by sentence.",
)


def shelf_page(address: str = "") -> str:
    """The catalogue, for somebody who has not signed in.

    Public on purpose. It is the shop window, and until it exists there is nothing for a
    search engine to find but a page saying "Coming soon".
    """
    from ..catalogue import everything

    name, blurb = SHELF
    return (
        _environment()
        .get_template("shelf.html.j2")
        .render(
            title=f"{name} — targum",
            description=blurb,
            canonical=f"{address}/library" if address else "",
            shelf_name=name,
            shelf_blurb=blurb,
            entries=everything(),
        )
    )


def text_schema(entry: Entry, address: str = "") -> dict[str, Any]:
    """What a text page is about, in the vocabulary a search engine reads.

    Every one of these pages carries a title, a byline, a translator and two lines of the
    text itself, and until now said none of it in a form a machine could read — so four
    hundred pages about four hundred books looked like four hundred pages.

    **Nothing goes in here that the catalogue actually knows.** `author` is the trap: the
    field holds a person for the moderns and something else entirely for the rest —
    `Ketuvim · Ruth`, `משנה · סדר זרעים` — and writing those down as a Person would be
    telling a machine something untrue in order to fill a slot. A byline carrying `·` is
    a place, not a person, and is left out. What a text belongs to is said instead by
    `isPartOf`, off the collections, which is real structure rather than a guess at one.

    `inLanguage` is the source's, because that is what the work is in; the translation is
    named as a separate `workTranslation` rather than folded in, since who made it is the
    thing a reader of scripture decides on.
    """
    from ..catalogue import collection_of

    about: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Book",
        "name": entry.title,
        "inLanguage": entry.language,
    }
    if entry.english:
        about["alternateName"] = entry.english
    if entry.blurb:
        about["description"] = entry.blurb
    if entry.author and "·" not in entry.author:
        about["author"] = {"@type": "Person", "name": entry.author}
    if address:
        about["url"] = f"{address}/library/{entry.id}"
    holding = collection_of(entry.id)
    if holding is not None:
        about["isPartOf"] = {
            "@type": "Book",
            "name": holding.title,
            **({"alternateName": holding.english} if holding.english else {}),
        }
    if entry.translations:
        about["workTranslation"] = [
            {
                "@type": "Book",
                "name": rendering.name,
                "inLanguage": "en",
                **(
                    {"publisher": {"@type": "Organization", "name": rendering.publisher}}
                    if rendering.publisher
                    else {}
                ),
                **({"license": rendering.licence} if rendering.licence else {}),
            }
            for rendering in entry.translations
        ]
    return about


def text_page(entry: Entry, address: str = "") -> str:
    """One text, for somebody who has not signed in.

    A page about the text rather than about targum: whoever arrives here searched for the
    book, and the sample is the reason the page is worth indexing at all.
    """
    from ..models import direction_for

    name = SHELF[0]
    return (
        _environment()
        .get_template("text.html.j2")
        .render(
            title=f"{entry.title} — {name} — targum",
            description=entry.blurb,
            canonical=f"{address}/library/{entry.id}" if address else "",
            og_type="book",
            structured=text_schema(entry, address),
            entry=entry,
            shelf_name=name,
            direction=direction_for(entry.language),
            sample=entry.sample,
            minutes=max(1, round(entry.words / 130)),
        )
    )


# The outlets the weekly can show a wordmark for, keyed exactly as `weekly/sources.py`
# attributes stories. §12: third-party marks in their own colours, shown only for
# outlets the issue on the page actually cites. The wordmark SVGs in `assets/press/`
# are verifiably free (PD-textlogo); `assets/press/pages/` — the hero's front-page
# photographs — is different, and its README says how.
PRESS_MARKS = {
    "ynet": "press/ynet.svg",
    "walla": "press/walla.svg",
    "haaretz": "press/haaretz.svg",
    "globes": "press/globes.svg",
    "israel hayom": "press/hayom.svg",
    "maariv": "press/maariv.svg",
    "kan": "press/kan11.svg",
}


def _press(issue: WeeklyIssue) -> list[tuple[str, str]]:
    """The press line: every cited outlet that has a mark, busiest first.

    Derived from what the issue actually cites, so nothing on the hero claims a source
    the foot does not.
    """
    counts = Counter(
        outlet for story in issue.sources for outlet in story.outlets if outlet in PRESS_MARKS
    )
    return [(outlet, PRESS_MARKS[outlet]) for outlet, _ in counts.most_common()]


def weekly_page(
    issue: WeeklyIssue,
    level: WeeklyLevel,
    *,
    address: str = "",
    archive: list[WeeklyIssue] | None = None,
) -> str:
    """A landing page for the weekly, with the issue's own reader inside it.

    Everything it needs comes off the index. It used to read the composed markdown and
    parse it on every request, back when the page rendered the prose itself; the reader
    is framed now, so that was a file read and a markdown parse per visit for a value
    the template had stopped using — and it meant a box serving the weekly needed the
    source files as well as the built readers. It needs the readers and the index.
    """
    from ..weekly.entries import NOTICE
    from ..weekly.models import LEVELS
    from ..weekly.models import folder as weekly_folder

    spec = LEVELS[level]
    blurb = issue.blurb
    press = _press(issue)
    return (
        _environment()
        .get_template("weekly.html.j2")
        .render(
            title=f"{issue.title} — {spec.label} — targum",
            description=blurb,
            canonical=f"{address}/weekly/{issue.id}/{level.value}" if address else "",
            issue=issue,
            level=level,
            spec=spec,
            folder=weekly_folder(issue.id, level),
            levels=LEVELS,
            explained=WEEKLY_LEVELS,
            notice=NOTICE,
            shelf_name=SHELF[0],
            press=press,
            archive=[other for other in (archive or []) if other.id != issue.id],
        )
    )


def daily_page(
    cycle: Any,
    day: Any,
    *,
    nearby: list[Any] | None = None,
    others: list[tuple[Any, str]] | None = None,
    absent: list[tuple[str, str]] | None = None,
    opens: str = "index.html",
    is_today: bool = True,
    address: str = "",
) -> str:
    """One day of a learning cycle, with its own reader inside it.

    The parasha's page without the hero: a portion is a week and can carry a photograph,
    a day is a day, and somebody who came for today's two mishnayot came to read them.
    Everything it needs was decided at build time; what is left at serve time is a lookup.
    """
    return (
        _environment()
        .get_template("daily.html.j2")
        .render(
            title=f"{day.title} — {cycle.name} — targum",
            # The reference goes in the description because it is how somebody who keeps
            # the cycle recognises the day: "Kelim 28:2-3" says which one faster than any
            # sentence about it.
            description=(
                f"{cycle.name} for {day.hdate}: {day.title}. {cycle.blurb} "
                "The Hebrew pointed, a translation beside every line, and every word "
                "explained."
            ),
            canonical=f"{address}/{cycle.slug}" if address and is_today else "",
            og_type="article",
            cycle=cycle,
            day=day,
            nearby=nearby or [],
            others=others or [],
            absent=absent or [],
            opens=opens,
            is_today=is_today,
            translation_said=_translation_said(day),
        )
    )


def _translation_said(day: Any) -> str:
    """Who made the English on a daily page, in a sentence.

    Off the catalogue rather than written down here, so a page never credits an edition
    the shelf has since swapped.
    """
    from ..daily.cut import entry_for

    entry = entry_for(day.span.book) if getattr(day, "span", None) else None
    if entry is None or not entry.translations:
        return "a published translation"
    rendering = entry.translations[0]
    who = rendering.publisher or rendering.name
    return f"{rendering.name}" + (f", published by {who}" if rendering.publisher else "")


def parasha_page(
    portion: Any,
    *,
    schedule: Any,
    other: Any = None,
    diaspora: Any = None,
    israel: Any = None,
    listed: list[Any] | None = None,
    taamim: bool = True,
    shabbat: date | None = None,
    hdate: str = "",
    address: str = "",
) -> str:
    """This week's portion, with its own reader inside it.

    Everything it needs comes off the corpus index, the same way `weekly_page` reads the
    weekly's: the calendar ran at build time and what is left at serve time is a lookup.
    """
    said = shabbat.strftime("%A, %B %-d, %Y") if shabbat is not None else "Shabbat"
    return (
        _environment()
        .get_template("parasha.html.j2")
        .render(
            # The same correction the headline already carries, in the tag that matters
            # more for it: on a portion asked for by name this is not this week's, and
            # fifty-four titles claiming to be is fifty-four pages a search engine cannot
            # tell apart — on a page whose entire argument is that every parasha name is
            # a query. The chapter range is what a reader searching the name wants to see
            # confirmed, and it is different for all fifty-four.
            title=(
                f"{portion.name} — this week's parasha — targum"
                if shabbat is not None
                else f"{portion.name} — {portion.summary} — targum"
                if portion.summary
                else f"{portion.name} — the weekly Torah portion — targum"
            ),
            # The opening words go in the description because they are how somebody
            # who knows the portion recognises it — a search result that leads with
            # אתם נצבים says which reading this is faster than the chapter numbers do.
            description=(
                f"{portion.name} — {portion.opening} — {portion.summary}. The Hebrew with "
                "its chanting marks or without, a translation beside every verse, and "
                "every word explained."
            ).replace(" —  — ", " — "),
            canonical=f"{address}/parasha/{portion.slug}" if address else "",
            portion=portion,
            schedule=schedule,
            other=other,
            diaspora=diaspora,
            israel=israel,
            # Whether this is the page that means "this Shabbat". A named portion has no
            # week to compare schedules over.
            this_week=shabbat is not None,
            # The Hebrew date belongs to the Shabbat, not the portion — a portion falls
            # on a different one every year — so it arrives from the week's own record.
            hdate=hdate,
            listed=listed or [],
            taamim=taamim,
            shabbat_said=said,
            translation_said=(
                "the Metsudah linear translation, published under CC BY and matched to "
                "the Hebrew verse by verse on this machine"
            ),
        )
    )


def weekly_note(
    message: str,
    *,
    address: str = "",
    done: bool = True,
    pending: dict[str, str] | None = None,
) -> str:
    """A sentence back from the weekly's own door.

    Separate from `weekly_page` because these are read in a mail client, arrived at from
    a link, by somebody who has no account and may never have seen targum. Nothing here
    needs JavaScript and nothing here is behind anything.
    """
    return (
        _environment()
        .get_template("weekly-note.html.j2")
        .render(
            title="the weekly — targum",
            description="A weekly digest of the news in Modern Hebrew, at three levels.",
            canonical=f"{address}/weekly" if address else "",
            message=message,
            done=done,
            pending=pending,
        )
    )


def you_page(token: str) -> str:
    """Who you are, how you read, and the two things that end an account.

    Built like the other app pages: the server hands over the page and the browser asks
    who is looking. Nothing about a person is baked into it, so one page serves everyone
    and a signed-out visitor gets a sentence rather than an empty form. The languages
    are baked in: which exist is a fact about targum, not about the person.
    """
    from ..translate.prompts import INTO, READING, REQUIRED_LEARNING

    return (
        _environment()
        .get_template("you.html.j2")
        .render(
            token=token,
            reading=_staged(READING),
            into=_staged(INTO),
            required=list(REQUIRED_LEARNING),
        )
    )


def library_page(token: str) -> str:
    """Texts worth reading, and the ones you have already built.

    The catalogue is baked in rather than fetched: it is a handful of entries that
    ship with targum, and a page that has to ask the server for them would be a page
    that can be empty.
    """
    from ..catalogue import collections, everything
    from ..translate.prompts import OFFERED

    return (
        _environment()
        .get_template("library.html.j2")
        .render(
            token=token,
            catalogue=[entry.state() for entry in everything()],
            # Which texts the page meets as one thing. Baked in beside the catalogue and
            # for the same reason — and only the members actually on the shelf, so a
            # collection can never open onto a row that is not there.
            collections=[group.state() for group in collections()],
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


#: What a drawn cover may have been saved as, newest format first.
COVER_SUFFIXES = ((".webp", "image/webp"), (".png", "image/png"), (".jpg", "image/jpeg"))

#: How wide a cover rides on a chapter page. The contents page carries the whole 320px
#: tile once; a chapter page carries one on every page of a book, so it gets a smaller
#: one — a hundred and fifty psalms would otherwise add three megabytes to a reader for
#: an image the size of a thumbnail.
PLATE_WIDTH = 128


def cover_bytes(covers: Path | None, name: str) -> bytes | None:
    """A drawn cover, whatever it was saved as, or None where nobody has drawn one."""
    if covers is None or not name:
        return None
    for suffix, _ in COVER_SUFFIXES:
        found = covers / f"{name}{suffix}"
        if found.is_file():
            return found.read_bytes()
    return None


def cover_uri(covers: Path | None, name: str) -> str:
    """A cover as a `data:` URI, because a reader fetches nothing.

    The whole point of a built reader is that it is one file that works off a disk, on a
    plane, in an e-reader's browser. An image it had to go and get would be the first
    thing in it that could fail — so covers ride inside the page, the same way the icons
    already do.
    """
    raw = cover_bytes(covers, name)
    if raw is None:
        return ""
    return f"data:image/webp;base64,{base64.b64encode(raw).decode('ascii')}"


def plate_uri(covers: Path | None, name: str) -> str:
    """The same cover, small enough to sit on every page of a book.

    Kept beside the original once made, so a book of a hundred and fifty chapters shrinks
    one image rather than a hundred and fifty. Without Pillow there is no small one to
    make, and a chapter page simply goes without — the contents page still has the whole
    thing, and nothing looks broken.
    """
    if covers is None or not name:
        return ""
    small = covers / "small" / f"{name}.webp"
    if not small.is_file():
        raw = cover_bytes(covers, name)
        if raw is None:
            return ""
        try:
            from ..covers import shrink
        except ImportError:  # pragma: no cover - covers is a package, not an extra
            return ""
        try:
            made = shrink(raw, width=PLATE_WIDTH)
        except Exception:
            # Pillow missing, or an image it cannot read. A reader without a plate is a
            # reader; a build that died over a decoration is not.
            return ""
        small.parent.mkdir(parents=True, exist_ok=True)
        small.write_bytes(made)
    return f"data:image/webp;base64,{base64.b64encode(small.read_bytes()).decode('ascii')}"


def cover_name(document: Document) -> str:
    """Which cover belongs to this text.

    Covers are drawn for the library's own texts and named by the catalogue's id, which
    is what lets one drawing serve every reader who builds that text. Anything else has
    none, and asks for none.
    """
    from .. import catalogue as catalogue_module

    entry = catalogue_module.matching(document.source)
    return entry.id if entry else ""


def english_title(document: Document) -> str:
    """The title in English, for a catalogue text; nothing for anything else.

    Render-time context, like the cover: it reaches every reader on the next rebuild and
    touches no cache key, and an upload — which has no English title anywhere — shows
    its Hebrew one alone.
    """
    from .. import catalogue as catalogue_module

    # `matching` knows the public source shapes; a source it does not recognise is still
    # a catalogue text if an entry names it exactly, which is how `/readers` decides too.
    entry = catalogue_module.matching(document.source) or next(
        (e for e in catalogue_module.CATALOGUE if e.source == document.source), None
    )
    return entry.english if entry else ""


def render(
    document: Document,
    segmented: SegmentedDocument,
    translations: list[Translation],
    out_dir: Path,
    annotation: Annotation | None = None,
    glossaries: Mapping[str, Glossary] | None = None,
    vocalization: Vocalization | None = None,
    clean: bool = True,
    glossary_pending: str = "",
    covers: Path | None = None,
    reads: Collection[str] | None = None,
    siblings: list[dict[str, str]] | None = None,
    whole: bool = False,
    folder: Path | None = None,
) -> list[Path]:
    """Write the reader. Returns every file written, index first.

    `folder` is the targum's own directory, where an imported recording's manifest and
    parts live — see `speech`. None for every text that has no such folder to ask.

    `glossaries` is keyed by target language, because a meaning is written in one and a
    reader may hold translations into two. A word means what it means in Russian and
    something else in English, and the page has to be able to hand a reader the one they
    asked for rather than whichever was built last.

    `glossary_pending` is the target whose meanings are still being written, or "". It is
    a language rather than a flag for the same reason: the reader polls for the target it
    is showing, and switching to one that was never bought must not start a wait for a
    file nobody is writing.

    `reads` is which languages the person this reader belongs to reads. A translation into
    any other is left out of the page: a picker offering a language somebody cannot read
    offers them a page of nothing, and a word kept from it would carry a meaning in that
    language into every text they own. None means ask nobody, which is the command line
    and a machine somebody runs themselves.

    A reader left with nothing by that keeps what it had. A page with no translation
    beside the source is not a reader at all, which is the worse of the two answers — and
    it only arises where somebody stopped reading a language they had already built in.

    `siblings` are other readers of the same text at other levels, each a dict of
    `name`, `figure`, `href` and `current`. The weekly is one issue written three times,
    and a reader who finds one level too hard should be able to say so in one press
    rather than going back out to the library to look for the easier one. Relative
    hrefs, so a folder that travels to a disk keeps working.

    `whole` keeps the text in one piece instead of breaking it at its headings. A book
    is chapters and a reader wants them one at a time; an issue of the weekly is five
    short sections that add up to a twenty-minute read, and splitting it gave a stranger
    a contents page and five clicks before any Hebrew. One file, no contents page, and
    the headings stay headings inside it.

    `clean=False` writes over what is already there instead of emptying the directory
    first. It is for the second pass, once the word meanings have arrived: the same
    segments produce the same section files under the same names, so overwriting leaves
    nothing stale behind, and a reader someone has open does not have the page they are
    reading deleted from under them for the moment it takes to write the new one.
    """
    if not translations:
        raise ValueError("a reader needs at least one translation")

    if reads is not None:
        offered = [t for t in translations if t.target_language in reads]
        translations = offered or translations

    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = _environment()
    sections = (
        [
            Section(
                number=1,
                title=document.title or "",
                segment_ids=[segment.id for segment in segmented.segments],
            )
        ]
        if whole
        else split_sections(segmented)
    )
    by_id = {segment.id: segment for segment in segmented.segments}
    single = len(sections) == 1

    # Two ways to show the same sentence. The bare form is what the page renders by
    # default and the one every stored offset is measured against; the pointed form is
    # the cell the switch reveals — everything the edition wrote above and below the
    # letters, accents included where it has them. Both are built here rather than in
    # the browser so each goes through isolate() and neither has to be reassembled in
    # JavaScript.
    #
    # One switch, two positions: bare, or the whole text.
    #
    # A middle step that showed the vowels without the accents existed for a day and
    # went — a third form on a Tanakh was a state to be lost in, and the only thing it
    # ever taught a reader was that the arrows had stopped working. It is back, on
    # 2026-09-01, and neither of those is true of what came back. It is not a middle
    # step: the vowel switch still has its two positions and the accents are their own
    # control, which is off in the ⋯ menu where a setting made once belongs. And the
    # arrows work because the reason they broke was fixed elsewhere in the meantime —
    # `markMap` in reader.js derives a cell's offsets from that cell's own characters,
    # so a form nobody had thought of when it was written maps like any other.
    #
    # What it is for: somebody preparing to leyn reads the te'amim, and somebody reading
    # the parasha for the Hebrew finds them noise on top of the vowels they are still
    # learning. Both are the same page. See `/parasha` and §12 of design.md.
    bare: dict[str, str] = {}
    to_bare: dict[str, list[int]] = {}
    for segment in segmented.segments:
        bare[segment.id], to_bare[segment.id] = strip_nikkud(segment.text)
    pointed = dict(vocalization.segments) if vocalization is not None else {}
    machine = set(vocalization.machine) if vocalization is not None else set()

    # The pointed text with the chanting marks taken out, for the segments that have
    # any. Built here beside the other two so it goes through the same isolate() and the
    # browser never has to reassemble a sentence; absent everywhere else, which is what
    # keeps every modern text exactly two cells and one switch.
    unaccented: dict[str, str] = {}
    for segment_id, text in pointed.items():
        if not has_taamim(text):
            continue
        without = strip_taamim(text)
        if without != text:
            unaccented[segment_id] = without

    # Which face this page carries follows the text, not the shelf. The modern face is
    # chosen for reading a newspaper and has no accents in it, so a text that carries one
    # anywhere — an essay quoting a verse — must be set in the face that can draw them. A
    # page that cannot draw its own text is the whole bug this began as.
    accented = any(has_taamim(text) for text in pointed.values())

    # Whose pointing this mostly is. A Tanakh or a pointed poem arrives with its vowels
    # already on the page and someone chose it for them, so it opens pointed; a news
    # article whose points are all guessed opens bare, which is how it was written.
    # The marker on a guessed sentence follows the same fact: when every line is
    # guessed it distinguishes nothing and only adds noise, so it is left off.
    from_source = len(pointed) - len(machine)
    source_pointed = bool(pointed) and from_source * 2 >= len(pointed)
    mark_guessed = bool(machine) and len(machine) * 2 < len(pointed)

    biblical = is_biblical(document.source)
    # Which verse each row is, by the address a learner would write. The number stands in
    # the margin and the row answers to `#2:1`, so a link to Ruth 2:1 opens on Ruth 2:1
    # (targum-internal#28). Only a verse carries one: prose has no address, and a heading
    # is the chapter's, not a verse's.
    verses = {
        segment.id: verse_address(segment.ref)
        for segment in segmented.segments
        if segment.kind is BlockKind.verse and verse_address(segment.ref)
    }
    source_direction = direction_for(segmented.language)
    target_direction = direction_for(translations[0].target_language)

    # Where a reader may jump to. Only the top-level headings, and never the first one,
    # which is the masthead: the weekly is one long targum, and somebody who does not
    # want the politics should not have to scroll past them to find the sport.
    parts: list[dict[str, str]] = []
    for segment in segmented.segments:
        if segment.kind is not BlockKind.heading or (segment.level or 1) > 1:
            continue
        parts.append({"id": segment.id, "title": segment.text})
    # The first is the masthead, which is where a reader already is.
    parts = parts[1:]

    drawn = cover_name(document)
    # Whether this text is an imported recording. The contents page asks so its
    # waiting rows can offer the work actually owed — a transcript, not a translation.
    from ..audio import manifest as manifest_module

    has_audio = folder is not None and (folder / manifest_module.MANIFEST).is_file()
    shared = {
        "has_audio": has_audio,
        # What to read next, worked out here because a reader cannot ask anybody.
        "suggested": next_after(document),
        "parts": parts,
        "document": document,
        "siblings": siblings or [],
        "title": document.title or "targum",
        "english": english_title(document),
        # The whole tile, once, on the page that lists the chapters.
        "cover": cover_uri(covers, drawn),
        "sections": sections,
        "source_language": segmented.language,
        "source_direction": source_direction,
        "target_language": translations[0].target_language,
        "target_direction": target_direction,
        "page_direction": source_direction,
        "has_nikkud": bool(pointed),
        "has_taamim": bool(unaccented),
        "source_pointed": source_pointed,
        "mark_guessed": mark_guessed,
        # A verse is not a paragraph. Tanakh pairs one pasuk to a row, and rows spaced
        # like paragraphs put a blank line between every verse — a chapter then reads as
        # a list of separate sayings rather than as continuous text. Asked of the source
        # rather than guessed from the content, the same way `biblical.for_source()`
        # decides which difficulty bands to use, and for the same reason.
        "verse_by_verse": biblical,
        # Which of the two Hebrew faces this page carries. Scripture is set in a face cut
        # for the Masorah; a newspaper is not — but see `accented` above: the deciding
        # question is what the text holds, not which shelf it came from.
        "biblical": accented,
        "difficulty": None
        if annotation is None
        else {
            "method": method_label(annotation.method),
            "note": annotation.method_note,
            "annotator": annotation.annotator,
        },
        "translations": [
            {
                "id": f"t{index}",
                "name": translation.name,
                "language": translation.target_language,
                "direction": direction_for(translation.target_language),
                "kind": translation.kind,
                "style": translation.style.value,
                "provider": translation.provider,
            }
            for index, translation in enumerate(translations)
        ],
    }

    written: list[Path] = []
    for section in sections:
        segments = [by_id[sid] for sid in section.segment_ids]
        # Only this section's translations ship with the page, so a long book stays
        # openable on a phone.
        payload = {
            f"t{index}": {
                "text": {sid: translation.segments.get(sid, "") for sid in section.segment_ids},
                # Regions that fell back to paragraph pairing, so the reader can mark
                # them. A learner needs to know the pairing here is approximate.
                "coarse": [sid for sid in section.segment_ids if sid in set(translation.coarse)],
                # Which language this one is, and which way it runs. The page used to
                # take both from `translations[0]` and stamp them on the cells once, so
                # switching to a translation in another language left every cell claiming
                # the first one's language — and left the reader's word lookups asking
                # for meanings in a language nobody was reading.
                "language": translation.target_language,
                "direction": direction_for(translation.target_language),
            }
            for index, translation in enumerate(translations)
        }
        # Per-word data ships as offsets rather than as a span for every word. A book
        # has hundreds of thousands of tokens, and emitting markup for all of them up
        # front is what makes a reader too heavy for a phone.
        # Lemmas go in a table and the words point into it: the same lemma turns up
        # dozens of times in a chapter, and repeating it with every token is what makes
        # a page heavy.
        lemmas: list[str] = []
        lemma_at: dict[str, int] = {}
        # Root and binyan belong to the dictionary form, not to the occurrence, so they
        # ride in tables beside the lemmas rather than on every token. Absent for every
        # word that is not a Hebrew verb, and for the verbs whose root could not be had.
        roots: list[str] = []
        binyanim: list[str] = []
        # And so does the register, for the same reason: which Hebrew a word belongs to
        # is a fact about the dictionary form. Codes rather than sentences, so the words
        # on the card can be rewritten without re-annotating a library.
        registers: list[str] = []
        # How a word is said belongs to the occurrence, not to the dictionary form — that
        # is the whole reason it is worth having — so it cannot ride beside the lemmas.
        # It rides in its own table instead, with an index on each token: a chapter has
        # far fewer distinct spellings than tokens, and the same word said twice is
        # stored once.
        sounds: list[str] = [""]
        sound_at: dict[str, int] = {"": 0}
        # How a split surface is put together, and the occurrence's grammar. Both are
        # facts about the occurrence, like the sound, and ride the same way: a table of
        # distinct strings with an index on each token, because ולבית is built the same
        # way every time it appears and a chapter conjugates far fewer ways than it has
        # words. Index 0 is "nothing to say".
        builts: list[str] = [""]
        built_at: dict[str, int] = {"": 0}
        grammar: list[str] = [""]
        grammar_at: dict[str, int] = {"": 0}
        words: dict[str, list[list[int]]] = {}
        if annotation is not None:
            for sid in section.segment_ids:
                tokens = annotation.tokens.get(sid)
                if not tokens:
                    continue
                rows: list[list[int]] = []
                for token in tokens:
                    if token.lemma not in lemma_at:
                        lemma_at[token.lemma] = len(lemmas)
                        lemmas.append(token.lemma)
                        roots.append(token.root or "")
                        binyanim.append(token.binyan or "")
                        registers.append(token.word_register or "")
                    # Offsets arrive measured against the segment as ingested, which may
                    # itself be pointed. They ship measured against the bare form, the
                    # one coordinate system the reader keeps everything in. Where the
                    # source had no marks the map is the identity and this costs nothing.
                    if token.ipa and token.ipa not in sound_at:
                        sound_at[token.ipa] = len(sounds)
                        sounds.append(token.ipa)
                    if token.built and token.built not in built_at:
                        built_at[token.built] = len(builts)
                        builts.append(token.built)
                    if token.feats and token.feats not in grammar_at:
                        grammar_at[token.feats] = len(grammar)
                        grammar.append(token.feats)
                    start, end = map_span(token.start, token.end, to_bare[sid])
                    rows.append(
                        [
                            start,
                            end,
                            token.band,
                            1 if token.split else 0,
                            lemma_at[token.lemma],
                            sound_at.get(token.ipa or "", 0),
                            # A name or a number, which the reader can tap and mark but
                            # which is never counted as vocabulary.
                            KIND_COLUMN.get(token.pos or "", 0),
                            built_at.get(token.built or "", 0),
                            grammar_at.get(token.feats or "", 0),
                        ]
                    )
                words[sid] = rows
        # One table of meanings per target language, each parallel to `lemmas`. A reader
        # holding an English and a Russian translation carries both and shows whichever
        # its picker is on; a reader with one carries one, which is what every text built
        # so far is. Empty tables are left out rather than shipped as a row of "".
        glosses = {
            code: filled
            for code, book in (glossaries or {}).items()
            if (filled := [book.entries.get(lemma, "") for lemma in lemmas]) and any(filled)
        }
        # Facts about the source word itself — a verb's citation form, a lying plural —
        # which any glossary that holds them can supply: they do not vary by target.
        citations = [""] * len(lemmas)
        plurals = [""] * len(lemmas)
        for book in (glossaries or {}).values():
            for at, lemma in enumerate(lemmas):
                citations[at] = citations[at] or book.citations.get(lemma, "")
                plurals[at] = plurals[at] or book.plurals.get(lemma, "")
        # Who speaks each line and where it is said, for a dialogue. Empty for every
        # other text, and computed per section so a scene split across pages carries only
        # the spans its own page needs.
        spoken = speech(document, segments, folder)
        # The one file too heavy to ride inside the page. Copied beside the reader and
        # named by a relative address, so a folder that travels to a disk keeps its
        # picture and the page still fetches nothing from any network (design.md §12).
        spoken_video = ""
        if spoken.video:
            reel = Path(spoken.video)
            sidecar = out_dir / "video" / reel.name
            # Size and mtime both: a re-transcoded part of identical size is still a
            # different file, and copy2 carries the mtime over so the pair agree.
            fresh = sidecar.is_file() and (
                sidecar.stat().st_size == reel.stat().st_size
                and sidecar.stat().st_mtime >= reel.stat().st_mtime
            )
            if not fresh:
                # Copied beside and renamed over, never written in place: a hosted
                # rebuild runs while somebody may be streaming this very file, and a
                # rename leaves their open handle on the old bytes — the same move
                # write_atomic makes for the same reason.
                sidecar.parent.mkdir(parents=True, exist_ok=True)
                passing = sidecar.with_name(sidecar.name + ".part")
                shutil.copy2(reel, passing)
                os.replace(passing, sidecar)
            spoken_video = f"video/{reel.name}"
        # Whether this section is an imported recording's part still waiting for its
        # transcript. The page says which work is owed, and the button asks for it.
        audio_waiting = any(segment.ref.endswith(":waiting") for segment in segments)
        # A chapter's own cover where one was drawn for it, and the book's where it was
        # not — which is most of them, since a numbered chapter is not a subject anything
        # could draw.
        chapter_cover = f"{drawn}-c{section.number:03d}" if drawn else ""
        # Whether this chapter has been translated at all. A book is bought a chapter
        # at a time and every chapter's page is written regardless, so one nobody has
        # paid for used to render as the source beside a column of empty paragraphs —
        # which is what a reader who followed the arrow from chapter one walked into.
        # The same rule `Library.chapters()` applies, so the contents page and the
        # chapter page cannot disagree about which chapters are waiting.
        translated = any(translations[0].segments.get(sid) for sid in section.segment_ids)
        html = env.get_template("reader.html.j2").render(
            **shared,
            plate=plate_uri(covers, chapter_cover) or plate_uri(covers, drawn),
            section=section,
            translated=translated,
            audio_waiting=audio_waiting,
            words=bool(words),
            segments=segments,
            verses=verses,
            bare=bare,
            pointed=pointed,
            unaccented=unaccented,
            machine=machine,
            speakers=spoken.speakers,
            spoken=spoken.spans,
            # The player asks whether there is a recording; the per-line controls ask
            # whether there are spans. Prose has the first and not the second.
            spoken_audio=bool(spoken.audio),
            spoken_video=spoken_video,
            spoken_label=spoken.label,
            speech_credit=spoken.credit,
            speech_licence=spoken.licence,
            speech_licence_url=spoken.licence_url,
            primary=translations[0].segments,
            primary_coarse=set(translations[0].coarse),
            data=embed_json(
                {
                    "translations": payload,
                    "words": words,
                    "lemmas": lemmas,
                    "roots": roots,
                    "binyanim": binyanim,
                    # Left out where the two registers agreed about every word on the
                    # page, and for every language the question is not asked of, rather
                    # than shipping a row of empty strings the reader would never read.
                    **({"registers": registers} if any(registers) else {}),
                    # Which register the reader is standing in, so the card can say the
                    # same fact from where they are: a word out of the Tanakh is
                    # ordinary in a Tanakh and an import in a newspaper.
                    "sourceRegister": "biblical" if is_biblical(document.source) else "modern",
                    # Left out entirely where nothing was read, rather than shipping a
                    # table holding one empty string in every reader that has no Hebrew.
                    **({"sounds": sounds} if len(sounds) > 1 else {}),
                    # How split words are put together and how each occurrence is
                    # conjugated or declined, for the card's own lines. Left out, like
                    # the sounds, wherever an annotation written before they existed —
                    # or a language they say nothing about — gave the tables nothing.
                    **({"built": builts} if len(builts) > 1 else {}),
                    **({"grammar": grammar} if len(grammar) > 1 else {}),
                    # A verb's citation form and a noun's lying plural, parallel to the
                    # lemmas. Left out while nothing on the page has either — which is
                    # every text glossed before they existed.
                    **({"citations": citations} if any(citations) else {}),
                    **({"plurals": plurals} if any(plurals) else {}),
                    "glosses": glosses,
                    "levelNames": BAND_NAMES,
                    # Which text this is. Lists are kept per document, not per
                    # language, so reading two articles does not pool their words.
                    "document": segmented.document_hash,
                    "title": document.title or "",
                    # For naming an export of the language's words, which the reader
                    # otherwise only knows by its tag.
                    "languageName": language_name(segmented.language),
                    # Whether the vowels on this text are its own, and so whether it
                    # should open with them showing.
                    "sourcePointed": source_pointed,
                    # Which target's meanings are on their way, if any. Words are looked
                    # up one at a time now, so most readers have none coming and must not
                    # sit asking for one for ten minutes — and a reader that switches to
                    # a language nobody bought a glossary for must not start asking
                    # either.
                    "glossPending": glossary_pending,
                    # A dialogue's audio and where each line sits in it. Absent for every
                    # other kind of text, rather than an empty table in every reader.
                    # On the audio, not the spans: prose has a recording and no spans,
                    # and keying this on spans left the player on the page with nothing
                    # behind it — a control that does nothing, which is worse than none.
                    **(
                        {
                            "speech": {
                                "audio": spoken.audio,
                                # The sidecar's relative address, never its bytes.
                                **({"video": spoken_video} if spoken_video else {}),
                                "spans": spoken.spans,
                                # Each written word's clock, char offsets mapped into
                                # the bare text like every token row, so the card can
                                # find the sound under a tapped word by overlap alone.
                                **(
                                    {
                                        "words": {
                                            sid: [
                                                [*map_span(int(cs), int(ce), to_bare[sid]), s, e]
                                                for cs, ce, s, e in rows
                                            ]
                                            for sid, rows in spoken.words.items()
                                            if sid in to_bare
                                        }
                                    }
                                    if spoken.words
                                    else {}
                                ),
                            }
                        }
                        if spoken.audio
                        else {}
                    ),
                }
            ),
            previous=None if section.number == 1 else sections[section.number - 2],
            following=None if section.number == len(sections) else sections[section.number],
            standalone=single,
        )
        name = "index.html" if single else section.filename
        written.append(_write(out_dir / name, html))

    if not single:
        # Which chapters each file holds, so the contents page can send `#2:1` on to the
        # file that has chapter 2 in it. Not the section number: a range ingested from
        # chapter 12 puts chapter 12 in the first file, and only the refs know that.
        chapters = {
            section.number: " ".join(
                dict.fromkeys(
                    verses[sid].split(":")[0] for sid in section.segment_ids if sid in verses
                )
            )
            for section in sections
        }
        index = env.get_template("index.html.j2").render(
            **shared,
            counts={s.number: len(s.segment_ids) for s in sections},
            chapters=chapters,
        )
        written.insert(0, _write(out_dir / "index.html", index))
    return written


def _write(path: Path, html: str) -> Path:
    path.write_text(html, encoding="utf-8")
    return path
