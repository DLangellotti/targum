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
#
# **Every issue has a Russian edition too** (David, 2026-09-27, targum-internal#288). It
# is the same Hebrew — the same three levels the guards measured — with Russian beside it
# instead of English, built into folders of its own after `publish` has said yes. That
# order is the point: an issue the guards refuse spends nothing on Russian, and a Russian
# build that stops cannot hold back an English issue that passed. A run whose Russian
# stopped still announces and ships the English, then ends non-zero and says so; running
# it again builds only the Russian that is missing (the translation cache keeps whatever
# it already bought) and ships it. Until then a Russian subscriber is mailed in Russian
# and lands on a Russian page with the English reader in it, which is the most there is.
#
# TARGUM_WEEKLY_LANGUAGES names the editions beside English, space-separated. Unset is
# "ru"; set it empty to build English alone.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

say() { printf '== %s\n' "$*"; }
die() { printf '!! %s\n' "$*" >&2; exit 1; }

# The keys live in 1Password and nothing loads them for you — not `uv run`, not the venv's
# own python. Without them the failure reads "Could not resolve authentication method",
# which sounds like a missing key rather than an unloaded one (CLAUDE.md). So the run
# starts itself again under `op run`, which puts op.env's keys in its environment.
#
# At 07:00 on a Monday nobody is there to touch the fingerprint reader, so the scheduled
# run reads the vault as the targum-box service account, whose token is kept in the login
# keychain (the plist says how it gets there). Read-only, and the targum vault only. A
# run by hand with no such token falls back to the app's own unlock.
if [ -z "${TARGUM_UNDER_OP:-}" ]; then
  command -v op >/dev/null || die "no op on PATH ($PATH): brew install 1password-cli, and put /opt/homebrew/bin in the plist's PATH"
  if [ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" ] &&
    token="$(security find-generic-password -s targum-op-service-account -w 2>/dev/null)"; then
    export OP_SERVICE_ACCOUNT_TOKEN="$token"
  fi
  export TARGUM_UNDER_OP=1
  exec op run --env-file "$ROOT/op.env" -- bash "$ROOT/deploy/weekly-run.sh" "$@"
fi
[ -n "${ANTHROPIC_API_KEY:-}" ] || die "op run gave no ANTHROPIC_API_KEY: is it in op.env and the vault?"

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

# What this checkout is about to build the issue's readers with (targum-internal#350).
#
# The weekly has to run from here, because its writer is one of the gitignored modules —
# and "here" is whichever branch happens to be checked out. On 2026-09-21 that was a
# working branch fifty commits behind master, and the issue shipped with a reader built
# from it: correct, live, answering 200, and not matching any other reader on the box.
#
# Said and not fatal, for the reason `preflight`'s stale-reader count is a warning: an
# issue built from a branch is still an issue, and a run that refuses on a Monday
# morning helps nobody. A checkout level with master says nothing at all.
behind_master() {
  git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1 || return 0
  local branch behind assets
  branch="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)" || return 0
  # Whatever has already been fetched. A scheduled run is not the place to reach the
  # network, and a stale remote ref understates the gap rather than inventing one.
  behind="$(git -C "$ROOT" rev-list --count HEAD..origin/master 2>/dev/null)" || return 0
  [ -n "$behind" ] && [ "$behind" -gt 0 ] || return 0
  assets="$(git -C "$ROOT" diff --name-only HEAD origin/master -- \
    src/targum/render/assets src/targum/render/templates 2>/dev/null | wc -l | tr -d ' ')"
  echo "   building from $branch, $behind commit(s) behind origin/master"
  [ "${assets:-0}" -gt 0 ] && echo "   $assets reader asset(s) differ — this issue's readers will not match the box"
  return 0
}
behind_master

state_of() {
  WEEK="$1" "$ROOT/.venv/bin/python" - <<'PY' 2>/dev/null || echo missing
import json, os, sys
from pathlib import Path
from targum.weekly import index as weekly_index
issue = weekly_index.by_week(os.environ["WEEK"])
print(issue.state.value if issue is not None else "missing")
PY
}

# Whether every level of this issue has been built into a language. `weekly build --to`
# writes the language onto the issue only once all three have, so this is never true of
# a half-built one.
speaks() {
  WEEK="$1" LANGUAGE="$2" "$ROOT/.venv/bin/python" - <<'PY' 2>/dev/null
import os, sys
from targum.weekly import index as weekly_index
issue = weekly_index.by_week(os.environ["WEEK"])
sys.exit(0 if issue is not None and os.environ["LANGUAGE"] in issue.languages else 1)
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

# The other editions, after publish and before the mail. After publish, so an issue the
# guards refused has spent nothing on them — and the guards need nothing of their own
# here: the Hebrew is the one they just measured, and `--anyway` is not passed here any
# more than above. Before the mail, so the letters can point at a finished edition.
#
# A failure is said and carried to the end, never fatal: the English passed every guard
# and is not held back by a translation into another language. (Draft and the English
# build above stay fatal: without them there is no issue.)
MISSING=""
for language in ${TARGUM_WEEKLY_LANGUAGES-ru}; do
  [ "$language" = "en" ] && continue
  if speaks "$WEEK" "$language"; then
    continue
  fi
  say "building the three levels in $language (this spends)"
  if ! "$TARGUM" weekly build "$WEEK" --to "$language"; then
    say "the $language edition stopped; the English goes out without it"
    MISSING="$MISSING $language"
  fi
done

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
  die "$WEEK is published, and this did not finish:$FAILED${MISSING:+, and no edition in$MISSING}.
   Run this again — it picks up where it stopped and re-does nothing."
fi

if [ -n "$MISSING" ]; then
  die "$WEEK is out in English, without its edition in$MISSING: that build stopped (read what
   it said above). Subscribers who asked in it were mailed and land on the English reader.
   Run this again — it builds only what is missing, then ships it."
fi

say "$WEEK is out"
