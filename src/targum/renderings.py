"""What a rendering beside the text is: a translation, a targum, or a commentary
(targum-internal#414).

A Torah carries three kinds of thing beside its Hebrew, and the reader treats them
differently. A **translation** (the Metsudah English, the 1875 Russian) is what the
column is for, and a reader picks one of them. A **targum** (Onkelos) and a
**commentary** (Rashi) are *companions*: they sit beside the verse together, like the
columns of a printed chumash, and each is turned on or off on its own.

Which is which is asked here once. The builder, the portion cut and the pipeline all
need the answer, and three hand-copied tests are how a fourth comes to disagree.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import Annotation, Segment, SegmentedDocument, Translation, read_artifact

#: A commentary is named by the work it comments on: "Rashi on Genesis". The same shape
#: `align.parallel` keys a commentary by, because it is the same question.
_COMMENTARY = re.compile(r"^(?P<who>[A-Z][A-Za-z]+) on (?P<book>.+)$")

#: What an unremarked verse holds. Sefaria has no comment on about a fifth of the verses
#: of the Torah, and the ingest keeps each one's place with this, the placeholder every
#: empty verse on the shelf gets. Beside the verse it is nothing to show.
EMPTY = "—"


def commentator(name: str) -> str:
    """Who wrote the commentary a rendering's name says it is, or "" for anything else."""
    found = _COMMENTARY.match((name or "").strip())
    return found.group("who") if found else ""


def is_commentary(name: str) -> bool:
    return bool(commentator(name))


def commentary_ref(source: str) -> str:
    """The commentary a `sefaria:` source names — `sefaria:en:Rashi on Genesis` is
    "Rashi on Genesis" — or "" where it names none.

    A rendering is named after its document's title, and Sefaria titles the Hebrew of
    Rashi in Hebrew (`רש"י על בראשית`). The name is what says a rendering is a
    commentary, so a commentary is named by its reference instead, which is the same on
    both sides.
    """
    text = str(source or "")
    if not text.startswith("sefaria:"):
        return ""
    ref = text.split(":", 1)[1]
    head, sep, tail = ref.partition(":")
    if sep and len(head) <= 3 and head.isalpha():
        ref = tail
    ref = ref.replace("_", " ").strip()
    return ref if is_commentary(ref) else ""


def is_companion(translation: Translation, beside: frozenset[str]) -> bool:
    """Whether a rendering sits beside the verse rather than in the translation column."""
    return translation.target_language in beside or is_commentary(translation.name)


def companion_key(translation: Translation, source_language: str, beside: frozenset[str]) -> str:
    """What a reader's on-or-off choice for this companion is kept under.

    The same on every text, so a choice made in Genesis holds in Exodus and in every
    portion: "targum" for Onkelos, "rashi" for Rashi in the text's own language and
    "rashi-en" for Rashi in English. "" for a translation, which is not a companion.
    """
    if translation.target_language in beside:
        return "targum"
    who = commentator(translation.name)
    if not who:
        return ""
    own = translation.target_language.split("-")[0] == source_language.split("-")[0]
    return who.lower() if own else f"{who.lower()}-{translation.target_language}"


def words_path(folder: Path, translation: Translation) -> Path:
    """Where a commentary's words live, beside the rendering itself."""
    from .ids import slug

    named = f"words.{slug(translation.name)}.{translation.target_language}.json"
    return folder / "translations" / named


def rendering_hash(translation: Translation) -> str:
    """What a commentary's words were read from. The rendering's text, not the book's:
    a new edition of Rashi beside the same Torah has to be read again."""
    digest = hashlib.sha256()
    for sid in sorted(translation.segments):
        digest.update(sid.encode())
        digest.update(b"\0")
        digest.update(translation.segments[sid].encode())
        digest.update(b"\0")
    return digest.hexdigest()


def as_segmented(translation: Translation, segmented: SegmentedDocument) -> SegmentedDocument:
    """A commentary as a text of its own, so the annotator can read it.

    Each line keeps the id of the verse it comments on, which is what lets its words be
    carried to a portion and drawn beside that verse exactly as the rendering is. An
    unremarked verse is left out: there is nothing in it to read.
    """
    segments: list[Segment] = []
    for segment in segmented.segments:
        text = translation.segments.get(segment.id, "")
        if not text or text.strip() == EMPTY:
            continue
        segments.append(segment.model_copy(update={"text": text, "language": None}))
    return SegmentedDocument(
        document_hash=rendering_hash(translation),
        language=translation.target_language,
        segmenter=segmented.segmenter,
        segments=segments,
    )


def words_in(folder: Path, translations: list[Translation]) -> dict[str, Annotation]:
    """Every commentary's words a build folder holds, by the rendering's name and
    language (`words_key`), and only where they were read from the text it holds now."""
    found: dict[str, Annotation] = {}
    for translation in translations:
        if not is_commentary(translation.name):
            continue
        words = read_artifact(Annotation, words_path(folder, translation))
        if words is not None and words.document_hash == rendering_hash(translation):
            found[words_key(translation)] = words
    return found


def words_key(translation: Translation) -> str:
    """A commentary's words are keyed by its name and its language: Rashi in Hebrew and
    Rashi in English share a name."""
    return f"{translation.name}|{translation.target_language}"


def with_commentaries(
    annotation: Annotation | None,
    words: dict[str, Annotation],
    only: list[Segment] | None = None,
) -> Annotation | None:
    """The text's words and its commentaries' together, for the meanings to be looked up
    in one pass: a word of Rashi is a Hebrew word, and its meaning is filed in the same
    glossary as the Torah's (targum-internal#414).

    Only for a whole build. One bought a chapter at a time is buying the text, and the
    commentary's words wait for the build that asks for all of it.
    """
    if annotation is None or not words or only is not None:
        return annotation
    merged = annotation.model_copy(update={"tokens": dict(annotation.tokens)})
    for key, held in words.items():
        for sid, tokens in held.tokens.items():
            merged.tokens[f"{sid}|{key}"] = tokens
    return merged
