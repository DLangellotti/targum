"""Score the free checks against the judgements a person actually made.

`dialogue/checks.py` claims to catch things. This says how many, against the 275
corrections David settled one by one on 2026-09-22 — the only Hebrew gold targum owns
that was marked by hand rather than by another model (targum-internal#351 item 2).

Two numbers come out, and the second matters more than the first:

- **recall**: of the gold errors, how many the free checks find. It will be low. Most
  of the 275 are a wrong vowel in a word that is spelled correctly, and no rule decides
  those — that is what the paid reading is for.
- **findings not in the gold**: each is either a real error two model readings and a
  person all missed, or a false positive. A check that produces these in quantity is a
  check that will be ignored, which is worse than a check that finds nothing.

With `--dicta`, the checks in `dialogue/agreement.py` are scored too, one at a time,
because they are the ones on trial (targum-internal#134): each reports its recall on the
corrections of its own kind (`KINDS`), what else in the gold it caught, and a sample of
what it found that the gold does not have, with the line, for a person to read. They
need DICTA's syntax. With `--annotations`, a scene is read from its stored annotation
where that keeps the syntax (annotations since targum-internal#134) and was made from the
same lines; every other scene is read with the local model — free, and slow on a
laptop's CPU, so that reading is kept at the `--dicta` path and read back next time.

    python3 scripts/score_scene_checks.py --scenes ~/…/dialogues --gold …/decisions.json
    PYTHONPATH=src .venv/bin/python scripts/score_scene_checks.py --scenes … --gold … \
        --annotations targum-out/dialogue-readers --dicta ~/…/scenes-dicta.json
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.dialogue.agreement import (  # noqa: E402
    CHECKS,
    GATED,
    Word,
    stored_turn_words,
    words_from_dicta,
)
from targum.dialogue.checks import (  # noqa: E402
    bare,
    check_turn,
    inconsistent_pointing,
)

#: Which settled corrections are of the kinds the agreement checks are for, labelled by
#: hand from the audit's own explanation before any check was scored against them. Keyed
#: as the gold is, (scene, turn, the word's consonants).
KINDS: dict[str, set[tuple[str, int, str]]] = {
    # The numeral's gender or state is wrong for what it counts. The last two are the
    # construct 'two of' written where the day, Monday, was meant.
    "number": {
        ("58-second-opinion", 17, "ובשלושה החודשים"),
        ("38-the-estimate", 5, "שמונה מאות"),
        ("38-the-estimate", 6, "שמונה מאות"),
        ("73-the-inheritance", 14, "שמונה יחידות"),
        ("22-at-the-bank", 9, "עשר"),
        ("26-the-appointment", 6, "שמונה"),
        ("79-the-double-booking", 10, "בשמונה עשר"),
        ("09-the-office", 16, "שני"),
        ("60-the-deadline", 11, "שני"),
    },
    # The construct state is wrong: the article on the head of a chain, an absolute
    # where the construct belongs or the reverse, or a word pointed as a construct noun
    # where none stands. The last eleven are that: a verb or an adjective pointed as the
    # construct noun its letters also spell (הַפְרָעַת for הִפְרַעְתְּ, חוּקֵּי for חוּקִּי).
    "smichut": {
        ("49-the-quiet-carriage", 2, "בקרון השקט"),
        ("84-the-new-manager", 21, "וחצי שנה"),
        ("65-the-leak", 19, "לרוב"),
        ("67-the-demonstration", 3, "מעבר"),
        ("77-the-bad-review", 8, "כוכב"),
        ("82-the-landlady", 28, "בכתב"),
        ("84-the-new-manager", 26, "בראש שקט"),
        ("78-the-driving-test", 25, "פני"),
        ("89-the-tender", 15, "חוקי"),
        ("09-the-office", 32, "חוקי"),
        ("95-the-eviction-notice", 12, "חוקי"),
        ("41-the-neighbour-upstairs", 1, "הפרעת"),
        ("47-the-tickets", 0, "הצלחת"),
        ("69-the-lawyer", 9, "והשכרת"),
        ("74-the-group-chat", 28, "הפסקת"),
        ("84-the-new-manager", 9, "העדפת"),
        ("64-the-partner", 1, "החלטת"),
        ("82-the-landlady", 1, "החלטת"),
    },
}

#: Which kind each agreement check is for.
KIND_OF = {
    "numeral_agreement": "number",
    "numeral_state": "number",
    "article_on_construct": "smichut",
    "construct_governs_nothing": "smichut",
}


def gold_from(path: Path) -> set[tuple[str, int, str]]:
    """The settled corrections, as (scene, turn, the word's consonants).

    Matched on consonants because a judgement quotes the word as it was pointed and a
    check quotes it as it stands; they are the same word.
    """
    out = set()
    for one in json.loads(path.read_text(encoding="utf-8")):
        if one.get("turn") is None or not one.get("word"):
            continue
        out.add((one["scene"], int(one["turn"]), bare(one["word"])))
    return out


def dicta_reading(files: list[Path], path: Path | None) -> dict[str, list[dict[str, Any]]]:
    """DICTA's JSON for every turn, by scene id: read from `path`, or with the local
    model and written there (or nowhere, without a `path`).

    Kept rather than recomputed because it is slow on a CPU — about a second a turn —
    and because it is a fact about the scenes as they were, which do not change.
    """
    if path is not None and path.exists():
        held: dict[str, list[dict[str, Any]]] = json.loads(path.read_text(encoding="utf-8"))
        if all(one.stem in held for one in files):
            return held
    import torch

    from targum.annotate.dicta import BATCH, DictaLemmatizer

    model, tokenizer = DictaLemmatizer(auto_download=False).model()
    out: dict[str, list[dict[str, Any]]] = {}
    for n, one in enumerate(files):
        scene = json.loads(one.read_text(encoding="utf-8"))
        texts = [unicodedata.normalize("NFC", t["text"]) for t in scene["turns"]]
        said: list[dict[str, Any]] = []
        with torch.inference_mode():
            for at in range(0, len(texts), BATCH):
                said += model.predict(texts[at : at + BATCH], tokenizer, output_style="json")
        out[scene["id"]] = said
        print(f"  read {n + 1}/{len(files)} {scene['id']}", file=sys.stderr)
    if path is not None:
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def stored_annotations(root: Path) -> dict[str, tuple[Any, Any]]:
    """Each scene's stored segments and annotation, by scene id, from a folder of built
    texts (`targum-out/dialogue-readers`): the folder whose document names the scene."""
    from targum.models import Annotation, SegmentedDocument

    out: dict[str, tuple[Any, Any]] = {}
    for document in sorted(root.glob("*/document.json")):
        source = str(json.loads(document.read_text(encoding="utf-8")).get("source") or "")
        segments, annotation = (
            document.parent / "segments.json",
            document.parent / "annotation.json",
        )
        if not source.startswith("dialogue:") or not segments.exists() or not annotation.exists():
            continue
        out[source.removeprefix("dialogue:")] = (
            SegmentedDocument.model_validate_json(segments.read_text(encoding="utf-8")).segments,
            Annotation.model_validate_json(annotation.read_text(encoding="utf-8")),
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--scenes", type=Path, required=True, help="the scenes as they were")
    parser.add_argument("--gold", type=Path, required=True, help="decisions.json")
    parser.add_argument("--show", type=int, default=40, help="how many findings to print")
    parser.add_argument(
        "--dicta",
        type=Path,
        default=None,
        help="DICTA's reading of the scenes, kept here; also scores dialogue/agreement.py",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=None,
        help="the built scenes (targum-out/dialogue-readers): read from what they store "
        "where it keeps DICTA's syntax; also scores dialogue/agreement.py",
    )
    parser.add_argument("--sample", type=int, default=20, help="findings not in the gold to show")
    args = parser.parse_args()

    files = sorted(args.scenes.expanduser().glob("*.json"))
    if not files:
        sys.exit(f"No scenes in {args.scenes}.")
    gold = gold_from(args.gold.expanduser())

    found: list[tuple[str, int, str, str, str]] = []
    lines_by_scene: dict[str, list[str]] = {}
    turns = 0
    for path in files:
        scene = json.loads(path.read_text(encoding="utf-8"))
        sid = scene["id"]
        cast = scene.get("cast") or {}
        lines_by_scene[sid] = [t["text"] for t in scene["turns"]]
        for n, turn in enumerate(scene["turns"]):
            turns += 1
            other = "B" if turn.get("who") == "A" else "A"
            addressee = (cast.get(other) or {}).get("gender", "")
            for one in check_turn(turn["text"], turn.get("english", ""), n, addressee, sid):
                found.append((sid, n, bare(one.word), one.kind, one.what))

    print(f"{len(files)} scenes, {turns} turns")
    print(f"gold: {len(gold)} settled corrections\n")

    def matches(one: tuple[str, int, str, str, str]) -> tuple[str, int, str] | None:
        """The gold entry this finding is about, if any.

        Not an equality: a judgement quotes what a person decided about — sometimes a
        phrase, `אֶחָד לְמֵאָה` — and a check quotes what it can point at, sometimes the
        whole line. Either containing the other is the same finding, and a finding with
        no word at all is about the turn.
        """
        sid, turn, word = one[0], one[1], one[2]
        for key in gold:
            if key[0] != sid or key[1] != turn:
                continue
            if not word or word in key[2] or key[2] in word:
                return key
        return None

    hit = [f for f in found if matches(f)]
    miss = [f for f in found if not matches(f)]
    caught = {k for f in found if (k := matches(f))}

    print(f"the free checks raised {len(found)} findings")
    print(
        f"  {len(caught)} are gold errors  -> recall {100 * len(caught) / max(len(gold), 1):.1f}%"
    )
    print(f"  {len(miss)} are not in the gold")

    kinds = collections.Counter(f[3] for f in hit)
    print(f"\ncaught, by kind: {dict(kinds)}")

    if miss:
        print("\nnot in the gold — each is a real error nobody found, or a false positive:")
        for sid, n, word, kind, what in miss[: args.show]:
            print(f"  {sid} t{n} [{kind}] {word or '(line)'}: {what}")
        if len(miss) > args.show:
            print(f"  … and {len(miss) - args.show} more")

    if args.dicta is not None or args.annotations is not None:
        gated = score_agreement(
            files,
            args.dicta.expanduser() if args.dicta else None,
            args.annotations.expanduser() if args.annotations else None,
            gold,
            matches,
            args.sample,
        )
        both = caught | gated
        print(
            f"\n  the gate, free checks and gated agreement checks together: {len(both)}/"
            f"{len(gold)} gold errors -> recall {100 * len(both) / max(len(gold), 1):.1f}%"
            f" (was {len(caught)})"
        )

    clashes = inconsistent_pointing(lines_by_scene)
    print(f"\n{len(clashes)} words the corpus points more than one way:")
    for row in clashes[: args.show]:
        print(f"  {row}")
    if len(clashes) > args.show:
        print(f"  … and {len(clashes) - args.show} more")


def scene_words(
    files: list[Path], dicta: Path | None, annotations: Path | None
) -> dict[str, list[list[Word]]]:
    """Every scene's turns as words: from the store where it keeps the syntax, the rest
    from DICTA — the reading at `dicta` if there is one, else the local model."""
    held = stored_annotations(annotations) if annotations else {}
    out: dict[str, list[list[Word]]] = {}
    rest: list[Path] = []
    for one in files:
        scene = json.loads(one.read_text(encoding="utf-8"))
        texts = [t["text"] for t in scene["turns"]]
        if scene["id"] in held:
            segments, annotation = held[scene["id"]]
            words = stored_turn_words(texts, segments, annotation)
            if words is not None:
                out[scene["id"]] = words
                continue
        rest.append(one)
    print(f"\n{len(out)} scenes read from their stored annotation, {len(rest)} with DICTA")
    if rest:
        reading = dicta_reading(rest, dicta)
        for one in rest:
            scene = json.loads(one.read_text(encoding="utf-8"))
            out[scene["id"]] = [
                words_from_dicta(reading[scene["id"]][n], unicodedata.normalize("NFC", t["text"]))
                for n, t in enumerate(scene["turns"])
            ]
    return out


def score_agreement(
    files: list[Path],
    dicta: Path | None,
    annotations: Path | None,
    gold: set[tuple[str, int, str]],
    matches: Any,
    sample: int,
) -> set[tuple[str, int, str]]:
    """Each agreement check on its own: recall on its kind, and what it found besides.

    Returns the gold the gated ones caught, so the gate can be counted whole.
    """
    reading = scene_words(files, dicta, annotations)
    lines: dict[tuple[str, int], str] = {}
    by_check: dict[str, list[tuple[str, int, str, str, str]]] = {name: [] for name in CHECKS}
    for one in files:
        scene = json.loads(one.read_text(encoding="utf-8"))
        sid = scene["id"]
        for n, turn in enumerate(scene["turns"]):
            text = unicodedata.normalize("NFC", turn["text"])
            lines[(sid, n)] = text
            words = reading[sid][n]
            for name, check in CHECKS.items():
                for f in check(words, n):
                    by_check[name].append((sid, n, bare(f.word), f.kind, f.what))

    for kind, keys in KINDS.items():
        unknown = keys - gold
        if unknown:
            sys.exit(f"KINDS names {kind} corrections that are not in the gold: {unknown}")

    print("\nthe agreement checks, one at a time (dialogue/agreement.py):")
    for name, found in by_check.items():
        kind = KINDS[KIND_OF[name]]
        caught = {k for f in found if (k := matches(f))}
        miss = [f for f in found if not matches(f)]
        mine = caught & kind
        gate = "gated" if name in GATED else "not gated"
        print(f"\n  {name} [{KIND_OF[name]}, {gate}]: {len(found)} findings")
        print(
            f"    recall on its kind: {len(mine)}/{len(kind)}"
            f" = {100 * len(mine) / max(len(kind), 1):.0f}%"
        )
        print(f"    other gold caught: {len(caught - kind)}")
        print(f"    not in the gold: {len(miss)}")
        for key in sorted(caught):
            print(f"    caught  {key[0]} t{key[1]} «{key[2]}»")
        shown = random.Random(134).sample(miss, min(sample, len(miss)))
        for sid, n, word, _, what in sorted(shown):
            print(f"    ?  {sid} t{n} «{word}»: {what}")
            print(f"         {lines[(sid, n)]}")

    for kind, keys in KINDS.items():
        names = [name for name, of in KIND_OF.items() if of == kind]
        every = {k for name in names for f in by_check[name] if (k := matches(f))} & keys
        gated = {k for name in names if name in GATED for f in by_check[name] if (k := matches(f))}
        print(
            f"\n  {kind}: {len(every)}/{len(keys)} caught by any check here,"
            f" {len(gated & keys)}/{len(keys)} by the gated ones"
        )
    return {k for name in GATED for f in by_check[name] if (k := matches(f))}


if __name__ == "__main__":
    main()
