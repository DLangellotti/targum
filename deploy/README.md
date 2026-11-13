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

A deploy that went out and is worse than what it replaced is
[`ROLLBACK.md`](ROLLBACK.md): a wheel the box kept put back with `rollback.sh`, or the
previous commit deployed again, and the database put back only if the data itself is
damaged. Something wrong on the site, whatever the cause,
is [`INCIDENT.md`](INCIDENT.md): who is told, where to look, and how to tell the box from
a model provider from the network in the first ten minutes.

The step that runs right after the next approved deploy (targum-internal#507) is
[`REINGEST-TANAKH.md`](REINGEST-TANAKH.md): find every Tanakh copy on the box without
verse refs, give it its refs, and re-annotate it so OSHB reads it, with readers' marks
carried across. On 2026-10-22 the box had none and the laptop had thirteen.

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
`TARGUM_PARASHA_DIR`; `TARGUM_RECORDING_DIR` does, which is how the re-cut below runs
from a worktree and still finds the main checkout's recordings.

**A rebuild does not reach every reader.** `targum rebuild` rewrites what has artifacts
beside it; the parasha corpus and the daily window keep none, and the four shared Russian
texts are skipped by design. After any change to reader CSS or JS those stay as they were
cut, and `deploy.sh` used to say "done" over them — three times. `targum preflight` now
counts them (`stale readers`), so the gap is a line in the deploy rather than something
found weeks later. Re-cut and ship what it names ("After: the re-cut", below).

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

## A deploy, step by step

Written after four deploys on 2026-11-12 and 13. Each step says what you should see; a
step that shows something else is where you stop. `<live>` is the SHA the box runs now
(the last deploy's note says it) and `<new>` is the one you are about to send.

**Before: every PR is merged, really.** `gh pr merge` once answered with a GitHub 502
and left the merge half done (2026-11-13). Run the same `gh pr merge` again, then

```
gh pr view <n> --json state,mergeCommit
git fetch origin && git merge-base --is-ancestor <its mergeCommit> <new> && echo in
```

You should see `"state":"MERGED"` and `in`. Anything else, and that PR is not in this
deploy.

**Before: what the diff will cost.** One line says whether the rebuild is minutes or
hours:

```
git diff -U0 <live> <new> -- src/targum | awk '/^\+\+\+ /{f=substr($2,3)} /^[-+](LANGUAGES|FEATURES|NAME|VERSION|SCHEMA_VERSION) = /{print f": "$0}'
```

Read each file it names:

- `annotate/lemma_check.py`, `annotate/verb_roots.py`, `annotate/russian_check.py`,
  `occurrences.py`: page-build and count time only. A free recount; the 2026-11-13
  deploys carried these and the rebuild behind them took 40 minutes.
- `annotate/base.py` `LANGUAGES`, `annotate/dicta.py` or `annotate/lemma.py` `FEATURES`,
  `annotate/russian.py` `VERSION`, a `NAME` under `annotate/` or `segment/`: an annotator
  rename. Every text in that language is read again on a box with no GPU: 86 minutes for
  grammar/8 (2026-10-27), 5–7 hours for a `languages` rename (2026-09). Do not press at
  the end of a day: schedule it, and never two renames in one release.
- `models.py` `SCHEMA_VERSION`: stop. It is the cache key for every stage and re-buys
  every translation (the repo's CLAUDE.md).
- `accounts.py` `SCHEMA_VERSION`: the database moves (next step).
- Anything else (`finds/`, `units.py`, `topics.py` `LANGUAGES`): settings, not names.

When a constant the list does not cover moves under `annotate/` or `segment/`, treat it as
a rename until you have found where it goes: one that ends up in a `def name` is one.

**Before: the accounts database.** `accounts.SCHEMA_VERSION` moved 61 → 66 over those
four deploys, and every step was an added column with a default:

```
git diff <live> <new> -- src/targum/accounts.py | grep -E '^\+.*(ALTER|CREATE|DROP|DELETE|UPDATE)'
```

You should see only `ALTER TABLE … ADD COLUMN … DEFAULT …` (and `CREATE … IF NOT
EXISTS`). Those are safe to step back over ([`ROLLBACK.md`](ROLLBACK.md): older code
leaves the new columns alone). A `DROP`, a rewrite of rows, or a table rebuilt is not this
case: stop and read `ROLLBACK.md` before pressing. Either way `deploy.sh` copies the
database before it installs anything; the line is under `== ship ==`.

**Before: the laptop's heavy lock.** A deploy runs under `/tmp/targum-heavy.lock`, like
every heavy job on the laptop, and a wrapper that waits on it waits silently: on
2026-11-13 a deploy sat 30 minutes behind somebody else's run. Look first:

```
cat /tmp/targum-heavy.lock/owner 2>/dev/null || echo free
```

`free`, or a line naming who holds it and since when. If it is held, say in the deploy
note that it is waiting and on what. Never remove a lock you did not take.

**Before: nothing is deploying already.**

```
ssh root@targum.page 'systemctl is-active targum-deploy'
```

You should see `inactive`. `active` is the last deploy's rebuild, still running:
`journalctl -u targum-deploy -f` says how far, and `deploy.sh` would refuse anyway.

**Press**, from a clean tree at exactly `<new>`, with the lock held:

```
TARGUM_CHECKED=<new> TARGUM_HOST=root@targum.page nice -n 15 ./deploy/deploy.sh
```

The log says, in order: `suite: passed by CI`, the keys, the wheel, then under
`== ship ==`

```
   database copied and checked: /var/lib/targum/backups/targum.db.before-<sha12>-<stamp>
```

with `<sha12>` the first twelve of `<new>`. No such line, or `could not be copied` or
`did not check out`, and nothing was installed: that deploy stopped, which is correct.
Then `== live now; rebuilding the shelf behind it ==` (the new code serves within seconds;
the rebuild runs behind it), a `still running after Nm` line every five minutes, and at
the end `https://targum.page/health is ok`, the preflight, and `Deployed.`

**After: the read-only checks.** None of them changes the box.

```
curl -sS -m 10 https://targum.page/health
curl -sS -m 10 -o /dev/null -w '%{http_code}\n' https://targum.page/library
ssh root@targum.page 'systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env /usr/local/bin/targum preflight --store /var/lib/targum/targum.db --out /var/lib/targum/targums'
ssh root@targum.page 'ls -1t /var/lib/targum/backups/ | grep before- | head -1'
```

You should see `"ok": true`, `200`, every preflight line `ok` or `warn` and none `FAIL`,
and the `before-<sha12>` copy this deploy made. The preflight goes through
`systemd-run` as targum, never as root: root-owned files under the service's tree break
the next deploy's install. Then read the deploy log's own `warn` lines and compare them
with the last deploy's. Known after the 2026-11-12 and 13 deploys: 6 Hebrew texts behind,
the topics lexicon short of 95%, and `stale readers` at 6. A number that grew is this
deploy's.

**After: the re-cut, when the reader's look changed.** The preflight's `stale readers`
counts pages that do not carry today's `tokens.css`, `shared.css` and `reader.css`. A
change to those, or to `reader.html.j2` (both on 2026-11-13: Cancel's rules in
`shared.css`, and #1197's source line in the reader's head), leaves every parasha and
daily page as it was cut, which preflight counts only for the stylesheets: 888 of 2,781
that day.
You can tell before pressing:

```
git diff --stat <live> <new> -- src/targum/render/assets/tokens.css src/targum/render/assets/shared.css src/targum/render/assets/reader.css src/targum/render/templates/reader.html.j2
```

Anything listed means a re-cut after the deploy. It runs on the laptop, from the main
checkout, under the heavy lock: a worktree at the deployed SHA, so the pages are cut by
the code that is live, with the private half copied in (`parasha leyning` cuts a doubled
week with `recording.attach`, and the eight modules exist only in the main checkout) and
pointed at the main checkout's `targum-out`:

```
until mkdir /tmp/targum-heavy.lock 2>/dev/null; do sleep 20; done; echo "<you> recut $(date +%H:%M)" > /tmp/targum-heavy.lock/owner
M=$PWD; W=$M/../targum-wt/recut-<new>
git -C $M worktree add --detach $W <new> && cd $W
for f in dialogue/write recording/attach recording/cut weekly/facts weekly/prompts weekly/sources weekly/voice weekly/write; do cp $M/src/targum/$f.py src/targum/$f.py; done
uv sync --frozen --inexact --extra difficulty --extra phonetics --extra covers --extra bring --extra mcp --extra speech-align
export PYTHONPATH=$PWD/src TARGUM_PARASHA_DIR=$M/targum-out/parasha TARGUM_DAILY_DIR=$M/targum-out/parasha/daily TARGUM_RECORDING_DIR=$M/targum-out/recordings
nice -n 15 .venv/bin/python -m targum parasha build --out $M/targum-out
nice -n 15 .venv/bin/python -m targum parasha leyning --out $M/targum-out
nice -n 15 .venv/bin/python -m targum daily build --out $M/targum-out
TARGUM_HOST=root@targum.page ./deploy/ship-parasha.sh
TARGUM_HOST=root@targum.page ./deploy/ship-daily.sh
```

The ships end `/parasha 200` and the four daily routes `200`. Then the preflight above
again: `stale readers` should be back to the handful it was (888 → 6 on 2026-11-13).
Then remove the worktree, which holds the private half, and your lock:
`git -C $M worktree remove --force $W && rm -rf /tmp/targum-heavy.lock`.

## What the box installs

`deploy.sh` installs the wheel with **uv.lock's versions as constraints**
(`dist/box-constraints.txt`, exported on every deploy), so the box gets what CI tested
rather than whatever PyPI has that day. Without them `uv tool install` resolved fresh:
transformers 5.17.0 broke every Hebrew build on 2026-09-13 and stanza 1.15.0 stopped a
rebuild on 2026-10-01, both with CI green. Torch, the CUDA packages and ru-core-news-lg are
left out of the constraints: torch comes from PyTorch's CPU index as a +cpu build, and the
model wheel is pinned by its URL. To move a library on the box, move it in uv.lock.

The week's sheet as a PDF (targum-internal#415) is set by WeasyPrint, which the `print`
extra installs, through Pango, which it does not. `provision.sh` installs Pango on a fresh
box; on the live one it is this, once, before the deploy that carries the extra:

```sh
ssh root@targum.page 'apt-get update -qq && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core fonts-urw-base35'
```

Without it the service still starts, and Download PDF answers "The PDF can't be made right
now" with the reason in the log.

## A test account

An account for trying targum as a new reader meets it, as often as you like: signing
out of it empties it — words, progress, what it said on arrival, conversations, lists,
connections and the texts it built — and keeps the account and its invitation, so the
next sign-in is a first visit. Made on the box:

```
ssh root@targum.page 'runuser -u targum -- targum test-account tester@example.com --store /var/lib/targum/targum.db'
```

As the service's own user and against the service's own database, both on purpose. Left
to itself `targum` reads `~/.targum/targum.db`, which for root is a database the site never
opens — the account is made there and does not exist on the site (found 2026-09-28, the
first time this ran). And a database file written as root is one the service can no
longer write to.

It is refused for an address that already has an account: a test account is emptied
the next time it signs out, so a real reader's account must never become one. For
testing without reading the address's mail, `--link` prints a one-time sign-in link, and
only for a test account:

```
ssh root@targum.page 'runuser -u targum -- targum test-account tester@example.com --link --store /var/lib/targum/targum.db --address https://targum.page'
```

The link opens the ordinary sign-in page; press its button. `targum test-account` with
no address lists them. What a test account builds is spent like anybody's, under the same
rails, and it shows in the usage figures.

## Speed

After a deploy that touches the public pages (the landing, the signed-out Library and its
text pages, `/about`, the legal pages), run the read-only speed pass from the laptop and
put its numbers on the surface's §14 card (design.md §14 line 5: useful in under 1.5 s on
a phone):

```
.venv/bin/python scripts/speed_pass.py --json speed.json
.venv/bin/python scripts/speed_pass.py --page /library/ruth     # one page instead of eight
```

It loads each page cold on a throttled phone (three loads) and an unthrottled desk (two),
prints the largest contentful paint and holds the phone's to 1.5 s. Beside it each phone
line prints the LCP with a 450 ms margin and says "near" when that one crosses the line: a
warning that a real first visit might, never the verdict. It exits 1 when a phone page is
over, or when a page records no LCP at all. Only GETs leave (it aborts anything else and says how many it stopped), nothing
signs in, and its user agent ends in `targum-speed-pass`, which the visitor count drops.
It takes about five minutes for the eight pages, and it is a heavy browser run, so it
takes the shared lock like any other.

The signed-in surfaces (home, Subscriptions, the signed-in Library and two readers) are
measured as the test account, and never as a reader (targum-internal#552; David's word to
sign in from a script, 2026-10-28). Mint the link on the box as above, sign in once, and
measure; the state file is a credential, so keep it out of the tree and delete it after:

```
.venv/bin/python scripts/speed_pass.py --sign-in "<link>" --state /tmp/state.json --expect <address>
.venv/bin/python scripts/speed_pass.py --state /tmp/state.json            # first visits
.venv/bin/python scripts/speed_pass.py --state /tmp/state.json --warm     # files kept
```

The `--sign-in` press is the run's only POST; afterwards every POST is aborted again, the
sign-out (which empties a test account) included, and readers are opened through `/open/`,
which never builds. Under each signed-in line it prints the server's time for the page,
the main thread's time and when the last fetch came back, so the likely cause sits beside
the figure.

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

It watches from the box, so a box that is off or unreachable sends nothing. There is no
outside monitor yet to hear that silence: the one planned on targum-internal#20
(UptimeRobot) was never set up, the access log shows no monitor's knock since it began
on 2026-08-27 (checked 2026-10-28), and David's word on 2026-10-28 is "Not before
Launch".

A provider out of credit mails the same address from the serving process, once per
provider per four hours. `targum drill-credit --provider <name> --state <scratch>`
sends that mail as a drill, through the same code and spending nothing;
[`INCIDENT.md`](INCIDENT.md) "Drills" has the command for the box, with the other
drills.

The weekly reaches the same address two ways (targum-internal#404). A run of
`deploy/weekly-run.sh` that stops hands what it said to `targum weekly stopped` on the
box, which mails it the same minute. And `targum-weekly-watch.timer` runs `targum
watch-weekly` every hour: from Monday 12:00 UTC it looks for the week's issue in the
box's own index (`TARGUM_WEEKLY_DIR`, which `ship-weekly.sh` writes into `targum.env`)
and mails once if it is not published, which is the only way a run that never started
is heard about. Every week it sees is a line in `/var/lib/targum/weekly-watch.json`, out
or not. On the laptop, every run is a line in `targum-out/weekly/runs.log`.

Subscriptions (design.md §12, 2026-10-09) have one timer and one loop. Every half hour
`targum-subscriptions.timer` runs `targum subscriptions poll`, which reads each live
subscription's source — the series built here, the news feeds, YouTube's Data API with
`TARGUM_YOUTUBE_API_KEY` (in `box.env.op`), a podcast's feed — and writes what is new; it
never builds and never spends. Inside `targum.service`, every five minutes, the server
gets a channel's or a podcast's new item ready: prepared like a pasted link (through the
proxy and the token minter), held to the subscription's monthly cap, and claimed through
`Library.press` like any build. Every deploy installs and enables the timer;
`journalctl -u targum-subscriptions -n 20` says what each run found. Once a day, at
04:30 UTC, `targum-subscriptions-mail.timer` runs `targum subscriptions mail`: one mail a
reader with everything new, the daily cycles included and the weekly left to its Monday
mail (`journalctl -u targum-subscriptions-mail -n 20`).

The language tables (targum-internal#587) have one timer too. At 02:30 UTC
`targum-tables.timer` runs `targum tables sweep --library /var/lib/targum/targums` as
targum, which counts every public text nobody has counted yet into the corpus ledger
(`TARGUM_LEDGER`), before the 04:00 backup copies it. It reads the `annotation.json` files
already written and refuses to import a model package, so it never loads a second DICTA
beside the service's; it runs at the lowest CPU and disk priority under a 1 GB memory
cap of its own, and it talks to nothing. Every deploy installs and enables the timer;
`journalctl -u targum-tables -n 20` says what each night counted. The laptop's own rows
(its parasha, Russian and scene shelves, and the external backfills) reach the box with
`targum tables push` from the laptop: it imports them over SSH as targum, never as
root, and a push run twice changes nothing.
