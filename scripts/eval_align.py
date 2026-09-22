"""How well the forced aligner finds word boundaries in synthesised speech.

targum-internal#265's acceptance 2. Word clocks on a read-aloud page — the thing that
would let a line light word by word where there is no recording, only a voice — are held
behind a number nobody had taken. This takes it.

    .venv/bin/python scripts/eval_align.py --languages he,fr,ru,it --words 40 --dry-run
    set -a && . ./.env && set +a && .venv/bin/python scripts/eval_align.py --languages he

**It spends.** The voice is $0.03 a minute, so forty words a language across four is a
few cents — but `--dry-run` prices it first and calls nothing, which is the only honest
default for a script whose whole job is to be run by somebody else.

**Where the truth comes from, and what that costs in honesty.** A synthesiser gives no
per-word timings, so there is nothing to score against unless somebody marks the
boundaries by hand — which is what the card asks for and what a script cannot do. This
takes the other road: **each word is synthesised as its own clip and the clips are joined**,
so every boundary is known exactly, by construction, for nothing.

That is a real measurement and it is not the card's. Words spoken one at a time have no
coarticulation: nothing runs into the next word, and the silences are cleaner than
connected speech ever is. So **this number is an upper bound** — the aligner will not do
better on a natural line than on this. If it fails here it fails everywhere, which makes
a bad number conclusive and a good one only encouraging. A hand-marked pass on natural
lines is still worth doing before change 3 goes on, and `--keep` writes the audio and the
alignment out so that pass has something to start from.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum import evals  # noqa: E402
from targum.audio.align import MODELS, CtcAligner  # noqa: E402
from targum.speech import (  # noqa: E402
    BYTES_PER_SECOND,
    NAME,
    PRICES,
    Clip,
    say,
    wav,
    write,
)

#: Short lines in each language the aligner has a model for. Ordinary sentences rather
#: than anything clever: what is being measured is where a word begins, and a hard word
#: measures the synthesiser instead.
LINES: dict[str, list[str]] = {
    "he": [
        "הילד הלך לבית הספר עם אחותו",
        "אמא שלי קנתה לחם וחלב בחנות",
        "מחר בבוקר נלך לים יחד",
        "הספר הזה מעניין מאוד ואני קורא אותו",
    ],
    "fr": [
        "le garçon est allé à l'école avec sa sœur",
        "ma mère a acheté du pain et du lait",
        "demain matin nous irons à la mer ensemble",
        "ce livre est très intéressant et je le lis",
    ],
    "ru": [
        "мальчик пошёл в школу вместе с сестрой",
        "моя мама купила хлеб и молоко в магазине",
        "завтра утром мы вместе пойдём на море",
        "эта книга очень интересная и я её читаю",
    ],
    "it": [
        "il ragazzo è andato a scuola con sua sorella",
        "mia madre ha comprato il pane e il latte",
        "domani mattina andremo al mare insieme",
        "questo libro è molto interessante e lo leggo",
    ],
}

#: A boundary this close to the truth is right for the purpose. A word lights when the
#: voice reaches it; fifty milliseconds early or late is not visible at reading speed,
#: and it is the tolerance the speech literature uses for the same question.
CLOSE_MS = 50.0


def words_of(language: str, most: int) -> list[str]:
    """The words to measure, in order, drawn from `LINES` until `most` are had."""
    drawn: list[str] = []
    for line in LINES.get(language, []):
        for word in line.split():
            if len(drawn) >= most:
                return drawn
            drawn.append(word)
    return drawn


def spoken_one_by_one(words: list[str], language: str, into: Path) -> tuple[Clip, list[float]]:
    """Say each word alone, join the clips, and answer with the clip and the true
    boundaries.

    The boundary between word *n* and word *n+1* is where the *n*-th clip ended, which
    is arithmetic rather than a judgement — that is the whole point of paying for one
    clip a word rather than one a line.

    The `Clip` comes back rather than the path handed in, because `write` chooses the
    suffix: it keeps mp3 where ffmpeg is present and WAV where it is not, so the file
    that exists is not always the name that was asked for.
    """
    pcm = b""
    boundaries: list[float] = []
    for word in words:
        pcm += say(word, language=language)[44:]
        boundaries.append(len(pcm) / BYTES_PER_SECOND)
    return write(wav(pcm), into), boundaries


def scored(found: list[tuple[float, float, float]], truth: list[float]) -> dict[str, float]:
    """How far each word's end is from where it really ended, in milliseconds.

    The *ends* and not the starts: a start is the previous end by construction here, so
    scoring both would count every boundary twice and halve the error it reports.
    """
    errors = [abs(end - was) * 1000.0 for (_, end, _), was in zip(found, truth, strict=True)]
    return {
        "boundary_ms_mean": round(statistics.fmean(errors), 1),
        "boundary_ms_median": round(statistics.median(errors), 1),
        "within_50ms": round(sum(1 for e in errors if e <= CLOSE_MS) / len(errors), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", default="he,fr,ru,it", help="Comma separated.")
    parser.add_argument("--words", type=int, default=40, help="How many words a language.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Say what it would cost and call nothing."
    )
    parser.add_argument("--keep", type=Path, help="Where to leave the audio and the alignment.")
    parser.add_argument("--ledger", type=Path, help="Which ledger file.")
    parser.add_argument("--note", default="", help="What was different about this run.")
    args = parser.parse_args()

    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    unknown = [code for code in languages if code not in MODELS]
    if unknown:
        sys.exit(
            f"The aligner has no model for {', '.join(unknown)}. It reads: {', '.join(MODELS)}"
        )

    drawn = {code: words_of(code, args.words) for code in languages}
    short = [code for code, words in drawn.items() if not words]
    if short:
        sys.exit(f"No lines written down for {', '.join(short)} — add them to LINES.")

    if args.dry_run:
        # A word is about half a second said alone, which is the number to price with:
        # measured against the shelf's own clips rather than guessed at.
        total = sum(len(words) for words in drawn.values()) * 0.5 / 60.0
        print(f"{'language':10} {'words':>6}")
        for code, words in drawn.items():
            print(f"{code:10} {len(words):>6}")
        print(
            f"\nabout {total:.1f} minutes of speech at ${PRICES[NAME]:.2f}/min "
            f"= about ${total * PRICES[NAME]:.2f}"
        )
        print("Nothing was called. Drop --dry-run to run it.")
        return

    keep = args.keep or Path.home() / ".targum" / "evals" / "align"
    keep.mkdir(parents=True, exist_ok=True)
    rows: list[evals.Row] = []
    for code in languages:
        words = drawn[code]
        clip = keep / f"{code}-{len(words)}.wav"
        print(f"{code}: saying {len(words)} words one at a time…", flush=True)
        made, truth = spoken_one_by_one(words, code, clip)
        aligner = CtcAligner(code)
        usable, hint = aligner.available()
        if not usable:
            sys.exit(f"The forced aligner is not installed: {hint}")
        print(f"{code}: aligning {made.seconds:.1f}s of {made.path.suffix} …", flush=True)
        found = aligner.align(made.path, words, code)
        marks = scored(found, truth)
        (keep / f"{code}-{len(words)}.json").write_text(
            json.dumps(
                {"words": words, "truth": truth, "found": found, "scored": marks},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{code}: {marks}")
        for metric, score in marks.items():
            rows.append(
                evals.Row(
                    at=date.today().isoformat(),
                    stage="align",
                    corpus=f"tts-{code}",
                    metric=metric,
                    score=score,
                    n=len(words),
                    system="ctc-forced-aligner",
                    version=MODELS[code][1],
                    note=(args.note or "one clip a word, joined; boundaries exact by construction"),
                )
            )
    written = evals.append(rows, args.ledger or evals.DEFAULT)
    print(f"\nRecorded {written} rows. The audio and the alignment are in {keep}.")


if __name__ == "__main__":
    main()
