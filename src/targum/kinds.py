"""Which kinds of source are public by what they are (targum-internal#653).

David, 2026-11-06: a source is private unless its kind is listed public. Before this,
only a reader's home made a text private (`ledger.home_of`), so a new kind of source
whose author forgot to say it was private would be counted, pooled and exported the
first time it was built outside a home, and none of that can be taken back out of a
total. Now every writer of the corpus ledger and the language tables asks
`private_source` first, and a source it answers True for is **withheld**: no `texts`
row, no stage rows, no renderings or pairs, no fold, no place in the imports pool, no
export and no shelf proposal. A public source left off the list costs only its counts,
and the back office names it (`withheld_kinds`), so the fix is one line here.

"Public" here is about the kind, not the copy. A kind on the list is one whose privacy
the rules that were there before decide: where the text sits (a reader's home is
private) and what its licence allows. A link a reader pasted is `https`, a listed kind,
and is still private because it is in their home. A kind off the list is private
wherever it sits.

The kind is the source's scheme, `sefaria` of `sefaria:Psalms`, read once nothing
invisible is left in it (NFKC, no zero-width or control characters); something before
the first `:` that is not a scheme is a kind nobody can list, so private. A scheme is not
enough on its own: the ingester that read the text must be a family the code has
(`PUBLIC_SCHEME_INGESTERS`), so a new private fetcher that reads links is withheld even
though `https` is listed. A source that names no scheme is a file on this machine (an
upload, a photographed page, a recording, a curated video's audio), and for that the
ingester alone is the kind (`PUBLIC_INGESTERS`). An ingester on `PRIVATE` makes a text
private whatever its source says.

No imports: the ledger asks this on every write, and nothing here may load a fetcher.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

__all__ = [
    "PRIVATE",
    "PUBLIC_INGESTERS",
    "PUBLIC_KINDS",
    "PUBLIC_SCHEME_INGESTERS",
    "UNREADABLE",
    "family",
    "kind_of",
    "label",
    "private_source",
    "withheld_kinds",
]

#: The schemes whose texts are public by what they are, each audited against the
#: laptop's library, ledger and tables and against the code that writes a source
#: (targum-internal#653, 2026-11-06). Where a text sits and its licence still decide.
PUBLIC_KINDS = frozenset(
    {
        # A catalogue row named by its id (`Build.PUBLIC_SOURCES`), resolved to its source.
        "catalogue",
        # The scenes targum writes (`ingest/fetch/dialogue.py`, the dialogue writer).
        "dialogue",
        # Global Storybooks, CC BY (`ingest/fetch/globalstorybooks.py`).
        "globalstorybooks",
        # Project Gutenberg, public domain (`ingest/fetch/gutenberg.py`).
        "gutenberg",
        # A link: the news shelf, Wikinews, Global Voices, Ben-Yehuda, the web finds, and
        # every link a reader pastes, which their home keeps private.
        "http",
        "https",
        # A published translation carried beside its text (`ingest/fetch/published.py`).
        "published",
        # Sefaria behind its own allowlist; the parasha, the haftarah, the daily cycles
        # and a daf are all `sefaria:` (`parasha/cut.py`, `daily/cut.py`, `fetch/daf.py`).
        "sefaria",
        # The siddur, read through Sefaria (`ingest/fetch/siddur.py`).
        "siddur",
        # StoryWeaver, CC BY (`ingest/fetch/storyweaver.py`).
        "storyweaver",
        # A curated video shipped beside its English (`video/curate.py`, `fetch/video.py`).
        "video",
        # The weekly, targum's own writing (`ingest/fetch/weekly.py`, `weekly/entries.py`).
        "weekly",
        # Wikisource, public domain (`ingest/fetch/wikisource.py`).
        "wikisource",
    }
)

#: The ingesters that read a file on this machine, by family, for a source that names no
#: scheme. Every one of them reads what a reader uploads (and so sits in their home) or
#: what the operator built on a laptop (the curated videos' audio, a test's markdown).
PUBLIC_INGESTERS = frozenset(
    {
        "audio",  # a recording or a video's sound (`ingest/audio.py`)
        "epub",  # `ingest/epub.py`
        "markdown",  # `ingest/markdown.py`
        "pdf",  # `ingest/pdf.py`
        "picture",  # photographed pages (`ingest/picture.py`)
        "subtitles",  # `ingest/subtitles.py`
        "text",  # a .txt, and the text a reader types into the Add page (`ingest/plaintext.py`)
        "transcript",  # a conversation written down (`ingest/transcript.py`)
    }
)

#: Every ingester family the code has, for a source that names a scheme: a listed scheme
#: read by an ingester nobody listed is private too (qa-claude on #1122), so a new private
#: fetcher that reads links, `https` being listed, is withheld until it is listed here.
#: The file ingesters are among them, since a link can be a file (a PDF, a recording).
PUBLIC_SCHEME_INGESTERS = PUBLIC_INGESTERS | frozenset(
    {
        "daily",  # the daily cycles (`daily/cut.py`)
        "dialogue",  # `ingest/fetch/dialogue.py`
        "globalstorybooks",  # `ingest/fetch/globalstorybooks.py`
        "gutenberg",  # `ingest/fetch/gutenberg.py`
        "parasha",  # the parasha and the haftarah (`parasha/cut.py`)
        "published",  # `ingest/fetch/published.py`
        "sefaria",  # `sefaria/6`, the siddur's `sefaria/siddur/1`, a daf
        "storyweaver",  # `ingest/fetch/storyweaver.py`
        "url",  # a page (`ingest/url.py`)
        "url-feed",  # a feed's item (`ingest/url.py`)
        "url-text",  # a plain-text link (`ingest/url.py`)
        "video",  # `ingest/fetch/video.py`
        "weekly",  # `ingest/fetch/weekly.py`, and `weekly/measure`
        "wikisource",  # `ingest/fetch/wikisource.py`
    }
)

#: Kinds, and ingester families, that are private whatever else is listed: a fetcher that
#: reads a reader's own file rather than a public source, and is named here both as a
#: scheme and as its ingester's family. A course book's extract (`course:`, read by
#: `course/1`, `ingest/fetch/course.py`) is somebody's copy of a book in copyright
#: (targum-internal#652); nothing made from it is counted, pooled or exported, and no
#: request may name it (`fetch.addressable`).
PRIVATE: frozenset[str] = frozenset({"course"})

#: What `kind_of` answers for a source that names something before a `:` that is not a
#: scheme (`novel :1`, `ספר:1`): no kind anybody can list, so private.
UNREADABLE = "?"

#: A scheme as RFC 3986 spells one, and nothing else before the `:`.
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")


def _normal(text: str) -> str:
    """NFKC, then without control and format characters (a zero-width space, a byte-order
    mark, a NUL), then stripped: what a source says once nothing invisible is in it."""
    folded = unicodedata.normalize("NFKC", text)
    seen = "".join(c for c in folded if unicodedata.category(c) not in {"Cc", "Cf"})
    return seen.strip()


def kind_of(source: str) -> str:
    """The scheme a source names, lowercased; "" for a file on this machine (nothing but a
    path: a `/` comes before any `:`, or there is no `:`), or `UNREADABLE` where something
    stands before the first `:` that is not a scheme."""
    clean = _normal(source)
    colon = clean.find(":")
    if colon < 0:
        return ""
    slash = clean.find("/")
    if 0 <= slash < colon:
        return ""
    found = _SCHEME.match(clean)
    if found is None or found.end() != colon + 1:
        return UNREADABLE
    return found.group(1).lower()


def family(ingester: str) -> str:
    """An ingester's family: `sefaria` of `sefaria/siddur/1`, `url-text` of `url-text/2`."""
    return _normal(ingester).partition("/")[0].lower()


def private_source(source: str, ingester: str = "") -> bool:
    """Whether a built text is private by what it is, wherever it was built.

    A source that names a scheme is public only where the scheme is on `PUBLIC_KINDS`
    and, where the ingester that read it is known, its family is on
    `PUBLIC_SCHEME_INGESTERS`. A file (no scheme) is public only where its ingester's
    family is on `PUBLIC_INGESTERS`. Either is private wherever its kind or its
    ingester's family is on `PRIVATE`, and a source with no kind and no ingester, or a
    kind that does not read cleanly, is private: every doubt is.
    """
    kind = kind_of(source)
    named = family(ingester)
    if kind in PRIVATE or named in PRIVATE:
        return True
    if kind:
        if kind not in PUBLIC_KINDS:
            return True
        return bool(named) and named not in PUBLIC_SCHEME_INGESTERS
    return named not in PUBLIC_INGESTERS


def label(source: str, ingester: str = "") -> str:
    """What the back office names a withheld text by: its kind, never its source, which
    can be a path through a reader's home. `course:`, `https: read by foo`, or `a file
    read by foo`."""
    kind = kind_of(source)
    named = family(ingester)
    if kind == UNREADABLE:
        return "an unreadable kind"
    if kind:
        if kind in PUBLIC_KINDS and named and named not in PRIVATE:
            return f"{kind}: read by {named}"
        return f"{kind}:"
    return f"a file read by {named}" if named else "a file read by nothing named"


def withheld_kinds(root: Path) -> Counter[str]:
    """How many built texts under a library are withheld, by `label`: what the back office
    shows as "withheld: unknown kind", so a kind somebody forgot to list shows up.

    Reads every `document.json` under `root` and writes nothing. Counts folders, so a text
    held in two homes is two; nothing here names a reader, a text or a hash.
    """
    from .ledger import text_folders

    found: Counter[str] = Counter()
    for folder in text_folders(root):
        try:
            document = json.loads((folder / "document.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(document, dict) or not document.get("source"):
            continue
        source = str(document.get("source") or "")
        ingester = str(document.get("ingester") or "")
        if private_source(source, ingester):
            found[label(source, ingester)] += 1
    return found
