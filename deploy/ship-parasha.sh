#!/usr/bin/env bash
# Put the built parasha corpus on the box.
#
#   TARGUM_HOST=root@targum.page ./deploy/ship-parasha.sh
#
# Same division as the weekly: built on a laptop, read on a box. The corpus is cut from
# the Tanakh on the local shelf and the aligner that gives a doubled week its audio lives
# in the gitignored half, so neither travels in the wheel. This only carries what is
# already built — it spends nothing and builds nothing. Run `targum parasha build` first.
#
# Unlike the weekly there is no publish gate, because there is nothing to gate: the
# fifty-four portions are the same fifty-four every year and no editorial judgment stands
# between building one and it being correct. What rotates is the pointer inside
# index.json, which is why a rerun is cheap and safe.
set -euo pipefail

HOST="${TARGUM_HOST:?set TARGUM_HOST=user@box}"
REMOTE="${TARGUM_REMOTE_PARASHA:-/var/lib/targum/targums/parasha}"
DOMAIN="${DOMAIN:-targum.page}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCAL="${TARGUM_PARASHA_DIR:-$ROOT/targum-out/parasha}"
INDEX="$LOCAL/index.json"
[ -f "$INDEX" ] || { echo "no index at $INDEX — run targum parasha build" >&2; exit 1; }
[ -d "$LOCAL/read" ] || { echo "no readers at $LOCAL/read — run targum parasha build" >&2; exit 1; }

# What the index says is readable, asked of the index rather than of the directory: a
# folder on disk proves a build started, not that the portion came out whole.
FOLDERS="$(
  INDEX="$INDEX" python3 - <<'PY'
import json, os
index = json.load(open(os.environ["INDEX"], encoding="utf-8"))
# portions is keyed by slug, not a list.
folders = sorted({p["folder"] for p in index.get("portions", {}).values() if p.get("folder")})
print("\n".join(folders))
PY
)"
[ -n "$FOLDERS" ] || { echo "the index lists no portions" >&2; exit 1; }
echo "== $(echo "$FOLDERS" | wc -l | tr -d ' ') portions =="

for folder in $FOLDERS; do
  [ -d "$LOCAL/read/$folder/reader" ] || {
    echo "not built: $folder — run targum parasha build" >&2; exit 1; }
done

# The shelf, kept in step with the corpus. A portion is a catalogue row and the
# fifty-four are one collection, and the catalogue is a file on this machine that
# deploy.sh carries over. The merge used to be a separate step run by hand, and it had
# not been run: the box held every portion and the live library listed none of them.
# Merged here from the corpus about to be shipped and sent below the way deploy.sh sends
# it, so a portion cannot be on the box without being on the shelf.
CATALOGUE="${TARGUM_CATALOGUE:-$HOME/.targum/catalogue.json}"
[ -f "$CATALOGUE" ] || {
  echo "no catalogue at $CATALOGUE — the portions have no shelf to go on" >&2; exit 1; }
echo "== shelf =="
TARGUM_PARASHA_DIR="$LOCAL" TARGUM_CATALOGUE="$CATALOGUE" uv run targum parasha entries --write

ssh "$HOST" "mkdir -p '$REMOTE/read' '$REMOTE/calendar'"

# rsync rather than scp, and directly rather than through a staging directory. The
# corpus is 63 readers and does not change from one week to the next — only the pointer
# inside index.json does — so a rerun sends almost nothing, where scp would send all of
# it every time. rsync writes each file to a temporary name and renames it into place,
# so no reader is ever served half a file; what a staging directory buys on top of that
# is cross-file consistency, and the one ordering that actually matters here is handled
# below by sending index.json last.
#
# `--stats` rather than `--info=stats1`: macOS ships openrsync claiming rsync 2.6.9, which
# predates --info by a decade and exits 1 on it. This runs from a laptop, so 2.6.9 is the
# floor, and every flag here has to exist in it.
echo "== copying =="
rsync -a --delete --stats "$LOCAL/read/" "$HOST:$REMOTE/read/" | tail -4
rsync -a --stats "$LOCAL/calendar/" "$HOST:$REMOTE/calendar/" | tail -3

# The index last, always: it is what makes a portion exist as far as the server is
# concerned, and it also carries the pointer at this week's reading. Written to a
# neighbouring name and renamed, so the server never reads a half-written index.
echo "== index =="
scp -q "$INDEX" "$HOST:$REMOTE/index.json.new"
ssh "$HOST" "mv '$REMOTE/index.json.new' '$REMOTE/index.json'"

# Handed to the service, for the reason the weekly's copy records: everything above
# arrived as root, and the service reads and rewrites it as targum.
ssh "$HOST" "chown -R targum:targum '$REMOTE'"

# The catalogue with the portions in it, placed the way deploy.sh places it. The service
# reads it as targum, from a directory only root writes.
echo "== catalogue =="
scp -q "$CATALOGUE" "$HOST:/tmp/catalogue.json"
ssh "$HOST" "install -o root -g targum -m 0640 /tmp/catalogue.json /etc/targum/catalogue.json \
  && rm -f /tmp/catalogue.json"

# Where the server looks. Without it `root()` falls back to the working directory, which
# for the unit is /srv/targum, and every portion 404s while the files sit in
# /var/lib. Appended only when absent, never rewritten: the file holds every secret the
# box has.
ssh "$HOST" "grep -q '^TARGUM_PARASHA_DIR=' /etc/targum/targum.env \
  || echo 'TARGUM_PARASHA_DIR=$REMOTE' >> /etc/targum/targum.env"
ssh "$HOST" "systemctl restart targum"

echo "== check =="
for attempt in $(seq 1 20); do
  curl -fsS --max-time 5 "https://$DOMAIN/health" 2>/dev/null | grep -q '"ok": *true' && break
  sleep 2
done
code="$(curl -s -o /dev/null -w '%{http_code}' -L "https://$DOMAIN/parasha")"
echo "   /parasha $code"
tag="$(curl -sS -D - -o /dev/null -L "https://$DOMAIN/parasha" | grep -i '^x-robots-tag' || true)"
echo "   ${tag:-no X-Robots-Tag — the portions are being offered to search engines}"
echo
echo "Out. Not indexed until TARGUM_INDEX_PARASHA=1 is set on the box."
