"""Difficulty bands.

Six bands, from the word a learner meets in their first week to the one a native
speaker looks up. What puts a word in a band is stated in the artifact and shown in
the reader, because a learner should know whether they are looking at curated level
data or a frequency proxy.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Protocol

from ..models import Segment, Token

BAND_COUNT = 6

# A word nothing can rate, because the language has no frequency data behind it. Shown
# as no level at all rather than as a guess.
UNRATED = 0

# Words a learner does not have to acquire, and so words a difficulty count leaves out.
# They are still tokens — the reader can tap a name, hear it read, and press `i` — but
# a frequency band for אחשורוש says nothing true about how hard Esther is, and counting
# every name in a chronicle as a hard word would move it a shelf up the library.
NOT_VOCABULARY = frozenset({"PROPN", "NUM"})

# What a lemmatizer writes when it could not read a token at all. DICTA's, and the only
# one measured here: 318 tokens across the shelf on 2026-09-17. It is not a word, and
# every one of them entered a reader's ledger as a word nobody knows, banded hardest
# (targum-internal#305).
NOT_A_WORD = frozenset({"[unk]", "[UNK]", "<unk>", ""})

# Hebrew words a lemmatizer keeps calling verbs that are not verbs. A closed set, small
# and unlikely to grow, so it is written out rather than inferred.
#
# `יש` and `אין` are the existential particles — "there is", "there is not" — and have no
# root, no binyan and no conjugation. DICTA tagged `יש` VERB 2,521 times across the shelf.
# The ledger survives it, because the lemma is right and that is what a word is filed
# under; what does not survive is everything keyed to the part of speech. A card offering
# the conjugations of `יש` is offering a table that does not exist.
#
# Written as the bare (unpointed) form, which is what a lemma is compared as everywhere
# else here.
NEVER_A_VERB = frozenset({"יש", "אין"})


# The same fact, as the reader receives it: a seventh column on every token row, 0 for
# a word, 1 for a name, 2 for a number. What the reader calls them is `KIND_NAMES` in
# reader.js, and a word marked while wearing one of those keeps it as its band — which
# is how the ledger and the ulpan ladder know to leave it out.
KIND_COLUMN = {"PROPN": 1, "NUM": 2}

# Plain difficulty, easiest first. Deliberately not CEFR levels: these come from
# frequency, and calling level 3 "B1" would claim a correspondence that has not been
# established. Deliberately not numbers either, in anything a reader sees.
BAND_NAMES = {
    1: "easy",
    2: "fairly easy",
    3: "moderate",
    4: "hard",
    5: "very hard",
    6: "extremely hard",
}

# What the reader offers: mark this level and everything harder.
HIGHLIGHT_LABELS = {
    2: "fairly easy and up",
    3: "moderate and up",
    4: "hard and up",
    5: "very hard and up",
    6: "extremely hard only",
}

# How the levels were worked out, said in the reader rather than left implied.
METHOD_LABELS = {
    "frequency": "by how common each word is",
    "none": "not rated, since this language has no frequency data",
}


def method_label(method: str) -> str:
    if method.startswith("curated:"):
        return f"from the {method.split(':', 1)[1]} word list"
    return METHOD_LABELS.get(method, method)


NO_METHOD = "none"

#: The rule that a segment in a language other than its document's is left unread, in
#: the annotator's name. A name, because the name is what decides whether an existing
#: annotation is the one this code would write: every Daniel and Ezra on the shelf was
#: annotated before a block could say it was Aramaic, and carries a Hebrew reading of
#: it. A new component in the name is what makes them be read again, and reading again
#: is free — nothing here is fetched or bought.
#:
#: `languages/2` (2026-09-05): left unread *unless the lemmatizer can read it*, and where
#: it is read, left unrated. The scripture path can read the Aramaic of Daniel and Ezra,
#: so it is looked up rather than skipped and the blank page those books had is now the
#: worse of the two answers — but the band table and the register are Hebrew, and asked
#: about Aramaic they call ordinary words rare (targum-internal#64, #195).
#:
#: `languages/3` (2026-09-07): a token with no letter of its block's script is not a
#: word of that block. A community notice photographed off a phone carried "Hannah",
#: "Chananel", "22:15" and a calendar emoji inside its Hebrew, and every one came back
#: a word: tappable, counted against "N of M known", and "Hannah" filed in the ledger as
#: extremely hard. English inside a Hebrew text is something a Hebrew reader reads past.
#: `languages/4` (2026-09-17): a token the lemmatizer could not read is not a word
#: either. `[unk]` is what DICTA writes when it fails, and 318 of them across the shelf
#: went into readers' ledgers as words nobody knows, banded hardest. And `יש` is not a
#: verb however often it is tagged one — 2,521 times here — which the ledger survives and
#: the card does not: conjugations offered for a word that has none. See `NOT_A_WORD` and
#: `NEVER_A_VERB` above, and targum-internal#305.
LANGUAGES = "languages/4"

#: The rule that English inside a text in another Latin-script language is not a word of
#: that text, in the annotator's name for the same reason as `LANGUAGES` above.
#:
#: `foreign/1` (2026-09-15): an Italian lesson glossing "Meglio tardi che mai" as "but
#: better late than never" had every English word tappable, markable and counted toward
#: "N of M known". `in_script` cannot see it — English and Italian share an alphabet — so
#: this asks the words instead. See `foreign_runs`. Only in the name of an annotator whose
#: lemmatizer marks foreign words (`marks_foreign`), which is the model's and never
#: Hebrew's: renaming DICTA's annotator re-reads the whole shelf on a box with no GPU.
FOREIGN = "foreign/1"

#: The language a foreign run is checked against. English because it is the language
#: every translation and every teacher's aside on the shelf is in; another would be a
#: guess at a problem nobody has shown.
FOREIGN_TO = "en"


def foreign_runs(
    tokens: Sequence[Token], language: str, zipf: Callable[[str, str], float]
) -> set[int]:
    """The positions of tokens that are English rather than words of `language`.

    Two signals, both needed. The tagger calls the word X — "other", where UD files a
    foreign word — and the run of X words it sits in is more common in English than in
    the text's language. The run, and not the word, because "in for a penny, in for a
    pound" is half made of words Italian has too; and the tag, not frequency alone,
    because "weekend" in an Italian sentence is an Italian word. Neither is enough by
    itself: the model also gives up and calls a whole Italian paragraph X, and every
    word of Cuore's "vieni avanti sei venuto" stays Italian by the count.
    """
    code = language.split("-")[0].lower()
    out: set[int] = set()
    if code == FOREIGN_TO:
        return out
    run: list[int] = []
    for index in range(len(tokens) + 1):
        if index < len(tokens) and tokens[index].pos == "X":
            run.append(index)
            continue
        if run:
            words = [tokens[at].surface.lower().strip("'’") for at in run]
            there = sum(zipf(word, FOREIGN_TO) for word in words)
            here = sum(zipf(word, code) for word in words)
            if there > here:
                out.update(run)
            run = []
    return out


#: What a language is written in, for the rule above. Anything not listed is written in
#: letters of some kind, and a token with no letter at all — a time, a number, an
#: emoji — is not a word in any of them.
SCRIPTS: dict[str, range] = {
    "he": range(0x05D0, 0x05EB),
    "arc": range(0x05D0, 0x05EB),
    "yi": range(0x05D0, 0x05EB),
    "ru": range(0x0400, 0x0530),
    "uk": range(0x0400, 0x0530),
    "ar": range(0x0600, 0x0700),
}


#: What is left of a Hebrew word when the word itself is English (2026-09-14). Spoken
#: Hebrew puts its prefixes on English words — ה-AI, וה-NSA, ב-MIT, שה-app — and a
#: transcript writes them apart: "ה AI". With the English read past, the prefix was left
#: standing as a word of its own, tappable and counted, and "ה" filed in the ledger. Only
#: letter runs that are nothing but prefixes: מה, לה, בה, כה, של and שב are words, and
#: are not here.
PREFIXES = frozenset(
    {
        "ה",
        "ו",
        "ב",
        "כ",
        "ל",
        "מ",
        "ש",
        "וה",
        "שה",
        "ושה",
        "כשה",
        "וב",
        "ול",
        "ומ",
        "וכ",
        "וש",
        "כש",
        "וכש",
    }
)
_MARKS = re.compile("[\u0591-\u05c7]")


def is_stranded_prefix(surface: str, following: str, language: str) -> bool:
    """Whether a token is only a Hebrew prefix, written apart from the English word it
    belongs to — the next word with letters in it, past a hyphen or a maqaf."""
    if (language or "").split("-")[0].lower() not in {"he", "iw"}:
        return False
    bare = _MARKS.sub("", surface).strip("-\u05be")
    return bare in PREFIXES and bool(following) and not in_script(following, language)


#: The same prefix written onto the English word rather than apart from it: ה-AI, בMIT.
_PREFIXED_FOREIGN = re.compile(
    "^[\u05d5\u05d4\u05d1\u05db\u05dc\u05de\u05e9]{1,3}[-\u05be]?(?P<rest>[^\u05d0-\u05ea]+)$"
)


def is_prefixed_foreign(surface: str, language: str) -> bool:
    """Whether a token is a Hebrew prefix joined to a word with no Hebrew letter in it,
    which is the English word it belongs to and not a Hebrew word."""
    if (language or "").split("-")[0].lower() not in {"he", "iw"}:
        return False
    found = _PREFIXED_FOREIGN.match(_MARKS.sub("", surface))
    return found is not None and any(char.isalpha() for char in found.group("rest"))


def in_script(surface: str, language: str) -> bool:
    """Whether this token has a letter of the language it is supposed to be in.

    A Latin name inside a Hebrew line, a clock time, an emoji: none is a word of the
    text, and none should be counted, tapped or learned as one. Asked of the surface
    rather than of the tagger, because the tagger answered confidently about all three.
    """
    span = SCRIPTS.get((language or "").split("-")[0].lower())
    if span is None:
        return any(char.isalpha() for char in surface)
    return any(ord(char) in span for char in surface)


def reads(lemmatizer: object | None, segment: Segment) -> bool:
    """Whether this lemmatizer says it can read this particular block.

    Asked of the object rather than declared on the protocol, because it is true of one
    implementation and false of every other: `ScriptureLemmatizer` can read the Aramaic
    of Daniel and Ezra because the Open Scriptures tagging covers it word for word, and
    nothing else here can read anything but the language it was built for. A lemmatizer
    that does not answer is one that cannot.

    Asked about the *block* and not merely its language, because the two are different
    questions and answering the easier one is how a text goes silently blank. Targum
    Onkelos is Aramaic and the tagging does not cover a word of it: a lemmatizer that
    said "yes, Aramaic" would be let through and would then produce nothing at all, for
    a whole book, with nothing anywhere saying why.
    """
    ask = getattr(lemmatizer, "reads", None)
    return bool(ask(segment)) if callable(ask) else False


def unread(segment: Segment, document_language: str, lemmatizer: object | None = None) -> bool:
    """Whether the annotator leaves this segment's words alone.

    A block in a language other than its document's is left without tokens rather than
    read as if it were in the document's. The lemmatizer, the bands, the register and
    the pronouncer were each chosen for the document's language, and every one of them
    answers confidently about a word in another: on Aramaic read as Hebrew, Stanza tagged
    half the tokens as names and gave יָת — the object marker — the lemma of the Hebrew
    verb נתן. No token is a word the reader can still read, and cannot tap; a wrong
    token is a card that lies.

    Unless something here can actually read it. That was the step this rule promised to
    the one after it (targum-internal#65, #67), and for biblical Aramaic it has arrived:
    the tagging covers Daniel and Ezra at 100% of words, so their Aramaic is looked up
    rather than guessed at, and a blank page is now the worse answer of the two. A
    lemmatizer that cannot read the block still gets nothing, which is every other case.
    """
    if segment.language_in(document_language) == document_language:
        return False
    return not reads(lemmatizer, segment)


def highlight_levels() -> list[dict[str, object]]:
    return [{"value": value, "label": label} for value, label in sorted(HIGHLIGHT_LABELS.items())]


class Lemmatizer(Protocol):
    """Surface forms into dictionary forms.

    Load-bearing rather than optional. Hebrew attaches ו, ה, ב, כ, ל, מ and ש directly
    to the word, and Russian inflects heavily, so looking up the surface form misses
    the majority of tokens in both.
    """

    @property
    def name(self) -> str:
        """Model identity, recorded on the annotation."""

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        """Tokens per segment id, with lemma and offsets but no band yet."""


class Pronouncer(Protocol):
    """Pointed words into how they are said.

    Optional, unlike the lemmatizer: a text with no reading is a text that reads exactly
    as it did before. The vowels are the input, so this can only ever run after the
    document has been pointed.
    """

    @property
    def name(self) -> str:
        """Engine identity, recorded on the annotation through the annotator's name."""

    def available(self) -> tuple[bool, str]:
        """Whether it can run here, and why not when it cannot."""

    def say(self, surfaces: list[str]) -> dict[str, str]:
        """A reading for each distinct pointed form that has one."""


class Bands(Protocol):
    """What makes a lemma hard."""

    @property
    def name(self) -> str: ...

    @property
    def method(self) -> str:
        """'frequency' or 'curated:<source>'. Shown to the reader."""

    @property
    def note(self) -> str:
        """One line on where the bands came from."""

    def supports(self, language: str) -> bool:
        """Whether this source can rate words in the language at all."""

    def band(self, lemma: str, language: str) -> int: ...
