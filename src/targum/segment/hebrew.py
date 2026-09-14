"""Hebrew sentences, drawn by rule rather than by Stanza's tokenizer.

Stanza's Hebrew tokenizer is trained on UD_Hebrew-HTB, CC BY-NC-SA, the same treebank
the lemmatizer it replaced was trained on. The annotator swap (targum-internal#116) moved
every Hebrew *word* off that model and left every Hebrew *boundary* on it: DICTA takes a
sentence at a time and publishes no splitter, so each sentence it was handed had been cut
by the NonCommercial one, and `LICENSING.md` said otherwise. This is the splitter that
makes that sentence true (targum-internal#146).

**Why a rule is enough here.** Hebrew has no capitalisation, which is what a splitter for
English leans on to tell "Dr. Cohen" from the end of a sentence — and is why the Stanza
docstring reached for a model. But Hebrew does not abbreviate with a full stop either: it
uses geresh and gershayim (ד״ר, תרנ״ז, ע״ד), or the ASCII quote and apostrophe standing in
for them (ד"ר, וכו'), and none of those is a terminal mark. What is left for a full stop
to be is the end of a sentence, an initial (N. O., נ.ב.), or a decimal point; the last two
are shapes, not vocabulary, and a shape is what a rule can see.

**What was measured, on the 47 readers' stored segmentation, before this replaced it.**
Stanza had never once split a Hebrew sentence on an exclamation mark — 2,100 of them sat
mid-segment ahead of the next sentence — and it split on three ASCII dots but not on the
ellipsis character. It also cut a speech tag off its speech wherever a dash introduced
one (`– מה יש? – שאל הוא עברית.`), so the English reader carried "he asked in Hebrew." as
a segment of its own, 327 times. Those are the disagreements this has with it, and each
is on purpose. `scripts/measure_segmentation.py` reproduces the count and shows a sample.

**What a moved boundary costs, and the decision.** A segment is what the translation
cache is keyed on, so every segment whose text changes is a translation bought again.
Nothing here is allowed to buy one: `pipeline.segment` reuses `segments.json` whenever
the document hash matches, without looking at the segmenter's name, so **a text already
on a shelf keeps the segmentation it was translated under, and only a new ingest — or a
rebuild that was told to force — is split by this.** The name is recorded so the artifact
says which drew its lines; it is not part of any cache key, and `SCHEMA_VERSION` is
untouched, because bumping it would re-buy every translation in the library to move
boundaries that are, for reading, fine where they are.

The rules:

- A run of terminal marks (`.` `!` `?` `…`) followed by space ends a sentence when it holds
  a `!` or a `?`, or is one full stop. A run that is only ellipsis (`…`, `...`) is a pause
  mid-utterance — "כן… אתה" — and does not end anything, unless what follows is a dash or
  an opening quote, which is a new speaker.
- A closing mark after the run — `"` `'` `)` `]` and their typographic forms — means the
  sentence that ended was inside a quotation or a parenthesis, and the outer sentence
  goes on: `"מה אתה רוצה?" שאל.` is one thing said and who said it. A full stop after the
  closing quote (`"קורס".`) is bare, and ends it.
- A dash after the run continues the turn: `– מה יש? – שאל הוא עברית.` is the speech and
  its tag, and a translation of the tag alone is a fragment. Three dashes in a row are a
  section break, and a dash the block ends on stays where it is.
- A full stop after a single letter that is itself preceded by a space, a full stop or the
  start of the text is an initial, and continues. Only a letter: `בן 5.` ends, and so does
  `חו"ל.`, whose quote is a gershayim inside the word and not a quote before an initial.
- A mark followed by anything but space or the end of the block — `3.14`, `?"בוא` — is
  inside something and ends nothing. Bidirectional and zero-width marks, which pasted text
  carries after nearly every full stop, are looked through.

Every lookup reads a fixed handful of characters around the mark rather than the rest of
the block, and the run is matched by one character class with nothing to backtrack into:
a reader can upload a single block of a megabyte, or a line of ten thousand dots, and the
build must stay linear in it.
"""

from __future__ import annotations

import re

from .base import Segmenter
from .stanza_segmenter import AUDITED, StanzaSegmenter, stanza_code

#: Part of every segments.json this draws. Bump it when a rule changes, so the artifact
#: says which rules cut it — see the docstring for why that is a record and not a key.
NAME = "hebrew-rules/1"

#: Sof pasuk (׃) is the verse end of pointed text, and ends a sentence in a paragraph too.
TERMINAL = ".!?…׃"
CLOSING = "\"'”’»)]"
DASHES = "–—-"
OPENING = "\"'“‘«"
#: Bidirectional and zero-width controls, invisible and not whitespace.
FORMAT = "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"

# A run: one terminal mark, then any mix of marks, closers and invisibles. One class with
# no alternative to fall back to, so a run of ten thousand dots is matched once.
_RUN = re.compile(rf"[{re.escape(TERMINAL)}][{re.escape(TERMINAL + CLOSING + FORMAT)}]*")
# The first three visible characters after the run, read in place rather than by slicing
# the rest of the block.
_AFTER = re.compile(rf"[\s{FORMAT}]*(.{{0,3}})", re.S)
_LETTER = re.compile(r"[^\W\d_]")
_DROP_FORMAT = {ord(c): None for c in FORMAT}
# The word a full stop closes, dots and hyphens inside it included: `Dr`, `e.g`, `J.-C`.
# Anchored at the end of a short window, so it reads a handful of characters and never
# the block before them.
_ABBREVIATED = re.compile(r"[^\W\d_]+(?:[.\-'’][^\W\d_]+)*$")
#: How far back an abbreviation is looked for. Longer than any in `cased.ABBREVIATIONS`.
_LOOKBACK = 24


def _initial(text: str, at: int) -> bool:
    """Whether the full stop at `at` follows a lone letter: `N.`, `נ.ב.`."""
    before = text[at - 1 : at] if at else ""
    if not before or not _LETTER.fullmatch(before):
        return False
    earlier = text[at - 2 : at - 1] if at >= 2 else ""
    return not earlier or earlier.isspace() or earlier == "."


def _abbreviation(text: str, stop: int, abbreviations: frozenset[str]) -> bool:
    """Whether the full stop at `stop` closes a word on the language's list."""
    word = _ABBREVIATED.search(text, max(0, stop - _LOOKBACK), stop)
    return bool(word) and word.group(0).lower() in abbreviations  # type: ignore[union-attr]


#: A dash that opens a line of dialogue, or closes the speech before its tag.
_DIALOGUE = "—–"
#: How long a quotation may run and still be one segment. A speech and its tag belong in
#: one row; a quoted page does not, and inside a longer one the ordinary rules apply.
QUOTED_MAX = 400


def _quotations(text: str) -> list[tuple[int, int]]:
    """Where a closed quotation runs, as (opening mark, closing mark), outermost only.

    For `cased.QUOTING`. Guillemets and curly quotes pair by kind. A straight `"` has one
    shape for both ends, so it pairs by what touches it: space before and a letter after
    opens, a letter before closes, anything else is left alone. A line that opens with a
    dash is dialogue, and its free-standing dashes pair in order — `— Non lo so. Forse
    domani — rispose.` Only what closes counts: a quotation still open at the end of the
    block is one that runs on into the next paragraph, and holding it would hold the rest
    of this one. One pass and one sort, so a megabyte block stays cheap.
    """
    spans: list[tuple[int, int]] = []
    waiting: dict[str, list[int]] = {"«": [], "“": [], '"': []}
    pairs = {"»": "«", "”": "“"}
    dashes: list[int] = []
    dialogue = text.lstrip()[:1] in _DIALOGUE if text.strip() else False
    for at, char in enumerate(text):
        if char in waiting and char != '"':
            waiting[char].append(at)
        elif char in pairs:
            if waiting[pairs[char]]:
                spans.append((waiting[pairs[char]].pop(), at))
        elif char == '"':
            before = text[at - 1] if at else " "
            after = text[at + 1] if at + 1 < len(text) else " "
            if (before.isspace() or before in "([«“" + _DIALOGUE) and not after.isspace():
                waiting['"'].append(at)
            elif not before.isspace() and waiting['"']:
                spans.append((waiting['"'].pop(), at))
        elif dialogue and char in _DIALOGUE:
            before = text[at - 1] if at else " "
            after = text[at + 1] if at + 1 < len(text) else " "
            if before.isspace() or after.isspace():
                dashes.append(at)
    spans.extend(zip(dashes[0::2], dashes[1::2], strict=False))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(span for span in spans if span[1] - span[0] <= QUOTED_MAX):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _ends_here(
    text: str,
    found: re.Match[str],
    *,
    cased: bool = False,
    abbreviations: frozenset[str] = frozenset(),
    quotations: bool = False,
) -> bool:
    """Whether a run of marks ends a sentence.

    `cased`, `abbreviations` and `quotations` are for a script with capitals (`cased.py`).
    With none, which is how Hebrew calls this, every rule is exactly the one the module
    docstring lists and `NAME` records.
    """
    end = found.end()
    if end < len(text) and not text[end].isspace():
        # `3.14`, `?"בוא` — the mark is inside something.
        return False
    run = found.group(0)
    last_closer = max(run.rfind(closer) for closer in CLOSING)
    marks = run[last_closer + 1 :].translate(_DROP_FORMAT)
    if not marks:
        # `...!)` — the terminal is inside something, and the outer sentence goes on.
        return False
    after = _AFTER.match(text, end).group(1)  # type: ignore[union-attr]
    opens = quotations and len(after) > 1 and after[0] in OPENING and not after[1].isspace()
    if cased and after and after[0] in CLOSING and not opens:
        # French sets a space inside its guillemets — `« Pourquoi ? »` — so the closer
        # arrives after the space; it is still this sentence's, and the rule above keeps
        # what follows it with it. A straight quote is a closer and an opener both, and
        # where quotations are read, one with a letter after it is the next sentence's:
        # `È finita. "Andiamo," disse.`
        return False

    if "!" not in marks and "?" not in marks and marks not in (".", "׃"):
        # Ellipsis alone is a pause, unless a new speaker takes over after it — or, where
        # there are capitals, a new sentence visibly starts.
        return bool(after) and (after[0] in DASHES + OPENING or (cased and after[0].isupper()))
    if after and after[0] in DASHES and (len(after) == 1 or after[1].isspace()):
        # `– שאל הוא` — the tag stays with what was said. `– – –` is a section break.
        return len(after) > 2 and after[2] in DASHES
    if marks != ".":
        return True
    stop = found.start() + last_closer + 1
    if _initial(text, stop):
        return False
    if cased:
        # A sentence starts with a capital, so a full stop before a small letter did not
        # end one (`approx. five`), and one closing a word on the list did not either.
        if after and after[0].islower():
            return False
        if _abbreviation(text, stop, abbreviations):
            return False
    return True


def sentences(
    text: str,
    *,
    cased: bool = False,
    abbreviations: frozenset[str] = frozenset(),
    quotations: bool = False,
) -> list[str]:
    """One block's sentences, in order, whitespace-trimmed, nothing dropped.

    With `quotations`, a mark inside a closed quotation ends nothing: `"Non lo so. Forse
    domani," rispose.` is one thing said and who said it. A run that reaches the closing
    mark itself is not inside, and is read by the rules as before.
    """
    out: list[str] = []
    start = 0
    held = _quotations(text) if quotations else []
    at = 0
    for found in _RUN.finditer(text):
        while at < len(held) and held[at][1] < found.end():
            at += 1
        if at < len(held) and held[at][0] < found.start():
            continue
        if not _ends_here(
            text, found, cased=cased, abbreviations=abbreviations, quotations=quotations
        ):
            continue
        piece = text[start : found.end()].strip()
        if piece:
            out.append(piece)
        start = found.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return out


#: Written in the Hebrew alphabet, abbreviated with geresh and gershayim, and uncased:
#: the rules above fit all three. Yiddish and Aramaic used to be handed to Stanza, which
#: has models for neither, so a paragraph of either failed the build.
HEBREW_SCRIPT = frozenset({"he", "yi", "arc"})


class HebrewSegmenter:
    """Rules for every language; Stanza, held as the delegate, only where it is audited.

    Hebrew-script text by the rules above, text in a script with capitals by the same
    rules taught abbreviations and case (`cased.py`), and Stanza for a language listed in
    `stanza_segmenter.AUDITED`, which today is none. The class keeps its name because
    everything that builds a reader constructs it.

    The same shape as `annotate.dicta.DictaLemmatizer` and for the same reason: the
    language only arrives with the text, so the thing that routes by it has to hold both.
    Every name that could draw a line is part of this one's, so a segments.json says
    everything that could have drawn its lines.
    """

    def __init__(self, *, other: Segmenter | None = None, auto_download: bool = True) -> None:
        self.other: Segmenter = (
            other if other is not None else StanzaSegmenter(auto_download=auto_download)
        )

    @property
    def name(self) -> str:
        from . import cased

        return f"{NAME}+{cased.NAME}+{self.other.name}"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        from . import cased

        code = stanza_code(language)
        if code in HEBREW_SCRIPT:
            return [sentences(text) for text in texts]
        if code in AUDITED:
            return self.other.split(texts, language)
        return [cased.sentences(text, code) for text in texts]
