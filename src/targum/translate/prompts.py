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
OFFERED = ("he", "ru", "en", "ar", "fr", "es", "de", "la")

# What somebody may upload, and how far along each one is. Hebrew is what targum was
# built for and everything works in it. The other two are here because a reader who has
# Aramaic or Yiddish has nowhere else to take it, and they are honestly labelled: neither
# has the frequency data that rates a word's difficulty, and Yiddish has no lemmatiser
# either, so those readers get the text and the translation without the word levels.
#
# A picker is not a boundary — see `_prepare`, which checks a request against these.
READING = (("he", "alpha"), ("arc", "R&D"), ("yi", "R&D"))

# And what it may be turned into. English first because the glossaries are deepest there.
# Russian is beta rather than R&D: it has been read end to end, it is simply not Hebrew.
# Both words reach a reader as "Experimental" — see STAGE_LABELS below.
INTO = (("en", "alpha"), ("ru", "beta"))

# What a reader is shown. "R&D" and "beta" are a real difference — a language with no word
# levels against one that simply is not Hebrew — but it is a difference about how targum
# was built, not one anybody choosing from a picker can act on. Both read as experimental;
# the note under the picker is where the two part company.
STAGE_LABELS = {"alpha": "alpha", "beta": "Experimental", "R&D": "Experimental"}


def stage_label(stage: str) -> str:
    return STAGE_LABELS.get(stage, stage)


_NAMES = {
    "he": "Hebrew",
    "ru": "Russian",
    "en": "English",
    "fr": "French",
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
