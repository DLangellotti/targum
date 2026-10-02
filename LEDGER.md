# The corpus ledger

Design for targum-internal#162, written 2026-10-02. One SQLite file that every stage
writes and the renderer reads, so the pipeline's exhaust can answer "what do we know
about this text, and which tool made it" rather than only "was this paid for already".

Status: **design, plus a first slice behind a flag** (`src/targum/ledger.py`, the
`vocalize` stage, off unless `TARGUM_LEDGER` names a file). Nothing reads from the ledger
yet. The cache is still the record and the read path.

## Decisions

1. **One file, `corpus.db`, beside the account store** (`/var/lib/targum/corpus.db` on
   the box). It is not a table in `targum.db`, because it is corpus data rather than
   personal data: it is shipped to a GPU job (#166), exported, and kept after an account
   is deleted. The one link back to an account is the private bucket (below), which holds
   no personal fields.
2. **A table per artefact kind, a row per unit.** Each row carries the stage, the tool
   name, the tool version, and the cache key that produced it. The cache key stays a
   column, so the cache can become a view of the ledger without changing a key.
3. **The ledger has its own schema version** (`meta.schema`), separate from
   `models.SCHEMA_VERSION`. Rows can change shape without moving a cache key, so a
   ledger migration never re-buys a translation.
4. **A rename is a new row.** A new tool name or version is a new cache key, so it is
   a new row, and the old row stays. Writing again under the same key replaces that key's
   row, as the cache does today. History lives in tool versions, not in overwrites.
5. **A value is recorded only if the rows give it back byte for byte.** `record` rebuilds
   the value inside its own transaction and rolls back on any difference. The ledger can
   never become a lossy copy of the cache it is meant to replace.
6. **SQLite stays.** One box, one file, until a number says otherwise. This is out of
   scope as in the card.

## Schema

Each table below has these columns, and they are not repeated in the list:
`id`, `stage`, `cache_key UNIQUE`, `tool`, `tool_version`, `schema_version`,
`written_at`, `exportable`. `exportable` is copied from `texts` at write time, so an
export is one `WHERE` with no join.

| table | one row is | its own columns |
|---|---|---|
| `texts` | a source document | `document_hash` PK, `source`, `licence`, `reader_publishable`, `corpus_exportable`, `ingester`, `owner` (null when public) |
| `segmentations` + `segments` | a split of a text / one sentence | `document_hash`, `segmenter`; `segment_id`, `ord`, `text` |
| `translations` + `pairs` | one rendering / one aligned pair | `document_hash`, `provider`, `model`, `style`, `target_language`; `segment_id`, `target`, `confidence`, `coarse` |
| `alignments` + `links` | a human translation matched / one link | `document_hash`, `translation_hash`, `aligner`; `source[]`, `target[]`, `confidence` |
| `annotations` + `tokens` | one annotator's pass / one token | `document_hash`, `annotator`; `segment_id`, `ord`, `form`, `lemma`, `pos`, `features`, `band` |
| `vocalizations` + `pointings` | one diacritizer's pass / one segment | `document_hash`, `language`; `segment_id`, `pointed`, `segment_ord`, `machine_ord`, `rejected_ord` — **built** |
| `glosses` | one lemma's meaning | `lemma`, `source_language`, `target_language`, `provider`, `grounded` |
| `timings` | one word's time | `document_hash`, `segment_id`, `word`, `start`, `end`, `aligner`, `acoustic_model` |
| `scores` | one eval result (#163) | `suite`, `metric`, `value`. Scores are never deleted with an account. |
| `jobs` | one compute job (#166) | `kind`, `provider`, `region`, `minutes`, `cost` |

`tool` and `tool_version` are the name the stage already keys on, such as
`dicta/menaked/1` with model `dictabert-large-char-menaked`, or `annotator.name`. They
are not a new naming scheme. Stages that cache whole blobs and have no unit worth a row
(`reading`, `refine`, `pockettorah`, `tanakh-count`) get one generic table,
`blobs (stage, cache_key, tool, tool_version, value JSON)`, until someone needs to query
inside them.

## The cache becomes a view

These steps go in order, one stage at a time, and each step is a flag on its own.

1. **Dual-write** (the slice). `Cache.put` writes its JSON, then `ledger.mirror_put`
   writes the rows. `Cache.drop` drops the row too, so a wrong answer an author removed
   is not rebuilt from the ledger. `Cache.clear` leaves the ledger alone, because that
   is what clearing scratch means.
2. **Read-through.** `Cache.get(stage, key)` asks the ledger first and falls back to the
   JSON. Every stage keeps its key, so nothing is a miss that was a hit before.
3. **Ledger-only.** For a stage whose rows have matched its JSON over a full rebuild,
   `put` stops writing JSON. `Cache` stays as the interface the stages call; only the
   storage under it changes.

## Rebuild from rows

`rebuild` reads rows and renders. It recomputes only what has no row for the current
tool version. A `SCHEMA_VERSION` bump then changes the page format and buys nothing
twice. In the slice, `ledger.rebuild(ledger, cache)` writes the cache back from rows, and
the test deletes a stage's cache, rebuilds it, and checks it is the same bytes and that
a new build reads it without running the tool.

## Migration from today's cache

`ledger.backfill(ledger, cache, stage)` reads a stage's JSON into rows and does not
change the cache. It returns (recorded, refused), and a refused entry stays in the cache
and is logged. It was run on 2026-10-02 against the laptop's real cache, into a scratch
file: **936 `vocalize` entries recorded, 0 refused, in 1.9 s**. That gave 39 MB of SQLite
for 35 MB of JSON. It was not run on the box.

Per stage, the order is: write the table, backfill, turn on dual-write, compare, then
read-through. `texts` comes first, because `exportable` is copied from it. It is
backfilled from the catalogue and from the licence string #115 writes at ingest. A text
with no licence string gets `exportable = 0`.

## `targum corpus export --exportable`

The command writes one JSONL file per table with `WHERE exportable = 1`, plus a datasheet
generated from the same rows. The datasheet lists the sources and licences, every
`(tool, tool_version)` with its row count, the counts per table, the date, and the ledger
schema. Because the bit is copied onto every row, the per-table counts in the datasheet
are exactly `SELECT COUNT(*) … WHERE exportable` (criterion 3), and an empty licence can
never appear (criterion 4). The private bucket (#161) is `texts.owner IS NOT NULL`. Those
rows are never exported, and they are deleted with the account. `scores` rows have no
owner and survive the deletion (criterion 5).

## How the criteria get verified

- **Criterion 1** (every stage writes rows, the cache reads from them, the four checks
  pass, and no paid stage re-runs) **needs a full local rebuild with DICTA loaded,
  watched through the `Usage` counter.** On a GPU-less machine that is the two-hour job.
  It was not run for the slice and cannot be run unattended. It is either a scheduled
  run on the laptop or the first job of #166.
- **Criterion 2** (renaming the annotator keeps the old rows, and a query returns
  per-token agreement) needs `tokens` written under two annotator names for one text.
  The slice already shows that a rename adds a row and keeps the old one
  (`test_a_renamed_tool_adds_rows_and_keeps_the_old`). The agreement query is a
  self-join on `tokens` by `(document_hash, segment_id, ord)`.
- **Criterion 6** (#16 and #1 closed before the ledger holds paid work) is met. #16
  closed on 2026-09-29. The vocalize slice holds nothing paid for: the diacritizer runs
  locally.

## Backups

Backups are #16, and they are already off the box. Until a stage goes ledger-only, the
ledger holds only a copy of what the cache holds, and the nightly cache zip covers it.
Once any stage goes ledger-only, `corpus.db` joins the nightly job through
`backup.snapshot` (the SQLite backup API, safe on a live WAL file), ships with the
database, and gets the same restore drill as #1. This is a precondition of step 3 above,
and it is not optional.

## Out of scope

- Selling or publishing a dataset. This design makes one producible; #161 decides what
  leaves.
- Replacing SQLite.
- The GPU runner (#166). It reads and writes this file, and it is designed there.
- Reader folders. They stay rendered output, and nothing here reads from them.

## Open questions for David

1. **Where the file lives.** The proposal is `corpus.db` beside `targum.db`, not a table
   inside it. Is that right, given that account deletion has to reach the private bucket
   across two files?
2. **History under the same key.** Today the same cache key replaces its row, as the
   cache does. Should it keep every write, so that a `--force` rebuild also leaves a
   comparison behind? The cost is size.
3. **Which stage next.** The proposal is `texts`, because the bit everything else copies
   comes from it, then `translations` and `pairs`, the paid half. Or `tokens` first, for
   criterion 2 and #166's annotate job?
4. **Criterion 1's rebuild.** Should it be a scheduled laptop run, or should it wait for
   #166's runner?
5. **Turning the slice on.** Is it acceptable to set `TARGUM_LEDGER` on the box for
   `vocalize` now, ahead of read-through, to gather real rows? It costs nothing and
   changes nothing a reader sees.
