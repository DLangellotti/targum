"""The owner of a text corrects its words, and cuts it into parts (targum-internal#533).

A transcript mishears, an article arrives with its caption glued to a sentence, a long
talk wants to be read in sittings. Somebody who brought a text may fix all three, in the
reader, and the fix is theirs alone: a library text is everybody's, and a reader's
correction of one stays a proposal (`Handler._propose_correction`, design.md §12 "An
editor settles a reader's proposal").

**One line at a time, and every other line keeps its id.** A segment's id is its block,
its place in the block and a hash of its text (`ids.segment_id`), so the corrected line
gets a new id and nothing else moves. That is what keeps everything already paid for:
every other line's English, words, pointing and clock are filed under ids the
correction never touched. Nothing here re-segments, which would renumber the block.

**Nothing here spends.** The corrected line keeps the English it had, marked as from
before the correction, until the reader presses Translate again — a quoted press through
`Library.press` like any other. Its words and its pointing are worked out again on this
machine (`words_again`); a language whose words a model reads waits for that press too.

**The record is kept, and replayed.** `corrections.json` beside the text says what each
corrected line was and is, and where the reader cut the text. A recording grows when its
next part is heard, and growing re-ingests the whole transcript; `replay_document` and
`replay_breaks` are what keep a correction and a cut across that.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import TargumError
from .ids import segment_id
from .models import (
    Alignment,
    Annotation,
    Document,
    Segment,
    SegmentedDocument,
    Translation,
    Vocalization,
    read_artifact,
)
from .paths import write_atomic

CORRECTIONS = "corrections.json"

#: One lock a folder, held while its artifacts are rewritten. A correction, a cut and
#: the words read again afterwards each read several files and write them back, and two
#: workers or a worker and a request doing that at once would each write over the other's
#: half. One a folder, so a model reading one text's words holds up no other text.
_LOCKS: dict[str, threading.RLock] = {}
_LOCKING = threading.Lock()


def lock(folder: Path) -> threading.RLock:
    with _LOCKING:
        return _LOCKS.setdefault(str(folder.resolve()), threading.RLock())


#: The longest line a correction may write. A sentence, or a long one; a paragraph pasted
#: into one line is a text of its own, and Add is where that goes.
LONGEST = 2000

#: Prefixes of sources that are everybody's, whoever's home holds a copy. `http(s)` is
#: not among them: a link is what a reader brings, unless the catalogue names it.
_SHARED = ("gutenberg:", "wikisource:", "sefaria:", "catalogue:", "weekly:", "dialogue:", "video:")


def own_source(source: str, home: str = "") -> bool:
    """Whether a text came from the reader rather than from the library.

    `home` is where an imported recording was fetched from (the manifest's `home`), since
    its `source` is the local file by the time anything asks.
    """
    if not source or source.startswith(_SHARED):
        return False
    from . import catalogue as catalogue_module

    return not any(
        catalogue_module.matching(address) is not None for address in (source, home) if address
    )


def own_folder(folder: Path) -> bool:
    """`own_source`, asked of a folder on disk."""
    from .audio import manifest as manifest_module

    document = read_artifact(Document, folder / "document.json")
    if document is None:
        return False
    kept = manifest_module.load(folder)
    return own_source(document.source, kept.home if kept is not None else "")


# -- the record -----------------------------------------------------------------------


def record(folder: Path) -> dict[str, Any]:
    """What `corrections.json` holds, or an empty record."""
    try:
        found = json.loads((folder / CORRECTIONS).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        found = {}
    if not isinstance(found, dict):
        found = {}
    return {
        # Each corrected line: its block, what it first was, what it is now.
        "lines": [line for line in found.get("lines") or [] if isinstance(line, dict)],
        # Where the reader started a part: the ids of the lines that open one.
        "breaks": [str(one) for one in found.get("breaks") or []],
        # Per language, each corrected line whose English is from before, and that
        # English — so a line translated since is recognised by its text changing.
        "before": {
            str(target): {str(k): str(v) for k, v in lines.items()}
            for target, lines in (found.get("before") or {}).items()
            if isinstance(lines, dict)
        },
        # Lines whose words and pointing are still to be worked out again.
        "unread": [str(one) for one in found.get("unread") or []],
    }


def keep(folder: Path, kept: dict[str, Any]) -> None:
    write_atomic(folder / CORRECTIONS, json.dumps(kept, ensure_ascii=False, indent=2) + "\n")


def stale(folder: Path) -> dict[str, list[str]]:
    """Per language, the corrected lines whose English is still from before."""
    kept = record(folder)
    out: dict[str, list[str]] = {}
    for path in sorted((folder / "translations").glob("*.json")):
        translation = read_artifact(Translation, path)
        if translation is None:
            continue
        before = kept["before"].get(translation.target_language, {})
        lines = [sid for sid, was in before.items() if translation.segments.get(sid) == was]
        if lines:
            out.setdefault(translation.target_language, []).extend(lines)
    return out


# -- a line ---------------------------------------------------------------------------


def tidy(text: str) -> str:
    """A line as it is kept: NFC, one line, no space at either end."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


@dataclass(slots=True)
class Corrected:
    was: str
    now: str
    #: The line's id before and after. The same where nothing changed.
    old: str
    new: str
    #: The languages whose English for this line is from before the correction.
    before: list[str] = field(default_factory=list)


def correct_line(folder: Path, line: str, text: str) -> Corrected:
    """Write one line's new words into every artifact the folder holds.

    Raises `TargumError` with a sentence for the reader where the line cannot be
    corrected: it is not there, it is a part still waiting to be heard, or the new text
    is empty or too long.
    """
    with lock(folder):
        return _correct_line(folder, line, text)


def _correct_line(folder: Path, line: str, text: str) -> Corrected:
    document = read_artifact(Document, folder / "document.json")
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if document is None or segmented is None:
        raise TargumError("We can't find that text any more.", key="correct.text-gone")
    found = next((s for s in segmented.segments if s.id == line), None)
    if found is None:
        raise TargumError(
            "We can't find that line any more. Reload the page.", key="correct.line-gone"
        )
    if found.ref.endswith(":waiting"):
        raise TargumError("That part isn't transcribed yet.", key="correct.waiting")
    now = tidy(text)
    if not now:
        raise TargumError(
            "A line needs some words. To start again, press Cancel.", key="correct.empty"
        )
    if len(now) > LONGEST:
        raise TargumError(
            "That's too long for one line. Add it as a text of its own.", key="correct.too-long"
        )
    if now == found.text:
        return Corrected(was=found.text, now=now, old=line, new=line)

    block = next((b for b in document.blocks if b.id == found.block_id), None)
    if block is None:
        raise TargumError(
            "We can't find that line any more. Reload the page.", key="correct.line-gone"
        )
    # Where this line sits in its block: each sentence is found after the one before it,
    # so a sentence said twice in one paragraph is told apart by its place.
    at = 0
    start = -1
    for segment in segmented.segments:
        if segment.block_id != block.id:
            continue
        start = block.text.find(segment.text, at)
        if start < 0:
            break
        if segment.id == line:
            break
        at = start + len(segment.text)
    if start < 0:
        raise TargumError("We couldn't change that line.", key="correct.could-not")
    block.text = block.text[:start] + now + block.text[start + len(found.text) :]
    document.content_hash = document.recompute_hash()

    new = segment_id(found.block_index, found.index, now)
    was = found.text
    found.text = now
    found.id = new
    segmented.document_hash = document.content_hash

    kept = record(folder)
    renamed = {line: new}
    kept["breaks"] = [new if one == line else one for one in kept["breaks"]]
    segmented.breaks = [one for one in kept["breaks"] if one in _ids(segmented)]

    document.write(folder / "document.json")
    segmented.write(folder / "segments.json")

    before: list[str] = []
    for path in sorted((folder / "translations").glob("*.json")):
        translation = read_artifact(Translation, path)
        if translation is None:
            continue
        translation.document_hash = segmented.document_hash
        english = translation.segments.pop(line, None)
        if english is not None:
            translation.segments[new] = english
            lines = kept["before"].setdefault(translation.target_language, {})
            lines.pop(line, None)
            lines[new] = english
            before.append(translation.target_language)
        translation.coarse = [new if one == line else one for one in translation.coarse]
        if line in translation.confidence:
            translation.confidence[new] = translation.confidence.pop(line)
        translation.write(path)

    _forget_words(folder, segmented.document_hash, line)
    _rename_alignments(folder, segmented.document_hash, renamed)
    _move_clocks(folder, line, was, found)

    # The record: the first thing the line ever was, and what it is now. A line put back
    # the way it arrived is no longer a correction at all.
    entry = next(
        (one for one in kept["lines"] if one.get("block") == block.id and one.get("now") == was),
        None,
    )
    if entry is None:
        entry = {"block": block.id, "was": was}
        kept["lines"].append(entry)
    entry["now"] = now
    if entry.get("was") == now:
        kept["lines"].remove(entry)
    kept["unread"] = [one for one in kept["unread"] if one != line] + [new]
    keep(folder, kept)
    return Corrected(was=was, now=now, old=line, new=new, before=before)


def _ids(segmented: SegmentedDocument) -> set[str]:
    return {segment.id for segment in segmented.segments}


def _forget_words(folder: Path, document_hash: str, line: str) -> None:
    """The old line's words and pointing go; everything else is filed under the new hash.

    Left in place they would be read against the wrong text: a token is a pair of
    offsets into its line, and a pointed line has to have the line's own letters.
    """
    annotation = read_artifact(Annotation, folder / "annotation.json")
    if annotation is not None:
        annotation.tokens.pop(line, None)
        annotation.document_hash = document_hash
        annotation.write(folder / "annotation.json")
    vocalization = read_artifact(Vocalization, folder / "vocalization.json")
    if vocalization is not None:
        vocalization.segments.pop(line, None)
        vocalization.machine = [one for one in vocalization.machine if one != line]
        vocalization.rejected = [one for one in vocalization.rejected if one != line]
        vocalization.document_hash = document_hash
        vocalization.write(folder / "vocalization.json")


def _rename_alignments(folder: Path, document_hash: str, renamed: dict[str, str]) -> None:
    for path in sorted((folder / "alignments").glob("*.json")):
        alignment = read_artifact(Alignment, path)
        if alignment is None:
            continue
        alignment.document_hash = document_hash
        for link in alignment.links:
            link.source = [renamed.get(one, one) for one in link.source]
        alignment.write(path)


def _move_clocks(folder: Path, old: str, was: str, line: Segment) -> None:
    """Keep the line's place in its recording, and the clock of every word still in it.

    The line's span is the line's, whatever its words: it keeps it under its new id. A
    word's clock is matched across by `audio.spans.word_spans_for`, the same difflib
    match a build makes against the transcript, so a word the correction left alone keeps
    its clock and a word it changed has none — a gap beats a clock that lies, as it does
    everywhere else. The next build re-derives both from the transcript the same way.
    """
    from .audio import manifest as manifest_module
    from .audio.spans import word_spans_for
    from .transcribe.models import Word

    kept = manifest_module.load(folder)
    if kept is None:
        return
    moved = False
    for part in kept.parts:
        if old in part.spans:
            part.spans[line.id] = part.spans.pop(old)
            moved = True
        rows = part.words.pop(old, None)
        if rows is not None:
            heard = [
                Word(text=was[int(row[0]) : int(row[1])], start=row[2], end=row[3]) for row in rows
            ]
            part.words.update(word_spans_for([line], heard))
            moved = True
        if old in part.speakers:
            part.speakers[line.id] = part.speakers.pop(old)
            moved = True
    if moved:
        manifest_module.write(folder, kept)


# -- a part ---------------------------------------------------------------------------


def cut(folder: Path, line: str, *, join: bool = False) -> list[str]:
    """Start a part at this line, or join the part it starts to the one before.

    A cut is a list of the lines that open a part (`SegmentedDocument.breaks`, which
    `render.split_sections` reads), so no id moves and nothing is bought again. Only a
    cut the reader made can be joined: a part that opens at a heading is the text's own.
    Returns the cuts as they now stand.
    """
    with lock(folder):
        return _cut(folder, line, join)


def _cut(folder: Path, line: str, join: bool) -> list[str]:
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if segmented is None:
        raise TargumError("We can't find that text any more.", key="correct.text-gone")
    ids = [segment.id for segment in segmented.segments]
    if line not in ids:
        raise TargumError(
            "We can't find that line any more. Reload the page.", key="correct.line-gone"
        )
    kept = record(folder)
    breaks = [one for one in kept["breaks"] if one in ids]
    if join:
        breaks = [one for one in breaks if one != line]
    else:
        if ids.index(line) == 0:
            raise TargumError("This is where the text starts already.", key="correct.at-start")
        if line not in breaks:
            breaks.append(line)
    order = {sid: index for index, sid in enumerate(ids)}
    breaks.sort(key=order.__getitem__)
    segmented.breaks = breaks
    segmented.write(folder / "segments.json")
    kept["breaks"] = breaks
    keep(folder, kept)
    return breaks


# -- replayed by a build --------------------------------------------------------------


def replay_document(folder: Path, document: Document) -> bool:
    """Put the reader's corrections back into a document read again from its source.

    A recording that grows is ingested whole again, from the transcript, which says what
    was heard and not what the reader corrected it to. Each correction is put back where
    its block still says what the line first was; a block that says something else now
    is left alone, since the transcript itself has moved under it. Returns whether
    anything changed, so the caller knows to hash the document again.
    """
    lines = record(folder)["lines"]
    if not lines:
        return False
    blocks = {block.id: block for block in document.blocks}
    changed = False
    for line in lines:
        block = blocks.get(str(line.get("block") or ""))
        was, now = str(line.get("was") or ""), str(line.get("now") or "")
        if block is None or not was or not now or now in block.text:
            continue
        if was in block.text:
            block.text = block.text.replace(was, now, 1)
            changed = True
    return changed


def replay_breaks(folder: Path, segmented: SegmentedDocument) -> None:
    """The reader's cuts, on segments made again. A cut at a line that is gone is gone."""
    ids = _ids(segmented)
    segmented.breaks = [one for one in record(folder)["breaks"] if one in ids]


# -- the words, again, here ------------------------------------------------------------


def words_again(folder: Path) -> list[str]:
    """Work out the pointing and the words of the corrected lines again, on this machine.

    Free: the diacritizer and the annotator both run here. A language whose words a model
    reads (`annotate.model_lemma.reads`) is left for the Translate again press, which is
    quoted and claimed, so its lines stay unread. Returns the lines read.

    Worked out outside the folder's `lock`, since a model takes seconds, and merged inside
    it, for the lines that are still there and still unread: a line corrected again
    meanwhile has a new id and is read by the next pass.
    """
    from .annotate import model_lemma
    from .vocalize import SOURCE_ONLY, for_source, supports, vocalize_document
    from .vocalize import russian as russian_stress

    with lock(folder):
        kept = record(folder)
        document = read_artifact(Document, folder / "document.json")
        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        vocalization = read_artifact(Vocalization, folder / "vocalization.json")
        has_words = (folder / "annotation.json").is_file()
    if document is None or segmented is None or not kept["unread"]:
        return []
    unread = set(kept["unread"])
    wanted = [segment for segment in segmented.segments if segment.id in unread]
    run = SegmentedDocument(
        document_hash=segmented.document_hash,
        language=segmented.language,
        segmenter=segmented.segmenter,
        segments=wanted,
    )
    pointed: Vocalization | None = None
    if (
        vocalization is not None
        and wanted
        and supports(segmented.language)
        and not russian_stress.supports(segmented.language)
    ):
        engine = None if vocalization.vocalizer == SOURCE_ONLY else for_source(document.source)
        try:
            pointed = vocalize_document(run, engine, source=document.source)
        except TargumError:
            pointed = None
        if pointed is not None:
            vocalization.segments.update(pointed.segments)
    words: Annotation | None = None
    if has_words and wanted and not model_lemma.reads(segmented.language):
        try:
            words = _annotator(folder, document).annotate(run, vocalization)
        except TargumError:
            words = None

    with lock(folder):
        ids = _ids(read_artifact(SegmentedDocument, folder / "segments.json") or segmented)
        kept = record(folder)
        still = {one for one in kept["unread"] if one in ids} & unread
        if pointed is not None:
            current = read_artifact(Vocalization, folder / "vocalization.json")
            if current is not None:
                current.segments.update({k: v for k, v in pointed.segments.items() if k in still})
                current.machine = sorted({*current.machine, *(set(pointed.machine) & still)})
                current.rejected = sorted({*current.rejected, *(set(pointed.rejected) & still)})
                current.write(folder / "vocalization.json")
        read: set[str] = set()
        if words is not None:
            annotation = read_artifact(Annotation, folder / "annotation.json")
            if annotation is not None:
                annotation.tokens.update({k: v for k, v in words.tokens.items() if k in still})
                annotation.write(folder / "annotation.json")
                read = still
        elif not has_words:
            # Nothing to read the words into: a text built without them stays without them.
            read = still
        kept["unread"] = [one for one in kept["unread"] if one in ids and one not in read]
        keep(folder, kept)
    return sorted(read)


def translated(folder: Path, target: str, lines: list[str], read: bool) -> None:
    """Forget that these lines' English was from before, once it is not; and that their
    words are unread, where the press read them."""
    with lock(folder):
        kept = record(folder)
        before = kept["before"].get(target, {})
        for line in lines:
            before.pop(line, None)
        if read:
            kept["unread"] = [one for one in kept["unread"] if one not in lines]
        keep(folder, kept)


def tidy_pages(folder: Path) -> None:
    """Take away the pages of parts that are no longer there.

    A reader is written over rather than emptied first (`render(clean=False)`), which
    leaves a page behind for every part a join took away — and the number of `sec-*`
    pages is how the shelf counts a text's parts. A text in one part has none at all: its
    reader is `index.html`.
    """
    from .render.builder import split_sections

    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if segmented is None:
        return
    count = len(split_sections(segmented))
    for page in (folder / "reader").glob("sec-*.html"):
        found = re.fullmatch(r"sec-(\d+)\.html", page.name)
        if found and (count < 2 or int(found.group(1)) > count):
            page.unlink(missing_ok=True)


def page_of(folder: Path, line: str) -> str:
    """The reader's page a line is on, as the folder now divides."""
    from .render.builder import split_sections

    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if segmented is None:
        return "index.html"
    sections = split_sections(segmented)
    if len(sections) < 2:
        return "index.html"
    return next(
        (section.filename for section in sections if line in section.segment_ids),
        "index.html",
    )


def _annotator(folder: Path, document: Document) -> Any:
    """The annotator `targum rebuild --words` would read this text with, here."""
    from .annotate import Annotator, PhonikudPronouncer, Pronouncer, biblical, lemma, pronounceable
    from .annotate import dictionary as dictionary_module

    pronouncer: Pronouncer | None = None
    if pronounceable(document.language) and (folder / "vocalization.json").is_file():
        phonikud = PhonikudPronouncer()
        if phonikud.available()[0]:
            pronouncer = phonikud
    return Annotator(
        lemmatizer=lemma.for_language(lemma.for_source(document.source), document.language),
        bands=biblical.for_source(document.source),
        pronouncer=pronouncer,
        **dictionary_module.for_language(document.language),
    )


def recache(builder: Any, segmented: SegmentedDocument, translation: Translation) -> None:
    """File what a corrected text's English already is under the keys its new text makes.

    A translation is cached by the text of the run it was bought for (`Build.cache_key`),
    so a corrected chapter has a key nothing holds, and the next build that reads the
    cache rather than the folder — a recording growing by a part — would buy the whole
    chapter again. Every line but the corrected ones is filed again under it; those stay
    out, so that build buys them and only them.
    """
    from .render.builder import split_sections

    corrected = record(builder.resolved_out)["before"].get(translation.target_language, {})
    before = {sid for sid, was in corrected.items() if translation.segments.get(sid) == was}
    runs = [segmented.segments]
    sections = split_sections(segmented)
    if len(sections) >= 2:
        by_id = {segment.id: segment for segment in segmented.segments}
        runs += [
            [by_id[sid] for sid in section.segment_ids]
            for section in sections
            if corrected.keys() & set(section.segment_ids)
        ]
    for run in runs:
        held = {
            segment.id: translation.segments[segment.id]
            for segment in run
            if segment.id in translation.segments and segment.id not in before
        }
        if held:
            key = builder.cache_key(segmented, run)
            builder.cache.put("translate", key, {"segments": builder.held(key) | held})
