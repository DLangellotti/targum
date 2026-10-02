"""Draft targum's list of English–French false friends (targum-internal#267).

*actuellement* means "currently", *librairie* "bookshop". No permissively licensed list of
these exists; Wiktionary's appendix is CC BY-SA, so it is a thing to look a word up in and
never a thing to copy. This list is written by the model from what it knows of French, a
slice of the alphabet at a time; judged entry by entry in a second, separate request;
checked against Grammalecte's lexicon (MPL-2.0, the pinned copy `french_endings.py`
fetches) so that every entry is a headword, which is what the French lemmatizer emits;
and read once more, which is `DOUBTFUL` below. Nothing from the lexicon ships: it is only
asked whether a word is a headword.

    set -a && . .env && set +a
    python scripts/false_friends.py draft [slices]   # the candidates, kept per slice
    python scripts/false_friends.py check            # the second request, and the lexicon
    python scripts/false_friends.py write            # the table; spends nothing

Every answer and its cost is kept under `~/.targum/cache/false_friends/`, so a run that
stops is resumed rather than paid for twice. The first run, on 2026-09-28, asked for JSON
in a longer prompt; Opus 5 refused that prompt for four of the twelve slices, and those
four were drafted with `DRAFT` as it stands.

The table is `src/targum/annotate/false_friends.json`. Its `reviewed` stays false until a
person has read every line.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from targum.usage import Usage  # noqa: E402

MODEL = "claude-opus-5"
OUT = ROOT / "src" / "targum" / "annotate" / "false_friends.json"
WORK = Path.home() / ".targum" / "cache" / "false_friends"
LEXICON = Path.home() / ".targum" / "cache" / "grammalecte" / "French-08511c222029.lex"

#: The alphabet in slices, so each request drafts a different part of it and no one
#: answer is long enough to be cut off.
SLICES = (
    "a",
    "b",
    "c",
    "d",
    "e",
    "f-h",
    "i-l",
    "m-o",
    "p",
    "q-r",
    "s",
    "t-z",
)

#: Entries judged in one request. Ninety filled the answer with the model's thinking and
#: cut it off; the first two requests of the run were ninety, the rest forty.
CHUNK = 40

#: Dropped on a read after both checks, each for a reason the checks missed. A lemma the
#: card cannot tell from a common word of another meaning (the lemmatizer gives *car* for
#: the coach as well as for "because"), or an English sense that is ordinary French too.
DOUBTFUL = {
    "altérer": "'to alter' is a literary sense still in use",
    "amical": "'amicable' is close enough to 'friendly'",
    "arrêt": "arrêt cardiaque is cardiac arrest",
    "balance": "balance commerciale, a balance in accounts",
    "banc": "banc de sable is a sandbank",
    "blâme": "blâme is blame, as censure",
    "bord": "à bord is on board",
    "bâton": "a baton is a stick",
    "caméra": "a video camera is a camera",
    "car": "the same lemma as un car, a coach",
    "cent": "also a euro cent",
    "chasser": "chasser is also to chase",
    "défaut": "par défaut is by default",
    "essai": "Montaigne's Essais: an essay too",
    "essence": "l'essence de, the essence of",
    "fin": "the same lemma as the adjective fin, fine",
    "fort": "the same lemma as un fort, a fort",
    "front": "the political and military front",
    "grand": "un grand homme, a great man",
    "herbe": "fines herbes: herbs too",
    "moral": "looks like and means morale",
    "or": "the same lemma as the conjunction or",
    "pair": "the same lemma as un pair, a peer",
    "quartier": "le Quartier latin, a quarter",
    "quitter": "quitter son emploi, to quit a job",
    "étranger": "un étranger is also a stranger",
}

#: Wording made consistent with the rest of the table.
REWORDED = {
    "bachelier": {"means": "holder of the baccalauréat"},
}


DRAFT = """List about {count} French words starting with {letters} that are false friends \
for English speakers: they look like an English word but usually mean something else, \
like actuellement (not "actually" but "currently"). Choose the ones a learner is most \
likely to meet. One per line, tab-separated: the French dictionary form (lowercase, a \
verb's infinitive without se), the English look-alike, what it usually means in one to \
four English words, and its part of speech (NOUN, VERB, ADJ, ADV). Nothing else."""

CHECK = """Below is a draft list of English–French false friends for a reading app. \
Each entry becomes one line on a word's card: "false friend: not <looks_like> — <means>".

Judge every entry strictly, from your own knowledge of French. Drop an entry if any of \
these holds:
- the French word does not ordinarily mean what "means" says, or "means" is misleading;
- the English look-alike's sense is also an ordinary sense of the French word today, so \
"not <looks_like>" would be false;
- french is not the dictionary form a lemmatizer gives (infinitive, masculine singular, \
singular noun, lowercase, no "se", one word);
- the word is too rare for a learner to meet, or the resemblance is too weak to mislead;
- you are not sure.

Keep the rest. You may correct the wording of means or looks_like on a kept entry, never \
the french. Answer with a JSON object {{"keep": [entries, corrected], "drop": [{{"french": \
..., "why": ...}}]}} and nothing else.

{entries}"""


def ask(client: Any, usage: Usage, prompt: str, name: str) -> Any:
    """One request, its answer kept under `name` and its cost logged, so a run that
    stops halfway has lost nothing it paid for. A reply that is not JSON is asked again
    once."""
    for _ in range(2):
        reply = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
        )
        usage.add(MODEL, reply.usage.input_tokens, reply.usage.output_tokens)
        with (WORK / "spend.jsonl").open("a") as log:
            log.write(
                json.dumps(
                    {
                        "name": name,
                        "in": reply.usage.input_tokens,
                        "out": reply.usage.output_tokens,
                        "stop": reply.stop_reason,
                        "blocks": [block.type for block in reply.content],
                    }
                )
                + "\n"
            )
        said = "".join(getattr(block, "text", "") for block in reply.content).strip()
        (WORK / f"{name}.txt").write_text(said)
        if said.startswith("```"):
            said = said.split("\n", 1)[1].rsplit("```", 1)[0]
        if name.startswith("draft"):
            return rows(said)
        try:
            return json.loads(said)
        except json.JSONDecodeError as why:
            print(f"{name}: not JSON ({why}), asking again", flush=True)
    raise SystemExit(f"{name}: no JSON twice")


def rows(said: str) -> list[dict[str, str]]:
    """The drafted lines, as entries. A line without four fields is not one."""
    found = []
    for line in said.splitlines():
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) == 4 and all(parts):
            found.append(dict(zip(("french", "looks_like", "means", "pos"), parts, strict=True)))
    return found


def draft(client: Any, usage: Usage, slices: tuple[str, ...] = SLICES) -> None:
    from concurrent.futures import ThreadPoolExecutor

    def one(letters: str) -> list[dict[str, str]]:
        kept = WORK / f"draft-{letters}.json"
        if kept.exists():
            return list(json.loads(kept.read_text()))
        got = ask(client, usage, DRAFT.format(count=45, letters=letters), f"draft-{letters}-raw")
        kept.write_text(json.dumps(got, ensure_ascii=False, indent=1))
        print(f"{letters}: {len(got)}", flush=True)
        return list(got)

    with ThreadPoolExecutor(max_workers=6) as pool:
        found = [entry for got in pool.map(one, slices) for entry in got]
    (WORK / "drafted.json").write_text(json.dumps(found, ensure_ascii=False, indent=1))


def headwords() -> set[str]:
    """Every dictionary form in the lexicon, which is all it is asked."""
    if not LEXICON.exists():
        sys.exit("run scripts/french_endings.py once to fetch the lexicon")
    heads = set()
    for line in LEXICON.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and not line.startswith("#"):
            heads.add(parts[1])
    return heads


def check(client: Any, usage: Usage) -> None:
    drafted = json.loads((WORK / "drafted.json").read_text())
    seen: set[str] = set()
    unique = []
    for entry in drafted:
        if entry["french"] not in seen:
            seen.add(entry["french"])
            unique.append(entry)
    kept: list[dict[str, str]] = []
    dropped: list[dict[str, str]] = []
    at = 0
    while at < len(unique):
        kept_at = WORK / f"check-{at}.json"
        if kept_at.exists():
            said = json.loads(kept_at.read_text())
        else:
            chunk = unique[at : at + CHUNK]
            asked = CHECK.format(entries=json.dumps(chunk, ensure_ascii=False))
            said = {"size": len(chunk), **ask(client, usage, asked, f"check-{at}")}
            kept_at.write_text(json.dumps(said, ensure_ascii=False, indent=1))
        kept.extend(said["keep"])
        dropped.extend(said["drop"])
        at += said["size"]
        print(f"checked {at}: kept {len(kept)}, ${usage.cost():.2f}", flush=True)
    heads = headwords()
    unknown = [entry for entry in kept if entry["french"] not in heads]
    for entry in unknown:
        dropped.append({"french": entry["french"], "why": "not a headword in the lexicon"})
    kept = [entry for entry in kept if entry["french"] in heads]
    (WORK / "checked.json").write_text(
        json.dumps({"keep": kept, "drop": dropped}, ensure_ascii=False, indent=1)
    )
    print(f"{len(kept)} kept, {len(dropped)} dropped")


def write(client: Any, usage: Usage) -> None:
    """The table, from what survived both checks and the read. Spends nothing."""
    kept = json.loads((WORK / "checked.json").read_text())["keep"]
    entries = []
    for entry in kept:
        if entry["french"] in DOUBTFUL:
            continue
        entry = {**entry, **REWORDED.get(entry["french"], {})}
        looks = entry["looks_like"]
        if entry.get("pos") == "VERB" and not looks.startswith("to "):
            looks = "to " + looks
        entries.append(
            {
                "french": entry["french"],
                "looks_like": looks,
                "means": entry["means"],
                "pos": entry["pos"],
            }
        )
    entries.sort(key=lambda entry: entry["french"])
    table = json.loads(OUT.read_text()) if OUT.exists() else {}
    table["entries"] = entries
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(entries)} entries written")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["draft", "check", "write"])
    parser.add_argument("slices", nargs="*", help="the slices to draft, all by default")
    args = parser.parse_args()
    import anthropic

    WORK.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic() if args.step != "write" else None
    usage = Usage()
    if args.step == "draft":
        draft(client, usage, tuple(args.slices) or SLICES)
    else:
        {"check": check, "write": write}[args.step](client, usage)
    print(f"This run cost ${usage.cost():.2f}.")


if __name__ == "__main__":
    main()
