"""The week's sheet as a download, set on the box (targum-internal#415).

`targum export mikra` sets the shnayim mikra sheet from the command line: the portion with
Onkelos beside each verse, the haftarah, and a reader's own words of the week. This is the
same sheet behind a link — the ⋯ menu of a portion's reader and the portion's public page
— set when it is asked for.

**What the box cuts from.** The command cuts the portion again from the books on the
shelf, and the box has no shelf of books: the corpus is built on a laptop and carried
(`deploy/ship-parasha.sh`), and only its readers travel. So the build keeps, beside each
reader, the little the sheet is set from — the cut text, its renderings and its pointing,
under `read/<folder>/print/` — and the words the text cites, which is what a reader's own
words are set beside. Not the annotation it came from, which is ten times the size and
which the sheet does not otherwise read. A corpus built before this has no `print/`, and
its portions say they are not ready rather than failing somewhere deeper.

**What is kept, and what is not.** A sheet with nobody's words on it is the same sheet for
everybody who asks in that language and on that paper, so it is set once and kept, under
the hash of the page it was set from: a rebuilt portion is a different page, and a
different file. A sheet with a reader's words on it is set each time and kept nowhere —
their week is theirs, and a file of it on the box would be a second copy of their record.

**What may run.** Two sheets at a time, each in a process of its own that is stopped
after `SECONDS`: a portion is a few hundred verses set through Pango, and a box that
answered every press at once would stop answering anything else.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from ..errors import TargumError
from ..models import (
    Document,
    SegmentedDocument,
    Translation,
    Vocalization,
    read_artifact,
)
from ..paths import cache_dir, write_atomic
from ..translate.prompts import BESIDE

if TYPE_CHECKING:
    from ..accounts import Store
    from ..render.printed import View, Word
    from .cut import Portion as Cut

log = logging.getLogger(__name__)

#: Beside `reader/` in a corpus folder: what the sheet is set from.
FOLDER = "print"

#: How long one sheet may take to set before it is stopped. Bereshit with its haftarah
#: took twenty seconds on a quiet laptop and eighty on a busy one.
SECONDS = 180.0

#: How many sheets may be set at once, and how long a press waits for a turn.
AT_ONCE = 2
WAIT = 30.0

#: How many kept sheets the cache holds before the oldest go. Fifty-four portions, a
#: few haftarot, two languages and two papers is the ceiling in practice.
KEPT = 256

_turns = threading.BoundedSemaphore(AT_ONCE)


class NotReady(TargumError):
    """The portion is on the shelf but its sheet's sources are not beside it."""


@dataclass(slots=True)
class Sheet:
    """A set sheet, and what to call it."""

    pdf: bytes
    name: str
    #: Whether a reader's own words are on it, which decides how it may be cached.
    personal: bool


def _file_of(translation: Translation) -> str:
    """A rendering's file beside the reader: its language, or for a commentary its work
    and language — Rashi in English beside the Metsudah English is two files, not one
    written over the other (targum-internal#414)."""
    from ..ids import slug
    from ..renderings import commentator

    who = commentator(translation.name)
    return f"{slug(who)}-{translation.target_language}" if who else translation.target_language


def keep(portion: Cut, folder: Path) -> Path:
    """Write what the sheet is set from beside a built reader, at `folder/print`.

    Called by the corpus build for every portion and haftarah it cuts. The cited forms
    are worked out here, once per language the text is rendered into, so the box never
    needs the annotation.
    """
    from ..render.printed import cited_forms

    out = folder / FOLDER
    (out / "translations").mkdir(parents=True, exist_ok=True)
    for stale in (out / "translations").glob("*.json"):
        stale.unlink()
    portion.document.write(out / "document.json")
    portion.segmented.write(out / "segments.json")
    for translation in portion.translations:
        translation.write(out / "translations" / f"{_file_of(translation)}.json")
    if portion.vocalization is not None:
        portion.vocalization.write(out / "vocalization.json")
    else:
        (out / "vocalization.json").unlink(missing_ok=True)
    from ..renderings import is_commentary

    languages = sorted(
        {
            t.target_language
            for t in portion.translations
            if t.target_language not in BESIDE and not is_commentary(t.name)
        }
    )
    cited = {
        language: {bare: list(pair) for bare, pair in cited_forms([portion], language).items()}
        for language in languages
    }
    write_atomic(out / "cited.json", json.dumps(cited, ensure_ascii=False) + "\n")
    _keep_words(portion, out)
    return out


#: What of a token the sheet reads: where it stands, what it is, how rare, and what its
#: meaning is filed under. Everything else on it is the card's.
_TOKEN_FIELDS = {"start", "end", "surface", "lemma", "band", "pos", "entity", "headword"}


def _keep_words(portion: Cut, out: Path) -> None:
    """The words a sheet marks, and their meanings, beside the reader (targum-internal
    #415): the annotation's tokens with only what `printed._marked` reads, the names and
    numbers left out, and each glossary cut to the words the text carries, first sense
    only. A tenth of what they were cut from."""
    from ..models import Annotation, Glossary, Token
    from ..render.printed import first_sense

    for stale in out.glob("glossary.*.json"):
        stale.unlink()
    annotation = portion.annotation
    if annotation is None:
        (out / "words.json").unlink(missing_ok=True)
        return
    from ..annotate.base import NOT_A_WORD, not_vocabulary

    tokens = {
        sid: [
            Token(**one.model_dump(include=_TOKEN_FIELDS))
            for one in kept
            if one.lemma not in NOT_A_WORD and not not_vocabulary(one.pos, one.entity)
        ]
        for sid, kept in annotation.tokens.items()
    }
    slim = Annotation(
        document_hash=annotation.document_hash,
        language=annotation.language,
        annotator=annotation.annotator,
        method=annotation.method,
        method_note=annotation.method_note,
        band_count=annotation.band_count,
        tokens={sid: kept for sid, kept in tokens.items() if kept},
    )
    slim.write(out / "words.json")
    used = {token.glossed_as for kept in slim.tokens.values() for token in kept}
    for code, glossary in portion.glossaries.items():
        Glossary(
            source_language=glossary.source_language,
            target_language=glossary.target_language,
            provider=glossary.provider,
            entries={
                key: first_sense(value)
                for key, value in glossary.entries.items()
                if key in used and first_sense(value)
            },
            citations={key: value for key, value in glossary.citations.items() if key in used},
        ).write(out / f"glossary.{code}.json")


def kept(folder: Path) -> tuple[Cut, dict[str, dict[str, tuple[str, str]]]]:
    """What `keep` wrote, as a cut the sheet can be set from, and the cited forms by
    language. Raises `NotReady` where it is not there."""
    from .cut import Portion as Cut

    where = folder / FOLDER
    document = read_artifact(Document, where / "document.json")
    segmented = read_artifact(SegmentedDocument, where / "segments.json")
    translations = [
        one
        for path in sorted((where / "translations").glob("*.json"))
        if (one := read_artifact(Translation, path)) is not None
    ]
    if document is None or segmented is None or not translations:
        raise NotReady(f"{folder.name} has no sheet beside its reader.")
    try:
        loaded = json.loads((where / "cited.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = {}
    cited = {
        str(language): {str(bare): (str(pair[0]), str(pair[1])) for bare, pair in forms.items()}
        for language, forms in loaded.items()
        if isinstance(forms, dict)
    }
    from ..models import Annotation, Glossary

    glossaries = {
        path.name.removeprefix("glossary.").removesuffix(".json"): glossary
        for path in sorted(where.glob("glossary.*.json"))
        if (glossary := read_artifact(Glossary, path)) is not None
    }
    cut = Cut(
        reading=None,
        document=document,
        segmented=segmented,
        translations=translations,
        # The words the sheet marks, where the build kept them; a corpus built before
        # the marks has none, and its sheet is the plain one.
        annotation=read_artifact(Annotation, where / "words.json"),
        vocalization=read_artifact(Vocalization, where / "vocalization.json"),
        glossaries=glossaries,
    )
    return cut, cited


def reader_week(
    store: Store,
    person_id: int,
    shabbat: date,
    translations: list[Translation],
    cite: Callable[[str], Mapping[str, tuple[str, str]]],
) -> tuple[list[Word], bool, tuple[str, ...]]:
    """One reader's words of the week ending on `shabbat`, as the sheet lists them.

    The words looked up that week, where the record names them; where it names none —
    the record off or stopped, or a week before look-ups carried their word — the words
    kept that week, and the list's heading says which. Returns the words, whether they
    are the looked-up ones, and the languages the reader reads, English first where they
    read it, as the account's own default is English. `cite` gives the week's texts'
    cited forms in the language the list is read in.
    """
    from ..render.printed import own_language, week_words
    from .calendar import week_began

    reads = tuple(sorted(store.reads(person_id), key=lambda code: code != "en"))
    language = own_language(translations, reads)
    began = week_began(shabbat)
    window = (
        person_id,
        int(began.timestamp() * 1000),
        int((began + timedelta(days=7)).timestamp() * 1000),
    )
    found = store.looked_up_between(*window, languages=("he", "arc"), target=language)
    looked = bool(found)
    if not looked:
        found = store.kept_between(*window, languages=("he", "arc"), target=language)
    return week_words(found, target=language, cited=cite(language)), looked, reads


#: The switches a view is written with, each on unless it says 0 (`view_from`).
_SWITCHES = ("vowels", "taamim", "gloss", "haftarah")


def view_from(query: Mapping[str, list[str]]) -> View:
    """The view a Download link asks for, read off its query (targum-internal#415).

        with=en,targum   the companions on, in order: a translation by its language,
                         Onkelos as `targum`; `with=` empty is the text alone; absent,
                         the reader's default — their own language
        vowels=0         the text bare; taamim=0 the vowels without the chanting marks
        layout=under     each companion under its verse, not beside it
        gloss=0          no marks and no meanings above the words
        aliyah=3         that aliyah only — and then no haftarah unless haftarah=1
        haftarah=0       the portion without the haftarah
        size=letter      the paper

    Anything it does not know, it passes over: a link from a newer reader still prints.
    """
    from ..render.printed import View

    def one(name: str) -> str | None:
        # The last value: a form sends a hidden 0 before each box, and the box's 1 after
        # it where it is ticked.
        values = query.get(name)
        return values[-1].strip().lower() if values else None

    companions: tuple[str, ...] | None = None
    if "with" in query:
        # Every value, as a form's boxes send them, and each a list as a link writes it.
        said = ",".join(query["with"]).lower()
        companions = tuple(
            dict.fromkeys(key for key in (k.strip() for k in said.split(",")) if key)
        )[:6]
    aliyah: int | None = None
    asked = one("aliyah")
    if asked and asked.isdigit() and 0 < int(asked) < 100:
        aliyah = int(asked)
    switches = {name: one(name) for name in _SWITCHES}
    haftarah = switches["haftarah"]
    return View(
        companions=companions,
        vowels=switches["vowels"] != "0",
        taamim=switches["taamim"] != "0",
        under=one("layout") == "under",
        gloss=switches["gloss"] != "0",
        aliyah=aliyah,
        haftarah=(haftarah == "1") if aliyah is not None else haftarah != "0",
        size=one("size") or "a4",
    )


def _cache() -> Path:
    return cache_dir() / "sheets"


def _prune(folder: Path, keep_at_most: int = KEPT) -> None:
    files = sorted(folder.glob("*.pdf"), key=lambda one: one.stat().st_mtime, reverse=True)
    for old in files[keep_at_most:]:
        old.unlink(missing_ok=True)


def _set(html: str, *, personal: bool) -> bytes:
    """The page as a PDF: off the cache where nobody's words are on it, else set now."""
    from ..render.printed import write_pdf_within

    folder = _cache()
    folder.mkdir(parents=True, exist_ok=True)
    named = folder / (hashlib.sha256(html.encode("utf-8")).hexdigest()[:32] + ".pdf")
    if not personal and named.is_file():
        named.touch()
        return named.read_bytes()
    if not _turns.acquire(timeout=WAIT):
        raise TargumError("Every press is busy setting a sheet.", "Try again in a minute.")
    try:
        if personal:
            import tempfile

            with tempfile.TemporaryDirectory(dir=folder) as scratch:
                out = write_pdf_within(html, Path(scratch) / "sheet.pdf", SECONDS)
                return out.read_bytes()
        write_pdf_within(html, named, SECONDS)
        _prune(folder)
        return named.read_bytes()
    finally:
        _turns.release()


def make(
    slug: str,
    *,
    store: Store | None = None,
    person_id: int | None = None,
    language: str = "en",
    israel: bool = False,
    view: View | None = None,
) -> Sheet | None:
    """The sheet for one portion, or None where the corpus has no such portion.

    This week's portion takes this week's haftarah, the date, and the reason a special
    haftarah displaced its own; any other portion takes the haftarah it ordinarily has
    and no date, as its page does. A reader signed in (`store` and `person_id`) gets
    their words of this week at the end, and the words they are learning lit with their
    meanings above them; anybody else gets the sheet in `language`, with the rarer
    words' meanings above them. `view` is what the reader's page showed (`view_from`).
    """
    from ..render.printed import (
        SIZES,
        Marker,
        View,
        learning_marker,
        mikra_html,
        own_language,
        rare_marker,
    )
    from . import build as corpus
    from .calendar import Schedule, pointing_at, root

    view = view or View()
    if view.size not in SIZES:
        view = replace(view, size="a4")
    index = corpus.load()
    portion = index.portions.get(slug)
    if portion is None or portion.folder not in corpus.readable(index):
        return None
    shabbat = pointing_at()
    schedule = Schedule.israel if israel else Schedule.diaspora
    when, reason = "", ""
    haftarah = index.haftarot.get(portion.haftarah) if portion.haftarah else None
    for one in (schedule, Schedule.israel if not israel else Schedule.diaspora):
        this_week = index.week(shabbat.isoformat(), one)
        if this_week is not None and this_week.slug == slug:
            when = this_week.hdate
            haftarah, reason = index.haftarah_on(shabbat.isoformat(), one)
            break

    read = root() / "read"
    text, cited = kept(read / portion.folder)
    reading_of_prophets = None
    if haftarah is not None and haftarah.folder:
        try:
            reading_of_prophets, also = kept(read / haftarah.folder)
        except NotReady:
            # The portion is the practice and the haftarah follows it: a sheet without
            # it is still this week's sheet.
            log.info("sheet %s: no haftarah sources beside %s", slug, haftarah.folder)
        else:
            for code, forms in also.items():
                cited[code] = {**forms, **cited.get(code, {})}

    week: list[Word] = []
    looked = True
    reads: Collection[str] = (language,)
    marker: Marker = rare_marker
    if store is not None and person_id is not None:
        week, looked, reads = reader_week(
            store,
            person_id,
            shabbat,
            text.translations,
            lambda code: cited.get(code, {}),
        )
        marker = learning_marker(
            store.learning_words(
                person_id, languages=("he",), target=own_language(text.translations, reads)
            )
        )
    if view.companions is None:
        # The reader's own default (targum-internal#414): their language, Onkelos and
        # Rashi beside the verse, and Rashi in English off. A key this text has no
        # rendering for is passed over.
        view = replace(view, companions=(own_language(text.translations, reads), "targum", "rashi"))
    html = mikra_html(
        text,
        reading_of_prophets,
        name=portion.name,
        hebrew=portion.hebrew,
        when=when,
        haftarah_note=reason,
        week=week,
        looked=looked,
        reads=reads,
        view=view,
        marker=marker,
        address=f"targum.page/parasha/{slug}",
    )
    # Anything of the reader's on it — their list, their lit words — makes it theirs.
    personal = store is not None and person_id is not None
    return Sheet(pdf=_set(html, personal=personal), name=f"{slug}.pdf", personal=personal)
