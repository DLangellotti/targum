"""Every main page against design.md §14's speed line, on a phone (targum-internal#484).

    PYTHONPATH=$PWD/src .venv/bin/python scripts/measure_pages.py --out <scratch-out> \\
      [--runs 3] [--json result.json] [--opened 5] [page name ...]

The profile is qa-claude's audit of 2026-10-22, the one every #484 number is quoted on:
slow 4G as Lighthouse states it (150 ms RTT, 1.6 Mbps down, 750 kbps up), a 4x slower CPU,
a 390x844 touch screen, every run cold (a new context, no cache, no `targum_kept`, so a
desk page arrives whole), and the median of three runs.

For each page it reports the bytes transferred, the first contentful paint, and the
first useful moment, against §14's 1.5 s:
- on a reader, the first working word tap (a script started before the page's own tries
  a word every 25 ms from the first byte until the word's card is drawn, as
  `measure_tap.py` does);
- everywhere else, the page's main press is visible and enabled and its scripts have
  run (DOMContentLoaded), so a press would be answered.

**It starts its own server and spends nothing.** `targum serve`'s `start()` runs in a
child process, hosted-style (accounts required, the front door, public shelves, the
connector, the indexes), with every API key taken out of its environment, a budget of
nothing, no feeds, subscriptions or mail loops, and a scratch store of its own. A test
account is signed in by minting its session in that store, so no link is mailed. Before
measuring it opens `--opened` texts from the shared shelf as that account, the way
qa-claude's account had, so home has a Continue to draw.

**`--out` must be a scratch copy, never the real `targum-out`**: a signed-in serve
rebuilds readers into its out folder when a reader changes language
(memory: serve-rebuilds-into-its-out). Make one with APFS clones, which cost no disk:

    mkdir -p /tmp/m484/out && for d in library shared thumbs parasha; do
      cp -c -R targum-out/$d /tmp/m484/out/; done

A page whose address the copy does not hold (a portion not cut, a day not cut) is
reported as missing rather than timed.

To time a server that is already running instead, pass `--base <url> --state
<storage_state.json>`; nothing is started then.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

RUNS = 3
RTT_MS = 150
DOWN_BPS = 1.6 * 1024 * 1024 / 8
UP_BPS = 750 * 1024 / 8
CPU_SLOWDOWN = 4
VIEWPORT = {"width": 390, "height": 844}
#: design.md §14.5: useful in under 1.5 s on a phone profile.
BUDGET_S = 1.5
#: Longest a page may take before a run is given up as not useful at all.
GIVE_UP_S = 45
#: The test accounts, by the language their desk is in: English, and one that reads in
#: Russian, so the Library is measured as a Russian reader meets it too.
TEST_EMAILS = {"en": "measure-484@example.test", "ru": "measure-484-ru@example.test"}

#: name, address, kind ("tap" on a reader, "ready" elsewhere), the press that makes it
#: useful, whether it is measured signed in, and as which account (`TEST_EMAILS`,
#: English unless named). `{today}` is today's date.
PAGES: list[dict[str, Any]] = [
    {
        "name": "front door",
        "path": "/",
        "kind": "ready",
        "sel": "input[name=link]",
        "signed": False,
    },
    {"name": "Library", "path": "/library", "kind": "ready", "sel": "button.band-card"},
    {
        "name": "Library (Russian)",
        "path": "/library",
        "kind": "ready",
        "sel": "button.band-card",
        "account": "ru",
    },
    {
        "name": "library reader (Ruth 1)",
        "path": "/reader/%D7%A8%D7%95%D7%AA-he/reader/sec-0001.html",
        "kind": "tap",
        "sel": ".pair .w",
    },
    {
        "name": "aliyah (Lech-Lecha 1)",
        "path": "/parasha/read/lech-lecha/reader/sec-0001.html",
        "kind": "tap",
        "sel": ".pair .w",
    },
    {
        "name": "aliyah (Ki Tavo 6)",
        "path": "/parasha/read/ki-tavo/reader/sec-0006.html",
        "kind": "tap",
        "sel": ".pair .w",
    },
    {"name": "Your targums", "path": "/", "kind": "ready", "sel": "a.try-open, a.upload-card"},
    {"name": "Words", "path": "/words", "kind": "ready", "sel": "input#search"},
    {
        "name": "Progress",
        "path": "/progress",
        "kind": "ready",
        "sel": "#library-link, #counts, #touchstones",
    },
    {"name": "account", "path": "/you", "kind": "ready", "sel": "#you-out"},
    {"name": "playlists", "path": "/playlists", "kind": "ready", "sel": "button.pl-new-card"},
    {"name": "Saved", "path": "/you/saved", "kind": "ready", "sel": "#saved-playlist"},
    {
        "name": "subscriptions",
        "path": "/?show=subscriptions",
        "kind": "ready",
        "sel": "main button.btn.tonal",
    },
    {"name": "chat", "path": "/chat", "kind": "ready", "sel": "#chat-said, #chat-new"},
    {"name": "/connect", "path": "/connect", "kind": "ready", "sel": "button.cn-copy"},
    {"name": "/parasha", "path": "/parasha", "kind": "ready", "sel": "main a.btn.filled"},
    {
        "name": "daily reading (Tanakh Yomi)",
        "path": "/tanakh-yomi/read/{today}/reader/sec-0001.html",
        "kind": "tap",
        "sel": ".pair .w",
    },
]

PROBE = """
window.__useful = null;
(function () {
  var cfg = %s;
  var dcl = false;
  document.addEventListener('DOMContentLoaded', function () { dcl = true; });
  function shown(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !el.disabled && !el.closest('[hidden]');
  }
  (function poll() {
    try {
      if (cfg.kind === 'tap') {
        var w = document.querySelector(cfg.sel);
        if (w) w.click();
        var c = document.getElementById('gloss-card');
        if (c && !c.hidden && c.getBoundingClientRect().height > 0) {
          window.__useful = performance.now(); return;
        }
      } else {
        var els = document.querySelectorAll(cfg.sel);
        for (var i = 0; i < els.length; i++) {
          if (shown(els[i]) && (dcl || document.readyState !== 'loading')) {
            window.__useful = performance.now(); return;
          }
        }
      }
    } catch (e) { window.__probeErr = String(e); }
    setTimeout(poll, 25);
  })();
})();
"""

#: What the child server must never see: anything that could spend or mail.
UNSAFE_ENV = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "TARGUM_SMTP", "OP_SERVICE")
HOSTED_FLAGS = (
    "TARGUM_FRONT_DOOR",
    "TARGUM_PUBLIC_SHELVES",
    "TARGUM_CONNECTOR",
    "TARGUM_INDEX_DAILY",
    "TARGUM_INDEX_WEEKLY",
    "TARGUM_INDEX_PARASHA",
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not any(u in k for u in UNSAFE_ENV)}
    for key in [
        k
        for k in env
        if k.startswith(("ANTHROPIC", "OPENAI", "GEMINI", "GOOGLE_", "ELEVENLABS", "VERTEX"))
    ]:
        del env[key]
    for flag in HOSTED_FLAGS:
        env[flag] = "1"
    env["HF_HUB_OFFLINE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def serve_child(out: Path, store: Path, port: int) -> None:
    """The server, in a process of its own: hosted, keyless, budget nothing, no loops."""
    from targum.serve import start

    start(
        out,
        port=port,
        open_browser=False,
        max_cost=0.0,
        budget=0.0,
        store=store,
        require_account=True,
        public_address=f"http://127.0.0.1:{port}",
    )


def sign_in(store: Path, language: str = "en") -> str:
    """A session for a test account in the scratch store, minted without a link."""
    from targum.accounts import Store

    words = Store(store)
    email = TEST_EMAILS[language]
    words.make_test_account(email)
    signed = words.sign_in_verified(email)
    if signed is None:
        raise SystemExit("Could not sign the test account in.")
    person, session = signed
    words.set_interest(person, ["everyday"])
    if language != "en":
        words.choose(person, "reading", [language])
    return session


def storage_state(cookie: str) -> dict[str, Any]:
    return {
        "cookies": [
            {
                "name": "targum_session",
                "value": cookie,
                "domain": "127.0.0.1",
                "path": "/",
                "expires": -1,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            }
        ],
        "origins": [],
    }


def _wait_up(base: str, child: subprocess.Popen[bytes]) -> None:
    deadline = time.time() + 120
    while time.time() < deadline:
        if child.poll() is not None:
            raise SystemExit("The server stopped before it answered; see its output above.")
        try:
            urllib.request.urlopen(base + "/health", timeout=2)
            return
        except urllib.error.HTTPError:
            return
        except OSError:
            time.sleep(0.5)
    raise SystemExit("The server did not answer within two minutes.")


def _exists(base: str, path: str, cookie: str) -> bool:
    req = urllib.request.Request(base + path, headers={"Cookie": f"targum_session={cookie}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.status) < 400
    except urllib.error.HTTPError as why:
        return why.code < 400
    except OSError:
        return False


def open_texts(base: str, state: dict[str, Any], out: Path, count: int) -> None:
    """Open `count` texts from the shared shelf as the account, unthrottled, so its sync
    records them and home has a Continue to draw, as qa-claude's account had."""
    if count <= 0:
        return
    from playwright.sync_api import sync_playwright

    readers = sorted(p.parent.parent.name for p in (out / "library").glob("*/reader/sec-0001.html"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(storage_state=state)  # type: ignore[arg-type]
        page = context.new_page()
        for name in readers[:count]:
            page.goto(f"{base}/reader/{name}/reader/sec-0001.html", wait_until="load")
            page.wait_for_timeout(2500)
        context.close()
        browser.close()


def measure(
    base: str,
    states: dict[str, dict[str, Any]],
    pages: list[dict[str, Any]],
    runs: int,
    debug: bool = False,
) -> list[dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    found = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for spec in pages:
            rows = []
            for _ in range(runs):
                args: dict[str, Any] = {"viewport": VIEWPORT, "has_touch": True, "is_mobile": True}
                state = states.get(spec.get("account", "en"))
                if spec.get("signed", True) and state is not None:
                    args["storage_state"] = state
                context = browser.new_context(**args)
                context.clear_cookies(name="targum_kept")  # cold: the page arrives whole
                context.add_init_script(
                    "try{localStorage.setItem('targum:welcomed','1');}catch(e){}"
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
                reqs: dict[str, dict[str, Any]] = {}

                def on_response(ev: dict[str, Any], reqs: dict[str, Any] = reqs) -> None:
                    reqs.setdefault(ev["requestId"], {})["url"] = ev["response"]["url"]

                def on_finished(ev: dict[str, Any], reqs: dict[str, Any] = reqs) -> None:
                    reqs.setdefault(ev["requestId"], {})["bytes"] = ev["encodedDataLength"]

                cdp.on("Network.responseReceived", on_response)
                cdp.on("Network.loadingFinished", on_finished)
                page.add_init_script(PROBE % json.dumps({"kind": spec["kind"], "sel": spec["sel"]}))
                errors: list[str] = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.goto(base + spec["path"], wait_until="commit")
                useful = None
                origin = None
                started = time.time()
                while time.time() - started < GIVE_UP_S:
                    try:
                        at, t0 = page.evaluate("[window.__useful, performance.timeOrigin]")
                    except Exception as why:  # noqa: BLE001 - a navigation in between
                        if debug:
                            print("    evaluate failed:", str(why)[:100], flush=True)
                        page.wait_for_timeout(50)
                        continue
                        # A page that reloads itself keeps counting from the first origin.
                    origin = origin if origin is not None else t0
                    if at is not None:
                        useful = (t0 + at - origin) / 1000
                        break
                    page.wait_for_timeout(100)
                try:
                    page.wait_for_load_state("load", timeout=60000)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(500)
                fcp = page.evaluate(
                    "(performance.getEntriesByName('first-contentful-paint')[0]||{})"
                    ".startTime||null"
                )
                context.close()
                served = {k: v for k, v in reqs.items() if str(v.get("url", "")).startswith("http")}
                rows.append(
                    {
                        "useful": useful,
                        "fcp": fcp / 1000 if fcp else None,
                        "bytes": sum(int(r.get("bytes", 0)) for r in served.values()),
                        "largest": sorted(
                            (
                                {
                                    "url": str(r.get("url", ""))[len(base) :][:120],
                                    "bytes": int(r.get("bytes", 0)),
                                }
                                for r in served.values()
                            ),
                            key=lambda r: -r["bytes"],
                        )[:12],
                        "errors": errors[:3],
                    }
                )

            def median(key: str, rows: list[dict[str, Any]] = rows) -> float | None:
                values = [r[key] for r in rows if r[key] is not None]
                return statistics.median(values) if values else None

            result = {
                "name": spec["name"],
                "path": spec["path"],
                "kind": spec["kind"],
                "bytes": median("bytes"),
                "fcp": median("fcp"),
                "useful": median("useful"),
                "runs": [{k: r[k] for k in ("useful", "fcp", "bytes")} for r in rows],
                "largest": rows[-1]["largest"],
                "errors": rows[-1]["errors"],
            }
            found.append(result)
            print(_line(result), flush=True)
        browser.close()
    return found


def _line(r: dict[str, Any]) -> str:
    if r.get("missing"):
        return f"{r['name']:<30} {'':>8}  {'':>7}  {'missing':>9}"
    useful = r["useful"]
    verdict = (
        "never"
        if useful is None
        else ("under" if useful < BUDGET_S else f"OVER +{useful - BUDGET_S:.2f}")
    )
    fcp = f"{r['fcp']:.2f} s" if r["fcp"] else "-"
    use = f"{useful:.2f} s" if useful is not None else "-"
    return f"{r['name']:<30} {(r['bytes'] or 0) / 1000:>5.0f} kB  {fcp:>7}  {use:>9}  {verdict}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("names", nargs="*", help="Pages to measure, by name; every page if none.")
    parser.add_argument("--out", type=Path, help="A scratch copy of targum-out to serve.")
    parser.add_argument("--runs", type=int, default=RUNS)
    parser.add_argument("--json", type=Path, help="Write every run and the largest requests here.")
    parser.add_argument("--opened", type=int, default=5, help="Shared texts to open first.")
    parser.add_argument("--base", help="Time a server already running at this address.")
    parser.add_argument("--state", type=Path, help="Its signed-in Playwright storage state.")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--serve-child", nargs=3, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.serve_child:
        out, store, port = args.serve_child
        serve_child(Path(out), Path(store), int(port))
        return 0

    today = date.today().isoformat()
    pages = [dict(p, path=p["path"].format(today=today)) for p in PAGES]
    if args.names:
        unknown = set(args.names) - {p["name"] for p in pages}
        if unknown:
            parser.error(f"no page named {', '.join(sorted(unknown))}")
        pages = [p for p in pages if p["name"] in args.names]

    child = None
    states: dict[str, dict[str, Any]] = {}
    if args.base:
        base = args.base.rstrip("/")
        if args.state:
            states["en"] = json.loads(args.state.read_text())
        # One account is all a running server is handed: the Russian one is left out.
        pages = [p for p in pages if p.get("account", "en") == "en"]
    else:
        if args.out is None:
            parser.error("give --out (a scratch copy of targum-out) or --base")
        out = args.out.resolve()
        if out.name == "targum-out" or (out / "p1").exists():
            parser.error(f"{out} looks like the real targum-out; serve a cp -c copy instead")
        scratch = Path(tempfile.mkdtemp(prefix="measure-pages-"))
        store = scratch / "targum.db"
        states = {code: storage_state(sign_in(store, code)) for code in TEST_EMAILS}
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        child = subprocess.Popen(
            [sys.executable, __file__, "--serve-child", str(out), str(store), str(port)],
            env=_child_env(),
            stdout=subprocess.DEVNULL if not args.debug else None,
        )
        _wait_up(base, child)
    cookie = next(
        (
            c["value"]
            for c in states.get("en", {}).get("cookies", [])
            if c["name"] == "targum_session"
        ),
        "",
    )
    try:
        if child is not None and args.out is not None:
            open_texts(base, states["en"], args.out.resolve(), args.opened)
        present, missing = [], []
        for page in pages:
            (present if _exists(base, page["path"], cookie) else missing).append(page)
        print(
            f"{'page':<30} {'bytes':>8}  {'FCP':>7}  {'useful':>9}  "
            f"budget {BUDGET_S} s, median of {args.runs}",
            flush=True,
        )
        results = measure(base, states, present, args.runs, args.debug)
        for page in missing:
            results.append({"name": page["name"], "path": page["path"], "missing": True})
            print(_line(results[-1]), flush=True)
        if args.json:
            args.json.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    finally:
        if child is not None:
            child.terminate()
            child.wait(timeout=30)
    return 0


if __name__ == "__main__":
    sys.exit(main())
