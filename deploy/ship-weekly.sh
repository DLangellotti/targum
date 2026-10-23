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

# The box side runs as the service account, never as root (targum-internal#515). The
# folders are targum's, so anything in them, a symlink included, may have been put there
# by the service, and root following one writes wherever it points; a symlinked parent
# redirects a root command the same way. The receiving rsync is started as targum
# (--rsync-path), the mkdir, mv and rm run as targum, and so the files arrive as
# targum's and no chown -R is needed after. Only what is root's stays root: the env file
# in /etc/targum and the restart.
AS_TARGUM="runuser -u targum --"

LOCAL="${TARGUM_WEEKLY_DIR:-$ROOT/targum-out/weekly}"
INDEX="$LOCAL/index.json"
[ -f "$INDEX" ] || { echo "no index at $INDEX — nothing has been drafted here" >&2; exit 1; }

# Which folders this issue is, and whether it may go at all. Asked of the index rather
# than of the directory: a folder on disk proves a build happened, not that a person
# read it and pressed publish.
#
# Every language the issue lists, not only English (targum-internal#288). A language is
# listed only once all three levels were built into it, so a Russian build that stopped
# halfway leaves its folders here and nothing is carried; the English goes regardless.
# Another language's folder is the English one with its code on the end — the rule
# `weekly.models.folder` writes down — because this reads the index with no targum.
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
languages = [code for code in issue.get("languages") or ["en"] if code != "en"]
for edition in issue["editions"]:
    print(edition["folder"])
    for code in languages:
        print(f"{edition['folder']}-{code}")
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
ssh "$HOST" "$AS_TARGUM mkdir -p '$REMOTE/.staging'"
for folder in $FOLDERS; do
  echo "   $folder"
  ssh "$HOST" "$AS_TARGUM rm -rf '$REMOTE/.staging/$folder'"
  rsync -rL -q --rsync-path="$AS_TARGUM rsync" "$LOCAL/$folder/" "$HOST:$REMOTE/.staging/$folder/"
done

# The issue's own sources ride along — the markdown the editions were composed as, and
# the brief they were composed from. Not decoration: a build on the box re-ingests from
# the markdown, and shipping the readers without it left every library-row build failing
# with "No such file or directory: …-aleph.md" the first time somebody pressed one.
echo "   $WEEK (sources)"
ssh "$HOST" "$AS_TARGUM rm -rf '$REMOTE/.staging/$WEEK'"
rsync -rL -q --rsync-path="$AS_TARGUM rsync" "$LOCAL/$WEEK/" "$HOST:$REMOTE/.staging/$WEEK/"

echo "== putting in place =="
ssh "$HOST" "$AS_TARGUM rm -rf '$REMOTE/$WEEK' && $AS_TARGUM mv '$REMOTE/.staging/$WEEK' '$REMOTE/$WEEK'"
for folder in $FOLDERS; do
  ssh "$HOST" "$AS_TARGUM rm -rf '$REMOTE/$folder' && $AS_TARGUM mv '$REMOTE/.staging/$folder' '$REMOTE/$folder'"
done

# The index last, always. It is what makes an issue exist as far as the server is
# concerned, so writing it before its readers have landed is the one ordering that can
# serve a 404 from the front page.
echo "== index =="
rsync -q --rsync-path="$AS_TARGUM rsync" "$INDEX" "$HOST:$REMOTE/index.json.new"
ssh "$HOST" "$AS_TARGUM mv '$REMOTE/index.json.new' '$REMOTE/index.json' && $AS_TARGUM rmdir '$REMOTE/.staging' 2>/dev/null || true"

# Everything above arrived as targum's. It used to arrive as root, and the service —
# which rebuilds every targum on the next deploy and writes a chapter when somebody
# reads — could not touch it: the deploy after a shipped issue died on
# `.annotation.json.tmp: Permission denied` inside the issue's own folder. A root
# chown -R fixed that and opened the symlink hole (targum-internal#515); writing as
# targum fixes both.

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
