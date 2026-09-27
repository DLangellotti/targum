"""The X door (targum-internal#158): a post, or the thread its author wrote up to it, read
off X's syndication endpoint — and shut unless the deployment arms it.

Every answer here is in the shape `cdn.syndication.twimg.com/tweet-result` gave on
2026-09-27, recorded live from a public post and trimmed to the keys the door reads; the
values are this file's own, not anybody's post. Nothing here connects.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum.errors import TargumError
from targum.ingest import post, x

Image = pytest.importorskip("PIL.Image", reason="Pillow is in the covers extra")

FIRST, SECOND, THIRD = "1837201000000000001", "1837201000000000002", "1837201000000000003"
ELSEWHERE = "1837200000000000000"


def answer(ident: str, text: str, **over: Any) -> dict[str, Any]:
    said: dict[str, Any] = {
        "__typename": "Tweet",
        "lang": "iw",
        "created_at": "2026-09-21T13:33:20.000Z",
        "display_text_range": [0, len(text)],
        "entities": {},
        "id_str": ident,
        "text": text,
        "user": {
            "id_str": "12",
            "name": "אביב בהר",
            "screen_name": "aviv_bahar",
            "profile_image_url_https": "https://pbs.twimg.com/profile_images/1/face_normal.jpg",
        },
        "edit_control": {"edit_tweet_ids": [ident]},
        "conversation_count": 3,
        "news_action_type": "conversation",
        "isEdited": False,
        "isStaleEdit": False,
    }
    said.update(over)
    return said


def a_reply(ident: str, text: str, parent: str, handle: str = "aviv_bahar", **over: Any) -> dict:
    return answer(
        ident,
        text,
        in_reply_to_screen_name=handle,
        in_reply_to_status_id_str=parent,
        parent={"id_str": parent, "user": {"screen_name": handle}},
        **over,
    )


# -- the address and the token ---------------------------------------------------------


def test_every_spelling_of_a_post_is_one_post_with_one_home() -> None:
    for url in (
        f"https://x.com/aviv_bahar/status/{FIRST}",
        f"https://twitter.com/aviv_bahar/status/{FIRST}?s=20",
        f"https://mobile.twitter.com/aviv_bahar/status/{FIRST}/photo/1",
        f"https://x.com/i/web/status/{FIRST}",
        f"https://x.com/i/status/{FIRST}",
    ):
        assert x.is_x(url) and x.status_id(url) == FIRST, url
        assert x.home_url(url) == f"https://x.com/i/status/{FIRST}", url
    for url in (
        "https://x.com/aviv_bahar",
        "https://x.com/search?q=שבת",
        "https://x.com.evil.example/a/status/1",
        "https://t.co/abc",
        f"javascript://x.com/a/status/{FIRST}",
    ):
        assert x.status_id(url) == "" and x.home_url(url) == "", url


@pytest.mark.parametrize(
    ("ident", "expected"),
    [
        # Worked by node from the widget's own expression on 2026-09-27.
        ("20", "6dq1a2xwd93"),
        ("1", "bhi2ay3f28n"),
        ("440322224407314432", "12fb9qdo78ad"),
        ("1628832338187636740", "3y54libozsy"),
        ("1790000000000000000", "4c7g8auqyik"),
        ("1837201999999999999", "4gbqnfqeopl"),
    ],
)
def test_the_token_is_the_widgets_own(ident: str, expected: str) -> None:
    assert x.token(ident) == expected


def test_the_door_is_shut_unless_armed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(x.ENV, raising=False)
    assert not x.is_open()
    for said in ("0", "no", "", "off"):
        monkeypatch.setenv(x.ENV, said)
        assert not x.is_open(), said
    monkeypatch.setenv(x.ENV, "1")
    assert x.is_open()


# -- a post, read ----------------------------------------------------------------------


def test_a_post_is_read_as_displayed_with_its_links_written_out() -> None:
    """A reply's leading mention is outside the displayed range; a shortened link is
    written out as where it goes; the link to the post's own photo is taken off; the
    entities X escapes are unescaped; a face is taken at 200, and only from X's store."""
    text = "@kan_news שבת שלום &amp; ברכה\nראו https://t.co/abc #שבת https://t.co/pic"
    found = x.read(
        answer(
            FIRST,
            text,
            display_text_range=[10, len(text) - len(" https://t.co/pic")],
            entities={
                "urls": [{"url": "https://t.co/abc", "expanded_url": "https://kan.org.il/x"}],
                "media": [{"url": "https://t.co/pic"}],
            },
            photos=[
                {"url": "https://pbs.twimg.com/media/one.jpg", "width": 1080, "height": 1350},
                {"url": "https://evil.example/two.jpg", "width": 10, "height": 10},
            ],
        )
    )
    assert found is not None
    assert found.text == "שבת שלום & ברכה\nראו https://kan.org.il/x #שבת"
    assert (found.handle, found.name) == ("aviv_bahar", "אביב בהר")
    assert found.avatar == "https://pbs.twimg.com/profile_images/1/face_200x200.jpg"
    assert found.posted == "2026-09-21T13:33:20Z"
    assert found.pictures == (x.Picture("https://pbs.twimg.com/media/one.jpg", 1080, 1350),)


def test_a_long_post_cut_short_says_it_goes_on() -> None:
    found = x.read(answer(FIRST, "התחלה של פוסט ארוך", note_tweet={"id": "abc"}))
    assert found is not None and found.text.endswith("…")


def test_a_tombstone_or_an_empty_answer_is_no_post() -> None:
    assert x.read({"__typename": "TweetTombstone", "tombstone": {}}) is None
    assert x.read({}) is None


# -- a thread --------------------------------------------------------------------------


def served(monkeypatch: pytest.MonkeyPatch, answers: dict[str, dict]) -> list[str]:
    asked: list[str] = []

    def fetch(ident: str) -> dict:
        asked.append(ident)
        return answers.get(ident, {})

    monkeypatch.setattr(x, "fetch", fetch)
    return asked


def test_a_thread_is_walked_back_to_its_start_and_stops_at_anybody_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Upward, because the endpoint says what a post answers and never what answers it;
    the first post by another account ends the walk and is not asked for."""
    asked = served(
        monkeypatch,
        {
            THIRD: a_reply(THIRD, "שלוש", SECOND),
            SECOND: a_reply(SECOND, "שתיים", FIRST),
            FIRST: a_reply(FIRST, "אחת", ELSEWHERE, handle="kan_news"),
        },
    )
    posts = x.thread(f"https://x.com/aviv_bahar/status/{THIRD}")
    assert [one.text for one in posts] == ["אחת", "שתיים", "שלוש"]
    assert asked == [THIRD, SECOND, FIRST], "the foreign post is never asked for"


def test_a_thread_is_walked_no_further_than_the_most(monkeypatch: pytest.MonkeyPatch) -> None:
    chain = {str(n): a_reply(str(n), f"פוסט {n}", str(n - 1)) for n in range(2, 100)}
    served(monkeypatch, chain)
    assert len(x.thread("https://x.com/aviv_bahar/status/99")) == x.MOST


def test_an_address_that_names_no_post_or_a_post_x_will_not_show_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    served(monkeypatch, {})
    with pytest.raises(TargumError) as none:
        x.thread("https://x.com/aviv_bahar")
    assert none.value.key == "x.one-post"
    with pytest.raises(TargumError) as gone:
        x.thread(f"https://x.com/aviv_bahar/status/{FIRST}")
    assert gone.value.key == "x.not-shown"


def test_a_thread_is_a_text_a_line_a_paragraph() -> None:
    posts = [
        x.Post(FIRST, "aviv_bahar", "", "", "שבת שלום\n\nלכולם", ""),
        x.Post(SECOND, "aviv_bahar", "", "", "ועוד שורה", ""),
    ]
    assert x.text_of(posts) == (
        "---\ntitle: שבת שלום\nauthor: @aviv_bahar\n---\n\nשבת שלום\n\nלכולם\n\nועוד שורה\n"
    )


# -- the hosted door -------------------------------------------------------------------


def test_shut_it_says_so_by_name_and_asks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Off by default: never falling through to the page reader, which would import X's
    JavaScript shell as the text."""
    from targum import serve

    monkeypatch.delenv(x.ENV, raising=False)
    monkeypatch.setattr(x, "fetch", lambda ident: pytest.fail("a shut door asks nothing"))
    job = serve.Job(id="a", source=f"https://x.com/aviv_bahar/status/{FIRST}")
    serve.Library(tmp_path).prepare(job)
    assert job.stage == "failed"
    assert job.error.startswith("We don't bring posts in from X.")


def test_armed_a_thread_arrives_as_a_post(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import serve

    monkeypatch.setenv(x.ENV, "1")
    served(
        monkeypatch,
        {
            SECOND: a_reply(
                SECOND,
                "ועוד שורה",
                FIRST,
                photos=[{"url": "https://pbs.twimg.com/media/b.jpg", "width": 800, "height": 800}],
            ),
            FIRST: answer(FIRST, "שבת שלום\nלכולם"),
        },
    )
    job = serve.Job(id="a", source=f"https://twitter.com/aviv_bahar/status/{SECOND}?s=20")
    serve.Library(tmp_path).prepare(job)
    assert job.error == "" and job.stage in ("ready", "blocked"), job.error
    said = job.options["post"]
    assert said["platform"] == "x" and said["url"] == f"https://x.com/i/status/{SECOND}"
    assert (said["handle"], said["name"]) == ("aviv_bahar", "אביב בהר")
    assert said["items"] == [
        {"lines": 2, "pictures": []},
        {"lines": 1, "pictures": ["https://pbs.twimg.com/media/b.jpg"]},
    ]
    assert Path(job.source).read_text(encoding="utf-8").endswith("לכולם\n\nועוד שורה\n")


def test_a_threads_manifest_keeps_each_posts_lines_and_photos_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counted from the end of the document, past the title and byline the head stands in
    for; each post's photos are its own item's, numbered on across the thread."""
    from targum import serve
    from targum.video import instagram

    def pictures_into(found: Any, into: Path) -> list[Path]:
        into.mkdir(parents=True, exist_ok=True)
        made = []
        for n, _ in enumerate(found.pictures, start=1):
            Image.new("RGB", (800, 1000), (1, 2, 3)).save(into / f"{n:02d}.jpg", format="JPEG")
            made.append(into / f"{n:02d}.jpg")
        return made

    monkeypatch.setattr(instagram, "pictures_into", pictures_into)
    folder = tmp_path / "thread"
    folder.mkdir()
    job = serve.Job(id="j", source="x", options={})
    job.options["post"] = {
        "platform": "x",
        "url": f"https://x.com/i/status/{SECOND}",
        "handle": "aviv_bahar",
        "name": "אביב בהר",
        "posted_at": "2026-09-21T13:33:20Z",
        "avatar": "",
        "pictures": [],
        "items": [
            {"lines": 2, "pictures": ["https://pbs.twimg.com/media/a.jpg"]},
            {"lines": 1, "pictures": ["https://pbs.twimg.com/media/b.jpg"]},
        ],
    }
    document = SimpleNamespace(
        blocks=[SimpleNamespace(id=f"b{n:04d}") for n in range(5)]  # title, byline, 3 lines
    )
    library = SimpleNamespace(incidents=None, _thread_items=serve.Library._thread_items)
    serve.Library.keep_post(library, job, folder, document)  # type: ignore[arg-type]
    got = post.read(folder)
    assert got is not None and got["platform"] == "x"
    assert [item["block_ids"] for item in got["items"]] == [["b0002", "b0003"], ["b0004"]]
    assert [[m["path"] for m in item["media"]] for item in got["items"]] == [
        ["post/media-001.webp"],
        ["post/media-002.webp"],
    ]
