"""How much glue is actually left in the shelf, and what a space-fixing model makes of it
(targum-internal#151).

`ingest/spacing.py` repairs words that arrived with the space between them missing, and
its rules only fire where the seam is provable. Everything they decline stays glued, is
looked up as one word, and finds nothing. #151 proposes letting
`dicta-il/dictabert-char-spacefix` propose a seam where the rules cannot see one, with
the rules still deciding — and asks, before any of that is built, how many words are in
that population at all.

This counts them. The population is the issue's own definition: a token `lexicon.known()`
rejects that splits somewhere into two halves it accepts. `known()` is the generous
question, so a token it rejects is one no amount of peeling reaches a word through, and
two halves it accepts is the weakest evidence of a seam there is. Anything outside that
set is either already a word or has nowhere to come apart, and a space-fixer has nothing
to say about it. A surface has to be one token to `unglue` to count: a maqaf compound or
a surface with a space or a gershayim inside is already two words to the tokenizer, and
270 of the first count's 1,937 were exactly that.

It reads the built shelf rather than the sources, which is the right place to look:
`unglue` runs at ingest, so what is on disk is the residue the rules left behind.

    python scripts/measure_glue.py --out targum-out
    python scripts/measure_glue.py --out targum-out --spacefix

Without `--spacefix` nothing here loads a model: it reads `annotation.json`, asks the
lexicon, and prints. With it, the population — and only the population — is put through
the model twice, each token alone and each inside the sentence it was found in, and the
issue's bar is applied: a proposal is accepted when the model wants exactly one space and
that place is one of the seams above, and rejected otherwise. The model is the one the
issue names, 87M parameters on `dictabert-char`, whose card on huggingface.co carries the
licence field `cc-by-4.0`; it is fetched to the Hugging Face cache on first use, runs on
the CPU in small batches, and is never part of an install or a reader. The hosted DICTA
tools are NonCommercial by their terms and are not called.

**Measured 2026-09-07, 422 Hebrew texts, 1,554,472 running tokens.** The population is
1,667 types (3,554 tokens, 0.23% of the shelf), 115 of them long enough for the lexical
rule to have looked at. Read in context, the model proposed nothing for 1,342 of them and
passed the bar on 96 (132 read alone; 39 at the same cut both ways). Every one of the 96
was read by hand, and none is a glued pair: Yiddish and European loanwords (זשידקי,
געווארען, מדיצינה), Aramaic and Mishnaic forms (אמרכלא, דגלחים, ופרוזבולין), ketiv
spellings and names (יהועדי, ראהאליין), and inflected Hebrew the lexicon does not hold
(שאתפחד, ותרעימיני). Precision 0 of 96. The one word on the shelf that reads as glue,
סוקולובספר, drew no proposal. The model does what its card says — it restores the
README's own sentence and splits ברקוביץהקדמה where the certain rule already does — but
what the rules leave on this shelf is not glue, it is vocabulary the lexicon lacks, and a
proposer over it can only ever be wrong. So it is not wired in, and the count is the
reason. The 100 hand-checked splits the issue asks for are the 96: there were no more.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from targum import lexicon
from targum.ingest.spacing import _MIN_PART, _MIN_STRENGTH, _MIN_WHOLE, _TOKEN, _bare, _spellable

SPACEFIX = "dicta-il/dictabert-char-spacefix"

#: How sure the model has to be that a space belongs before a character. Its card draws
#: the line at the label, which is this.
SPACEFIX_THRESHOLD = 0.5

#: Letters of the sentence kept on either side of the token when it is read in context.
WINDOW = 160

#: Tokens per forward pass. The laptop this was measured on has 8 GB and other work.
BATCH = 8

#: What the bar says about one token, given where the model put spaces.
Verdict = tuple[str, int | list[int] | None]


def seams(bare: str) -> list[int]:
    """Every place this comes apart into two words the lexicon knows at all.

    The same scan `_cuts` calls a rival, and deliberately the low bar: `known()` rather
    than `strength()`. A seam here is a candidate, not a repair.
    """
    found = []
    for n in range(_MIN_PART, len(bare) - _MIN_PART + 1):
        left, right = bare[:n], bare[n:]
        if not _spellable(left) or not _spellable(right):
            continue
        if lexicon.known(left) and lexicon.known(right):
            found.append(n)
    return found


def population(surfaces: Iterable[str]) -> dict[str, list[int]]:
    """The surfaces a space-fixer could have something to say about, with their seams.

    One token to `unglue`, long enough to hold two words, unknown as it stands, and
    with somewhere to come apart. A maqaf compound is out: the tokenizer already reads
    it as two words, so a model finding the maqaf finds nothing.
    """
    found: dict[str, list[int]] = {}
    for surface in surfaces:
        if not _TOKEN.fullmatch(surface):
            continue
        bare = _bare(surface)
        if len(bare) < 2 * _MIN_PART or lexicon.known(bare):
            continue
        cuts = seams(bare)
        if cuts:
            found[surface] = cuts
    return found


def verdict(cuts: Sequence[int] | None, seam: Sequence[int]) -> Verdict:
    """The issue's bar: one proposal, at a seam, or nothing.

    `cuts` is where the model wants a space, as letter indexes into the bare token, or
    None where the token could not be read in context at all.
    """
    if cuts is None:
        return "no-context", None
    if not cuts:
        return "no-proposal", None
    if len(cuts) > 1:
        return "many", list(cuts)
    (n,) = cuts
    return ("accept" if n in seam else "off-seam"), n


def _pointed(token: str) -> bool:
    """Whether the token carries vowel points, which says which shelf it came off."""
    return any(unicodedata.category(c) == "Mn" for c in token)


def _read(out: Path) -> tuple[Counter[str], dict[str, set[str]], int]:
    """Every Hebrew surface form on the shelf, counted, with the texts it appears in."""
    surfaces: Counter[str] = Counter()
    where: dict[str, set[str]] = defaultdict(set)
    texts = 0
    for path in sorted(out.rglob("annotation.json")):
        document = json.loads(path.read_text())
        if document.get("language", "").split("-")[0].lower() != "he":
            continue
        texts += 1
        for tokens in document.get("tokens", {}).values():
            for token in tokens:
                surface = token.get("surface") or ""
                if surface:
                    surfaces[surface] += 1
                    where[surface].add(path.parent.name)
    return surfaces, where, texts


def _contexts(out: Path, wanted: set[str]) -> dict[str, str]:
    """One sentence per wanted surface, from the segment its annotation token points at."""
    found: dict[str, str] = {}
    for path in sorted(out.rglob("annotation.json")):
        document = json.loads(path.read_text())
        if document.get("language", "").split("-")[0].lower() != "he":
            continue
        need: dict[str, str] = {}
        for segment_id, tokens in document.get("tokens", {}).items():
            for token in tokens:
                surface = token.get("surface") or ""
                if surface in wanted and surface not in found and surface not in need:
                    need[surface] = segment_id
        segments_path = path.parent / "segments.json"
        if not need or not segments_path.exists():
            continue
        segments = {
            segment["id"]: segment["text"]
            for segment in json.loads(segments_path.read_text())["segments"]
        }
        for surface, segment_id in need.items():
            text = segments.get(segment_id, "")
            if surface in text:
                found[surface] = text
    return found


def _load() -> tuple[Any, Any]:
    """The model and its tokenizer, fetched on first use.

    The tokenizer is built from the repository's `tokenizer.json` directly: the card's
    `tokenizer_config.json` names the slow `BertTokenizer`, which reads a whole word as
    one `[UNK]` and lets the model see nothing. The fast file splits per character, and
    strips nikkud on the way in, which is why a pointed surface can be read unpointed.
    """
    from huggingface_hub import hf_hub_download
    from transformers import AutoModelForTokenClassification, PreTrainedTokenizerFast

    tokenizer = PreTrainedTokenizerFast(
        tokenizer_file=hf_hub_download(SPACEFIX, "tokenizer.json"),
        unk_token="[UNK]",
        cls_token="[CLS]",
        sep_token="[SEP]",
        pad_token="[PAD]",
        mask_token="[MASK]",
    )
    model = AutoModelForTokenClassification.from_pretrained(SPACEFIX).eval()
    return tokenizer, model


def _propose(tokenizer: Any, model: Any, texts: list[str]) -> list[list[int]]:
    """For each text, the character offsets the model wants a space before.

    A space before a space, or before the first character, or after an existing space,
    is not a proposal: the model is asked about letters that touch.
    """
    import torch

    out: list[list[int]] = []
    for start in range(0, len(texts), BATCH):
        chunk = texts[start : start + BATCH]
        encoded = tokenizer(
            chunk,
            return_offsets_mapping=True,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=2048,
        )
        offsets = encoded.pop("offset_mapping").tolist()
        with torch.no_grad():
            scores = model(**encoded).logits.softmax(-1)[:, :, 1].tolist()
        for text, spans, probabilities in zip(chunk, offsets, scores, strict=True):
            proposals = []
            for (begin, end), probability in zip(spans, probabilities, strict=True):
                if begin == end or probability <= SPACEFIX_THRESHOLD:
                    continue
                if text[begin] == " " or begin == 0 or text[begin - 1] == " ":
                    continue
                proposals.append(begin)
            out.append(proposals)
    return out


def _window(surface: str, sentence: str) -> tuple[str, int] | None:
    """The sentence around `surface`, unpointed, and where the token starts in it."""
    words = sentence.split()
    at = next((i for i, word in enumerate(words) if surface in word), None)
    if at is None:
        return None
    bare = _bare(surface)
    left = " ".join(_bare(word) or word for word in words[:at])[-WINDOW:]
    right = " ".join(_bare(word) or word for word in words[at + 1 :])[:WINDOW]
    text = (left + " " if left else "") + bare + (" " + right if right else "")
    return text, len(left) + 1 if left else 0


def spacefix(out: Path, found: dict[str, list[int]]) -> dict[str, tuple[Verdict, Verdict]]:
    """Every surface in the population, with the bar's verdict alone and in context."""
    tokenizer, model = _load()
    order = sorted(found, key=len)
    alone = _propose(tokenizer, model, [_bare(surface) for surface in order])

    sentences = _contexts(out, set(found))
    windows = {
        surface: _window(surface, sentences[surface]) for surface in order if surface in sentences
    }
    readable = [surface for surface in order if windows.get(surface)]
    proposals = _propose(tokenizer, model, [windows[surface][0] for surface in readable])  # type: ignore[index]
    in_context: dict[str, list[int] | None] = dict.fromkeys(order)
    for surface, cuts in zip(readable, proposals, strict=True):
        start = windows[surface][1]  # type: ignore[index]
        end = start + len(_bare(surface))
        in_context[surface] = [cut - start for cut in cuts if start < cut < end]

    return {
        surface: (verdict(alone[i], found[surface]), verdict(in_context[surface], found[surface]))
        for i, surface in enumerate(order)
    }


def _report_spacefix(
    surfaces: Counter[str],
    where: dict[str, set[str]],
    verdicts: dict[str, tuple[Verdict, Verdict]],
    limit: int,
) -> None:
    for mode, pick in (("alone", 0), ("in context", 1)):
        types: Counter[str] = Counter()
        tokens: Counter[str] = Counter()
        for surface, both in verdicts.items():
            types[both[pick][0]] += 1
            tokens[both[pick][0]] += surfaces[surface]
        print(f"\n=== spacefix, each token {mode} ===")
        for kind in ("accept", "off-seam", "many", "no-proposal", "no-context"):
            print(f"  {kind:12s} types {types[kind]:5d}  tokens {tokens[kind]:5d}")
        accepted = [s for s, both in verdicts.items() if both[pick][0] == "accept"]
        gated = sum(1 for s in accepted if len(_bare(s)) >= _MIN_WHOLE)
        print(f"  accepted at or above the {_MIN_WHOLE}-letter gate: {gated}")
        print("  accepted — read every one of these before believing any:")
        for surface in sorted(accepted, key=lambda s: -surfaces[s])[:limit]:
            bare = _bare(surface)
            cut = verdicts[surface][pick][1]
            assert isinstance(cut, int)
            strong = min(lexicon.strength(bare[:cut]), lexicon.strength(bare[cut:]))
            mark = " *" if strong >= _MIN_STRENGTH else ""
            print(
                f"    {surfaces[surface]:5d}  {surface:24s} {bare[:cut]}·{bare[cut:]}"
                f"   strength {strong:.1f}{mark}   [{sorted(where[surface])[0]}]"
            )
    same = sum(1 for a, c in verdicts.values() if a[0] == c[0] == "accept" and a[1] == c[1])
    print(f"\n  accepted both ways at the same cut: {same}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--limit", type=int, default=40, help="How many to list per group.")
    parser.add_argument(
        "--spacefix",
        action="store_true",
        help=f"Put the population through {SPACEFIX} and apply the issue's bar.",
    )
    args = parser.parse_args()

    if not lexicon.available():
        raise SystemExit("no lexicon on this box: install the difficulty extra")

    surfaces, where, texts = _read(args.out)
    running = sum(surfaces.values())
    print(f"Hebrew texts read : {texts}")
    print(f"distinct surfaces : {len(surfaces):,}")
    print(f"running tokens    : {running:,}")

    found = population(surfaces)

    # Split by the rule's own length gate. Below it the lexical rule never looks, so those
    # tokens are in the issue's population and out of the rules' reach — a separate
    # question from the one the rules decline having considered.
    above = {s: cuts for s, cuts in found.items() if len(_bare(s)) >= _MIN_WHOLE}
    below = {s: cuts for s, cuts in found.items() if len(_bare(s)) < _MIN_WHOLE}
    groups = (
        (f"at or above the rule's {_MIN_WHOLE}-letter gate", above),
        ("below that gate, where the lexical rule never looks", below),
    )
    for label, group in groups:
        tokens = sum(surfaces[s] for s in group)
        single = sum(1 for cuts in group.values() if len(cuts) == 1)
        share = tokens / max(running, 1) * 100
        print(f"\n=== {label} ===")
        print(f"  distinct types  : {len(group):,}")
        print(f"  running tokens  : {tokens:,} ({share:.4f}% of the shelf)")
        print(f"  one seam only   : {single}   more than one: {len(group) - single}")
        print(f"  carrying nikkud : {sum(1 for surface in group if _pointed(surface))}")
        ranked = sorted(group.items(), key=lambda item: (-surfaces[item[0]], item[0]))
        for surface, cuts in ranked[: args.limit]:
            bare = _bare(surface)
            shown = " | ".join(f"{bare[:n]}·{bare[n:]}" for n in cuts[:3])
            text = sorted(where[surface])[0]
            print(f"    {surfaces[surface]:5d}  {surface:24s} {shown}   [{text}]")

    if args.spacefix:
        _report_spacefix(surfaces, where, spacefix(args.out, found), args.limit)


if __name__ == "__main__":
    main()
