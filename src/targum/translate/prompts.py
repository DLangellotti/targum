"""Prompts for the two translation styles."""

from __future__ import annotations

from ..models import Style

_SHARED = """You are translating {source} into {target} for a language learner reading \
the original alongside your translation.

You will be given numbered segments. Translate each one and return it under the same id.

Rules that hold for every segment:
- Translate every segment you are given, including single words, headings and fragments.
- One segment in, one segment out. Never merge two segments or split one.
- Keep names, numbers and dates as they are unless {target} has an established form.
- Keep the register of the original. A legal text stays legal, a plain one stays plain.
- Return the translation only. No notes, no transliteration, no commentary.
- Surrounding text is given for context. Do not translate it and do not quote it back."""

_STYLE = {
    Style.natural: """Translate into idiomatic {target}: what a reader would want as prose. \
Follow the conventions of {target} for word order and phrasing, and resolve idioms into \
their meaning.""",
    Style.direct: """Translate close to the structure of the original: keep its word order, \
its clause boundaries and its grammatical shape wherever {target} allows it, so a learner \
can see how the source is built. Render idioms literally. Awkward {target} is acceptable \
here and is often the point.""",
}


def system_prompt(source_language: str, target_language: str, style: Style) -> str:
    names = {"source": language_name(source_language), "target": language_name(target_language)}
    return f"{_SHARED.format(**names)}\n\n{_STYLE[style].format(**names)}"


# Offered in the picker on the start page, in the order they appear there. Each one
# has been checked end to end: a Stanza model to find dictionary forms with, and
# frequency data to rate words by, except Latin which has the first but not the second
# and so shows meanings without levels. Yiddish has neither and is not offered.
OFFERED = ("he", "ru", "en", "ar", "fr", "it", "es", "de", "la")

# What somebody may upload, and how its words are read. Hebrew is what targum was built
# for and its words are read locally by DICTA. The other two are here because a reader
# who has Aramaic or Yiddish has nowhere else to take it: Aramaic's words are not read at
# all (its Onkelos taps go to a list), and Yiddish, French, Russian and Italian (since
# 2026-09-13) are read by the model (`annotate/model_lemma.py`) because no Stanza model
# for them clears the licence bar; each is scored against its Universal Dependencies dev
# set before it is trusted.
#
# How far along each one is — the word the menu badges it with — is not here. It used to
# be ("alpha", "R&D"), and it disagreed with the badge in `lang.js` about Hebrew and
# Russian on the same day; since 2026-10-12 the one table is `stages.DECLARED`, checked
# by `tests/test_stages.py` (design.md §12, "A badge is a promise, checked").
#
# A picker is not a boundary — see `_prepare`, which checks a request against these.
READING = (
    ("he", "dicta"),
    ("arc", "none"),
    ("yi", "model"),
    ("fr", "model"),
    ("ru", "model"),
    ("it", "model"),
)

# And what it may be turned into. English first because the glossaries are deepest there.
# These two words are about the *into* side and are not a badge: Russian meanings have
# been read end to end and are simply not English; the upload page says "Experimental"
# beside Russian for it (`render.builder._staged`). Left alone by the standard of
# 2026-10-12 on purpose.
INTO = (("en", "alpha"), ("ru", "beta"))

# What a text may carry a rendering in without that being a language anybody reads it
# *into*. Targum Onkelos is Aramaic, beside the Hebrew of the Torah (targum-internal#65):
# it is half of a practice rather than a way of understanding the Hebrew, and nobody is
# handed a definition in it. So a reader keeps it whichever languages they said they read,
# it is never the language a book is said to open in, and while it is on show the word
# meanings stay in the language they were in — a Hebrew word looked up "into Aramaic"
# would be bought, and be no use to anybody.
BESIDE = frozenset({"arc"})

# What every account is learning whether it says so or not. Hebrew is what targum is for,
# and in this version the profile draws it ticked and will not let it be unticked. Empty
# this out when that stops being true; nothing else has to change.
REQUIRED_LEARNING = ("he",)

_NAMES = {
    "he": "Hebrew",
    "ru": "Russian",
    "en": "English",
    "fr": "French",
    "it": "Italian",
    "es": "Spanish",
    "de": "German",
    "ar": "Arabic",
    "yi": "Yiddish",
    "arc": "Aramaic",
    "la": "Latin",
}


def language_name(tag: str) -> str:
    """A name the model will recognise, falling back to the tag itself."""
    return _NAMES.get(tag.split("-")[0].lower(), tag)
