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
        self,
        message: str,
        hint: str | None = None,
        *,
        status: int | None = None,
        host: str = "",
        challenge: bool = False,
        via: str = "direct",
    ) -> None:
        super().__init__(message, hint)
        self.status = status
        self.host = host
        #: The host answered with a bot check rather than a page — Cloudflare's
        #: `cf-mitigated: challenge`, measured on 2026-09-08 as what six of the seven
        #: "unreachable" Hebrew hosts actually do. Not an address block: the laptop and
        #: the box got the identical answer. Worth telling a reader apart from a host
        #: that never answered, because their own browser passes the check.
        self.challenge = challenge
        #: Which way out the failing knock went: `direct` or `proxy`. The record of a
        #: shut door has to say which door.
        self.via = via


class ProviderError(TargumError):
    """A translation provider could not be used, or did not answer usefully."""


class ModelMissing(TargumError):
    """A language model is needed and is not on disk."""


class SkeletonChanged(TargumError):
    """A vocalizer altered a letter instead of only the marks above it.

    Raised per segment rather than per document: one bad sentence falls back to the
    source's own text, and the rest of the build keeps its vowels.
    """
