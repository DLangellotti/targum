"""Date every catalogue row that has no arrival date, from the catalogue's own history.

`Entry.added` arrived with targum-internal#315, and nine hundred rows predate it. The
honest source for when a row appeared is the file it appeared in: the catalogue is private
data and lives outside the repository, but it is written by commits to `scripts/` and to
the fetchers, and its own copies through time are what this reads.

Two passes, and the second is the point:

1. **A git history, where the file has one.** Walk the commits that touched the catalogue,
   oldest first, and record the first commit in which each id appears. That is the day
   the row arrived, to the day, from evidence rather than from memory.

2. **Nothing, where it has none.** `~/.targum/catalogue.json` is not in a repository on
   this machine, so on a first run every row falls through — and the first draft of this
   dated them all from the file's modification time, which was today, which would have
   marked the entire nine-hundred-row shelf as new for a fortnight. That is not a
   fallback, it is a lie with a plausible shape.

   A row nothing can date keeps an empty `added`, which the shelf reads as "not known":
   it sorts below every dated row under Newest and carries no mark. `library.js` orders
   those among themselves by where they sit in the file, which is evidence of *order*
   and not of date, and is the most that can honestly be said about them.

So a first run here may well write nothing at all. That is the correct outcome, and the
feature turns on as rows arrive: whatever adds one stamps it.

    uv run python scripts/backfill_added.py            # say what it would do
    uv run python scripts/backfill_added.py --write    # do it

Never overwrites a date that is already there.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def from_git(path: Path) -> dict[str, str]:
    """The day each id first appears in this file's history, where it has one."""
    repo = path.parent
    try:
        commits = subprocess.run(
            ["git", "log", "--reverse", "--format=%H %cI", "--", path.name],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        ).stdout.splitlines()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {}

    first: dict[str, str] = {}
    for line in commits:
        sha, _, when = line.partition(" ")
        if not sha:
            continue
        try:
            blob = subprocess.run(
                ["git", "show", f"{sha}:{path.name}"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            ).stdout
            rows = json.loads(blob)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            continue
        day = when[:10]
        for entry in rows.get("entries", rows if isinstance(rows, list) else []):
            entry_id = entry.get("id")
            if entry_id and entry_id not in first:
                first[entry_id] = day
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write the dates back.")
    parser.add_argument(
        "--catalogue",
        type=Path,
        default=None,
        help="Which catalogue. Default: the one targum would read.",
    )
    args = parser.parse_args()

    from targum.catalogue import catalogue_path

    path = args.catalogue or catalogue_path()
    if path is None:
        print("no catalogue file to date")
        return 1
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = data["entries"] if isinstance(data, dict) else data

    dated = from_git(Path(path))

    from_history = 0
    left_alone = 0
    already = 0
    for entry in entries:
        if entry.get("added"):
            already += 1
            continue
        when = dated.get(entry.get("id", ""))
        if not when:
            # Nothing can date it, so nothing does. An empty `added` is "not known", and
            # the shelf sorts it below everything dated rather than above.
            left_alone += 1
            continue
        entry["added"] = when
        from_history += 1

    print(f"{already} already dated")
    print(f"{from_history} dated from the catalogue's history")
    print(f"{left_alone} left undated — nothing here can say when they arrived")
    if not from_history:
        print("\nnothing to write")
        return 0
    if not args.write:
        print("\nnothing written — pass --write")
        return 0

    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwritten to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
