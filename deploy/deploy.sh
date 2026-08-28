#!/usr/bin/env bash
# Ship the working tree to the box, restart, and prove it came back up.
#
#   TARGUM_HOST=root@targum.page ./deploy/deploy.sh
#
# One command, because a fiddly deploy is one that does not happen while an alpha
# reader is waiting on the fix.
set -euo pipefail

HOST="${TARGUM_HOST:?set TARGUM_HOST=user@box}"
DOMAIN="${DOMAIN:-targum.page}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== checks, before anything leaves this machine =="
# Deploying a tree that fails its own tests is how a bad afternoon starts.
uv run ruff check . >/dev/null
uv run mypy >/dev/null
uv run pytest -q >/dev/null
echo "   clean"

echo "== build =="
rm -rf dist
# The about page reads `git log`, and a wheel has no repository to read. The counts are
# written into the package here, from this tree, and served from there on the box.
uv run python -c "from targum.about import stamp; stamp()"
uv build --wheel >/dev/null
WHEEL="$(ls -t dist/*.whl | head -1)"
echo "   $(basename "$WHEEL")"

echo "== ship =="
scp -q "$WHEEL" "$HOST:/tmp/"
REMOTE_WHEEL="/tmp/$(basename "$WHEEL")"

ssh "$HOST" "bash -euo pipefail -s" <<EOF
  # Installed as the service account so the tool and its virtualenv are owned by the
  # user that runs it. --force because the version usually has not changed.
  # The covers extra is Pillow, which shrinks a drawn cover to the 320px tile that is
  # actually served. Installed whether or not there is a key for it: without Pillow
  # the app refuses to draw rather than keeping a 2.5 MB original, so a key added
  # later would otherwise need a redeploy to become useful.
  #
  # No backticks in here, in comments included: this heredoc is unquoted, so the
  # shell runs whatever they hold. The word covers was being run as a command on
  # every deploy.
  # The launcher lands in targum's own bin; root then points /usr/local/bin at it,
  # because the service user cannot write to /usr/local/bin and should not be able to.
  sudo -u targum env HOME=/srv/targum UV_TOOL_BIN_DIR=/srv/targum/.local/bin \
    /usr/local/bin/uv tool install --force "${REMOTE_WHEEL}[difficulty,covers]" >/dev/null
  ln -sfn /srv/targum/.local/bin/targum /usr/local/bin/targum
  rm -f "${REMOTE_WHEEL}"

  # Every reader carries the stylesheet and the script it was written with, baked in, so
  # the ones already on the shelves keep the old ones until they are written again. This
  # rewrites every targum in every home from the artifacts beside it: nothing is fetched,
  # nothing is spent, and no key is needed. As the service account, or the files come out
  # owned by root in a directory owned by targum and the next chapter cannot be written.
  # Through systemd, with the service's environment: the rebuild fills each reader's
  # meanings from the shared cache, and without TARGUM_CACHE_DIR it looked in an empty
  # one and filled nothing — silently, which is how it went unnoticed for a deploy.
  systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum \
    --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env \
    /usr/local/bin/targum rebuild --out /var/lib/targum/targums >/dev/null

  systemctl restart targum
EOF

echo "== verify =="
# The point of the whole exercise: a deploy that says it worked and did not is the
# thing this is meant to stop. Ask the box, over TLS, the way a reader would.
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 5 "https://$DOMAIN/health" 2>/dev/null | grep -q '"ok": *true'; then
    echo "   https://$DOMAIN/health is ok"
    # With the service's environment, or it reports every secret as missing. Through
    # systemd, because targum.env is in systemd's format, not the shell's: a value with
    # a space or an angle bracket in it is fine there and a syntax error here.
    ssh "$HOST" "systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum \
      --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env \
      /usr/local/bin/targum preflight \
      --store /var/lib/targum/targum.db --out /var/lib/targum/targums" || true
    echo
    echo "Deployed."
    exit 0
  fi
  sleep 2
done

echo "   health check never passed" >&2
ssh "$HOST" "journalctl -u targum -n 40 --no-pager" >&2
exit 1
