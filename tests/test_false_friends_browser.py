"""A false friend on the card, and only for a French text read into English
(targum-internal#267)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import SWITCH, browser, open_reader  # noqa: E402, F401

from targum.annotate.false_friends import friend_of  # noqa: E402
from targum.models import (  # noqa: E402
    Annotation,
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
)
from targum.render import render  # noqa: E402

FRIEND = """
(text) => {
  [...document.querySelectorAll('.w')].find((w) => w.textContent === text).click();
  const line = document.querySelector('.gloss-card .false-friend');
  return line ? line.textContent : null;
}
"""


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


def test_the_card_names_a_false_friend_only_for_french_read_into_english(
    browser,  # noqa: F811
    tmp_path: Path,
) -> None:
    context, page = open_reader(browser, reader(tmp_path / "fr", "fr"))
    means = friend_of("actuellement")[1]
    assert page.evaluate(FRIEND, "actuellement") == f"false friend: not actually — {means}"
    looks = "() => document.querySelector('.gloss-card .false-friend i').textContent"
    assert page.evaluate(looks) == "actually", "the look-alike is set apart"
    page.keyboard.press("Escape")
    page.evaluate(SWITCH, "t1")
    assert page.evaluate(FRIEND, "actuellement") is None, "read into Russian"
    context.close()
    # The same word on a page that is not French says nothing: the list is English–French.
    context, page = open_reader(browser, reader(tmp_path / "it", "it"))
    assert page.evaluate(FRIEND, "actuellement") is None
    context.close()
