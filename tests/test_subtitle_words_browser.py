"""A subtitle-timed video, re-timed by the aligner, lights its words (#572).

The whole road in one browser: cues as `ingest.subtitles` makes them, the aligner's
answer (faked) run through `retime_folder`, the reader built from the manifest that
leaves, and the film's clock driven by hand. Each word the aligner was sure of is lit
as the clock reaches it; the one it was not sure of is never lit.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import address, browser, opened  # noqa: E402, F401
from test_subtitle_words import CUES, GOOD, WORD_FLOOR, Fake, folder  # noqa: E402

from targum.audio import manifest as manifest_module  # noqa: E402
from targum.audio.subtitle_words import retime_folder  # noqa: E402
from targum.models import (  # noqa: E402
    Annotation,
    Document,
    SegmentedDocument,
    Token,
    Translation,
    read_artifact,
)

#: The film's clock, held by the test, on the page's one film element.
FAKE_CLOCK = """
() => {
  const v = document.querySelector('.video-el');
  window.__t = 0;
  Object.defineProperty(v, 'currentTime', {
    configurable: true, get: () => window.__t, set: (x) => { window.__t = x; },
  });
  Object.defineProperty(v, 'paused', { configurable: true, get: () => false });
  v.play = () => { v.dispatchEvent(new Event('play')); return Promise.resolve(); };
  v.pause = () => {};
  window.__words = [];
  new MutationObserver((changes) => {
    for (const change of changes) {
      const el = change.target;
      const had = (change.oldValue || '').split(/\\s+/);
      if (el.matches('#reader .w') && el.classList.contains('voiced-now')
          && !had.includes('voiced-now')) {
        window.__words.push(el.textContent);
      }
    }
  }).observe(document.getElementById('reader'), {
    subtree: true, attributes: true, attributeFilter: ['class'], attributeOldValue: true,
  });
}
"""

AT = """
async (t) => {
  window.__t = t;
  const v = document.querySelector('.video-el');
  v.dispatchEvent(new Event('timeupdate'));
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const lit = document.querySelector('#reader .w.voiced-now');
  return lit ? lit.textContent : null;
}
"""


def reader(tmp_path: Path, rows) -> Path:
    """The two cues' targum with a picture, re-timed from `rows`, and built."""
    from targum.render import render

    built = folder(tmp_path)
    (built / "audio" / "parts" / "part-001.mp3").unlink()
    with wave.open(str(built / "audio" / "parts" / "part-001.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00" * 16000)
    (built / "video" / "parts").mkdir(parents=True)
    (built / "video" / "parts" / "part-001.webm").write_bytes(
        (Path(__file__).parent / "fixtures" / "tiny.webm").read_bytes()
    )
    kept = manifest_module.load(built)
    kept.parts[0].audio = "audio/parts/part-001.wav"
    kept.parts[0].video = "video/parts/part-001.webm"
    manifest_module.write(built, kept)
    retime_folder(built, Fake(rows))

    segmented = read_artifact(SegmentedDocument, built / "segments.json")
    tokens: dict[str, list[Token]] = {}
    for segment in segmented.segments:
        offset = 0
        tokens[segment.id] = []
        for word in segment.text.split(" "):
            tokens[segment.id].append(
                Token(start=offset, end=offset + len(word), surface=word, lemma=word, band=1)
            )
            offset += len(word) + 1
    document = Document(
        source="source.mp4", title="A talk", language="he", blocks=[], content_hash="h"
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "A line." for segment in segmented.segments},
    )
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="test/1",
        method="frequency",
        method_note="a test",
        tokens=tokens,
    )
    return render(
        document,
        segmented,
        [translation],
        built / "reader",
        annotation=annotation,
        folder=built,
    )[0]


def test_an_aligned_subtitle_video_lights_each_sure_word(browser, tmp_path) -> None:  # noqa: F811
    rows = list(GOOD)
    rows[1] = (rows[1][0], rows[1][1], WORD_FLOOR - 1)  # «רוצה», unsure
    built = reader(tmp_path, rows)
    context = opened(browser)
    page = context.new_page()
    try:
        page.goto(address(built))
        page.wait_for_selector("#video:not([hidden])")
        page.wait_for_function("() => window.TargumPlayer && window.TargumPlayer.length() > 0")
        page.evaluate(FAKE_CLOCK)
        page.click(".bar .listen")
        page.wait_for_timeout(100)
        said = " ".join(cue.text for cue in CUES).split()
        for k, (start, end, _) in enumerate(rows):
            lit = page.evaluate(AT, (start + end) / 2)
            assert lit == (None if k == 1 else said[k]), (k, lit)
        assert page.evaluate("() => window.__words") == [w for k, w in enumerate(said) if k != 1]
    finally:
        context.close()
