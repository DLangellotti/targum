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

The kind is the source's scheme, `sefaria` of `sefaria:Psalms`. A source that names no
scheme is a file on this machine (an upload, a photographed page, a recording, a
curated video's audio), and for that the ingester that read it is the kind: the family
before the first `/`, so `picture` of `picture/2`. An ingester on `PRIVATE` makes a text
private whatever its source says, so a source rewritten by hand in `document.json` is
still caught by what read it.

No imports: the ledger asks this on every write, and nothing here may load a fetcher.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

__all__ = [
    "PRIVATE",
    "PUBLIC_INGESTERS",
    "PUBLIC_KINDS",
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

#: Kinds, and ingester families, that are private whatever else is listed: a fetcher that
#: reads a reader's own file rather than a public source. Empty today; a course book's
#: extract (`course`, targum#1121) is the first to come.
PRIVATE: frozenset[str] = frozenset()

#: A scheme as RFC 3986 spells one. A path has none (a `/` or a non-ASCII letter comes
#: before any `:`), so `targum-out/x:y/source.mp4` is a file, not the kind `targum-out`.
_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")


def kind_of(source: str) -> str:
    """The scheme a source names, lowercased; "" for a file on this machine, or none."""
    found = _SCHEME.match(source.strip())
    return found.group(1).lower() if found else ""


def family(ingester: str) -> str:
    """An ingester's family: `sefaria` of `sefaria/siddur/1`, `url-text` of `url-text/2`."""
    return ingester.strip().partition("/")[0].lower()


def private_source(source: str, ingester: str = "") -> bool:
    """Whether a built text is private by what it is, wherever it was built.

    True unless its kind is on `PUBLIC_KINDS` or, for a source that names no scheme, its
    ingester's family is on `PUBLIC_INGESTERS`; and True whatever is listed where either
    is on `PRIVATE`. A source with no kind and no ingester is private: every doubt is.
    """
    kind = kind_of(source)
    if kind in PRIVATE or family(ingester) in PRIVATE:
        return True
    if kind:
        return kind not in PUBLIC_KINDS
    return family(ingester) not in PUBLIC_INGESTERS


def label(source: str, ingester: str = "") -> str:
    """What the back office names a withheld text by: its kind, never its source, which
    can be a path through a reader's home. `course:`, or `a file read by foo`."""
    kind = kind_of(source)
    if kind:
        return f"{kind}:"
    named = family(ingester)
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
