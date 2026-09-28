"""English–French false friends, from a list targum owns (targum-internal#267)."""

from __future__ import annotations

import json

from targum.annotate import false_friends


def test_every_entry_says_all_three_things_once() -> None:
    raw = json.loads(false_friends._TABLE.read_text(encoding="utf-8"))
    entries = raw["entries"]
    assert len(entries) >= 250, "about three hundred"
    for entry in entries:
        for field in ("french", "looks_like", "means"):
            assert isinstance(entry.get(field), str) and entry[field].strip(), (entry, field)
    french = [entry["french"] for entry in entries]
    assert len(french) == len(set(french)), "a lemma is on the list twice"


def test_every_entry_is_a_form_the_lemmatizer_gives() -> None:
    """Lowercase, one word, no *se*: what `model_lemma` writes for a French word, so the
    card finds it. And the table says how it was made and that nobody has read it yet."""
    raw = json.loads(false_friends._TABLE.read_text(encoding="utf-8"))
    assert raw["reviewed"] is False and "model" in raw["made"]
    for entry in raw["entries"]:
        lemma = entry["french"]
        assert lemma == lemma.lower() and " " not in lemma and "'" not in lemma, lemma
        assert entry["means"].lower() != entry["looks_like"].lower(), entry
    looks, means = false_friends.friend_of("actuellement")
    assert looks == "actually" and "currently" in means
    assert false_friends.friend_of("pomme") == []
