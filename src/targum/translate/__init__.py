"""Translation providers."""

from __future__ import annotations

from ..errors import ProviderError
from .anthropic_provider import AnthropicProvider
from .base import Provider
from .null import NullProvider

__all__ = ["AnthropicProvider", "NullProvider", "Provider", "build", "names"]

_BUILDERS = {
    "anthropic": AnthropicProvider,
    "null": NullProvider,
}


def names() -> list[str]:
    return sorted(_BUILDERS)


def build(name: str, **options: object) -> Provider:
    builder = _BUILDERS.get(name)
    if builder is None:
        raise ProviderError(f"No provider named '{name}'.", f"Available: {', '.join(names())}")
    if builder is NullProvider:
        return NullProvider()
    return AnthropicProvider(**options)  # type: ignore[arg-type]
