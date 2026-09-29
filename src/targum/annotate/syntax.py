"""The shape of a Hebrew sentence, read off the tree DICTA already returns (#150).

`dictabert-joint` runs its syntax head on every call — `do_syntax` is on in the model's
own config — so each word `model.predict(..., output_style="json")` hands back carries a
`syntax` block: the index of its head word (`-1` at the root) and the relation to it, in
Universal Dependencies. `dicta._tokens` reads the lemma, the morphology and the entities
out of the same answer and has never read this. Nothing here changes that: this is the
measuring half of #150, and it takes a sentence's answer as it came, so a script can ask
what the tree would say before anybody decides whether a `Token` should carry it.

**Depth** is the longest walk from a word up to the root, in arcs: the root is at 0, a
word hanging off it at 1, and a one-word sentence is 0 deep. Punctuation is left out,
because a full stop hangs off the root in every sentence and says nothing about the
sentence's shape.

**Clauses** are counted from the relations rather than guessed from the verbs. One per
root, and one more per word attached by a relation that opens a clause of its own:

- `ccomp`, `csubj` — a clause that is an argument ("he said *that the boy left*");
- `advcl` — a clause that modifies ("*when he came*, ...");
- `acl`, with `acl:relcl` — a clause that modifies a noun ("the boy *who saw*");
- `parataxis` — a clause set beside another with no word joining them;
- `conj`, only where the conjunct is a verb — "he went home *and ate*" is two clauses,
  "bread and butter" is none.

Subtypes count as their base relation. `xcomp` is left out on purpose: an infinitive that
completes its verb ("he wanted *to go*") shares that verb's subject, and a reader does
not parse it as a second sentence. A clause whose predicate is a noun or an adjective
still counts under the first four, since Hebrew needs no verb to make one; only `conj`
asks for a verb, because that is the one relation that joins phrases as readily as
clauses.

**The pairs** come two ways: `Tree.arcs` in the model's own order, which counts
punctuation as words, and `Tree.on_tokens()` renumbered to the words `dicta._tokens`
keeps, which is the shape a `Token` would carry them in. Both use `-1` for the root.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Relations that attach a clause of its own, by their base name.
CLAUSAL = frozenset({"ccomp", "csubj", "advcl", "acl", "parataxis"})

#: And the one that does only when what it joins is a verb.
CONJ = "conj"
PREDICATES = frozenset({"VERB", "AUX"})

#: What the model calls punctuation, by tag or by relation.
PUNCT_POS = frozenset({"PUNCT", "SYM"})
PUNCT_REL = "punct"

#: The head the model gives the root.
ROOT = -1


@dataclass(frozen=True)
class Tree:
    """One sentence's shape."""

    #: The longest walk from a word to the root, in arcs, punctuation left out.
    depth: int
    #: Roots plus clause-opening attachments; see the module's docstring.
    clauses: int
    #: Words that are not punctuation.
    words: int
    #: `(head, relation)` per word, in the model's order, `-1` at the root.
    arcs: tuple[tuple[int, str], ...]
    #: Which of those words are punctuation, in the same order.
    punct: tuple[bool, ...] = ()

    def on_tokens(self) -> list[tuple[int, str]]:
        """The pairs as a `Token` list would hold them. Punctuation is never a token, so
        it is dropped and every head renumbered to the words kept; a head that was
        punctuation (the model has not been seen to do it) is read through to that
        word's own head."""
        punct = self.punct or (False,) * len(self.arcs)
        kept = [at for at in range(len(self.arcs)) if not punct[at]]
        renumber = {old: new for new, old in enumerate(kept)}
        out: list[tuple[int, str]] = []
        for at in kept:
            head, relation = self.arcs[at]
            passed = {at}
            while 0 <= head < len(self.arcs) and punct[head] and head not in passed:
                passed.add(head)
                head = self.arcs[head][0]
            out.append((renumber.get(head, ROOT), relation))
        return out


def base(relation: str) -> str:
    """`acl:relcl` as `acl`: the relation without its subtype."""
    return relation.split(":", 1)[0]


def arcs(said: dict[str, Any]) -> tuple[tuple[int, str], ...]:
    """The `(head, relation)` pairs of one sentence's predict answer.

    A word with no syntax block, or a head that is not a number, is read as a root
    with no relation: the model has never done this, and a sentence it cannot measure
    should come out shallow rather than raise halfway through a book.
    """
    out: list[tuple[int, str]] = []
    for word in said.get("tokens") or []:
        syntax = word.get("syntax") or {}
        try:
            head = int(syntax.get("dep_head_idx", ROOT))
        except (TypeError, ValueError):
            head = ROOT
        out.append((head, str(syntax.get("dep_func") or "")))
    return tuple(out)


def _punctuation(said: dict[str, Any], pairs: tuple[tuple[int, str], ...]) -> tuple[bool, ...]:
    words = said.get("tokens") or []
    return tuple(
        (words[at].get("morph") or {}).get("pos") in PUNCT_POS or base(relation) == PUNCT_REL
        for at, (_, relation) in enumerate(pairs)
    )


def tree(said: dict[str, Any]) -> Tree:
    """Depth, clauses and pairs for one sentence of `model.predict(..., "json")`."""
    pairs = arcs(said)
    punct = _punctuation(said, pairs)
    words = said.get("tokens") or []
    kept = [at for at in range(len(pairs)) if not punct[at]]
    depth = max((_walk(at, pairs) for at in kept), default=0)
    clauses = 0
    for at in kept:
        head, relation = pairs[at]
        if head == ROOT or base(relation) in CLAUSAL:
            clauses += 1
        elif base(relation) == CONJ and (words[at].get("morph") or {}).get("pos") in PREDICATES:
            clauses += 1
    return Tree(depth=depth, clauses=clauses, words=len(kept), arcs=pairs, punct=punct)


def _walk(at: int, pairs: tuple[tuple[int, str], ...]) -> int:
    """Arcs from word `at` up to where its chain of heads stops: the root, or a head out
    of range, or a word already passed. The model has produced neither of the last two;
    a malformed tree should read shallow rather than walk forever."""
    seen = {at}
    steps = 0
    head = pairs[at][0]
    while 0 <= head < len(pairs) and head not in seen:
        seen.add(head)
        steps += 1
        head = pairs[head][0]
    return steps
