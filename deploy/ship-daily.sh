#!/usr/bin/env bash
# Put the built daily-learning window on the box.
#
#   TARGUM_HOST=root@targum.page ./deploy/ship-daily.sh
#
# Same division as the parasha and the weekly: built on a laptop, read on a box. A day is
# cut from the Tanakh and the Mishnah on the local shelf, and neither travels in the
# wheel. This only carries what is already built — it spends nothing and builds nothing.
# Run `targum daily build` first.
#
# Unlike the parasha this wants running nightly, and that is the whole difference between
# the two. The parasha's corpus is fifty-four readings that are the same fifty-four every
# year, so shipping it is about moving a pointer. A cycle is two thousand days of which
# fourteen are built, and the window rolls: yesterday's page is still wanted, next
# fortnight's is not there yet, and a box that is a month stale is a box serving a page
# that says "today" over the wrong reading. `--delete` is what takes the fallen-out days
# away, and it is safe because the local window is the whole truth about what should be
# there.
set -euo pipefail

HOST="${TARGUM_HOST:?set TARGUM_HOST=user@box}"
REMOTE="${TARGUM_REMOTE_DAILY:-/var/lib/targum/targums/parasha/daily}"
DOMAIN="${DOMAIN:-targum.page}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCAL="${TARGUM_DAILY_DIR:-$ROOT/targum-out/parasha/daily}"
INDEX="$LOCAL/index.json"
[ -f "$INDEX" ] || { echo "no index at $INDEX — run targum daily build" >&2; exit 1; }
[ -d "$LOCAL/read" ] || { echo "no readers at $LOCAL/read — run targum daily build" >&2; exit 1; }

# What the index says was built, asked of the index rather than of the directory: a
# folder on disk proves a build started, not that the day came out whole.
DAYS="$(
  INDEX="$INDEX" python3 - <<'PY'
import json, os
index = json.load(open(os.environ["INDEX"], encoding="utf-8"))
print(sum(len(days) for days in index.get("cycles", {}).values()))
PY
)"
[ "$DAYS" -gt 0 ] || { echo "the index lists no days" >&2; exit 1; }
echo "== $DAYS days =="

ssh "$HOST" "mkdir -p '$REMOTE/read'"

# rsync, and `--delete`, for the reason at the top: the window rolls and the days that
# have left it must leave the box too. rsync writes each file to a temporary name and
# renames it into place, so no reader is ever served half a file.
#
# `--stats` rather than `--info=stats1`: macOS ships openrsync claiming rsync 2.6.9, which
# predates --info by a decade and exits 1 on it. This runs from a laptop, so 2.6.9 is the
# floor, and every flag here has to exist in it.
echo "== copying =="
rsync -a --delete --stats "$LOCAL/read/" "$HOST:$REMOTE/read/" | tail -4

# The index last, always: it is what makes a day exist as far as the server is concerned.
# Written to a neighbouring name and renamed, so the server never reads a half-written one.
echo "== index =="
scp -q "$INDEX" "$HOST:$REMOTE/index.json.new"
ssh "$HOST" "mv '$REMOTE/index.json.new' '$REMOTE/index.json'"

# The learning calendar, so a box that cannot reach Hebcal still knows what day it is on.
if [ -d "$LOCAL/../daily" ] && ls "$LOCAL"/*.json >/dev/null 2>&1; then
  rsync -a "$LOCAL"/*.json "$HOST:$REMOTE/" 2>/dev/null || true
fi

# Handed to the service: everything above arrived as root, and the service reads it as
# targum. The daily corpus sits inside the parasha's directory on purpose — `daily/build`
# roots itself there — so this is the same tree the parasha's ship already chowns.
ssh "$HOST" "chown -R targum:targum '$REMOTE'"
ssh "$HOST" "systemctl restart targum"

echo "== check =="
for attempt in $(seq 1 20); do
  curl -fsS --max-time 5 "https://$DOMAIN/health" 2>/dev/null | grep -q '"ok": *true' && break
  sleep 2
done
for route in mishna-yomi nach-yomi tanakh-yomi tehillim; do
  code="$(curl -s -o /dev/null -w '%{http_code}' -L "https://$DOMAIN/$route")"
  echo "   /$route $code"
done
echo
echo "Out. Run this nightly: the window rolls, and a stale box says \"today\" over the wrong day."
