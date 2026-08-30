#!/usr/bin/env bash
# Put one published issue of the weekly on the box.
#
#   TARGUM_HOST=root@targum.page ./deploy/ship-weekly.sh 2026-w35
#
# The weekly is written on a laptop and read on a box. Generation is the proprietary
# half and does not ship in the wheel, so an issue travels the way the catalogue does:
# built here, copied there, owned by the machine that made it.
#
# Nothing here builds or spends. Draft, build and publish first; this only carries.
set -euo pipefail

WEEK="${1:?usage: ship-weekly.sh <week>, e.g. 2026-w35}"
HOST="${TARGUM_HOST:?set TARGUM_HOST=user@box}"
REMOTE="${TARGUM_REMOTE_WEEKLY:-/var/lib/targum/targums/weekly}"
DOMAIN="${DOMAIN:-targum.page}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCAL="${TARGUM_WEEKLY_DIR:-$ROOT/targum-out/weekly}"
INDEX="$LOCAL/index.json"
[ -f "$INDEX" ] || { echo "no index at $INDEX — nothing has been drafted here" >&2; exit 1; }

# Which folders this issue is, and whether it may go at all. Asked of the index rather
# than of the directory: a folder on disk proves a build happened, not that a person
# read it and pressed publish.
FOLDERS="$(
  WEEK="$WEEK" INDEX="$INDEX" python3 - <<'PY'
import json, os, sys
index = json.load(open(os.environ["INDEX"], encoding="utf-8"))
issue = next((one for one in index["issues"] if one["id"] == os.environ["WEEK"]), None)
if issue is None:
    sys.exit(f"no issue for {os.environ['WEEK']}")
if issue.get("state") != "published":
    sys.exit(f"{os.environ['WEEK']} is {issue.get('state')} — publish it first")
bad = [e for e in issue["editions"] if e.get("lifted")]
if bad:
    sys.exit(f"{len(bad)} level(s) still carry a source's wording; this one does not go out")
print("\n".join(e["folder"] for e in issue["editions"]))
PY
)"
[ -n "$FOLDERS" ] || { echo "no editions to send" >&2; exit 1; }

echo "== $WEEK =="
for folder in $FOLDERS; do
  [ -d "$LOCAL/$folder/reader" ] || { echo "not built: $folder — run targum weekly build" >&2; exit 1; }
done

# Into a staging directory first, then renamed into place. A folder is not atomic: a
# reader who opens the issue while scp is halfway through it gets a page whose second
# half has not arrived. Rename is atomic within a filesystem, so an edition is either
# the old one or the new one and never a mixture.
echo "== copying =="
ssh "$HOST" "mkdir -p '$REMOTE/.staging'"
for folder in $FOLDERS; do
  echo "   $folder"
  ssh "$HOST" "rm -rf '$REMOTE/.staging/$folder'"
  scp -qr "$LOCAL/$folder" "$HOST:$REMOTE/.staging/$folder"
done

# The issue's own sources ride along — the markdown the editions were composed as, and
# the brief they were composed from. Not decoration: a build on the box re-ingests from
# the markdown, and shipping the readers without it left every library-row build failing
# with "No such file or directory: …-aleph.md" the first time somebody pressed one.
echo "   $WEEK (sources)"
ssh "$HOST" "rm -rf '$REMOTE/.staging/$WEEK'"
scp -qr "$LOCAL/$WEEK" "$HOST:$REMOTE/.staging/$WEEK"

echo "== putting in place =="
ssh "$HOST" "rm -rf '$REMOTE/$WEEK' && mv '$REMOTE/.staging/$WEEK' '$REMOTE/$WEEK'"
for folder in $FOLDERS; do
  ssh "$HOST" "rm -rf '$REMOTE/$folder' && mv '$REMOTE/.staging/$folder' '$REMOTE/$folder'"
done

# The index last, always. It is what makes an issue exist as far as the server is
# concerned, so writing it before its readers have landed is the one ordering that can
# serve a 404 from the front page.
echo "== index =="
scp -q "$INDEX" "$HOST:$REMOTE/index.json.new"
ssh "$HOST" "mv '$REMOTE/index.json.new' '$REMOTE/index.json' && rmdir '$REMOTE/.staging' 2>/dev/null || true"

# The path a standalone build reads the issue from. The server works it out from its own
# --out, but `targum build weekly:…` run for one person's shelf does not — it fell back
# to the working directory and failed with a path that exists on no box. Appended only
# when absent, never rewritten: the file holds every secret the box has.
ssh "$HOST" "grep -q '^TARGUM_WEEKLY_DIR=' /etc/targum/targum.env || echo 'TARGUM_WEEKLY_DIR=$REMOTE' >> /etc/targum/targum.env"

echo "== check =="
for folder in $FOLDERS; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/weekly/read/$folder/reader/index.html")"
  echo "   $folder $code"
  [ "$code" = "200" ] || { echo "the box is not serving it" >&2; exit 1; }
done
code="$(curl -s -o /dev/null -w '%{http_code}' -L "https://$DOMAIN/weekly")"
echo "   /weekly $code"
echo "Out. Nobody has been told yet — that is: targum weekly announce $WEEK"
