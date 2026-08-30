#!/usr/bin/env bash
# Put the recordings and the dialogue shelf on the box.
#
#   TARGUM_HOST=root@targum.page ./deploy/ship-audio.sh
#
# Both are content: cut and aligned on a laptop, read on a box, and never in the
# repository. They travel the way the catalogue and the weekly do — built here, copied
# there, owned by the machine that made them.
#
# Nothing here builds or spends. It carries, points the service at what it carried, and
# stops.
#
# Targums already on the box gain their audio too. A recording is addressed by verse ref,
# refs arrived with ingester `sefaria/3`, and anything older has segments with nothing to
# map a recording onto — so `targum refs` asks each source for its document again and
# copies the refs across, and `targum rebuild` then writes the pages. Both are free and
# neither touches a reader's own words: the annotation is not rewritten, the segment ids
# do not move, and a text whose wording has changed since it was built is declined whole
# rather than mapped onto the wrong verses.
set -euo pipefail

HOST="${TARGUM_HOST:?set TARGUM_HOST=user@box}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RECORDINGS="${TARGUM_RECORDING_DIR:-$ROOT/targum-out/recordings}"
DIALOGUES="${TARGUM_DIALOGUE_DIR:-$ROOT/targum-out/dialogues}"
REMOTE_RECORDINGS="${TARGUM_REMOTE_RECORDINGS:-/var/lib/targum/recordings}"
REMOTE_DIALOGUES="${TARGUM_REMOTE_DIALOGUES:-/var/lib/targum/dialogues}"

[ -d "$RECORDINGS" ] || { echo "no recordings at $RECORDINGS" >&2; exit 1; }
[ -d "$DIALOGUES" ] || { echo "no dialogues at $DIALOGUES" >&2; exit 1; }

# Every recording is a folder with a manifest. A folder without one is half-cut, and
# shipping it would put a book on the box whose spans nothing can read.
BAD="$(find "$RECORDINGS" -mindepth 1 -maxdepth 1 -type d ! -exec test -f '{}/recording.json' \; -print | head -5)"
if [ -n "$BAD" ]; then
  echo "these recordings have no recording.json, so they are half-cut:" >&2
  echo "$BAD" >&2
  exit 1
fi

echo "== what would go =="
du -sh "$RECORDINGS" "$DIALOGUES" | sed 's/^/   /'
echo "   $(find "$RECORDINGS" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ') books, $(ls "$DIALOGUES"/*.json 2>/dev/null | wc -l | tr -d ' ') scenes"

echo "== ship =="
# rsync rather than scp: this is a gigabyte the first time and almost nothing after it.
# --delay-updates so a build that runs mid-copy reads the old file whole rather than the
# new one half-written — a truncated mp3 becomes a reader with a recording that stops.
# Every flag here is one both openrsync — which is what macOS ships, and which has no
# `--info` at all — and rsync 3 accept. Check any new one against the older of the two:
# `--info=stats1` cost a deploy, because rsync answered with a usage message, the
# script stopped on it, and the box was left looking for a shelf that never arrived.
command -v rsync >/dev/null || { echo "rsync is not installed here" >&2; exit 1; }
ssh "$HOST" "install -d -o targum -g targum -m 0755 '$REMOTE_RECORDINGS' '$REMOTE_DIALOGUES'"
rsync -a --delete --delay-updates --stats \
  "$RECORDINGS/" "$HOST:$REMOTE_RECORDINGS/" | sed 's/^/   /'
rsync -a --delete --delay-updates --stats \
  "$DIALOGUES/" "$HOST:$REMOTE_DIALOGUES/" | sed 's/^/   /'

echo "== point the service at it =="
ssh "$HOST" "bash -euo pipefail -s" <<EOF
  chown -R targum:targum '$REMOTE_RECORDINGS' '$REMOTE_DIALOGUES'
  # Appended only when absent, and existing lines are never rewritten: this file holds
  # every secret the box has, and a script that edits it in place is one bad sed from
  # locking everybody out. These two are paths rather than secrets, which is the only
  # reason touching it at all is reasonable.
  touch /etc/targum/targum.env
  grep -q '^TARGUM_RECORDING_DIR=' /etc/targum/targum.env \
    || echo 'TARGUM_RECORDING_DIR=$REMOTE_RECORDINGS' >> /etc/targum/targum.env
  grep -q '^TARGUM_DIALOGUE_DIR=' /etc/targum/targum.env \
    || echo 'TARGUM_DIALOGUE_DIR=$REMOTE_DIALOGUES' >> /etc/targum/targum.env
  systemctl restart targum
EOF

echo "== give the targums already here their refs, and write their pages =="
# Free, and safe to run again: a text that already carries refs is skipped without a
# fetch, and one whose wording has moved on is left exactly as it was.
ssh "$HOST" "bash -euo pipefail -s" <<'EOF'
  run() {
    systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum       --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env "$@"
  }
  run /usr/local/bin/targum refs --out /var/lib/targum/targums | tail -3 | sed 's/^/   /'
  run /usr/local/bin/targum rebuild --out /var/lib/targum/targums | tail -1 | sed 's/^/   /'
EOF

echo "== verify =="
ssh "$HOST" "bash -euo pipefail -s" <<EOF
  books=\$(find '$REMOTE_RECORDINGS' -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
  scenes=\$(ls '$REMOTE_DIALOGUES'/*.json 2>/dev/null | wc -l | tr -d ' ')
  echo "   \$books books, \$scenes scenes on the box"
  grep -E '^TARGUM_(RECORDING|DIALOGUE)_DIR=' /etc/targum/targum.env | sed 's/^/   /'
EOF

cat <<'NOTE'

Done. Texts built from here on carry their audio with no ceremony; the ones already on
the box have just been given their refs and rewritten.

If a book was declined above, its wording on Sefaria has moved since it was built. That
is a real difference and not a migration problem: rebuild that text properly rather than
mapping a recording onto verses it no longer matches.
NOTE
