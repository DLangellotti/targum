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

_NAMES = {
    "he": "Hebrew",
    "ru": "Russian",
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "ar": "Arabic",
    "yi": "Yiddish",
    "la": "Latin",
}


def language_name(tag: str) -> str:
    """A name the model will recognise, falling back to the tag itself."""
    return _NAMES.get(tag.split("-")[0].lower(), tag)
