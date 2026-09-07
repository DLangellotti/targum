"""How long the annotator takes on one line of conversation.

The record forming in the thread (design.md §12, 2026-09-06) annotates every Hebrew
line the model writes as it arrives, so the words can take their ledger state while
the reader is still reading them. Whether that is "as it arrives" or "a moment later"
is a number, not a hope: the annotator is a BERT model on a box with no GPU, measured
at about a text a minute over a whole shelf. A line is not a text, and this says what
a line costs — cold, with the model still to load, and warm, line by line and in a
batch of a turn's worth.

    PYTHONPATH=src .venv/bin/python scripts/measure_line_annotation.py

Prints JSON. Run it on the box, not only on a laptop: the number that gates the record
is the box's.
"""

from __future__ import annotations

import json
import time

from targum.annotate import lemma
from targum.models import Segment
from targum.vocalize.base import strip_nikkud

LINES = [
    "נָסַעְתִּי לַנֶּגֶב בַּשָּׁבוּעַ שֶׁעָבַר, הָיָה חַם מְאוֹד.",
    "יָפֶה. מָה רָאִיתָ שָׁם? הָיִיתָ בְּמִצְפֵּה רָמוֹן?",
    "כֵּן, הַמַּכְתֵּשׁ הָיָה עָצוּם.",
    "הַמַּכְתֵּשׁ הוּא מָקוֹם שֶׁהַמַּיִם לָחֲצוּ וְחָפְרוּ.",
    "הָיָה לְךָ מִצְפֶּה טוֹב?",
]


def segments(lines: list[str]) -> list[Segment]:
    out = []
    for index, line in enumerate(lines):
        plain, _ = strip_nikkud(line)
        out.append(Segment(id=f"l{index}", block_id="b", block_index=0, index=index, text=plain))
    return out


def main() -> None:
    model = lemma.for_source("chat:measure")
    timings: dict[str, float] = {}

    started = time.perf_counter()
    first = model.lemmas(segments(LINES[:1]), "he")
    timings["cold_one_line"] = time.perf_counter() - started

    warm = []
    for line in LINES[1:]:
        started = time.perf_counter()
        model.lemmas(segments([line]), "he")
        warm.append(time.perf_counter() - started)
    timings["warm_one_line_mean"] = sum(warm) / len(warm)
    timings["warm_one_line_max"] = max(warm)

    started = time.perf_counter()
    batch = model.lemmas(segments(LINES), "he")
    timings["warm_five_lines_batch"] = time.perf_counter() - started

    print(
        json.dumps(
            {
                "lemmatizer": model.name,
                "seconds": {key: round(value, 3) for key, value in timings.items()},
                "tokens_first_line": [token.lemma for token in first["l0"]],
                "tokens_batch": sum(len(tokens) for tokens in batch.values()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
