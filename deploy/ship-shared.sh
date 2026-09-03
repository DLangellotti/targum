#!/usr/bin/env bash
# Put built readers on the box's shared shelf — what every reader is handed.
#
#   TARGUM_HOST=root@targum.page ./deploy/ship-shared.sh <folder> [folder…]
#
# The third way content reaches the box, beside ship-audio and ship-parasha, and here
# for the case neither of those covers: a text the box cannot build for itself. A
# curated video is one — `Library.prepare` refuses a YouTube address by name, so a
# catalogue row pointing at one would fail on the box every time a reader pressed
# build. So it is built on a laptop and carried, the way a recording is.
#
# Nothing here builds or spends. It carries, hands the files to the service, and stops.
#
# No --delete, ever: `targum seed` writes this same directory during a deploy, and the
# texts it puts there are not ours to remove.
set -euo pipefail

HOST="${TARGUM_HOST:?set TARGUM_HOST=user@box}"
REMOTE="${TARGUM_REMOTE_SHARED:-/var/lib/targum/targums/shared}"
DOMAIN="${DOMAIN:-targum.page}"

[ "$#" -gt 0 ] || { echo "usage: ship-shared.sh <built-reader-folder> [folder…]" >&2; exit 1; }

# A folder without a rendered reader is a build that started and did not finish, and
# `Library.readers` skips it — so it would arrive on the box and be invisible there,
# which is worse than not arriving.
for folder in "$@"; do
  [ -f "$folder/reader/index.html" ] || { echo "not built: $folder" >&2; exit 1; }
  [ -f "$folder/document.json" ] || { echo "no document.json: $folder" >&2; exit 1; }
done

echo "== what would go =="
du -sh "$@" | sed 's/^/   /'

echo "== ship =="
# --delay-updates so a page being read mid-copy is the old one whole rather than the new
# one half-written; a truncated sidecar is a reader whose video stops.
ssh "$HOST" "mkdir -p '$REMOTE'"
rsync -a --delay-updates --stats "$@" "$HOST:$REMOTE/" | tail -4

# Everything above arrived as root, and the service reads and rewrites it as targum.
ssh "$HOST" "chown -R targum:targum '$REMOTE'"
ssh "$HOST" "systemctl restart targum"

echo "== check =="
for attempt in $(seq 1 20); do
  curl -fsS --max-time 5 "https://$DOMAIN/health" 2>/dev/null | grep -q '"ok": *true' && break
  sleep 2
done
curl -fsS --max-time 5 "https://$DOMAIN/health" >/dev/null 2>&1 \
  && echo "   healthy" || echo "   /health did not come back — look at the box"
