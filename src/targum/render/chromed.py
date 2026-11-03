"""A reader's chrome in the reader's own language, whatever its text was built into.

A reader is built once and served to everybody, and its menus, its card's labels and its
notices were said in the language of its first translation (targum-internal#184). On a
library text whose only translation is English that made a Russian-interface reader's
whole page English, the word card's labels and the bar included, with 860 Russian lines
in the catalogue that never reached it (beta review, 2026-11-03, R1). The chrome is the
reader's; the meanings are the text's (design.md §12, "A reader's chrome is the reader's
language", 2026-11-03).

So a reader is still written once, in its first translation's language, and opens as it
always did from a disk, a saved copy or a server that knows nothing of this. Every piece
of it that would read differently in another interface language is written with a mark
around it while the page is drawn (`Chrome.varied`, and the `t`/`tn` the template is
handed), and `seal` takes the marks out and writes, after `</html>`, one comment holding
where each piece sits and what it says in every other interface language. Serving the
page to somebody whose interface is another, `chromed_in` puts their words in those
places and drops the comment. Nothing is bought, nothing re-rendered at serve time, and a
page drawn before this has no comment and is served exactly as it is.

A page reaches its readers' languages on the routine rebuild, which reads every text from
the cache and spends nothing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from markupsafe import Markup, escape

#: The marks around a piece while the page is drawn: open, its number, a divider, the
#: piece as the page says it, close. From the Private Use Area, which no text, catalogue
#: line or asset of ours writes, and which `seal` removes before the page is written.
OPEN, MID, CLOSE = "\ue000", "\ue001", "\ue002"
_PIECE = re.compile(f"{OPEN}(\\d+){MID}([^{OPEN}{MID}{CLOSE}]*){CLOSE}")
#: A mark something escaped on its way into the page — `tojson`, a URL — which cannot be
#: put back in place and is only taken out, leaving the page's own words.
_ESCAPED = re.compile(
    r"\\ue000\d+\\ue001|\\ue002|%EE%80%80\d+%EE%80%81|%EE%80%82|&#57344;\d+&#57345;|&#57346;",
    re.IGNORECASE,
)
_STRAY = re.compile(f"[{OPEN}{MID}{CLOSE}]")

#: The comment after `</html>` that carries the other languages' words.
TRAILER = "<!--targum-chrome "
_TRAILER_END = "-->"

#: A piece whose words in a language the server has, named rather than carried: the
#: chrome's Cyrillic cut is 29 kB and the reader's script lines in Russian 40 kB, and a
#: page that never meets a Russian reader should not carry them on disk for one that
#: might. `{SHEET: name}` is a face by its file's name; `{WORDS: code}` the reader's
#: script lines in that language (`builder.carried_named`), read from the catalogue as
#: it is when the page is served.
SHEET = "sheet"
WORDS = "words"


class Chrome:
    """The pieces of one page as it is drawn: `base` is the language the page is written
    in, `others` the interface languages it can be served in besides."""

    def __init__(self, base: str, others: list[str]):
        self.base = base
        self.others = [code for code in others if code != base]
        self.pieces: list[dict[str, Any]] = []
        # Each marked piece's words in every language, by the piece as the page has it,
        # so a piece handed to `t` as a blank fills each language's sentence with its own.
        self.known: dict[str, dict[str, Any]] = {}

    @property
    def languages(self) -> list[str]:
        return [self.base, *self.others]

    def varied(self, by: Mapping[str, Any]) -> Markup:
        """A piece, said as the page says it and marked, where any language says it
        differently; the page's own words, unmarked, where every language agrees. Each
        value is Markup already, or a `{SHEET: name}`."""
        own = by[self.base]
        if all(by.get(code, own) == own for code in self.others):
            return own if isinstance(own, Markup) else Markup("")
        number = len(self.pieces)
        self.pieces.append({code: by.get(code, own) for code in self.others})
        shown = own if isinstance(own, str) else ""
        marked = Markup(f"{OPEN}{number}{MID}{_unmarked(shown)}{CLOSE}")
        self.known[str(marked)] = dict(by)
        return marked

    def each(self, said: Callable[[str], Any]) -> Markup:
        """`said(language)` for every language, escaped, as one piece."""
        return self.varied({code: _markup(said(code)) for code in self.languages})

    def words(self, page_words: Callable[[str], Callable[..., Markup]]) -> Callable[..., Markup]:
        """A template's `t`, saying each piece in every language."""
        said = {code: page_words(code) for code in self.languages}

        def t(key: str, english: str, **fill: object) -> Markup:
            return self.varied(
                {
                    code: said[code](key, english, **self._fills(fill, code))
                    for code in self.languages
                }
            )

        return t

    def counts(self, page_counts: Callable[[str], Callable[..., Markup]]) -> Callable[..., Markup]:
        """A template's `tn`, likewise."""
        said = {code: page_counts(code) for code in self.languages}

        def tn(key: str, n: int, one: str, other: str, **fill: object) -> Markup:
            return self.varied(
                {
                    code: said[code](key, n, one, other, **self._fills(fill, code))
                    for code in self.languages
                }
            )

        return tn

    def _fills(self, fill: Mapping[str, object], code: str) -> dict[str, object]:
        out: dict[str, object] = {}
        for name, value in fill.items():
            if isinstance(value, str) and str(value) in self.known:
                value = self.known[str(value)].get(code, Markup(_unmarked(str(value))))
            elif isinstance(value, str) and _STRAY.search(value):
                value = Markup(_unmarked(value)) if isinstance(value, Markup) else _unmarked(value)
            out[name] = value
        return out


def _markup(value: object) -> Any:
    if isinstance(value, dict):
        return value
    return value if isinstance(value, Markup) else escape(str(value))


def _unmarked(text: str) -> str:
    """A value with any marks it carried taken out: pieces do not nest."""
    return _PIECE.sub(lambda found: found.group(2), text).translate(
        {ord(OPEN): None, ord(MID): None, ord(CLOSE): None}
    )


def seal(html: str, chrome: Chrome) -> str:
    """The page as it is written: the marks out, and where it has pieces in another
    language, the comment that carries them. Offsets are into the page as written, in
    characters."""
    # A mark something escaped is not where its piece is any more: out first, so every
    # offset below is into the page without it.
    html = _ESCAPED.sub("", html)
    out: list[str] = []
    spans: list[list[Any]] = []
    at = 0
    length = 0
    for found in _PIECE.finditer(html):
        before = html[at : found.start()]
        out.append(before)
        length += len(before)
        own = found.group(2)
        number = int(found.group(1))
        if number < len(chrome.pieces):
            spans.append([length, len(own), chrome.pieces[number]])
        out.append(own)
        length += len(own)
        at = found.end()
    out.append(html[at:])
    page = "".join(out)
    strays = [found.start() for found in _STRAY.finditer(page)]
    if strays:
        # A piece something cut in half: its marks out, its words as the page says them,
        # and every span after one moved back by the marks before it.
        page = _STRAY.sub("", page)
        kept: list[list[Any]] = []
        for at_, long_, by_ in spans:
            moved = sum(1 for one in strays if one < at_)
            if any(at_ <= one < at_ + long_ for one in strays):
                continue
            kept.append([at_ - moved, long_, by_])
        spans = kept
    if not spans:
        return page
    said = json.dumps(
        {"base": chrome.base, "spans": spans}, ensure_ascii=False, separators=(",", ":")
    )
    # A comment cannot hold "--"; JSON writes a hyphen inside a string only, where
    # `\u002d` is the same hyphen once decoded.
    return page + TRAILER + said.replace("-", "\\u002d") + _TRAILER_END + "\n"


def without_comment(page: str) -> str:
    """The page as written, less the comment that carries its other languages' words:
    what two pages are compared as, since a piece more in one moves every offset after it."""
    where = page.rfind(TRAILER)
    return page if where < 0 else page[:where]


def chromed_in(page: str, language: str, named: Callable[[dict[str, Any]], str]) -> str:
    """A written page in `language`'s words, where its comment has them, without the
    comment; in the language it is written in, the page exactly as it is. The page as
    written, less the comment, where the comment does not fit it: a page edited by hand,
    or cut short, is served as written rather than spliced wrong.
    `named` gives a named piece (`SHEET`, `WORDS`) as the page would carry it."""
    where = page.rfind(TRAILER)
    if where < 0:
        return page
    body = page[:where]
    try:
        told = json.loads(page[where + len(TRAILER) :].strip().removesuffix(_TRAILER_END))
        spans = told["spans"]
        base = str(told["base"])
    except (ValueError, KeyError, TypeError):
        return body
    code = (language or "").split("-")[0].lower()
    if code == base.split("-")[0].lower():
        # Read in the language it is written in: the page exactly as on disk, which is
        # what a save keeps.
        return page
    out: list[str] = []
    at = 0
    for span in spans:
        try:
            start, size, by = int(span[0]), int(span[1]), span[2]
        except (ValueError, TypeError, IndexError):
            return body
        if start < at or start + size > len(body):
            return body
        out.append(body[at:start])
        value = by.get(code) if isinstance(by, dict) else None
        if value is None:
            out.append(body[start : start + size])
        elif isinstance(value, dict):
            out.append(named(value))
        else:
            out.append(str(value))
        at = start + size
    out.append(body[at:])
    return "".join(out)
