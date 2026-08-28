"""How much has landed lately, read out of the repository itself.

targum is under construction and the page says so. What it shows besides is the work:
thirty days of commits, which is the one claim about the state of the thing that cannot
be written into being. The page described itself at length once — what it does, what had
shipped, what it could not do yet — and none of that was what somebody arriving early
needs to be told.

Two places this runs, and they can see different things. Here there is a repository and
`git log` answers. On the box there is a wheel and no repository at all, so the counts
are written down at build time by `stamp()` and read back out of the package — which is
why the page names the day its thirty days end on rather than saying "today" about
numbers that were true when the wheel was built. Where there is neither, every function
returns empty rather than raising and the page renders without the calendar. Nothing
about the product depends on any of it working.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# Thirty, not ninety. Ninety days of mostly-empty squares says "abandoned" about a
# project that is three days old; it earns the longer window by living long enough.
DAYS = 30

#: What `stamp()` writes and a wheel carries. Beside the code rather than in the build
#: directory, because it has to survive being installed: `pyproject.toml` names it under
#: `artifacts` so hatchling packs it despite `.gitignore`, which is where it belongs —
#: it is built, not written, and a stamp committed to the repository would be one more
#: thing to remember to refresh.
STAMP = Path(__file__).with_name("activity.json")


@dataclass
class Work:
    """Everything the page shows. Empty when there is nothing to read it out of."""

    days: list[tuple[str, int]] = field(default_factory=list)

    @property
    def commits(self) -> int:
        return sum(count for _, count in self.days)

    @property
    def busiest(self) -> int:
        return max((count for _, count in self.days), default=0)

    @property
    def through(self) -> str:
        """The last day counted, said the way a person would say it.

        The page carries this because the numbers can be a fortnight old: a wheel is
        stamped when it is built and serves that stamp until the next deploy. "In the
        30 days to 26 August" is true whenever it is read; "in the last 30 days" is
        true for about a day.
        """
        if not self.days:
            return ""
        return date.fromisoformat(self.days[-1][0]).strftime("%-d %B")


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _git(*args: str) -> str:
    if not (_root() / ".git").exists():
        return ""
    try:
        done = subprocess.run(
            ["git", "-C", str(_root()), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def _from_git(today: date | None = None) -> Work:
    """The last thirty days as the repository has them. Empty where there is none."""
    today = today or date.today()
    since = today - timedelta(days=DAYS - 1)
    log = _git("log", f"--since={since.isoformat()}", "--date=short", "--pretty=%ad")
    if not log.strip():
        return Work()

    per_day: Counter[str] = Counter(when for when in log.split() if when)
    return Work(
        days=[
            (day.isoformat(), per_day.get(day.isoformat(), 0))
            for day in (since + timedelta(days=n) for n in range(DAYS))
        ]
    )


def _from_stamp() -> Work:
    """What was written down when the wheel was built."""
    try:
        raw = json.loads(STAMP.read_text(encoding="utf-8"))
        days = [(str(day), int(count)) for day, count in raw["days"]]
    except (OSError, ValueError, TypeError, KeyError):
        return Work()
    return Work(days=days)


def work(today: date | None = None) -> Work:
    """How much has landed lately, day by day.

    The repository wherever there is one, so what a developer sees is today's answer and
    not the last build's. Asked of the repository's presence rather than of what the log
    returned: a genuinely quiet month answers nothing either, and falling back to a stamp
    there would print a fortnight-old number over a real and honest zero.
    """
    if (_root() / ".git").exists():
        return _from_git(today)
    return _from_stamp()


def stamp(today: date | None = None) -> Path | None:
    """Write the counts down for a build that will run without a repository.

    Called by `deploy/deploy.sh` between the checks and `uv build`. Answers the path it
    wrote, or None where there was no repository to read — in which case the wheel ships
    without a stamp and the page is the notice and the link, which is honest.
    """
    found = _from_git(today)
    if not found.days:
        return None
    STAMP.write_text(
        json.dumps({"days": [list(day) for day in found.days]}, indent=1) + "\n",
        encoding="utf-8",
    )
    return STAMP
