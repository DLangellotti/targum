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


# -- the weekly loop (targum-internal#484) --------------------------------------------------


def test_the_public_pages_include_the_four_drawn_as_public_since_1193() -> None:
    pages = load_script().PAGES
    for path in ("/how", "/credits", "/connect", "/aliyah"):
        assert path in pages.values()


def _speed_check(tmp_path: Path, python: str) -> tuple[Any, str]:
    """`speed_check` from weekly-run.sh, run alone in a tree whose python is `python`."""
    import re
    import subprocess

    script = (SCRIPT.parent.parent / "deploy" / "weekly-run.sh").read_text(encoding="utf-8")
    found = re.search(r"^speed_check\(\) \{\n.*?^\}\n", script, re.S | re.M)
    assert found is not None
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "speed_pass.py").write_text("")
    fake = tmp_path / ".venv" / "bin" / "python"
    fake.write_text("#!/bin/sh\n" + python)
    fake.chmod(0o755)
    run = subprocess.run(
        [
            "bash",
            "-c",
            'say() { echo "$*"; }; record() { echo "REC $*"; }\n'
            + found.group(0)
            + "speed_check; echo returned $?",
        ],
        env={"ROOT": str(tmp_path), "WEEK": "2026-w47", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    return run, run.stdout


# The fake pass finds its --json path as the argument after --json.
_WRITE_JSON = 'while [ "$1" != --json ]; do shift; done; echo "{}" > "$2"\n'


def test_the_weekly_speed_check_never_stops_the_run(tmp_path: Path) -> None:
    """A page over the budget is written down beside the issue and said in runs.log; it
    never ends the run, never reaches `die`, and never tells the box."""
    over = _WRITE_JSON + ("echo '§14 line 5, 1500 ms on a phone: 1 over, 0 with no LCP.'\nexit 1\n")
    run, said = _speed_check(tmp_path, over)
    assert run.returncode == 0 and "returned 0" in said
    assert "REC speed: 1 over, 0 with no LCP." in said
    assert (tmp_path / "targum-out" / "weekly" / "speed" / "2026-w47.txt").exists()


def test_a_weekly_pass_that_could_not_run_says_so(tmp_path: Path) -> None:
    run, said = _speed_check(tmp_path, "echo no browser >&2\nexit 1\n")
    assert "returned 0" in said
    assert "REC speed: the pass could not run (exit 1)" in said


def test_a_weekly_pass_that_holds_says_so(tmp_path: Path) -> None:
    run, said = _speed_check(tmp_path, _WRITE_JSON + "exit 0\n")
    assert "REC speed: every public page holds" in said


def test_the_weekly_speed_check_comes_after_the_mail_and_can_be_left_out() -> None:
    script = (SCRIPT.parent.parent / "deploy" / "weekly-run.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))
    assert code.index("targum weekly announce") < code.index("\nspeed_check\n")
    assert code.index("\nspeed_check\n") < code.index('if [ -n "$FAILED" ]')
    body = code[code.index("speed_check() {") : code.index("\nspeed_check\n")]
    assert "die" not in body and "tell_the_box" not in body
    assert "TARGUM_WEEKLY_SPEED" in body
