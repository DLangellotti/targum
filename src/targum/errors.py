"""Errors that the CLI turns into a one-line message instead of a traceback."""

from __future__ import annotations


class TargumError(Exception):
    """Anything the user can act on. The CLI prints it and exits 1."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class UnsupportedSource(TargumError):
    """A source targum cannot read yet."""


class Unreachable(TargumError):
    """A host would not answer, as distinct from a page that is not there.

    The difference is the whole point: a 404 is one address a reader mistyped, and a
    403, a timeout or a refused connection is a door that will be shut the next time
    too. Only the second is worth remembering (`accounts.Store.reach`). `status` is the
    HTTP status where there was one and `None` where the connection never got that far.
    """

    def __init__(
        self, message: str, hint: str | None = None, *, status: int | None = None, host: str = ""
    ) -> None:
        super().__init__(message, hint)
        self.status = status
        self.host = host


class ProviderError(TargumError):
    """A translation provider could not be used, or did not answer usefully."""


class ModelMissing(TargumError):
    """A language model is needed and is not on disk."""


class SkeletonChanged(TargumError):
    """A vocalizer altered a letter instead of only the marks above it.

    Raised per segment rather than per document: one bad sentence falls back to the
    source's own text, and the rest of the build keeps its vowels.
    """
