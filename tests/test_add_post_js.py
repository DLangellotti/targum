"""Add's "Bring a post" form (targum-internal#158), run rather than read.

The form quotes; it never spends. The one spend a brought post can have — reading the
words in its pictures — is the card's own button, and it sends the post again by its job
rather than anything the page could name. Asserted on what was asked, because that is
where the money is.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "add_post.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(**payload: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


QUOTE = {
    "id": "j1",
    "title": "הופעות הקיץ",
    "language": "he",
    "stage": "ready",
    "pictures_offered": 2,
}
READ = dict(QUOTE, id="j2", pictures_offered=0, pages=2)


def test_the_form_takes_the_boxs_place_and_quotes_what_was_typed() -> None:
    said = run(
        fields={"handle": "@aviv.bahar", "name": "אביב בהר", "words": "שורה\nעוד שורה"},
        files=["one.jpg", "two.jpg"],
        answers={"/prepare": QUOTE},
    )
    assert said["open"] and said["expanded"] == "true", "one box on the page at a time"
    assert said["chips"] == 2
    assert said["uploaded"] == [["one.jpg", "two.jpg"]], "in the order chosen"
    prepares = [one for one in said["asked"] if one["path"] == "/prepare"]
    assert len(prepares) == 1
    body = prepares[0]["body"]
    assert body["brought"] == {
        "platform": "instagram",
        "handle": "aviv.bahar",
        "name": "אביב בהר",
        "text": "שורה\nעוד שורה",
        "link": "",
    }
    assert body["uploads"] == ["u0", "u1"]
    assert "pictures" not in body, "the pictures' words are never asked for by Continue"
    assert not [one for one in said["asked"] if one["path"] == "/build"], "a quote, not a build"
    assert "Confirm" in said["status"] and "Also read the 2 pictures" in said["status"]


def test_reading_the_pictures_is_the_cards_press_and_names_the_post_by_its_job() -> None:
    said = run(
        fields={"handle": "aviv.bahar", "words": "שורה"},
        files=["one.jpg", "two.jpg"],
        answers={"/prepare": [QUOTE, READ]},
        press=["Also read the 2 pictures"],
    )
    assert "missing" not in said, said
    prepares = [one["body"] for one in said["asked"] if one["path"] == "/prepare"]
    assert len(prepares) == 2
    again = prepares[1]
    assert again["again"] == "j1" and again["pictures"] is True
    assert again["brought"] == {}, "nothing typed goes again: the job holds the post"
    assert "uploads" not in again, "nothing is uploaded twice"
    assert len(said["uploaded"]) == 1


@pytest.mark.parametrize(
    ("are", "button"),
    [("pictures", "Read the 2 pictures"), ("pages", "Read the 2 pages")],
)
def test_pictures_that_are_all_there_is_are_not_also_read(are: str, button: str) -> None:
    """Copy audit, 2026-09-28 (Q28). "Also read the 2 pictures" under a post whose
    words are all in its pictures, and under a scanned PDF, whose pictures are its
    pages: there was nothing for "also" to be in addition to. "Also" stays where a
    caption was read."""
    refused = dict(
        QUOTE,
        stage="failed",
        error="That post's words are all in its pictures.",
        pictures_are=are,
    )
    said = run(fields={"handle": "h"}, files=["one.jpg", "two.jpg"], answers={"/prepare": refused})
    assert button in said["status"]
    assert not [line for line in said["status"] if line.startswith("Also read")]


def test_a_link_moves_the_switch_to_where_it_was_posted() -> None:
    said = run(
        fields={
            "handle": "h",
            "words": "שורה",
            "link": "https://twitter.com/h/status/1834567890123456789",
        },
        answers={"/prepare": dict(QUOTE, pictures_offered=0)},
    )
    assert said["platform"] == ["x"]
    body = next(one["body"] for one in said["asked"] if one["path"] == "/prepare")
    assert body["brought"]["platform"] == "x"


@pytest.mark.parametrize(
    ("fields", "files", "said"),
    [
        ({"words": "שורה"}, [], "Add the handle it was posted under."),
        ({"handle": "h"}, [], "Paste what the post says, or add its pictures or its video."),
        ({"handle": "h"}, ["a.jpg", "b.mp4"], "Add either its pictures or a single video."),
        ({"handle": "h"}, ["a.mp4", "b.mov"], "Add either its pictures or a single video."),
    ],
)
def test_the_form_says_what_is_missing_before_anything_goes_up(
    fields: dict[str, str], files: list[str], said: str
) -> None:
    got = run(fields=fields, files=files, answers={"/prepare": QUOTE})
    assert said in got["status"]
    assert got["uploaded"] == []
    assert not [one for one in got["asked"] if one["path"] in ("/prepare", "/build")]


def test_one_video_goes_up_as_a_film() -> None:
    got = run(
        fields={"handle": "h", "words": "כיתוב"},
        files=["clip.mp4"],
        answers={"/prepare": dict(QUOTE, pictures_offered=0, audio=True, seconds=40)},
    )
    body = next(one["body"] for one in got["asked"] if one["path"] == "/prepare")
    assert body["upload"] == "v0" and "uploads" not in body


def test_a_refused_post_link_offers_the_form_with_the_link_in_it() -> None:
    """X shut, or a post the box could not reach: the refusal carries the way that
    works, and the form opens with the link already typed."""
    link = "https://x.com/aviv/status/1834567890123456789"
    got = run(
        refusal=link,
        answers={
            "/prepare": {"id": "j0", "stage": "failed", "error": "We don't bring posts in from X."}
        },
    )
    assert got["offered"], got
    assert got["open"] and got["link"] == link and got["platform"] == ["x"]


def test_a_refused_article_offers_no_form() -> None:
    got = run(
        refusal="https://example.com/article",
        answers={
            "/prepare": {"id": "j0", "stage": "failed", "error": "We couldn't open that page."}
        },
    )
    assert not got["offered"]


def said_whole(got: dict[str, Any]) -> str:
    return " ".join(got["status"] + got.get("after", []))


@pytest.mark.parametrize(
    "quote",
    [
        {"id": "j1", "title": "הופעות הקיץ", "stage": "ready"},
        {"id": "j1", "stage": "ready", "pictures_offered": 2},
        {"id": "j1", "title": "A clip", "stage": "ready", "audio": True},
        {"id": "j1", "title": "A clip", "stage": "ready", "audio": True, "parts": 2},
        {"id": "j1", "stage": "blocked", "blocked": ""},
    ],
)
def test_a_quote_missing_a_fact_leaves_it_out_rather_than_saying_undefined(
    quote: dict[str, Any],
) -> None:
    """The card read `job.segments` and `job.seconds` as though every quote had them,
    and printed "undefined sentences" when one did not (targum-internal#158). Whatever
    the quote leaves out, the card says nothing about it."""
    got = run(
        fields={"handle": "h", "words": "שורה"},
        files=["a.jpg"],
        answers={"/prepare": quote},
    )
    text = said_whole(got)
    assert "undefined" not in text and "NaN" not in text and "null" not in text, text
