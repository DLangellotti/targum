# Putting the previous build back

For a deploy that went out and is worse than what it replaced. Written against
`deploy.sh` as of 2026-10-22 (targum-internal#482); every path and command below was
checked against the code and, read-only, against the box. **Not yet run as a drill**: the
date it first runs goes on #482 and here.

Rolling back is a change to the box, so it happens on David's word, in the moment. The
read-only checks in step 1 need nobody's word.

Three things can be put back, and they are separate:

| What | How | Loses |
|---|---|---|
| **The code** (the wheel) | Deploy the previous commit again (step 3) | Nothing. The database is kept. |
| **The database** | Restore the `targum.db.before-*` copy taken before the deploy (step 4) | Everything readers did since that copy: words saved, sign-ups, jobs, the spend ledger. |
| **The reader pages** | Come back with the code: the rollback's rebuild rewrites them | Hours of box time if an annotator name moves (step 5). |

**Roll back the code first, and the database only if the data itself is damaged.** The
schema changes in `accounts.py` are additive columns and tables (`CREATE TABLE IF NOT
EXISTS`, `ALTER TABLE … ADD COLUMN … DEFAULT`) plus a few idempotent `UPDATE`s that
`_migrate` runs on every open (`UPDATE person SET interest = …`), so older code opens a
newer database and runs: it leaves the new tables and columns alone and sets
`user_version` back to its own number, and the next deploy forward migrates it up again.
A bad deploy is almost always bad code over good data. Check this still holds before
relying on it: `git diff <good>..<bad> -- src/targum/accounts.py` should add columns,
tables and nothing that drops or renames one; read any new `UPDATE` in it, because the
real risk is the newer code writing a value the older code does not expect.

## 1. Read-only checks first

From the laptop. None of these changes anything.

```sh
curl -sS -m 10 https://targum.page/health
```

You should see `{"ok": true, "store": true, "queue": 0, "jobs": 69}` (the numbers vary;
`queue` is what is waiting, `jobs` is what this process has seen since it started). A
`502` is Caddy answering for a targum that is not running; no answer at all is the box or
the network ([`INCIDENT.md`](INCIDENT.md) tells those apart).

```sh
curl -sS -m 10 https://targum.page/ | grep -o 'data-build="[^"]*"'
```

`data-build="07646ff2961c"`: the first 12 characters of the commit the running wheel was
built from (`about.stamp`, written by `deploy.sh`). This is the build that is live, not the
one somebody meant to ship. `dev` means a wheel built from a tree with edits in it, which
`deploy.sh` would not ship.

```sh
ssh root@targum.page 'systemctl show targum -p ActiveEnterTimestamp; systemctl is-active targum targum-deploy'
```

```
ActiveEnterTimestamp=Thu 2026-10-22 01:42:00 UTC
active
inactive
```

When the service last started, whether it is up, and whether a deploy's rebuild is still
running on the box (`active` on the second line means it is; see "Never" below).

```sh
ssh root@targum.page 'grep "\"build\"" /srv/targum/.local/share/uv/tools/targum/lib/python3.*/site-packages/targum/activity.json'
```

The build the installed wheel carries. It equals `data-build` once the service has
restarted onto it; if it differs, the wheel is in and the process predates it.

```sh
ssh root@targum.page 'journalctl -u targum -n 80 --no-pager'
ssh root@targum.page 'journalctl -u targum-deploy -n 20 --no-pager'
```

The service's own log (a traceback, a preflight `FAIL`, `Start request repeated too
quickly`), and the deploy unit's starts and finishes. The deploy unit's rebuild writes
nothing per text into the journal; the lines you will see are
`Started targum-deploy.service` and `Deactivated successfully` (or `Failed`).

Decide what is wrong before putting anything back: a provider out of credit or down looks
like a broken deploy from a reader's chair and is not one ([`INCIDENT.md`](INCIDENT.md)).

## 2. Find the commit to go back to

The one deployed before the bad one. In order of trust:

1. The deploy note for the previous deploy (Claude's memory, `deploy-YYYY-MM-DD*.md`,
   which records the SHA and the build stamp), or the #targum room.
2. `journalctl -u targum-deploy --no-pager | grep Started` gives the time of each deploy;
   the previous one's commit is on master at or just before that time:
   `git log --first-parent --format='%h %cI %s' origin/master | head -20`.

Take the **full** SHA (`git rev-parse <short>`): `TARGUM_CHECKED` is compared with
`git rev-parse HEAD`, which is 40 characters.

Roll back one deploy, not several. The `deploy.sh` that runs is the one at that commit,
and an old enough one has bugs the current one fixed.

Before going further, look at what the step back will cost:

```sh
cd ~/Vaults/Projects/targum
git fetch -q origin
git diff <good>..<bad> -- src/targum/annotate src/targum/vocalize | grep -E '^-[^#]*[a-z_]+/[0-9]+'
git diff <good>..<bad> -- uv.lock | grep -A2 '^ name = "stanza"$' | grep '^[-+]version'
```

The first prints the versioned names the bad deploy moved away from. On the 2026-10-22
deploy it printed three: `grammar/6` (`annotate/dicta.py` `FEATURES`), `oshb/6`
(`annotate/scripture.py`) and `phonikud/2` (`annotate/pronounce.py`); on the one before,
nothing. The others that can move are `annotate/lemma.py` `FEATURES`, `register/N`,
`aramaic/N`, `tanakh/N`, `LANGUAGES = "languages/N"` in `annotate/base.py`, and the
vocalizers' `nakdimon/N` and `dicta/menaked/N`. The second catches a Stanza version bump,
whose version is part of the lemmatizer's name too. Any output from either means an
annotator rename, and the rollback re-annotates: read step 5 before going on.

## 3. Put the previous code back

Exactly the deploy that put it there the first time, from a detached worktree at that
commit, never from the main checkout.

**First, no deploy may be running on the box.** This is a precondition you check, not
something `deploy.sh` will catch for you: until targum#876 is deployed, its
`a deploy is already running` guard sits *after* the wheel and catalogue install, so a
refused deploy has already put the old wheel under the running rebuild.

```sh
ssh root@targum.page 'systemctl is-active targum-deploy'      # inactive (or failed)
```

`active` means the bad deploy's rebuild is still going. Ask David whether to wait for it
(`journalctl -u targum-deploy -f`) or stop it (`systemctl stop targum-deploy`), and
check again before going on. Stopping it is safe for the data (`rebuild --words` is
incremental and resumes rather than repeats), but it leaves pages half-rewritten until
the rollback's own rebuild covers them.

```sh
GOOD=<full sha>
cd ~/Vaults/Projects/targum
git worktree add --detach ~/Vaults/Projects/targum-wt/rollback-${GOOD:0:8} "$GOOD"
cd ~/Vaults/Projects/targum-wt/rollback-${GOOD:0:8}
git rev-parse HEAD            # must print $GOOD
```

Take the database copy now, before anything is installed, so the restore in step 4 has a
starting point that is the state the rollback began from:

```sh
COPY=/var/lib/targum/targum.db.before-rollback-$(date -u +%Y-%m-%d-%H%M)
ssh root@targum.page "runuser -u targum -- sqlite3 /var/lib/targum/targum.db '.backup $COPY' && cp $COPY /tmp/rollback-check.db && sqlite3 /tmp/rollback-check.db 'PRAGMA integrity_check; PRAGMA user_version;'; rm -f /tmp/rollback-check.db*"
```

You should see `ok` and the schema number (`47` on 2026-10-22). Taken as `targum`, so the
copy is the service's and not root's; checked on a throwaway duplicate, so the copy
itself is never opened and grows no `-wal`/`-shm` beside it. (The `before-deploy-*` copies so far were taken as root
and some are `0600 root`; step 4 handles both.)

Then, under the laptop's heavy lock, the deploy:

```sh
mkdir /tmp/targum-heavy.lock   # wait and retry if it exists: something heavy is running
TARGUM_CHECKED="$GOOD" TARGUM_HOST=root@targum.page nice -n 15 ./deploy/deploy.sh
rmdir /tmp/targum-heavy.lock
```

`TARGUM_CHECKED` stands the local suite down, because CI passed this commit on master
when it was first deployed. The lint, format and type checks still run. What you should
see, in order:

```
== checks, before anything leaves this machine ==
   suite: passed by CI at <short sha>
   clean
== secrets, from 1Password ==
   reading the vault as the targum-box service account
   N keys
== build ==
   targum-0.2.0.0-py3-none-any.whl
   N versions pinned from uv.lock
== ship ==
   N covers
== live now; rebuilding the shelf behind it ==
   ...
   done
== verify ==
   https://targum.page/health is ok
   (preflight's checks)
Deployed.
```

If it stops at `a deploy is already running on this box (targum-deploy.service)` anyway
(a deploy started between your check and this one), the refusal came after the install
on today's `deploy.sh`: the good wheel and today's catalogue are already in, under the
bad deploy's rebuild, whose remaining steps (`seed`, `catalogue-lemmas`, its final
restart) then run the good code over pages the bad rebuild wrote. Step 1's
`activity.json` check shows which build is installed. Go back to the precondition above,
let that unit finish or stop it, and deploy again.

The service restarts onto the old wheel within seconds of `== live now ==` (the restart
is the first line inside the deploy unit; a busy box takes up to ten minutes to drain).
The rebuild then rewrites every reader page with that commit's stylesheet and script,
behind the running service.

**What a redeploy of an old commit does not put back,** because it is not in the commit:

- **The catalogue, sources, sentence levels and binyans** ship from this laptop's
  `~/.targum/`, as they are today. If the bad change was there, put the old file back in
  `~/.targum/` first. The box does not keep the previous copy.
- **Keys** come from today's vault through that commit's `box.env.op`; a line the bad
  deploy added stays in `/etc/targum/targum.env`, harmlessly.
- **A timer the bad deploy added** stays installed and enabled, and runs a `targum`
  subcommand the old code may not have. `systemctl list-timers 'targum*' --no-pager` and
  compare with the old commit's `deploy/*.timer`; a timer the old tree does not name is
  stopped with `systemctl disable --now <name>.timer` (on David's word, like the rest).

### Check it took

```sh
curl -sS -m 10 https://targum.page/ | grep -o 'data-build="[^"]*"'   # the first 12 of $GOOD
curl -sS -m 10 https://targum.page/health                              # "ok": true
ssh root@targum.page 'systemctl show targum -p ActiveEnterTimestamp'   # a minute ago
ssh root@targum.page 'systemctl is-active targum-deploy'               # inactive once the rebuild is done
```

Then open the page that was broken, in a visible browser tab. Afterwards:
`git worktree remove ~/Vaults/Projects/targum-wt/rollback-${GOOD:0:8}`.

## 4. Restore the database, only if the data is damaged

The copy taken before each deploy is `targum.db.before-<what>-<date>`, made with
SQLite's `.backup` (a consistent snapshot through the backup API, never a plain `cp` of a
live WAL database). Recent ones sit beside the database in `/var/lib/targum/`; older ones
in `/var/lib/targum/backups/`, beside the nightly `targum-YYYYMMDD-HHMMSS.db` copies that
`targum-backup.timer` takes at 04:00 UTC.

```sh
ssh root@targum.page 'ls -la /var/lib/targum/targum.db* /var/lib/targum/backups/ | grep -E "before-|targum-[0-9]{8}"'
```

**Restoring loses every write since the copy**: words kept, accounts made, sign-in links,
jobs and what they spent. Say to David what will be lost (the copy's time against now)
before going on. It is his call.

From here on as root on the box, in one SSH session:

```sh
ssh root@targum.page
FROM=/var/lib/targum/targum.db.before-deploy-2026-10-21b      # the copy to restore
```

**a. Check the copy, on a throwaway duplicate.** A snapshot is in WAL mode; opening it
read-only fails with `unable to open database file (14)`, which is not corruption, and
opening it normally writes `-wal`/`-shm` beside it. So check a copy:

First, the copy's own `-wal` must be empty or absent. Every `before-*` and nightly copy
so far has a 0-byte one or none; a copy with a non-empty `-wal` carries pages that live
only in that file, and copying the main file alone would check, and restore, without them.

```sh
ls -la "$FROM"-wal 2>/dev/null                                   # absent, or size 0
```

Anything bigger: copy the `-wal` beside the duplicate below (as `/tmp/restore-check.db-wal`),
and to `restore-source.db-wal` in step c, or ask before going on.

```sh
cp "$FROM" /tmp/restore-check.db
sqlite3 /tmp/restore-check.db 'PRAGMA integrity_check; PRAGMA user_version; SELECT count(*) FROM person; SELECT count(*) FROM word;'
rm -f /tmp/restore-check.db*
```

For comparison, the same counts from the live database (as `targum`, and through the
backup API so the live file is only read):

```sh
runuser -u targum -- sqlite3 /var/lib/targum/targum.db '.backup /tmp/live-check.db'
sqlite3 /tmp/live-check.db 'SELECT count(*) FROM person; SELECT count(*) FROM word;'
rm -f /tmp/live-check.db*
```

You should see `ok`, the schema number, and counts a little below the live ones: a
snapshot is a moment, and readers kept going after it. Counts far below, or zero: that
copy is the wrong file (an empty database once passed as a backup for weeks; see
[`RESTORE.md`](RESTORE.md)). Anything but `ok`: stop, and try the previous copy.

**b. Stop what writes to the database.**

Four timers start something that writes to it: the subscriptions poll, the visit count,
the nightly backup, and the 04:30 UTC subscriptions mail, which stamps each item it
mails (`subscriptions.py`). Stopping a `.timer` leaves alone a `.service` it already
started (the backup's may run for an hour), so stop both, and check no deploy is running:

```sh
systemctl is-active targum-deploy                               # inactive (or failed)
systemctl stop targum-subscriptions.timer targum-visits.timer targum-backup.timer targum-subscriptions-mail.timer
systemctl stop targum-subscriptions.service targum-visits.service targum-backup.service targum-subscriptions-mail.service
systemctl stop targum
systemctl is-active targum targum-subscriptions targum-visits targum-backup targum-subscriptions-mail   # all inactive
```

A copy taken before 04:30 UTC on the day of the restore does not have that morning's
"mailed" stamps, so the 04:30 mail goes out again to everyone it reached. Say so to David
before restoring such a copy.

The stop drains: it can take up to ten minutes while builds and chat turns finish
(`TimeoutStopSec=660`). The health watch will mail `TARGUM_ALERT_TO` after ten minutes
down; that mail is expected.

**c. Keep what is there now, then restore into it.** `.restore` copies through SQLite's
backup API into the live file, so the live database's own `-wal` and `-shm` are handled
rather than left to be replayed over the restored pages, which a plain `cp` over the file
would risk.

```sh
STAMP=$(date -u +%Y-%m-%d-%H%M)
runuser -u targum -- sqlite3 /var/lib/targum/targum.db ".backup /var/lib/targum/targum.db.before-restore-$STAMP"
install -o targum -g targum -m 0600 "$FROM" /var/lib/targum/restore-source.db
runuser -u targum -- sqlite3 /var/lib/targum/targum.db ".restore /var/lib/targum/restore-source.db"
runuser -u targum -- sqlite3 /var/lib/targum/targum.db 'PRAGMA integrity_check; PRAGMA user_version;'
rm -f /var/lib/targum/restore-source.db*
ls -la /var/lib/targum/targum.db*
```

You should see `ok`, the copy's schema number, and `targum.db`, `-shm` and `-wal` all
owned `targum targum`. The `install` step is there because older `before-*` copies are
`0600 root` and the `targum` user cannot read them. Do not delete
`targum.db.before-restore-*`: it is the way back from this step.

**d. Start it again.**

```sh
systemctl start targum
systemctl is-active targum                                      # active
systemctl start targum-subscriptions.timer targum-visits.timer targum-backup.timer targum-subscriptions-mail.timer
journalctl -u targum -n 30 --no-pager
curl -sS -m 10 https://targum.page/health
```

`systemctl start` runs `preflight --no-connect` first (`ExecStartPre`); a `FAIL` there
stops the start and says why in the journal. A copy from an older schema is migrated up
by the code on open. `/health` should answer `"ok": true, "store": true`.

If it says `Start request repeated too quickly`, the unit gave up after five failures in
five minutes: read the journal, fix the cause, then `systemctl reset-failed targum &&
systemctl start targum`.

## 5. When the step back crosses an annotator rename

The annotator's name is the cache key for a text's words (repo `CLAUDE.md`). `rebuild
--words` re-annotates every text whose recorded name differs from what the running code
would call its annotator, with no cache in between: a rollback to an older name
re-annotates the whole shelf again, back to the old name, and the next deploy forward
does it a third time.

Measured on this box (no GPU): grammar/7 + oshb/7 + phonikud/3, about 1 h 40 (2026-10-22);
grammar/5 + oshb/6 + tanakh/3, about 1 h 30 (2026-10-13); a `languages/*` rename, 5 to 7
hours (2026-09-16). The service is live on the rolled-back code within seconds; what takes
the hours is the box's CPU, under which every reader's build is slower, and pages
re-annotated one by one behind it. It costs little money (the meanings for the old names
were bought before and are in the cache) but it can buy some (`--gloss`).

So, across a rename:

- **Prefer fixing forward** unless the rename itself is what broke. A one-line fix
  deployed on top costs minutes; a rollback and a re-deploy cost the shelf twice.
- If rolling back anyway, say so to David with the hours, and plan the roll forward as an
  overnight operation, not the same evening.
- The parasha corpus and the daily window keep no artifacts and are not touched by any
  rebuild. They stay as they were last cut on the laptop, whichever way the box moves
  (`deploy/README.md`, "A rebuild does not reach every reader").

How far along it is, read-only:

```sh
ssh root@targum.page 'systemctl is-active targum-deploy; find /var/lib/targum/targums -name annotation.json -newermt "<the rollback deploy start, UTC>" | wc -l'
```

The count rises toward the number of built texts; `inactive` is the finish.
`targum preflight`, run as below, says how many Hebrew texts are still behind the
annotator the running code uses.

```sh
ssh root@targum.page 'systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env /usr/local/bin/targum preflight --store /var/lib/targum/targum.db --out /var/lib/targum/targums'
```

## Never

- **Run `targum` as root on the box**, `--help` included. It writes root-owned
  `__pycache__` into `/srv/targum/.local/share/uv/tools/targum`, and the next deploy's
  `uv tool install` stops at `Permission denied` after it has begun taking the old
  environment apart. Any one-off `targum` command goes through `systemd-run --uid=targum
  --gid=targum --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env`, as
  above; `sqlite3` alone goes through `runuser -u targum --`. (`sudo -u targum` cannot read
  `/etc/targum/targum.env`, which is root's.)
- **Restart `targum` or start a deploy while `targum-deploy` is active** without knowing
  what it is doing. It may be hours into a rebuild. A second deploy is refused for that
  reason; a hand restart is not. The restart itself does the rebuild no harm (the service
  went live at the start of the unit already), but it loads the models again beside a
  rebuild holding its own, on a box that has been OOM-killed by exactly that kind of load,
  and it drains the readers' running builds for up to ten minutes. Know which wheel is
  installed (step 1) and why the restart is needed before doing it.
- **Delete a `targum.db.before-*` copy, a nightly copy, or `targum.db.before-restore-*`**
  during or after a rollback. They are the only way back from a restore. Pruning them is
  a separate, unhurried decision.
- **`cp` a backup over the live `targum.db`** with the old `-wal` beside it. Use `.restore`
  (step 4c).
