"""One thread in trafilatura at a time (targum-internal#667).

trafilatura parses every page with one lxml parser made at import, and six news-round
workers using it side by side corrupted libxml2's memory and aborted `targum serve`.
These pin that `ingest.url`'s two doors into trafilatura never let a second thread in.
"""

from __future__ import annotations

import sys
import threading
import time
import types
from typing import Any

import pytest

from targum.ingest import url


class _Counted:
    """A stand-in trafilatura that notes the most threads ever inside it at once."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.inside = 0
        self.most_inside = 0
        self.calls = 0

    def _visit(self, pause: float) -> None:
        with self.lock:
            self.inside += 1
            self.calls += 1
            self.most_inside = max(self.most_inside, self.inside)
        time.sleep(pause)
        with self.lock:
            self.inside -= 1

    def extract(self, html: str, **_: Any) -> str:
        self._visit(0.02)
        return "<p>read</p>"

    def extract_metadata(self, html: str) -> None:
        self._visit(0.01)


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> _Counted:
    stand_in = _Counted()
    module = types.ModuleType("trafilatura")
    module.extract = stand_in.extract  # type: ignore[attr-defined]
    module.extract_metadata = stand_in.extract_metadata  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "trafilatura", module)
    return stand_in


def test_six_threads_never_extract_side_by_side(counted: _Counted) -> None:
    start = threading.Barrier(6)

    def worker(k: int) -> None:
        start.wait()
        for _ in range(4):
            if k % 2:
                url.extract_metadata("<html></html>")
            else:
                url.extract("<html></html>", output_format="html")

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert counted.calls == 24
    assert counted.most_inside == 1


def test_article_paragraphs_goes_through_the_lock(
    counted: _Counted, monkeypatch: pytest.MonkeyPatch
) -> None:
    held: list[bool] = []
    real = counted.extract

    def noting(html: str, **options: Any) -> str:
        held.append(url.TRAFILATURA.locked())
        return real(html, **options)

    monkeypatch.setattr(sys.modules["trafilatura"], "extract", noting)
    url.article_paragraphs("<html><body><p>read</p></body></html>")
    assert held == [True]
    assert not url.TRAFILATURA.locked()


def test_a_failing_extraction_lets_the_lock_go(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("trafilatura")

    def broken(html: str, **_: Any) -> str:
        raise ValueError("unreadable")

    module.extract = broken  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "trafilatura", module)
    with pytest.raises(ValueError):
        url.extract("<html></html>")
    assert not url.TRAFILATURA.locked()
