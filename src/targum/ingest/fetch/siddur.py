"""The weekday siddur, from Sefaria, one service at a time.

    targum build "siddur:Weekday, Shacharit"
    targum build "siddur:en:Weekday, Maariv"

Hebrew unless a language is named, like every other fetcher here.

**Why this is not `sefaria:`.** A book of the Tanakh is one address holding chapters of
verses, and `sefaria.py` fetches it in a single request. A siddur is not shaped like that
at all: `Siddur Ashkenaz` is a *complex* index — a tree of four hundred and fifty-six
named leaves, `Weekday, Shacharit, Pesukei Dezimra, Ashrei` and the rest — and the API
refuses any reference above a leaf. There is no request that returns a service. So the
tree is walked here, the leaves are fetched one by one, and the service is assembled from
them under its own headings.

**The edition is Metsudah 1981, on both sides, and that is what decides the scope.** It
is CC-BY both ways — the same publisher as the Chumash the shelf already reads, and a
linear translation, made to be read beside the Hebrew rather than instead of it. It
covers 170 of the weekday's 174 leaves and almost none of Shabbat or the festivals, so
the weekday is what is here. The Hebrew that does cover Shabbat, `Daat Siddur Ashkenaz`,
is public domain and has no English facing it under any licence this shelf may serve;
a Shabbat siddur would be Hebrew alone, and is not worth doing badly.

**Both sides are assembled from the same leaves, so the two pair for nothing.** The
ingester is named under `sefaria/`, which is what `align/parallel.py` reads as a promise
that the two sides are numbered by whoever published them — true here in the strongest
form, since the same walk of the same tree produces both. A leaf missing from either
side is dropped from both: keeping it would put a heading on one side that the other
does not have, and `parallel.pair` counts chapters.
"""

from __future__ import annotations

import json
from typing import Any

from ...errors import TargumError
from ...ids import block_id
from ...models import BlockKind, Document
from ..base import Paragraph, blocks_from_paragraphs, build_document, normalize
from ..url import get
from .sefaria import USABLE, plain

INDEX = "Siddur Ashkenaz"
SCHEMA = "https://www.sefaria.org/api/v2/raw/index/Siddur%20Ashkenaz"
TEXT = "https://www.sefaria.org/api/v3/texts/{ref}?version={version}"

DEFAULT_LANGUAGE = "he"

#: The pinned editions. Two entries rather than one because Sefaria files the Hebrew of a
#: bilingual edition under its own title: `The Metsudah siddur, 1981` is the Hebrew of the
#: book whose English is `Translation based on the Metsudah linear siddur…`.
VERSIONS = {
    "he": ("hebrew", "The Metsudah siddur, 1981"),
    "en": ("english", "Translation based on the Metsudah linear siddur, by Avrohom Davis, 1981"),
}

#: What may be asked for. The siddur is large and the walk is one request per leaf per
#: language, so an open-ended path would be a slow way to fetch nothing.
SERVICES = ("Weekday, Shacharit", "Weekday, Minchah", "Weekday, Maariv")


def split_identifier(identifier: str) -> tuple[str, str]:
    """`en:Weekday, Shacharit` -> ("en", "Weekday, Shacharit"). Hebrew by default."""
    rest = identifier
    if rest.lower().startswith("siddur:"):
        rest = rest.split(":", 1)[1]
    head, sep, tail = rest.partition(":")
    if sep and head.lower() in VERSIONS:
        return head.lower(), tail.strip()
    return DEFAULT_LANGUAGE, rest.strip()


def titled(node: dict[str, Any], language: str) -> str:
    """A node's own name, in the language being read.

    Sefaria writes a node's names as a list of alternatives with one marked primary per
    language, and a node that borrows a shared term carries none of its own.
    """
    wanted = "he" if language == "he" else "en"
    for title in node.get("titles") or []:
        if title.get("lang") == wanted and title.get("primary"):
            return str(title.get("text") or "")
    for title in node.get("titles") or []:
        if title.get("lang") == wanted:
            return str(title.get("text") or "")
    return str(node.get("heTitle" if wanted == "he" else "title") or node.get("key") or "")


def schema() -> dict[str, Any]:
    """The index's tree of nodes."""
    try:
        body = json.loads(get(SCHEMA))
    except json.JSONDecodeError as error:
        raise TargumError(
            "Sefaria sent something that is not JSON for the siddur.", str(error)
        ) from error
    found = body.get("schema")
    if not isinstance(found, dict):
        raise TargumError(f"Sefaria has no schema for {INDEX}.", str(body.get("error", "")))
    return found


def _descend(node: dict[str, Any], path: list[str]) -> dict[str, Any]:
    """The node one English path names, from the root."""
    here = node
    for step in path:
        children = here.get("nodes") or []
        found = next((child for child in children if titled(child, "en") == step), None)
        if found is None:
            names = ", ".join(titled(child, "en") for child in children)
            raise TargumError(
                f"The siddur has no '{step}' here.", f"What is here: {names}" if names else ""
            )
        here = found
    return here


def leaves(node: dict[str, Any], trail: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    """Every text-bearing node under this one, in reading order.

    Each comes back as the trail of English names above it — which is both the heading
    path a reader sees and, joined with commas under the index title, the address the
    text API answers to.
    """
    out: list[tuple[tuple[str, ...], str]] = []
    if "nodes" in node:
        for child in node["nodes"]:
            name = titled(child, "en")
            out.extend(leaves(child, trail + ((name,) if name else ())))
        return out
    return [(trail, f"{INDEX}, {', '.join(trail)}")]


def units(ref: str, language: str) -> list[str] | None:
    """One leaf's paragraphs, or None where this edition does not have it.

    None and empty are the same answer to the caller and are kept apart anyway: a leaf
    the edition does not carry comes back with no versions at all, and one it carries
    empty comes back with a version and nothing in it. Both are dropped; only the first
    is worth reading twice if this ever starts returning less than it used to.
    """
    tag, version = VERSIONS[language]
    url = TEXT.format(ref=_quote(ref), version=_quote(f"{tag}|{version}", safe="|"))
    try:
        body = json.loads(get(url))
    except json.JSONDecodeError as error:
        raise TargumError(
            f"Sefaria sent something that is not JSON for {ref}.", str(error)
        ) from error
    except TargumError:
        # A leaf this edition does not carry can answer with a 4xx rather than an empty
        # version list — `Weekday, Minchah, Post Amidah, Vidui and 13 Middot` does — and
        # from out here that is indistinguishable from the network being unhappy. Treated
        # as absent, because the two failures cannot end in the same place: a leaf really
        # missing is missing on both sides and is dropped from both, while a network that
        # is failing drops leaves from one build and not the next, and `parallel.pair`
        # counts chapters and refuses to write a thing.
        return None
    editions = body.get("versions") or []
    if not editions:
        return None
    edition = editions[0]

    licence = (edition.get("license") or "").strip()
    if licence not in USABLE:
        raise TargumError(
            f"'{version}' is licensed {licence or 'unclearly'}, which targum may not serve.",
            "Only public domain, CC0 and CC-BY editions go on the shelf.",
        )
    text = edition.get("text") or []
    return [normalize(plain(str(line))).strip() for line in text if isinstance(line, str)]


def _quote(text: str, safe: str = "") -> str:
    from urllib.parse import quote

    return quote(text, safe=safe)


def paragraphs_for(
    root: dict[str, Any], path: list[str], language: str
) -> tuple[list[Paragraph], dict[int, str]]:
    """One service, as headings and the lines under them, with each line's reference.

    Both languages are fetched for every leaf even though only one is kept, because what
    goes into the document is not "the leaves this side has" but "the leaves both sides
    have" — and that has to be the same answer whichever side is being built, or the two
    stop pairing.
    """
    other = "en" if language == "he" else "he"
    paragraphs: list[Paragraph] = []
    refs: dict[int, str] = {}
    shown: tuple[str, ...] = ()
    for trail, ref in leaves(_descend(root, path), tuple(path)):
        mine = units(ref, language)
        theirs = units(ref, other)
        if not mine or not theirs or len(mine) != len(theirs):
            continue
        # The headings above this leaf that the last one did not already print. A service
        # is three levels deep in places and one in others, so this is what keeps
        # Pesukei Dezimra from being written above every psalm inside it.
        inner = trail[len(path) :]
        for depth in range(len(inner)):
            if shown[: depth + 1] != inner[: depth + 1]:
                node = _descend(root, list(trail[: len(path) + depth + 1]))
                heading = titled(node, language) or inner[depth]
                paragraphs.append((BlockKind.heading, min(depth + 2, 6), heading))
        shown = inner
        for count, line in enumerate(mine, start=1):
            # `verse`, not `paragraph`: the segmenter never splits a verse, and a line of
            # the siddur has to stay whole to pair with the line facing it.
            refs[len(paragraphs)] = f"{ref} {count}"
            paragraphs.append((BlockKind.verse, None, line or "—"))
    return paragraphs, refs


class SiddurFetcher:
    # Under `sefaria/` because that prefix is what `align/parallel.py` reads as "these two
    # sides are numbered by whoever published them". 1: the weekday, Metsudah 1981.
    name = "sefaria/siddur/1"

    def load(self, identifier: str) -> Document:
        language, service = split_identifier(identifier)
        if not service:
            raise TargumError(
                "No service named.", f"Try: siddur:{SERVICES[0]}. Also: {', '.join(SERVICES[1:])}"
            )
        if service not in SERVICES:
            raise TargumError(
                f"targum does not carry '{service}'.",
                "The Metsudah edition covers the weekday and almost nothing else. "
                f"What there is: {', '.join(SERVICES)}.",
            )

        path = [step.strip() for step in service.split(",") if step.strip()]
        root = schema()
        node = _descend(root, path)
        paragraphs, refs = paragraphs_for(root, path, language)
        if not paragraphs:
            raise TargumError(f"Sefaria returned no text for {service}.")

        title = titled(node, language) or service
        paragraphs.insert(0, (BlockKind.heading, 1, title))
        refs = {index + 1: ref for index, ref in refs.items()}

        blocks = blocks_from_paragraphs(paragraphs)
        by_id = {block_id(index): ref for index, ref in refs.items()}
        for block in blocks:
            block.ref = by_id.get(block.id, "")

        return build_document(
            f"siddur:{service}" if language == DEFAULT_LANGUAGE else f"siddur:{language}:{service}",
            blocks,
            ingester=self.name,
            language=language,
            title=title,
        )
