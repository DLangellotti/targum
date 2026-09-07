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

# Keep the connection talking while the box is silent. Something between here and the
# box drops a connection that says nothing for long enough — a plain TCP idle drop, not
# sshd, which reports `clientaliveinterval 0` — and the install below is minutes of
# nothing said while the box pulls torch. It was the rebuild that showed this first: an
# annotator rename re-annotates every text by design, two hours of silence on a box with
# no GPU, and the connection went with it. The rebuild no longer holds a connection at all
# (see the box-side block), and this stays for everything that still does. Two hours at
# sixty seconds is 120 unanswered probes before the client gives up. targum-internal#177.
SSH_OPTS=(-o ServerAliveInterval=60 -o ServerAliveCountMax=120)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== checks, before anything leaves this machine =="
# Deploying a tree that fails its own tests is how a bad afternoon starts.
#
# Quiet while they pass and loud when they do not. They used to be quiet either way, and
# a failure printed the word "checks" and nothing else — which says a check failed but
# not which one, so finding out meant running all three again by hand. The output is held
# and printed only if the command fails.
check() {
  local said
  if ! said="$("$@" 2>&1)"; then
    echo "   $* failed:" >&2
    echo "$said" | tail -40 >&2
    exit 1
  fi
}
# CI is the gate for the suite, and the laptop is not: a single-process run of the
# whole suite is killed for memory on an 8 GB machine (2026-09-06), and a deploy that
# dies in its preflight for a reason that is not the code is a deploy that does not
# happen. So the suite here may be stood down for a tree CI has already passed — and
# only for that exact tree: TARGUM_CHECKED must name the commit being shipped, and the
# tree must be clean, or the suite runs as it always did.
check uv run ruff check .
check uv run ruff format --check .
check uv run mypy
if [ "${TARGUM_CHECKED:-}" = "$(git rev-parse HEAD)" ] && [ -z "$(git status --porcelain)" ]; then
  echo "   suite: passed by CI at $(git rev-parse --short HEAD)"
else
  check uv run pytest -q
fi
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
# The catalogue is private data, not code: it is not in the repository and not in the
# wheel. It travels from this machine's copy to the box, beside the secrets, where the
# service reads it by default.
CATALOGUE="${TARGUM_CATALOGUE:-$HOME/.targum/catalogue.json}"
if [ ! -f "$CATALOGUE" ]; then
  echo "no catalogue at $CATALOGUE — the library would be empty" >&2
  exit 1
fi
scp -q "$CATALOGUE" "$HOST:/tmp/catalogue.json"
# The publishers the chat may search — private data for the same reason, read from
# beside the catalogue by default. Optional, unlike the catalogue: a box without one
# has nowhere to search and says so, and nothing else changes.
SOURCES="${TARGUM_SOURCES:-$HOME/.targum/sources.json}"
if [ -f "$SOURCES" ]; then
  scp -q "$SOURCES" "$HOST:/tmp/sources.json"
else
  echo "no sources.json at $SOURCES — the chat will have no publishers to search" >&2
fi
# The unit too. provision.sh installs it once, on a fresh box, and nothing carried it
# after that: a limit raised here stayed raised here.
scp -q deploy/targum.service "$HOST:/tmp/targum.service"

ssh "${SSH_OPTS[@]}" "$HOST" "bash -euo pipefail -s" <<EOF
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
  #
  # Torch from PyTorch's own CPU index rather than PyPI, where the Linux wheel is the
  # CUDA build and brings 4.9 GB of driver libraries to a box with no GPU. The index
  # is added beside PyPI, not in front of it: on its own it also carries old copies of
  # requests and friends, and uv's default of trusting the first index that has a
  # package would pin them there. Best match across both leaves every other package
  # exactly where PyPI put it and changes torch alone, from 2.14.0 to 2.14.0+cpu,
  # with the nvidia-*, cuda-* and triton packages gone: checked by resolving the same
  # extras for x86_64 Linux both ways and diffing (targum-internal#93).
  sudo -u targum env HOME=/srv/targum UV_TOOL_BIN_DIR=/srv/targum/.local/bin \
    /usr/local/bin/uv tool install --force "${REMOTE_WHEEL}[difficulty,covers,bring]" \
      --index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match \
      >/dev/null
  ln -sfn /srv/targum/.local/bin/targum /usr/local/bin/targum
  rm -f "${REMOTE_WHEEL}"
  # The directory too: it was root-only, which systemd never minded — it reads the
  # secrets as root — and the service, which reads the catalogue as targum, could not
  # reach into it. The library was empty for the length of one deploy.
  install -d -o root -g targum -m 0750 /etc/targum
  install -o root -g targum -m 0640 /tmp/catalogue.json /etc/targum/catalogue.json
  rm -f /tmp/catalogue.json
  if [ -f /tmp/sources.json ]; then
    install -o root -g targum -m 0640 /tmp/sources.json /etc/targum/sources.json
    rm -f /tmp/sources.json
  fi
  install -o root -g root -m 0644 /tmp/targum.service /etc/systemd/system/targum.service
  rm -f /tmp/targum.service
  systemctl daemon-reload

  # Every reader carries the stylesheet and the script it was written with, baked in, so
  # the ones already on the shelves keep the old ones until they are written again. This
  # rewrites every targum in every home from the artifacts beside it: nothing is fetched,
  # nothing is spent, and no key is needed. As the service account, or the files come out
  # owned by root in a directory owned by targum and the next chapter cannot be written.
  # Through systemd, with the service's environment: the rebuild fills each reader's
  # meanings from the shared cache, and without TARGUM_CACHE_DIR it looked in an empty
  # one and filled nothing — silently, which is how it went unnoticed for a deploy.
  # --words: a text whose words were worked out by an older annotator has them worked
  # out again, on the box, before its page is written. Free, and nothing at all when
  # the annotator has not changed — the name is compared without loading a model.
  # --gloss: and the meanings that re-annotation left unbought are bought, here, with
  # the box's key. Nothing when nothing moved; a few dollars once when an annotator
  # starts filing words under keys nobody has paid for, which oshb/2 did — 92 of 200
  # rows of Judges opened on "look it up" for a day because this line did not say it.
  #
  # The rebuild, the seed and the restart as one transient unit that this shell starts
  # and does not wait on. They ran here in turn, each under its own systemd-run --wait,
  # with this shell holding the connection open through all of it — and an annotator
  # rename is two hours of nothing said on a box with no GPU, which is longer than the
  # path from the laptop to the box tolerates. The failure that made was the worst shape
  # available: the rebuild, a unit owned by PID 1 already, finished every text
  # regardless; what died with this shell was the seed and the restart after it, so the
  # expensive work succeeded, the deploy reported 255, and the box went on serving the
  # old process (targum-internal#177). Past this line nothing on the box needs the
  # laptop: the unit runs to its end or fails on its own, what it says goes to the
  # journal under its name rather than onto a connection that may be gone, and the
  # laptop asks after it below. The two inner units keep the service's user and
  # environment, as before; the outer one is root, because the restart is.
  #
  # Named, so the laptop has something to ask about, and so a second deploy started
  # during a rebuild is refused at this line rather than run two rebuilds over one
  # shelf. Not --collect: that forgets a failed unit the moment it fails, and the
  # laptop would read the absence as a finish. The last deploy's failed state is
  # cleared here instead, its journal having been read by whoever ran it.
  systemctl reset-failed targum-deploy.service 2>/dev/null || true
  systemd-run --quiet --unit=targum-deploy \
    --description="targum deploy: rebuild, seed, restart" \
    /bin/bash -euo pipefail -c '
      systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum \
        --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env \
        /usr/local/bin/targum rebuild --words --gloss --out /var/lib/targum/targums

      # The shared texts a reader with nothing is handed first. Published translations,
      # so nothing is spent; every stage is cached, so after the first time this is a
      # rewrite.
      systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum \
        --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env \
        /usr/local/bin/targum seed --out /var/lib/targum/targums

      systemctl restart targum
    '
EOF

echo "== rebuild, seed, restart =="
# The box is doing these on its own (the block above). Asked after, on a fresh connection
# each time, so there is nothing for an idle drop to take: a poll that cannot reach the
# box is a poll to repeat, not a deploy that failed — up to a point, because a box that
# has answered nothing for five minutes is a box to go and look at.
#
# A transient unit that ends well is unloaded, and systemctl calls a unit it no longer
# has "inactive", so inactive is the finish. One that ends badly stays loaded as
# "failed" until the next deploy clears it, above. is-active says either on stdout and
# exits 3 for both, which is not a failure of the asking; ssh's own trouble is 255.
asked() {
  local said rc=0
  said="$(ssh "${SSH_OPTS[@]}" "$HOST" "systemctl is-active targum-deploy.service" 2>/dev/null)" || rc=$?
  if [ "$rc" -eq 255 ]; then echo unreachable; else echo "${said:-unknown}"; fi
}
began=$SECONDS
polls=0
unanswered=0
while :; do
  state="$(asked)"
  case "$state" in
    inactive) break ;;
    failed)
      echo "   targum-deploy failed on the box:" >&2
      ssh "${SSH_OPTS[@]}" "$HOST" "journalctl -u targum-deploy -n 40 --no-pager" >&2
      exit 1 ;;
    active|activating|deactivating) unanswered=0 ;;
    unreachable)
      unanswered=$((unanswered + 1))
      if [ "$unanswered" -ge 20 ]; then
        echo "   the box has not answered for five minutes; the unit may still be running there" >&2
        echo "   (ssh $HOST journalctl -u targum-deploy -f)" >&2
        exit 1
      fi ;;
    *)
      echo "   targum-deploy is '$state', which this script does not understand" >&2
      exit 1 ;;
  esac
  polls=$((polls + 1))
  # A line every five minutes, so a two-hour rebuild does not read as a hung deploy.
  if [ $((polls % 20)) -eq 0 ]; then
    echo "   still running after $(( (SECONDS - began) / 60 ))m; journalctl -u targum-deploy on the box says how far"
  fi
  sleep 15
done
echo "   done"

echo "== verify =="
# The point of the whole exercise: a deploy that says it worked and did not is the
# thing this is meant to stop. Ask the box, over TLS, the way a reader would.
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 5 "https://$DOMAIN/health" 2>/dev/null | grep -q '"ok": *true'; then
    echo "   https://$DOMAIN/health is ok"
    # With the service's environment, or it reports every secret as missing. Through
    # systemd, because targum.env is in systemd's format, not the shell's: a value with
    # a space or an angle bracket in it is fine there and a syntax error here.
    ssh "${SSH_OPTS[@]}" "$HOST" "systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum \
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
ssh "${SSH_OPTS[@]}" "$HOST" "journalctl -u targum -n 40 --no-pager" >&2
exit 1
