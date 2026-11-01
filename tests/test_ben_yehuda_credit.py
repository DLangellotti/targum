"""Project Ben-Yehuda's closing credit line is boilerplate, not the text (2026-11-01).

Every download ends with one unpointed line naming the volunteers and the work's
address. A reader was shown it as the text's last line, and it moved a short poem's
difficulty. The credit stays in the row's `credit` and `licence_url`.
"""

from __future__ import annotations

from typing import Any

from targum.ingest import url as door

#: A synthetic download in the shape Ben-Yehuda serves: the attribution line, a
#: pointed body, and the credit line after a run of blank lines.
SAMPLE = (
    "שָׁלוֹם! מאת סוֹפֵר בָּדוּי\n\n\n\n\n"
    "אֲנִי אוֹמֵר: שָׁלוֹם.\n\n"
    "אֲנִי רוֹצֶה לִשְׁמֹעַ תְּשׁוּבָה.\n\n\n\n\n"
    "את הטקסט[ים] לעיל הפיקו מתנדבי פרויקט בן־יהודה באינטרנט.  "
    "הכל זמין תמיד בכתובת הבאה:https://benyehuda.org/read/1\n"
)


def _served(monkeypatch: Any, body: str) -> None:
    monkeypatch.setattr(
        door, "page", lambda url: door.Fetched(text=body, content_type="text/plain")
    )


def _text(document: Any) -> str:
    return "\n".join(block.text for block in document.blocks)


def test_a_ben_yehuda_download_loses_its_credit_line(monkeypatch: Any) -> None:
    _served(monkeypatch, SAMPLE)
    document = door.UrlIngester().load("https://benyehuda.org/download/1.txt")
    text = _text(document)
    assert "מתנדבי" not in text and "benyehuda.org" not in text
    assert text.rstrip().endswith("תְּשׁוּבָה.")
    assert "אֲנִי אוֹמֵר: שָׁלוֹם." in text
    assert document.ingester == "url-text/2"


def test_an_older_wording_and_a_plain_hyphen_go_too() -> None:
    older = "גּוּף.\n\nאת הטקסט לעיל הפיקו מתנדבי פרויקט בן-יהודה באינטרנט. הוא זמין תמיד"
    assert door.drop_ben_yehuda_credit(older) == "גּוּף."


def test_the_sentence_quoted_mid_text_is_kept() -> None:
    quoted = "הפיקו מתנדבי פרויקט בן־יהודה.\n\nוְעוֹד שׁוּרָה."
    assert door.drop_ben_yehuda_credit(quoted) == quoted


def test_another_host_s_text_file_is_left_whole(monkeypatch: Any) -> None:
    _served(monkeypatch, SAMPLE)
    document = door.UrlIngester().load("https://example.org/download/1.txt")
    assert "מתנדבי" in _text(document)
