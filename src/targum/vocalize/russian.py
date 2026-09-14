"""The Russian stress stage: silero-stress proposes, OpenRussian confirms (`stress.py`).

Shaped like the Hebrew vocalizers, so the reader's vowel toggle carries it unchanged: a
name compared with a stored pointing to know whether it is stale, a model identity for
the artifact, `available()` saying in one sentence what is missing, and `vocalize()`
returning the marked text per segment.

One difference: a homograph's stress is settled by the word's case and number, which the
tagger knows and this stage does not, so a Russian text is annotated first and the
annotation handed in (`pipeline.Build.stress`). Without one a homograph is left unmarked,
which is the rule's answer to any doubt.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from ..annotate import openrussian
from ..models import Annotation, Segment, SegmentedDocument, Vocalization
from . import stress

#: The package rather than a model on a hub: MIT, weights inside the wheel.
PACKAGE = "silero-stress"
CREDIT = "Silero Team"
LICENCE = "MIT"


def supports(language: str) -> bool:
    return (language or "").split("-")[0].lower() == "ru"


def _version() -> str:
    try:
        return importlib.metadata.version(PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return ""


class StressVocalizer:
    """Stress marks for Russian, where silero-stress and OpenRussian's tables agree."""

    def __init__(self, annotation: Annotation | None = None, accentor: Any = None) -> None:
        self.annotation = annotation
        self._accentor = accentor
        version = _version() or "none"
        # Both sources are in the name: a new silero or a new pin of the tables marks a
        # text differently, so either redoes it.
        self.name = f"stress/{PACKAGE}-{version}+{openrussian.NAME}"
        self.model: str | None = f"{PACKAGE} {version}"

    def available(self) -> tuple[bool, str]:
        if self._accentor is None and not _version():
            return False, "silero-stress is not installed (uv sync --extra stress)."
        if not openrussian.available():
            return (
                False,
                "OpenRussian's tables are not downloaded (targum models fetch openrussian).",
            )
        return True, "silero-stress and OpenRussian"

    def accentor(self) -> Any:
        if self._accentor is None:
            from silero_stress import load_accentor

            self._accentor = load_accentor("ru")
        return self._accentor

    def propose(self, text: str) -> dict[int, stress.Proposal] | None:
        return stress.read_proposal(text, self.accentor()(text))

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        lexicon = openrussian.load()
        tokens = self.annotation.tokens if self.annotation is not None else {}
        out: dict[str, str] = {}
        for segment in segments:
            proposals = self.propose(segment.text)
            if proposals is None:
                continue
            marked = stress.mark(segment.text, proposals, lexicon, tokens.get(segment.id, ()))
            if marked != segment.text:
                out[segment.id] = marked
        return out


def settled_by(engine: Any, annotation: Annotation | None) -> str:
    """What a stored marking records as its model: the engine, and the words it was
    settled with. A text whose words are read again is marked again, since a homograph
    may now be settled differently."""
    return f"{engine.model} · {annotation.annotator if annotation else 'untagged'}"


def current(
    existing: Vocalization | None, document_hash: str, engine: Any, annotation: Annotation | None
) -> bool:
    return (
        existing is not None
        and existing.document_hash == document_hash
        and existing.vocalizer == engine.name
        and existing.model == settled_by(engine, annotation)
    )


def mark_document(
    segmented: SegmentedDocument,
    engine: StressVocalizer,
    annotation: Annotation | None,
    source: str,
) -> Vocalization:
    from . import vocalize_document

    engine.annotation = annotation
    marked = vocalize_document(segmented, engine, source=source)
    marked.model = settled_by(engine, annotation)
    return marked
