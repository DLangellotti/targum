#!/usr/bin/env bash
# Write, build, publish, announce and ship one issue of the weekly, start to finish.
#
#   ./deploy/weekly-run.sh              this week
#   ./deploy/weekly-run.sh 2026-w38     a named one
#
# The chore this removes is six commands in order, every week, each of which has to be
# remembered. What it does not remove is any of the refusals: `weekly publish` still
# stops on a level carrying somebody else's wording and on a level that missed the band
# it is labelled with, and **this never passes `--anyway`**. A run that stops has found
# something, and the right thing to do with it is look.
#
# Decided 2026-09-17: the issue goes out without anybody reading it first. What that
# costs is written down in `weekly publish`'s own docstring and in design.md; what it
# buys is an issue every week rather than an issue whenever somebody had a free evening.
#
# **Where this runs.** Here, on a laptop, from the main checkout. The half of the weekly
# that *writes* an issue is eight gitignored modules: they are not in the wheel, not on
# the box, and not in any worktree (see CLAUDE.md). A run from anywhere else gets as far
# as `draft` and stops with an import error.
#
# It is safe to run twice. Every step asks what has already happened and skips what has:
# a re-run after a failed ship ships, and does not rewrite the issue.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

say() { printf '== %s\n' "$*"; }
die() { printf '!! %s\n' "$*" >&2; exit 1; }

# The key lives in .env and nothing loads it for you — not `uv run`, not the venv's own
# python. Without it the failure reads "Could not resolve authentication method", which
# sounds like a missing key rather than an unloaded one (CLAUDE.md).
[ -f .env ] || die "no .env here, so there is no API key and draft would fail on a sentence that blames the key"
set -a
# shellcheck disable=SC1091
. ./.env
set +a
[ -n "${ANTHROPIC_API_KEY:-}" ] || die ".env has no ANTHROPIC_API_KEY"

TARGUM="${TARGUM_BIN:-$ROOT/.venv/bin/targum}"
[ -x "$TARGUM" ] || die "no targum at $TARGUM — run: uv sync --all-extras"

# The private half, checked before anything is spent rather than after. `draft` is the
# first step that would fail on it and the first step that costs money, and finding out
# afterwards is finding out too late.
[ -f "$ROOT/src/targum/weekly/write.py" ] || die \
  "this checkout has no weekly writer (src/targum/weekly/write.py). It is gitignored and
   exists only in the main clone — a worktree cannot draft an issue."

WEEK="${1:-$(date +%G-w%V)}"
say "$WEEK"

state_of() {
  WEEK="$1" "$ROOT/.venv/bin/python" - <<'PY' 2>/dev/null || echo missing
import json, os, sys
from pathlib import Path
from targum.weekly import index as weekly_index
issue = weekly_index.by_week(os.environ["WEEK"])
print(issue.state.value if issue is not None else "missing")
PY
}

STATE="$(state_of "$WEEK")"
say "it is currently: $STATE"

if [ "$STATE" = "missing" ] || [ "$STATE" = "draft" ]; then
  say "drafting (this is the step that spends)"
  "$TARGUM" weekly draft "$WEEK" || die "draft failed — nothing is published and nothing is out"
  say "building the three levels"
  "$TARGUM" weekly build "$WEEK" || die "build failed — the issue is drafted and unbuilt"
fi

if [ "$(state_of "$WEEK")" != "published" ]; then
  say "publishing"
  # No --anyway, ever. A level that missed its band or carries a source's own wording is
  # a thing to look at, and a run that waves it through is a run that publishes the one
  # issue nobody should have published.
  "$TARGUM" weekly publish "$WEEK" || die \
    "publish refused $WEEK. Read what it said: a missed band is edited in the markdown
     and redrafted, and a lifted phrase is rewritten. Neither is waved through here."
fi

# Mail and carriage are separate verbs on purpose: an issue is out whether or not either
# happened, and both are safe to run again. Neither can un-publish anything, so a failure
# here is worth saying loudly and is not worth stopping the world for.
FAILED=""

if [ -n "${TARGUM_PUBLIC_ADDRESS:-}" ]; then
  say "telling everybody who asked"
  "$TARGUM" weekly announce "$WEEK" || FAILED="$FAILED announce"
else
  say "no TARGUM_PUBLIC_ADDRESS, so nobody is being told (the issue is still out)"
fi

if [ -n "${TARGUM_HOST:-}" ]; then
  say "shipping to $TARGUM_HOST"
  # A hotel network kills this at kex_exchange_identification while the site is perfectly
  # up: the local network, not the box. The issue is built and published either way, so a
  # failed ship is re-run and loses nothing.
  ./deploy/ship-weekly.sh "$WEEK" || FAILED="$FAILED ship"
else
  say "no TARGUM_HOST, so it stays here"
fi

if [ -n "$FAILED" ]; then
  die "$WEEK is published, and this did not finish:$FAILED. Run this again — it picks up
   where it stopped and re-does nothing."
fi

say "$WEEK is out"
