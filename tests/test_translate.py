from __future__ import annotations

from typing import Any

import httpx
import pytest

from targum.errors import ProviderError
from targum.models import Segment, SegmentedDocument, Style
from targum.translate import NullProvider, build, names
from targum.translate.anthropic_provider import (
    CHARS_PER_TOKEN,
    DEFAULT_MODEL,
    PRICES,
    TOKENS_PER_BATCH,
    AnthropicProvider,
)
from targum.translate.base import batches, context_window
from targum.translate.prompts import system_prompt


def make_segments(count: int) -> list[Segment]:
    return [
        Segment(id=f"0001.{i:03d}-aaaaaa", block_id="b0001", block_index=1, index=i, text=f"s{i}")
        for i in range(count)
    ]


def test_null_provider_returns_every_id(segmented: SegmentedDocument) -> None:
    out = NullProvider().translate(segmented.segments, "he", "en", Style.natural)
    assert set(out) == {s.id for s in segmented.segments}


def test_batches_cover_everything_once() -> None:
    segments = make_segments(23)
    chunks = list(batches(segments, 10))
    assert [len(c) for c in chunks] == [10, 10, 3]
    assert [s.id for chunk in chunks for s in chunk] == [s.id for s in segments]


def test_context_window_excludes_the_batch() -> None:
    segments = make_segments(10)
    before, after = context_window(segments, segments[4:6], span=2)
    assert before == "s2 s3"
    assert after == "s6 s7"
    assert "s4" not in before and "s4" not in after


def test_context_window_at_the_edges() -> None:
    segments = make_segments(4)
    assert context_window(segments, segments[:2]) == ("", "s2 s3")
    assert context_window(segments, segments[2:]) == ("s0 s1", "")


def test_styles_ask_for_different_things() -> None:
    natural = system_prompt("he", "en", Style.natural)
    direct = system_prompt("he", "en", Style.direct)
    assert "idiomatic" in natural and "Hebrew" in natural and "English" in natural
    assert "word order" in direct
    assert natural != direct


def test_unknown_provider_lists_the_real_ones() -> None:
    with pytest.raises(ProviderError) as caught:
        build("deepl")
    assert "deepl" in caught.value.message
    assert "anthropic" in (caught.value.hint or "")
    assert names() == ["anthropic", "null"]


# --- the Anthropic provider, against recorded answers ------------------------


def _ok(table: dict[str, str]) -> object:
    from targum.translate.anthropic_provider import _Batch, _Line

    return type(
        "R",
        (),
        {
            "stop_reason": "end_turn",
            "parsed_output": _Batch(segments=[_Line(id=k, text=v) for k, v in table.items()]),
        },
    )()


def install(provider: AnthropicProvider, cassette: object) -> None:
    class Client:
        messages = type("M", (), {"parse": staticmethod(cassette.messages_parse)})()

    provider._client = Client()


def test_keys_results_by_segment_id(cassette_factory: object) -> None:
    segments = make_segments(3)
    provider = AnthropicProvider(batch_size=3)
    cassette = cassette_factory([{s.id: f"translated {s.text}" for s in segments}])
    install(provider, cassette)

    out = provider.translate(segments, "he", "en", Style.natural)
    assert out == {s.id: f"translated {s.text}" for s in segments}
    assert len(cassette.calls) == 1


def test_ignores_ids_it_did_not_ask_for(cassette_factory: object) -> None:
    segments = make_segments(2)
    answer = {s.id: "ok" for s in segments} | {"0009.999-zzzzzz": "invented"}
    provider = AnthropicProvider(batch_size=2)
    install(provider, cassette_factory([answer]))

    out = provider.translate(segments, "he", "en", Style.natural)
    assert set(out) == {s.id for s in segments}


def test_retries_only_the_missing_segments(cassette_factory: object) -> None:
    segments = make_segments(4)
    partial = {s.id: "ok" for s in segments[:3]}
    cassette = cassette_factory([partial, {segments[3].id: "late"}])
    provider = AnthropicProvider(batch_size=4)
    install(provider, cassette)

    out = provider.translate(segments, "he", "en", Style.natural)
    assert out[segments[3].id] == "late"
    assert len(cassette.calls) == 2
    # The retry asked for one segment, not the whole batch.
    assert cassette.calls[1].count("0001.") == 1


def test_gives_up_loudly_rather_than_silently(cassette_factory: object) -> None:
    segments = make_segments(2)
    provider = AnthropicProvider(batch_size=2)
    install(provider, cassette_factory([{segments[0].id: "ok"}]))

    with pytest.raises(ProviderError, match="came back empty"):
        provider.translate(segments, "he", "en", Style.natural)


def test_progress_counts_segments(cassette_factory: object) -> None:
    segments = make_segments(4)
    provider = AnthropicProvider(batch_size=2)
    install(
        provider,
        cassette_factory([{s.id: "ok" for s in segments[:2]}, {s.id: "ok" for s in segments[2:]}]),
    )

    seen: list[int] = []
    provider.translate(segments, "he", "en", Style.natural, seen.append)
    assert sum(seen) == 4


def test_a_blocked_batch_is_split_rather_than_lost(monkeypatch: pytest.MonkeyPatch) -> None:
    """The safety filter reads a batch whole and sometimes objects to the combination.

    Halving the batch recovers the run instead of ending it.
    """
    import anthropic

    segments = make_segments(4)
    provider = AnthropicProvider(batch_size=4)
    calls: list[int] = []

    def parse(**kwargs: object) -> object:
        body = str(kwargs.get("messages"))
        asked = [s for s in segments if s.id in body]
        calls.append(len(asked))
        if len(asked) > 2:
            raise anthropic.APIStatusError(
                "Output blocked by content filtering policy",
                response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
                body=None,
            )
        return _ok({s.id: f"tr {s.text}" for s in asked})

    install(provider, type("C", (), {"messages_parse": staticmethod(parse), "calls": calls})())
    out = provider.translate(segments, "he", "en", Style.natural)

    assert set(out) == {s.id for s in segments}
    assert max(calls) == 4 and min(calls) == 2  # tried whole, then halves


def test_a_single_blocked_segment_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    import anthropic

    segments = make_segments(1)
    provider = AnthropicProvider(batch_size=1)

    def parse(**kwargs: object) -> object:
        raise anthropic.APIStatusError(
            "Output blocked by content filtering policy",
            response=httpx.Response(400, request=httpx.Request("POST", "http://x")),
            body=None,
        )

    install(provider, type("C", (), {"messages_parse": staticmethod(parse)})())
    with pytest.raises(ProviderError, match=segments[0].id):
        provider.translate(segments, "he", "en", Style.natural)


# --- what a run will cost, before it is spent --------------------------------


SENTENCE = "בראשית ברא אלהים את השמים ואת הארץ והארץ היתה תהו ובהו"


def sized_segments(count: int) -> list[Segment]:
    """Segments with a body the length of a real sentence, so cost scales with count."""
    segments = make_segments(count)
    return [segment.model_copy(update={"text": SENTENCE}) for segment in segments]


def counting_client(provider: AnthropicProvider, *, chars_per_token: float = 1.45) -> None:
    """A stand-in for the token-counting endpoint, proportional the way a real one is."""

    def count_tokens(**kwargs: object) -> object:
        messages: Any = kwargs["messages"]
        body = str(messages[0]["content"])
        return type("C", (), {"input_tokens": int(len(body) / chars_per_token)})()

    class Client:
        messages = type("M", (), {"count_tokens": staticmethod(count_tokens)})()

    provider._client = Client()


def offline_client(provider: AnthropicProvider) -> None:
    def count_tokens(**kwargs: object) -> object:
        raise RuntimeError("no network")

    class Client:
        messages = type("M", (), {"count_tokens": staticmethod(count_tokens)})()

    provider._client = Client()


def test_estimate_is_linear_in_the_length_of_the_text() -> None:
    """The overhead is a fixed cost per batch, not a share of the whole document.

    Charging it as a percentage made the estimate grow with the square of the length,
    far enough over the cap that no book could be built at all.
    """
    provider = AnthropicProvider(batch_size=20)
    counting_client(provider)

    short = provider.estimate(sized_segments(100), "he", "en", Style.natural)
    long = provider.estimate(sized_segments(1000), "he", "en", Style.natural)

    assert 9.9 < long / short < 10.1


def test_estimate_charges_the_batch_overhead_once_per_batch() -> None:
    segments = sized_segments(100)
    in_price, out_price = PRICES[DEFAULT_MODEL]

    twenty = AnthropicProvider(batch_size=20)
    counting_client(twenty)
    ten = AnthropicProvider(batch_size=10)
    counting_client(ten)

    # Halving the batch doubles the number of requests, so the fixed overhead is paid
    # twice as often and each batch re-sends its context against half as much body.
    extra = ten.estimate(segments, "he", "en", Style.natural) - twenty.estimate(
        segments, "he", "en", Style.natural
    )
    body_tokens = len("\n".join(s.text for s in segments)) / 1.45
    expected = (5 * TOKENS_PER_BATCH + body_tokens * 0.2) * in_price / 1_000_000
    assert expected * 0.99 < extra < expected * 1.01
    assert out_price > 0  # output does not move with batching; only input does


def test_estimate_falls_back_to_the_source_language_when_it_cannot_count() -> None:
    """Hebrew is 1.45 characters per token. A Latin-script guess undercounts it by 1.7x."""
    segments = sized_segments(50)
    provider = AnthropicProvider()
    offline_client(provider)

    hebrew = provider.estimate(segments, "he", "en", Style.natural)
    english = provider.estimate(segments, "en", "he", Style.natural)
    unknown = provider.estimate(segments, "sw", "en", Style.natural)

    assert hebrew > unknown > english
    assert 1.6 < hebrew / english < 2.0
    assert CHARS_PER_TOKEN["he"] == 1.45


def test_estimate_of_nothing_is_nothing() -> None:
    provider = AnthropicProvider()
    offline_client(provider)
    assert provider.estimate([], "he", "en", Style.natural) == 0.0
