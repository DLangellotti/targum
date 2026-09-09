"""Fill the licence, credit and licence URL on every catalogue row, from what its source says.

`targum licences` answered "what may leave targum?" honestly on 2026-09-04: 42 of 546
sources, every one a recording, because the 501 texts on the shelf had no licence
recorded at all. Not because their terms were unknown — every family on the shelf is
pinned somewhere, and the fetchers refuse what they cannot serve — but because nothing
wrote the answer onto the row (targum-internal#115).

**From the source, never from memory.** Each rule below reads the terms where the source
states them, so the field is a claim that can be re-checked at `licence_url`:

- `sefaria:` and `siddur:` — the pinned Hebrew edition's `license` off the texts API, one
  small call per text, the same field the fetcher asserts before it reads a word.
- `https://benyehuda.org` — Project Ben-Yehuda's own terms: the texts are public domain
  (נחלת הכלל), and the project asks to be named.
- `https://he.wikinews.org`, `https://he.globalvoices.org` — the Creative Commons link in
  the page's own footer, read off the page, so a site that changes its terms changes the
  row on the next run rather than being remembered wrong.
- `video:` — the curation record, which already carries all three (`video/store.py`).
- `dialogue:` — targum's own writing, which `licensing.verdict` reads as nothing owed.
- `wikisource:` — the page's licence template, where it has one. The seven on the shelf
  have none, and they are left empty and listed rather than assumed public domain by
  selection, which is what `promote.py`'s table does and what this refuses to write down.

**Both sides of a targum.** The English beside the Hebrew is a separate work under a
separate licence and ships in the same reader, so every `translations` entry is filled
the same way. A Sefaria rendering names its language in the ref — `sefaria:en:Ruth` —
and the Hebrew side does not, which is the only difference between the two readers
(targum-internal#234).

A dry run prints what it would write, one line per entry with the rule that produced it,
and a count by standing. `--write` writes it back.

    .venv/bin/python scripts/backfill_licences.py
    .venv/bin/python scripts/backfill_licences.py --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.catalogue import catalogue_path  # noqa: E402
from targum.ingest.fetch import sefaria, siddur  # noqa: E402
from targum.licensing import verdict  # noqa: E402
from targum.video import store as video_store  # noqa: E402

#: Wikimedia refuses a request with no user agent, and asks that one say who is asking.
USER_AGENT = "targum/backfill_licences (https://targum.page)"

#: What the sites that state their terms in a footer call themselves for the credit.
SITES = {"he.wikinews.org": "Wikinews", "he.globalvoices.org": "Global Voices"}

BEN_YEHUDA = "benyehuda.org"

CC_LINK = re.compile(r"creativecommons\.org/licenses/(by(?:-[a-z]+)*)/(\d\.\d)")

#: What Hebrew Wikisource marks a page with when it says anything about its terms.
WIKISOURCE_TEMPLATES = (
    (re.compile(r"\{\{\s*(?:נחלת הכלל|PD[-a-z]*|Public domain)", re.IGNORECASE), "Public Domain"),
    (re.compile(r"\{\{\s*CC-BY-SA[-\d.]*", re.IGNORECASE), "CC BY-SA 3.0"),
)


@dataclass(frozen=True)
class Terms:
    licence: str
    credit: str = ""
    licence_url: str = ""
    #: Which rule read it, for the dry run's line.
    rule: str = ""


Fetch = Callable[[str], str]


def cc_name(kind: str, version: str) -> str:
    """`by-sa`, `3.0` as the shelf writes it: `CC BY-SA 3.0`."""
    return f"CC {kind.upper()} {version}"


def from_page(url: str, html: str) -> Terms | None:
    """The Creative Commons licence a page links in its footer, or None where it links
    none — which is not a page under no licence, only a page that does not say."""
    found = CC_LINK.search(html)
    if found is None:
        return None
    kind, version = found.groups()
    return Terms(
        cc_name(kind, version),
        SITES.get(urlparse(url).netloc, urlparse(url).netloc),
        f"https://creativecommons.org/licenses/{kind}/{version}/",
        "footer",
    )


def from_ben_yehuda() -> Terms:
    return Terms(
        "Public Domain", "Project Ben-Yehuda", f"https://{BEN_YEHUDA}/page/about", "benyehuda"
    )


def from_edition(edition: dict[str, Any], name: str, rule: str) -> Terms | None:
    """A Sefaria edition's terms, as the API states them: the same `license` field the
    fetcher refuses on, kept verbatim."""
    licence = str(edition.get("license") or "").strip()
    if not licence:
        return None
    title = str(edition.get("versionTitle") or "").strip()
    source = str(edition.get("versionSource") or "").strip()
    return Terms(
        licence,
        f"{title}, via Sefaria" if title else "Sefaria",
        source if source.startswith("http") else f"https://www.sefaria.org/{quote(name)}",
        rule,
    )


def first_verse(name: str) -> str:
    """One verse of a source, whatever shape its reference takes: a book (`Ruth`), a
    chapter range (`Mishnah Bikkurim 1-3`), a verse range (`Genesis 6:9-11:32`), or
    several of those (`Genesis 37:1-40:23; Numbers 7:1-17`). One verse is enough to ask
    the edition's licence, and a range is not a reference the texts API answers."""
    # A comma is a range separator only before a number — `Exodus 21:1-24:18, 30:11-16` —
    # and part of the title otherwise: `Mishneh Torah, Repentance`.
    head = re.split(r";|,\s*(?=\d)", name)[0].strip()
    head = re.split(r"(?<=\d)-", head)[0].strip()
    if ":" in head:
        return head
    if re.search(r"\s\d+$", head):
        return f"{head}:1"
    return f"{head} 1:1"


def from_sefaria(source: str, fetch: Fetch) -> Terms | None:
    """One verse of the pinned Hebrew edition, for the licence on it. A text whose
    Hebrew side is not on Sefaria — the Kuzari — pins no Hebrew edition and is None."""
    name = source.split(":", 1)[1]
    ref = first_verse(name)
    try:
        version = sefaria.version_for("he", ref)
    except Exception:  # noqa: BLE001 - a reference the pinning table does not know
        return None
    if not version:
        return None
    url = sefaria.API.format(ref=quote(ref), version=quote(f"hebrew|{version}", safe="|"))
    body = json.loads(fetch(url))
    editions = body.get("versions") or []
    return from_edition(editions[0], name, "sefaria") if editions else None


def from_sefaria_rendering(source: str, fetch: Fetch) -> Terms | None:
    """The same question asked of a *translation's* edition rather than the Hebrew's.

    A rendering's source carries the language — `sefaria:en:Ruth` — and `from_sefaria`
    hardcodes `he`, so it would ask for `en:Ruth 1:1`, which is not a reference. Split
    the language off and ask the pinning table for that side.
    """
    rest = source.split(":", 1)[1]
    language, _, name = rest.partition(":")
    if not name:
        return None
    ref = first_verse(name)
    try:
        version = sefaria.version_for(language, ref)
    except Exception:  # noqa: BLE001 - a reference the pinning table does not know
        return None
    if not version:
        return None
    tag = "hebrew" if language == "he" else "english"
    url = sefaria.API.format(ref=quote(ref), version=quote(f"{tag}|{version}", safe="|"))
    editions = json.loads(fetch(url)).get("versions") or []
    return from_edition(editions[0], name, f"sefaria:{language}") if editions else None


def from_siddur(source: str, fetch: Fetch) -> Terms | None:
    """The first leaf of the service, for the licence on the pinned Hebrew edition."""
    path = source.split(":", 1)[1].split(", ")
    tree = json.loads(fetch(siddur.SCHEMA)).get("schema") or {}
    node = siddur._descend(tree, path)
    tag, version = siddur.VERSIONS["he"]
    # The first few leaves, not only the first: a leaf this edition does not carry
    # answers 4xx (`siddur.units` says which), and the licence is the same on every
    # leaf it does.
    for _trail, ref in siddur.leaves(node, tuple(path))[:6]:
        url = siddur.TEXT.format(ref=quote(ref), version=quote(f"{tag}|{version}", safe="|"))
        try:
            editions = json.loads(fetch(url)).get("versions") or []
        except Exception:  # noqa: BLE001 - a leaf the edition lacks; try the next
            continue
        if editions:
            return from_edition(editions[0], siddur.INDEX, "siddur")
    return None


def wikisource_terms(wikitext: str) -> Terms | None:
    for pattern, licence in WIKISOURCE_TEMPLATES:
        if pattern.search(wikitext):
            return Terms(licence, "Wikisource", "", "wikisource")
    return None


def from_wikisource(source: str, fetch: Fetch) -> Terms | None:
    _kind, language, title = source.split(":", 2)
    query = urlencode(
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": title,
            "format": "json",
            "formatversion": "2",
        }
    )
    body = json.loads(fetch(f"https://{language}.wikisource.org/w/api.php?{query}"))
    pages = body.get("query", {}).get("pages") or []
    if not pages:
        return None
    revisions = pages[0].get("revisions") or [{}]
    wikitext = str(revisions[0].get("slots", {}).get("main", {}).get("content") or "")
    found = wikisource_terms(wikitext)
    if found is None:
        return None
    page = f"https://{language}.wikisource.org/wiki/{quote(title.replace(' ', '_'))}"
    return Terms(found.licence, found.credit, page, found.rule)


def from_video(source: str, videos: Path) -> Terms | None:
    record = videos / source.split(":", 1)[1] / "video.json"
    if not record.is_file():
        return None
    held = json.loads(record.read_text(encoding="utf-8"))
    licence = str(held.get("licence") or "").strip()
    if not licence:
        return None
    return Terms(
        licence, str(held.get("credit") or ""), str(held.get("licence_url") or ""), "video"
    )


def terms_for(source: str, fetch: Fetch, videos: Path, rendering: bool = False) -> Terms | None:
    """What the source says its terms are, by family; None where it says nothing.

    `rendering` says this is the *translation* beside a text rather than the text — the
    only difference is that a Sefaria rendering names its language in the ref and the
    Hebrew side does not (targum-internal#234).
    """
    if source.startswith("sefaria:"):
        return from_sefaria_rendering(source, fetch) if rendering else from_sefaria(source, fetch)
    if source.startswith("siddur:"):
        return from_siddur(source, fetch)
    if source.startswith("wikisource:"):
        return from_wikisource(source, fetch)
    if source.startswith("video:"):
        return from_video(source, videos)
    if source.startswith("dialogue:"):
        return Terms("targum", "", "", "own")
    if source.startswith("http"):
        host = urlparse(source).netloc
        if host == BEN_YEHUDA or host.endswith("." + BEN_YEHUDA):
            return from_ben_yehuda()
        if host in SITES:
            return from_page(source, fetch(source))
    return None


def over_the_network(url: str) -> str:
    import httpx

    answer = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=60.0, follow_redirects=True)
    answer.raise_for_status()
    return answer.text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="write the terms back")
    parser.add_argument(
        "--redo", action="store_true", help="re-read rows that already carry a licence"
    )
    parser.add_argument("--only", default="", help="a source prefix to limit the run to")
    args = parser.parse_args()

    path = catalogue_path()
    if path is None:
        print("no catalogue file", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    loaded = json.loads(text)
    entries = loaded["entries"] if isinstance(loaded, dict) else loaded
    videos = video_store.root()

    cache: dict[str, str] = {}

    def fetch(url: str) -> str:
        if url not in cache:
            cache[url] = over_the_network(url)
        return cache[url]

    filled = 0
    silent: list[str] = []
    failed: list[str] = []
    standings: dict[str, int] = {}
    for raw in entries:
        source = str(raw.get("source", ""))
        if args.only and not source.startswith(args.only):
            continue
        if raw.get("licence") and not args.redo:
            continue
        try:
            terms = terms_for(source, fetch, videos)
        except Exception as error:  # noqa: BLE001 - one source failing is a line, not a stop
            failed.append(f"{raw['id']}\t{type(error).__name__}: {error}")
            continue
        if terms is None:
            silent.append(f"{raw['id']}\t{source}")
            continue
        standing = verdict(terms.licence).standing.value
        standings[standing] = standings.get(standing, 0) + 1
        print(f"{raw['id']}\t{terms.rule}\t{standing}\t{terms.licence}\t{terms.credit}")
        if args.write:
            raw["licence"] = terms.licence
            raw["credit"] = terms.credit
            raw["licence_url"] = terms.licence_url
        filled += 1

    # The translation beside each text, which is a separate work under a separate licence
    # and ships in the same reader. `targum licences` read only the Hebrew's until
    # targum-internal#234, so nothing ever needed these filled and 88 of them were owed.
    for raw in entries:
        for beside in raw.get("translations") or []:
            source = str(beside.get("source", ""))
            if args.only and not source.startswith(args.only):
                continue
            if beside.get("licence") and not args.redo:
                continue
            name = f"{raw['id']} · {beside.get('name', '')}"
            try:
                terms = terms_for(source, fetch, videos, rendering=True)
            except Exception as error:  # noqa: BLE001 - one source failing is a line
                failed.append(f"{name}\t{type(error).__name__}: {error}")
                continue
            if terms is None:
                silent.append(f"{name}\t{source}")
                continue
            standing = verdict(terms.licence).standing.value
            standings[standing] = standings.get(standing, 0) + 1
            print(f"{name}\t{terms.rule}\t{standing}\t{terms.licence}\t{terms.credit}")
            if args.write:
                beside["licence"] = terms.licence
                beside["publisher"] = terms.credit
            filled += 1

    if args.write and filled:
        indent = 2 if "\n  " in text[:200] else None
        path.write_text(
            json.dumps(loaded, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8"
        )
    verb = "wrote" if args.write else "would write"
    print(
        f"\n{verb} {filled} rows: " + ", ".join(f"{k} {v}" for k, v in sorted(standings.items())),
        file=sys.stderr,
    )
    if silent:
        print(f"{len(silent)} say nothing about their terms, left empty:", file=sys.stderr)
        for line in silent:
            print(f"  {line}", file=sys.stderr)
    if failed:
        print(f"{len(failed)} could not be read:", file=sys.stderr)
        for line in failed:
            print(f"  {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
