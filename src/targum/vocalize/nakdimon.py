"""Nakdimon, from Gershuni and Pinter's "Restoring Hebrew Diacritics Without a Dictionary".

Picked over the alternatives on measured accuracy, but as much on behaviour: it is the
only diacritizer surveyed that returns the letters it was given. The others delete a
matres lectionis by default, turning ktiv male into ktiv haser, and one deletes the maqaf
and fuses the words either side. Its weights ship inside the wheel, so there is no
download step and nothing for `targum models` to manage.
"""

from __future__ import annotations

import logging

from ..errors import TargumError
from ..models import Segment

# diacritize() hard-codes maxlen=10000 and pads every sentence to it, so a twenty-word
# line costs what a whole chapter would. Sizing the window to the line is byte-for-byte
# identical and around thirty times faster. The ceiling is the library's own default,
# kept so that a very long segment behaves exactly as it always did.
LOG = logging.getLogger(__name__)

FLOOR, CEILING = 128, 10000


def window(text: str) -> int:
    return min(CEILING, max(FLOOR, len(text) + 16))


class NakdimonVocalizer:
    # 2, because a document pointed by 1 was pointed by a run that lost every sentence
    # to the first one Nakdimon disliked. The name is in the cache key, so renaming is
    # what makes the fix reach texts already built — and re-pointing costs nothing,
    # since it runs here rather than at a provider.
    name = "nakdimon/2"

    @property
    def model(self) -> str | None:
        return "Nakdimon.onnx"

    def available(self) -> tuple[bool, str]:
        try:
            import nakdimon  # noqa: F401
        except ImportError:
            return False, "nakdimon is not installed"
        return True, ""

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        try:
            import nakdimon
            from nakdimon.predict import predict
        except ImportError as exc:  # pragma: no cover - the package is a hard dependency
            raise TargumError(
                "Adding vowel points needs the nakdimon package.",
                "pip install nakdimon",
            ) from exc

        out: dict[str, str] = {}
        failed = 0
        for segment in segments:
            text = segment.text
            if not text.strip():
                continue
            # Per sentence, because the alternative is what happened: Nakdimon raises
            # bare AssertionErrors on input it dislikes, the caller caught it around the
            # whole call, and one bad sentence in Judenstaat threw away the vowels for
            # the other 1,079. The document came out 123 of 1,080 pointed — all of them
            # from pointing already in the source — and said nothing about it.
            try:
                out[segment.id] = predict(text, nakdimon.MAIN_MODEL, maxlen=window(text))
            except Exception as error:  # noqa: BLE001 - a third-party model, not our code
                failed += 1
                LOG.debug("no vowel points for %s: %s", segment.id, error)
        if failed:
            LOG.warning(
                "the diacritizer could not point %d of %d sentences; the rest are pointed",
                failed,
                len(segments),
            )
        return out
