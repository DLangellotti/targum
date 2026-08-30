"""ingest -> segment -> translate -> render.

Every stage writes its artifact and reads the one before it, so a rerun redoes only
what changed. A hand-edited artifact is left alone: fixing a bad extraction by editing
document.json and rerunning is a supported way to work, not a trick.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import align as align_module
from . import annotate as annotate_module
from . import ingest, render
from . import vocalize as vocalize_module
from .cache import Cache
from .errors import TargumError
from .ids import slug
from .models import (
    Alignment,
    Annotation,
    Document,
    Glossary,
    Segment,
    SegmentedDocument,
    Style,
    Translation,
    Vocalization,
    glossaries_in,
    glossary_path,
    is_biblical,
    read_artifact,
)
from .segment import Segmenter, StanzaSegmenter, segment_document
from .translate import build as build_provider
from .usage import Usage

Notify = Callable[[str], None]
Progress = Callable[[int], None]
# Called once the reader can be read, before the word meanings are looked up.
Ready = Callable[["Result"], None]


@dataclass(slots=True)
class Plan:
    """What a build will do, decided before anything is spent."""

    document: Document
    segmented: SegmentedDocument | None = None
    cached_translation: Translation | None = None
    estimated_cost: float = 0.0
    # How the text divides, and how much of it this estimate covers. A book is priced a
    # chapter at a time, so the two differ and the page needs both to say anything true.
    chapters: int = 1
    buying: int = 0
    # The segments that number counts. Kept rather than recomputed, so what the page
    # prices and what the build buys cannot come apart.
    buying_segments: list[Segment] = field(default_factory=list)

    @property
    def needs_payment(self) -> bool:
        return self.cached_translation is None and self.estimated_cost > 0


@dataclass(slots=True)
class Result:
    out_dir: Path
    document: Document
    segmented: SegmentedDocument
    translation: Translation
    translations: list[Translation] = field(default_factory=list)
    annotation: Annotation | None = None
    glossary: Glossary | None = None
    vocalization: Vocalization | None = None
    pages: list[Path] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    # What this build really cost, from the API's own numbers rather than the estimate.
    spent: Usage = field(default_factory=Usage)

    @property
    def index(self) -> Path:
        return self.pages[0]


class Build:
    def __init__(
        self,
        source: str,
        *,
        target_language: str,
        source_language: str | None = None,
        # What to call it, where the source will not say. Ben Yehuda's plain-text
        # downloads put the title and the author in the first line as prose, so nothing
        # parses one out and a book lands on a shelf named after its file.
        title: str = "",
        style: Style = Style.natural,
        provider_name: str = "anthropic",
        model: str | None = None,
        owner: str = "",
        out: Path | None = None,
        out_root: Path | None = None,
        force: bool = False,
        batch_size: int = 20,
        effort: str = "medium",
        segmenter: Segmenter | None = None,
        # A file on disk, or anything ingest reads: a catalogue text's published
        # translation is a wikisource: or gutenberg: name, not something downloaded
        # by hand first.
        translations: Sequence[Path | str] = (),
        machine: bool | None = None,
        difficulty: bool = False,
        gloss: bool = False,
        gloss_model: str | None = None,
        aligner: align_module.Aligner | None = None,
        annotator: annotate_module.Annotator | None = None,
        vocalizer: vocalize_module.Vocalizer | None = None,
        # Which languages whoever this build is for reads. A translation into any other
        # is left out of the reader — see `render`. None asks nobody, which is the command
        # line and a machine somebody runs themselves.
        reads: Sequence[str] | None = None,
        # The weekly's chrome: other levels of the same issue, and the line saying how
        # it was made. Both ride into `render` untouched; nothing else in the pipeline
        # looks at them.
        siblings: list[dict[str, str]] | None = None,
        whole: bool = False,
        notify: Notify | None = None,
    ) -> None:
        self.source = source
        self.target_language = target_language
        self.source_language = source_language
        self.style = style
        self.provider_name = provider_name
        self.title = title
        self.force = force
        self.notify = notify or (lambda _message: None)
        self.cache = Cache()
        self.segmenter: Segmenter = segmenter or StanzaSegmenter()
        self.translation_files: list[Path | str] = list(translations)
        # Supplying a published translation is a reason not to pay for a machine one,
        # unless the point is to compare them.
        self.machine = (not self.translation_files) if machine is None else machine
        self._aligner = aligner
        # Glosses need the same lemmas difficulty does, so asking for one implies the other.
        self.siblings = siblings
        self.whole = whole
        self.difficulty = difficulty or gloss
        self.gloss = gloss
        # Meanings may be bought on a cheaper model than the prose; hosted, they are.
        self.gloss_model = gloss_model
        self._annotator = annotator
        self._vocalizer = vocalizer
        self.provider: Any = build_provider(
            provider_name, model=model, batch_size=batch_size, effort=effort
        )
        self.model = getattr(self.provider, "model", None)
        # Whose build this is. Only used to scope the cache for a text that is not
        # public, so one person's upload is never re-served to another.
        self.owner = owner
        self.reads = set(reads) if reads is not None else None
        self._glosser: Any = None
        self._out = out
        self._out_root = out_root
        self._resolved_out: Path | None = None
        self.reused: list[str] = []

    # -- locations ---------------------------------------------------------

    def out_dir(self, document: Document) -> Path:
        if self._resolved_out is None:
            # A file is known by its name; anything fetched by link or identifier is
            # known by its title, since "wikisource:he:..." makes a poor folder.
            path = Path(self.source)
            name = slug(
                path.stem if path.is_file() else (self.title or document.title or path.stem)
            )
            root = self._out_root or (Path.cwd() / "targum-out")
            self._resolved_out = self._out or (root / f"{name}-{document.language}")
        return self._resolved_out

    @property
    def covers(self) -> Path:
        """Where drawn covers live: one directory for the library, not one per text.

        A cover belongs to a text rather than to a build of it, and two readers of the
        same book share the drawing the same way they share its English.
        """
        return (self._out_root or (Path.cwd() / "targum-out")) / "thumbs"

    @property
    def resolved_out(self) -> Path:
        if self._resolved_out is None:
            raise RuntimeError("out_dir is resolved during ingest")
        return self._resolved_out

    def translation_path(self, out: Path) -> Path:
        return (
            out
            / "translations"
            / f"{self.provider_name}.{self.style.value}.{self.target_language}.json"
        )

    # -- stages ------------------------------------------------------------

    def ingest(self) -> Document:
        fresh = ingest.load(self.source, language=self.source_language)
        # Where the source will not name itself, the caller may. Only ever as a fallback:
        # a title parsed out of the text is the text's own and beats anything passed in.
        if self.title and not fresh.title:
            fresh.title = self.title
        path = self.out_dir(fresh) / "document.json"
        if not self.force:
            existing = read_artifact(Document, path)
            if existing is not None:
                # The stored hash may predate a hand edit. Recompute from the blocks.
                actual = existing.recompute_hash()
                if actual != existing.content_hash:
                    existing.content_hash = actual
                    existing.write(path)
            if (
                existing is not None
                and fresh.source_hash
                and existing.source_hash
                and existing.source_hash != fresh.source_hash
            ):
                # The file itself changed, so the artifact describes a different text.
                existing = None
            if existing is not None and existing.ingester != fresh.ingester:
                # targum reads this format differently now, so the old extraction is
                # stale rather than edited. Re-ingest.
                existing = None
            if existing is not None and existing.content_hash != fresh.content_hash:
                # Someone edited the extraction by hand. Their version wins.
                self.notify(f"Using the edited {path.name}")
                self.reused.append("document (edited)")
                if self.source_language:
                    existing.language = self.source_language
                return existing
            if existing is not None and self.title and not existing.title:
                # A name is not part of the text, so an artifact written before anyone
                # knew the name is not stale — it is nameless. Five books were built from
                # plain .txt files this way and opened with nothing at the top of the
                # page; re-ingesting to fix that would change nothing but the metadata
                # and would risk the translation keyed to it.
                existing.title = self.title
                existing.write(path)
            if existing is not None:
                self.reused.append("document")
                return existing
        fresh.write(path)
        return fresh

    def segment(self, document: Document) -> SegmentedDocument:
        path = self.out_dir(document) / "segments.json"
        if not self.force:
            existing = read_artifact(SegmentedDocument, path)
            if existing is not None and existing.document_hash == document.content_hash:
                self.reused.append("segments")
                return existing
        segmented = segment_document(document, self.segmenter)
        if not segmented.segments:
            raise TargumError(f"No text found in {self.source}.")
        segmented.write(path)
        return segmented

    # Sources whose text is public, and whose translation may therefore be shared.
    # A translation is expensive and identical for everybody, so two subscribers reading
    # the same Gutenberg novel should pay for it once between them. An uploaded file is
    # somebody's own and is not shared, which is the position A7 has to take anyway —
    # and it costs almost nothing, because the overlap that makes sharing worth having
    # happens precisely where texts are public. Two people uploading the same private
    # file is not a thing that happens.
    PUBLIC_SOURCES = (
        "gutenberg:",
        "wikisource:",
        "sefaria:",
        "http://",
        "https://",
        "catalogue:",
        # An issue of the weekly is one public text that everybody reads. Its English
        # is bought once and shared, like a Gutenberg novel's.
        "weekly:",
        # A dialogue likewise, and more simply: its English is written with the scene,
        # so there is nothing to buy at all.
        "dialogue:",
    )

    def shared_source(self) -> bool:
        return str(self.source).startswith(self.PUBLIC_SOURCES)

    def cache_key(self, segmented: SegmentedDocument, segments: list[Segment] | None = None) -> str:
        """The key for a run of segments — a chapter, or the whole text.

        Keyed on the segments' own text rather than on the document, so a book that was
        translated as far as chapter four keeps those four chapters when the fifth is
        asked for, and so two readers of the same book share every chapter they have both
        reached. Keyed on the document, as it was, a part-translated book cached under a
        key nothing would ever ask for again.
        """
        run = segments if segments is not None else segmented.segments
        return self.cache.key(
            "translate",
            source=segmented.language,
            target=self.target_language,
            provider=self.provider_name,
            model=self.model,
            style=self.style.value,
            # The text itself, so identical prose keys the same wherever it came from.
            text=[segment.text for segment in run],
            # Private texts get a key nobody else can arrive at.
            owner="" if self.shared_source() else self.owner,
        )

    def cached(self, segmented: SegmentedDocument) -> Translation | None:
        if self.force:
            return None
        on_disk = read_artifact(Translation, self.translation_path(self.resolved_out))
        if on_disk is not None and on_disk.document_hash == segmented.document_hash:
            self.reused.append("translation")
            # The label is cosmetic and not part of the cache key, so keep it current
            # rather than invalidating paid-for work over a rename.
            on_disk.name = self._translation_name()
            return on_disk
        # The shared cache is not consulted here any more. It holds runs of segments — a
        # chapter at a time — rather than whole documents, so it is read in `_translated`
        # where the run is known. What is left here is this build's own artifact.
        return None

    def translate(
        self,
        segmented: SegmentedDocument,
        on_progress: Progress | None = None,
        only: list[Segment] | None = None,
    ) -> Translation:
        """Translate the whole text, or one run of it.

        `only` is a chapter. A book is translated a chapter at a time — nobody reads a
        novel the week they open it, and paying up front for chapters a reader will
        never reach is the single largest avoidable cost in the product.
        """
        cached = self.cached(segmented)
        if cached is not None and only is None:
            return cached

        run = only if only is not None else segmented.segments
        mapping = dict(cached.segments) if cached is not None else {}

        # Whatever this run already has, from a previous sitting or from somebody else
        # who read the same book. Only the rest is paid for.
        owed = [segment for segment in run if segment.id not in mapping]
        if owed:
            mapping |= self._translated(segmented, owed, on_progress)
        translation = Translation(
            name=self._translation_name(),
            document_hash=segmented.document_hash,
            source_language=segmented.language,
            target_language=self.target_language,
            provider=self.provider_name,
            model=self.model,
            style=self.style,
            segments=mapping,
        )
        translation.write(self.translation_path(self.resolved_out))
        return translation

    def _first_chapters(self, segmented: SegmentedDocument, count: int) -> list[Segment] | None:
        """What this build will translate now: the first `count` sections, and anything
        already paid for.

        A text that does not divide into chapters is translated whole: the machinery for
        paying by the chapter is worth nothing on an article, which costs five cents.

        The rationing is about money, so it only applies to chapters that cost something.
        A book whose English is already in the shared cache — the prose canon, bought once
        — arrives whole, rather than opening at chapter one with a row of Translate
        buttons against work that has been done and paid for.
        """
        from .render.builder import split_sections

        sections = split_sections(segmented)
        if len(sections) < 2:
            return None
        wanted = {sid for section in sections[:count] for sid in section.segment_ids}
        if not self.force:
            for section in sections[count:]:
                run = self.chapter_segments(segmented, section.number)
                if self.bought(segmented, run):
                    wanted |= set(section.segment_ids)
        return [segment for segment in segmented.segments if segment.id in wanted]

    def chapter_segments(self, segmented: SegmentedDocument, number: int) -> list[Segment]:
        """One chapter's segments, by its number on the contents page."""
        from .render.builder import split_sections

        for section in split_sections(segmented):
            if section.number == number:
                ids = set(section.segment_ids)
                return [segment for segment in segmented.segments if segment.id in ids]
        return []

    def _translated(
        self,
        segmented: SegmentedDocument,
        owed: list[Segment],
        on_progress: Progress | None,
    ) -> dict[str, str]:
        """One run of segments, from the cache where possible and the API where not.

        The cache is consulted per run rather than per document, so a book stopped at
        chapter four keeps those four when the fifth is asked for. Each run is written
        back under its own key, which is also what makes a build resumable: an
        interrupted chapter costs a chapter, not a book.
        """
        key = self.cache_key(segmented, owed)
        # `force` means force: it has to reach past the shared cache too, or "redo this
        # properly" quietly hands back the same answer that was being questioned.
        held = self.held_for(segmented, owed)
        wanted = [segment for segment in owed if segment.id not in held]

        if not wanted:
            self.reused.append("translation (cache)")
            if on_progress:
                on_progress(len(owed))
            return held

        if held:
            # A run that died partway is money already spent, and it is written down.
            # Only the rest is bought. The sentences either side of a batch are its
            # context, so a resumed run has slightly less of it than a fresh one — which
            # is a smaller price than translating the first eighty per cent again.
            self.notify(f"{len(held)} of {len(owed)} sentences were already translated.")
            if on_progress:
                on_progress(len(held))

        def keep(done: dict[str, str]) -> None:
            """Write down every batch as it lands, under the key for the whole run."""
            self.cache.put("translate", key, {"segments": held | done})

        # Positionally, as every other call to a provider here is: a double in a test
        # implements this protocol too, and naming the arguments would make its parameter
        # names part of the contract. Only the new one is a keyword.
        fresh: dict[str, str] = self.provider.translate(
            wanted,
            segmented.language,
            self.target_language,
            self.style,
            on_progress,
            on_batch=keep,
        )
        whole = held | fresh
        self.cache.put("translate", key, {"segments": whole})
        return whole

    def held_for(self, segmented: SegmentedDocument, run: list[Segment]) -> dict[str, str]:
        """Every sentence of this run already paid for, under whichever key it was bought.

        A chapter bought on its own sits under its own key, a book bought whole under
        the document's, and a run of several chapters under theirs. A run that spans
        chapters bought one at a time matches none of them by its own key alone, and
        would buy every one of them again. `force` still means force: it reaches past
        the shared cache too, or "redo this properly" hands back the answer in question.
        """
        if self.force:
            return {}
        wanted = {segment.id for segment in run}
        keys = [self.cache_key(segmented, run), self.cache_key(segmented)]
        from .render.builder import split_sections

        sections = split_sections(segmented)
        if len(sections) >= 2:
            for section in sections:
                ids = set(section.segment_ids)
                if ids & wanted:
                    chapter = [segment for segment in segmented.segments if segment.id in ids]
                    keys.append(self.cache_key(segmented, chapter))
        found: dict[str, str] = {}
        for key in dict.fromkeys(keys):
            for sid, text in self.held(key).items():
                if sid in wanted and sid not in found:
                    found[sid] = text
            if len(found) == len(wanted):
                break
        return found

    def held(self, key: str) -> dict[str, str]:
        """What has been translated for this run so far, whole or in part.

        A partial entry is the ordinary shape of an interrupted build: batches are
        written down as they finish, so what is here is what has been paid for.
        """
        stored = self.cache.get("translate", key)
        if isinstance(stored, dict) and isinstance(stored.get("segments"), dict):
            return {str(k): str(v) for k, v in stored["segments"].items()}
        return {}

    def bought(self, segmented: SegmentedDocument, run: list[Segment]) -> bool:
        """Whether every sentence of this run is already paid for.

        Not "is there an entry": since a dying run leaves a partial one, an entry alone
        no longer means a chapter is free, and treating it as free is how a reader gets
        charged for something a page told them they already had.
        """
        held = self.held_for(segmented, run)
        return bool(run) and all(segment.id in held for segment in run)

    @property
    def aligner(self) -> align_module.Aligner:
        if self._aligner is None:
            self._aligner = align_module.Aligner()
        return self._aligner

    def already_here(self, made: list[Translation]) -> list[Translation]:
        """Translations the folder already holds that this build did not make.

        Building the same text into a second language used to take the first one away:
        the reader was rendered from this run's translations alone, so `--to ru` left a
        text that could no longer be read in English — with the English still sitting in
        the folder, paid for, unreachable. A build adds a language rather than replacing
        one, and the reader's picker is where the two meet.

        This run's own work wins, matched on the three things that name a translation, so
        a rebuild of the same pair replaces rather than duplicates it.
        """
        theirs = {(t.provider, t.style, t.target_language) for t in made}
        out: list[Translation] = []
        for path in sorted((self.resolved_out / "translations").glob("*.json")):
            translation = read_artifact(Translation, path)
            if translation is None:
                continue
            if (translation.provider, translation.style, translation.target_language) in theirs:
                continue
            out.append(translation)
        return out

    def aligned(self, source: Document, segmented: SegmentedDocument) -> list[Translation]:
        """Ingest, segment and align every supplied translation."""
        from .align import parallel

        out: list[Translation] = []
        mine = parallel.parallel_key(source)
        for path in self.translation_files:
            document = ingest.load(str(path))
            target = segment_document(document, self.segmenter)
            name = document.title or (path.stem if isinstance(path, Path) else str(path))

            # Some pairs do not need matching: both sides were published against the same
            # verse numbering, so the correspondence is stated rather than inferred. Both
            # must say so and say the same thing — never guessed from the shapes.
            theirs = parallel.parallel_key(document)
            declared = mine is not None and mine == theirs
            if mine is not None and theirs is not None and mine != theirs:
                self.notify(f"{name} covers a different range; matching it instead.")

            key = self.cache.key(
                "align",
                document=segmented.document_hash,
                translation=target.document_hash,
                aligner=parallel.NAME if declared else self.aligner.name,
            )
            stored = self.cache.get("align", key)
            if isinstance(stored, dict):
                alignment = Alignment.model_validate(stored)
                self.reused.append(f"alignment ({name})")
            elif declared:
                # No embeddings, no model, nothing downloaded: the publisher already
                # numbered both sides and this copies that down.
                alignment = parallel.pair(segmented, target, name)
                self.cache.put("align", key, alignment.model_dump(mode="json"))
            else:
                self.notify(f"Matching {name} to the source…")
                alignment = self.aligner.align(segmented, target, name)
                self.cache.put("align", key, alignment.model_dump(mode="json"))
            alignment.write(
                self.resolved_out / "alignments" / f"{slug(name)}.{target.language}.json"
            )
            projected = align_module.to_translation(alignment, target)
            # The projection goes to disk beside a machine translation, not only into
            # this run's memory. The alignment alone cannot be re-rendered later: it
            # holds links, not text, and the published translation's segments are not
            # kept anywhere. Without this, `targum rebuild` reports a catalogue reader
            # as "never translated" and skips it — so the readers that cost nothing to
            # build were the only ones a design change could never reach.
            projected.write(
                self.resolved_out / "translations" / f"aligned.{slug(name)}.{target.language}.json"
            )
            out.append(projected)
        return out

    def authored(self, source: Document, segmented: SegmentedDocument) -> Translation | None:
        """A dialogue's English, which arrives with it and is never bought.

        The catalogue's rule, applied to a text targum wrote itself: where a translation
        already exists, no model is asked for one. A dialogue goes further than a
        catalogue pair — there is nothing to align either, because the English was
        written line by line against the Hebrew and the correspondence is a fact of the
        file rather than something to infer from shapes. One turn is one block is one
        segment, which is what `UNSPLIT` guarantees.
        """
        if not source.source.startswith("dialogue:"):
            return None
        from .dialogue import index as dialogue_index

        scene = dialogue_index.load(source.source.split(":", 1)[1])
        english = {f"b{n:04d}": turn.english for n, turn in enumerate(scene.turns) if turn.english}
        segments = {
            segment.id: english[segment.block_id]
            for segment in segmented.segments
            if segment.block_id in english
        }
        if not segments:
            return None
        return Translation(
            name=scene.english or scene.id,
            document_hash=segmented.document_hash,
            source_language=segmented.language,
            target_language="en",
            provider="authored",
            kind="authored",
            segments=segments,
        )

    def annotate(
        self, segmented: SegmentedDocument, vocalization: Vocalization | None = None
    ) -> Annotation | None:
        """Difficulty bands, when asked for, and how each word is said where that can be had."""
        if not self.difficulty:
            return None
        path = self.resolved_out / "annotation.json"
        self.notify("Finding each word's dictionary form…")
        # A Tanakh is banded against the Tanakh. wordfreq's Hebrew is contemporary
        # Israeli media, which asks the wrong question of scripture and answers it
        # confidently: vocabulary that is everywhere in Torah but has left modern usage
        # would show as "very hard" to somebody for whom it is the first thing to learn.
        # `for_source` returns None for everything else, and `Annotator` then takes its
        # own default, so no other text is affected.
        from .annotate import biblical, lemma

        # A reading needs vowels above the word and phonikud installed to turn them into
        # sounds. Where either is missing the annotation is made without readings and
        # named for that, so a machine with both redoes the text instead of inheriting
        # the gap — which costs nothing, since this runs here.
        pronouncer: annotate_module.Pronouncer | None = None
        if vocalization is not None and annotate_module.pronounceable(segmented.language):
            candidate = annotate_module.PhonikudPronouncer()
            if candidate.available()[0]:
                pronouncer = candidate

        annotator = self._annotator or annotate_module.Annotator(
            lemmatizer=lemma.for_source(self.source),
            bands=biblical.for_source(self.source),
            pronouncer=pronouncer,
        )
        if not self.force:
            existing = read_artifact(Annotation, path)
            # Same text, and made by the same annotator that would run now. Naming
            # the annotator is what lets a new word-level feature reach texts already
            # built: a file from before it names something else, so it is redone.
            # Redoing one is free — Stanza runs here, so nothing is fetched or spent.
            if (
                existing is not None
                and existing.document_hash == segmented.document_hash
                and existing.annotator == annotator.name
            ):
                self.reused.append("difficulty")
                return existing
        try:
            annotation = annotator.annotate(segmented, vocalization)
        except TargumError as error:
            # Losing word help is worth saying out loud; it is not worth losing the
            # reader over, since the translation is the greater part of the work.
            self.notify(f"{error.message} Building without it.")
            self.gloss = False
            return None
        annotation.write(path)
        return annotation

    def vocalize(self, segmented: SegmentedDocument) -> Vocalization | None:
        """The pointed form of each segment, for the reader's vowel toggle.

        Not asked for and not switched off: a Hebrew text gets the toggle, and one in any
        other language has nothing to toggle. The source's own pointing is used wherever
        it exists, so a Tanakh or a pointed poem needs no diacritizer at all.
        """
        if not vocalize_module.supports(segmented.language):
            return None
        self.notify("Adding vowel points…")
        path = self.resolved_out / "vocalization.json"
        if not self.force:
            existing = read_artifact(Vocalization, path)
            if existing is not None and existing.document_hash == segmented.document_hash:
                self.reused.append("nikkud")
                return existing

        engine = self._vocalizer
        if is_biblical(self.source):
            # Not merely unused: never loaded. A diacritizer has nothing to offer a text
            # it must not touch, and the ONNX model costs a second and a few hundred
            # megabytes to open for the privilege of being ignored.
            engine = None
        elif engine is None and vocalize_module.wants_pointing(segmented.segments):
            engine = vocalize_module.build()
        key = self.cache.key(
            "vocalize",
            document=segmented.document_hash,
            vocalizer=engine.name if engine else vocalize_module.SOURCE_ONLY,
            model=engine.model if engine else None,
        )
        stored = self.cache.get("vocalize", key)
        if isinstance(stored, dict) and not self.force:
            vocalization = Vocalization.model_validate(stored)
            self.reused.append("nikkud (cache)")
        else:
            try:
                vocalization = vocalize_module.vocalize_document(
                    segmented, engine, source=str(self.source)
                )
            except TargumError as error:
                # Vowels are a reading aid on top of a translation someone has already
                # paid for. Losing them is worth saying; it is not worth losing the build.
                self.notify(f"{error.message} Building without vowel points.")
                return None
            self.cache.put("vocalize", key, vocalization.model_dump(mode="json"))
        if vocalization.rejected:
            self.notify(
                f"Kept the source text for {len(vocalization.rejected)} sentence(s): "
                "the diacritizer changed letters, not just marks."
            )
        # A pointed edition arriving unpointed means the edition changed, and on this
        # shelf nothing fills the gap. Said out loud so a degraded upstream is caught in
        # a build log rather than by a reader. The threshold is `wants_pointing`'s own,
        # so a ketiv or two — bare on purpose — never triggers it.
        if is_biblical(self.source) and vocalize_module.wants_pointing(segmented.segments):
            self.notify(
                "Most of this text arrived without vowel points. Nothing was guessed; "
                "check the edition."
            )
        vocalization.write(path)
        return vocalization

    def glossary(
        self, annotation: Annotation | None, only: list[Segment] | None = None
    ) -> Glossary | None:
        """What the words mean, for the part of the text that was bought.

        `only` is the same run the translation was bought for. Meanings are the expensive
        half of a build and were looked up for the whole document however little of it
        had been paid for, so a novel bought a chapter at a time was glossed twenty times
        over in advance — Altneuland priced its first chapter at $0.21 and its meanings at
        $4.23, and the cap then refused the pair and the book could not be opened at all.
        The rest arrives as the rest is bought, and a lemma already looked up is free.
        """
        if annotation is None:
            return None
        from .annotate.gloss import AnthropicGlosses, build_glossary, unique_lemmas

        wanted = {segment.id for segment in only} if only is not None else None

        provider = AnthropicGlosses(self.gloss_model or self.model)
        if not self.gloss:
            # Nothing is bought, but what is already held is still handed over: a
            # meaning looked up in another text, or bought for this one by somebody
            # else, costs nothing to show, and a card should open with it rather than
            # with a button.
            held, _ = build_glossary(
                annotation, self.target_language, provider, cache=self.cache, buy=False
            )
            if not held.entries:
                return None
            held.write(glossary_path(self.resolved_out, self.target_language))
            self.reused.append("glossary (cache)")
            return held
        # Kept so what the meanings cost is counted with the rest. Glossing runs on its
        # own provider instance, so without this its spend is simply invisible.
        self._glosser = provider
        # By far the longest stage on a real article: one lookup per distinct dictionary
        # form, six hundred of them on a news piece. Said out loud and counted as it
        # goes, because a progress bar that stopped moving several minutes ago is
        # indistinguishable from a hang.
        total = len(unique_lemmas(annotation, only=wanted))
        done = 0
        self.notify(f"Looking up {total} word meanings…")

        def progress(step: int) -> None:
            nonlocal done
            done += step
            self.notify(f"Looking up word meanings… {min(done, total)} of {total}")

        # Published as it goes. The reader is already open and asking for this file
        # every few seconds, so holding it back until the last lemma meant every word
        # someone tapped showed a blank card for the length of the whole run.
        destination = glossary_path(self.resolved_out, self.target_language)

        def publish(partial: Glossary) -> None:
            partial.write(destination)

        glossary, paid = build_glossary(
            annotation,
            self.target_language,
            provider,
            only=wanted,
            cache=self.cache,
            on_progress=progress,
            on_batch=publish,
        )
        if paid:
            self.notify(f"{paid} word meanings looked up")
        else:
            self.reused.append("glossary")
        glossary.write(destination)
        return glossary

    def _translation_name(self) -> str:
        from .translate.prompts import language_name

        # The whole label is built here, so the reader template just prints it.
        return f"{language_name(self.target_language)} (machine, {self.style.value})"

    # -- driving -----------------------------------------------------------

    @property
    def spent(self) -> Usage:
        """What this build has really cost so far, across every provider it used."""
        total = getattr(self.provider, "spent", None) or Usage()
        glossing = getattr(self._glosser, "spent", None) if self._glosser else None
        return total + glossing if glossing else total

    def plan(self, chapters: int | None = None) -> Plan:
        """Ingest, segment, and price what a build would actually spend.

        `chapters` is what the build will buy, and so what the estimate is for. Pricing
        the whole book when only the first chapter is bought is not a rounding error: a
        novel prices at $7.58 against a real $0.38, the cap refuses it, and a book can
        never be opened at all — which is what happened when the chapter engine was
        built and the estimate was left alone.
        """
        document = self.ingest()
        plan = Plan(document=document)
        plan.segmented = self.segment(document)
        plan.cached_translation = self.cached(plan.segmented) if self.machine else None
        if self.machine and plan.cached_translation is None and hasattr(self.provider, "estimate"):
            from .render.builder import split_sections

            buying = (
                self._first_chapters(plan.segmented, chapters) if chapters else None
            ) or plan.segmented.segments
            # Priced net of the shared cache, the way the build will actually spend. A
            # book bought once — the prose canon — quoted at full price here, and the
            # cap refused a text that would have cost nothing to open.
            paid = self.held_for(plan.segmented, buying)
            owed = [segment for segment in buying if segment.id not in paid]
            plan.estimated_cost = self.provider.estimate(
                owed, plan.segmented.language, self.target_language, self.style
            )
            plan.chapters = len(split_sections(plan.segmented))
            plan.buying = len(buying)
            plan.buying_segments = list(buying)
        return plan

    def run(
        self,
        plan: Plan | None = None,
        on_progress: Progress | None = None,
        on_ready: Ready | None = None,
        chapters: int | None = None,
    ) -> Result:
        """Build the reader, then keep filling it in.

        `on_ready` fires the moment there is something worth reading — translated, banded
        and vowelled — and before the long wait for word meanings. Looking those up is
        most of the calls a build makes and none of what you need to start, so it happens
        afterwards, into a reader that is already open.
        """
        plan = plan or self.plan()
        assert plan.segmented is not None
        segmented = plan.segmented

        # How much of a book to pay for now. `chapters=1` translates the first section
        # and leaves the rest waiting, which is what stops a reader who opens a novel and
        # reads one chapter from buying nineteen they will never reach. None means all of
        # it, which is what the command line does and what a single-section text needs.
        only = self._first_chapters(segmented, chapters) if chapters else None

        translations: list[Translation] = []
        # Before anything is bought: a dialogue carries its own English, so a build of one
        # spends nothing and needs no network.
        written = self.authored(plan.document, segmented)
        if written is not None:
            written.write(self.resolved_out / "translations" / "authored.en.json")
            translations.append(written)
        if self.machine and written is None:
            translations.append(
                plan.cached_translation or self.translate(segmented, on_progress, only=only)
            )
        translations.extend(self.aligned(plan.document, segmented))
        if not translations:
            raise TargumError("Nothing to render.", "Pass --translation, or drop --no-machine")
        translations.extend(self.already_here(translations))

        # Vowels first. The bands do not need them, but the reading of each word is
        # worked out from them, and a stage cannot use what has not run yet.
        vocalization = self.vocalize(segmented)
        annotation = self.annotate(segmented, vocalization)

        def build_reader(glossary: Glossary | None, *, clean: bool) -> list[Path]:
            self.notify("Building the reader…")
            # Every target the folder holds, not only the one this build bought. A text
            # read in two languages keeps a glossary for each, and a reader carrying only
            # the newest would have nothing to say about the words of the other
            # translation — or, before the files were named for their language, would
            # have said it in the wrong one.
            books = glossaries_in(self.resolved_out)
            if glossary is not None:
                books[self.target_language] = glossary
            return render.render(
                plan.document,
                segmented,
                translations,
                self.resolved_out / "reader",
                annotation=annotation,
                glossaries=books,
                vocalization=vocalization,
                clean=clean,
                # The target whose meanings are still coming, and only on the first pass
                # of a build that ordered them.
                glossary_pending=(self.target_language if self.gloss and glossary is None else ""),
                covers=self.covers,
                reads=self.reads,
                siblings=self.siblings,
                whole=self.whole,
            )

        result = Result(
            out_dir=self.resolved_out,
            document=plan.document,
            segmented=segmented,
            translation=translations[0],
            translations=translations,
            annotation=annotation,
            vocalization=vocalization,
            pages=build_reader(None, clean=True),
            reused=self.reused,
            spent=self.spent,
        )
        if on_ready:
            on_ready(result)

        try:
            result.glossary = self.glossary(annotation, only=only)
        except TargumError as error:
            # The reader is already written and, where this is serving a page, already
            # open. Losing the meanings is worth saying; it is not worth taking back a
            # book someone is reading.
            self.notify(f"{error.message} Building without word meanings.")
            result.spent = self.spent
            return result
        if result.glossary is not None:
            # Bake them into the files too, so opening this reader again does not depend
            # on a server being there to hand them over.
            result.pages = build_reader(result.glossary, clean=False)
        result.spent = self.spent
        return result
