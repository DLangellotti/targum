"""A meaning answered as broken JSON costs that word, never the rebuild (2026-09-28)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from targum.annotate import gloss


class _Messages:
    """Answers every batch, except that any batch holding `poison` comes back as JSON
    cut off mid-string — which `messages.parse` raises as a pydantic ValidationError."""

    def __init__(self, poison: str) -> None:
        self.poison = poison
        self.asked: list[list[str]] = []

    def parse(self, **request: Any) -> Any:
        content = request["messages"][0]["content"]
        forms = [
            line.removeprefix("form: ")
            for line in content.splitlines()
            if line.startswith("form: ")
        ]
        self.asked.append(forms)
        if self.poison in forms:
            gloss._Batch.model_validate_json(
                '{"entries":[{"lemma":"ה","part_of_speech":"other"},{"'
            )
        entries = [gloss._Entry(lemma=form, gloss=f"meaning of {form}") for form in forms]
        return SimpleNamespace(
            parsed_output=gloss._Batch(entries=entries),
            usage=SimpleNamespace(input_tokens=10, output_tokens=10),
        )


def test_a_broken_answer_costs_one_word_and_the_rest_are_bought(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = _Messages(poison="רע")
    glosses = gloss.AnthropicGlosses(batch_size=4)
    monkeypatch.setattr(glosses._provider, "client", lambda: SimpleNamespace(messages=messages))
    got = glosses.gloss(["טוב", "רע", "בית", "ספר", "מים"], "he", "en")
    assert set(got) == {"טוב", "בית", "ספר", "מים"}, "only the broken word is left unbought"
    assert ["רע"] in messages.asked, "the batch was halved down to the word itself"


def test_the_fake_really_raises_what_the_sdk_raises() -> None:
    with pytest.raises(ValidationError):
        gloss._Batch.model_validate_json('{"entries":[{"lemma":"ה"},{"')
