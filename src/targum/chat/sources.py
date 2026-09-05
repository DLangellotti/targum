"""Where the chat may look for something to read: the publishers this box knows.

The list is data and it is private, the way the catalogue is: which feeds targum reads
and under what terms is editorial, and the public repository carries the code that
reads a list and not the list (`weekly/sources.py`, which the weekly draws on, is
gitignored for the same reason and is absent from a public checkout). So the chat reads
`sources.json` — named by `TARGUM_SOURCES`, else beside the catalogue — and a box with
no such file simply has nowhere to search.

The same list is what the server-side search is allowed to look at. `allowed_domains` is
a **relevance** list, not a permission list: its job is to keep the model on Hebrew a
reader would actually study, not to decide what a reader may bring to their own shelf.
What a reader imports is refused only on SSRF, format and spend (targum-internal#126).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from ..video.youtube import HOSTS as YOUTUBE_HOSTS

#: Sites that are not anybody's editorial secret and that the shelf already reads from:
#: the public-domain fetchers' homes, and YouTube's. Always in the search's domain list.
PUBLIC_HOSTS: tuple[str, ...] = (
    "www.sefaria.org",
    "sefaria.org",
    "he.wikisource.org",
    "www.gutenberg.org",
    "benyehuda.org",
    *sorted(YOUTUBE_HOSTS),
)

#: What one entry in `sources.json` may say it is.
KINDS = ("news", "podcast", "video", "text")

#: The API takes at most this many domains on one search tool.
MAX_DOMAINS = 64


@dataclass(frozen=True)
class Publisher:
    key: str
    name: str
    publisher: str
    #: An RSS or Atom address, or "" for a site that is searched but not pulled.
    feed: str = ""
    homepage: str = ""
    kind: str = "news"
    #: The licence as the publisher states it, recorded on what is imported from here
    #: and read at promotion — never enforced against the reader who imports.
    licence: str = ""
    language: str = "he"


def sources_path() -> Path | None:
    """Where the list is. A path named in the environment is the path, found or not —
    the same rule `catalogue_path` keeps, for the same reason."""
    named = os.environ.get("TARGUM_SOURCES", "").strip()
    if named:
        return Path(named) if Path(named).is_file() else None
    for path in (Path.home() / ".targum" / "sources.json", Path("/etc/targum/sources.json")):
        if path.is_file():
            return path
    return None


def load() -> list[Publisher]:
    """Every publisher in the file, in its order. Empty where there is no file."""
    path = sources_path()
    if path is None:
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw.get("publishers", []) if isinstance(raw, dict) else raw
    out: list[Publisher] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("key"):
            continue
        kind = str(row.get("kind") or "news")
        out.append(
            Publisher(
                key=str(row["key"]),
                name=str(row.get("name") or row["key"]),
                publisher=str(row.get("publisher") or ""),
                feed=str(row.get("feed") or ""),
                homepage=str(row.get("homepage") or ""),
                kind=kind if kind in KINDS else "news",
                licence=str(row.get("licence") or ""),
                language=str(row.get("language") or "he"),
            )
        )
    return out


def by_key(key: str) -> Publisher | None:
    return next((one for one in load() if one.key == key), None)


def allowed_domains() -> list[str]:
    """The hosts the server-side search may look at: the publishers' and the public ones.

    Deduplicated in first-seen order and capped at what the API takes, with the
    publishers first so a long list loses a reference site before it loses a paper.
    """
    hosts: list[str] = []
    for publisher in load():
        for address in (publisher.homepage, publisher.feed):
            host = (urlparse(address).hostname or "").lower()
            if host and host not in hosts:
                hosts.append(host)
    for host in PUBLIC_HOSTS:
        if host not in hosts:
            hosts.append(host)
    return hosts[:MAX_DOMAINS]
