#!/usr/bin/env bash
# Run once, as root, on a fresh Debian or Ubuntu box. Idempotent: running it twice
# changes nothing the second time.
#
#   scp -r deploy root@box:/tmp/ && ssh root@box bash /tmp/deploy/provision.sh
set -euo pipefail

DOMAIN="${DOMAIN:-targum.page}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "== packages =="
apt-get update -qq
apt-get install -y -qq curl ca-certificates debian-keyring debian-archive-keyring apt-transport-https sqlite3 ffmpeg

echo "== caddy =="
if ! command -v caddy >/dev/null; then
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy
fi

echo "== user and directories =="
# A service account with no shell and no home to log into. targum parses documents from
# the open internet; it should own as little of this box as possible.
id -u targum >/dev/null 2>&1 || useradd --system --shell /usr/sbin/nologin --home-dir /srv/targum targum
install -d -o targum -g targum -m 0755 /srv/targum
# Everything that cannot be rebuilt lives here, and it is the only path the unit may
# write to. Backups land in it too, then leave the box on a separate schedule.
install -d -o targum -g targum -m 0750 /var/lib/targum /var/lib/targum/targums \
  /var/lib/targum/models /var/lib/targum/cache /var/lib/targum/backups
install -d -o root -g root -m 0750 /etc/targum
install -d -o caddy -g caddy -m 0755 /var/log/caddy

echo "== uv, for the targum user =="
if [ ! -x /usr/local/bin/uv ]; then
  curl -fsSL https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
fi

echo "== yt-dlp, and the token minter that makes it work here =="
# Two halves of one thing, so they are provisioned together and pinned together.
#
# yt-dlp is a subprocess rather than a dependency (see video/youtube.py), and the box
# needs it as much as a laptop does: Library.prepare opens a YouTube paste to a hosted
# fetch, so without it every one of those fails at the button. The distribution's package
# is old enough to be broken by YouTube on arrival; uv is already here, so it installs
# the binary and the plugin into one environment where yt-dlp finds the plugin itself and
# nothing has to pass --plugin-dirs.
#
# As `targum`, not as root, because that is where the tool already lives — the box's
# /usr/local/bin/yt-dlp is a symlink into /srv/targum/.local, put there beside the targum
# tool itself. Installed as root it would be a second copy in root's uv directory,
# shadowed by the symlink, and the plugin would go to the copy nobody runs. That is the
# shape of "preflight says the minter is fine and imports still fail".
# A JavaScript runtime, which YouTube extraction now requires and which is a separate
# thing from the token minter below — the box needed both, and having only one of them
# fails exactly like having neither. yt-dlp says `JS runtimes: none` and then reports the
# bot check, so the runtime is easy to mistake for the minter not working.
#
# deno rather than the node installed below, because deno is the one yt-dlp enables by
# default: with it on the PATH nothing has to pass --js-runtimes, and targum's argv stays
# a description of what it wants rather than of how this box is furnished.
if ! command -v deno >/dev/null; then
  apt-get install -y -qq unzip
  curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- -y --no-modify-path
fi
# Somewhere to write. The unit runs with ProtectHome=true and /var/lib/targum as its only
# writable tree, so a runtime that caches under $HOME would fail there and nowhere else —
# in a build, on a reader's import, rather than here.
install -d -o targum -g targum -m 0750 /var/lib/targum/cache/deno

YTDLP_PY=/srv/targum/.local/share/uv/tools/yt-dlp/bin/python
has_plugin() {
  [ -x "$YTDLP_PY" ] && "$YTDLP_PY" -c \
    'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec("yt_dlp_plugins") else 1)' \
    2>/dev/null
}
if ! has_plugin; then
  # --force because the tool is usually already installed without the plugin, and `uv
  # tool install` is otherwise a no-op that would leave it that way.
  sudo -u targum -H env HOME=/srv/targum UV_TOOL_BIN_DIR=/srv/targum/.local/bin \
    /usr/local/bin/uv tool install --quiet --force yt-dlp --with bgutil-ytdlp-pot-provider
  ln -sfn /srv/targum/.local/bin/yt-dlp /usr/local/bin/yt-dlp
  has_plugin || { echo "   the yt-dlp plugin did not install" >&2; exit 1; }
fi

# The other half. YouTube asks an unfamiliar address to prove it is a browser and a
# datacenter IP is the definition of unfamiliar; measured 2026-09-04, the same video
# answered on a laptop and came back "Sign in to confirm you're not a bot" here. The
# documented alternative is a cookie file, which is a Google session living on the box
# with a ban as its failure mode. This mints a token instead: no account, nothing to ban.
#
# Pinned. The provider tracks YouTube's changes, so a floating clone is a box whose
# YouTube door breaks on somebody else's merge; bumping this is a decision with a
# deploy behind it.
BGUTIL_VERSION="${BGUTIL_VERSION:-1.3.2}"
id -u bgutil >/dev/null 2>&1 || useradd --system --shell /usr/sbin/nologin --home-dir /srv/bgutil bgutil
install -d -o bgutil -g bgutil -m 0755 /srv/bgutil
if ! command -v node >/dev/null || [ "$(node --version | cut -c2- | cut -d. -f1)" -lt 20 ]; then
  # The distribution's own, wherever it is new enough — Ubuntu 26.04 offers Node 22, and
  # a third apt source on a box that has two is a cost with nothing bought. NodeSource
  # only where the archive is genuinely too old, which is Debian 12 and its Node 18.
  apt-get install -y -qq nodejs npm
  if ! command -v node >/dev/null || [ "$(node --version | cut -c2- | cut -d. -f1)" -lt 20 ]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y -qq nodejs
  fi
fi
if [ ! -f /srv/bgutil/server/build/main.js ] \
  || [ "$(cat /srv/bgutil/.version 2>/dev/null || true)" != "$BGUTIL_VERSION" ]; then
  apt-get install -y -qq git
  rm -rf /srv/bgutil/src
  git clone --quiet --single-branch --branch "$BGUTIL_VERSION" \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /srv/bgutil/src
  rm -rf /srv/bgutil/server
  mv /srv/bgutil/src/server /srv/bgutil/server
  rm -rf /srv/bgutil/src
  (cd /srv/bgutil/server && npm ci --silent && npx --yes tsc)
  echo "$BGUTIL_VERSION" > /srv/bgutil/.version
  chown -R bgutil:bgutil /srv/bgutil
fi
# The minter listens on every interface and cannot be told not to — see the file this
# installs. So the port is closed to everything but this machine before the service that
# opens it is ever started, and in that order.
install -o root -g root -m 0644 "$HERE/nftables-targum.conf" /etc/nftables-targum.conf
grep -q 'nftables-targum.conf' /etc/nftables.conf \
  || printf '\ninclude "/etc/nftables-targum.conf"\n' >> /etc/nftables.conf
systemctl enable --now nftables
systemctl reload nftables 2>/dev/null || systemctl restart nftables
nft list table inet targum >/dev/null || { echo "   the 4416 guard is not loaded" >&2; exit 1; }

install -o root -g root -m 0644 "$HERE/bgutil-pot.service" /etc/systemd/system/bgutil-pot.service
systemctl daemon-reload
systemctl enable --now bgutil-pot
# Proof rather than a hope. `targum preflight` knocks on the same door at deploy, but a
# provision that leaves this dead is one whose next symptom is a reader's failed import.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  curl -fsS --max-time 2 http://127.0.0.1:4416/ping >/dev/null && break || sleep 2
done
curl -fsS --max-time 2 http://127.0.0.1:4416/ping \
  || echo "   WARNING: the minter is not answering — journalctl -u bgutil-pot"

echo "== configuration =="
if [ ! -f /etc/targum/targum.env ]; then
  install -o root -g root -m 0600 "$HERE/targum.env.example" /etc/targum/targum.env
  echo "   wrote /etc/targum/targum.env — FILL IT IN before starting"
fi
install -o root -g root -m 0644 "$HERE/targum.service" /etc/systemd/system/targum.service
sed "s/targum\.page/$DOMAIN/g" "$HERE/Caddyfile" > /etc/caddy/Caddyfile
systemctl daemon-reload
caddy validate --config /etc/caddy/Caddyfile >/dev/null
# validate ran as root and may have created the log file root-owned; the service runs as caddy.
chown -R caddy:caddy /var/log/caddy
systemctl reload caddy || systemctl restart caddy

echo "== nightly backup =="
# Where the copies go is still a decision, but it is now one line rather than a project:
# fill in TARGUM_BACKUP_TO with an rclone remote and tonight's copy leaves the box.
#
# Here rather than in targum.env because that file is 0600 root and this runs as targum,
# which cannot read it — and a destination is not a secret. The credentials are rclone's,
# in ~targum/.config/rclone/rclone.conf, where only targum can read them.
#
# stderr is deliberately not swallowed. A copy that did not leave is exactly the night
# somebody needs to hear about, and `>/dev/null 2>&1` is how a backup quietly stops
# working for four months.
# --store, named. Without it `targum backup` falls back to ~/.targum/targum.db, the
# HOME default, which on this box is an empty leftover: from the day the box went up
# until 2026-09-04 every nightly copy was a database holding 0 accounts and 0 words
# while the real one at /var/lib/targum held 3,069. It said "checked" and exited 0 each
# time, because it had faithfully copied the wrong file.
#
# Through systemd-run with the service's own EnvironmentFile, so the copy sees
# TARGUM_CACHE_DIR and the cache is copied too — the paid inventory this module calls
# the second thing that cannot be rebuilt. Run directly as targum it saw an empty cache
# and archived nothing, silently, the same way.
#
# Hence root rather than targum: only root may systemd-run --uid. And no redirect at
# all — there is no MTA, so cron discards whatever it is handed and two failed nights
# left no trace anywhere on the box. systemd-run puts it in the journal instead:
# `journalctl -u targum-backup`.
cat > /etc/cron.d/targum-backup <<'CRON'
MAILTO=root
TARGUM_BACKUP_TO=
0 4 * * * root systemd-run --quiet --wait --collect --unit=targum-backup --uid=targum --gid=targum --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env /usr/local/bin/targum backup --keep 14 --store /var/lib/targum/targum.db --out /var/lib/targum/backups
CRON
chmod 0644 /etc/cron.d/targum-backup

cat <<EOF

Provisioned. Three things left, none of them this script's to do:

  1. Fill in /etc/targum/targum.env    (chmod 600, secrets only here)
  2. Point $DOMAIN's A record at this box, and wait for it
  3. From your laptop:  TARGUM_HOST=root@$DOMAIN ./deploy/deploy.sh

And to get the backups off this disk, which is the one failure the nightly copy
does not cover:

  apt-get install -y rclone
  sudo -u targum -H rclone config          # add a remote; put a crypt in front of it
  sudo -u targum -H rclone lsd <remote>:   # prove it answers
  editor /etc/cron.d/targum-backup         # set TARGUM_BACKUP_TO=<remote>:targum/backups

A backup holds addresses and every word somebody has kept, so the remote wants to be
an rclone crypt remote — encryption belongs there and not in targum. Check it worked with:

  sudo -u targum -H targum backup --to <remote>:targum/backups \
    --store /var/lib/targum/targum.db --out /var/lib/targum/backups
EOF
