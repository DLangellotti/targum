# Coming back from a backup

Done once on 2026-09-04, while nothing was on fire, which is the only time it is worth
doing (targum-internal#1). What follows is what was actually run and what actually came
back, not a plan.

The claim being tested is not "the file exists". It is: **the box is gone, and everything
that cannot be rebuilt comes back from these files alone.**

## What a backup holds, and what it deliberately does not

`backup.py` copies two things, because two things cannot be rebuilt:

- **The database.** Accounts, every word somebody has kept, phrases, reading days, the
  job queue, the spend ledger.
- **The translation cache.** Paid inventory. `Build.plan()` looks there before pricing,
  so a cache hit is quoted at nothing. Lose it and everyone pays again for work already
  bought.

It does **not** copy language models, and that is not an oversight: they are downloads.
A restored box fetches them again with `targum models fetch scripture`. Expect
`preflight` to warn about scripture until you do — that warning is the design, not a
broken restore.

Readers are not copied either. They are rendered from artifacts on disk, and
`targum rebuild` writes them again.

## The drill

Everything below ran on a laptop, against a scratch directory and a spare port. It never
touched the live box.

**1. See what is there.**

```
ssh root@targum.page 'ls -la /var/lib/targum/backups/'
```

**2. Take the newest set — and only those files.** The point is to prove they are
sufficient, so copy them somewhere empty and work from there.

```
mkdir -p /tmp/drill && cd /tmp/drill
cp ~/targum-backups/targum-<stamp>.db  ./targum.db
cp ~/targum-backups/cache-<stamp>.zip  .
cp ~/targum-backups/weekly-<stamp>.zip .
unzip -q cache-<stamp>.zip  -d cache
unzip -q weekly-<stamp>.zip -d weekly
```

17.6 MB of cache archive unpacked to 40,705 files, 179 MB.

**3. Bring the service up against it.** A spare port, and the budget at nought so a
drill cannot spend money.

```
TARGUM_CACHE_DIR=/tmp/drill/cache TARGUM_WEEKLY_DIR=/tmp/drill/weekly \
  targum serve --no-open --port 8499 --budget 0 --max-cost 0 \
    --store /tmp/drill/targum.db --out /tmp/drill/targums
```

**4. Ask it the question.**

```
curl -s http://127.0.0.1:8499/health
```

## What came back, 2026-09-04

`{"ok": true, "store": true, "queue": 116}` — and `queue: 116` matched the live box
exactly, which is what says the number came out of the restored file rather than out of
an empty one.

Row for row against the live database at the same moment:

| | live, 11:20 | restored, snapshot of 10:09 | |
|---|---|---|---|
| person | 2 | 2 | same |
| doc | 92 | 92 | same |
| day | 12 | 12 | same |
| job | 116 | 116 | same |
| word | 3,097 | 3,069 | 28 saved in the hour between |
| phrase | 24 | 23 | 1 |
| meaning | 1,951 | 1,921 | 30 |

The gaps are the point, not a fault: a snapshot is a moment, and somebody was reading in
the hour after it was taken.

Cache: 40,215 gloss entries, 217 translations, 225 vocalizations. Intact.

`preflight` against the restored store reported 3 of 16 would fail a reader: two missing
API keys (the laptop's, not the backup's) and the scripture models, which backups
deliberately skip. Nothing in that list is restore content.

## What this measured, and what it did not

**Measured:** the files are sufficient, they open, the service runs against them, and the
data is all there as of the snapshot.

**Not measured:** a real rebuild of the box — provision, deploy, restore, DNS. That is a
longer drill and it needs a spare box.

**The exposure this puts a number on:** the recovery point is the last nightly copy, so
the loss on a total failure is up to a day of reading. Measured that day: 28 words in an
hour. That is the argument for the copy leaving the box more often than nightly, and
`TARGUM_BACKUP_TO` is still empty — see targum-internal#16, deliberately deferred until
somebody outside the household has an account.
