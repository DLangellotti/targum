"""scripts/speed_pass.py, without a network (targum-internal#551).

The pass loads the live site, so what is pinned here is what it decides and what it
promises: only GETs leave, its loads never reach the visitor count, the median is the
median, and a phone page is held to §14's 1.5 s with the connection setup added.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from targum.visits import BOTS

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "speed_pass.py"


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("speed_pass", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # A dataclass looks its module up by name while it is built.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Route:
    def __init__(self) -> None:
        self.did = ""

    def abort(self) -> None:
        self.did = "abort"

    def continue_(self) -> None:
        self.did = "continue"


class Request:
    def __init__(self, method: str, url: str) -> None:
        self.method = method
        self.url = url


def test_only_a_get_leaves() -> None:
    speed = load_script()
    blocked: list[str] = []
    handle = speed.guard(blocked, "https://targum.page")
    for method, expect in (("GET", "continue"), ("POST", "abort"), ("PUT", "abort")):
        route = Route()
        handle(route, Request(method, "https://targum.page/sync"))
        assert route.did == expect, method
    assert blocked == ["POST /sync", "PUT /sync"]


def test_its_loads_are_never_counted_as_visitors() -> None:
    speed = load_script()
    for agent in speed.AGENTS.values():
        assert agent.endswith(speed.TAG)
        assert BOTS.search(agent), agent


def figures(lcp: float | None, **more: Any) -> dict[str, Any]:
    return {"fcp": 900, "lcp": lcp, "load": 1200, "cls": 0.0, "kb": 90, "requests": 1, **more}


def test_a_page_is_the_median_of_its_loads() -> None:
    speed = load_script()
    loads = [
        figures(1000),
        figures(1400, cls=0.02),
        figures(1200, fcp=990, blocked=["POST /events"]),
    ]
    result = speed.summarize("ruth", "/library/ruth", "phone", loads)
    assert (result.lcp, result.fcp) == (1200, 900)
    assert result.cls == 0.02, "the worst shift, not the middle one"
    assert result.blocked == ["POST /events"]
    assert not hasattr(result, "ttfb"), "DevTools' latency is not in responseStart"


def test_the_verdict_is_the_measured_lcp_and_the_margin_only_warns() -> None:
    speed = load_script()
    assert (speed.BUDGET_MS, speed.SETUP_MS, speed.MARGIN_MS) == (1500, 0, 450)
    phone = speed.summarize("x", "/", "phone", [figures(1100)])
    desk = speed.summarize("x", "/", "desk", [figures(1100)])
    # 1100 holds; with the 450 ms margin it would be 1550, so it is near, not over.
    assert phone.holds(speed.SETUP_MS) and phone.near(speed.MARGIN_MS)
    said = speed.line(phone, speed.SETUP_MS, speed.BUDGET_MS)
    assert "near" in said and "OVER" not in said and "1550" in said
    # A desk is not on a phone's network: no margin, never near.
    assert desk.holds(speed.SETUP_MS) and not desk.near(speed.MARGIN_MS)
    assert "holds" in speed.line(desk, speed.SETUP_MS, speed.BUDGET_MS)
    # A setup asked for is added to the verdict.
    assert not phone.holds(450)
    over = speed.summarize("x", "/", "phone", [figures(1600)])
    assert "OVER" in speed.line(over, speed.SETUP_MS, speed.BUDGET_MS)


def test_a_page_with_no_lcp_says_so_and_does_not_hold() -> None:
    speed = load_script()
    blank = speed.summarize("x", "/", "phone", [figures(None), figures(None)])
    assert blank.lcp is None
    assert not blank.holds(speed.SETUP_MS)
    said = speed.line(blank, speed.SETUP_MS, speed.BUDGET_MS)
    assert "no LCP" in said and "holds" not in said and " 0 " not in said
    # One load that painted is enough to have a figure.
    some = speed.summarize("x", "/", "phone", [figures(None), figures(1300)])
    assert some.lcp == 1300


def test_the_sign_out_never_leaves_whatever_its_method() -> None:
    # Signing out empties a test account (deploy/README.md, "A test account").
    speed = load_script()
    blocked: list[str] = []
    handle = speed.guard(blocked, "https://targum.page")
    route = Route()
    handle(route, Request("GET", "https://targum.page/account/sign-out"))
    assert route.did == "abort"
    assert blocked == ["GET /account/sign-out"]


def test_a_signed_in_cold_load_is_a_first_visit_past_the_welcome(tmp_path: Path) -> None:
    import json

    speed = load_script()
    saved = tmp_path / "state.json"
    cookies = [
        {"name": "targum_session", "value": "s"},
        {"name": speed.KEPT_COOKIE, "value": "k"},
    ]
    saved.write_text(json.dumps({"cookies": cookies, "origins": []}), encoding="utf-8")
    state = speed.signed_in(saved, "https://targum.page")
    assert [one["name"] for one in state["cookies"]] == ["targum_session"]
    assert state["origins"] == [
        {"origin": "https://targum.page", "localStorage": [{"name": speed.WELCOMED, "value": "1"}]}
    ]


def test_a_signed_in_reader_is_opened_through_the_door_that_never_builds() -> None:
    speed = load_script()
    readers = [url for name, url in speed.SIGNED_IN.items() if name.startswith("reader")]
    assert readers and all(url.startswith("/open/") for url in readers)


def test_why_names_the_three_causes() -> None:
    speed = load_script()
    detail = {
        "server": 120,
        "script_ms": 30,
        "style_layout_ms": 40,
        "task_ms": 300,
        "last_fetch": 2500,
        "html_kb": 600,
        "url": "/",
        "lcp_element": "p#first-home",
    }
    said = speed.why([figures(1000, detail=detail)])
    assert "server 120" in said and "script 30" in said and "last fetch 2500" in said
    assert "p#first-home" in said


def test_the_sign_in_lets_only_its_own_press_through() -> None:
    speed = load_script()
    blocked: list[str] = []
    handle = speed.entering(blocked, "https://targum.page")
    for method, url, expect in (
        ("POST", "https://targum.page/account/enter", "continue"),
        ("POST", "https://targum.page/account/enter?lang=ru", "continue"),
        ("GET", "https://targum.page/account/enter?t=x", "continue"),
        ("POST", "https://targum.page/sync", "abort"),
        ("POST", "https://elsewhere.example/account/enter", "abort"),
        ("POST", "https://targum.page/account/sign-out", "abort"),
    ):
        route = Route()
        handle(route, Request(method, url))
        assert route.did == expect, (method, url)


def test_the_link_must_name_the_expected_address() -> None:
    speed = load_script()
    said = "Sign in as tester​@example.com"
    assert speed.heading_names(said, "Tester@example.com")
    assert not speed.heading_names(said, "reader@example.com")


def test_the_state_is_owner_only_and_never_in_the_tree(tmp_path: Path) -> None:
    speed = load_script()
    keep = tmp_path / "state.json"
    keep.write_text("old", encoding="utf-8")
    keep.chmod(0o644)
    speed.keep_state(keep, {"cookies": []})
    assert keep.stat().st_mode & 0o777 == 0o600
    assert speed.inside_tree(SCRIPT.parent / "state.json")
    assert not speed.inside_tree(tmp_path / "state.json")
