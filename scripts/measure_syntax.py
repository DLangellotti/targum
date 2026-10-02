"""What the dependency tree DICTA already returns would say about the shelf, before
anybody stores it (targum-internal#150).

`dictabert-joint` runs its syntax head on every call, and `dicta._tokens` throws the
answer away. #150 wants that tree on `Token`, which is an annotator rename and so a
scheduled two-hour re-read of the shelf on the box. This measures the three things worth
knowing first, locally and for nothing:

1. **Mean depth and clauses per sentence, per text** (`annotate/syntax.py` says how each
   is counted). The issue's acceptance is that Brenner comes out above the news.
2. **What storing `(head, relation)` would cost**, in bytes per token as the reader's own
   payload writes a word — a row of small integers, so two more of them — and as a share
   of the reader pages on disk, whose median is measured here rather than assumed.
3. **Whether it says anything #320's rungs do not**: Spearman's rank correlation between
   each measure and the rung Jev gave the same sentence (`sentence_level.load()`), matched
   on `sentence_level.key` of the segment's text. Sentence length is correlated the same
   way beside it, since a longer sentence is a deeper one and that is not news.

The texts are every built Brenner in the catalogue and the Wikinews `article` rows, read
from `--out` as a build left them: one segment is one sentence, headings and bylines
left out. A segment longer than the annotator's `PIECE_CHARS` is skipped rather than
cut, since a tree of half a sentence measures the cut. The model is the annotator's own,
at the pinned revision, on the CPU, in the annotator's batches; nothing is written into
`--out`, and nothing here costs money. Each sentence's result is appended to `--save` as
it comes, and a rerun reads that file first.

**Measured 2026-09-28**, four built Brenners (4,286 sentences, 4,070 of them *Shkhol
ve-khishalon*) against six Wikinews articles (352), 74,704 tokens, about 50 minutes on
the laptop's CPU.

- **Clauses order them the way the issue wants; depth does not.** Clauses per sentence:
  Brenner 3.06, the news 2.61, and Brenner is ahead at every sentence length past five
  words (3.00 to 2.45 at 11-20 words, 5.05 to 3.93 at 21-40). Depth: the news 4.56,
  Brenner 3.28, and the news is deeper at every length. The news is deep in its noun
  phrases — `compound`, `nmod` and `flat` are 25% of its arcs and 9% of Brenner's — which
  is titles, names and construct chains, not a harder sentence to follow. Text by text
  neither is clean: the short stories are dialogue and come out below news-livni.
- **Storing it is cheap.** 5.2 bytes a token as the reader writes a word, plus a table of
  the 45 relations once a page. The 1,554 Hebrew reader pages under `library/` have a
  median of 567 kB and 318 word rows, so a page grows by a median 2.1 kB (0.29%), at
  most 0.91%. In `annotation.json`, as two named fields, it is 23.7 bytes a token.
- **Against #320's rungs**, all 4,638 sentences matched: Spearman +0.61 for depth, +0.56
  for clauses, and +0.68 for plain word count. Neither beats sentence length alone.

    .venv/bin/python scripts/measure_syntax.py --out targum-out --save /tmp/syntax.jsonl
    .venv/bin/python scripts/measure_syntax.py --out targum-out --per-text 400
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import catalogue  # noqa: E402
from targum import sentence_level as sl  # noqa: E402
from targum.annotate import syntax  # noqa: E402

#: Kinds of block that are not sentences anybody reads for their Hebrew.
SKIP_KINDS = ("heading", "byline")

#: Who counts as the news: the catalogue's own Wikinews article rows.
NEWS_CREDIT = "Wikinews"

#: And as Brenner: his name as the catalogue spells it in `author`.
BRENNER = "ברנר"

#: Sentence lengths, in words, at which Brenner and the news are compared like for like.
LENGTHS = ((1, 5), (6, 10), (11, 20), (21, 40), (41, 999))

#: The reader's payload, as `render.builder` embeds it.
PAYLOAD = re.compile(r'<script type="application/json" id="targum-data">(.*?)</script>', re.S)


@dataclass
class Text:
    id: str
    group: str
    folder: Path
    sentences: list[str]


def texts(out: Path, news: int) -> Iterator[Text]:
    """Every built Brenner, then up to `news` Wikinews articles, each once however many
    shelves carry a copy, in sorted order so a rerun walks the same way."""
    entries = {catalogue._key(entry.source): entry for entry in catalogue.everything()}
    seen: set[str] = set()
    found: list[Text] = []
    for document in sorted(out.glob("*/*/document.json")):
        folder = document.parent
        try:
            doc = json.loads(document.read_text(encoding="utf-8"))
            seg = json.loads((folder / "segments.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entry = entries.get(catalogue._key(str(doc.get("source") or "")))
        if entry is None or entry.id in seen or entry.language != "he":
            continue
        if BRENNER in entry.author:
            group = "brenner"
        elif entry.kind.value == "article" and entry.credit == NEWS_CREDIT:
            group = "news"
        else:
            continue
        seen.add(entry.id)
        sentences = [
            str(one["text"]).strip()
            for one in seg.get("segments") or []
            if one.get("kind") not in SKIP_KINDS and str(one.get("text") or "").strip()
        ]
        found.append(Text(entry.id, group, folder, sentences))
    yield from (text for text in found if text.group == "brenner")
    yield from [text for text in found if text.group == "news"][:news]


# -- the numbers ----------------------------------------------------------------------


def ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks, ties given the mean of the ranks they span."""
    order = sorted(range(len(values)), key=lambda at: values[at])
    out = [0.0] * len(values)
    at = 0
    while at < len(order):
        end = at
        while end + 1 < len(order) and values[order[end + 1]] == values[order[at]]:
            end += 1
        for one in order[at : end + 1]:
            out[one] = (at + end) / 2 + 1
        at = end + 1
    return out


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman's rho: Pearson's r on the ranks. None where either side is constant or
    there are fewer than three pairs."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if not sxx or not syy:
        return None
    return float(sxy / (sxx * syy) ** 0.5)


def row_bytes(pairs: Sequence[tuple[int, str]], relations: dict[str, int]) -> int:
    """Bytes the reader's word rows would grow by: `,head,relation` on each, the relation
    as its number in a table written once per page."""
    return sum(len(f",{head},{relations[relation]}") for head, relation in pairs)


def field_bytes(pairs: Sequence[tuple[int, str]]) -> int:
    """And what `annotation.json` would grow by, as two named fields on each token."""
    return sum(len(f',"head":{head},"rel":"{relation}"') for head, relation in pairs)


# -- running the model ----------------------------------------------------------------


def measure(sentences: list[str], done: dict[str, dict[str, Any]], save: Path | None) -> None:
    """Put every sentence not in `done` through the model, a batch at a time, and add
    what it says to `done` (and to `save`) as it comes."""
    from targum.annotate.dicta import DictaLemmatizer, _batches

    todo = [text for text in dict.fromkeys(sentences) if sl.key(text) not in done]
    if not todo:
        return
    import torch

    model, tokenizer = DictaLemmatizer(auto_download=False).model()
    sink = save.open("a", encoding="utf-8") if save else None
    try:
        with torch.inference_mode():
            finished = 0
            for batch in _batches(todo):
                read = model.predict([todo[at] for at in batch], tokenizer, output_style="json")
                for at, said in zip(batch, read, strict=True):
                    tree = syntax.tree(said)
                    got = {
                        "key": sl.key(todo[at]),
                        "depth": tree.depth,
                        "clauses": tree.clauses,
                        "words": tree.words,
                        "pairs": tree.on_tokens(),
                    }
                    done[got["key"]] = got
                    if sink:
                        sink.write(json.dumps(got, ensure_ascii=False) + "\n")
                if sink:
                    sink.flush()
                before, finished = finished, finished + len(batch)
                if finished // 500 > before // 500:
                    print(f"  {finished:,} / {len(todo):,}", flush=True)
    finally:
        if sink:
            sink.close()


def recorded(save: Path | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if save is None or not save.exists():
        return out
    for line in save.read_text(encoding="utf-8").splitlines():
        try:
            got = json.loads(line)
        except ValueError:
            continue
        got["pairs"] = [tuple(pair) for pair in got.get("pairs") or []]
        out[str(got["key"])] = got
    return out


# -- the reader pages ------------------------------------------------------------------


def pages(out: Path) -> Iterator[tuple[int, int]]:
    """Each Hebrew reader page under `out/library`: its size in bytes and how many word
    rows its payload carries — the rows a stored tree would lengthen."""
    for page in sorted((out / "library").glob("*/reader/*.html")):
        try:
            doc = json.loads((page.parents[1] / "document.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not str(doc.get("language") or "").startswith("he"):
            continue
        raw = page.read_bytes()
        found = PAYLOAD.search(raw.decode("utf-8", "replace"))
        rows = 0
        if found:
            try:
                words = json.loads(found.group(1)).get("words") or {}
                rows = sum(len(one) for one in words.values())
            except ValueError:
                pass
        yield len(raw), rows


# -- the report -----------------------------------------------------------------------


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else float("nan")


def _rho(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:+.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--news", type=int, default=10, help="Wikinews articles, at most")
    parser.add_argument("--per-text", type=int, default=0, help="sentences per text, at most")
    parser.add_argument("--save", type=Path, default=None, help="per-sentence results, JSONL")
    args = parser.parse_args()

    from targum.annotate.dicta import PIECE_CHARS

    chosen = list(texts(args.out, args.news))
    if not chosen:
        raise SystemExit(f"no Brenner and no Wikinews built under {args.out}")
    skipped = 0
    for text in chosen:
        within = [one for one in text.sentences if len(one) <= PIECE_CHARS]
        skipped += len(text.sentences) - len(within)
        text.sentences = within[: args.per_text] if args.per_text else within

    done = recorded(args.save)
    measure([one for text in chosen for one in text.sentences], done, args.save)

    print(f"\nskipped as longer than {PIECE_CHARS} characters: {skipped}\n")
    print(f"{'text':28} {'group':8} {'sents':>6} {'words':>6} {'depth':>6} {'clauses':>8}")
    groups: dict[str, list[dict[str, Any]]] = {}
    per_text: dict[str, list[tuple[float, float]]] = {}
    for text in chosen:
        rows = [done[sl.key(one)] for one in text.sentences]
        groups.setdefault(text.group, []).extend(rows)
        depth = _mean([row["depth"] for row in rows])
        clauses = _mean([row["clauses"] for row in rows])
        per_text.setdefault(text.group, []).append((depth, clauses))
        words = _mean([row["words"] for row in rows])
        print(f"{text.id:28} {text.group:8} {len(rows):6} {words:6.1f} {depth:6.2f} {clauses:8.2f}")
    print()
    for group, rows in groups.items():
        texts_depth = _mean([depth for depth, _ in per_text[group]])
        texts_clauses = _mean([clauses for _, clauses in per_text[group]])
        print(
            f"{group:8} {len(rows):6} sentences  "
            f"depth {_mean([r['depth'] for r in rows]):.2f} (texts' mean {texts_depth:.2f})  "
            f"clauses {_mean([r['clauses'] for r in rows]):.2f} "
            f"(texts' mean {texts_clauses:.2f})  "
            f"words {_mean([r['words'] for r in rows]):.1f}"
        )
    if {"brenner", "news"} <= set(per_text):
        brenner, news = per_text["brenner"], per_text["news"]
        print(
            "every Brenner above every news text: "
            f"depth {min(d for d, _ in brenner) > max(d for d, _ in news)}, "
            f"clauses {min(c for _, c in brenner) > max(c for _, c in news)}"
        )
        # A longer sentence is a deeper one, so the two are also set side by side at
        # equal length: which reads deeper when the sentence is no longer.
        print(f"\n{'words':>8} {'brenner n':>10} {'depth':>6} {'clauses':>8}", end="")
        print(f" {'news n':>7} {'depth':>6} {'clauses':>8}")
        for low, high in LENGTHS:
            cells = []
            for group in ("brenner", "news"):
                rows = [r for r in groups[group] if low <= r["words"] <= high]
                cells.append(
                    f"{len(rows):>{10 if group == 'brenner' else 7}} "
                    f"{_mean([r['depth'] for r in rows]):6.2f} "
                    f"{_mean([r['clauses'] for r in rows]):8.2f}"
                )
            print(f"{low:>3}-{high:<4} {cells[0]} {cells[1]}")

    # -- what storing it would cost
    every = [row for rows in groups.values() for row in rows]
    relations = {
        name: at
        for at, name in enumerate(sorted({rel for row in every for _, rel in row["pairs"]}))
    }
    tokens = sum(len(row["pairs"]) for row in every)
    per_row = sum(row_bytes(row["pairs"], relations) for row in every) / tokens
    per_field = sum(field_bytes(row["pairs"]) for row in every) / tokens
    table = len(json.dumps(sorted(relations), ensure_ascii=False, separators=(",", ":")))
    print(
        f"\n{tokens:,} tokens, {len(relations)} relations. Stored as the reader writes a word: "
        f"{per_row:.2f} bytes a token, plus a {table}-byte table a page. "
        f"In annotation.json as two named fields: {per_field:.1f} bytes a token."
    )
    sized = list(pages(args.out))
    if sized:
        sizes = [size for size, _ in sized]
        growth = [(rows * per_row + table) / size for size, rows in sized if size]
        added = [rows * per_row + table for _, rows in sized]
        print(
            f"{len(sized)} Hebrew reader pages under {args.out / 'library'}: median "
            f"{statistics.median(sizes) / 1000:.0f} kB, median "
            f"{statistics.median([rows for _, rows in sized]):.0f} word rows; stored, a page "
            f"grows by a median {statistics.median(added) / 1000:.1f} kB "
            f"({100 * statistics.median(growth):.2f}%), at most "
            f"{100 * max(growth):.2f}%"
        )

    # -- against #320's rungs
    levels = sl.load()
    print(f"\n#320 rungs loaded: {len(levels):,}")
    print(f"{'Spearman vs rung score':28} {'n':>6} {'depth':>6} {'clauses':>8} {'words':>6}")
    matched: dict[str, list[tuple[dict[str, Any], float]]] = {}
    for text in chosen:
        for one in text.sentences:
            level = levels.get(sl.key(one))
            if level is not None:
                matched.setdefault(text.group, []).append((done[sl.key(one)], level.score))
    matched["all"] = [pair for pairs in list(matched.values()) for pair in pairs]
    for group, pairs in matched.items():
        score = [s for _, s in pairs]
        cells = [
            _rho(spearman([float(row[measure_]) for row, _ in pairs], score))
            for measure_ in ("depth", "clauses", "words")
        ]
        print(f"{group:28} {len(pairs):6} {cells[0]:>6} {cells[1]:>8} {cells[2]:>6}")


if __name__ == "__main__":
    main()
