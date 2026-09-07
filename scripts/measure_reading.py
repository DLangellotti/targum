"""How well targum reads pictures and text-layer PDFs, against transcriptions checked by hand.

    set -a && . ./.env && set +a
    PYTHONPATH=$PWD/src .venv/bin/python scripts/measure_reading.py <folder>

The folder holds pictures (`.png .jpg .jpeg .webp .heic`) and PDFs, each beside a `.txt`
of the same name holding what the page really says, one printed line per line. The
sample set is the builder's own phone and screen and stays out of the public repo
(targum-internal#217, acceptance criterion 7); `tests/fixtures/pages` holds one
Chromium-drawn pair of each kind for a dry run.

Two numbers a file, both order-free. *Words* is the share of the truth's words found in
the reading, spelled exactly, nikkud and all. *Letters* is the same after every mark is
stripped, which is what a reader tapping a word needs and what a font's vowel
placement should not decide. Pictures are read through the model (a real spend, at
the cache's mercy: a picture already read costs nothing); PDFs cost nothing.
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

from targum import vision
from targum.ingest import pdf as pdf_module
from targum.usage import Usage

MARKS = re.compile(r"[֑-ׇ]")
PUNCT = re.compile(r"[^\wא-ת]+")


def words(text: str) -> Counter[str]:
    return Counter(w for w in PUNCT.sub(" ", text).split() if w)


def letters(text: str) -> Counter[str]:
    return words(MARKS.sub("", text))


def share(truth: Counter[str], read: Counter[str]) -> float:
    total = sum(truth.values())
    if not total:
        return 1.0
    return sum(min(count, read[word]) for word, count in truth.items()) / total


def main(folder: Path) -> int:
    pairs = []
    for path in sorted(folder.iterdir()):
        truth = path.with_suffix(".txt")
        if path.suffix.lower() in vision.PICTURE_SUFFIXES | {".pdf"} and truth.is_file():
            pairs.append((path, truth))
    if not pairs:
        print(f"nothing to measure in {folder}: a picture or a PDF beside its .txt")
        return 1
    usage = Usage()
    started = time.monotonic()
    totals = {"pictures": [0.0, 0.0, 0], "pdfs": [0.0, 0.0, 0]}
    print(f"{'file':40} {'words':>7} {'letters':>8} {'doubt':>6}")
    for path, truth in pairs:
        expected = truth.read_text(encoding="utf-8")
        if path.suffix.lower() == ".pdf":
            pages = pdf_module.page_lines(path)
            got = "\n".join(line for lines in pages for line in lines)
            doubtful = pdf_module.doubtful_lines(pages)
            bucket = totals["pdfs"]
        else:
            read = vision.read_pages([path], usage=usage)[0]
            got, doubtful = read.text, read.doubtful
            bucket = totals["pictures"]
        by_word = share(words(expected), words(got))
        by_letter = share(letters(expected), letters(got))
        bucket[0] += by_word
        bucket[1] += by_letter
        bucket[2] += 1
        print(f"{path.name:40} {by_word:7.1%} {by_letter:8.1%} {doubtful:6d}")
    for kind, (by_word, by_letter, count) in totals.items():
        if count:
            print(f"{kind:40} {by_word / count:7.1%} {by_letter / count:8.1%}   over {count}")
    seconds = time.monotonic() - started
    print(
        f"model: {usage.calls} calls, {usage.input_tokens} in / {usage.output_tokens} out, "
        f"${usage.cost():.4f}, {seconds:.1f} s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/pages")))
