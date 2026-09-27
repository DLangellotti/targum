#!/usr/bin/env bash
# Prove the newest off-box copy comes back (targum-internal#1). On the laptop, never the box:
# the box cannot open these files, which is the point of sealing them.
#
#   brew install age rclone
#   op run --env-file deploy/box.env.op -- \
#     env TARGUM_BACKUP_TO=backblaze:<bucket> ./deploy/restore-drill.sh
#
# `op run` puts the bucket key (RCLONE_CONFIG_BACKBLAZE_*) in this process's environment
# and nowhere else. The age identity — the private key — is read from 1Password with
# TARGUM_AGE_IDENTITY_REF=op://..., or from a file with TARGUM_AGE_IDENTITY=<path>; by
# reference it never touches the disk.
#
# A copy that comes down, decrypts, passes an integrity check and answers a count is a
# backup. Anything else is a directory of ciphertext somebody is paying to store.
set -euo pipefail

TO="${TARGUM_BACKUP_TO:?set TARGUM_BACKUP_TO, e.g. backblaze:targum-backups}"
FOLDER="${1:-daily}"
# The remote's type is a setting rather than a secret, so it is not in box.env.op.
export RCLONE_CONFIG_BACKBLAZE_TYPE="${RCLONE_CONFIG_BACKBLAZE_TYPE:-b2}"

for tool in age rclone sqlite3 gunzip; do
  command -v "$tool" >/dev/null || { echo "no $tool here: brew install $tool" >&2; exit 1; }
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

newest="$(rclone lsf "$TO/$FOLDER" --include 'targum-*.db.gz.age' | sort | tail -1)"
if [ -z "$newest" ]; then
  echo "nothing at $TO/$FOLDER — no night has left the box yet" >&2
  exit 1
fi
echo "== $TO/$FOLDER/$newest =="
rclone copyto "$TO/$FOLDER/$newest" "$work/$newest"

if [ -n "${TARGUM_AGE_IDENTITY_REF:-}" ]; then
  age --decrypt -i <(op read "$TARGUM_AGE_IDENTITY_REF") "$work/$newest" | gunzip >"$work/targum.db"
else
  IDENTITY="${TARGUM_AGE_IDENTITY:-$HOME/.config/targum/backup-age.key}"
  [ -f "$IDENTITY" ] || { echo "no identity at $IDENTITY; set TARGUM_AGE_IDENTITY_REF" >&2; exit 1; }
  age --decrypt -i "$IDENTITY" "$work/$newest" | gunzip >"$work/targum.db"
fi

said="$(sqlite3 "$work/targum.db" 'PRAGMA integrity_check')"
if [ "$said" != "ok" ]; then
  echo "integrity check said: $said" >&2
  exit 1
fi
for table in person word phrase doc; do
  printf '   %-7s %s\n' "$table" "$(sqlite3 "$work/targum.db" "SELECT COUNT(*) FROM $table")"
done
echo "   decrypted, checked and counted. Compare the counts with the box:"
echo "   ssh root@targum.page \"sqlite3 -readonly /var/lib/targum/targum.db 'SELECT COUNT(*) FROM person'\""
