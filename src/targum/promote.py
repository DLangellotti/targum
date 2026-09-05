"""A reader's build, proposed for the shelf — where the licence finally bites.

A private import is refused on nothing to do with permission (targum-internal#126): the
reader had lawful access, the copy is theirs, it never leaves their home. This module is
the one moment a private thing might become public, and so it is the one place the
licence recorded at ingest is *read*: a build whose source stands `free` or `owed` may be
proposed for the catalogue, so the next reader gets it for nothing; one whose source is
`exportable` may enter the corpus. `Standing.unknown` — which is most of the web — stays
private for ever, however good the text.

**Curated, not automatic.** "Every new entry: verify the record, never the look of the
thing" is in the roadmap, and a shelf that mirrored whatever readers pasted would stop
being a shelf. So a candidate is proposed by machine and accepted by a person in the back
office — with one exception: a source whose licence is certain by construction (the
public-domain fetchers: Gutenberg, Wikisource, Sefaria behind its own allowlist, the
siddur) is a catalogue row that simply was not there yet, and it promotes on completion.

**What accepting does, and reuses.** Nothing is rebuilt and nothing moves: the reader's
folder stays theirs. The translation they paid for is re-keyed into the shared cache the
way `targum warm` already does it — `Build.cache_key` gives a public source `owner=""`,
so the next reader's build finds the chapter already translated — and an entry is merged
into the catalogue file the way `targum parasha entries --write` merges, owning what the
build knows and leaving what a person later writes. What is **never** promoted: the
reader's words, notes and phrases (they are not in the folder), a conversation transcript
(half reader-authored — #161's fourth layer needs a grant this is not), and anything the
verdict cannot place.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import catalogue as catalogue_module
from .accounts import now
from .errors import TargumError
from .licensing import Standing, verdict
from .models import Annotation, Document, Translation, is_biblical, read_artifact
from .paths import write_atomic

if TYPE_CHECKING:
    from .accounts import Store
    from .cache import Cache
    from .serve import Job, Library

#: Sources whose licence is certain before anything is read: each fetcher refuses
#: anything it cannot serve under public-domain terms, so a build from one is a
#: catalogue row by construction and may promote itself.
PUBLIC_DOMAIN_FETCHERS = ("gutenberg:", "wikisource:", "sefaria:", "siddur:")


@dataclass(frozen=True)
class Proposal:
    """One build, as the back office sees it: what it is and why it may be promoted."""

    id: str
    job: str
    owner: int | None
    home: str
    folder: str
    source: str
    title: str
    author: str
    language: str
    words: int
    difficulty: int
    register: str
    kind: str
    licence: str
    standing: str
    catalogue_ok: bool
    corpus_ok: bool
    because: str
    state: str = "proposed"
    by: str = ""
    made: int = 0

    def state_row(self) -> dict[str, Any]:
        return asdict(self)


def licence_of(folder: Path, source: str) -> str:
    """The licence recorded on what was built, as a string `licensing.verdict` reads.

    A public-domain fetcher's is certain. A recording's rides in the manifest beside the
    reader. An article's is whatever the page said, which today is nothing — so it is
    `unknown`, and unknown is the honest answer, not a gap to paper over.
    """
    if source.startswith(PUBLIC_DOMAIN_FETCHERS):
        return "Public Domain"
    manifest = folder / "audio.json"
    if manifest.is_file():
        try:
            found = json.loads(manifest.read_text(encoding="utf-8")).get("licence")
        except (OSError, json.JSONDecodeError, AttributeError):
            found = None
        if found:
            return str(found)
    return ""


def eligible(licence: str) -> tuple[bool, bool, str]:
    """(may join the catalogue, may enter the corpus, why) — from the one verdict."""
    call = verdict(licence)
    catalogue_ok = call.standing in (Standing.free, Standing.owed) and call.derivatives
    return catalogue_ok, call.exportable, call.because


def candidate(library: Library, store: Store | None, job: Job) -> Proposal | None:
    """Whether this finished build may be proposed, and if so the proposal — written.

    Called after every build the queue finishes. It must never fail the build: a shelf
    decision is a separate thing from a reader getting their text, so the caller wraps
    it, and everything here that can be asked without raising is.
    """
    if store is None or job.kind != "build" or not job.reader or job.home is None:
        return None
    source = str(job.source)
    if not source or catalogue_module.matching(source) is not None:
        return None
    # A conversation is half the reader's own words; #161's fourth layer is a grant a
    # person gives, not a thing a build earns. And a file on the server is an upload,
    # whose terms nobody recorded.
    if source.endswith(".chat.json") or not (
        source.startswith(PUBLIC_DOMAIN_FETCHERS) or "://" in source
    ):
        return None
    folder = job.home / job.reader.split("/")[0]
    document = read_artifact(Document, folder / "document.json")
    if document is None:
        return None
    licence = licence_of(folder, source)
    catalogue_ok, corpus_ok, because = eligible(licence)
    if not catalogue_ok and not corpus_ok:
        return None
    words = sum(len(block.text.split()) for block in document.blocks)
    proposal = Proposal(
        id=secrets.token_hex(6),
        job=job.id,
        owner=job.owner,
        home=str(job.home),
        folder=folder.name,
        source=source,
        title=document.title or folder.name,
        author=document.author or "",
        language=document.language,
        words=words,
        difficulty=_difficulty(folder, document.language),
        register="biblical" if is_biblical(source) else "modern",
        kind="article" if "://" in source else "prose",
        licence=licence,
        standing=verdict(licence).standing.value,
        catalogue_ok=catalogue_ok,
        corpus_ok=corpus_ok,
        because=because,
        made=now(),
    )
    store.propose(proposal.state_row())
    if source.startswith(PUBLIC_DOMAIN_FETCHERS):
        # Certain by construction, so the operator is told rather than asked.
        try:
            accept(library, store, proposal.id, by="machine")
        except TargumError:
            # A box with no catalogue file to merge into keeps the proposal for a person.
            pass
    return proposal


def _difficulty(folder: Path, language: str) -> int:
    """The share of words a learner looks up, off the annotation already on disk —
    seconds, where `scripts/measure_difficulty.py` spends minutes because it has to
    annotate first. Zero where nothing can be measured, which the catalogue reads as
    unmeasured rather than easy."""
    annotation = read_artifact(Annotation, folder / "annotation.json")
    if annotation is None:
        return 0
    try:
        from .annotate.difficulty import hard_share
    except ImportError:
        # The `difficulty` extra is not installed; the operator can measure later.
        return 0
    try:
        return int(hard_share(annotation, language))
    except Exception:  # noqa: BLE001 - a measurement, never a reason to lose the proposal
        return 0


def warm_folder(folder: Path, cache: Cache, model: str | None = None) -> int:
    """Write the chapter-shaped public cache keys for one built text; how many.

    `targum warm`'s body, so accepting a proposal and warming a shelf are one rule. A
    translation is cached under the exact run of segments it was asked for, and served
    a book is bought a chapter at a time — so the reader's build under an owner-scoped key,
    or the command line's whole-book key, is a key the next reader never asks for. This
    writes the ones they will. Nothing is fetched and nothing is spent.
    """
    from .models import SegmentedDocument, Style
    from .pipeline import Build

    document = read_artifact(Document, folder / "document.json")
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if document is None or segmented is None:
        return 0
    machine = [
        t
        for path in sorted((folder / "translations").glob("*.json"))
        if (t := read_artifact(Translation, path)) is not None and t.provider != "aligned"
    ]
    if not machine:
        return 0
    translation = machine[0]
    builder = Build(
        document.source,
        target_language=translation.target_language,
        source_language=segmented.language,
        style=Style.natural,
        provider_name=translation.provider,
        model=model or translation.model or catalogue_module.BOUGHT_WITH,
        owner="",
    )
    written = 0
    for number in range(1, 500):
        run = builder.chapter_segments(segmented, number)
        if not run:
            break
        have = {s.id: translation.segments[s.id] for s in run if translation.segments.get(s.id)}
        if len(have) != len(run):
            continue  # a chapter that was never finished is not one to promise
        cache.put("translate", builder.cache_key(segmented, run), {"segments": have})
        written += 1
    return written


def _model_of(folder: Path) -> str:
    for path in sorted((folder / "translations").glob("*.json")):
        translation = read_artifact(Translation, path)
        if translation is not None and translation.provider != "aligned":
            return translation.model or ""
    return ""


def merge_into_catalogue(entry: dict[str, Any]) -> Path:
    """Put one entry into the catalogue file, owning what the build knows.

    Field by field over an existing row, the way `parasha entries --write` merges, so a
    blurb or an English title somebody later wrote survives the next acceptance of the
    same text. The catalogue is data and gitignored; this touches nothing public.
    """
    path = catalogue_module.catalogue_path()
    if path is None:
        raise TargumError(
            "No catalogue to merge into.",
            "Set TARGUM_CATALOGUE, or put one at ~/.targum/catalogue.json.",
        )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TargumError("That catalogue is not the shape targum reads.")
    rows: list[dict[str, Any]] = list(loaded.get("entries") or [])
    for index, row in enumerate(rows):
        if row.get("id") == entry["id"]:
            rows[index] = {**row, **{k: v for k, v in entry.items() if v not in ("", 0, [])}}
            break
    else:
        rows.append(entry)
    loaded["entries"] = rows
    write_atomic(path, json.dumps(loaded, ensure_ascii=False, indent=2) + "\n")
    catalogue_module.reload()
    return path


def accept(
    library: Library,
    store: Store,
    proposal_id: str,
    *,
    register: str = "",
    kind: str = "",
    credit: str = "",
    by: str = "person",
) -> dict[str, Any]:
    """Promote one proposal: re-key its translation to public, merge its entry.

    An `owed` licence needs a credit, the way `video/curate.py` refuses a build with no
    `--credit`: a CC-BY text on the public shelf must name who it is by, and a merge that
    let one through without would discharge nothing.
    """
    from .cache import Cache

    row = store.proposal(proposal_id)
    if row is None or row["state"] != "proposed":
        raise TargumError("No such proposal, or it was already decided.")
    if not row["catalogue_ok"]:
        raise TargumError(
            "This may enter the corpus, not the shelf: its licence does not allow a public copy."
        )
    if row["standing"] == Standing.owed.value and not credit:
        raise TargumError(
            "An owed licence needs a credit.", "Say who it is by, as they ask to be named."
        )
    folder = Path(str(row["home"])) / str(row["folder"])
    warmed = warm_folder(folder, Cache())
    entry = {
        "id": str(row["folder"]),
        "title": row["title"],
        "author": row["author"],
        "language": row["language"],
        "source": row["source"],
        "blurb": "",
        "english": "",
        "words": int(row["words"]),
        "tags": [],
        "translations": [],
        "kind": kind or row["kind"],
        "register": register or row["register"],
        "difficulty": int(row["difficulty"]),
        # Naming the model is what makes the next reader's build free: the cache is
        # keyed on it, and a build that did not name it would translate the book again.
        "model": _model_of(folder),
        "licence": row["licence"],
        "credit": credit,
    }
    merge_into_catalogue(entry)
    store.proposal_state(proposal_id, "accepted", by)
    return {"entry": entry["id"], "warmed": warmed, "corpus": bool(row["corpus_ok"])}


def decline(store: Store, proposal_id: str, *, by: str = "person") -> None:
    row = store.proposal(proposal_id)
    if row is None or row["state"] != "proposed":
        raise TargumError("No such proposal, or it was already decided.")
    store.proposal_state(proposal_id, "declined", by)
