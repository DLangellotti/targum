#!/usr/bin/env bash
# Put back a wheel the box already has, restart, and prove it came back up.
#
#   TARGUM_HOST=root@targum.page ./deploy/rollback.sh                 # what the box keeps
#   TARGUM_HOST=root@targum.page ./deploy/rollback.sh <sha>           # step back to it
#   TARGUM_HOST=root@targum.page ./deploy/rollback.sh <sha> --catalogue      # and the catalogue
#   TARGUM_HOST=root@targum.page ./deploy/rollback.sh <sha> --keep-catalogue # code only
#
# Nothing is built here, and nothing needs this checkout to be on any commit: deploy.sh
# keeps each wheel it installed in /var/lib/targum/wheels/<sha12>/ on the box, with the
# constraints and extras it went in with, and this installs one of those again the same
# way, as the service account (targum-internal#482). The last five deploys are there; a
# commit older than that is a deploy of that commit, from a worktree, as ROLLBACK.md says.
#
# What this does not do, on purpose:
# - It does not touch the database. MIGRATIONS only ever add, so older code reads a newer
#   database. Restoring the copy deploy.sh took before the install is a separate, rarer
#   step (ROLLBACK.md), because it loses everything readers did since.
# - It does not rebuild reader pages. Pages the newer deploy rewrote keep the stylesheet
#   and script they were written with until the next deploy's rebuild rewrites them.
# - It does not run during a deploy's rebuild: that unit restarts the service at its end
#   and would put the newer code straight back.
set -euo pipefail

HOST="${TARGUM_HOST:?set TARGUM_HOST=user@box}"
DOMAIN="${DOMAIN:-targum.page}"
SSH_OPTS=(-o ServerAliveInterval=60 -o ServerAliveCountMax=120)
WHEELS=/var/lib/targum/wheels

WANTED=""
CATALOGUE=ask
for arg in "$@"; do
  case "$arg" in
    --catalogue) CATALOGUE=yes ;;
    --keep-catalogue) CATALOGUE=no ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "rollback.sh does not know $arg" >&2; exit 2 ;;
    *)
      [ -z "$WANTED" ] || { echo "one commit at a time: $WANTED or $arg" >&2; exit 2; }
      WANTED="$arg" ;;
  esac
done

# One look at the box, read-only: the wheels it keeps, newest first, and whether there is
# a catalogue from before the last deploy to offer back.
LOOK="ls -1t $WHEELS 2>/dev/null | sed 's/^/wheel /' || true
if [ -f /etc/targum/catalogue.json.prev ]; then
  echo \"catalogue-prev \$(date -u -r /etc/targum/catalogue.json.prev +%Y-%m-%dT%H:%MZ)\"
fi"
SEEN="$(ssh "${SSH_OPTS[@]}" "$HOST" "$LOOK")"
KEPT_LIST="$(sed -n 's/^wheel //p' <<<"$SEEN")"
PREV_AT="$(sed -n 's/^catalogue-prev //p' <<<"$SEEN")"

kept() {
  if [ -n "$KEPT_LIST" ]; then
    sed 's/^/     /' <<<"$KEPT_LIST" >&2
  else
    echo "     none: no deploy since rollback.sh arrived has kept one" >&2
  fi
}

if [ -z "$WANTED" ]; then
  echo "   the box keeps these wheels, newest first:" >&2
  kept
  echo "   the last deploys (deploys.log):" >&2
  ssh "${SSH_OPTS[@]}" "$HOST" "tail -n 8 /var/lib/targum/deploys.log 2>/dev/null || echo '     (no deploys.log yet)'" >&2
  echo "   say which: rollback.sh <sha>" >&2
  exit 2
fi

# A commit as git prints it, whole or short, or the -dirty name a deploy of an
# uncommitted tree was kept under. Anything else is refused before it reaches a shell.
if ! [[ "$WANTED" =~ ^([0-9a-f]{7,40})(-dirty)?$ ]]; then
  echo "   '$WANTED' is not a commit (7 to 40 hex characters, optionally -dirty)" >&2
  exit 2
fi
PREFIX="${BASH_REMATCH[1]:0:12}"
DIRTY="${BASH_REMATCH[2]}"
MATCHES="$(grep -E "^${PREFIX}[0-9a-f]*${DIRTY}\$" <<<"$KEPT_LIST" || true)"
if [ -z "$MATCHES" ]; then
  echo "   the box keeps no wheel for $WANTED, so there is nothing to put back. It keeps:" >&2
  kept
  echo "   to step back further, deploy that commit from a worktree (deploy/ROLLBACK.md)" >&2
  exit 1
fi
if [ "$(grep -c . <<<"$MATCHES")" -gt 1 ]; then
  echo "   $WANTED names more than one kept wheel; say more of it:" >&2
  sed 's/^/     /' <<<"$MATCHES" >&2
  exit 1
fi
NAME="$MATCHES"

PUT_BACK=0
if [ -n "$PREV_AT" ]; then
  case "$CATALOGUE" in
    yes) PUT_BACK=1 ;;
    no) ;;
    ask)
      if [ -t 0 ]; then
        read -r -p "   Put back the catalogue from before the last deploy too (replaced $PREV_AT)? [y/N] " answer
        case "$answer" in y|Y|yes) PUT_BACK=1 ;; esac
      else
        echo "   the catalogue stays as it is; --catalogue puts back the one replaced $PREV_AT"
      fi ;;
  esac
elif [ "$CATALOGUE" = yes ]; then
  echo "   there is no catalogue.json.prev on the box; the catalogue stays as it is" >&2
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WHO="$(id -un | tr -cd 'A-Za-z0-9._-')"
WHO="${WHO:-unknown}"

echo "== putting back $NAME =="
# Unquoted on purpose, like deploy.sh's: what this side knows goes in as text, and what
# the box works out is escaped. No backticks in here, in comments included.
ssh "${SSH_OPTS[@]}" "$HOST" "bash -euo pipefail -s" <<EOF
  if systemctl is-active --quiet targum-deploy.service; then
    echo "   a deploy is running on this box (targum-deploy.service), and it restarts the" >&2
    echo "   service when its rebuild ends, which would undo this. Nothing was changed." >&2
    echo "     journalctl -u targum-deploy -f" >&2
    exit 1
  fi
  KEPT=$WHEELS/$NAME
  WHEEL="\$(ls -1 "\$KEPT"/*.whl 2>/dev/null | head -1)"
  if [ -z "\$WHEEL" ] || [ ! -f "\$KEPT/box-constraints.txt" ] || [ ! -f "\$KEPT/extras" ]; then
    echo "   \$KEPT is missing its wheel, constraints or extras; nothing was changed." >&2
    exit 1
  fi
  EXTRAS="\$(cat "\$KEPT/extras")"

  # Exactly as deploy.sh installs: the service account owns the tool, the constraints
  # the wheel shipped with, torch from PyTorch's CPU index beside PyPI.
  if [ -d /srv/targum/.local/share/uv/tools/targum ]; then
    chown -R targum:targum /srv/targum/.local/share/uv/tools/targum
  fi
  sudo -u targum env HOME=/srv/targum UV_TOOL_BIN_DIR=/srv/targum/.local/bin \
    /usr/local/bin/uv tool install --force "\$WHEEL[\$EXTRAS]" \
      --constraints "\$KEPT/box-constraints.txt" \
      --index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match \
      >/dev/null
  ln -sfn /srv/targum/.local/bin/targum /usr/local/bin/targum
  touch "\$KEPT"
  echo "   installed \$(basename "\$WHEEL")"

  # Swapped rather than copied, so the catalogue this replaces becomes the .prev and a
  # second run with --catalogue undoes the first.
  if [ "$PUT_BACK" = 1 ]; then
    mv /etc/targum/catalogue.json /etc/targum/catalogue.json.swap
    mv /etc/targum/catalogue.json.prev /etc/targum/catalogue.json
    mv /etc/targum/catalogue.json.swap /etc/targum/catalogue.json.prev
    chown root:targum /etc/targum/catalogue.json /etc/targum/catalogue.json.prev
    chmod 0640 /etc/targum/catalogue.json /etc/targum/catalogue.json.prev
    echo "   catalogue put back; the one it replaced is catalogue.json.prev"
  fi

  printf '%s %s %s rollback\n' "$STAMP" "$NAME" "$WHO" >> /var/lib/targum/deploys.log

  # Blocking: the stop drains, finishing running builds and chat turns for up to ten
  # minutes while the old process serves, and a health check that answered before the
  # restart finished would be the old code saying it is fine.
  echo "   restarting (a busy box drains for up to ten minutes first)"
  systemctl restart targum
EOF

echo "== verify =="
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 5 "https://$DOMAIN/health" 2>/dev/null | grep -q '"ok": *true'; then
    echo "   https://$DOMAIN/health is ok, on $NAME"
    echo
    echo "Rolled back."
    exit 0
  fi
  sleep 2
done

echo "   health check never passed after putting back $NAME" >&2
ssh "${SSH_OPTS[@]}" "$HOST" "journalctl -u targum -n 40 --no-pager" >&2
exit 1
