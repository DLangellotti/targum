"""Two faults the beta's browsers reported, run rather than read (targum-internal#668, #669).

The landing film drew its spoon's handle with `ctx.roundRect`, which Safari before 16 and
Chrome before 99 do not have, so the film threw on every frame there; it now draws the
same shape from `arcTo` where `roundRect` is missing. And `report.js` sent what is not a
fault of ours — the ResizeObserver notice, a wallet extension's complaints, an extension's
own script. The browser drops the ResizeObserver notice and extensions' errors and
promises before sending, in as few bytes as it can, since `report.js` counts against the
reader's `A_WORD_WAITS_GZ`; the wallets' wording is left to the server's `FAULT_NOISE`
(`test_tell_us.py`). Both are run in node against stubs.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

ASSETS = Path(__file__).resolve().parents[1] / "src" / "targum" / "render" / "assets"


def node(script: str) -> Any:
    done = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30, check=False
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


# -- #668: the film's rounded rectangle --------------------------------------------------


def rounded_source() -> str:
    text = (ASSETS / "landing.js").read_text(encoding="utf-8")
    # At whatever depth the film's code sits (the after-duolingo page's restructure,
    # targum-internal#676, put it one block deeper); the function ends at its own indent.
    found = re.search(r"\n( +)function rounded\(.*?\n\1}\n", text, re.S)
    assert found, "landing.js draws its rounded rectangle through one function"
    return found.group(0)


def draw_with(has_round_rect: bool) -> list[list[Any]]:
    return node(
        f"""
        const calls = [];
        const ctx = {{
          moveTo: (...a) => calls.push(["moveTo", ...a]),
          arcTo: (...a) => calls.push(["arcTo", ...a]),
          closePath: () => calls.push(["closePath"]),
        }};
        if ({json.dumps(has_round_rect)}) ctx.roundRect = (...a) => calls.push(["roundRect", ...a]);
        {rounded_source()}
        rounded(10, 20, 100, 30, 8);
        rounded(0, 0, 10, 4, 9);
        process.stdout.write(JSON.stringify(calls));
        """
    )


def test_the_film_uses_round_rect_where_the_browser_has_it() -> None:
    """Identical where `roundRect` exists: the same call with the same arguments."""
    assert draw_with(True) == [["roundRect", 10, 20, 100, 30, 8], ["roundRect", 0, 0, 10, 4, 9]]


def test_the_film_draws_the_same_shape_from_arc_to_where_it_does_not() -> None:
    """Four corners from `arcTo`, a closed path, and a radius held to half the short side
    as `roundRect` holds it."""
    calls = draw_with(False)
    assert calls[:6] == [
        ["moveTo", 18, 20],
        ["arcTo", 110, 20, 110, 50, 8],
        ["arcTo", 110, 50, 10, 50, 8],
        ["arcTo", 10, 50, 10, 20, 8],
        ["arcTo", 10, 20, 110, 20, 8],
        ["closePath"],
    ]
    assert calls[6] == ["moveTo", 2, 0] and all(c[-1] == 2 for c in calls[7:11])


def test_nothing_in_the_landing_calls_round_rect_but_the_fallback() -> None:
    text = (ASSETS / "landing.js").read_text(encoding="utf-8")
    assert text.count("ctx.roundRect(") == 1, "only `rounded` may call it, after checking"


# -- #669: what report.js does not send --------------------------------------------------

REPORT = (ASSETS / "report.js").read_text(encoding="utf-8")


def sent_for(events: list[dict[str, Any]]) -> list[str]:
    """Run `report.js` on a stub page at https://targum.test, fire `events` at it, and
    answer the messages it posted to /errors."""
    return node(
        f"""
        const vm = require("vm");
        const posted = [];
        const listeners = {{}};
        const window = {{
          addEventListener: (kind, fn) => {{ listeners[kind] = fn; }},
          fetch: (url, init) => {{
            if (url === "/errors") posted.push(JSON.parse(init.body).message);
            return Promise.resolve({{ status: 200 }});
          }},
        }};
        const sandbox = {{
          window,
          location: {{
            protocol: "https:",
            origin: "https://targum.test",
            pathname: "/",
            href: "https://targum.test/",
          }},
          document: {{ currentScript: {{ getAttribute: () => "abc" }} }},
          navigator: {{ onLine: true }},
          URL,
        }};
        vm.runInNewContext({json.dumps(REPORT)}, sandbox);
        for (const e of {json.dumps(events)}) {{
          if (e.kind === "error") {{
            listeners.error({{
              message: e.message,
              filename: e.filename || "",
              error: e.stack ? {{ stack: e.stack }} : null,
            }});
          }} else {{
            listeners.unhandledrejection({{
              reason: {{ name: "Error", message: e.message, stack: e.stack || "" }},
            }});
          }}
        }}
        process.stdout.write(JSON.stringify(posted));
        """
    )


OURS = "at paint (https://targum.test/:1457:5)"


@pytest.mark.parametrize(
    "event",
    [
        {"kind": "error", "message": "ResizeObserver loop limit exceeded"},
        {
            "kind": "error",
            "message": "ResizeObserver loop completed with undelivered notifications.",
        },
        {
            "kind": "rejection",
            "message": "Cannot read properties of undefined",
            "stack": "TypeError\n    at x (chrome-extension://abcdef/inpage.js:1:2)",
        },
        {
            "kind": "error",
            "message": "Uncaught TypeError: boom",
            "filename": "moz-extension://1234/content.js",
            "stack": "TypeError: boom\n    at y (moz-extension://1234/content.js:3:4)",
        },
    ],
)
def test_noise_is_not_sent(event: dict[str, Any]) -> None:
    assert sent_for([event]) == []


def test_a_fault_of_ours_is_still_sent() -> None:
    sent = sent_for(
        [
            {"kind": "error", "message": "ResizeObserver loop limit exceeded"},
            {
                "kind": "error",
                "message": "TypeError: ctx.roundRect is not a function",
                "filename": "https://targum.test/",
                "stack": "TypeError\n    " + OURS,
            },
        ]
    )
    assert sent == ["TypeError: ctx.roundRect is not a function"]


@pytest.mark.parametrize(
    "message",
    [
        "ReferenceError: Can't find variable: ResizeObserver",
        "ReferenceError: ResizeObserver is not defined",
        "TypeError: Failed to execute 'observe' on 'ResizeObserver': "
        "parameter 1 is not of type 'Element'.",
    ],
)
def test_a_resize_observer_fault_that_is_not_the_loop_notice_is_sent(message: str) -> None:
    """Only the loop notice is noise. A browser without ResizeObserver, or our observing
    nothing, is a fault of ours like any other (qa-claude on targum#1155)."""
    sent = sent_for(
        [
            {
                "kind": "error",
                "message": message,
                "filename": "https://targum.test/",
                "stack": "Error\n    " + OURS,
            }
        ]
    )
    assert sent == [message]


def test_a_rejection_of_ours_through_an_extension_frame_is_sent() -> None:
    """An extension that wraps `fetch` puts its frame in our stack; the rejection is still
    ours, because a frame of ours is in it."""
    sent = sent_for(
        [
            {
                "kind": "rejection",
                "message": "x is undefined",
                "stack": "TypeError: x is undefined\n    at load (https://targum.test/:900:3)"
                "\n    at async chrome-extension://abc/wrap.js:1:1",
            },
            {
                "kind": "rejection",
                "message": "wrapped",
                "stack": "TypeError: wrapped\n    at chrome-extension://abc/wrap.js:1:1"
                "\n    at load (https://targum.test/:900:3)",
            },
        ]
    )
    assert sent == ["Error: x is undefined", "Error: wrapped"]
