"""How level-appropriate is what the shelf offers? targum-internal#244, acceptance 4.

The card asks for *"the mean `known_share` of offered cards, over the stored prompts
re-run live"*. That measurement cannot be taken on a laptop, and the reason is not the
key or the memory: **`known_share` rides only a row that is already built**
(`tools.py`, inside `if built is not None`), so the mean is taken over the built shelf
and not over the catalogue. A box with the shelf on it answers one question; a laptop
with six canon texts against nine hundred catalogue rows answers a different one, and
the two are not comparable unless the shelf is written down beside the number.

So this takes the narrowed measurement David chose on 2026-09-22, and **records the
shelf size with it** — `n` is the suggestions read and `corpus` names the shelf, so a
later run on a fuller shelf is a different row rather than the same one moved.

**It calls no model and spends nothing.** `suggest_next` is the ranking, and the
ranking is what generalises: whether the *model* picks well from what it is handed is
the other half of criterion 4 and still wants the box. What is measured here is what it
is handed.

    .venv/bin/python scripts/eval_suggest.py --out ~/targum-canon
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum import evals  # noqa: E402
from targum import level as level_module  # noqa: E402
from targum.accounts import Store  # noqa: E402
from targum.chat import hebrew, tools  # noqa: E402
from targum.serve import Library  # noqa: E402


def reader_who_knows(store: Store, many: int, language: str) -> Any:
    """An account with `many` of the commonest words marked known.

    The commonest rather than a sample of the catalogue's: that is what a reader at this
    size actually knows, and drawing from the texts being ranked would measure the
    drawing rather than the ranking.
    """
    token = store.start_sign_in("eval@targum.page")
    signed = store.finish_sign_in(token)
    if signed is None:
        sys.exit("could not make an account to measure with")
    person = signed[0]
    common = hebrew.common_words()
    if not common:
        sys.exit("wordfreq is not installed: uv sync --extra difficulty")
    store.push(
        person,
        {
            "words": [
                {
                    "language": language,
                    "lemma": word,
                    "status": 9,
                    "band": "easy",
                    "at": n + 1,
                    "seen": n + 1,
                }
                for n, word in enumerate(common[:many])
            ]
        },
    )
    return person


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--known", type=int, default=500, help="words the reader knows")
    parser.add_argument("--limit", type=int, default=10, help="suggestions to read")
    parser.add_argument("--language", default="he")
    parser.add_argument(
        "--out",
        type=Path,
        help="the readers directory `targum serve` is given, NOT a shelf inside it",
    )
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    out = args.out or (Path.home() / "targum-out")
    with tempfile.TemporaryDirectory() as where:
        store = Store(Path(where) / "words.db")
        person = reader_who_knows(store, args.known, args.language)
        # `Library(out)` and then `library.home(...)`, never `Library(a_home)`.
        #
        # **`Library.__init__` calls `adopt()`**, which moves every built text at the top
        # of `out` down into the signed-out home. Handed a shelf as its `out`, it does
        # that to the shelf — and again on the next call, and again, nesting `local/`
        # one deeper every time. It cost the canon shelf five levels on 2026-09-22
        # before I understood that the call was doing it rather than something else on
        # the machine.
        library = Library(out)
        home = library.home(None)
        # Both shelves, because both are what a suggestion can come from — and the
        # *shared* one is where the number comes from in practice. `suggest_next` never
        # offers a text the reader already has (`if key in own: continue`), so a reader
        # who owns every built text on the machine is offered none of them and no
        # suggestion carries a known share at all. Counting only the signed-out home
        # recorded `shelf-0` beside six offered rows on the first run, which is the kind
        # of label that makes a number useless a month later.
        built = library.readers(home) + library.readers(library.shared)
        ctx = tools.Ctx(
            person=person,
            home=home,
            library=library,
            store=store,
            chat_id="eval",
            level=level_module.snapshot(store, person.id, args.language),
            reads={"en"},
            said_reads={"en"},
        )
        offered = tools.suggest_next(ctx, {"language": args.language, "limit": args.limit})[
            "suggestions"
        ]

    shares = [float(row["known_share"]) for row in offered if row.get("known_share") is not None]
    print(f"shelf at {home}: {len(built)} built")
    print(f"{len(offered)} suggestions read, {len(shares)} carrying a known share\n")
    for row in offered[: args.limit]:
        share = row.get("known_share")
        said = "—" if share is None else f"{float(share):.2f}"
        print(f"  {said:>5}  {str(row.get('title') or row.get('id'))[:56]}")

    if not shares:
        print(
            "\nNo suggestion carried a known share, so there is no mean to take: "
            "`known_share` rides only a built row, and this shelf has none the "
            "catalogue matches. Nothing recorded."
        )
        return

    mean = statistics.fmean(shares)
    print(f"\nmean known_share of offered built rows: {mean:.3f}")
    rows = [
        evals.Row(
            at=date.today().isoformat(),
            stage="suggest",
            # The shelf is part of the measurement, not context for it: the same
            # ranking over a fuller shelf is a different number and deserves its own row.
            corpus=f"shelf-{len(built)}",
            metric=metric,
            score=round(score, 4),
            n=len(offered),
            system="suggest_next",
            version=f"known-{args.known}",
            note=(
                args.note or "narrowed from #244 acceptance 4: the ranking, not the model's pick"
            ),
        )
        for metric, score in (
            ("suggested_known_share", mean),
            ("suggested_with_known_share", len(shares) / len(offered) if offered else 0.0),
        )
    ]
    print(f"Recorded {evals.append(rows, args.ledger)} rows.")


if __name__ == "__main__":
    main()
