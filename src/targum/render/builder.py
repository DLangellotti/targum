"""Turning artifacts into readable HTML.

The output is split into sections rather than written as one file. A full-length book
with several translations and, later, per-token annotation runs to tens of megabytes,
and a phone browser will not open it. Splitting is decided here, at the top of the
renderer, because it is not something that can be added later without a rewrite.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import shutil
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:  # imported for types only; the real import is inside each function,
    from ..catalogue import Entry  # because catalogue imports nothing from here
from markupsafe import Markup, escape

from ..annotate.base import BAND_NAMES, KIND_COLUMN, method_label
from ..models import (
    Annotation,
    BlockKind,
    Document,
    Glossary,
    SegmentedDocument,
    Translation,
    Vocalization,
    direction_for,
    is_biblical,
)
from ..translate.prompts import language_name
from ..vocalize import has_taamim, map_span, strip_nikkud

# A section beyond this many segments is split again. Sized so a section stays under a
# megabyte once M4 adds per-token annotation.
MAX_SEGMENTS_PER_SECTION = 400

TEMPLATES = Path(__file__).parent / "templates"
ASSETS = Path(__file__).parent / "assets"

# A run keeps its interior spaces, so "Magma Devs" isolates as one name rather than
# two words with a gap the bidi algorithm is free to reorder.
_LATIN_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .,:/'’&-]*[A-Za-z0-9]|[A-Za-z0-9]")
_RTL_RUN = re.compile(r"[֐-׿؀-ۿ][֐-ۿ\s.,'\"־-]*[֐-׿؀-ۿ]|[֐-׿]")


@dataclass(slots=True)
class Section:
    number: int
    title: str
    segment_ids: list[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return f"sec-{self.number:04d}.html"


def isolate(text: str, direction: str) -> Markup:
    """Wrap opposite-direction runs in <bdi>.

    Without this, a year or a Latin name inside a Hebrew sentence drags its punctuation
    to the wrong end of the line. The browser's own bidi algorithm is correct and still
    produces this, because it has no way to know where the embedded run ends.
    """
    pattern = _LATIN_RUN if direction == "rtl" else _RTL_RUN
    parts: list[str] = []
    position = 0
    for match in pattern.finditer(text):
        parts.append(str(escape(text[position : match.start()])))
        parts.append(f"<bdi>{escape(match.group())}</bdi>")
        position = match.end()
    parts.append(str(escape(text[position:])))
    return Markup("".join(parts))


def embed_json(payload: object) -> Markup:
    r"""JSON safe to sit inside a <script> element.

    The HTML parser ends the element at the first "</script" it meets, even inside a
    JSON string, so a translation containing that sequence would break out into
    markup. Splitting every "</" across an escape closes the door; "<\/" is the same
    string once JSON-decoded.
    """
    return Markup(json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))


def split_sections(segmented: SegmentedDocument) -> list[Section]:
    """Break at top-level headings, then on length."""
    sections: list[Section] = []
    current: Section | None = None
    has_body = False

    # A heading only opens a new section once the current one holds actual prose.
    # Otherwise a title, or a title and byline, would each become a section of its own.
    front_matter = {BlockKind.heading, BlockKind.byline}

    for segment in segmented.segments:
        starts_section = (
            segment.kind is BlockKind.heading
            and (segment.level or 1) <= 2
            and current is not None
            and has_body
        )
        too_long = current is not None and len(current.segment_ids) >= MAX_SEGMENTS_PER_SECTION
        if current is None or starts_section or too_long:
            title = segment.text if segment.kind is BlockKind.heading else ""
            current = Section(number=len(sections) + 1, title=title)
            sections.append(current)
            has_body = False
        has_body = has_body or segment.kind not in front_matter
        if not current.title and segment.kind is BlockKind.heading:
            current.title = segment.text
        current.segment_ids.append(segment.id)

    for section in sections:
        if not section.title:
            section.title = f"Section {section.number}"
    return sections


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        # Unconditionally, not select_autoescape: that helper matches on the final
        # extension, and these templates end in .j2, so it silently escaped nothing.
        # Every template renders text that can come from a fetched web page.
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["isolate"] = isolate
    env.globals["asset"] = _asset
    env.globals["data_uri"] = _data_uri
    env.globals["hebrew_face"] = _hebrew_face
    return env


def _strip(name: str, text: str) -> str:
    """An asset with its comments taken out, for baking into a page.

    The comments in these files are for whoever reads them here, and a reader carries
    its whole stylesheet and script inlined — so every one of them is paid for again on
    every page, and a book of 151 chapters is 151 copies. Across the set they are 30% of
    what gets baked in: 129 kB a page before compression, and near a megabyte on disk
    per book. The source keeps them; the page does not need them.

    Whole lines only, and nothing is ever joined. Two things follow from that, and both
    are the reason this is thirty lines rather than a dependency:

    * A comment that opens a line cannot be inside a string, because no asset carries a
      template literal that spans a line — `test_render.py` holds that to be true rather
      than trusting it, since the day one appears this would quietly eat it.
    * Because every removal takes a whole line, nothing that stood on two lines ends up
      on one, so JavaScript's semicolon insertion sees exactly what it saw before.

    Trailing comments are left alone. Telling `//` in code from `//` inside a string or
    a regular expression needs a parser, and there are 78 bytes of them in the whole set.
    """
    js = name.endswith(".js")
    kept: list[str] = []
    inside = False
    for line in text.splitlines():
        bare = line.strip()
        if inside:
            if "*/" not in bare:
                continue
            inside = False
            rest = line.split("*/", 1)[1]
            if rest.strip():
                kept.append(rest)
            continue
        if not bare:
            continue
        if js and bare.startswith("//"):
            continue
        if bare.startswith("/*"):
            head = line.split("/*", 1)[1]
            if "*/" not in head:
                inside = True
                continue
            rest = head.split("*/", 1)[1]
            if rest.strip():
                kept.append(rest)
            continue
        kept.append(line)
    if inside:
        # Loud, because the alternative is a page missing the second half of its script.
        raise ValueError(f"{name}: a block comment is never closed")
    return "\n".join(kept) + "\n"


@cache
def _asset(name: str) -> Markup:
    """One stylesheet or script, ready to bake in.

    Cached like `_data_uri` and for the same reason: the same two files are asked for on
    every page of every section, and rewriting a book asks 151 times. The cost is that a
    running `targum serve` reads each asset once — editing one while it is up needs a
    restart to see it.
    """
    return Markup(_strip(name, (ASSETS / name).read_text(encoding="utf-8")))


# The Hebrew faces, one per register, and why they are in the page rather than named.
#
# The stack asked for "Frank Ruhl CLM" and "Taamey Frank CLM" and never got either: they
# are not on a stock machine, so every reader fell through to New Peninim MT — which has
# no accents at all, nor meteg, paseq, sof pasuq or qamats qatan. That was invisible while
# the Tanakh arrived stripped of its accents. The moment it did not, every letter carrying
# one was borrowed from whatever font the browser could find, and Safari substitutes the
# whole cluster, so the letter changed size too. A font a page merely asks for is a font
# some readers do not have; the only fix is to carry it.
#
# Two faces because the shelves read differently: Taamey Frank CLM is cut for pointed and
# accented scripture, and its accents are designed rather than tolerated — and its letters
# hold one size, which Taamey Ashkenaz beside it in the same collection does not: its shin,
# mem and final mem draw visibly larger than their neighbours, which on a page of verses
# reads as broken text. Frank Ruhl Libre
# is a modern cut of the Hebrew book serif, for a newspaper — and a serif, so a Hebrew
# column and the Latin one beside it still read as one document, which is what §5 asks.
# Taamey Frank CLM is Yoram Gnat's, GPL with the font-embedding exception that says a
# document carrying the font is not itself covered — which is exactly what a reader is.
# Frank Ruhl Libre is OFL, which permits the same thing outright. The exception is per
# author and not per project: Taamey David CLM sits in the same collection and does not
# carry it, because its glyphs are Maxim Iorsh's. Check before swapping either of these.
BIBLICAL_FACE = ("Taamey Frank CLM", "fonts/TaameyFrankCLM-Medium.woff2")
MODERN_FACE = ("Frank Ruhl Libre", "fonts/FrankRuhlLibre-Regular.woff2")

# What a page falls back through if it somehow carries no face of its own. Kept in step
# with `--reading-hebrew` in reader.css.
_FALLBACK = '"Taamey Frank CLM", "Frank Ruhl CLM", "SBL Hebrew", "New Peninim MT", David, serif'


@cache
def _hebrew_face(biblical: bool = False) -> Markup:
    """The page's own Hebrew face, carried rather than hoped for.

    Emitted per page instead of from the stylesheet because a page needs one of the two
    and paying for both would double the cost of the thing for no reader's benefit.
    """
    # `block`, not `swap`: the face is in the page, so there is nothing to wait for and
    # nothing to gain from painting a fallback first — and a fallback that is painted is
    # a fallback the page gets measured in. reader.js measures again when the font
    # arrives; this is what keeps there being nothing to measure twice.
    family, file = BIBLICAL_FACE if biblical else MODERN_FACE
    return Markup(
        "<style>"
        f'@font-face{{font-family:"{family}";'
        f'src:url({_data_uri(file)}) format("woff2");font-display:block}}'
        f':root{{--reading-hebrew:"{family}", {_FALLBACK}}}'
        "</style>"
    )


@cache
def _data_uri(name: str) -> str:
    """An asset as a `data:` URI, for the places only a URL will do.

    A built reader is one file in a folder of its own — there is nowhere to put a
    sibling icon and nothing serving it, so the icons ride inside the page. They are
    small enough (the whole set is under 3 kB) not to matter beside the inlined CSS.
    Cached because the same three icons are asked for on every page of every section.
    """
    path = ASSETS / name
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if mime == "image/svg+xml":
        mime += ";charset=utf-8"
    # Not every machine's mimetypes knows woff2, and a font served as octet-stream is a
    # font some browsers decline to use.
    if path.suffix == ".woff2":
        mime = "font/woff2"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def learn_page(token: str) -> str:
    """The page you land on: carry on, what you have, what you know.

    In that order on purpose. Most visits are somebody returning to a text rather than
    looking for a new one, and the brand rule is that the reader is a reader rather than
    a player — so the numbers sit under the thing you came to do, not over it.

    Nothing about the reader is baked in. The shelf comes from `/readers` and the words
    from the browser's own stores, which is what lets one rendered page serve everybody.
    """
    from ..catalogue import CATALOGUE
    from ..translate.prompts import OFFERED, language_name

    return (
        _environment()
        .get_template("learn.html.j2")
        .render(
            token=token,
            languages=[(code, language_name(code)) for code in OFFERED],
            # Enough of the catalogue to suggest the next thing to read and then to
            # build it: a title and a line about it, the two numbers that say whether it
            # is the right size and the right difficulty for this reader, and what a
            # build is started from. The last two are here because the suggestion is
            # taken up on this page — it used to be a link to the catalogue, and a page
            # that can only point at a text has to send the reader somewhere to act.
            #
            # Sources rather than whole translation records: `/prepare` wants a list of
            # them and the page has no use for a publisher or a licence it never shows.
            catalogue=[
                {
                    "id": entry.id,
                    "title": entry.title,
                    "language": entry.language,
                    "blurb": entry.blurb,
                    "difficulty": entry.difficulty,
                    "minutes": entry.minutes,
                    "source": entry.source,
                    "translations": [t.source for t in entry.translations],
                }
                for entry in CATALOGUE
            ],
        )
    )


#: What each of the three list pages is called, in the order Learn shows them. The route
#: names are code — "texts" rather than "targums" — and the heading is the copy.
LISTS = {"texts": "Your targums", "words": "Your Words", "phrases": "Your Phrases"}


def list_page(token: str, which: str) -> str:
    """One of Learn's three lists, whole.

    Learn caps every list it draws, because a page somebody lands on with four hundred
    rows on it is not a landing page. This is where the rest of a list is, and it is the
    same template three times rather than three templates: the difference between them is
    which section is rendered, and nothing else.
    """
    from ..translate.prompts import OFFERED, language_name

    if which not in LISTS:
        raise KeyError(which)
    return (
        _environment()
        .get_template("yours.html.j2")
        .render(
            token=token,
            which=which,
            heading=LISTS[which],
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


def add_page(token: str, no_key: str = "") -> str:
    """Bringing a text targum does not have.

    No longer the page anybody lands on — Learn is — so it introduces nothing and says
    what it is for. It is still the only place in the product with a file input, a free
    source field, a choice of language pair, and a price shown before anything is spent.

    `no_key` is the notice to show when nothing can be translated. It is passed in rather
    than worked out here, so the page states the same thing the builder would have
    refused with — and it matters more here than it used to, this now being the only page
    that spends anything.
    """
    from ..translate.prompts import INTO, OFFERED, READING, language_name

    return (
        _environment()
        .get_template("add.html.j2")
        .render(
            token=token,
            # What an upload may be, and what it may become. Narrower than `languages`
            # below, which is every language the rest of the app knows how to show.
            reading=_staged(READING),
            into=_staged(INTO),
            no_key=no_key,
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


def _staged(pairs: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    """A language list with its stage beside each, for a page to draw a picker from."""
    from ..translate.prompts import language_name, stage_label

    return [
        {"code": code, "name": language_name(code), "stage": stage, "label": stage_label(stage)}
        for code, stage in pairs
    ]


def about_page() -> str:
    """That targum is under construction, and how much has landed lately.

    Nothing here is written by hand: the count and the calendar both come from `git
    log`, and the rest of what this page used to say is on GitHub.
    """
    from ..about import DAYS, work

    def level(count: int, busiest: int) -> int:
        """Which of five shades a day gets. Zero stays zero rather than rounding up."""
        if not count or not busiest:
            return 0
        return min(4, 1 + int(3 * (count - 1) / max(1, busiest - 1)))

    return _environment().get_template("about.html.j2").render(work=work(), days=DAYS, level=level)


def holding_page() -> str:
    """What a stranger sees while the product is not open yet.

    Deliberately not the sign-in page: that is a door, and a door presented to somebody
    with no key is a wall that looks like a mistake. This says where things are, and
    keeps the door in the corner for the people who have one.
    """
    return _environment().get_template("holding.html.j2").render()


def signin_page(*, landing: str = "", token: str = "", expired: bool = False) -> str:
    """The door. Three states, one template.

    Empty is the sign-in form. `landing` is the page an emailed link opens, naming the
    account it would sign in without having spent anything to find out. `expired` is
    what a link that has been used or has aged out arrives at, which is a normal thing
    to hit rather than an error.
    """
    return (
        _environment()
        .get_template("signin.html.j2")
        .render(landing=landing, token=token, expired=expired)
    )


def progress_page(token: str) -> str:
    """Everything kept, with what it adds up to.

    Built from the browser's own store like the start page, because that is where a
    word list lives; the server only hands over the page.
    """
    from ..translate.prompts import OFFERED

    return (
        _environment()
        .get_template("progress.html.j2")
        .render(
            token=token,
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


#: One catalogue, one name for it. There were two — a Library and a Beit Midrash — and
#: the split made the Tanakh harder to find rather than easier to avoid. What the Beit
#: Midrash was for is now a tag on the entries themselves.
SHELF = (
    "Library",
    "Hebrew — Tanakh, novels, essays and speeches — each with a translation beside it, "
    "sentence by sentence.",
)


def shelf_page(address: str = "") -> str:
    """The catalogue, for somebody who has not signed in.

    Public on purpose. It is the shop window, and until it exists there is nothing for a
    search engine to find but a page saying "Coming soon".
    """
    from ..catalogue import CATALOGUE

    name, blurb = SHELF
    return (
        _environment()
        .get_template("shelf.html.j2")
        .render(
            title=f"{name} — targum",
            description=blurb,
            canonical=f"{address}/library" if address else "",
            shelf_name=name,
            shelf_blurb=blurb,
            entries=CATALOGUE,
        )
    )


def text_page(entry: Entry, address: str = "") -> str:
    """One text, for somebody who has not signed in.

    A page about the text rather than about targum: whoever arrives here searched for the
    book, and the sample is the reason the page is worth indexing at all.
    """
    from ..models import direction_for

    name = SHELF[0]
    return (
        _environment()
        .get_template("text.html.j2")
        .render(
            title=f"{entry.title} — {name} — targum",
            description=entry.blurb,
            canonical=f"{address}/library/{entry.id}" if address else "",
            entry=entry,
            shelf_name=name,
            direction=direction_for(entry.language),
            sample=entry.sample,
            minutes=max(1, round(entry.words / 130)),
        )
    )


def you_page(token: str) -> str:
    """Who you are, how you read, and the two things that end an account.

    Built like the other app pages: the server hands over the page and the browser asks
    who is looking. Nothing about a person is baked into it, so one page serves everyone
    and a signed-out visitor gets a sentence rather than an empty form. The languages
    are baked in: which exist is a fact about targum, not about the person.
    """
    from ..translate.prompts import INTO, READING, REQUIRED_LEARNING

    return (
        _environment()
        .get_template("you.html.j2")
        .render(
            token=token,
            reading=_staged(READING),
            into=_staged(INTO),
            required=list(REQUIRED_LEARNING),
        )
    )


def library_page(token: str) -> str:
    """Texts worth reading, and the ones you have already built.

    The catalogue is baked in rather than fetched: it is a handful of entries that
    ship with targum, and a page that has to ask the server for them would be a page
    that can be empty.
    """
    from ..catalogue import CATALOGUE
    from ..translate.prompts import OFFERED

    return (
        _environment()
        .get_template("library.html.j2")
        .render(
            token=token,
            catalogue=[entry.state() for entry in CATALOGUE],
            languages=[(code, language_name(code)) for code in OFFERED],
        )
    )


#: What a drawn cover may have been saved as, newest format first.
COVER_SUFFIXES = ((".webp", "image/webp"), (".png", "image/png"), (".jpg", "image/jpeg"))

#: How wide a cover rides on a chapter page. The contents page carries the whole 320px
#: tile once; a chapter page carries one on every page of a book, so it gets a smaller
#: one — a hundred and fifty psalms would otherwise add three megabytes to a reader for
#: an image the size of a thumbnail.
PLATE_WIDTH = 128


def cover_bytes(covers: Path | None, name: str) -> bytes | None:
    """A drawn cover, whatever it was saved as, or None where nobody has drawn one."""
    if covers is None or not name:
        return None
    for suffix, _ in COVER_SUFFIXES:
        found = covers / f"{name}{suffix}"
        if found.is_file():
            return found.read_bytes()
    return None


def cover_uri(covers: Path | None, name: str) -> str:
    """A cover as a `data:` URI, because a reader fetches nothing.

    The whole point of a built reader is that it is one file that works off a disk, on a
    plane, in an e-reader's browser. An image it had to go and get would be the first
    thing in it that could fail — so covers ride inside the page, the same way the icons
    already do.
    """
    raw = cover_bytes(covers, name)
    if raw is None:
        return ""
    return f"data:image/webp;base64,{base64.b64encode(raw).decode('ascii')}"


def plate_uri(covers: Path | None, name: str) -> str:
    """The same cover, small enough to sit on every page of a book.

    Kept beside the original once made, so a book of a hundred and fifty chapters shrinks
    one image rather than a hundred and fifty. Without Pillow there is no small one to
    make, and a chapter page simply goes without — the contents page still has the whole
    thing, and nothing looks broken.
    """
    if covers is None or not name:
        return ""
    small = covers / "small" / f"{name}.webp"
    if not small.is_file():
        raw = cover_bytes(covers, name)
        if raw is None:
            return ""
        try:
            from ..covers import shrink
        except ImportError:  # pragma: no cover - covers is a package, not an extra
            return ""
        try:
            made = shrink(raw, width=PLATE_WIDTH)
        except Exception:
            # Pillow missing, or an image it cannot read. A reader without a plate is a
            # reader; a build that died over a decoration is not.
            return ""
        small.parent.mkdir(parents=True, exist_ok=True)
        small.write_bytes(made)
    return f"data:image/webp;base64,{base64.b64encode(small.read_bytes()).decode('ascii')}"


def cover_name(document: Document) -> str:
    """Which cover belongs to this text.

    Covers are drawn for the library's own texts and named by the catalogue's id, which
    is what lets one drawing serve every reader who builds that text. Anything else has
    none, and asks for none.
    """
    from .. import catalogue as catalogue_module

    entry = catalogue_module.matching(document.source)
    return entry.id if entry else ""


def render(
    document: Document,
    segmented: SegmentedDocument,
    translations: list[Translation],
    out_dir: Path,
    annotation: Annotation | None = None,
    glossaries: Mapping[str, Glossary] | None = None,
    vocalization: Vocalization | None = None,
    clean: bool = True,
    glossary_pending: str = "",
    covers: Path | None = None,
    reads: Collection[str] | None = None,
) -> list[Path]:
    """Write the reader. Returns every file written, index first.

    `glossaries` is keyed by target language, because a meaning is written in one and a
    reader may hold translations into two. A word means what it means in Russian and
    something else in English, and the page has to be able to hand a reader the one they
    asked for rather than whichever was built last.

    `glossary_pending` is the target whose meanings are still being written, or "". It is
    a language rather than a flag for the same reason: the reader polls for the target it
    is showing, and switching to one that was never bought must not start a wait for a
    file nobody is writing.

    `reads` is which languages the person this reader belongs to reads. A translation into
    any other is left out of the page: a picker offering a language somebody cannot read
    offers them a page of nothing, and a word kept from it would carry a meaning in that
    language into every text they own. None means ask nobody, which is the command line
    and a machine somebody runs themselves.

    A reader left with nothing by that keeps what it had. A page with no translation
    beside the source is not a reader at all, which is the worse of the two answers — and
    it only arises where somebody stopped reading a language they had already built in.

    `clean=False` writes over what is already there instead of emptying the directory
    first. It is for the second pass, once the word meanings have arrived: the same
    segments produce the same section files under the same names, so overwriting leaves
    nothing stale behind, and a reader someone has open does not have the page they are
    reading deleted from under them for the moment it takes to write the new one.
    """
    if not translations:
        raise ValueError("a reader needs at least one translation")

    if reads is not None:
        offered = [t for t in translations if t.target_language in reads]
        translations = offered or translations

    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = _environment()
    sections = split_sections(segmented)
    by_id = {segment.id: segment for segment in segmented.segments}
    single = len(sections) == 1

    # Two ways to show the same sentence. The bare form is what the page renders by
    # default and the one every stored offset is measured against; the pointed form is
    # the cell the switch reveals — everything the edition wrote above and below the
    # letters, accents included where it has them. Both are built here rather than in
    # the browser so each goes through isolate() and neither has to be reassembled in
    # JavaScript.
    #
    # One switch, two positions: bare, or the whole text. A middle step that showed the
    # vowels without the accents existed for a day and went — a third form on a Tanakh
    # was a state to be lost in, and the only thing it ever taught a reader was that
    # the arrows had stopped working.
    bare: dict[str, str] = {}
    to_bare: dict[str, list[int]] = {}
    for segment in segmented.segments:
        bare[segment.id], to_bare[segment.id] = strip_nikkud(segment.text)
    pointed = dict(vocalization.segments) if vocalization is not None else {}
    machine = set(vocalization.machine) if vocalization is not None else set()

    # Which face this page carries follows the text, not the shelf. The modern face is
    # chosen for reading a newspaper and has no accents in it, so a text that carries one
    # anywhere — an essay quoting a verse — must be set in the face that can draw them. A
    # page that cannot draw its own text is the whole bug this began as.
    accented = any(has_taamim(text) for text in pointed.values())

    # Whose pointing this mostly is. A Tanakh or a pointed poem arrives with its vowels
    # already on the page and someone chose it for them, so it opens pointed; a news
    # article whose points are all guessed opens bare, which is how it was written.
    # The marker on a guessed sentence follows the same fact: when every line is
    # guessed it distinguishes nothing and only adds noise, so it is left off.
    from_source = len(pointed) - len(machine)
    source_pointed = bool(pointed) and from_source * 2 >= len(pointed)
    mark_guessed = bool(machine) and len(machine) * 2 < len(pointed)

    biblical = is_biblical(document.source)
    source_direction = direction_for(segmented.language)
    target_direction = direction_for(translations[0].target_language)

    drawn = cover_name(document)
    shared = {
        "document": document,
        "title": document.title or "targum",
        # The whole tile, once, on the page that lists the chapters.
        "cover": cover_uri(covers, drawn),
        "sections": sections,
        "source_language": segmented.language,
        "source_direction": source_direction,
        "target_language": translations[0].target_language,
        "target_direction": target_direction,
        "page_direction": source_direction,
        "has_nikkud": bool(pointed),
        "source_pointed": source_pointed,
        "mark_guessed": mark_guessed,
        # A verse is not a paragraph. Tanakh pairs one pasuk to a row, and rows spaced
        # like paragraphs put a blank line between every verse — a chapter then reads as
        # a list of separate sayings rather than as continuous text. Asked of the source
        # rather than guessed from the content, the same way `biblical.for_source()`
        # decides which difficulty bands to use, and for the same reason.
        "verse_by_verse": biblical,
        # Which of the two Hebrew faces this page carries. Scripture is set in a face cut
        # for the Masorah; a newspaper is not — but see `accented` above: the deciding
        # question is what the text holds, not which shelf it came from.
        "biblical": accented,
        "difficulty": None
        if annotation is None
        else {
            "method": method_label(annotation.method),
            "note": annotation.method_note,
            "annotator": annotation.annotator,
        },
        "translations": [
            {
                "id": f"t{index}",
                "name": translation.name,
                "language": translation.target_language,
                "direction": direction_for(translation.target_language),
                "kind": translation.kind,
                "style": translation.style.value,
                "provider": translation.provider,
            }
            for index, translation in enumerate(translations)
        ],
    }

    written: list[Path] = []
    for section in sections:
        segments = [by_id[sid] for sid in section.segment_ids]
        # Only this section's translations ship with the page, so a long book stays
        # openable on a phone.
        payload = {
            f"t{index}": {
                "text": {sid: translation.segments.get(sid, "") for sid in section.segment_ids},
                # Regions that fell back to paragraph pairing, so the reader can mark
                # them. A learner needs to know the pairing here is approximate.
                "coarse": [sid for sid in section.segment_ids if sid in set(translation.coarse)],
                # Which language this one is, and which way it runs. The page used to
                # take both from `translations[0]` and stamp them on the cells once, so
                # switching to a translation in another language left every cell claiming
                # the first one's language — and left the reader's word lookups asking
                # for meanings in a language nobody was reading.
                "language": translation.target_language,
                "direction": direction_for(translation.target_language),
            }
            for index, translation in enumerate(translations)
        }
        # Per-word data ships as offsets rather than as a span for every word. A book
        # has hundreds of thousands of tokens, and emitting markup for all of them up
        # front is what makes a reader too heavy for a phone.
        # Lemmas go in a table and the words point into it: the same lemma turns up
        # dozens of times in a chapter, and repeating it with every token is what makes
        # a page heavy.
        lemmas: list[str] = []
        lemma_at: dict[str, int] = {}
        # Root and binyan belong to the dictionary form, not to the occurrence, so they
        # ride in tables beside the lemmas rather than on every token. Absent for every
        # word that is not a Hebrew verb, and for the verbs whose root could not be had.
        roots: list[str] = []
        binyanim: list[str] = []
        # How a word is said belongs to the occurrence, not to the dictionary form — that
        # is the whole reason it is worth having — so it cannot ride beside the lemmas.
        # It rides in its own table instead, with an index on each token: a chapter has
        # far fewer distinct spellings than tokens, and the same word said twice is
        # stored once.
        sounds: list[str] = [""]
        sound_at: dict[str, int] = {"": 0}
        words: dict[str, list[list[int]]] = {}
        if annotation is not None:
            for sid in section.segment_ids:
                tokens = annotation.tokens.get(sid)
                if not tokens:
                    continue
                rows: list[list[int]] = []
                for token in tokens:
                    if token.lemma not in lemma_at:
                        lemma_at[token.lemma] = len(lemmas)
                        lemmas.append(token.lemma)
                        roots.append(token.root or "")
                        binyanim.append(token.binyan or "")
                    # Offsets arrive measured against the segment as ingested, which may
                    # itself be pointed. They ship measured against the bare form, the
                    # one coordinate system the reader keeps everything in. Where the
                    # source had no marks the map is the identity and this costs nothing.
                    if token.ipa and token.ipa not in sound_at:
                        sound_at[token.ipa] = len(sounds)
                        sounds.append(token.ipa)
                    start, end = map_span(token.start, token.end, to_bare[sid])
                    rows.append(
                        [
                            start,
                            end,
                            token.band,
                            1 if token.split else 0,
                            lemma_at[token.lemma],
                            sound_at.get(token.ipa or "", 0),
                            # A name or a number, which the reader can tap and mark but
                            # which is never counted as vocabulary.
                            KIND_COLUMN.get(token.pos or "", 0),
                        ]
                    )
                words[sid] = rows
        # One table of meanings per target language, each parallel to `lemmas`. A reader
        # holding an English and a Russian translation carries both and shows whichever
        # its picker is on; a reader with one carries one, which is what every text built
        # so far is. Empty tables are left out rather than shipped as a row of "".
        glosses = {
            code: filled
            for code, book in (glossaries or {}).items()
            if (filled := [book.entries.get(lemma, "") for lemma in lemmas]) and any(filled)
        }
        # A chapter's own cover where one was drawn for it, and the book's where it was
        # not — which is most of them, since a numbered chapter is not a subject anything
        # could draw.
        chapter_cover = f"{drawn}-c{section.number:03d}" if drawn else ""
        # Whether this chapter has been translated at all. A book is bought a chapter
        # at a time and every chapter's page is written regardless, so one nobody has
        # paid for used to render as the source beside a column of empty paragraphs —
        # which is what a reader who followed the arrow from chapter one walked into.
        # The same rule `Library.chapters()` applies, so the contents page and the
        # chapter page cannot disagree about which chapters are waiting.
        translated = any(translations[0].segments.get(sid) for sid in section.segment_ids)
        html = env.get_template("reader.html.j2").render(
            **shared,
            plate=plate_uri(covers, chapter_cover) or plate_uri(covers, drawn),
            section=section,
            translated=translated,
            words=bool(words),
            segments=segments,
            bare=bare,
            pointed=pointed,
            machine=machine,
            primary=translations[0].segments,
            primary_coarse=set(translations[0].coarse),
            data=embed_json(
                {
                    "translations": payload,
                    "words": words,
                    "lemmas": lemmas,
                    "roots": roots,
                    "binyanim": binyanim,
                    # Left out entirely where nothing was read, rather than shipping a
                    # table holding one empty string in every reader that has no Hebrew.
                    **({"sounds": sounds} if len(sounds) > 1 else {}),
                    "glosses": glosses,
                    "levelNames": BAND_NAMES,
                    # Which text this is. Lists are kept per document, not per
                    # language, so reading two articles does not pool their words.
                    "document": segmented.document_hash,
                    "title": document.title or "",
                    # For naming an export of the language's words, which the reader
                    # otherwise only knows by its tag.
                    "languageName": language_name(segmented.language),
                    # Whether the vowels on this text are its own, and so whether it
                    # should open with them showing.
                    "sourcePointed": source_pointed,
                    # Which target's meanings are on their way, if any. Words are looked
                    # up one at a time now, so most readers have none coming and must not
                    # sit asking for one for ten minutes — and a reader that switches to
                    # a language nobody bought a glossary for must not start asking
                    # either.
                    "glossPending": glossary_pending,
                }
            ),
            previous=None if section.number == 1 else sections[section.number - 2],
            following=None if section.number == len(sections) else sections[section.number],
            standalone=single,
        )
        name = "index.html" if single else section.filename
        written.append(_write(out_dir / name, html))

    if not single:
        index = env.get_template("index.html.j2").render(
            **shared, counts={s.number: len(s.segment_ids) for s in sections}
        )
        written.insert(0, _write(out_dir / "index.html", index))
    return written


def _write(path: Path, html: str) -> Path:
    path.write_text(html, encoding="utf-8")
    return path
