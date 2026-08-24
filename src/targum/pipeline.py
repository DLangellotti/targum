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
        aligner: align_module.Aligner | None = None,
        annotator: annotate_module.Annotator | None = None,
        vocalizer: vocalize_module.Vocalizer | None = None,
        notify: Notify | None = None,
    ) -> None:
        self.source = source
        self.target_language = target_language
        self.source_language = source_language
        self.style = style
        self.provider_name = provider_name
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
        self.difficulty = difficulty or gloss
        self.gloss = gloss
        self._annotator = annotator
        self._vocalizer = vocalizer
        self.provider: Any = build_provider(
            provider_name, model=model, batch_size=batch_size, effort=effort
        )
        self.model = getattr(self.provider, "model", None)
        # Whose build this is. Only used to scope the cache for a text that is not
        # public, so one person's upload is never re-served to another.
        self.owner = owner
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
            name = slug(path.stem if path.is_file() else (document.title or path.stem))
            root = self._out_root or (Path.cwd() / "targum-out")
            self._resolved_out = self._out or (root / f"{name}-{document.language}")
        return self._resolved_out

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
    PUBLIC_SOURCES = ("gutenberg:", "wikisource:", "http://", "https://", "catalogue:")

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
        """The segments of the first `count` sections, or None when there is one section.

        A text that does not divide into chapters is translated whole: the machinery for
        paying by the chapter is worth nothing on an article, which costs five cents.
        """
        from .render.builder import split_sections

        sections = split_sections(segmented)
        if len(sections) < 2:
            return None
        wanted = {sid for section in sections[:count] for sid in section.segment_ids}
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
        stored = None if self.force else self.cache.get("translate", key)
        if isinstance(stored, dict) and isinstance(stored.get("segments"), dict):
            self.reused.append("translation (cache)")
            if on_progress:
                on_progress(len(owed))
            return {str(k): str(v) for k, v in stored["segments"].items()}

        fresh: dict[str, str] = self.provider.translate(
            owed,
            segmented.language,
            self.target_language,
            self.style,
            on_progress,
        )
        self.cache.put("translate", key, {"segments": fresh})
        return fresh

    @property
    def aligner(self) -> align_module.Aligner:
        if self._aligner is None:
            self._aligner = align_module.Aligner()
        return self._aligner

    def aligned(self, segmented: SegmentedDocument) -> list[Translation]:
        """Ingest, segment and align every supplied translation."""
        out: list[Translation] = []
        for path in self.translation_files:
            document = ingest.load(str(path))
            target = segment_document(document, self.segmenter)
            name = document.title or (path.stem if isinstance(path, Path) else str(path))

            key = self.cache.key(
                "align",
                document=segmented.document_hash,
                translation=target.document_hash,
                aligner=self.aligner.name,
            )
            stored = self.cache.get("align", key)
            if isinstance(stored, dict):
                alignment = Alignment.model_validate(stored)
                self.reused.append(f"alignment ({name})")
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

    def annotate(self, segmented: SegmentedDocument) -> Annotation | None:
        """Difficulty bands, when asked for."""
        if not self.difficulty:
            return None
        path = self.resolved_out / "annotation.json"
        self.notify("Finding each word's dictionary form…")
        annotator = self._annotator or annotate_module.Annotator()
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
            annotation = annotator.annotate(segmented)
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
        if engine is None and any(
            not vocalize_module.is_fully_pointed(segment.text) for segment in segmented.segments
        ):
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
                vocalization = vocalize_module.vocalize_document(segmented, engine)
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
        vocalization.write(path)
        return vocalization

    def glossary(self, annotation: Annotation | None) -> Glossary | None:
        if not self.gloss or annotation is None:
            return None
        from .annotate.gloss import AnthropicGlosses, build_glossary, unique_lemmas

        provider = AnthropicGlosses(self.model)
        # Kept so what the meanings cost is counted with the rest. Glossing runs on its
        # own provider instance, so without this its spend is simply invisible.
        self._glosser = provider
        # By far the longest stage on a real article: one lookup per distinct dictionary
        # form, six hundred of them on a news piece. Said out loud and counted as it
        # goes, because a progress bar that stopped moving several minutes ago is
        # indistinguishable from a hang.
        total = len(unique_lemmas(annotation))
        done = 0
        self.notify(f"Looking up {total} word meanings…")

        def progress(step: int) -> None:
            nonlocal done
            done += step
            self.notify(f"Looking up word meanings… {min(done, total)} of {total}")

        # Published as it goes. The reader is already open and asking for this file
        # every few seconds, so holding it back until the last lemma meant every word
        # someone tapped showed a blank card for the length of the whole run.
        destination = self.resolved_out / "glossary.json"

        def publish(partial: Glossary) -> None:
            partial.write(destination)

        glossary, paid = build_glossary(
            annotation,
            self.target_language,
            provider,
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

    def plan(self) -> Plan:
        document = self.ingest()
        plan = Plan(document=document)
        plan.segmented = self.segment(document)
        plan.cached_translation = self.cached(plan.segmented) if self.machine else None
        if self.machine and plan.cached_translation is None and hasattr(self.provider, "estimate"):
            plan.estimated_cost = self.provider.estimate(
                plan.segmented.segments, plan.segmented.language, self.target_language, self.style
            )
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
        if self.machine:
            translations.append(
                plan.cached_translation or self.translate(segmented, on_progress, only=only)
            )
        translations.extend(self.aligned(segmented))
        if not translations:
            raise TargumError("Nothing to render.", "Pass --translation, or drop --no-machine")

        annotation = self.annotate(segmented)
        vocalization = self.vocalize(segmented)

        def build_reader(glossary: Glossary | None, *, clean: bool) -> list[Path]:
            self.notify("Building the reader…")
            return render.render(
                plan.document,
                segmented,
                translations,
                self.resolved_out / "reader",
                annotation=annotation,
                glossary=glossary,
                vocalization=vocalization,
                clean=clean,
                # True only on the first pass of a build that ordered one.
                glossary_pending=self.gloss and glossary is None,
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
            result.glossary = self.glossary(annotation)
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
