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
import re
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

    # A commit dated after today belongs to today. Git prints the author's date in the
    # author's own timezone, and a clock three hours east of the runner's writes
    # "tomorrow" on anything committed after nine in the evening UTC. On a shallow
    # checkout that one commit is the whole log, and a window that ends today then held
    # nothing at all — the page drew no squares, and CI said so on every push made late
    # in the day from Israel.
    last = today.isoformat()
    per_day: Counter[str] = Counter(min(when, last) for when in log.split() if when)
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


# -- what was built, day by day --------------------------------------------------------
#
# The calendar says how much landed and nothing about what. `built.txt` says what, in a
# line or three a day, and it is written for somebody deciding whether the people behind
# targum know what they are doing — so it says what changed for a reader and stops.
#
# Nobody reads a day's lines before they go out (David, 2026-09-29), which is the
# weekly's arrangement and has the weekly's answer: the writer is not trusted, the guard
# is. `refused()` is asked twice, by a test over the file and by the page over every line
# it is about to draw, so a line that got past the first is still not shown.

#: Where the days are written down. Committed, unlike the stamp: these are written, not
#: built, and hatchling packs a tracked file beside the code without being asked.
BUILT = Path(__file__).with_name("built.txt")

#: How many lines a day may have, and how long one may be. A day that needs a fourth
#: line is a day nobody chose from, and a line that needs a second breath is explaining.
MOST = 3
LONGEST = 110

#: How many days the page draws, newest first. The file keeps every day; the page is
#: read by somebody with a minute, and a year of days is not a minute.
SHOWN = 90

#: What a line may not say, by the reason it may not. Each is a pattern read from the
#: start of a word, in any case, so a stem catches its family: `licen` is licence,
#: license and licensing. **To let a word through, take it out here and nowhere else.**
UNSAID: dict[str, tuple[str, ...]] = {
    # The log is what changed, not how the change was made.
    "how it is made": (
        r"commit",
        r"merge",
        r"refactor",
        r"deploy",
        r"pull request",
        r"repo\b",
        r"repositor",
        r"worktree",
        r"regex",
        r"endpoint",
        r"database",
        r"cache",
        r"payload",
        r"schema",
        r"token",
        r"lemma",
        r"eval\b",
        r"evals\b",
        r"benchmark",
        r"pipeline",
        r"feature flag",
        r"unit test",
    ),
    # Servers, copies, who is let in and how they are counted (David, 2026-09-29).
    "the back office": (
        r"back ?office",
        r"back ?up",
        r"server",
        r"firewall",
        r"ssh\b",
        r"password",
        r"secret",
        r"credential",
        r"1password",
        r"vault",
        r"api key",
        r"admin",
        r"wait ?list",
        r"waiting list",
        r"visitor",
        r"access log",
        r"rate limit",
        r"harden",
        r"security",
        r"vulnerab",
        r"attack",
        r"abuse",
        r"spam",
        r"operator",
        r"invit",
        r"invoice",
        r"billing",
        r"spend\b",
        r"spending",
        r"outage",
        r"david",
    ),
    # What is in the library may be said. Where it came from, and under what terms, is
    # not (David, 2026-09-29) — so the names of the places are here with the words.
    "where a text comes from": (
        r"licen[cs]",
        r"copyright",
        r"public domain",
        r"creative commons",
        r"cc[ -]by",
        r"scrap(e|ing)",
        r"crawl",
        r"dataset",
        r"corpus",
        r"corpora",
        r"treebank",
        r"publisher",
        r"permission",
        r"rights\b",
        r"sefaria",
        r"wikisource",
        r"wikidata",
        r"wiktionary",
        r"wikipedia",
        r"storyweaver",
        r"global voices",
        r"global storybooks",
        r"tatoeba",
        r"flores",
        r"ntrex",
        r"heq\b",
        r"dicta",
        r"stanza",
        r"morphalou",
        r"iahlt",
        r"knesset",
        r"ben[- ]yehuda",
        r"jps\b",
        r"pealim",
        r"nakdimon",
        r"whisper",
        r"labse",
        r"universal dependencies",
        r"youtube",
        r"instagram",
        r"tiktok",
        r"facebook",
        r"yt-dlp",
    ),
}

_UNSAID = {
    why: re.compile(r"(?<![A-Za-z])(?:" + "|".join(words) + r")", re.IGNORECASE)
    for why, words in UNSAID.items()
}

#: The marks of something copied out of the work rather than written about it: code in
#: backticks, an issue's number, a name with an underscore in it, a file, an address, a
#: sum of money, and the abbreviations only the people building it say aloud.
_WORKINGS = re.compile(
    r"[`$_]|#\d|://|\.(?:py|js|json|css|sh|md|txt)\b|\b(?:PR|CI|API|JSON|SQL|CLI|URL|HTML|CSS|SDK)\b"
)


def refused(line: str) -> str:
    """Why a line may not be shown, or nothing where it may.

    Design.md §6 first — the name lowercase, no exclamation mark, no emoji, and short —
    then the workings, then the three things the log keeps to itself. The reason is a
    sentence for whoever wrote the line, and it names the word, because "refused" alone
    sends them to read the whole list.
    """
    if not line.strip():
        return "it is empty"
    if len(line) > LONGEST:
        return f"it is {len(line)} characters, and a line is {LONGEST} at most"
    if not line.endswith("."):
        return "it does not end in a full stop"
    if "!" in line:
        return "it has an exclamation mark (design.md §6)"
    if "Targum" in line:
        return "the name is lowercase, even at the start of a sentence (design.md §6)"
    if any(ord(char) >= 0x1F000 or 0x2600 <= ord(char) <= 0x27BF for char in line):
        return "it has an emoji (design.md §6)"
    found = _WORKINGS.search(line)
    if found:
        return f"{found.group(0)!r} is the workings, not what changed"
    for why, pattern in _UNSAID.items():
        found = pattern.search(line)
        if found:
            return f"{found.group(0)!r} is {why}, which the log does not say"
    return ""


def written() -> list[tuple[str, list[str]]]:
    """Every day in the file as it was written, newest first, nothing taken out.

    What the test reads. A day is its date on a line of its own and its lines under it,
    and a blank line ends it; a line starting `#` is a note to whoever edits the file.
    A block that does not open on a date is left out rather than guessed at.
    """
    try:
        text = BUILT.read_text(encoding="utf-8")
    except OSError:
        return []
    days: dict[str, list[str]] = {}
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines()]
        lines = [line for line in lines if line and not line.startswith("#")]
        if not lines:
            continue
        try:
            day = date.fromisoformat(lines[0]).isoformat()
        except ValueError:
            continue
        days.setdefault(day, []).extend(lines[1:])
    return sorted(days.items(), reverse=True)


def built() -> list[tuple[date, list[str]]]:
    """What the page draws: the newest days, and only the lines that may be shown.

    A refused line is dropped and the day keeps its others; a day left with nothing is
    not drawn. The page never fails over this and never shows what it should not, which
    are the two things it is for.
    """
    shown = []
    for day, lines in written():
        kept = [line for line in lines if not refused(line)][:MOST]
        if kept:
            shown.append((date.fromisoformat(day), kept))
    return shown[:SHOWN]
