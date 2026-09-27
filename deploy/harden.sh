#!/usr/bin/env bash
# Harden the box (targum-internal#9): swap, security updates, password login off, and a
# firewall. Run as root on the box itself, after provision.sh:
#
#   scp -r deploy root@targum.page:/tmp/ && ssh root@targum.page bash /tmp/deploy/harden.sh --dry-run
#   ssh root@targum.page bash /tmp/deploy/harden.sh
#
# then, from a NEW terminal, within ten minutes:
#
#   ssh root@targum.page bash /tmp/deploy/harden.sh --confirm
#
# Every step looks before it touches, so a second run changes nothing. --dry-run does
# every look and none of the touches, and says what it would have changed.
#
# The two steps that can lock the door behind you are ordered so they cannot:
#
#   sshd  — the drop-in is checked with `sshd -t` before sshd is told about it, a failed
#           check puts the old file back, and sshd is reloaded, never restarted, so the
#           session running this survives either way. It refuses to start at all if root
#           has no key, which is the one way "password login off" is a lock-out.
#   wall  — the SSH accept and the drop policy live in one file and load as one nft
#           transaction; `nft -c` checks it first; and a rollback that takes the wall
#           down again is armed BEFORE it goes up. If you cannot get back in, wait ten
#           minutes and the box opens itself. --confirm, from a fresh session that proves
#           the way in still works, disarms it.
#
# If SSH does break anyway: the Hetzner Cloud console (console.hetzner.cloud → the server
# → the >_ console button) is a root shell that goes through neither sshd nor the
# firewall. From there:
#
#   rm /etc/ssh/sshd_config.d/00-targum.conf && systemctl reload ssh
#   /usr/local/sbin/targum-wall-rollback
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DRY=0
MODE=apply
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --confirm) MODE=confirm ;;
    -h | --help)
      sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown argument: $arg (try --dry-run, --confirm, --help)" >&2
      exit 2
      ;;
  esac
done

SWAPFILE=/swapfile
SWAP_SIZE=2G
SSHD_DROPIN=/etc/ssh/sshd_config.d/00-targum.conf
AUTO_UPGRADES=/etc/apt/apt.conf.d/20auto-upgrades
WALL_SRC="$HERE/nftables-targum-wall.conf"
WALL=/etc/nftables-targum-wall.conf
WALL_INCLUDE='include "/etc/nftables-targum-wall.conf"'
NFT_CONF=/etc/nftables.conf
ROLLBACK=/usr/local/sbin/targum-wall-rollback
ROLLBACK_UNIT=targum-wall-rollback
ROLLBACK_AFTER=10min

CHANGED=0

say() { printf '%s\n' "$*"; }
die() {
  printf '\n  REFUSED: %s\n\n' "$*" >&2
  exit 1
}

# Do it, or in a dry run say it would have been done. Every change goes through here or
# through put_file, so --dry-run is honest by construction rather than by care.
act() {
  CHANGED=1
  if [ "$DRY" = 1 ]; then
    say "   would run: $*"
  else
    say "   running: $*"
    "$@"
  fi
}

# Write $2 with the text on stdin, mode $1, only when it differs from what is there.
# Returns 0 when it wrote (or would have written), 1 when the file was already right.
put_file() {
  local mode="$1" dest="$2" tmp
  tmp="$(mktemp)"
  cat >"$tmp"
  if [ -f "$dest" ] && cmp -s "$tmp" "$dest"; then
    rm -f "$tmp"
    return 1
  fi
  CHANGED=1
  if [ "$DRY" = 1 ]; then
    say "   would write $dest:"
    sed 's/^/      | /' "$tmp"
    rm -f "$tmp"
  else
    say "   writing $dest"
    install -o root -g root -m "$mode" "$tmp" "$dest"
    rm -f "$tmp"
  fi
  return 0
}

# ---------------------------------------------------------------------------------------
# Is this the box? Everything below edits sshd and the firewall of whatever machine it is
# standing on, so it proves it is on the one it was written for before it looks at
# anything else — a laptop, a CI runner and a container all stop here.
# ---------------------------------------------------------------------------------------
[ "$(uname -s)" = Linux ] || die "this is $(uname -s), not the box. harden.sh runs ON targum.page, as root: ssh root@targum.page bash /tmp/deploy/harden.sh"
[ "$(id -u)" = 0 ] || die "not root. It edits sshd and the firewall; run it as root on the box."
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}" in
  ubuntu | debian) ;;
  *) die "this is ${ID:-an unknown system}, and the box is Ubuntu." ;;
esac
[ -d /run/systemd/system ] || die "no systemd here, so this is a container or a chroot, not the box."
if [ ! -f /etc/systemd/system/targum.service ] || [ ! -d /etc/targum ]; then
  die "no targum.service or /etc/targum, so this box was never provisioned. Run provision.sh first; harden.sh finishes a targum box, it does not make one."
fi
[ -f "$WALL_SRC" ] || die "$WALL_SRC is missing; copy the whole deploy/ directory, not the script alone."

# ---------------------------------------------------------------------------------------
# --confirm: you are in, from a fresh session, so the wall can stay.
# ---------------------------------------------------------------------------------------
if [ "$MODE" = confirm ]; then
  if systemctl is-active --quiet "$ROLLBACK_UNIT.timer"; then
    if [ "$DRY" = 1 ]; then
      say "would disarm the firewall rollback ($ROLLBACK_UNIT.timer)"
    else
      systemctl stop "$ROLLBACK_UNIT.timer"
      say "Rollback disarmed. The firewall stays."
    fi
  else
    say "No rollback armed. Nothing to confirm."
  fi
  sshd -T 2>/dev/null | grep -Ei '^(passwordauthentication|permitrootlogin) ' | sed 's/^/   sshd: /' || true
  if nft list table inet targum_wall >/dev/null 2>&1; then say "   firewall: up"; else say "   firewall: down"; fi
  exit 0
fi

[ "$DRY" = 1 ] && say "DRY RUN — looks at everything, changes nothing." && say ""

# ---------------------------------------------------------------------------------------
say "== swap =="
# So a build that peaks is slow rather than killed (the DICTA OOMs of 2026-09-03). The
# box got a 4G swapfile by hand before this script existed; that one is kept, and only a
# box with no swap at all is given one.
# ---------------------------------------------------------------------------------------
if [ -n "$(swapon --show --noheadings 2>/dev/null)" ]; then
  say "   swap is on: $(swapon --show --noheadings | awk '{print $1, $3}' | paste -sd, -)"
else
  if [ ! -f "$SWAPFILE" ]; then
    act fallocate -l "$SWAP_SIZE" "$SWAPFILE"
    act chmod 600 "$SWAPFILE"
    act mkswap "$SWAPFILE"
  fi
  act swapon "$SWAPFILE"
fi
# On at boot as well as now. Only for our own file: a box whose swap is something else
# already has its own line.
if [ -f "$SWAPFILE" ] && ! grep -qE "^[[:space:]]*${SWAPFILE}[[:space:]]" /etc/fstab; then
  CHANGED=1
  if [ "$DRY" = 1 ]; then
    say "   would add to /etc/fstab: $SWAPFILE none swap sw 0 0"
  else
    printf '%s none swap sw 0 0\n' "$SWAPFILE" >>/etc/fstab
    say "   added $SWAPFILE to /etc/fstab"
  fi
fi

# ---------------------------------------------------------------------------------------
say "== security updates =="
# unattended-upgrades, on the distribution's default origins, which include -security.
# ---------------------------------------------------------------------------------------
if ! dpkg-query -W -f='${Status}' unattended-upgrades 2>/dev/null | grep -q 'install ok installed'; then
  act apt-get install -y -qq unattended-upgrades
fi
put_file 0644 "$AUTO_UPGRADES" <<'APT' || say "   $AUTO_UPGRADES already on"
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT
if [ -f /etc/apt/apt.conf.d/50unattended-upgrades ] \
  && ! grep -qE '^[[:space:]]*"[^"]*-security";' /etc/apt/apt.conf.d/50unattended-upgrades; then
  say "   WARNING: 50unattended-upgrades names no -security origin; it is on but may install nothing"
fi

# ---------------------------------------------------------------------------------------
say "== ssh: keys only =="
# Password login off for everyone, and root by key only. `00-` so it sorts before any
# drop-in cloud-init writes: sshd takes the first value it reads for a key.
# ---------------------------------------------------------------------------------------
# The one way this step locks the door: shutting passwords off on a box where root has no
# key. That box is not hardened by this script; it is refused by it.
grep -qE '^[[:space:]]*(ssh-|ecdsa-|sk-)' /root/.ssh/authorized_keys 2>/dev/null \
  || die "/root/.ssh/authorized_keys holds no key. Turning passwords off would leave no way in. Add a key, log in with it, then run this again."
grep -qE '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config \
  || die "/etc/ssh/sshd_config does not include sshd_config.d/*.conf, so a drop-in there would do nothing."

# Whatever is there now is kept aside until sshd -t has passed the replacement.
SSHD_BACKUP=""
if [ "$DRY" = 0 ] && [ -f "$SSHD_DROPIN" ]; then
  SSHD_BACKUP="$(mktemp)"
  cp -p "$SSHD_DROPIN" "$SSHD_BACKUP"
fi
if put_file 0644 "$SSHD_DROPIN" <<'SSHD'; then
# Written by deploy/harden.sh (targum-internal#9). Keys only.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
SSHD
  if [ "$DRY" = 1 ]; then
    say "   would check it with: sshd -t"
    say "   would reload (not restart) ssh"
  else
    # Check before reload. put_file has already written the file, so sshd -t is reading
    # exactly what a reload would; if it objects, the file goes and sshd never hears of it.
    if ! sshd -t; then
      rm -f "$SSHD_DROPIN"
      [ -n "$SSHD_BACKUP" ] && mv "$SSHD_BACKUP" "$SSHD_DROPIN"
      die "sshd -t rejected the config. The drop-in was removed and sshd was not touched."
    fi
    # Reload, never restart: a reload re-reads the config for new connections and leaves
    # every open session — this one included — exactly where it is. With socket
    # activation the service may be idle, and then the next connection reads the new
    # file anyway.
    if systemctl is-active --quiet ssh.service; then
      systemctl reload ssh.service
    fi
    say "   reloaded ssh"
  fi
  [ -z "$SSHD_BACKUP" ] || rm -f "$SSHD_BACKUP"
else
  [ -z "$SSHD_BACKUP" ] || rm -f "$SSHD_BACKUP"
  say "   $SSHD_DROPIN already in place"
fi
if [ "$DRY" = 0 ]; then
  effective="$(sshd -T 2>/dev/null | grep -Ei '^(passwordauthentication|permitrootlogin) ' | sort | paste -sd' ' -)" || true
  say "   effective: $effective"
  case "$effective" in
    *"passwordauthentication no"*"permitrootlogin prohibit-password"*) ;;
    *) die "sshd -T does not say keys only ($effective). Something read earlier overrides $SSHD_DROPIN." ;;
  esac
fi

# ---------------------------------------------------------------------------------------
say "== firewall =="
# SSH, 80 and 443 in; everything else out. See nftables-targum-wall.conf for why nft
# rather than ufw, and for why the rule and the policy are one file.
# ---------------------------------------------------------------------------------------
command -v nft >/dev/null || act apt-get install -y -qq nftables
[ -f "$NFT_CONF" ] || die "$NFT_CONF is missing; provision.sh writes the include this step extends."

# The way back down, written before the way up. A root script rather than a line in the
# timer, so the console recovery above is one command and the same one the timer runs.
put_file 0755 "$ROLLBACK" <<ROLL || true
#!/bin/sh
# Written by deploy/harden.sh. Takes the targum firewall down, now and at boot, and
# leaves the 4416 guard in nftables-targum.conf where it is.
sed -i '\\|^$WALL_INCLUDE\$|d' $NFT_CONF
nft delete table inet targum_wall 2>/dev/null || true
echo "targum firewall down"
ROLL

wall_changed=0
put_file 0644 "$WALL" <"$WALL_SRC" && wall_changed=1
if ! grep -qxF "$WALL_INCLUDE" "$NFT_CONF"; then
  wall_changed=1
  CHANGED=1
  if [ "$DRY" = 1 ]; then
    say "   would add to $NFT_CONF: $WALL_INCLUDE"
  else
    printf '\n%s\n' "$WALL_INCLUDE" >>"$NFT_CONF"
  fi
fi
nft list table inet targum_wall >/dev/null 2>&1 || wall_changed=1

if [ "$wall_changed" = 0 ]; then
  say "   firewall already up"
elif [ "$DRY" = 1 ]; then
  CHANGED=1
  say "   would check the whole ruleset with: nft -c -f $NFT_CONF"
  say "   would arm $ROLLBACK_UNIT to take the wall down in $ROLLBACK_AFTER"
  say "   would load it: systemctl reload nftables"
else
  # 1. Check. The whole of nftables.conf, as the reload will read it, without applying.
  if ! nft -c -f "$NFT_CONF"; then
    "$ROLLBACK" >/dev/null
    die "nft -c rejected the ruleset. Nothing new was loaded, and the wall is off: its include is out of $NFT_CONF."
  fi
  # 2. Arm the rollback. If the wall shuts you out, it comes down by itself.
  systemctl stop "$ROLLBACK_UNIT.timer" 2>/dev/null || true
  systemctl reset-failed "$ROLLBACK_UNIT.service" 2>/dev/null || true
  systemd-run --quiet --unit="$ROLLBACK_UNIT" --on-active="$ROLLBACK_AFTER" "$ROLLBACK"
  # 3. Load. nftables.conf is one transaction: flush and re-add, SSH rule and drop policy
  #    together, so there is no window with one and not the other.
  systemctl enable --quiet nftables
  systemctl reload nftables 2>/dev/null || systemctl restart nftables
  nft list table inet targum_wall >/dev/null || die "the wall did not load; see journalctl -u nftables"
  say "   firewall up, and it comes down again in $ROLLBACK_AFTER unless confirmed"
fi

say ""
if [ "$DRY" = 1 ]; then
  if [ "$CHANGED" = 1 ]; then
    say "Dry run: the lines above are what a real run would change."
  else
    say "Dry run: nothing to change. The box is already hardened."
  fi
  exit 0
fi
if systemctl is-active --quiet "$ROLLBACK_UNIT.timer"; then
  cat <<EOF
Done, with one thing left and a clock on it.

  Leave THIS session open. From a NEW terminal, within $ROLLBACK_AFTER:

    ssh root@targum.page bash $HERE/harden.sh --confirm

  If that connects, the key works, the password door is shut and the wall lets you
  in; --confirm keeps the wall. If it does not connect, do nothing: the wall takes
  itself down when the time runs out, and this session is still here to look.
EOF
else
  if [ "$CHANGED" = 1 ]; then say "Done."; else say "Nothing to change. The box is already hardened."; fi
  say "Log out and ssh back in before trusting it: if you still get in, the key works."
fi
