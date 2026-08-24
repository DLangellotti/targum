"""What has been built, read out of the repository itself.

targum is open source, so the honest way to say what state it is in is to show the work
rather than describe it. This reads `git log` and turns it into the three things a
stranger actually wants: how much is happening, where, and what changed lately.

It reads the repository targum is running from. Installed from a wheel there is no
repository and no history, and that is a fine thing to have nothing to say about: every
function here returns empty rather than raising, and the page renders without the
section. Nothing about the product depends on this working.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# Thirty, not ninety. Ninety days of mostly-empty squares says "abandoned" about a
# project that is three days old; it earns the longer window by living long enough.
DAYS = 30

# Where the work landed, named as the paths themselves. They were prose once — "The
# reader and its pages", "Words and their meanings" — which read as a description of a
# product rather than of a repository, and gave a reader nothing they could go and open.
# Ordered, because the first match wins and the narrower patterns have to come first.
AREAS: tuple[tuple[str, str], ...] = (
    ("src/targum/render/", "render/"),
    ("src/targum/translate/", "translate/"),
    ("src/targum/annotate/", "annotate/"),
    ("src/targum/vocalize/", "vocalize/"),
    ("src/targum/align/", "align/"),
    ("src/targum/segment/", "segment/"),
    ("src/targum/ingest/", "ingest/"),
    ("src/targum/serve.py", "serve.py"),
    ("src/targum/accounts.py", "accounts.py"),
    ("src/targum/catalogue.py", "catalogue.py"),
    ("src/targum/pipeline.py", "pipeline.py"),
    ("src/targum/cli.py", "cli.py"),
    ("tests/", "tests/"),
    ("docs/", "docs/"),
    ("src/targum/", "src/targum/"),
)

# Enough to show what is being worked on. The rest is a click away, and a page that
# lists every commit of the last month is a changelog nobody scrolls.
RECENT = 10


@dataclass
class Work:
    """Everything the page shows. Empty when there is no repository to read."""

    days: list[tuple[str, int]] = field(default_factory=list)
    commits: int = 0
    shipping_days: int = 0
    areas: list[tuple[str, int]] = field(default_factory=list)
    recent: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def busiest(self) -> int:
        return max((count for _, count in self.days), default=0)


def _git(*args: str) -> str:
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return ""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def _area(path: str) -> str:
    for prefix, name in AREAS:
        if path.startswith(prefix):
            return name
    return "other"


def work(today: date | None = None) -> Work:
    """Read the last thirty days out of the repository."""
    today = today or date.today()
    since = today - timedelta(days=DAYS - 1)
    log = _git("log", f"--since={since.isoformat()}", "--date=short", "--pretty=%ad\t%s")
    if not log.strip():
        return Work()

    per_day: Counter[str] = Counter()
    subjects: list[tuple[str, str]] = []
    for line in log.splitlines():
        when, _, subject = line.partition("\t")
        if not when:
            continue
        per_day[when] += 1
        subjects.append((when, subject.strip()))

    days = [
        (
            (since + timedelta(days=n)).isoformat(),
            per_day.get((since + timedelta(days=n)).isoformat(), 0),
        )
        for n in range(DAYS)
    ]

    touched: Counter[str] = Counter()
    for path in _git(
        "log", f"--since={since.isoformat()}", "--name-only", "--pretty=format:"
    ).splitlines():
        if path.strip():
            touched[_area(path.strip())] += 1

    return Work(
        days=days,
        commits=sum(per_day.values()),
        shipping_days=sum(1 for _, count in days if count),
        areas=touched.most_common(8),
        recent=_recent(subjects),
    )


def _recent(subjects: list[tuple[str, str]], limit: int = RECENT) -> list[tuple[str, str, str]]:
    """The last few commit subjects, newest first: (iso date, short date, subject).

    Flat and capped. It was grouped into weeks with a count on each heading, which is
    scaffolding around ten lines of text — and the count answered a question about the
    repository that nobody had asked.
    """
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    # `git log` already hands them back newest first.
    for when, subject in subjects:
        # Merges and formatting passes are noise on a page about what changed.
        if subject.lower().startswith(("merge ", "format")) or subject in seen:
            continue
        try:
            day = date.fromisoformat(when)
        except ValueError:
            continue
        seen.add(subject)
        out.append((when, day.strftime("%-d %b"), subject))
        if len(out) == limit:
            break
    return out
