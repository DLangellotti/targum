"""Frequency bands.

Works for every language with a corpus behind it and does not wait on curated
pedagogical data existing. Where a curated level list does exist for a language it
should be used instead and labelled as such; none is wired up yet, so Hebrew, Russian
and English all run on frequency here.
"""

from __future__ import annotations

from collections.abc import Callable

from ..errors import TargumError
from .base import BAND_COUNT, UNRATED

MISSING = (
    "Difficulty bands need the frequency data, which is not installed.",
    "uv tool install 'targum[difficulty]'  (or: pip install 'targum[difficulty]')",
)

# Zipf frequency, a log scale where 7 is a word like "the" and 2 is one most native
# speakers rarely write. The cuts are even across that range rather than tuned per
# language, so a band means the same thing whichever language you are reading.
CUTS = (5.5, 4.8, 4.1, 3.4, 2.7)


class FrequencyBands:
    """Bands from word frequency, via wordfreq's blended corpora."""

    def __init__(self) -> None:
        self._zipf: Callable[[str, str], float] | None = None

    @property
    def name(self) -> str:
        return "wordfreq"

    @property
    def method(self) -> str:
        return "frequency"

    @property
    def note(self) -> str:
        return (
            "Levels come from how often a word is used, not from a graded syllabus. "
            "No curated level list is available for these languages."
        )

    def supports(self, language: str) -> bool:
        """Whether there is frequency data behind this language at all.

        Latin has none. Without this every Latin word scores as rare, which is worse
        than saying nothing: it looks like an answer.
        """
        try:
            from wordfreq import available_languages
        except ImportError:
            return False
        return language.split("-")[0].lower() in available_languages()

    def zipf(self) -> Callable[[str, str], float]:
        if self._zipf is None:
            try:
                from wordfreq import zipf_frequency
            except ImportError as exc:
                raise TargumError(*MISSING) from exc
            self._zipf = zipf_frequency
        return self._zipf

    def band(self, lemma: str, language: str) -> int:
        if not self.supports(language):
            return UNRATED
        score = self.zipf()(lemma, language.split("-")[0].lower())
        for index, cut in enumerate(CUTS, start=1):
            if score >= cut:
                return index
        return BAND_COUNT


def available() -> bool:
    try:
        import wordfreq  # noqa: F401
    except ImportError:
        return False
    return True
