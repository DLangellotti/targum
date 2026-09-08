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

#: Where a reader can be sent to read Hebrew that no publisher list carries: the
#: reference works, the science and language sites, the broadcaster, the papers outside
#: the feed list. Public code, because which sites hold Hebrew is nobody's secret — the
#: editorial choice of *which papers targum pulls* stays in `sources.json`.
#:
#: Every entry was fetched through `ingest.url` and parsed by `ingest.htmltext` on
#: 2026-09-07, and the numbers below are that measurement: words of running prose off
#: one real page, and what share of its letters were Hebrew. A site that would not
#: answer, or answered with nothing a parser could read, is in `UNREACHABLE` instead
#: with the reason — naming a site the fetch door cannot open only teaches the model to
#: offer a reader a page that will not open.
#:
#: The numbers are a moment, not a property. On 2026-09-08 kan.org.il and geektime.co.il
#: — 1,524 and 859 words the day before — answered the same door with a Cloudflare bot
#: check, after an afternoon of careless probing from the one address. The door has since
#: become a browser's (`ingest/url.py:BROWSER`) and knocks politely (`POLITE_S`), and the
#: box learns for itself which doors open (`accounts.Store.reach`); a count here is what
#: one page held once, not a promise.
#:
#: Named by the Hebrew subdomain wherever a project has one: `wikipedia.org` would put
#: every language's Wikipedia in the list, and the point is Hebrew.
READING_HOSTS: tuple[str, ...] = (
    # Reference. The largest bodies of free modern Hebrew prose there are.
    "he.wikipedia.org",  # 15,132 words, 99% Hebrew
    "he.wikivoyage.org",  # 4,926 words, 99%
    "he.wikiquote.org",  # 4,404 words, 99%
    # Science and knowledge, written for a general reader.
    "weizmann.ac.il",  # Davidson Institute, 1,150 words, 95%
    "hayadan.org.il",  # 288, 99%
    "geektime.co.il",  # 859, 92%
    # The broadcaster and the papers the feed list does not carry.
    "kan.org.il",  # 1,524 words, 100%
    "shakuf.co.il",  # 1,035, 100%
    "13tv.co.il",  # 773, 97%
    "calcalist.co.il",  # 542, 92%
    "inn.co.il",  # 1,597, 100%
    "ice.co.il",  # 1,292, 99%
    "one.co.il",  # 294, 100%
    # Religious and haredi Hebrew, a register the papers above do not write in.
    "kipa.co.il",  # 2,418 words, 100%
    "srugim.co.il",  # 2,195, 100%
    "kikar.co.il",  # 1,787, 100%
    "bhol.co.il",  # 1,047, 99%
    "yeshiva.org.il",  # 2,128, 96%
    "mechon-mamre.org",  # Tanakh and Mishneh Torah, 417, 100%
    # Song, language, health.
    "zemereshet.co.il",  # 185 words, 94%
    "safa-ivrit.org",  # 53, 100%
    "infomed.co.il",  # 29,706 words but 36% — Latin drug and disease names throughout
)

#: Sites worth reading that targum could not reach, kept as a record so they are not
#: proposed again without a probe. First written 2026-09-07 as "403 to any client, so it
#: is the address they refuse"; corrected 2026-09-08 when the box was probed and answered
#: identically to the laptop. The 403s are Cloudflare's bot check (`cf-mitigated:
#: challenge`), served to any client whose TLS handshake is not a browser's — a full
#: Chrome header set on plain curl gets the same page. Not an address block, which is
#: why two networks agreed. A browser's handshake opened kan.org.il from a burned laptop
#: address; whether it opens these from the box's clean one is what the box probe
#: (targum-internal#226) measures, and `reached` will record the answer on its own.
UNREACHABLE: dict[str, str] = {
    "hebrew-academy.org.il": "bot check; and robots.txt says Disallow: / to every "
    "crawler — the one host here to ask rather than fetch",
    "nli.org.il": "bot check",
    "davar1.co.il": "bot check; robots.txt allows articles",
    "mekomit.co.il": "bot check, intermittent; robots.txt allows articles",
    "ivrit.wzo.org.il": "bot check",
    "adult-education.education.gov.il": "TCP connects, TLS handshake hangs — the one "
    "here a proxy might fix. The Ministry of Education's easy-Hebrew newsletter, pointed "
    "and glossed, is the single best learner text found and the one targum cannot open",
    "chabad.org": "bot check (recorded on 2026-09-07 as its own 404; it is not)",
    "sport5.co.il": "fetches, parses to nothing — rendered in the browser",
    "clalit.co.il": "fetches, parses to nothing — rendered in the browser",
    "cbs.gov.il": "fetches, parses to nothing — rendered in the browser",
    "he.wikinews.org": "reachable, but dormant: 37 words on the front page",
    "he.wikibooks.org": "reachable, but thin: no page found over 150 words",
}

#: What one entry in `sources.json` may say it is.
KINDS = ("news", "podcast", "video", "text")

#: The API takes at most this many domains on one search tool.
MAX_DOMAINS = 64

#: Second-level suffixes under which a site's own name is the third label from the
#: right — walla.co.il, kan.org.il — so `site()` keeps three labels there and two
#: elsewhere. The Israeli ones, which is where the publishers are, plus the few generic
#: ones a feed might live under.
TWO_LABEL_SUFFIXES = frozenset(
    {"co.il", "org.il", "gov.il", "ac.il", "net.il", "muni.il", "co.uk", "org.uk", "com.au"}
)


def site(address: str) -> str:
    """The domain a search should be allowed on, from an address on it.

    A feed lives on a subdomain — rss.walla.co.il, rcs.mako.co.il — and the API's
    `allowed_domains` matches a bare domain against every subdomain of it, so the
    publisher's own domain is the one to name: naming the feed host would let the search
    read the RSS server and nothing the paper actually prints.
    """
    host = (urlparse(address).hostname or "").lower().strip(".")
    if not host:
        return ""
    labels = host.split(".")
    if labels[0] == "www" and len(labels) > 2:
        labels = labels[1:]
    keep = 3 if ".".join(labels[-2:]) in TWO_LABEL_SUFFIXES else 2
    return ".".join(labels[-keep:])


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
    publishers first so a long list loses a reference site before it loses a paper, and
    the reading hosts last so the fetchers' own homes outlive them. A publisher is named
    by its site (`site()`); the rest are named as written, because he.wikisource.org is
    a choice and wikisource.org would not be.

    The cap is the API's: `allowed_domains` takes 1-64 entries, and a list long enough
    to make the request too large comes back as a `request_too_large` search error
    rather than a refusal, which reads like the search failing for no reason.
    """
    hosts: list[str] = []
    for publisher in load():
        for address in (publisher.homepage, publisher.feed):
            host = site(address)
            if host and host not in hosts:
                hosts.append(host)
    for host in (*PUBLIC_HOSTS, *READING_HOSTS):
        if host not in hosts:
            hosts.append(host)
    return hosts[:MAX_DOMAINS]
