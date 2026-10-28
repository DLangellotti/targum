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


def test_a_page_is_the_median_of_its_loads() -> None:
    speed = load_script()
    loads = [
        {"fcp": 900, "lcp": 1000, "ttfb": 300, "load": 1100, "cls": 0.0, "kb": 90, "requests": 1},
        {"fcp": 950, "lcp": 1400, "ttfb": 320, "load": 1500, "cls": 0.02, "kb": 90, "requests": 1},
        {
            "fcp": 990,
            "lcp": 1200,
            "ttfb": 340,
            "load": 1300,
            "cls": 0.0,
            "kb": 91,
            "requests": 1,
            "blocked": ["POST /events"],
        },
    ]
    result = speed.summarize("ruth", "/library/ruth", "phone", loads)
    assert (result.lcp, result.fcp, result.ttfb) == (1200, 950, 320)
    assert result.cls == 0.02, "the worst shift, not the middle one"
    assert result.blocked == ["POST /events"]


def test_a_phone_page_is_held_to_the_budget_with_its_setup() -> None:
    speed = load_script()
    loads = [
        {"fcp": 1000, "lcp": 1100, "ttfb": 300, "load": 1200, "cls": 0, "kb": 90, "requests": 1}
    ]
    phone = speed.summarize("x", "/", "phone", loads)
    desk = speed.summarize("x", "/", "desk", loads)
    assert speed.BUDGET_MS == 1500
    # 1100 measured is under the line; with 450 ms of setup it is over.
    assert phone.holds(0) and not phone.holds(speed.SETUP_MS)
    # A desk is not on a phone's network, so nothing is added.
    assert desk.holds(speed.SETUP_MS)
    assert "OVER" in speed.line(phone, speed.SETUP_MS, speed.BUDGET_MS)
    assert "holds" in speed.line(desk, speed.SETUP_MS, speed.BUDGET_MS)
