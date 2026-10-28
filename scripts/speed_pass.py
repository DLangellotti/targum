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

The verdict is on the measured LCP. "Slow 4G"'s 562.5 ms is Lighthouse's 150 ms round trip
× 3.75, and that factor is DevTools' own allowance for what applied throttling cannot
slow (DNS, TCP and TLS among it), so adding a setup on top would count it twice. Whether
the allowance is enough on a real first visit is not settled (builder-3's pass,
2026-10-28), so each phone line also prints the LCP with a 450 ms margin and says "near"
when that one is over: a warning, never the verdict. `--setup-ms` still adds a setup to
the verdict for a run that wants it; it is 0 by default. A page whose loads record no LCP
says "no LCP" and fails the run, since nothing was shown to have been useful.

There is no time-to-first-byte column: DevTools puts its emulated latency into
`responseEnd`, not `responseStart`, so a throttled phone's first byte read as a few
milliseconds (qa on targum#973).

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
#: Added to the phone's LCP before the verdict; 0, since Slow 4G's latency already stands in
#: for the connection's setup (qa on targum#973).
SETUP_MS = 0
#: The warning margin printed beside each phone LCP: three round trips at Lighthouse's
#: 150 ms, in case DevTools' allowance falls short on a real first visit.
MARGIN_MS = 450
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
window.__lcp = null;
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
    fcp: Math.round(fcp), lcp: window.__lcp === null ? null : Math.round(window.__lcp),
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
    #: None when no load recorded a largest contentful paint.
    lcp: float | None
    load: float
    cls: float
    kb: float
    requests: float
    blocked: list[str] = field(default_factory=list)
    loads: list[dict[str, Any]] = field(default_factory=list)

    def counted(self, setup_ms: int) -> float | None:
        """The LCP held to the budget: the phone's with any setup added; None with no LCP."""
        if self.lcp is None:
            return None
        return self.lcp + (setup_ms if self.profile == "phone" else 0)

    def holds(self, setup_ms: int, budget_ms: int = BUDGET_MS) -> bool:
        """Under the budget. A page with no LCP does not hold: nothing showed it useful."""
        counted = self.counted(setup_ms)
        return counted is not None and counted < budget_ms

    def near(self, margin_ms: int, budget_ms: int = BUDGET_MS) -> bool:
        """A phone page under the budget measured, and over it with the margin added."""
        return (
            self.profile == "phone"
            and self.lcp is not None
            and self.lcp < budget_ms <= self.lcp + margin_ms
        )


def summarize(name: str, url: str, profile: str, loads: list[dict[str, Any]]) -> Result:
    """The median of each figure over the loads, the worst layout shift, and every request
    any load stopped."""

    def median(key: str) -> float:
        return float(statistics.median(float(one[key]) for one in loads))

    painted = [float(one["lcp"]) for one in loads if one.get("lcp") is not None]

    return Result(
        name=name,
        url=url,
        profile=profile,
        fcp=median("fcp"),
        lcp=float(statistics.median(painted)) if painted else None,
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


def line(result: Result, setup_ms: int, budget_ms: int, margin_ms: int = MARGIN_MS) -> str:
    if result.lcp is None:
        lcp, margin, said = f"{'no LCP':>11}", "", "no LCP"
    else:
        counted = result.counted(setup_ms) or 0.0
        lcp = f"{counted:>6.0f}" + (
            f" (+{setup_ms})" if setup_ms and result.profile == "phone" else ""
        )
        margin = f"{result.lcp + margin_ms:>6.0f}" if result.profile == "phone" else ""
        said = (
            ("near" if result.near(margin_ms, budget_ms) else "holds")
            if result.holds(setup_ms, budget_ms)
            else "OVER"
        )
    return (
        f"{result.name:12} {result.profile:5} lcp {lcp:<13} with {margin_ms} margin {margin:>6}  "
        f"fcp {result.fcp:>6.0f}  {result.kb:>5.0f} kB  {result.requests:>3.0f} req  "
        f"cls {result.cls:<5}  {said}"
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
    parser.add_argument(
        "--setup-ms", type=int, default=SETUP_MS, help="added to the phone's LCP for the verdict"
    )
    parser.add_argument(
        "--margin-ms", type=int, default=MARGIN_MS, help="the warning column; never the verdict"
    )
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
                    print(line(result, args.setup_ms, args.budget_ms, args.margin_ms), flush=True)
        finally:
            browser.close()

    stopped = [one for result in results for one in result.blocked]
    phones = [r for r in results if r.profile == "phone"]
    over = [r for r in phones if r.lcp is not None and not r.holds(args.setup_ms, args.budget_ms)]
    unpainted = [r for r in results if r.lcp is None]
    near = [r for r in phones if r.holds(args.setup_ms, args.budget_ms) and r.near(args.margin_ms)]
    said = f"{args.budget_ms} ms on a phone" + (
        f" with {args.setup_ms} ms of setup" if args.setup_ms else ""
    )
    if not over and not unpainted:
        print(f"\n§14 line 5, {said}: every page holds.")
    else:
        print(f"\n§14 line 5, {said}: {len(over)} over, {len(unpainted)} with no LCP.")
        for r in over + unpainted:
            print(f"  {r.name} ({r.profile})")
    if near:
        print(
            f"Within {args.margin_ms} ms of the line: {', '.join(r.name for r in near)} "
            "(a warning: a real first visit may cross it)."
        )
    print(f"Requests stopped for not being a GET: {len(stopped)}.")
    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "site": site,
                    "budget_ms": args.budget_ms,
                    "setup_ms": args.setup_ms,
                    "margin_ms": args.margin_ms,
                    "results": [r.__dict__ for r in results],
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    return 1 if over or unpainted else 0


if __name__ == "__main__":
    sys.exit(main())
