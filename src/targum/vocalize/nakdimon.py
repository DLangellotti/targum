"""Nakdimon, from Gershuni and Pinter's "Restoring Hebrew Diacritics Without a Dictionary".

Picked over the alternatives on measured accuracy, but as much on behaviour: it is the
only diacritizer surveyed that returns the letters it was given. The others delete a
matres lectionis by default, turning ktiv male into ktiv haser, and one deletes the maqaf
and fuses the words either side. Its weights ship inside the wheel, so there is no
download step and nothing for `targum models` to manage.
"""

from __future__ import annotations

from ..errors import TargumError
from ..models import Segment

# diacritize() hard-codes maxlen=10000 and pads every sentence to it, so a twenty-word
# line costs what a whole chapter would. Sizing the window to the line is byte-for-byte
# identical and around thirty times faster. The ceiling is the library's own default,
# kept so that a very long segment behaves exactly as it always did.
FLOOR, CEILING = 128, 10000


def window(text: str) -> int:
    return min(CEILING, max(FLOOR, len(text) + 16))


class NakdimonVocalizer:
    name = "nakdimon/1"

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
        for segment in segments:
            text = segment.text
            if not text.strip():
                continue
            out[segment.id] = predict(text, nakdimon.MAIN_MODEL, maxlen=window(text))
        return out
