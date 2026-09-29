# What was built: the brief for a day's lines

`/about` says targum is built in public and shows, under the calendar, what each day
was. The days are `src/targum/built.txt`. This is what a day's lines are written to,
whoever or whatever writes them. Decided with David on 2026-09-29; design.md §12 has the
entry.

## Who reads it

Peers and partners: somebody deciding whether the people behind targum know what they
are doing. They have a minute. They are not shown how clever the work was. They are shown
what changed, plainly, day after day, and they draw the conclusion themselves.

## What a day is

- **One to three lines.** The three things that day a person using targum would notice
  most. A day with forty changes still has three lines; choosing is the work.
- **What changed, not how.** "A verb's card shows its full conjugation." Not what was
  refactored, measured, renamed or fixed on the way.
- **Present tense, no "we", no adjectives doing the selling.** One sentence, two at most,
  110 characters at most, ending in a full stop. design.md §6 holds: targum is lowercase,
  and there is no exclamation mark and no emoji.
- **In the reader's words.** "The Library", "a word's card", "conversation". Not "the
  shelf", "the desk", "scenes", "the box", "the ledger", "a rung".
- **Work that is built but not switched on is said like anything else.**
- **A measurement may be said when it is the outcome**, in words a stranger follows:
  "Every measured score has a floor, and a change that falls below it is refused."
- **A quiet day has no entry.** Nothing is written to fill a date.

## What the log does not say

Two subjects, and the workings:

1. **The back office.** Servers, copies of the data, keys, who is let in and how, how
   visitors are counted, what anything costs to run.
2. **Where a text comes from.** What is in the Library may be said. Its sources, the
   terms they are under, and how they are found may not, and neither may the names of
   the places.
3. **The workings.** No code, file, flag or issue number, and no word only the people
   building it use.

`about.refused()` holds the words, in `UNSAID`. It is asked by `tests/test_about.py` over
every line in the file, and again by the page over every line it is about to draw. **A
line the guard refuses is rewritten or left out. The guard is never loosened to let a
line through**: a word comes off the list when David takes it off.

The guard reads words and cannot read meaning. A line can pass it and still say what
should not be said. When unsure whether something belongs to either subject, leave the
line out. A missing line costs nothing.

## Writing a day

The day is the day the work reached `master`, by the clock in Israel.

```
TZ=Asia/Jerusalem git log origin/master --first-parent \
  --since="2026-09-29 00:00" --until="2026-09-29 23:59" --format=%s
```

Read the subjects, and the CHANGELOG where a subject is not enough. Add the day at the
top of `built.txt`, under the notes. Do not rewrite a day that is already there. Then:

```
PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q tests/test_about.py
```

The lines go out in a pull request of their own that changes `built.txt` and nothing
else, merged when CI is green. They reach the site with the next deploy: the page is
served from a wheel, and the wheel carries the file.
