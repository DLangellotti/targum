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
And a second (design.md §12, 2026-11-02): a find a reader opened, whose licence its source
states and clears `JOIN_BAR`, joins by itself, copied onto the shared shelf and naming
nobody (`join_find`); the back office lists those and takes one down (`take_down`).

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
from datetime import date
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
    # A find the reader opened joins the library by itself where its licence clears the
    # bar, and is never a proposal: a proposal row names the reader (design.md §12,
    # 2026-11-02).
    if (job.options or {}).get("via") == "find":
        join_find(library, store, job)
        return None
    source = str(job.source)
    if not source or catalogue_module.matching(source) is not None:
        return None
    # A conversation is half the reader's own words; #161's fourth layer is a grant a
    # person gives, not a thing a build earns. And a file on the server is an upload,
    # whose terms nobody recorded.
    if source.endswith(".chat") or not (
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


def _sentence(folder: Path) -> float:
    """Mean words per sentence, off the segmentation already on disk (targum-internal#382).

    The other half of a level, written into the row at the same moment as the share so
    an accepted text arrives on the level map measured. 0.0 where there is nothing to
    read, which the map counts as unmeasured, never as easy.
    """
    from .models import SegmentedDocument

    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if segmented is None:
        return 0.0
    try:
        from .annotate.difficulty import sentence_length
    except ImportError:
        return 0.0
    return sentence_length(segmented)


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
            # A row already here keeps the day it arrived. Accepting the same text again
            # is not it arriving again, and the merge below drops empty values anyway,
            # so an entry with no date of its own can never blank one that has one.
            rows[index] = {**row, **{k: v for k, v in entry.items() if v not in ("", 0, [])}}
            break
    else:
        # And a row arriving now is dated now (targum-internal#315). Here rather than at
        # each caller because this is the one door the catalogue grows through: a date
        # stamped in `accept()` alone would be missing from every other way a row is
        # added, and "what is new" would be a question about how a text got here.
        entry.setdefault("added", date.today().isoformat())
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
        "sentence": _sentence(folder),
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


# -- a find that joins the library (design.md §12, 2026-11-02) --------------------------
#
# A reader opened a find, a text targum found on the web, and its build is done. Where the
# licence its source states clears the bar, the build is copied onto the shared shelf and
# entered in the catalogue, credited to the outlet, naming nobody. Automatic, unlike the
# rest of this module, because nothing is left for a person to judge: the licence was read
# from the source, the outlet is the find's own, and the back office can take it down.

#: The licences a find may join on (David, 2026-11-02): CC0 and public domain, CC BY,
#: CC BY-SA, and their NonCommercial forms. Never ND, never all rights reserved, never
#: unknown, and never terms not on this list.
JOIN_BAR = "CC0 / public domain, CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA"

#: Files a reader's build keeps that are never copied: the page itself, which is rendered
#: again for the shelf; the shelf row's remembered answer, worked out again; a deck of the
#: reader's own words; and anything a door marks a folder with.
NOT_COPIED = frozenset({"reader", "shelf.json", "deck.apkg"})


def _flat(licence: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", (licence or "").lower()).strip()


def clears(licence: str) -> bool:
    """Whether a find on this licence may join the library: on `JOIN_BAR`, and allowed
    derivatives by `licensing.verdict`, which reads NoDerivatives first."""
    call = verdict(licence)
    if not call.derivatives or call.standing is Standing.unknown:
        return False
    flat = _flat(licence)
    words = flat.split()
    if call.standing is Standing.free:
        return any(word in flat for word in ("public domain", "publicdomain", "cc0")) or (
            "pd" in words
        )
    creative = "cc" in words or "creative commons" in flat or flat.startswith("cc ")
    attributed = "by" in words or "attribution" in flat
    return creative and attributed


def _deed(address: str) -> str:
    """A Creative Commons address said as a licence: "CC BY-SA 4.0", "CC0 1.0", "Public
    Domain Mark 1.0". "" for any other address."""
    from urllib.parse import urlparse

    parsed = urlparse(address.strip())
    host = (parsed.hostname or "").removeprefix("www.")
    if host != "creativecommons.org":
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "licenses":
        version = parts[2] if len(parts) > 2 else ""
        return f"CC {parts[1].upper()} {version}".strip()
    if len(parts) >= 2 and parts[0] == "publicdomain":
        version = parts[2] if len(parts) > 2 else ""
        name = {"zero": "CC0", "mark": "Public Domain Mark"}.get(parts[1], "")
        return f"{name} {version}".strip() if name else ""
    return ""


def page_licence(html: str) -> tuple[str, str]:
    """The licence a page states in its own markup, as (licence, the licence's address):
    `rel="license"` on a link or an anchor, a licence `meta`, or schema.org `license` in
    its JSON-LD, and only where it points at a Creative Commons licence or deed. A footer's
    words are not markup and are never read. ("", "") where the page states none."""
    import json as json_module
    from html.parser import HTMLParser

    found: list[str] = []
    scripts: list[str] = []

    class Reader(HTMLParser):
        in_ld = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            said = {name.lower(): (value or "") for name, value in attrs}
            if tag in ("link", "a") and "license" in said.get("rel", "").lower().split():
                found.append(said.get("href", ""))
            elif tag == "meta" and said.get("name", "").lower() in (
                "license",
                "dcterms.license",
                "dc.rights",
                "dcterms.rights",
            ):
                found.append(said.get("content", ""))
            elif tag == "script" and said.get("type", "").lower() == "application/ld+json":
                self.in_ld = True

        def handle_endtag(self, tag: str) -> None:
            if tag == "script":
                self.in_ld = False

        def handle_data(self, data: str) -> None:
            if self.in_ld:
                scripts.append(data)

    try:
        Reader().feed(html or "")
    except Exception:  # noqa: BLE001 - a page we cannot parse states nothing
        return "", ""

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            value = node.get("license")
            if isinstance(value, str):
                found.append(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for script in scripts:
        try:
            walk(json_module.loads(script))
        except ValueError:
            continue
    for address in found:
        said = _deed(address)
        if said:
            return said, address.strip()
    return "", ""


def read_page(url: str) -> str:
    """The page's HTML, for its licence tag: the copy read through the door in the last
    ten minutes where there is one, else one direct knock where robots.txt allows. Never
    through the proxy, never spending; "" where it cannot be had."""
    from .finds.robots import ROBOTS
    from .ingest.url import PAGES, fetch

    held = PAGES.held(url)
    if held is not None and held.is_html and held.via != "feed":
        return held.text
    if not ROBOTS.allowed(url):
        return ""
    try:
        got = fetch(url, proxy=False)
    except Exception:  # noqa: BLE001 - a page that will not come states nothing
        return ""
    return got.text if got.is_html else ""


def find_licence(found: Any, read: Any = read_page) -> tuple[str, str, str]:
    """A find's licence as (licence, where it was read, which statement): the article
    page's own tag first, then what the find carries from its source — YouTube's licence
    field, or the licence its outlet states for the whole site (David, 2026-11-02: that
    counts where the page has no tag). ("", "", "") where nothing was stated."""
    if getattr(found, "medium", "text") == "text":
        licence, address = page_licence(read(found.url))
        if licence:
            return licence, address, "page"
    if found.licence:
        return found.licence, found.licence_url, found.licence_from
    return "", "", ""


def joined_name(source: str) -> str:
    """The shelf's folder for an original, named from its address and nothing else."""
    import hashlib

    return "find-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


def _copy_build(folder: Path, into: Path) -> None:
    """The reader's finished artifacts, copied into a fresh folder: never the page, which
    is rendered again for the shelf, nor anything in `NOT_COPIED` or marked with a dot."""
    import shutil

    into.mkdir(parents=True)
    for item in folder.iterdir():
        if item.name in NOT_COPIED or item.name.startswith(".") or item.name.endswith(".part"):
            continue
        if item.is_dir():
            shutil.copytree(item, into / item.name)
        else:
            shutil.copy2(item, into / item.name)


def join_find(
    library: Library,
    store: Store | None,
    job: Job,
    *,
    read: Any = read_page,
    render: Any = None,
    today: date | None = None,
) -> dict[str, Any] | None:
    """Copy a finished find onto the shared shelf where its licence clears the bar;
    the catalogue entry, or None where nothing joined.

    Called from `candidate` for a build whose press was a find (`options.via == "find"`).
    Nothing is bought: the copy is the reader's artifacts, the page is rendered again from
    them (`render`, `cli.rebuild_one` unless a test passes one), and the translation is
    re-keyed for the next reader (`warm_folder`). No proposal row is written, and nothing
    written here names the reader, their home, the job or when it was opened.
    """
    from .finds import pool as finds_pool
    from .source_line import outlet_of
    from .weekly.feeds import link_key

    if store is None or job.kind != "build" or not job.reader or job.home is None:
        return None
    if (job.options or {}).get("via") != "find":
        return None
    try:
        find_id = int((job.options or {}).get("find") or 0)
    except (TypeError, ValueError):
        return None
    found = finds_pool.get(store, find_id) if find_id else None
    if found is None:
        return None
    source = link_key(found.url)
    if store.joined_source(source) is not None or catalogue_module.matching(source) is not None:
        return None
    licence, licence_url, licence_from = find_licence(found, read)
    if not clears(licence):
        return None
    folder = job.home / job.reader.split("/")[0]
    document = read_artifact(Document, folder / "document.json")
    if document is None:
        return None
    name = joined_name(source)
    shelf = library.shared / name
    if shelf.exists():
        return None
    library.shared.mkdir(parents=True, exist_ok=True)
    staging = library.shared / f".{name}.part"
    if staging.exists():
        import shutil

        shutil.rmtree(staging)
    _copy_build(folder, staging)
    outlet = outlet_of(found.publisher) or found.host.removeprefix("www.")
    (staging / "credit.json").write_text(
        json.dumps(
            {
                "outlet": outlet,
                "source": found.url,
                "licence": licence,
                "licence_url": licence_url,
                "licence_from": licence_from,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    staging.rename(shelf)
    if render is None:
        from .cli import rebuild_one

        def render(where: Path) -> None:
            rebuild_one(where, reads=None, covers=library.out / "thumbs")

    try:
        render(shelf)
    except Exception:
        import shutil

        shutil.rmtree(shelf, ignore_errors=True)
        raise
    from .cache import Cache

    warm_folder(shelf, Cache())
    words = sum(len(block.text.split()) for block in document.blocks)
    added = (today or date.today()).isoformat()
    entry: dict[str, Any] = {
        "id": name,
        "title": document.title or found.title,
        "author": "",
        "language": document.language,
        "source": found.url,
        "blurb": "",
        "english": "",
        "words": words,
        "tags": [],
        "translations": [],
        "kind": "article" if found.medium == "text" else "talk",
        "register": "modern",
        "difficulty": _difficulty(shelf, document.language),
        "sentence": _sentence(shelf),
        "model": _model_of(shelf),
        "licence": licence,
        "credit": outlet,
        "licence_url": licence_url,
        "licence_from": licence_from if licence_from != "page" else "",
        "added": added,
    }
    if not store.join(
        {
            "id": name,
            "source": source,
            "title": entry["title"],
            "outlet": outlet,
            "language": entry["language"],
            "licence": licence,
            "licence_url": licence_url,
            "licence_from": licence_from,
            "added": added,
        }
    ):
        # Another build of the same original got here first: its copy stands.
        import shutil

        shutil.rmtree(shelf, ignore_errors=True)
        return None
    merge_into_catalogue(entry)
    return entry


def remove_from_catalogue(entry_id: str) -> bool:
    """Take one entry out of the catalogue file; whether it was there."""
    path = catalogue_module.catalogue_path()
    if path is None:
        return False
    loaded = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = list(loaded.get("entries") or [])
    kept = [row for row in rows if row.get("id") != entry_id]
    if len(kept) == len(rows):
        return False
    loaded["entries"] = kept
    write_atomic(path, json.dumps(loaded, ensure_ascii=False, indent=2) + "\n")
    catalogue_module.reload()
    return True


def take_down(library: Library, store: Store, entry_id: str) -> bool:
    """The back office's one press on a find that joined: its catalogue entry and its
    shared copy go, and its row stays, `removed`, so the same original never joins again."""
    import shutil

    row = store.joined_one(entry_id)
    if row is None or row["state"] != "joined":
        return False
    remove_from_catalogue(entry_id)
    shelf = library.shared / entry_id
    if entry_id.startswith("find-") and shelf.is_dir():
        shutil.rmtree(shelf, ignore_errors=True)
    store.joined_removed(entry_id)
    return True
