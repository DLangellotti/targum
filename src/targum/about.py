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

# Paths to the part of the product a reader would recognise. Ordered, because the first
# match wins and the narrower patterns have to come first.
AREAS: tuple[tuple[str, str], ...] = (
    ("src/targum/render/", "The reader and its pages"),
    ("src/targum/translate/", "Translation"),
    ("src/targum/annotate/", "Words and their meanings"),
    ("src/targum/vocalize/", "Vowel points"),
    ("src/targum/align/", "Matching published translations"),
    ("src/targum/ingest/", "Reading a text in"),
    ("src/targum/accounts.py", "Accounts"),
    ("src/targum/serve.py", "Serving it"),
    ("src/targum/mail.py", "Accounts"),
    ("src/targum/usage.py", "Counting what it costs"),
    ("src/targum/catalogue.py", "The catalogue"),
    ("src/targum/cli.py", "The command line"),
    ("tests/", "Tests"),
    ("docs/", "Writing it down"),
    ("src/targum/", "The pipeline"),
)


@dataclass
class Work:
    """Everything the page shows. Empty when there is no repository to read."""

    days: list[tuple[str, int]] = field(default_factory=list)
    commits: int = 0
    shipping_days: int = 0
    areas: list[tuple[str, int]] = field(default_factory=list)
    weeks: list[tuple[str, int, list[str]]] = field(default_factory=list)

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
    return "Everything else"


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
        weeks=_weeks(subjects),
    )


def _weeks(subjects: list[tuple[str, str]]) -> list[tuple[str, int, list[str]]]:
    """Commits grouped by the week they landed in, newest first.

    Subjects are shown as they were written. They are one line each by house style,
    which is what makes them readable as a list rather than needing a summary.
    """
    grouped: dict[date, list[str]] = {}
    for when, subject in subjects:
        try:
            day = date.fromisoformat(when)
        except ValueError:
            continue
        monday = day - timedelta(days=day.weekday())
        grouped.setdefault(monday, []).append(subject)

    out: list[tuple[str, int, list[str]]] = []
    for monday in sorted(grouped, reverse=True):
        landed = grouped[monday]
        # Merge commits and formatting passes are noise on a page about what changed.
        worth = [s for s in dict.fromkeys(landed) if not s.lower().startswith(("merge ", "format"))]
        out.append((monday.strftime("%-d %B"), len(landed), worth))
    return out
