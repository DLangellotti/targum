"""Errors that the CLI turns into a one-line message instead of a traceback."""

from __future__ import annotations


class TargumError(Exception):
    """Anything the user can act on. The CLI prints it and exits 1.

    `key` names this refusal in the string catalogue, for the ones a reader can meet
    (targum-internal#348). It is optional and most refusals have none: the command line
    is English by design, and a message raised where nobody is reading has nobody to
    translate it for. Where there is a key, the hint is `<key>.hint` by convention —
    one field, two sentences, and no second field to keep in step.

    The message stays here in English whatever the key says, because it is what the log
    records and what a traceback carries; the language is chosen where the refusal
    reaches a reader, which is the only place that knows who is reading.

    `fill` is what the sentence names — the address, the host — because the English is
    already interpolated by the time it is raised and a translation is not. Without it a
    Russian reader would be handed the catalogue's `{url}` with the braces still on.
    """

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        *,
        key: str = "",
        **fill: object,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.key = key
        self.fill = fill


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
