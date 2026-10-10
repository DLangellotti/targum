"""Where a word on Your Words was met (design.md §12, "Your Words is one table and a
practice card", 2026-10-09): a line it came round in, the case it came in, and the whole
of `/account/words` end to end.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import test_serve
from test_reading_line import ms
from test_serve import Postbox, call, sign_in

from targum import meetings
from targum.coverage import KNOWN
from targum.models import BlockKind, Segment, SegmentedDocument, Translation

served = test_serve.served
postbox = test_serve.postbox


def text(
    folder: Path,
    sections: dict[int, list[tuple[str, list[dict[str, Any]]]]],
    *,
    language: str = "he",
    content_hash: str = "book",
    translation: dict[str, str] | None = None,
    pointed: dict[str, str] | None = None,
) -> Path:
    """A built text: each section a heading and its lines, each line its words with
    their offsets, found in the line by their surface."""
    segments: list[Segment] = []
    tokens: dict[str, list[dict[str, Any]]] = {}
    for number, lines in sections.items():
        segments.append(
            Segment(
                id=f"h{number}",
                block_id=f"b{number}",
                block_index=number,
                index=len(segments),
                text=f"Chapter {number}",
                kind=BlockKind.heading,
                level=1,
            )
        )
        for n, (said, words) in enumerate(lines):
            sid = f"s{number}-{n}"
            segments.append(
                Segment(
                    id=sid,
                    block_id=f"b{number}",
                    block_index=number,
                    index=len(segments),
                    text=said,
                )
            )
            placed = []
            for token in words:
                start = said.index(token["surface"])
                placed.append({"start": start, "end": start + len(token["surface"]), **token})
            tokens[sid] = placed
    folder.mkdir(parents=True, exist_ok=True)
    SegmentedDocument(
        document_hash=content_hash, language=language, segmenter="t/1", segments=segments
    ).write(folder / "segments.json")
    (folder / "annotation.json").write_text(json.dumps({"tokens": tokens}), encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"title": "A Book", "language": language, "content_hash": content_hash}),
        encoding="utf-8",
    )
    if translation is not None:
        (folder / "translations").mkdir(exist_ok=True)
        Translation(
            name="t",
            document_hash=content_hash,
            source_language=language,
            target_language="en",
            provider="test",
            segments=translation,
        ).write(folder / "translations" / "t.en.json")
    if pointed is not None:
        (folder / "vocalization.json").write_text(
            json.dumps({"segments": pointed}, ensure_ascii=False), encoding="utf-8"
        )
    reader = folder / "reader"
    reader.mkdir(exist_ok=True)
    for number in range(1, len(sections) + 1):
        (reader / f"sec-{number:04d}.html").write_text("<p>x</p>", encoding="utf-8")
    return folder


def w(surface: str, lemma: str, feats: str = "") -> dict[str, Any]:
    return {"surface": surface, "lemma": lemma, "pos": "NOUN", "feats": feats or None}


def test_a_line_is_from_a_finished_section_and_the_latest_text_first(tmp_path: Path) -> None:
    old = text(tmp_path / "old", {1: [("ספר ישן", [w("ספר", "ספר")])]}, content_hash="old")
    new = text(
        tmp_path / "new",
        {
            1: [("בית גדול", [w("בית", "בית")])],
            2: [("ספר חדש", [w("ספר", "ספר")])],
        },
        content_hash="new",
    )
    folders = {"old": (old, "he"), "new": (new, "he")}
    finished = [("old", "1", ms(2026, 8)), ("new", "2", ms(2026, 9))]
    lines = meetings.lines_met(["ספר", "בית"], finished, folders.get, "he")
    assert lines["ספר"].document == "new" and lines["ספר"].section == 2
    assert "בית" not in lines, "section 1 of the new text was never finished"


def test_the_card_line_marks_the_word_in_the_pointed_text(tmp_path: Path) -> None:
    """Offsets counted in bare letters, carried onto the pointed line the reader shows."""
    folder = text(
        tmp_path / "t",
        {1: [("ולנעמי מודע לאישה", [w("מודע", "מודע")])], 2: [("סוף", [])]},
        translation={"s1-0": "Naomi had a kinsman"},
        pointed={"s1-0": "וּלְנָעֳמִי מוֹדַע לְאִישָׁהּ"},
    )
    line = meetings.lines_met(["מודע"], [("book", "1", 1)], {"book": (folder, "he")}.get, "he")
    said = meetings.card_line(line["מודע"], "en")
    assert said is not None
    assert said["word"] == "מוֹדַע"
    assert said["line"] == "וּלְנָעֳמִי מוֹדַע לְאִישָׁהּ"
    assert said["translation"] == "Naomi had a kinsman"
    assert said["title"] == "A Book" and said["chapter"] == 1


def test_scripture_offsets_into_the_text_as_written_lose_only_the_chanting_marks() -> None:
    written = "וַאֲדֹ֣נִיָּ֔הוּ יָרֵ֖א מִפְּנֵ֣י"
    start = written.index("יָרֵ֖א")
    line = meetings.Line("ירא", "d", Path("."), 1, "s", start, start + len("יָרֵ֖א"))
    shown, at, end = meetings.drawn(line, written)
    assert shown[at:end] == "יָרֵא"


def test_a_russian_word_is_said_in_the_case_it_mostly_comes_in(tmp_path: Path) -> None:
    folder = text(
        tmp_path / "r",
        {
            1: [
                ("рукой", [w("рукой", "рука", "Case=Ins|Number=Sing")]),
                ("рукой махнул", [w("рукой", "рука", "Case=Ins|Number=Sing")]),
                ("руки", [w("руки", "рука", "Case=Gen|Number=Sing")]),
                ("рука", [w("рука", "рука", "Case=Nom|Number=Sing")]),
                ("год", [w("год", "год", "Case=Nom")] * 1),
            ]
        },
        language="ru",
    )
    folders = {"book": (folder, "ru")}
    finished = [("book", "1", 1)]
    said = meetings.cases_met(["рука", "год"], finished, folders.get, "ru")
    assert said == {"рука": ("Ins", "рукой")}, "two in four is half; the nominative says nothing"
    line = meetings.lines_met(["рука"], finished, folders.get, "ru")["рука"]
    assert line.case == "Ins"


def test_the_cache_is_read_back_the_same(tmp_path: Path) -> None:
    folder = text(tmp_path / "t", {1: [("ספר", [w("ספר", "ספר", "Case=Acc")])]})
    first = meetings.text_meetings(folder)
    assert (folder / meetings.MEETINGS).is_file()
    meetings._cached.cache_clear()
    assert meetings.text_meetings(folder) == first


# -- /account/words, end to end ---------------------------------------------------------


def test_the_words_page_is_nobodys_business_signed_out(served: tuple[int, str, Path]) -> None:
    port, token, _ = served
    status, said, _ = call(port, "GET", f"/account/words?language=he&k={token}")
    assert status == 401 and said == {"signedIn": False}


def test_the_words_page_says_where_each_word_was_met_and_offers_lines(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, token, out = served
    for name in ("one", "two"):
        text(
            out / "shared" / name,
            {1: [("ספר וים", [w("ספר", "ספר"), w("ים", "ים")])]},
            content_hash=name,
            translation={"s1-0": "a book and a sea"},
        )
    cookie = sign_in(port, postbox)
    words = [
        {"language": "he", "lemma": "ים", "status": KNOWN, "at": 1, "seen": 1},
        {"language": "he", "lemma": "ספר", "status": 2, "at": 1, "seen": 1},
        {"language": "he", "lemma": "עיר", "status": 1, "at": 1, "seen": 1},
    ]
    sections = [
        {"hash": name, "section": "1", "at": ms(2026, 9), "seen": ms(2026, 9)}
        for name in ("one", "two")
    ]
    status, answer, _ = call(
        port, "POST", f"/sync?k={token}", {"words": words, "sections": sections}, cookie=cookie
    )
    assert status == 200, answer

    status, said, _ = call(port, "GET", f"/account/words?language=he&k={token}", cookie=cookie)
    assert status == 200, said
    assert said["met"] == {"ים": 2, "ספר": 2}, "a word met nowhere is left out"
    assert said["often"] == 2
    (line,) = said["practise"]
    assert line["lemma"] == "ספר" and line["word"] == "ספר"
    assert line["translation"] == "a book and a sea"
    assert said["notes"] == {}, "Hebrew has nothing to say beside a meaning"


def test_french_notes_wait_for_their_switches(
    served: tuple[int, str, Path], postbox: Postbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, token, _ = served
    cookie = sign_in(port, postbox)
    words = [{"language": "fr", "lemma": "actuellement", "status": 1, "at": 1, "seen": 1}]
    call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)

    monkeypatch.delenv("TARGUM_FALSE_FRIENDS", raising=False)
    monkeypatch.delenv("TARGUM_FRENCH_IPA", raising=False)
    _, said, _ = call(port, "GET", f"/account/words?language=fr&k={token}", cookie=cookie)
    assert said["notes"] == {}, "off, the row is what it was"

    monkeypatch.setenv("TARGUM_FALSE_FRIENDS", "1")
    _, said, _ = call(port, "GET", f"/account/words?language=fr&k={token}", cookie=cookie)
    assert said["notes"]["actuellement"]["friend"]["looks"] == "actually"
    _, said, _ = call(port, "GET", f"/account/words?language=fr&into=ru&k={token}", cookie=cookie)
    assert said["notes"] == {}, "a false friend of English is said only into English"


def test_home_says_nothing_is_due_while_there_is_nothing_to_practise(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Home's Practise line opens the practice card, so it is left out while the card is
    empty (design.md §12, 2026-10-10): words still being learned, but none met in a
    section the reader finished, are nothing to practise yet."""
    port, token, out = served
    text(
        out / "shared" / "one",
        {1: [("ספר וים", [w("ספר", "ספר"), w("ים", "ים")])]},
        content_hash="one",
        translation={"s1-0": "a book and a sea"},
    )
    cookie = sign_in(port, postbox)
    words = [
        {"language": "he", "lemma": "ספר", "status": 2, "at": 1, "seen": 1},
        {"language": "he", "lemma": "עיר", "status": 1, "at": 1, "seen": 1},
    ]
    call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)
    status, said, _ = call(port, "GET", f"/account/due?language=he&k={token}", cookie=cookie)
    assert status == 200 and said == {"signedIn": True, "due": 0}, "nothing met, nothing due"

    sections = [{"hash": "one", "section": "1", "at": ms(2026, 9), "seen": ms(2026, 9)}]
    call(port, "POST", f"/sync?k={token}", {"sections": sections}, cookie=cookie)
    _, said, _ = call(port, "GET", f"/account/due?language=he&k={token}", cookie=cookie)
    assert said["due"] == 2, "once one is on the card, the count is every word still learned"
