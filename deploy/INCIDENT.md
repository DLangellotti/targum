# The first ten minutes

Something is wrong on targum.page: a mail from the health watch, a reader saying so, a
deploy that ended badly. This is what to do before deciding anything. Written
2026-10-22 (targum-internal#482) against the code and, read-only, the box. **First run
as a drill on 2026-10-22**: the commands below took three seconds, and the preflight with
connections about two minutes. The output is on #482.

Everything in "Where to look" is read-only and needs nobody's word. Everything that
changes the box (a restart, a rollback, a restore, a key) waits for David's word, in the
moment, unless he is the one doing it.

## Minute 0: who is told

- **David**, first and directly: in his chat if a session is open, and in #targum
  (`r00ms send targum --as <seat> --to claude "…"`, which reaches him through the lead).
  One line: what is broken, since when, what a reader sees. No reader's words or address
  in the room or on a card; "a reader on /add" is enough.
- **`TARGUM_ALERT_TO`** (set in `/etc/targum/targum.env`, confirmed 2026-10-22) already
  gets three kinds of mail without anybody sending them: the health watch (after two
  failed checks five minutes apart, every six hours while down, once on recovery), a
  provider out of credit (once per provider per four hours, from the process that met
  it), and the weekly not out by Monday noon UTC. If one of those started this, David
  has it already; say what you are looking at so two people do not look at the same
  thing.
- **The outside monitor** (UptimeRobot, deploy/README.md "Alerts") is the only thing that
  hears a box that is off: the health watch runs on the box and goes quiet with it.

Write down the time (UTC) you started. Everything after is measured from it.

## Minutes 1–5: where to look

From the laptop, in this order. Each line says what healthy looks like.

**1. Does it answer, from outside?**

```sh
curl -sS -m 10 -o /dev/null -w '%{http_code} %{time_total}s\n' https://targum.page/
curl -sS -m 10 https://targum.page/health
curl -sS -m 10 https://targum.page/ | grep -o 'data-build="[^"]*"'
```

Healthy: `200` in well under a second; `{"ok": true, "store": true, "queue": 0, ...}`;
the build stamp of the last deploy. `queue` is what is waiting for a worker; a `queue`
that climbs while nothing finishes is a stuck worker, not a busy box.

**2. Can we reach the box at all?**

```sh
ssh -o ConnectTimeout=10 root@targum.page 'uptime; systemctl is-active targum caddy targum-deploy'
```

Healthy: an uptime line, then `active`, `active`, `inactive`. `targum-deploy` `active`
means a deploy's rebuild is still running (it can be hours; see "Never").

**3. What the service says.**

```sh
ssh root@targum.page 'systemctl status targum --no-pager | head -15; journalctl -u targum --since "-30 min" --no-pager | tail -80'
ssh root@targum.page 'systemctl show targum -p ActiveEnterTimestamp -p NRestarts'
```

Look for a traceback, a preflight `FAIL` (the unit runs `targum preflight --no-connect`
before every start, and a failure stops the start), `Start request repeated too quickly`
(five failures in five minutes: systemd has stopped trying), or a provider's error text.
`NRestarts` climbing is a crash loop.

**4. Disk, memory, swap, and the kernel.**

```sh
ssh root@targum.page 'df -h / ; free -h; swapon --show; journalctl -k --since "-2 h" --no-pager | grep -iE "oom|killed process" | tail'
```

Healthy on 2026-10-22: `/` at 36% of 150 G; 7.6 Gi memory with most of it cache; 4 G
swapfile, barely used; no OOM lines. A full disk stops SQLite writing (sign-ins and saved
words fail first). An OOM kill names the process: it has been DICTA batching long
transcripts before, and a rebuild beside a busy service.

**5. The backups are there.**

```sh
ssh root@targum.page 'ls -la /var/lib/targum/targum.db* ; ls -lt /var/lib/targum/backups/ | head -8; journalctl -u targum-backup -n 5 --no-pager'
```

Healthy: last night's `targum-YYYYMMDD-0400NN.db`, `cache-…zip` and `weekly-…zip` in
`/var/lib/targum/backups/`, the backup unit `Finished` at about 04:00 UTC, and the
`targum.db.before-*` copy from the last deploy. Knowing these exist is what makes the
later decisions calm. Do not open the copies in place (see [`ROLLBACK.md`](ROLLBACK.md)
step 4a).

**6. What readers are getting, from Caddy.**

```sh
ssh root@targum.page 'tail -n 2000 /var/log/caddy/targum.log | grep -o "\"status\":[0-9]*" | sort | uniq -c | sort -rn'
ssh root@targum.page 'journalctl -u caddy --since "-30 min" --no-pager | tail -20'
```

Healthy: mostly `200`, some `304`/`302`/`404`. A run of `502` is Caddy up with targum
down behind it; `504` is targum too slow to answer. The access log holds readers' IP
addresses and paths: read it on the box, never paste it into a card or the room.

**7. The deploy, if there was one in the last day.**

```sh
ssh root@targum.page 'journalctl -u targum-deploy --since "-24 h" --no-pager | tail -20'
```

When it started and whether it `Deactivated successfully` or `Failed`. A failed one stays
`failed` until the next deploy clears it.

## Minutes 5–8: which kind of trouble it is

| What you see | It is | First move |
|---|---|---|
| No answer from `curl`, **and** `ssh` times out | **The box or its network.** | Hetzner Cloud console: is the server running? Its status page: is the location down? Try from another network (a phone off Wi-Fi). If the console shows it running and nothing reaches it, the firewall or the provider's network; the console's own shell goes through neither (deploy/README.md). |
| No answer from `curl` from here, but `ssh` works and `curl` on the box works (`ssh root@targum.page 'curl -sS -m 5 http://127.0.0.1:8420/health'`) | **The network between**: DNS, TLS, a path from this network. | `dig +short targum.page` should give the box's address; try from another network. A hotel network resets SSH and can do the same to HTTPS. Nothing on the box to change. |
| `502` from Caddy; `systemctl is-active targum` says `failed` or `activating` | **The service is down** on a running box. | The journal (step 3) says why. After a deploy: [`ROLLBACK.md`](ROLLBACK.md). Not after a deploy: disk, memory, the env file. |
| `/health` `"ok": true`, but builds or chat fail for readers | **A model provider**, almost always. | `journalctl -u targum --since "-30 min" \| grep -iE "credit\|quota\|billing\|overloaded\|529\|503\|rate.limit\|timed out"`, then the provider's status page (status.anthropic.com, status.openai.com, the Google Cloud status page for Gemini and Vertex). |
| A mail "targum: <provider> is out of credit" | **Out of credit.** | Top up that provider's console (David's accounts). Nothing on the box needs changing; readers are already told it is on our side. `/var/lib/targum/credit-watch.json` holds when each was last mailed; it appears only with the first credit mail, so a box without it is normal. |
| `/health` `{"ok": false, "store": false}` (503) | **The database cannot be read.** | Disk full? Permissions (`ls -la /var/lib/targum/targum.db*`, all `targum targum`)? Then [`ROLLBACK.md`](ROLLBACK.md) step 4, on David's word. |
| `/health` ok, pages slow, `queue` climbing | **Workers stuck or the box saturated.** | `targum-deploy` active (a rebuild eating the CPU)? Memory and swap (step 4)? `uptime`'s load against the box's 4 cores. |
| Everything ok, one page broken | **A bug**, not an incident. | A `beta-found` card through triage, not this page. |

A provider being down or out of credit looks, from a reader's chair, exactly like a
broken deploy. Rule it out before rolling anything back: a rollback does not bring a
provider back, and it costs a deploy.

The preflight with connections checks mail, egress, the proxy and the token minter in one
go, and spends nothing:

```sh
ssh root@targum.page 'systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env /usr/local/bin/targum preflight --store /var/lib/targum/targum.db --out /var/lib/targum/targums'
```

Healthy: every line `ok`, with the known warnings (the port answering, which is the
running service; stale parasha and daily pages awaiting a laptop re-cut).

**If it says `warn yt-dlp: YouTube imports are off without yt-dlp`**, YouTube, Instagram,
TikTok and Facebook imports are all off for readers, and the cause is almost always the
nightly upgrade, not a deploy. At 03:30 UTC `/etc/cron.d/targum-ytdlp` (root's, written
by `provision.sh`) runs `uv tool install --upgrade yt-dlp` as `targum` through
`systemd-run --unit=targum-ytdlp`. When it meets a file `targum` cannot remove it stops
halfway, after it has deleted `bin/yt-dlp`. That happened on 2026-10-22 and imports were
off for about 18 hours. Read-only:

```sh
ssh root@targum.page 'journalctl -u targum-ytdlp -n 5 --no-pager'
ssh root@targum.page 'find /srv/targum/.local/share/uv/tools ! -user targum | head; find /srv/targum/.local/share/uv/tools ! -user targum | wc -l'
```

Healthy: no `error:` in the last run, and `0` files. On 2026-10-22 the journal said
`failed to remove directory …/yt_dlp/utils/jslib/__pycache__: Permission denied` and 90
files were root's, left by somebody running `yt-dlp` as root. The fix, on David's word:
give those files back to `targum`, then run the cron's install again. The first line
gives nothing back unless the tools directory's real path is the one named, because
`targum` owns every directory above it and one of them swapped for a symlink would send
root's chown elsewhere. It runs as
`targum` through `systemd-run`, so copy the command from the cron file rather than
typing it, because it pins the token minter's version:

```sh
ssh root@targum.page 'cd -P /srv/targum/.local/share/uv/tools && [ "$(pwd -P)" = /srv/targum/.local/share/uv/tools ] && find . ! -user targum -execdir chown -h targum:targum {} +'
ssh root@targum.page 'cat /etc/cron.d/targum-ytdlp'
ssh root@targum.page '<everything after "root" on the 30 3 line>'
```

Then the preflight with connections again: `yt-dlp` and the four platforms should say
`ok`. Nothing else needs restarting, because the service looks for `yt-dlp` on each import.

## Minutes 8–10: decide

**Roll back** ([`ROLLBACK.md`](ROLLBACK.md)) when all of these hold:

- it started with a deploy (the build stamp moved and the trouble began after
  `ActiveEnterTimestamp`);
- it is not a provider, the network or the disk;
- a fix forward is not minutes away. A one-line fix deployed on top is cheaper than a
  rollback, and much cheaper when the deploy renamed an annotator (a rollback then
  re-annotates the whole shelf: hours of box time, twice).

**Restore the database** only when the data itself is damaged, not because the code is
broken: it loses every reader's writes since the copy. Code first, data last.

**Wait** when it is a provider (their status page says so, or the credit mail came) or the
network between: nothing on the box would help, and readers are told a sentence already.

**Restart** only to recover a service that is down for a reason now fixed (a full disk
cleared, a key put back), and never while `targum-deploy` is active without knowing why.
`systemctl reset-failed targum` first if systemd has given up on it.

Whatever is decided is David's call; bring him the evidence from the steps above and the
recommendation, in a few lines.

## Never

- **Run `targum` or `yt-dlp` as root on the box**, `--help` included. It leaves root-owned
  `__pycache__` in `/srv/targum/.local/share/uv/tools/targum` (or `…/tools/yt-dlp`), and
  the next deploy (or the nightly yt-dlp upgrade) fails at `Permission denied` halfway
  through replacing the tool. One-off commands go through
  `systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum
  --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env /usr/local/bin/targum …`;
  `sqlite3` through `runuser -u targum --`. The env file is systemd's format and root's
  alone: do not `source` it. To see that a key is set, count it, which prints `1` and never
  the value: `grep -c '^NAME=.' /etc/targum/targum.env`. Read a value with `grep ^NAME=
  /etc/targum/targum.env | cut -d= -f2-` only for a setting that is not a secret (an
  address, a path, a switch); never print a key's value anywhere.
- **Restart `targum`, or start a deploy, during a detached rebuild without knowing what it
  is doing.** `systemctl is-active targum-deploy` says whether one runs;
  `journalctl -u targum-deploy` says since when. The service already went live at the
  start of that unit, so a restart buys nothing there, and it loads models a second time
  beside a rebuild on a box that has been OOM-killed by that.
- **Delete backups**: `targum.db.before-*`, the nightly copies, the cache archives, or
  anything in `/var/lib/targum/backups/`. Not to free disk in a hurry either; find what
  else filled it (`du -xh /var/lib/targum --max-depth=1 | sort -h | tail`), and ask.
- **Rotate or edit keys on the box by hand.** They come from 1Password on every deploy
  (`deploy/box.env.op`); a hand edit is overwritten by the next one.
- **Paste reader data** (addresses, Tell us text, IPs from the Caddy log) into the room, a
  card or a commit.

## After

- A line on the card that tracked it, or a new one: what happened, from when to when (UTC),
  what readers saw, what fixed it.
- If a step here was wrong or missing, fix this page in the same week.
