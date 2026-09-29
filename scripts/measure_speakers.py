"""Can a model say who speaks a line well enough to give it a voice? (targum-internal#77)

Plays as free gold: each turn carries its speaker, so the catalogue's Hebrew plays are
parsed into lines and speakers (`targum.speakers.parse_play`), the names are taken off,
and the model is shown the text as dialogue among the stage directions and asked who
says each line and how sure it is. The report is accuracy, and precision and coverage at
each confidence threshold: the card switches a line from the narrator to a dialogue
voice only above a threshold, so the number that matters is how many lines switch at a
threshold that is right, say, 95 times in 100.

**An upper bound for prose.** Every numbered line in a play is speech and the turns
alternate; in a novel neither holds. `alternation` — the speaker two turns back — is
printed beside the model, to say how much of the number the form gives away.

The plays are the catalogue's `play` rows from Project Ben-Yehuda (public domain),
fetched once into `--plays` if they are not there. Two are left out: `לילה בבית הקברות`
is one voice speaking to a grave, and `אחשורוש מלך טפש` prints each name alone on a line
above verse, which this parser does not read. The two Chekhov rows are Russian.

**What it costs.** One Sonnet call per forty lines, about a thousand lines in all: under
$2 at the prices in `PRICES`. Every answer is cached under `--out` by the exact request,
so a rerun, or a change to the report, costs nothing. `--dry-run` parses and prints the
batches without calling anything. `--budget` stops the run before a call that would take
the spend past it.

    op run --env-file op.env -- .venv/bin/python scripts/measure_speakers.py \\
      --plays /tmp/plays --out /tmp/speakers
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import speakers  # noqa: E402
from targum.usage import Usage  # noqa: E402


class Play(NamedTuple):
    id: str
    title: str
    download: int
    #: Every name the play prints before a line, onto the name the gold uses.
    cast: dict[str, str]
    #: Text on the first line of the play proper, after the list of characters.
    opening: str


def same(*names: str) -> dict[str, str]:
    return {name: name for name in names}


PLAYS = [
    Play("play-al-yad-hahalon", "על יד החלון", 1031, same("מנחם", "מרים"), "מנחם ( בלחש )"),
    Play("play-bagan-hair", "בגן העיר", 1381, same("יוסף", "מלכה"), "יוסף ( מתעורר )"),
    Play("play-olam-haba", "עולם הבא", 32067, same("גבריאל", "סרל"), "סרל (יושבת ליד"),
    Play(
        "play-leachar-hakvura",
        "לאחר הקבורה",
        32068,
        same("האלמנה", "הדודה הראשונה", "הדודה השניה", "הדודות"),
        "האלמנה (יושבת על שרפרף",
    ),
    Play(
        "play-hadov",
        "הדוב",
        32078,
        same("הלנה", "סמירנוב", "לוקא"),
        "מחזה ראשון",
    ),
    Play(
        "play-achat",
        "אחת",
        52746,
        same("אמא", "יוסף", "אמנון", "ימימה", "תמר"),
        "תָּמָר, מֵאַיִן",
    ),
    Play(
        "play-bat-hashadchan",
        "בת השדכן",
        40973,
        same("השדכן", "ציפה", "קילה", "חיקלסון", "ליכטנשטין", "ברטה", "ליזה", "רוזה"),
        "קילה. (אל חיקלסון)",
    ),
    Play(
        "play-bimkom-drasha",
        "במקום דרשה",
        24753,
        same("אחיטוב", "שולמית", "דוד", "יוסף", "בנימין", "יקטן", "המורה", "יוסף ובנימין"),
        "אחיטוב (מתהלך",
    ),
    Play(
        "play-baohel",
        "באוהל",
        13951,
        same("יעקב", "שמעון", "לוי", "יהודה", "יששכר", "זבולון", "ראובן", "נפתלי", "גד", "אשר")
        | {"זבלון": "זבולון", "בני ישראל": "בני ישראל", "בני-ישראל": "בני ישראל"}
        | {"בני יעקב": "בני ישראל", "בני-יעקב": "בני ישראל", "אחדים": "אחדים"},
        "(אהל-בד כהה",
    ),
    Play(
        "play-mordechai-vehaman",
        "מרדכי והמן",
        10857,
        same("מרדכי", "אסתר", "המן", "ויזתא", "כלם")
        | {f"ילד {letter}{stop}": f"ילד {letter}" for letter in "אבגד" for stop in ("", ".")}
        | {"יהודים רבים": "יהודים רבים"},
        "תְּמוּנָה רִאשׁוֹנָה",
    ),
]


def source(play: Play, folder: Path) -> str:
    path = folder / f"{play.download}.txt"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        url = f"https://benyehuda.org/download/{play.download}.txt"
        with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
            path.write_bytes(response.read())
    return path.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--plays", type=Path, required=True, help="where the texts are kept")
    parser.add_argument("--out", type=Path, required=True, help="cache and results")
    parser.add_argument("--model", default=speakers.MODEL)
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--batch", type=int, default=40, help="lines asked about per call")
    parser.add_argument("--before", type=int, default=6, help="paragraphs of context before")
    parser.add_argument("--after", type=int, default=4, help="paragraphs of context after")
    parser.add_argument("--only", nargs="*", default=None, help="play ids")
    parser.add_argument("--budget", type=float, default=5.0, help="USD, stop before passing")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    chosen = [play for play in PLAYS if not args.only or play.id in args.only]
    usage = Usage()
    client = None
    if not args.dry_run:
        import anthropic

        client = anthropic.Anthropic()

    gold: dict[str, str] = {}
    guessed: dict[str, tuple[str, float]] = {}
    baseline: dict[str, str] = {}
    by_play: dict[str, dict[str, object]] = {}
    rows = []
    for play in chosen:
        lines = speakers.parse_play(
            source(play, args.plays), play.cast, opening=play.opening, prefix=f"{play.id}:"
        )
        cast = speakers.speakers(play.cast)
        spoken = [line for line in lines if line.speaker is not None]
        mine = {line.id: str(line.speaker) for line in spoken}
        gold |= mine
        baseline |= speakers.alternation(lines)
        if args.dry_run:
            print(f"== {play.id}: {len(spoken)} lines, {len(lines) - len(spoken)} directions")
            print(speakers.present(lines[:12]))
            continue
        answers: dict[str, tuple[str, float]] = {}
        for before, batch, after in speakers.windows(
            lines, args.batch, before=args.before, after=args.after
        ):
            if usage.cost() > args.budget:
                sys.exit(f"stopped at ${usage.cost():.2f}, over the ${args.budget:.2f} budget")
            answers |= speakers.ask(
                client,
                cast,
                before,
                batch,
                after,
                model=args.model,
                effort=args.effort,
                usage=usage,
                cache=args.out / "cache",
            )
        guessed |= answers
        named = {key: value[0] for key, value in answers.items()}
        by_play[play.id] = {
            "title": play.title,
            "cast": len(cast),
            "lines": len(spoken),
            "accuracy": round(speakers.accuracy(mine, named), 3),
            "alternation": round(speakers.accuracy(mine, speakers.alternation(lines)), 3),
        }
        for line in spoken:
            name, confidence = answers.get(line.id, (speakers.UNKNOWN, 0.0))
            rows.append(
                {
                    "id": line.id,
                    "gold": line.speaker,
                    "said": name,
                    "confidence": confidence,
                    "text": line.text,
                }
            )

    if args.dry_run:
        print(f"{len(gold)} lines in all; alternation {speakers.accuracy(gold, baseline):.3f}")
        return

    named = {key: value[0] for key, value in guessed.items()}
    points = speakers.curve(gold, guessed)
    # The lines where the two-back rule fails: what the model does when the form does
    # not hand it the answer.
    broken = {key: value for key, value in gold.items() if baseline.get(key) != value}
    report = {
        "model": args.model,
        "effort": args.effort,
        "batch": args.batch,
        "context": [args.before, args.after],
        "plays": len(chosen),
        "lines": len(gold),
        "accuracy": round(speakers.accuracy(gold, named), 3),
        "alternation": round(speakers.accuracy(gold, baseline), 3),
        "off_alternation": {
            "lines": len(broken),
            "accuracy": round(speakers.accuracy(broken, named), 3),
        },
        "curve": [
            {
                "threshold": point.threshold,
                "switched": point.switched,
                "coverage": round(point.coverage, 3),
                "precision": round(point.precision, 3),
            }
            for point in points
        ],
        "at_precision": {},
        "by_play": by_play,
        "spent_usd": round(usage.cost(), 4),
        "calls": usage.calls,
        "tokens": [usage.input_tokens, usage.output_tokens],
    }
    # Every distinct confidence is a threshold, so the bar is found exactly rather than
    # on the printed grid.
    fine = speakers.curve(gold, guessed, sorted({value[1] for value in guessed.values()}))
    for bar in (0.9, 0.95, 0.98):
        point = speakers.lowest(fine, bar)
        report["at_precision"][str(bar)] = (  # type: ignore[index]
            None
            if point is None
            else {
                "threshold": point.threshold,
                "switched": point.switched,
                "coverage": round(point.coverage, 3),
                "precision": round(point.precision, 3),
            }
        )
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "lines.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    (args.out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"spent ${usage.cost():.4f} over {usage.calls} calls")


if __name__ == "__main__":
    main()
