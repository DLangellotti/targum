"""English–French false friends, from a list targum owns (targum-internal#267)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.annotate import false_friends
from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
)
from targum.render import render


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


# --- behind the switch -------------------------------------------------------------------


def reader(out: Path, language: str) -> Path:
    """One sentence with a false friend in it, read into English and into Russian."""
    text = "Il pleut actuellement."
    segment = Segment(id="0000.000-aaaaaa", block_id="b0000", block_index=0, index=0, text=text)
    start = text.index("actuellement")
    token = Token(
        start=start,
        end=start + len("actuellement"),
        surface="actuellement",
        lemma="actuellement",
        band=1,
        pos="ADV",
        feats="UPOS=ADV",
    )
    document = Document(
        source="memory",
        title="La pluie",
        language=language,
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=text)],
        content_hash="f",
    )
    segmented = SegmentedDocument(
        document_hash="f", language=language, segmenter="test/1", segments=[segment]
    )
    translations = [
        Translation(
            name=name,
            document_hash="f",
            source_language=language,
            target_language=code,
            provider="null",
            segments={segment.id: saying},
        )
        for name, code, saying in (
            ("English", "en", "It is raining at the moment."),
            ("Русский", "ru", "Сейчас идёт дождь."),
        )
    ]
    annotation = Annotation(
        document_hash="f",
        language=language,
        annotator="test/1",
        method="frequency",
        method_note="a test",
        tokens={segment.id: [token]},
    )
    return render(document, segmented, translations, out, annotation=annotation)[0]


def test_the_switch_off_leaves_the_reader_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off, a French reader carries neither the table nor the script; on, those two are
    the whole difference (David, 2026-09-28: off until he has read the list)."""
    monkeypatch.delenv(false_friends.ENV, raising=False)
    off = reader(tmp_path / "off", "fr").read_text(encoding="utf-8")
    monkeypatch.setenv(false_friends.ENV, "1")
    on = reader(tmp_path / "on", "fr").read_text(encoding="utf-8")
    assert "false-friend" not in off and '"friends"' not in off
    assert "false-friend" in on and '"friends"' in on
    # The script, and the table: the page had no extensions for it to join.
    at = on.index("register false-friend")
    script = on[on.rindex("<script>", 0, at) : on.index("</script>", at) + len("</script>")]
    friends = [false_friends.friend_of("actuellement")]
    table = '"extensions": ' + json.dumps({"friends": friends}, ensure_ascii=False) + ", "
    assert table in on, "the table rides in the extensions"
    assert on.replace(script + "\n", "").replace(table, "") == off
