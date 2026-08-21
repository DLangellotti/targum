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


class ProviderError(TargumError):
    """A translation provider could not be used, or did not answer usefully."""


class ModelMissing(TargumError):
    """A language model is needed and is not on disk."""
