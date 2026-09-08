"""The Hebrew of a daf, from Sefaria: the Mishnah, Rashi and Tosafot (targum-internal#193).

    targum build sefaria:daf:Berakhot
    targum build "sefaria:Rashi on Berakhot"
    targum build "sefaria:Tosafot on Berakhot"

Everything on a daf except the Aramaic Gemara is public-domain text and needs no OCR.
The Gemara is not: every Aramaic edition Sefaria holds is CC-BY-NC or ShareAlike, so it
comes from the Vilna scan instead (#191, #192). Splitting the children by how a text is
sourced rather than by where it sits on the page means one fetcher and one licence
assertion cover three of the four texts, and all three go through the mature Hebrew
pipeline unchanged.

**Editions are pinned and the licence is asserted, not assumed.** The Mishnah here is
`Mishnah, ed. Romm, Vilna 1913`: Romm is the Vilna printer, so the Mishnah arrives in the
same edition family as the daf rather than as a different recension. It is not the
Mishnah the Mishnah shelf reads — that is Torat Emet 357, pointed and paired with Kulp's
English (`sefaria.MISHNAH`) — which is why the daf's Mishnah has an identifier of its own,
`sefaria:daf:<tractate>`, rather than a second rule about `Mishnah <tractate>`. Rashi and
Tosafot are the `Vilna Edition`. Public domain or nothing: `sefaria.USABLE` admits CC-BY
and CC0 for the shelf, and this path does not, because a daf is one object and the day a
commentary arrives under a licence that travels is the day the whole daf carries it.

**`fill_in_missing_segments` is never sent.** `sefaria.py` says why: the API fills a
version's gaps from other versions and reports the licence you asked for. Pinned by a
test on the URL.

**Every block carries its anchor in `ref`.** A mishnah is `Mishnah Berakhot 1:1` — perek
and mishnah; a comment is `Rashi on Berakhot 2a:3:1` — daf, line and comment, as Sefaria
addresses it, which is what #194 lays beside the passage. `anchor_of` reads either back.

**The order of a daf is a contract, and this side owns it** because this side has the
perek structure. `Perakim` is the tractate's chapters as daf ranges, read from the index
(`alt_structs.Chapters`), and `reading_key` sorts any anchor — Mishnah, Gemara, or a
comment — into reading order: a mishnah stands before the Gemara that discusses it, and
a perek's Gemara ends where the index says it does, mid-daf. #192's Gemara blocks say
which mishnah they follow through the `mishnah` field of their anchor; where they do not
say, they follow the first, which is right for the opening of every perek and wrong only
until #192 marks its מתני׳ lines.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from ...errors import TargumError
from ...ids import block_id
from ...models import BlockKind, Document
from ..base import Paragraph, blocks_from_paragraphs, build_document, normalize
from ..url import get
from .sefaria import API, SefariaFetcher, hebrew_numeral, plain

#: What a daf's Hebrew may be: public domain, under either of Sefaria's spellings.
PUBLIC_DOMAIN = frozenset({"Public Domain", "PD"})

#: The Mishnah of the daf, in the daf's own edition family.
MISHNAH = "Mishnah, ed. Romm, Vilna 1913"

#: The commentaries this path reads, each pinned to the printing on the daf.
COMMENTARIES: dict[str, str] = {"Rashi": "Vilna Edition", "Tosafot": "Vilna Edition"}

#: How the commentators are written in a Hebrew heading.
HEBREW_NAMES: dict[str, str] = {"Rashi": "רש״י", "Tosafot": "תוספות"}

INDEX = "https://www.sefaria.org/api/v2/raw/index/{title}"

DAF_PREFIX = "daf:"

_COMMENTARY = re.compile(r"^(?P<who>[A-Za-z]+) on (?P<tractate>[A-Z][A-Za-z ]+?)\s*$")
_DAF = re.compile(r"^(?P<number>\d+)(?P<side>[ab])$")


def commentary_of(ref: str) -> tuple[str, str] | None:
    """`Rashi on Berakhot` -> ("Rashi", "Berakhot"), for the commentators this reads.

    A tractate, and not merely anything with a name. Rashi wrote on the Torah as well,
    and this pattern claimed that too: `Rashi on Genesis` came here, asked Sefaria for
    the Vilna edition — which exists for tractates and not for the Chumash — and was
    refused with "Sefaria has no 'Vilna Edition' of Rashi on Genesis". True, and about
    the wrong thing. What targum lacks there is a reader for a commentary numbered by
    chapter and verse (targum-internal#200), not an edition, and `sefaria.py` says so
    now that this declines it.
    """
    match = _COMMENTARY.match(ref.strip())
    if not match or match.group("who") not in COMMENTARIES:
        return None
    subject = match.group("tractate").strip()
    # Imported here rather than at the top: `sefaria.py` reads this module.
    from .sefaria import ENGLISH

    if subject in ENGLISH:
        return None
    return match.group("who"), subject


def daf_index(daf: str) -> int:
    """`2a` -> 3, `2b` -> 4: Sefaria's own count of amudim, which puts them in order."""
    match = _DAF.match(daf.strip())
    if not match:
        raise TargumError(f"'{daf}' is not a daf.", "A daf is a number and a side: 2a, 13b.")
    return int(match.group("number")) * 2 - 1 + (1 if match.group("side") == "b" else 0)


def hebrew_daf(daf: str) -> str:
    """`2a` -> ב., `2b` -> ב: — the notation every printed index of the Talmud uses."""
    match = _DAF.match(daf.strip())
    if not match:
        return daf
    return hebrew_numeral(int(match.group("number"))).replace("׳", "").replace("״", "") + (
        "." if match.group("side") == "a" else ":"
    )


@dataclass(frozen=True)
class Anchor:
    """Where a block sits on the daf, read off its ref."""

    #: "mishnah", "gemara" or "comment".
    kind: str
    tractate: str
    #: Which commentator, for a comment.
    who: str = ""
    perek: int = 0
    #: Which mishnah of its perek, for a mishnah; which mishnah it follows, for Gemara
    #: and comments that know. Zero where nobody has said.
    mishnah: int = 0
    daf: str = ""
    line: int = 0
    comment: int = 0


_MISHNAH_REF = re.compile(
    r"^Mishnah (?P<tractate>[A-Z][A-Za-z ]+?) (?P<perek>\d+):(?P<mishnah>\d+)$"
)
_COMMENT_REF = re.compile(
    r"^(?P<who>[A-Za-z]+) on (?P<tractate>[A-Z][A-Za-z ]+?) "
    r"(?P<daf>\d+[ab]):(?P<line>\d+):(?P<comment>\d+)$"
)
_GEMARA_REF = re.compile(
    r"^(?P<tractate>[A-Z][A-Za-z ]+?) (?P<daf>\d+[ab]):(?P<line>\d+)(?:/(?P<mishnah>\d+))?$"
)


def anchor_of(ref: str) -> Anchor | None:
    """The anchor a ref carries, or None for a ref this contract does not know.

    Gemara refs are #192's to write; the shape agreed here is Sefaria's `Berakhot 2a:5`,
    with `/3` after it where the block knows it follows the third mishnah of its perek.
    """
    text = ref.strip()
    match = _MISHNAH_REF.match(text)
    if match:
        return Anchor(
            "mishnah",
            match.group("tractate"),
            perek=int(match.group("perek")),
            mishnah=int(match.group("mishnah")),
        )
    match = _COMMENT_REF.match(text)
    if match:
        return Anchor(
            "comment",
            match.group("tractate"),
            who=match.group("who"),
            daf=match.group("daf"),
            line=int(match.group("line")),
            comment=int(match.group("comment")),
        )
    match = _GEMARA_REF.match(text)
    if match:
        return Anchor(
            "gemara",
            match.group("tractate"),
            daf=match.group("daf"),
            line=int(match.group("line")),
            mishnah=int(match.group("mishnah") or 0),
        )
    return None


@dataclass(frozen=True)
class Perakim:
    """A tractate's chapters as ranges of (daf index, line), first to last, inclusive."""

    tractate: str
    ranges: tuple[tuple[tuple[int, int], tuple[int, int]], ...]

    def perek_of(self, daf: str, line: int) -> int:
        """Which perek a line of the Gemara is in. The last perek runs to the end, so a
        line past every range is the last perek's rather than nobody's."""
        at = (daf_index(daf), line)
        for number, (first, last) in enumerate(self.ranges, start=1):
            if first <= at <= last:
                return number
        return len(self.ranges)


_WHOLE_REF = re.compile(r"(?P<daf1>\d+[ab]):(?P<line1>\d+)-(?P<daf2>\d+[ab]):(?P<line2>\d+)\s*$")


def perakim_from_index(index: dict[str, Any], tractate: str) -> Perakim:
    """The perek table, from the index's `Chapters` structure: `Berakhot 2a:1-13a:15`."""
    nodes = ((index.get("alt_structs") or {}).get("Chapters") or {}).get("nodes") or []
    ranges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for node in nodes:
        match = _WHOLE_REF.search(str(node.get("wholeRef") or ""))
        if not match:
            raise TargumError(
                f"Sefaria's index of {tractate} has a chapter with no daf range.",
                "The order of a daf rests on the index saying where each perek runs.",
            )
        ranges.append(
            (
                (daf_index(match.group("daf1")), int(match.group("line1"))),
                (daf_index(match.group("daf2")), int(match.group("line2"))),
            )
        )
    if not ranges:
        raise TargumError(
            f"Sefaria's index of {tractate} names no chapters.",
            "Only a tractate of the Bavli has the perek structure a daf is ordered by.",
        )
    return Perakim(tractate, tuple(ranges))


def perakim_of(tractate: str) -> Perakim:
    """The perek table of a tractate, from the index."""
    try:
        index = json.loads(get(INDEX.format(title=quote(tractate))))
    except json.JSONDecodeError as error:
        raise TargumError(
            f"Sefaria sent something that is not JSON for the index of {tractate}.", str(error)
        ) from error
    return perakim_from_index(index, tractate)


def reading_key(anchor: Anchor, perakim: Perakim) -> tuple[int, int, int, int, int, int]:
    """Where an anchor sorts in the daf's reading order.

    Perek first. Within a perek, by the mishnah a block belongs to or follows; the
    mishnah itself before the Gemara on it (kind 0 before 1), and a comment beside the
    line it comments on (kind 2, after the line). Gemara that has not said which mishnah
    it follows sorts as following the first.
    """
    if anchor.kind == "mishnah":
        return (anchor.perek, anchor.mishnah, 0, 0, 0, 0)
    perek = perakim.perek_of(anchor.daf, anchor.line)
    rank = 1 if anchor.kind == "gemara" else 2
    return (perek, anchor.mishnah or 1, rank, daf_index(anchor.daf), anchor.line, anchor.comment)


def _daf_payload(ref: str, version: str, depth: int) -> dict[str, Any]:
    url = API.format(ref=quote(ref), version=quote(f"hebrew|{version}", safe="|"))
    try:
        body = json.loads(get(url))
    except json.JSONDecodeError as error:
        raise TargumError(
            f"Sefaria sent something that is not JSON for {ref}.", str(error)
        ) from error
    editions = body.get("versions") or []
    if not editions:
        offered = [v.get("versionTitle", "") for v in (body.get("available_versions") or [])][:5]
        raise TargumError(
            f"Sefaria has no '{version}' of {ref}.",
            f"It offers: {', '.join(offered)}" if offered else "Check the reference.",
        )
    edition = editions[0]
    licence = (edition.get("license") or "").strip()
    if licence not in PUBLIC_DOMAIN:
        raise TargumError(
            f"'{version}' of {ref} is licensed {licence or 'unclearly'}, and a daf is "
            "public domain or nothing.",
            "The daf is one object; a commentary under a licence that travels would "
            "carry it onto the whole page.",
        )
    if body.get("isComplex") or body.get("textDepth") != depth:
        raise TargumError(
            f"{ref} is not shaped the way this reads it.",
            f"Expected a text {depth} deep; Sefaria says {body.get('textDepth')}.",
        )
    return {"edition": edition, "body": body, "licence": licence, "version": version}


def mishnah_document(payload: dict[str, Any], tractate: str) -> Document:
    """The tractate's Mishnah, a perek a heading and a mishnah a verse, in the Romm text."""
    body = payload["body"]
    perakim = payload["edition"].get("text") or []
    if perakim and isinstance(perakim[0], str):
        perakim = [list(perakim)]
    hebrew_title = str(body.get("heRef") or body.get("heTitle") or f"משנה {tractate}")
    paragraphs: list[Paragraph] = []
    refs: dict[int, str] = {}
    for number, mishnayot in enumerate(perakim, start=1):
        paragraphs.append((BlockKind.heading, 2, f"{hebrew_title} {hebrew_numeral(number)}"))
        for count, mishnah in enumerate(mishnayot, start=1):
            clean = normalize(plain(mishnah or "")).strip()
            refs[len(paragraphs)] = f"Mishnah {tractate} {number}:{count}"
            paragraphs.append((BlockKind.verse, None, clean or "—"))
    blocks = blocks_from_paragraphs(paragraphs)
    by_id = {block_id(index): text for index, text in refs.items()}
    for block in blocks:
        block.ref = by_id.get(block.id, "")
    return build_document(
        f"sefaria:{DAF_PREFIX}{tractate}",
        blocks,
        ingester=SefariaFetcher.name,
        language="he",
        title=hebrew_title,
    )


def commentary_document(payload: dict[str, Any], who: str, tractate: str) -> Document:
    """A commentary on the tractate, an amud a heading and a comment a paragraph.

    Sefaria hands a whole commentary over as amudim of lines of comments, and a single
    amud as lines of comments; both are read. An amud or a line with nothing on it is
    skipped and its number is not: the ref is Sefaria's address, so the count stays
    theirs. The heading is the traditional notation, ב. for 2a and ב: for 2b.
    """
    body = payload["body"]
    text = payload["edition"].get("text") or []
    sections = body.get("sections") or []
    # One amud asked for arrives flat: lines of comments, with the daf in `sections`.
    if sections and text and (not text or not text[0] or isinstance(text[0][0], str)):
        first = daf_index(str(sections[0]))
        amudim: list[tuple[int, Any]] = [(first, text)]
    else:
        amudim = [(index, amud) for index, amud in enumerate(text, start=1)]
    hebrew_name = HEBREW_NAMES.get(who, who)
    paragraphs: list[Paragraph] = []
    refs: dict[int, str] = {}
    for index, lines in amudim:
        daf = f"{(index + 1) // 2}{'a' if index % 2 else 'b'}"
        # The comments first, the heading only if there are any: 1a arrives as one line
        # with nothing on it, and a heading over nothing is a page that says "ב." twice.
        found: list[tuple[str, str]] = []
        for line_number, comments in enumerate(lines or [], start=1):
            for count, comment in enumerate(comments or [], start=1):
                clean = normalize(plain(comment or "")).strip()
                if clean:
                    found.append((f"{who} on {tractate} {daf}:{line_number}:{count}", clean))
        if not found:
            continue
        heading = f"{hebrew_name} {tractate_in_hebrew(body, tractate)} {hebrew_daf(daf)}"
        paragraphs.append((BlockKind.heading, 2, heading))
        for ref, clean in found:
            refs[len(paragraphs)] = ref
            paragraphs.append((BlockKind.paragraph, None, clean))
    blocks = blocks_from_paragraphs(paragraphs)
    by_id = {block_id(index): text for index, text in refs.items()}
    for block in blocks:
        block.ref = by_id.get(block.id, "")
    return build_document(
        f"sefaria:{who} on {tractate}",
        blocks,
        ingester=SefariaFetcher.name,
        language="he",
        title=f"{hebrew_name} {tractate_in_hebrew(body, tractate)}",
    )


def tractate_in_hebrew(body: dict[str, Any], tractate: str) -> str:
    """The tractate's Hebrew name off the response, `ברכות`, or its English failing that."""
    hebrew = str(body.get("heIndexTitle") or body.get("heTitle") or "")
    # `רש"י על ברכות`: the tractate is what follows "על".
    if " על " in hebrew:
        return hebrew.split(" על ", 1)[1].strip()
    return hebrew or tractate


def load(ref: str) -> Document | None:
    """A daf text, or None where the ref is not one — the ordinary Sefaria path then."""
    if ref.startswith(DAF_PREFIX):
        tractate = ref[len(DAF_PREFIX) :].strip()
        if not tractate:
            raise TargumError("No tractate named.", "Try: sefaria:daf:Berakhot")
        return mishnah_document(_daf_payload(f"Mishnah {tractate}", MISHNAH, 2), tractate)
    named = commentary_of(ref)
    if named is None:
        return None
    who, tractate = named
    return commentary_document(_daf_payload(ref, COMMENTARIES[who], 3), who, tractate)
