"""The Tatoeba pool: native-written Hebrew sentences with their English, lemmatized.

What `chat/exemplars.py` reads (targum-internal#218) and the two evals draw on (#219,
#220). Built here, on a developer's machine, from Tatoeba's exports, and carried to the
box the way `sources.json` is: it is data, not code, and the lemmatizer it needs is a
BERT model the box has no GPU for.

**What is kept.** A Hebrew sentence whose contributor declares Hebrew native (skill 5 in
`user_languages.csv`), that nobody has reviewed as wrong (`users_sentences.csv`), and
that is linked to at least one English sentence. Tatoeba's Hebrew is 212,000 sentences
(2026-09-07) and 165,000 of them pass; 1,300 of those were written in Hebrew rather than
translated into it (`sentences_base.csv` says which), and the pool marks them, because
an exemplar of idiom is best when nobody was translating. The English kept for a
sentence is the one it was translated from where that is English, else the shortest
linked one.

**Tranches.** Lemmatizing runs at about 47 ms a line on a laptop, so the whole pool is a
two-hour job. The script writes what it has and picks up where it left off: rows are
ordered originals first, then shortest first — the sentences most likely to fall inside
a reader's words — and `--limit` says how many more to lemmatize this run. A row without
its `words` is in the file and is not yet retrievable.

**Licence.** CC BY 2.0 FR, per sentence, per contributor; every row keeps both usernames.
`LICENSING.md` says what is owed and where it is given.

    .venv/bin/python scripts/tatoeba_pool.py --exports ~/tatoeba \\
      --out ~/.targum/exemplars.jsonl --limit 20000

The exports: `heb_sentences_detailed.tsv`, `eng_sentences_detailed.tsv`, `links.csv`,
`sentences_base.csv`, `user_languages.csv`, `users_sentences.csv`, from
https://tatoeba.org/en/downloads, unpacked into one directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

csv.field_size_limit(1 << 30)

LANGUAGE = "he"
NATIVE = "5"
#: Lines per lemmatizer call. Measured 2026-09-07: batching past fifty gains nothing.
BATCH = 200
#: How often the file is rewritten while lemmatizing, in batches, so a killed run keeps
#: most of its work.
CHECKPOINT = 10


@dataclass
class Row:
    id: int
    he: str
    en: str
    by: str
    en_by: str = ""
    original: bool = False
    from_english: bool = False
    #: (lemma, pos) per token, as the build lemmatizer reads the line. Absent until the
    #: row's tranche has run.
    words: list[list[str]] | None = None
    #: The Zipf frequency of the rarest content lemma, or 0 where wordfreq is missing.
    zipf: float = 0.0

    def as_json(self) -> str:
        raw: dict[str, Any] = asdict(self)
        if raw["words"] is None:
            del raw["words"]
        return json.dumps(raw, ensure_ascii=False)


@dataclass
class Exports:
    where: Path
    native: set[str] = field(default_factory=set)
    hebrew: dict[int, tuple[str, str]] = field(default_factory=dict)
    english: dict[int, tuple[str, str]] = field(default_factory=dict)
    base: dict[int, str] = field(default_factory=dict)
    wrong: set[int] = field(default_factory=set)
    links: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))

    def rows(self, path: str) -> Iterator[list[str]]:
        with (self.where / path).open(encoding="utf-8", newline="") as handle:
            yield from csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)

    def read(self) -> None:
        self.native = {
            row[2]
            for row in self.rows("user_languages.csv")
            if len(row) >= 3 and row[0] == "heb" and row[1] == NATIVE
        }
        for row in self.rows("heb_sentences_detailed.tsv"):
            if len(row) >= 4:
                self.hebrew[int(row[0])] = (row[2], row[3])
        for row in self.rows("eng_sentences_detailed.tsv"):
            if len(row) >= 4:
                self.english[int(row[0])] = (row[2], row[3])
        for row in self.rows("sentences_base.csv"):
            if len(row) >= 2 and int(row[0]) in self.hebrew:
                self.base[int(row[0])] = row[1]
        for row in self.rows("users_sentences.csv"):
            if len(row) >= 3 and row[2] == "-1":
                self.wrong.add(int(row[1]))
        for row in self.rows("links.csv"):
            if len(row) >= 2:
                a, b = int(row[0]), int(row[1])
                if a in self.hebrew and b in self.english:
                    self.links[a].append(b)


def select(exports: Exports) -> list[Row]:
    """The rows the pool keeps, originals first and shortest first."""
    out: list[Row] = []
    seen: set[str] = set()
    for sid, (text, user) in exports.hebrew.items():
        text = text.strip()
        if user not in exports.native or sid in exports.wrong or not text or text in seen:
            continue
        linked = exports.links.get(sid)
        if not linked:
            continue
        base = exports.base.get(sid, "")
        original = base == "0"
        from_english = base.isdigit() and int(base) in exports.english
        chosen = (
            int(base)
            if from_english
            else min(linked, key=lambda eid: (len(exports.english[eid][0]), eid))
        )
        en_text, en_user = exports.english[chosen]
        seen.add(text)
        out.append(
            Row(
                id=sid,
                he=text,
                en=en_text.strip(),
                by=user,
                en_by=en_user,
                original=original,
                from_english=from_english,
            )
        )
    out.sort(key=lambda row: (not row.original, len(row.he.split()), row.id))
    return out


def read_pool(path: Path) -> dict[int, Row]:
    """What an earlier run wrote, by id, so its lemmas are not paid for twice."""
    if not path.is_file():
        return {}
    kept: dict[int, Row] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        raw = json.loads(line)
        kept[int(raw["id"])] = Row(**raw)
    return kept


def write_pool(path: Path, rows: Iterable[Row]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(row.as_json() + "\n")
    os.replace(tmp, path)


def lemmatize(rows: list[Row], limit: int, path: Path, all_rows: list[Row]) -> int:
    """Fill in `words` and `zipf` on up to `limit` rows that lack them. Returns how many."""
    from targum.annotate import lemma
    from targum.annotate.base import NOT_VOCABULARY
    from targum.models import Segment

    try:
        from wordfreq import zipf_frequency
    except ImportError:  # pragma: no cover - the difficulty extra
        zipf_frequency = None  # type: ignore[assignment]

    todo = [row for row in rows if row.words is None][:limit]
    if not todo:
        return 0
    reader = lemma.for_source("chat:exemplars")
    started = time.time()
    done = 0
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        segments = [
            Segment(id=f"s{n}", block_id="pool", block_index=0, index=n, text=row.he)
            for n, row in enumerate(batch)
        ]
        read = reader.lemmas(segments, LANGUAGE)
        for n, row in enumerate(batch):
            tokens = read.get(f"s{n}", [])
            row.words = [[token.lemma, token.pos or ""] for token in tokens]
            content = [
                token.lemma
                for token in tokens
                if token.lemma and (token.pos or "") not in NOT_VOCABULARY
            ]
            if zipf_frequency is not None and content:
                row.zipf = round(min(zipf_frequency(word, LANGUAGE) for word in content), 2)
        done += len(batch)
        if (start // BATCH + 1) % CHECKPOINT == 0:
            write_pool(path, all_rows)
            rate = (time.time() - started) / done * 1000
            print(f"  {done}/{len(todo)} lemmatized, {rate:.0f} ms/line", flush=True)
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--exports", type=Path, required=True, help="the unpacked exports")
    parser.add_argument("--out", type=Path, required=True, help="the pool, JSONL")
    parser.add_argument(
        "--limit", type=int, default=0, help="how many more rows to lemmatize (0: none)"
    )
    args = parser.parse_args()

    exports = Exports(args.exports)
    exports.read()
    selected = select(exports)
    earlier = read_pool(args.out)
    rows = [earlier.get(row.id, row) for row in selected]
    for row, fresh in zip(rows, selected, strict=True):
        # The text and the English may have been re-chosen; the lemmas stay theirs.
        if row is not fresh and row.he != fresh.he:
            row.words, row.zipf = None, 0.0
            row.he = fresh.he
        row.en, row.en_by, row.original, row.from_english = (
            fresh.en,
            fresh.en_by,
            fresh.original,
            fresh.from_english,
        )
    originals = sum(1 for row in rows if row.original)
    lemmatized = sum(1 for row in rows if row.words is not None)
    print(
        f"{len(exports.hebrew)} Hebrew sentences, {len(exports.native)} native contributors, "
        f"{len(rows)} kept ({originals} originals), {lemmatized} lemmatized so far"
    )
    if args.limit:
        did = lemmatize(rows, args.limit, args.out, rows)
        print(f"lemmatized {did} more")
    write_pool(args.out, rows)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
