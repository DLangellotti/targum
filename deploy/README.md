# deploy

targum behind Caddy on one box. Loopback only; Caddy terminates TLS.

Once, as root on a fresh Debian or Ubuntu box:

```
scp -r deploy root@box:/tmp/ && ssh root@box bash /tmp/deploy/provision.sh
```

Then fill in `/etc/targum/targum.env` and point the A record at the box.

Then harden it (targum-internal#9): swap if there is none, unattended security updates,
SSH by key only, and a firewall that lets in 22, 80 and 443 and nothing else.

```
scp -r deploy root@box:/tmp/ && ssh root@box bash /tmp/deploy/harden.sh --dry-run
ssh root@box bash /tmp/deploy/harden.sh
ssh root@box bash /tmp/deploy/harden.sh --confirm     # from a NEW terminal, within 10 min
```

The firewall arms a rollback before it goes up: if the new session cannot get in, do
nothing, and the wall takes itself down after ten minutes. If SSH is lost anyway, the
Hetzner Cloud console is a root shell that goes through neither sshd nor the firewall;
`rm /etc/ssh/sshd_config.d/00-targum.conf && systemctl reload ssh` and
`/usr/local/sbin/targum-wall-rollback` undo the two halves. The script refuses to run
anywhere but a provisioned targum box, and refuses to turn passwords off while root has
no key.

Coming back the other way — the box is gone and there is a backup — is
[`RESTORE.md`](RESTORE.md). It was run once on 2026-09-04 rather than written from
imagination, and it says what came back.

Every time after that, from here:

```
TARGUM_HOST=root@targum.page ./deploy/deploy.sh
```

It runs the checks, builds a wheel, installs it, restarts, and fails loudly if
`/health` does not come back. `targum preflight` is the same gate on the box, and
systemd runs it before every start.

Secrets live in the `targum` vault in 1Password. `deploy.sh` writes the lines named in
`box.env.op` into `/etc/targum/targum.env` on every deploy; everything else in that file
is a setting, and is edited on the box as before.

Daily learning is not indexed until `TARGUM_INDEX_DAILY=1` is set on the box, and that
is a separate switch from `TARGUM_INDEX_PARASHA`. Sharing one would mean that inviting
crawlers to fifty-four portions — a corpus that is finished, and the same fifty-four every
year — also invited them to four pages that change every night.

**`targum parasha build` must run with the main checkout as its working directory.** The
recordings root is `cwd/targum-out/recordings`, so a build from a worktree finds no
chanted audio and ships the portions without it, silently — caught on 2026-09-20 only by
diffing against a backup. `--out` does not govern it and neither does
`TARGUM_PARASHA_DIR`.

**A rebuild does not reach every reader.** `targum rebuild` rewrites what has artifacts
beside it; the parasha corpus and the daily window keep none, and the four shared Russian
texts are skipped by design. After any change to reader CSS or JS those stay as they were
cut, and `deploy.sh` used to say "done" over them — three times. `targum preflight` now
counts them (`stale readers`), so the gap is a line in the deploy rather than something
found weeks later. Re-cut and ship what it names.

Daily learning. `ship-daily.sh` carries the rolling window of `/mishna-yomi` and its
three siblings. Unlike `ship-parasha.sh` it wants running **nightly**, and that is the
whole difference between them: the parasha's corpus is the same fifty-four readings every
year and shipping it moves a pointer, while a learning cycle is two thousand days of which
fourteen are built. A box a month stale serves a page headed "today" over the wrong
reading. Build first (`targum daily build`), then ship; both are free and neither fetches
a text.

Video notes. A video reader's folder carries `video/part-NNN.mp4` sidecars — 50–100 MB
per part — so a shipped folder is gigabytes where an audio one was tens of megabytes;
budget the box's disk and the rsync accordingly (`ship-audio.sh` copies whole folders).
Caddy needs no change: chunked uploads stay 8 MiB under the 48 MB body ceiling, and
responses stream, so the reader's Range requests pass through. Hosted video transcodes
on the box at roughly real-time ÷ 4 per part. The box never fetches from YouTube —
that import is CLI-only, on purpose.

## A test account

An account for trying targum as a new reader meets it, as often as you like: signing
out of it empties it — words, progress, what it said on arrival, conversations, lists,
connections and the texts it built — and keeps the account and its invitation, so the
next sign-in is a first visit. Made on the box:

```
targum test-account tester@example.com
```

It is refused for an address that already has an account: a test account is emptied
the next time it signs out, so a real reader's account must never become one. For
testing without reading the address's mail, `--link` prints a one-time sign-in link, and
only for a test account:

```
ssh root@targum.page 'set -a; . /etc/targum/targum.env; set +a; targum test-account tester@example.com --link'
```

The link opens the ordinary sign-in page; press its button. `targum test-account` with
no address lists them. What a test account builds is spent like anybody's, under the same
rails, and it shows in the usage figures.

## Backups off the box

`targum-backup.timer` runs `targum backup` at 04:00 UTC (it replaced the cron line in
`/etc/cron.d/targum-backup`, which `deploy.sh` removes). It takes a consistent SQLite
snapshot through the backup API, runs `PRAGMA integrity_check` on it, archives the
cache and the weekly, and keeps fourteen of each beside the database. That much is what
it always did.

With `TARGUM_BACKUP_TO` **and** `TARGUM_BACKUP_AGE_RECIPIENT` set in `targum.env` it
also gzips the database, encrypts each file with [age](https://age-encryption.org) to
that public key, and sends the three to `<remote>/daily` — and on Sundays to
`<remote>/weekly` as well — through rclone, then lists the folder back and compares
sizes. The box holds only the public key, so it can write a copy and cannot read one.
Neither set: it says "not configured" and exits 0. One set: it fails, because the other
reading is sending plaintext. A failed night mails `TARGUM_ALERT_TO`.

Retention is the bucket's, not the box's: two lifecycle rules expire `daily/` and
`weekly/`, so the box's key needs no right to delete.

Switching it on:

1. **Bucket** (Backblaze, a different company from the box on purpose). Private, default
   encryption (SSE-B2) on. Lifecycle rules, custom:
   `daily/` — hide after 30 days, delete 1 day after hiding;
   `weekly/` — hide after 182 days, delete 1 day after hiding.
2. **Key**, restricted to that bucket and with no delete. The web console's "Read and
   Write" includes `deleteFiles`, so make it with the b2 CLI:
   `b2 key create --bucket <bucket> targum-box listBuckets,listFiles,readFiles,writeFiles`.
   The applicationKey is shown once: into 1Password, item `Backblaze` in the `targum`
   vault, fields `keyID` and `applicationKey`.
3. **age keypair, on the laptop**: `age-keygen -o backup-age.key`. It prints the public
   key (`age1...`). The file is the private key: put it in 1Password (same vault, its own
   item), keep a paper copy somewhere that is not the laptop, then `rm backup-age.key`.
   It never goes on the box.
4. **Secrets**, in `deploy/box.env.op`, using the item from step 2:
   `RCLONE_CONFIG_BACKBLAZE_ACCOUNT` and `RCLONE_CONFIG_BACKBLAZE_KEY`, each a reference
   to that item's field.
5. **Settings**, in `/etc/targum/targum.env` on the box:
   ```
   RCLONE_CONFIG_BACKBLAZE_TYPE=b2
   TARGUM_BACKUP_TO=backblaze:<bucket>
   TARGUM_BACKUP_AGE_RECIPIENT=age1...
   ```
6. Deploy (it installs `age` and `rclone` if missing), then take one by hand rather than
   waiting for 04:00: `systemctl start targum-backup && journalctl -u targum-backup -n 30`.
   It should end "Sealed and sent to backblaze:<bucket>/daily".
7. **The drill** (targum-internal#1), from this checkout on the laptop:
   ```
   brew install age rclone
   op run --env-file deploy/box.env.op -- env TARGUM_BACKUP_TO=backblaze:<bucket> \
     TARGUM_AGE_IDENTITY_REF='op://targum/<age item>/<field>' ./deploy/restore-drill.sh
   ```
   It downloads the newest `daily/targum-*.db.gz.age`, decrypts, integrity-checks and
   counts rows. Then the rest of [`RESTORE.md`](RESTORE.md) runs against that file.

## Alerts

`targum-health.timer` runs `targum watch-health` every five minutes. It knocks on
`TARGUM_PUBLIC_ADDRESS/health` (or `TARGUM_HEALTH_URL`) and mails `TARGUM_ALERT_TO`
through the same SMTP settings as a sign-in link: once after two failed checks in a row,
again every six hours while it stays down, and once when it answers. State lives in
`/var/lib/targum/health-watch.json`. Without `TARGUM_ALERT_TO` it logs "not configured".

Switching it on is one line in `/etc/targum/targum.env` — `TARGUM_ALERT_TO=<address>` —
and nothing else; the timer is already running. To see both mails arrive without
breaking anything, knock twice on a path that is not `/health`, then once on the real
one, against a scratch state file:

```
drill() { systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum \
  --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env \
  /usr/local/bin/targum watch-health --state /var/lib/targum/health-drill.json "$@"; }
drill --url https://targum.page/no-such-page; drill --url https://targum.page/no-such-page
drill && rm /var/lib/targum/health-drill.json
```

It watches from the box, so a box that is off or unreachable sends nothing. An outside
monitor (UptimeRobot, the other half of targum-internal#20) is what hears that silence.
