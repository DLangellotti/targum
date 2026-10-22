# Tanakh copies without verse refs

A deploy step, run on the box **right after the next deploy David approves**, once
`targum-deploy` has gone inactive (David, 2026-10-22, targum-internal#507 part 2). It
covers every Tanakh copy on the box, the shared shelf's and every reader's own home's.
It changes files on the box, so it runs on David's word, in the moment, like the deploy.

Written 2026-10-22 against origin/master `d8f68ab7` and, read-only, against the box.
**Not yet run.** The date it first runs goes on #507 and here.

## Why

A Tanakh text ingested before `sefaria/3` has verse segments with no `ref`. The OSHB
morphology is looked up by ref (`ScriptureLemmatizer._verse`, `annotate/scripture.py`),
so such a text gets DICTA's reading for every verse while its annotator name still says
`oshb/7`. ling-he found it on the laptop's starter-shelf Ruth: שְׂדֵי as "breast; demon",
שַׁדַּי as "enough", וַתָּקָם as hif'il (targum-internal#454, finding 1).

Two things do not fix it on their own:

- **`targum refs` alone.** It copies the refs onto the segments on disk and leaves the
  annotation as it is. `rebuild --words` re-annotates a text only when the annotator's
  name differs from what the running code would call it (`rebuild_one`, `cli.py`), and
  neither the name nor the document hash moves when refs arrive. So the DICTA reading
  stays.
- **Deleting `annotation.json`.** `rebuild_one` re-annotates only an annotation it finds
  (`if annotation is not None and annotate is not None`). With none, the page is
  rewritten with no words on it at all. Never do this.

So: give the text its refs, then mark its annotation as out of date by name, then let
`rebuild --words` do the re-annotation it already knows how to do, which also carries the
readers' marks across (below).

## The count today: 0 on the box, 13 on the laptop

Run on 2026-10-22, read-only:

- **The box: 0.** Every Tanakh copy on the box already has its verse refs: the five on the
  shared shelf (Ruth, Genesis, Genesis 1:1–6:8, Joshua, Psalms), the eleven in a reader's
  home (Esther, Genesis, Daniel, Noach, Ezra, Judges, Leviticus 16–18, Deuteronomy 32,
  Joshua, and, in Aramaic, Targum Onkelos on Genesis and Targum Jonathan on Obadiah), and
  the parasha cuts. Three of the home copies still say `ingester: sefaria/2` and have their
  refs anyway: `targum refs` was run on the box before. Each annotated one reports a
  `scripture_share` between 0.87 and 0.97, which means OSHB answered for nearly every
  word. The box's shared Ruth reads every word ling-he listed correctly: בִּימֵי under
  יום, שְׂדֵי under שדה, שַׁדַּי (1:20) under שדי, וַתָּקָם under קום qal, וַתָּשָׁב
  (1:6, 1:22) under שוב, וַיָּבֹאוּ under בוא qal.
- **The laptop's `targum-out`: 13**, 11,469 verses, all `sefaria/2`: `shared/רות-he`, and
  the laptop's own test homes' Esther, Psalms (twice), I Kings, II Samuel (twice), Job,
  Lamentations, Genesis, Proverbs and Song of Songs. That is the shelf ling-he read.

So on the box today the step is the check below and nothing else: about a minute.
Run the check anyway after the deploy. A home can grow a refless copy between now and then
only through a path that still ingests with `sefaria/2`, which none does on master, but the
check is what proves it.

## 1. Find them (read-only)

From the laptop. It reads JSON and writes nothing; as `targum` so nothing on the box is
opened as root.

```sh
ssh root@targum.page 'runuser -u targum -- python3 -I - /var/lib/targum/targums' <<'EOF'
import json, sys
from pathlib import Path
# models.BEYOND_SCRIPTURE and models.is_biblical, copied: this runs without targum.
BEYOND = ("Mishneh Torah", "Mishnah", "Pirkei Avot", "Kuzari", "daf:", "Rashi on ",
          "Tosafot on ", "Mesilat Yesharim", "Mesillat Yesharim", "Chovot HaLevavot",
          "Duties of the Heart")
def biblical(source):
    text = str(source or "")
    if not text.startswith("sefaria:"):
        return False
    ref = text.split(":", 1)[1]
    head, sep, tail = ref.partition(":")
    if sep and len(head) <= 3 and head.isalpha() and head != "daf":
        ref = tail
    return not ref.strip().startswith(BEYOND)
root, found = Path(sys.argv[1]), 0
for path in sorted(root.rglob("segments.json")):
    folder = path.parent
    try:
        document = json.loads((folder / "document.json").read_text())
        segments = json.loads(path.read_text())["segments"]
    except (OSError, ValueError, KeyError):
        continue
    if not biblical(document.get("source")):
        continue
    verses = [s for s in segments if s.get("kind") == "verse"]
    with_ref = sum(1 for s in verses if s.get("ref"))
    annotation = folder / "annotation.json"
    share = json.loads(annotation.read_text()).get("scripture_share") if annotation.is_file() else None
    if verses and with_ref < len(verses) or (share is not None and share < 0.5):
        found += 1
        print(folder.relative_to(root), document.get("source"), document.get("ingester"),
              f"{with_ref}/{len(verses)} refs", f"share {share}", sep="\t")
print(f"{found} Tanakh texts to fix")
EOF
```

You should see, on 2026-10-22:

```
0 Tanakh texts to fix
```

**`0`: stop here.** Write the date and the `0` on #507. Nothing else in this page runs.

Otherwise, one line per text: its folder (`shared/…` or a home `p<id>/…`), source,
ingester, how many verses carry a ref, and the share of words OSHB answered. Three kinds:

- `0/N refs`: refless. Steps 2–4 fix it.
- `M/N refs` with M between 0 and N: partly referenced. `targum refs` skips it (it only
  fills a text with no refs at all). Bring it to David; do not improvise.
- `N/N refs` with a share under 0.5: the refs are there and do not match OSHB's numbering
  (a different edition). Refs cannot fix that. Bring it to David.

Write the list down: steps 3 and 4 need the folders.

## 2. No deploy running, and a copy of the database

```sh
ssh root@targum.page 'systemctl is-active targum-deploy'                 # inactive (or failed)
```

`active`: the deploy's rebuild is still going. Wait (`journalctl -u targum-deploy -f`);
never run a second rebuild over the shelf beside it.

The step writes no database row, but it rewrites pages readers are on, and the deploy's
own `before-deploy` copy is minutes old. Nothing more is needed here.

## 3. Give them their refs (free)

```sh
ssh root@targum.page 'systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum \
  --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env \
  /usr/local/bin/targum refs --out /var/lib/targum/targums'
```

It walks every `segments.json` under the root (`refs.backfill`), skips without a fetch any
text that is not Tanakh or already has refs, asks Sefaria for the book once, and copies
each verse's ref onto the segment, checked verse by verse against the text on disk. These
are exactly the refs `sefaria/3` introduced (the ingester is `sefaria/5` now); the text
itself is not rewritten. You should see one line per text it filled, then a total:

```
רות-he: 85 verses can now be reached by a recording
1 given their refs, 0 left alone.
```

A text named with `the text on disk is not the text the source sends now` was **left
alone**: Sefaria's text has changed since it was ingested, so the refs cannot be paired
with certainty. That one needs a fresh `sefaria/5` ingest, which for a reader's own copy
is a new build of their text. Bring each such folder to David; do not delete it to make
`seed` or a build redo it.

Free: one HTTP fetch per book from Sefaria, no model, no lemmatizer.

## 4. Mark each filled text's annotation out of date

For each folder step 3 filled (from step 1's list, `0/N refs` lines only), as `targum`.
It keeps a copy of the annotation as it was beside it, then appends `+before-refs` to the
recorded annotator name, so the next `rebuild --words` sees a name the running code would
not give and re-annotates that text, and only that text.

```sh
ssh root@targum.page 'runuser -u targum -- python3 -I - /var/lib/targum/targums "shared/רות-he"' <<'EOF'
import json, shutil, sys
from pathlib import Path
root = Path(sys.argv[1])
for name in sys.argv[2:]:
    path = root / name / "annotation.json"
    segments = json.loads((root / name / "segments.json").read_text())["segments"]
    if not any(s.get("ref") for s in segments if s.get("kind") == "verse"):
        print(f"{name}: still has no refs; left alone")
        continue
    kept = path.with_name("annotation.json.before-refs")
    if not kept.exists():  # a second run must not copy the marked one over it
        shutil.copy2(path, kept)
    held = json.loads(path.read_text())
    if not held["annotator"].endswith("+before-refs"):
        held["annotator"] += "+before-refs"
        path.write_text(json.dumps(held, ensure_ascii=False))
    print(f"{name}: marked")
EOF
```

Put every folder from the list after the root, each quoted (`"p12/בראשית-he"`). You
should see `<folder>: marked` once each. It refuses a folder step 3 did not fill, because
re-annotating a refless text gives the DICTA reading again. Running it twice is harmless.

If targum-internal#507 part 1 has added a path-scoped re-annotate by the time this runs,
use that instead of this step and say so on #507.

## 5. Re-annotate them

The same rebuild the deploy runs, with the same flags:

```sh
ssh root@targum.page 'systemd-run --quiet --wait --pipe --collect --uid=targum --gid=targum \
  --setenv=HOME=/srv/targum -p EnvironmentFile=/etc/targum/targum.env \
  /usr/local/bin/targum rebuild --words --gloss --out /var/lib/targum/targums'
```

Every other text's annotator name matches the running code, so only the marked ones are
re-annotated; everything is re-rendered, which is what makes it take as long as it does.
Run it from a terminal that will stay open, or wrap it in `systemd-run --unit=targum-refs`
without `--wait` and follow `journalctl -u targum-refs -f`: an SSH session that drops
mid-rebuild has dropped it before (deploy notes, 2026-09-08).

Then the same closing restart `deploy.sh` ends its own rebuild with:

```sh
ssh root@targum.page 'systemctl restart targum && sleep 5 && curl -sS -m 10 http://127.0.0.1:8420/health'
```

`{"ok": true, ...}`. Then run step 1 again: it should say `0 Tanakh texts to fix`.

## How long

Measured from the box's own history, not guessed:

- **The rebuild pass: about 25 minutes**, whatever N is, because it re-renders every text.
  Deploys that renamed nothing took 27 minutes start to finish (2026-10-18 to 10-21,
  `journalctl -u targum-deploy`), and that included `seed` and `catalogue-lemmas`.
- **Re-annotating a Tanakh book: seconds, not minutes.** On the 2026-10-21 23:26 rebuild,
  which renamed `oshb` and re-annotated every Tanakh text, the gap between one
  `annotation.json` write and the next was 2 s for Ruth, 5–8 s for Genesis, 14 s for
  Psalms and 47 s for Joshua (the gap includes rendering the text before it). The ~1 text a
  minute figure is modern Hebrew through DICTA; a Tanakh book with refs is mostly OSHB
  lookups. Allow a minute a book to be safe.
- **`targum refs`: seconds a book**, one fetch each.

So with N on the box: about 25 minutes plus N minutes. With today's 0: the one-minute
check in step 1.

## What it spends

- `targum refs`: nothing. A fetch from Sefaria.
- Re-annotation: nothing. OSHB and DICTA both run on the box.
- `--gloss`: it buys the English meanings the cache lacks, through the same model the build
  uses, and only for lemmas nobody has met before. A Tanakh text moved from DICTA's reading
  to OSHB's lands mostly on common words already bought (שדה, קום, שוב, יום), so expect
  cents; the whole-shelf rebuild of 2026-09-20 bought $0.56. Leave `--gloss` off and it
  spends nothing at all, and a card whose meaning is not in the cache opens with a button
  instead of the meaning.

## What readers see meanwhile

- The service stays up throughout: nothing restarts until the closing restart, which drains
  running builds for up to ten minutes as every deploy's does.
- A page keeps its old (DICTA) reading until the rebuild reaches it, then has the OSHB one.
  The rebuild writes over pages in place (`clean=False` in `rebuild_one`), so nobody has a
  page deleted from under them.
- The box's CPU is busy for the rebuild's length, so a reader's own build is slower, as
  during any deploy's rebuild.

## Readers' marks follow the words

A reader's marks are stored by lemma (`targum:vocab:<language>`, `annotate/moves.py`), so
a word whose lemma moves from DICTA's to OSHB's (שד to שדה) would orphan a mark. It does
not, because this goes through the path built for exactly that (targum-internal#141):

1. `rebuild_one` (`cli.py`) keeps the old annotation in hand while it re-annotates, and,
   since the document hash is unchanged (refs do not touch the text), pairs the two token
   by token by position: `moves.between(was, annotation)`.
2. `moves.between` keeps a move only where `same_word` says the two spellings are the same
   word (in order, they must share all but one of the shorter one's letters, and at least two). שד→שדה, שדי→שדה, די→שדי,
   הקים→קום, ישב→שוב and בימי→יום all pass it; a move onto a different word is screened
   out, because a mis-migrated mark is worse than a lost one.
3. `moves.keep` composes them with what the text had already recorded and writes
   `moves.json` beside the annotation, so the moves outlive the next rebuild.
4. The page carries them (`render`'s `moves`), and `migrateLemmas` in
   `render/assets/vocab.js` renames the reader's mark, and its meanings, the first time
   they open that text. It never deletes a mark; where both names are kept, the one touched
   more recently stands. The rename is stamped so `sync.js` pushes it to the account.

What does not follow: a reader who never opens the text again keeps the mark under the old
name until they do. And a text re-ingested fresh (step 3's refused case) has a new
document hash, so no moves are worked out for it; that is one more reason it goes to
David rather than through this page.

## On the laptop

The laptop's `targum-out` is what ling-he reads, and it holds the 13. The same steps work
there, from the main checkout (it is where `targum-out` is) and under the heavy lock, with
`--out targum-out` and `.venv/bin/python -m targum` in place of the `ssh … systemd-run`
wrapper (`op run --env-file op.env --` in front of the rebuild, for `--gloss`), and the
scripts in steps 1 and 4 run with `python3 -I - targum-out …`. The laptop's rebuild re-renders about
1,900 files: run it alone, `nice -n 15`. None of it reaches the box: `ship-shared.sh`
carries only folders named to it. Never name the laptop's `shared/רות-he` to it before the
laptop's copy is fixed, because it would replace the box's good Ruth with the refless one.
