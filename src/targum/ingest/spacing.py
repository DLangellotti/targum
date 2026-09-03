"""Words that arrive with the space between them missing.

A scraped text loses spaces where its source lost a boundary: a byline runs into the
heading under it, the end of one paragraph into the start of the next. Ben Yehuda's
own .txt of *Der Judenstaat* opens with `ברקוביץהקדמה` — the translator's name and the
word "הקדמה" with nothing between them. The reader then treats the pair as one word,
looks it up as one word, and finds nothing, because there is no such word.

This runs once, when a text is ingested, and never in the reader: what the page loads
is already repaired, so nothing here can cost a reader a millisecond.

Splitting a word that was never glued is worse than leaving a glued one alone — one is
a text with a seam in it, the other is a text this changed the words of. So the rules
are ordered by what they can prove, and only the ones that can prove it get to write.
"""

from __future__ import annotations

import re

from .. import lexicon

# Five Hebrew letters are written differently at the end of a word, and that is the
# whole of the rule: a final form appears at the end of a word and nowhere else. So a
# final form with letters after it is not a long word — it is two words, and the boundary
# is not a guess. Nothing in the language spells a word this way.
FINALS = "ךםןףץ"

# What the certain rule is certain about is where a boundary falls in text that is
# spelled correctly. Scanned text is not: Ben Yehuda's OCR reads ו as ן often enough that
# `ןיזבח` — one word, one wrong letter — looked like a final nun with a word after it and
# came apart into `ן יזבח`. No Hebrew word is one letter long, so a piece that short means
# the premise was wrong and this is a typo rather than a seam. Measured over every text
# here: the guard costs nothing in repairs and takes the damage to none.
MIN_PIECE = 2

# The other half of the same rule, used to reject a proposed split rather than make one:
# these five cannot end a word, because that is what their final forms are for.
NON_FINAL = "כמנפצ"

_LETTERS = "".join(chr(c) for c in range(0x05D0, 0x05EB))

# The points and accents that ride on a letter. Built from code points on purpose: maqaf
# (U+05BE), paseq (U+05C0) and sof pasuq (U+05C3) sit in the middle of this range and are
# separators — a class written as a span swallows them, and then בית־ישראל is one token
# and every hyphenated name in the Tanakh looks like a word run together.
_MARKS = "".join(
    chr(c) for c in [*range(0x0591, 0x05BE), 0x05BF, 0x05C1, 0x05C2, 0x05C4, 0x05C5, 0x05C7]
)

_TOKEN = re.compile(f"[{_LETTERS}][{_LETTERS}{_MARKS}]*")

# What the lexical rule demands before it will touch a word. The numbers are not tuning
# knobs to be turned up for more repairs: they are what it takes for a split to be worth
# more than the word it rewrites. Both halves have to be words a Hebrew reader meets —
# in either register, so the bar is `lexicon.strength`, not modern frequency — both have
# to be long enough not to be a stray prefix, and the whole has to be long enough that no
# ordinary word is being taken apart.
_MIN_PART = 3
_MIN_STRENGTH = 4.0
_MIN_WHOLE = 10

# A rival boundary is any other place the word comes apart into two words the lexicon
# knows at all — a much lower bar than the one that lets a repair happen. ותהיהמלחמה is
# ותהי המלחמה and also ותהיה מלחמה, both real, and the wrong one is a sentence the reader
# will believe. Where there is more than one reading, the seam is not evidence.


def _bare(token: str) -> str:
    """The letters alone. Points are how a word is read, not which word it is."""
    return "".join(c for c in token if c in _LETTERS)


def _spellable(part: str) -> bool:
    """Whether a run of letters could be a Hebrew word on its own.

    Not whether it is one — only that nothing in how it is written rules it out. A final
    form anywhere but the end, or a letter that has a final form standing at the end
    without using it, and it is not a word.
    """
    if not part:
        return False
    return not any(c in FINALS for c in part[:-1]) and part[-1] not in NON_FINAL


def _cuts(token: str) -> list[int]:
    """Where to break this token, as indexes into the token as written.

    Two rules, and they are tried in the order of what they can prove.
    """
    bare = _bare(token)
    if len(bare) < 4:
        return []

    # Where each letter sits in the token as written, so a cut worked out on the letters
    # lands in the right place in a word carrying points.
    at = [i for i, c in enumerate(token) if c in _LETTERS]

    # The certain rule. Every final form but the last letter ends a word, so every one of
    # them is a cut — three words run together come apart in one pass.
    #
    # The cut goes after the marks the letter carries, not straight after the letter: a
    # dagesh or a vowel belongs to the letter before it, and cutting between them puts a
    # point at the head of the next word.
    certain = [n for n, c in enumerate(bare[:-1]) if c in FINALS]
    if certain:
        # Every piece has to be long enough to be a word. One that is not says the token
        # was misspelled rather than run together, and a misspelling is not this to fix.
        edges = [-1] + certain + [len(bare) - 1]
        if any(edges[i + 1] - edges[i] < MIN_PIECE for i in range(len(edges) - 1)):
            return []
        return [_after(token, at[n]) for n in certain]

    # The lexical rule, for glue the spelling cannot see. Only where the whole is a word
    # the lexicon cannot account for — not modern, not biblical, and not either of those
    # inflected — and where both halves are words a Hebrew reader meets. Anything the
    # lexicon can read as a word is left alone, whatever it could be split into.
    if len(bare) < _MIN_WHOLE or not lexicon.available() or lexicon.known(bare):
        return []
    passing: list[int] = []
    rivals = 0
    for n in range(_MIN_PART, len(bare) - _MIN_PART + 1):
        left, right = bare[:n], bare[n:]
        if not _spellable(left) or not _spellable(right):
            continue
        if lexicon.known(left) and lexicon.known(right):
            rivals += 1
        if min(lexicon.strength(left), lexicon.strength(right)) >= _MIN_STRENGTH:
            passing.append(n)

    # One place to cut, and nowhere else it could plausibly have been. Two candidates is
    # not a repair, it is a coin toss with the reader's text.
    if len(passing) != 1 or rivals != 1:
        return []
    return [_after(token, at[passing[0] - 1])]


def _after(token: str, index: int) -> int:
    """Just past the letter at `index` and everything hanging off it."""
    end = index + 1
    while end < len(token) and token[end] in _MARKS:
        end += 1
    return end


# The inverse rule, for the one way the certain rule used to be wrong. Before `MIN_PIECE`
# it cut after every final form it found, so `ןיזבח` — one OCR'd word — became `ן יזבח`,
# and a text built then still says so. The evidence for the join is the evidence the
# guard uses for the refusal: no Hebrew word is one letter long, and a final form on its
# own is not a word, so a lone final letter beside a word is a piece of that word.
#
# It sits to the left of its word — the cut fell after it — and that is the case this
# is written for. A lone final letter to the right of a word is the same shape from a
# doubled final, and is joined the other way when nothing stands to its right.
#
# The neighbour has to be a word, `MIN_PIECE` letters or more. An alef-bet written out
# one letter at a time is a row of lone letters with finals among them, and it stays
# as it is.
#
# And no quotation mark may touch the letter. Hebrew abbreviates with gershayim before
# the last letter — תנ"ך, רמב"ם, האו"ם, בג"ץ — and the letter after the mark is a final
# form standing on its own by every other measure. Scanned over every text built here,
# the rule without this clause found nothing else.
_QUOTES = "\"'\u05f3\u05f4\u201c\u201d\u2018\u2019"
_LONE = f"(?<![{_LETTERS}{_MARKS}{_QUOTES}])[{FINALS}][{_MARKS}]*(?![{_LETTERS}{_MARKS}{_QUOTES}])"
_WORD = f"[{_LETTERS}][{_MARKS}]*(?:[{_LETTERS}][{_MARKS}]*){{{MIN_PIECE - 1},}}"
_STRAY_LEFT = re.compile(f"({_LONE}) (?={_WORD}(?![{_LETTERS}{_MARKS}]))")
# The word is matched rather than looked behind for, because a lookbehind cannot be
# told to want two letters or more. The lookahead is what keeps the two rules apart:
# a lone letter with a word on either side belongs to the one on its right.
_STRAY_RIGHT = re.compile(
    f"(?<![{_LETTERS}{_MARKS}])({_WORD}) ({_LONE})(?! {_WORD}(?![{_LETTERS}{_MARKS}]))"
)


def stranded(text: str) -> list[str]:
    """Every lone final letter in `text` that `reglue` would put back on its word.

    The scan the repair is measured by: a built text with nothing here is clean.
    """
    return [m.group(1) for m in _STRAY_LEFT.finditer(text)] + [
        m.group(2) for m in _STRAY_RIGHT.finditer(text)
    ]


def reglue(text: str, language: str) -> str:
    """Take out the space a repair once put in front of a word that was never two.

    Only a lone final letter beside a word — the one split the certain rule made
    before it learned that a piece one letter long proves the word was misspelled
    rather than run together. Anything else that looks like a bad split is left,
    because nothing in the text can prove it was one.
    """
    if not language.split("-")[0].lower() == "he" or not text:
        return text
    text = _STRAY_LEFT.sub(r"\1", text)
    return _STRAY_RIGHT.sub(r"\1\2", text)


def unglue(text: str, language: str) -> str:
    """Put back the spaces a source dropped between two Hebrew words.

    Returns the text unchanged when there is nothing to repair, which is the ordinary
    case: across every text on this machine — the Tanakh, Herzl, news, poetry — this
    fires on a single word.
    """
    if not language.split("-")[0].lower() == "he" or not text:
        return text

    out: list[str] = []
    end = 0
    for match in _TOKEN.finditer(text):
        token = match.group(0)
        cuts = _cuts(token)
        if not cuts:
            continue
        out.append(text[end : match.start()])
        pieces: list[str] = []
        here = 0
        for cut in cuts:
            pieces.append(token[here:cut])
            here = cut
        pieces.append(token[here:])
        out.append(" ".join(piece for piece in pieces if piece))
        end = match.end()
    if not out:
        return text
    out.append(text[end:])
    return "".join(out)
