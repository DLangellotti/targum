"""A photographed page's number and a reading's false start stay out of the text.

From a reader's book (2026-11-23): its page numbers came back as paragraphs of their
own, so the book was called "3" and "4", "40" and "47" stood in it as headings; and one
paragraph was begun, broken off and read again, so its opening words came twice.
"""

from __future__ import annotations

from targum.ingest import pages as pages_module
from targum.models import BlockKind

OPENING = "כמה בולי עץ, וקקשי רב הן מושכות ומניחות על הבולים את המשטח"
WHOLE = (
    "כמה בולי עץ, וביקשי רב הן מושכות ומניחות על הבולים את המשטח הסלע, והמתחילות לגלגל בול עץ נוסף."
)


def document(*pages: list[str], conversation: bool = False):
    return pages_module.document_from_pages(
        "/uploads/abc",
        list(pages),
        ingester="picture/2",
        source_hash="abc",
        conversation=conversation,
    )


def test_a_page_number_is_neither_the_title_nor_a_heading() -> None:
    book = document(
        ["3", "", "לִפְנֵי כ-10,000 שָׁנָה", "", "לֹג יוֹשֶׁבֶת בַּחוּץ."],
        ["מֶלֶג אוֹמֶרֶת שָׁלוֹם.", "", "- 4 -"],
        ["40", "", "עוֹד שׁוּרָה.", "", "47"],
    )
    assert book.title == "לִפְנֵי כ-10,000 שָׁנָה"
    texts = [block.text for block in book.blocks]
    assert texts == [
        "לִפְנֵי כ-10,000 שָׁנָה",
        "לֹג יוֹשֶׁבֶת בַּחוּץ.",
        "מֶלֶג אוֹמֶרֶת שָׁלוֹם.",
        "עוֹד שׁוּרָה.",
    ]
    assert not any(block.kind is BlockKind.heading for block in book.blocks)


def test_a_number_inside_a_sentence_stays() -> None:
    assert pages_module.paragraphs_of(["לפני 10,000 שנה", "", "שנת 1948"]) == [
        "לפני 10,000 שנה",
        "שנת 1948",
    ]


def test_a_paragraph_begun_again_is_read_once() -> None:
    book = document([OPENING, "", WHOLE, "", "מה קרה?"])
    assert [block.text for block in book.blocks] == [WHOLE, "מה קרה?"]


def test_a_refrain_said_twice_stays_twice() -> None:
    assert pages_module.paragraphs_of(["לא, לא!", "", "לא, לא! אמרה הילדה."]) == [
        "לא, לא!",
        "לא, לא! אמרה הילדה.",
    ]


def test_a_chat_keeps_a_message_that_is_only_a_number() -> None:
    chat = document(["דנה: כמה אתם?", "", "me: 5"], conversation=True)
    assert [block.text for block in chat.blocks] == ["כמה אתם?", "5"]
