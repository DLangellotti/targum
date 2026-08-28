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
uv build --wheel >/dev/null
WHEEL="$(ls -t dist/*.whl | head -1)"
echo "   $(basename "$WHEEL")"

echo "== ship =="
scp -q "$WHEEL" "$HOST:/tmp/"
REMOTE_WHEEL="/tmp/$(basename "$WHEEL")"

ssh "$HOST" "bash -euo pipefail -s" <<EOF
  # Installed as the service account so the tool and its virtualenv are owned by the
  # user that runs it. --force because the version usually has not changed.
  #
  # No UV_TOOL_BIN_DIR: it used to point at /usr/local/bin, which root owns and the
  # targum user cannot write. uv clears the bin directory before it writes the shim, so
  # the failure did not just abort — it left /usr/local/bin/targum dangling and the box
  # one restart away from not starting at all. uv's default is $HOME/.local/bin, which
  # the service account owns and which /usr/local/bin/targum already points at.
  sudo -u targum env HOME=/srv/targum \
    /usr/local/bin/uv tool install --force "${REMOTE_WHEEL}[difficulty]" >/dev/null
  rm -f "${REMOTE_WHEEL}"
  systemctl restart targum
EOF

echo "== verify =="
# The point of the whole exercise: a deploy that says it worked and did not is the
# thing this is meant to stop. Ask the box, over TLS, the way a reader would.
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 5 "https://$DOMAIN/health" 2>/dev/null | grep -q '"ok": *true'; then
    echo "   https://$DOMAIN/health is ok"
    ssh "$HOST" "sudo -u targum env HOME=/srv/targum /usr/local/bin/targum preflight \
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
