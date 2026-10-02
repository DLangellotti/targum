"""The mail's English as notes in a folder David keeps to hand, and back again (David,
2026-09-28: "give me a way to edit this text myself, in obsidian", and then, "put all
emails we have in another easier to access place … Targum Marketing on desktop").

Every mail targum sends is written from `src/targum/strings/en.json`, a flat map that is a
poor thing to write prose in. This lays each mail out as one Markdown note — a heading per
piece of it, the words under the heading — in `~/Desktop/targum marketing/emails`, which
any editor opens and Obsidian opens as a vault of its own, and reads the notes
back into the catalogue:

    uv run python scripts/mail_notes.py push   # write a note for each mail not yet there
    uv run python scripts/mail_notes.py pull   # take what the notes say into en.json

A mail is every key under a `mail.<name>.subject`: its subject names it. Each heading's key
rides beside it as an HTML comment, which Obsidian does not show in reading view, so a
heading can be renamed and the words still go home.

`push` never overwrites a note that is already there — that note may hold edits nobody has
pulled — unless told to with `--force`. `pull` refuses a note that drops or invents a
`{blank}`, because the blank is where targum puts a link or a name and a mail without its
link is a mail that does nothing. It changes English only: a translation made from the old
English is then stale, `tests/test_strings.py` says so, and `scripts/stamp_strings.py` is
run once the translation has been looked at again. Pull prints which those are.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import string
import sys
from collections import OrderedDict
from pathlib import Path

STRINGS = Path(__file__).resolve().parent.parent / "src" / "targum" / "strings"
#: Where the notes live unless `--dir` or `TARGUM_MAIL_NOTES` says otherwise.
VAULT = Path("~/Desktop/targum marketing/emails").expanduser()

#: Headings a person would give each piece, where the key's own last word would not do.
NAMES = {
    "subject": "Subject",
    "preheader": "Preview line (shown in the inbox after the subject)",
    "heading": "Heading",
    "lead": "Opening",
    "button": "Button",
    "reply": "Closing note",
    "why": "Footer: why they got this",
    "connector": "Claude and ChatGPT",
}

KEY = re.compile(r"<!--\s*(mail\.[a-z0-9.-]+)\s*-->")


def english() -> OrderedDict[str, str]:
    loaded: OrderedDict[str, str] = json.loads(
        (STRINGS / "en.json").read_text(encoding="utf-8"), object_pairs_hook=OrderedDict
    )
    return loaded


def mails(catalogue: dict[str, str]) -> dict[str, list[str]]:
    """Each mail's name and its keys, in catalogue order. A key goes to the longest name it
    sits under, so `mail.weekly.confirm.*` is its own mail and not the weekly's."""
    names = sorted(
        (key[len("mail.") : -len(".subject")] for key in catalogue if key.endswith(".subject")),
        key=len,
        reverse=True,
    )
    found: dict[str, list[str]] = {name: [] for name in sorted(names)}
    for key in catalogue:
        for name in names:
            if key.startswith(f"mail.{name}."):
                found[name].append(key)
                break
    return found


def title(name: str) -> str:
    return name.replace(".", " ").replace("-", " ").replace("_", " ").capitalize()


def heading(key: str, name: str) -> str:
    rest = key[len(f"mail.{name}.") :]
    return NAMES.get(rest, rest.replace(".", " ").replace("-", " ").capitalize())


def note(name: str, keys: list[str], catalogue: dict[str, str]) -> str:
    lines = [
        "---",
        f"mail: {name}",
        "---",
        f"# {title(name)} email",
        "",
        "Edit the words under each heading. Leave anything in {curly braces} exactly as it",
        "is: targum puts a link or a name there. Then ask Claude to pull the mail notes, or",
        "run `uv run python scripts/mail_notes.py pull` in the targum folder.",
        "",
    ]
    for key in keys:
        lines += [f"## {heading(key, name)}", f"<!-- {key} -->", catalogue[key], ""]
    return "\n".join(lines)


def read(path: Path) -> dict[str, str]:
    """A note's keys and their words. The words are everything under a key's comment up to
    the next heading, lines joined by a space, since a mail's pieces are single lines."""
    said: dict[str, str] = {}
    key = ""
    body: list[str] = []

    def close() -> None:
        if key:
            said[key] = " ".join(line.strip() for line in body if line.strip())

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            close()
            key, body = "", []
            continue
        found = KEY.search(line)
        if found and not key:
            key = found.group(1)
            continue
        if key:
            body.append(line)
    close()
    return said


def blanks(value: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(value) if field}


def where(given: str | None) -> Path:
    return Path(given or os.environ.get("TARGUM_MAIL_NOTES") or VAULT).expanduser()


def push(folder: Path, force: bool = False) -> list[Path]:
    catalogue = english()
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, keys in mails(catalogue).items():
        path = folder / f"{title(name)}.md"
        if path.exists() and not force:
            continue
        path.write_text(note(name, keys, catalogue), encoding="utf-8")
        written.append(path)
    return written


def pull(folder: Path) -> list[str]:
    """Take the notes' words into en.json. Returns the keys that changed; raises
    ValueError, and writes nothing, if any note would break a mail."""
    catalogue = english()
    changed: dict[str, str] = {}
    problems = []
    for path in sorted(folder.glob("*.md")):
        for key, words in read(path).items():
            if key not in catalogue:
                problems.append(f"{path.name}: {key} is not a string targum has")
            elif not words:
                problems.append(f"{path.name}: {key} is empty")
            elif blanks(words) != blanks(catalogue[key]):
                problems.append(
                    f"{path.name}: {key} must keep "
                    + (
                        ", ".join("{" + b + "}" for b in sorted(blanks(catalogue[key])))
                        or "no {blanks}"
                    )
                )
            elif words != catalogue[key]:
                changed[key] = words
    if problems:
        raise ValueError("\n".join(problems))
    if changed:
        catalogue.update(changed)
        raw = (STRINGS / "en.json").read_text(encoding="utf-8")
        text = json.dumps(catalogue, ensure_ascii=False, indent=2)
        (STRINGS / "en.json").write_text(
            text + ("\n" if raw.endswith("\n") else ""), encoding="utf-8"
        )
    return sorted(changed)


def stale(keys: list[str]) -> dict[str, list[str]]:
    """Which translations were made from English that has just changed."""
    out = {}
    for path in sorted(STRINGS.glob("*.json")):
        if path.name == "en.json":
            continue
        said = json.loads(path.read_text(encoding="utf-8"))
        behind = [key for key in keys if key in said]
        if behind:
            out[path.stem] = behind
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("action", choices=["push", "pull"])
    parser.add_argument("--dir", help=f"the notes' folder (default: {VAULT})")
    parser.add_argument("--force", action="store_true", help="push over notes already there")
    args = parser.parse_args(argv)
    folder = where(args.dir)
    if args.action == "push":
        written = push(folder, force=args.force)
        print(f"{len(written)} note(s) written to {folder}")
        for path in written:
            print(f"  {path.name}")
        return 0
    try:
        changed = pull(folder)
    except ValueError as problem:
        print(f"Nothing pulled:\n{problem}", file=sys.stderr)
        return 1
    print(f"{len(changed)} string(s) changed in en.json")
    for key in changed:
        print(f"  {key}")
    for code, keys in stale(changed).items():
        print(f"{code}: {len(keys)} translation(s) now behind the English: {', '.join(keys)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
