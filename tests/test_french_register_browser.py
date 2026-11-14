"""French register on the card (`annotate/french_register.py`), French's seventh hard spot:
the Informal line with its formal clause, the drop alone where the clause is withheld,
*on* for "we" and the open line, in an English interface and a Russian one."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are imported
# by name to register them here.
from test_reader_browser import browser, open_reader  # noqa: E402, F401

from targum.annotate.french_register import words_of  # noqa: E402
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

TEXT = "Je sais pas. Nous, on est contents. On dit ça. Vous dérangez pas."

#: The card's facts once the word is tapped, as [label, value, the value's French], after
#: a turn of the event loop for the card to be drawn.
FACTS = """
async (at) => {
  document.querySelectorAll('.w')[at].click();
  await new Promise((done) => setTimeout(done));
  const names = [...document.querySelectorAll('.gloss-card .card-facts dt')];
  return names.map((dt) => {
    const dd = dt.nextElementSibling;
    const french = dd.querySelector('bdi[lang="fr"]');
    return [dt.textContent, dd.textContent, french ? french.textContent : null];
  });
}
"""


def _reader(out: Path, into: str) -> Path:
    """The four lines in one segment, read into `into`, which is the page's interface."""
    segment = Segment(id="0000.000-aaaaaa", block_id="b0000", block_index=0, index=0, text=TEXT)
    tokens = [
        Token(
            start=word.start,
            end=word.end,
            surface=word.surface,
            lemma=word.surface.lower(),
            band=1,
            pos="ADV" if word.surface == "pas" else None,
        )
        for word in words_of(TEXT)
    ]
    document = Document(
        source="memory",
        title="On parle",
        language="fr",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=TEXT)],
        content_hash="r",
    )
    segmented = SegmentedDocument(
        document_hash="r", language="fr", segmenter="test/1", segments=[segment]
    )
    name, saying = {
        "en": ("English", "I don't know. We're happy. People say so. Don't trouble yourself."),
        "ru": ("Русский", "Не знаю. Мы довольны. Так говорят. Не беспокойтесь."),
    }[into]
    translation = Translation(
        name=name,
        document_hash="r",
        source_language="fr",
        target_language=into,
        provider="null",
        segments={segment.id: saying},
    )
    annotation = Annotation(
        document_hash="r",
        language="fr",
        annotator="test/1",
        method="frequency",
        method_note="a test",
        tokens={segment.id: tokens},
    )
    return render(document, segmented, [translation], out, annotation=annotation)[0]


def _at(surface: str, nth: int = 0) -> int:
    found = [i for i, word in enumerate(words_of(TEXT)) if word.surface == surface]
    return found[nth]


def test_the_card_says_the_register_in_english_and_in_russian(
    browser,  # noqa: F811
    tmp_path: Path,
) -> None:
    context, page = open_reader(browser, _reader(tmp_path / "en", "en"))
    facts = page.evaluate(FACTS, _at("pas"))
    assert ["Informal", "ne dropped. Formal: Je ne sais pas", "Je ne sais pas"] in facts
    page.keyboard.press("Escape")
    facts = page.evaluate(FACTS, _at("on"))
    assert ["Informal", "on here means “we”, for nous", None] in facts
    page.keyboard.press("Escape")
    facts = page.evaluate(FACTS, _at("On"))
    assert ["Who", "people in general, or “we” in speech", None] in facts
    page.keyboard.press("Escape")
    # *Vous dérangez pas* may be either, so the drop is said and no formal clause is.
    facts = page.evaluate(FACTS, _at("pas", 1))
    assert ["Informal", "ne dropped", None] in facts
    context.close()

    context, page = open_reader(browser, _reader(tmp_path / "ru", "ru"))
    facts = page.evaluate(FACTS, _at("pas"))
    assert ["Разговорное", "ne опущено. Нормативно: Je ne sais pas", "Je ne sais pas"] in (facts)
    page.keyboard.press("Escape")
    facts = page.evaluate(FACTS, _at("on"))
    assert ["Разговорное", "on здесь значит «мы», вместо nous", None] in facts
    page.keyboard.press("Escape")
    facts = page.evaluate(FACTS, _at("On"))
    assert ["Кто", "люди вообще или, в разговорной речи, «мы»", None] in facts
    context.close()
