"""Time to a working word tap on a phone profile, for built reader pages (targum-internal#409).

    PYTHONPATH=$PWD/src .venv/bin/python scripts/measure_tap.py <out-folder> \\
      parasha/bereshit/reader/sec-0001.html ...

Slow 4G as Lighthouse states it (150 ms RTT, 1.6 Mbps down, 750 kbps up) and a 4x CPU
slowdown, each page served gzipped from the folder as Caddy serves it. Each page is
opened cold three times; a script started before the page's own tries a word every
25 ms from the first byte until the word's card is drawn, and the median is reported
with the page's raw and gzipped size. Nothing here is fetched from anywhere but the
local server, and nothing spends.
"""

from __future__ import annotations

import gzip
import http.server
import socketserver
import statistics
import sys
import threading
from pathlib import Path
from typing import Any

RUNS = 3
RTT_MS = 150
DOWN_BPS = 1.6 * 1024 * 1024 / 8
UP_BPS = 750 * 1024 / 8
CPU_SLOWDOWN = 4

PROBE = """
window.__tap = null;
(function poll() {
  var word = document.querySelector('.pair .w');
  var card = document.getElementById('gloss-card');
  if (word) { word.click(); }
  if (card && !card.hidden && card.getBoundingClientRect().height > 0) {
    window.__tap = performance.now();
    return;
  }
  setTimeout(poll, 25);
})();
"""


def _handler(root: Path) -> type[http.server.SimpleHTTPRequestHandler]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:
            path = root / self.path.split("?")[0].lstrip("/")
            if path.suffix != ".html" or not path.is_file():
                super().do_GET()
                return
            body = gzip.compress(path.read_bytes(), 6)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def measure(root: Path, pages: list[str]) -> list[tuple[str, list[float], int, int]]:
    """Each page's tap times in seconds, raw size and gzipped size."""
    from playwright.sync_api import sync_playwright

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _handler(root))
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    found = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for page_path in pages:
                times = []
                for _ in range(RUNS):
                    context = browser.new_context(
                        viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
                    )
                    page = context.new_page()
                    cdp = context.new_cdp_session(page)
                    cdp.send("Network.enable")
                    cdp.send(
                        "Network.emulateNetworkConditions",
                        {
                            "offline": False,
                            "latency": RTT_MS,
                            "downloadThroughput": DOWN_BPS,
                            "uploadThroughput": UP_BPS,
                        },
                    )
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": CPU_SLOWDOWN})
                    page.add_init_script(PROBE)
                    page.goto(f"http://127.0.0.1:{port}/{page_path}", wait_until="commit")
                    page.wait_for_function("window.__tap !== null", timeout=60000)
                    times.append(page.evaluate("window.__tap") / 1000)
                    context.close()
                raw = (root / page_path).read_bytes()
                found.append((page_path, times, len(raw), len(gzip.compress(raw, 6))))
            browser.close()
    finally:
        server.shutdown()
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    for page_path, times, raw, packed in measure(Path(argv[0]), argv[1:]):
        runs = ", ".join(f"{t:.2f}" for t in times)
        print(
            f"{page_path}: tap {statistics.median(times):.2f} s (runs {runs}), "
            f"{raw / 1000:.0f} kB raw, {packed / 1000:.0f} kB gzipped"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
