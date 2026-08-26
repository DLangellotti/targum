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
apt-get install -y -qq curl ca-certificates debian-keyring debian-archive-keyring apt-transport-https sqlite3

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

echo "== configuration =="
if [ ! -f /etc/targum/targum.env ]; then
  install -o root -g root -m 0600 "$HERE/targum.env.example" /etc/targum/targum.env
  echo "   wrote /etc/targum/targum.env — FILL IT IN before starting"
fi
install -o root -g root -m 0644 "$HERE/targum.service" /etc/systemd/system/targum.service
sed "s/targum\.page/$DOMAIN/g" "$HERE/Caddyfile" > /etc/caddy/Caddyfile
systemctl daemon-reload
caddy validate --config /etc/caddy/Caddyfile >/dev/null && systemctl reload caddy || systemctl restart caddy

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
cat > /etc/cron.d/targum-backup <<'CRON'
MAILTO=root
TARGUM_BACKUP_TO=
0 4 * * * targum /usr/local/bin/targum backup --keep 14 --out /var/lib/targum/backups >/dev/null
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
an rclone `crypt` — encryption belongs there and not in targum. Check it worked with:

  sudo -u targum -H targum backup --to <remote>:targum/backups \
    --store /var/lib/targum/targum.db --out /var/lib/targum/backups
EOF
