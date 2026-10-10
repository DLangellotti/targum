"""The door to the next part of a video, in a real browser (David, 2026-10-07; design.md
§12, "One press gets the whole video, a part at a time").

"At the end of the first part of a video I uploaded, there's no button to take me to the
next video." The way on was the pager at the foot of the transcript, and Theatre does not
show the transcript. Now "Next part" stands under the picture once the voice reaches the
last line or the film ends, in Theatre and in Beside. The page asks the box once, as it
opens, for the part after it — the press on the quote was consent to every part — and the
door says what became of it. Nothing plays by itself, and nothing the door does spends.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import address, browser, built, opened  # noqa: E402, F401

WIDE = {"width": 1440, "height": 900}

#: Where the screenshots go, when a run is asked to keep them.
SHOTS = os.environ.get("TARGUM_SHOTS", "")


def two_parts(tmp_path: Path, *, second_ready: bool = True, count: int = 2) -> Path:
    """A video in `count` parts, built the way an import is: a heading and two lines a
    part, each part its own film. Part one is made; the rest are made, or all waiting for
    their transcripts."""
    import wave

    from targum.audio import manifest as manifest_module
    from targum.models import BlockKind, Document, Segment, SegmentedDocument, Translation
    from targum.render import render

    film = (Path(__file__).parent / "fixtures" / "tiny.webm").read_bytes()
    (tmp_path / "audio" / "parts").mkdir(parents=True)
    (tmp_path / "video" / "parts").mkdir(parents=True)
    segments: list[Segment] = []
    parts = []
    for p in range(1, count + 1):
        made = p == 1 or second_ready
        with wave.open(str(tmp_path / "audio" / "parts" / f"part-00{p}.wav"), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(8000)
            out.writeframes(b"\x00" * 16000)
        (tmp_path / "video" / "parts" / f"part-00{p}.webm").write_bytes(film)
        ref = f"part {p}" if made else f"part {p}:waiting"
        head = Segment(
            id=f"{p}0000.000-aaaaaa",
            block_id=f"h{p}",
            block_index=p * 10,
            index=0,
            kind=BlockKind.heading,
            level=2,
            text=f"חלק {p}",
            ref=ref,
        )
        lines = [
            Segment(
                id=f"{p}000{n}.000-aaaaaa",
                block_id=f"b{p}{n}",
                block_index=p * 10 + n,
                index=0,
                text=f"שורה {p}.{n}",
                ref=ref,
            )
            for n in (1, 2)
        ]
        segments += [head, *lines]
        parts.append(
            manifest_module.ManifestPart(
                number=p,
                start=(p - 1) * 200.0,
                end=p * 200.0,
                audio=f"audio/parts/part-00{p}.wav",
                video=f"video/parts/part-00{p}.webm" if made else "",
                spans={lines[0].id: [0.05, 0.45], lines[1].id: [0.5, 0.95]} if made else {},
            )
        )
    manifest_module.write(
        tmp_path,
        manifest_module.AudioManifest(
            source="source.mp4", sha256="x", duration=200.0 * count, language="he", parts=parts
        ),
    )
    document = Document(
        source="source.mp4", title="A talk", language="he", blocks=[], content_hash="h"
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="fake/1", segments=segments
    )
    translated = [s for s in segments if second_ready or not s.ref.endswith(":waiting")]
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: f"Line {s.text[-3:]}." for s in translated},
    )
    render(document, segmented, [translation], tmp_path / "reader", folder=tmp_path)
    return tmp_path / "reader"


def answering(page, chapter, jobs=None) -> list[dict]:
    """Stand in for the box: `/chapter` answers `chapter`, `/job/<id>` the next of `jobs`
    (the last one again once they run out). Every request the page sends is kept."""
    asked: list[dict] = []
    left = list(jobs or [])

    def on_chapter(route) -> None:
        body = route.request.post_data or ""
        asked.append({"path": "/chapter", "body": json.loads(body) if body else {}})
        status, payload = chapter
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def on_job(route) -> None:
        asked.append({"path": route.request.url.split("?")[0].split("/job/")[1], "body": {}})
        payload = left.pop(0) if len(left) > 1 else (left[0] if left else {"stage": "working"})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/chapter*", on_chapter)
    page.route("**/job/*", on_job)
    return asked


def film_page(browser, reader: Path, name: str, view: str, chapter, jobs=None):  # noqa: F811
    context = opened(browser, WIDE)
    context.add_init_script(
        f"try {{ localStorage.setItem('targum:film-view', '{view}'); }} catch (e) {{}}"
    )
    page = context.new_page()
    asked = answering(page, chapter, jobs)
    page.goto(address(reader / name))
    page.wait_for_selector(".pair", state="attached")
    page.wait_for_selector("#video:not([hidden])")
    page.wait_for_function("() => window.TargumPlayer && window.TargumPlayer.length() > 0")
    return context, page, asked


def play_to_end(page) -> None:
    page.wait_for_function("() => window.TargumPlayer.seekable()")
    page.evaluate(
        "() => { const v = document.querySelector('.video-el');"
        " v.currentTime = Math.max(0, v.duration - 0.15); return v.play(); }"
    )
    page.wait_for_function("() => document.querySelector('.video-el').ended", timeout=10000)
    page.wait_for_timeout(150)


def shot(page, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"video-next-{name}.png"))


def test_the_end_of_a_part_has_a_door_to_the_next(browser, tmp_path) -> None:  # noqa: F811
    """Theatre, played to the end: "Next part" under the picture, leading to part two's
    page. It was not there before the end, the page asked once for the next part as it
    opened — `ahead`, the page's own number plus one — and nothing played by itself."""
    reader = two_parts(tmp_path)
    context, page, asked = film_page(
        browser, reader, "sec-0001.html", "theatre", (200, {"ready": True})
    )
    try:
        door = page.locator("#film-next")
        assert not door.is_visible(), "not before the end"
        page.wait_for_function("() => document.getElementById('film-next').dataset.state")
        assert asked == [{"path": "/chapter", "body": {**asked[0]["body"]}}]
        assert asked[0]["body"]["ahead"] is True and asked[0]["body"]["number"] == 2
        play_to_end(page)
        assert page.evaluate("() => document.body.classList.contains('film-theatre')")
        assert door.is_visible(), "the end of the part leads on"
        go = page.locator(".film-next-go")
        assert go.inner_text().strip() == "Next part"
        assert go.get_attribute("href") == "sec-0002.html"
        assert page.locator(".film-next-said").inner_text() == ""
        box = go.bounding_box()
        assert box and box["height"] >= 44, box
        shot(page, "theatre-ended")

        # Keyboard: the door is reached with Tab and opened with Enter.
        for _ in range(40):
            page.keyboard.press("Tab")
            if page.evaluate("() => document.activeElement.classList.contains('film-next-go')"):
                break
        else:
            pytest.fail("Tab never reached the door")
        assert page.evaluate("() => document.activeElement.matches(':focus-visible')")
        page.keyboard.press("Enter")
        page.wait_for_url("**/sec-0002.html")
        assert page.evaluate("() => document.querySelector('.video-el').paused"), (
            "the next part opens waiting for its press"
        )
    finally:
        context.close()


def test_beside_has_the_door_at_the_last_line_without_playing_to_the_end(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """Stepped to the last line with ↓, the door is under the picture in Beside, and the
    pager still stands at the foot of the transcript."""
    reader = two_parts(tmp_path)
    context, page, _asked = film_page(
        browser, reader, "sec-0001.html", "beside", (200, {"ready": True})
    )
    try:
        assert not page.locator("#film-next").is_visible()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        page.wait_for_function("() => document.body.classList.contains('film-at-end')")
        assert page.evaluate("() => document.body.classList.contains('film-beside')")
        assert page.locator("#film-next").is_visible()
        assert page.evaluate("() => document.querySelector('.video-el').paused"), "nothing plays"
        assert page.locator(".pager .next").get_attribute("href") == "sec-0002.html"
        shot(page, "beside-last-line")
    finally:
        context.close()


def test_a_part_being_made_says_so_and_opens_when_it_is_ready(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """Part two not made yet: the ask on opening started it, so the door says it is being
    got ready; pressed then, it says it will open it, and does once the job is done. The
    door itself sends nothing that spends — the one ask is the page's, on opening."""
    reader = two_parts(tmp_path, second_ready=False)
    context, page, asked = film_page(
        browser,
        reader,
        "sec-0001.html",
        "theatre",
        (200, {"id": "j1", "stage": "queued", "blocked": "", "error": ""}),
        jobs=[{"stage": "working"}],
    )
    try:
        play_to_end(page)
        said = page.locator(".film-next-said")
        assert said.inner_text() == "We're getting it ready."
        shot(page, "theatre-making")
        page.locator(".film-next-go").click()
        assert said.inner_text() == "We'll open it when it's ready."
        page.wait_for_timeout(300)
        assert page.url.endswith("sec-0001.html"), "not before it is ready"
        page.unroute("**/job/*")
        answering_done = []

        def done(route) -> None:
            answering_done.append(route.request.url)
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"stage": "done"})
            )

        page.route("**/job/*", done)
        page.wait_for_url("**/sec-0002.html", timeout=10000)
        posts = [one for one in asked if one["path"] == "/chapter"]
        assert len(posts) == 1 and posts[0]["body"]["ahead"] is True, posts
    finally:
        context.close()


def test_a_refused_part_says_why_and_a_failed_one_offers_again(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    reader = two_parts(tmp_path, second_ready=False)
    refusal = "You've used this month's credits. Top up, or they reset on 1 November."
    # What still works and the way on ride beside the sentence (design.md §12,
    # 2026-10-09): Top up drawn and greyed, with the reason and the fact after it.
    refused = {
        "id": "j1",
        "stage": "blocked",
        "blocked": refusal,
        "error": "",
        "fact": "The library still opens",
        "act": "top-up",
    }
    context, page, _asked = film_page(browser, reader, "sec-0001.html", "theatre", (402, refused))
    try:
        play_to_end(page)
        assert page.locator(".film-next-said").inner_text() == refusal
        assert not page.locator(".film-next-again").is_visible()
        up = page.locator(".film-next-extra .fault-go")
        assert up.inner_text() == "Top up" and up.is_disabled()
        facts = page.locator(".film-next-extra .fault-fact").all_inner_texts()
        assert facts == ["Payments open soon", "The library still opens"]
    finally:
        context.close()

    context, page, asked = film_page(
        browser,
        reader,
        "sec-0001.html",
        "theatre",
        (200, {"id": "j2", "stage": "failed", "blocked": "", "error": "We couldn't hear it."}),
    )
    try:
        play_to_end(page)
        assert page.locator(".film-next-said").inner_text() == "We couldn't hear it."
        again = page.locator(".film-next-again")
        assert again.is_visible()
        again.click()
        page.wait_for_timeout(200)
        posts = [one for one in asked if one["path"] == "/chapter"]
        assert len(posts) == 2 and all(one["body"]["ahead"] for one in posts), (
            "the same ask again, under the same consent"
        )
    finally:
        context.close()


def test_the_last_part_ends_at_the_foot_of_its_transcript(browser, tmp_path) -> None:  # noqa: F811
    """No door on the last part. In Theatre the transcript opens at the end, to its foot,
    where Done and the library's offer are — the end of any text."""
    reader = two_parts(tmp_path)
    context, page, asked = film_page(
        browser, reader, "sec-0002.html", "theatre", (200, {"ready": True})
    )
    try:
        assert page.locator("#film-next").count() == 0
        play_to_end(page)
        page.wait_for_function("() => document.body.classList.contains('film-panel')")
        foot = page.locator("#foot")
        assert foot.is_visible()
        box = foot.bounding_box()
        assert box and 0 <= box["y"] < WIDE["height"], box
        assert not [one for one in asked if one["path"] == "/chapter"], "nothing after the last"
        shot(page, "last-part")
    finally:
        context.close()


def test_a_waiting_part_starts_itself_and_asks_for_nothing_ahead(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """David, 2026-10-07: opening any waiting part starts it — the quote's press covered
    every part — so its page has no Transcribe press. It asks for itself once (not
    `ahead`), says it is being made, and asks for no part after it: a reader on a part
    that is not made yet is not working on it. A failure offers Try again."""
    reader = two_parts(tmp_path, second_ready=False, count=3)
    context = opened(browser, WIDE)
    page = context.new_page()
    asked = answering(
        page,
        (200, {"id": "j3", "stage": "queued", "blocked": "", "error": ""}),
        jobs=[{"stage": "working"}, {"stage": "failed", "error": "We couldn't hear it."}],
    )
    try:
        page.goto(address(reader / "sec-0002.html"))
        page.wait_for_selector("#waiting-note")
        page.wait_for_function(
            "() => document.getElementById('waiting-said').textContent.trim() !== ''"
        )
        posts = [one for one in asked if one["path"] == "/chapter"]
        assert len(posts) == 1, posts
        assert posts[0]["body"]["number"] == 2 and not posts[0]["body"].get("ahead")
        assert page.locator("#waiting-said").inner_text() == "We're getting it ready."
        assert not page.locator("#translate-chapter").is_visible(), "no press to make"
        assert page.locator("#waiting-cost").inner_text() == "Already in the credits you confirmed"
        shot(page, "waiting-part")
        page.wait_for_function(
            "() => document.getElementById('waiting-said').textContent"
            ' === "We couldn\'t hear it."',
            timeout=10000,
        )
        again = page.locator("#translate-chapter")
        assert again.is_visible() and again.inner_text() == "Try again"
        assert len([one for one in asked if one["path"] == "/chapter"]) == 1
    finally:
        context.close()


def test_beside_has_one_primary_at_the_end_of_a_part(browser, tmp_path) -> None:  # noqa: F811
    """David, 2026-10-07: in Beside "Next part" stays the teal pill and Done becomes a
    quiet text link, so the end of a part has one primary; on the last part, with no door,
    Done is the pill it always was."""
    reader = two_parts(tmp_path)
    looks = (
        "() => { const s = getComputedStyle(document.getElementById('done-mark'));"
        " return { bg: s.backgroundImage + ' ' + s.backgroundColor, line: s.textDecorationLine }; }"
    )
    context, page, _asked = film_page(
        browser, reader, "sec-0001.html", "beside", (200, {"ready": True})
    )
    try:
        done = page.evaluate(looks)
        # The pill is the primary's flat fill (§13; its sheen went on 2026-10-09).
        assert done["line"] == "underline" and "rgb(31, 111, 107)" not in done["bg"], done
    finally:
        context.close()
    context, page, _asked = film_page(
        browser, reader, "sec-0002.html", "beside", (200, {"ready": True})
    )
    try:
        done = page.evaluate(looks)
        assert "rgb(31, 111, 107)" in done["bg"] and done["line"] != "underline", done
    finally:
        context.close()


# -- the end of a part in Theatre (David, 2026-10-08; design.md §12) -------------------

END = """
() => {
  const end = document.getElementById('film-end');
  const foot = document.getElementById('foot');
  const shown = (el) => !!el && el.getClientRects().length > 0;
  return {
    shown: shown(end),
    head: end ? end.querySelector('.film-end-head').textContent.trim() : null,
    footInside: !!end && end.contains(foot),
    footShown: shown(foot),
    footBottom: foot ? foot.getBoundingClientRect().bottom : null,
    line: shown(document.getElementById('film-sub')),
    press: document.getElementById('done-mark').textContent.trim(),
    finished: !document.getElementById('finished').hidden,
  };
}
"""


def test_theatre_ends_a_part_with_the_foot_under_the_picture(browser, tmp_path) -> None:  # noqa: F811
    """Played to its end in Theatre, the line under the picture gives way to "End of part 1
    of 2" and the text's own foot — Done, the press that marks the rest known — moved in,
    so a part can be finished without opening the transcript. Next part is still there.
    Moving the film again puts the foot back under the transcript."""
    reader = two_parts(tmp_path)
    context, page, _ = film_page(
        browser, reader, "sec-0001.html", "theatre", (200, {"ready": True})
    )
    try:
        before = page.evaluate(END)
        assert not before["shown"] and not before["footInside"]
        # The fixture carries no glosses; what the chips draw from one is what is tested.
        page.evaluate(
            """() => { window.TargumReader.unmarked = () => ({count: 2,
              words: ['מטבעות', 'הכהן'],
              glossed: [{word: 'מטבעות', gloss: 'coins; money', language: 'en'},
                        {word: 'הכהן', gloss: '', language: 'en'}]}); }"""
        )
        play_to_end(page)
        ended = page.evaluate(END)
        assert ended["shown"] and ended["head"] == "End of part 1 of 2", ended
        assert ended["footInside"] and ended["footShown"], ended
        assert ended["footBottom"] <= WIDE["height"], "inside the window"
        assert not ended["line"], "the line under the picture gave way"
        chips = page.evaluate(
            "() => [...document.querySelectorAll('#film-end .film-end-word')]"
            ".map((c) => !!c.querySelector('.film-end-he'))"
        )
        assert chips == [True, True], "each chip carries the word as the text writes it"
        glosses = page.evaluate(
            "() => [...document.querySelectorAll('#film-end .film-end-word')]"
            ".map((c) => c.querySelector('.film-end-gloss')?.textContent || '')"
        )
        assert glosses == ["coins", ""], "its first meaning beside it, where it has one"
        assert page.locator("#film-next").is_visible(), "and the next part is still the way on"
        shot(page, "theatre-end-block")
        page.click("#done-mark")
        assert page.evaluate(END)["finished"], "the part is finished from here"
        page.evaluate("() => window.TargumPlayer.seek(0.1)")
        page.wait_for_timeout(150)
        back = page.evaluate(END)
        assert not back["shown"] and not back["footInside"], back
    finally:
        context.close()


def test_inside_a_playlist_theatre_ends_a_part_under_the_picture_too(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """Audit Q10 (2026-10-09): inside a playlist the end of a part stood at the foot of the
    transcript, far under the picture. It comes under the picture as it does outside one,
    the column stepping aside, and the foot moved in is the playlist's."""
    reader = two_parts(tmp_path)
    context, page, _ = film_page(
        browser, reader, "sec-0001.html?list=1&at=0", "theatre", (200, {"ready": True})
    )
    try:
        play_to_end(page)
        ended = page.evaluate(END)
        assert ended["shown"] and ended["footInside"] and ended["footShown"], ended
        assert not page.evaluate("() => document.body.classList.contains('film-panel')")
    finally:
        context.close()


def test_the_unmarked_words_are_the_ones_the_press_would_mark(browser, built) -> None:  # noqa: F811
    """What the end of a part asks about is what the foot's press marks: the same count,
    and the words met most first."""
    context = opened(browser, WIDE)
    page = context.new_page()
    try:
        page.goto(address(built))
        page.wait_for_selector(".pair")
        rest = page.evaluate("() => window.TargumReader.unmarked(4)")
        press = page.locator("#done-mark").inner_text()
        assert rest["count"] > 4 and len(rest["words"]) == 4, rest
        assert str(rest["count"]) in press, (rest, press)
        # And what each means, for the chips (design.md §12, 2026-10-09).
        assert [one["word"] for one in rest["glossed"]] == rest["words"]
        assert all("gloss" in one for one in rest["glossed"]), rest["glossed"]
    finally:
        context.close()
