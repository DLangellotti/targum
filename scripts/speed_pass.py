"""A read-only speed pass on the live public pages (design.md §14 line 5, targum-internal#551).

    .venv/bin/python scripts/speed_pass.py                     # the eight public pages
    .venv/bin/python scripts/speed_pass.py --page /library/ruth --json speed.json

§14 line 5: "On a phone profile the surface is useful in under 1.5 s". Useful is read as
the largest contentful paint (LCP), with the first contentful paint beside it. Each page
is loaded cold, in a fresh context, on two profiles:

- **phone:** 412×823 with touch, the CPU throttled 4× (the Moto G Power class Lighthouse
  uses) and DevTools' "Slow 4G" (562.5 ms latency, 1.47 Mbps down, 675 kbps up). Three
  loads, median.
- **desk:** 1440×900, unthrottled. Two loads, median.

DevTools throttling does not delay the connection's own setup, so a real phone pays DNS,
TCP and TLS on top of what is measured: about three round trips at Lighthouse's 150 ms,
0.45 s, which `--setup-ms` adds to the phone's LCP before it is held to the budget
(builder-3's pass of 2026-10-28 found the phone's first byte no slower than the desk's).
The verdict is on that figure; the measured one is printed beside it.

Read-only by construction: every request that is not a GET is aborted before it leaves,
and the run says how many it stopped (none, so far). Nothing signs in, so nothing is
built or spent. The user agent ends in `targum-speed-pass`, which `visits.BOTS` drops, so
these loads never reach the visitor count. Run it from the laptop after a deploy that
touches the public pages (deploy/README.md, "Speed"), never against a test server that
needs a key. It exits 1 when a phone page is over the budget, so it can stand in a check.

Needs Playwright's Chromium: `uv sync --extra browser && uv run playwright install chromium`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SITE = "https://targum.page"
#: The signed-out pages a stranger meets, by name (builder-3's list, 2026-10-28).
PAGES = {
    "landing": "/",
    "library": "/library",
    "ruth": "/library/ruth",
    "scene-01": "/library/scene-01-nice-to-meet-you",
    "scene-he-01": "/library/scene-he-01-florentin-electricity-bill-split",
    "about": "/about",
    "privacy": "/privacy",
    "terms": "/terms",
}
#: §14 line 5.
BUDGET_MS = 1500
#: DNS, TCP and TLS on a real phone: three round trips at Lighthouse's 150 ms.
SETUP_MS = 450
#: The tag the visitor count drops (`visits.BOTS`).
TAG = "targum-speed-pass"
CHROME = "Chrome/151.0.0.0"
AGENTS = {
    "phone": (
        "Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) {CHROME} Mobile Safari/537.36 {TAG}"
    ),
    "desk": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) {CHROME} Safari/537.36 {TAG}"
    ),
}
#: DevTools' "Slow 4G", applied: latency in ms, throughput in bytes a second.
SLOW_4G = {
    "offline": False,
    "latency": 562.5,
    "downloadThroughput": 1474.56 * 1024 / 8,
    "uploadThroughput": 675 * 1024 / 8,
}

OBSERVE = """
window.__lcp = 0;
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) window.__lcp = entry.startTime;
}).observe({type: 'largest-contentful-paint', buffered: true});
window.__cls = 0;
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__cls += entry.value;
}).observe({type: 'layout-shift', buffered: true});
"""

COLLECT = """() => {
  const nav = performance.getEntriesByType('navigation')[0];
  const fcp = (performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime || 0;
  const resources = performance.getEntriesByType('resource');
  let bytes = nav.transferSize || 0;
  for (const one of resources) bytes += one.transferSize || 0;
  return {
    ttfb: Math.round(nav.responseStart), fcp: Math.round(fcp), lcp: Math.round(window.__lcp),
    load: Math.round(nav.loadEventEnd), cls: Math.round(window.__cls * 1000) / 1000,
    requests: resources.length + 1, kb: Math.round(bytes / 1024),
  };
}"""


@dataclass
class Result:
    """One page on one profile: the median of its loads."""

    name: str
    url: str
    profile: str
    fcp: float
    lcp: float
    ttfb: float
    load: float
    cls: float
    kb: float
    requests: float
    blocked: list[str] = field(default_factory=list)
    loads: list[dict[str, Any]] = field(default_factory=list)

    def counted(self, setup_ms: int) -> float:
        """The LCP held to the budget: the phone's with the connection setup added."""
        return self.lcp + (setup_ms if self.profile == "phone" else 0)

    def holds(self, setup_ms: int, budget_ms: int = BUDGET_MS) -> bool:
        return self.counted(setup_ms) < budget_ms


def summarize(name: str, url: str, profile: str, loads: list[dict[str, Any]]) -> Result:
    """The median of each figure over the loads, the worst layout shift, and every request
    any load stopped."""

    def median(key: str) -> float:
        return float(statistics.median(float(one[key]) for one in loads))

    return Result(
        name=name,
        url=url,
        profile=profile,
        fcp=median("fcp"),
        lcp=median("lcp"),
        ttfb=median("ttfb"),
        load=median("load"),
        cls=max(float(one["cls"]) for one in loads),
        kb=median("kb"),
        requests=median("requests"),
        blocked=[stopped for one in loads for stopped in one.get("blocked", [])],
        loads=loads,
    )


def guard(blocked: list[str], site: str) -> Any:
    """A route handler that lets a GET through and aborts anything else, writing it down."""

    def handle(route: Any, request: Any) -> Any:
        if request.method != "GET":
            blocked.append(f"{request.method} {request.url.replace(site, '')}")
            return route.abort()
        return route.continue_()

    return handle


def load(browser: Any, site: str, url: str, profile: str) -> dict[str, Any]:
    """One cold load of one page on one profile."""
    phone = profile == "phone"
    context = browser.new_context(
        viewport={"width": 412, "height": 823} if phone else {"width": 1440, "height": 900},
        is_mobile=phone,
        has_touch=phone,
        user_agent=AGENTS[profile],
    )
    blocked: list[str] = []
    context.route("**/*", guard(blocked, site))
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    if phone:
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        cdp.send("Network.emulateNetworkConditions", SLOW_4G)
    page.add_init_script(OBSERVE)
    try:
        page.goto(site + url, wait_until="load", timeout=120_000)
        # LCP settles after load; a phone at 4× is given longer to say its last.
        page.wait_for_timeout(5000 if phone else 2000)
        got: dict[str, Any] = page.evaluate(COLLECT)
    finally:
        context.close()
    got["blocked"] = blocked
    return got


def line(result: Result, setup_ms: int, budget_ms: int) -> str:
    counted = result.counted(setup_ms)
    said = "holds" if result.holds(setup_ms, budget_ms) else "OVER"
    extra = f" (+{setup_ms} setup = {counted:.0f})" if result.profile == "phone" else ""
    return (
        f"{result.name:12} {result.profile:5} lcp {result.lcp:>6.0f}{extra:<22} "
        f"fcp {result.fcp:>6.0f}  ttfb {result.ttfb:>5.0f}  {result.kb:>5.0f} kB  "
        f"{result.requests:>3.0f} req  cls {result.cls:<5}  {said}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", default=SITE)
    parser.add_argument(
        "--page",
        action="append",
        default=[],
        help="a path to measure instead of the eight public pages (repeatable)",
    )
    parser.add_argument("--phone-runs", type=int, default=3)
    parser.add_argument("--desk-runs", type=int, default=2)
    parser.add_argument("--setup-ms", type=int, default=SETUP_MS)
    parser.add_argument("--budget-ms", type=int, default=BUDGET_MS)
    parser.add_argument("--json", type=Path, help="write every load here")
    args = parser.parse_args(argv)

    from playwright.sync_api import sync_playwright

    site = args.site.rstrip("/")
    pages = {path: path for path in args.page} if args.page else PAGES
    results: list[Result] = []
    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            for name, url in pages.items():
                for profile, runs in (("phone", args.phone_runs), ("desk", args.desk_runs)):
                    loads = [load(browser, site, url, profile) for _ in range(runs)]
                    result = summarize(name, url, profile, loads)
                    results.append(result)
                    print(line(result, args.setup_ms, args.budget_ms), flush=True)
        finally:
            browser.close()

    stopped = [one for result in results for one in result.blocked]
    over = [
        r for r in results if r.profile == "phone" and not r.holds(args.setup_ms, args.budget_ms)
    ]
    print(
        f"\n§14 line 5, {args.budget_ms} ms on a phone with {args.setup_ms} ms of setup: "
        + (
            "every page holds."
            if not over
            else f"{len(over)} over: {', '.join(r.name for r in over)}."
        )
    )
    print(f"Requests stopped for not being a GET: {len(stopped)}.")
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "site": site,
                    "budget_ms": args.budget_ms,
                    "setup_ms": args.setup_ms,
                    "results": [r.__dict__ for r in results],
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main())
