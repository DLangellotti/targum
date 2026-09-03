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
from .stanza_segmenter import StanzaSegmenter, stanza_code

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


def _initial(text: str, at: int) -> bool:
    """Whether the full stop at `at` follows a lone letter: `N.`, `נ.ב.`."""
    before = text[at - 1 : at] if at else ""
    if not before or not _LETTER.fullmatch(before):
        return False
    earlier = text[at - 2 : at - 1] if at >= 2 else ""
    return not earlier or earlier.isspace() or earlier == "."


def _ends_here(text: str, found: re.Match[str]) -> bool:
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

    if "!" not in marks and "?" not in marks and marks not in (".", "׃"):
        # Ellipsis alone is a pause, unless a new speaker takes over after it.
        return bool(after) and after[0] in DASHES + OPENING
    if after and after[0] in DASHES and (len(after) == 1 or after[1].isspace()):
        # `– שאל הוא` — the tag stays with what was said. `– – –` is a section break.
        return len(after) > 2 and after[2] in DASHES
    return not (marks == "." and _initial(text, found.start() + last_closer + 1))


def sentences(text: str) -> list[str]:
    """One block's sentences, in order, whitespace-trimmed, nothing dropped."""
    out: list[str] = []
    start = 0
    for found in _RUN.finditer(text):
        if not _ends_here(text, found):
            continue
        piece = text[start : found.end()].strip()
        if piece:
            out.append(piece)
        start = found.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return out


class HebrewSegmenter:
    """Rules for Hebrew; Stanza, held as the delegate, for every other language.

    The same shape as `annotate.dicta.DictaLemmatizer` and for the same reason: the
    language only arrives with the text, so the thing that routes by it has to hold both.
    The delegate's name is part of this one's, so a segments.json says everything that
    could have drawn its lines.
    """

    def __init__(self, *, other: Segmenter | None = None, auto_download: bool = True) -> None:
        self.other: Segmenter = (
            other if other is not None else StanzaSegmenter(auto_download=auto_download)
        )

    @property
    def name(self) -> str:
        return f"{NAME}+{self.other.name}"

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        if stanza_code(language) != "he":
            return self.other.split(texts, language)
        return [sentences(text) for text in texts]
