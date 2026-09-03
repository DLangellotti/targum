"""Where a word went when the annotator changed (targum-internal#141).

A reader's marked words are stored by lemma — `targum:vocab:<language>` maps lemma to
what they said about it — so a text re-annotated by a different annotator orphans every
mark whose lemma moved. Measured against the real store, that is 23.4% of marks, and it
is silent: nothing in the reader knows the word it is showing used to be called something
else.

This works out the moves for one text, by pairing the annotation that was on disk against
the one just made. It is a by-product of a rebuild rather than a pass of its own — both
annotations are already in hand at that moment, and a token pairs with a token by where it
sits in the text, which is the one thing two annotators cannot disagree about.

**Nothing here may be applied unscreened.** On the first full run over the shelf, 15% of
the moves landed on a *different word*: הבליח → מבצבץ, הכסיף → מכוסה, a place name →
סובייטי. Carrying a mark across one of those is worse than losing it — an orphaned mark is
a word the reader meets again, while a mis-migrated one sits in their list for good under
a meaning that was never theirs. So `same_word` asks whether the two spellings still share
a run of letters the way a real derivation does, and anything that fails is left out. It
is a screen and not a verdict: `הללו → אלה` fails it and is arguably right. Held back is
the safe side of that error.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..models import Annotation

# Where a text keeps what its words used to be called. Beside the annotation, because it
# is about that annotation — and on disk rather than only in the page, for the reason
# `keep` exists.
FILE = "moves.json"

# Folded so a rule can see past a final letter, exactly as `hebrew.py` folds them.
FINALS = str.maketrans("ךםןףץ", "כמנפצ")


def letters(word: str) -> str:
    return "".join(c for c in word.translate(FINALS) if "א" <= c <= "ת")


def shared(old: str, new: str) -> int:
    """The longest run of letters both words spell in order."""
    first, second = letters(old), letters(new)
    best = [[0] * (len(second) + 1) for _ in range(len(first) + 1)]
    for i, one in enumerate(first, 1):
        for j, two in enumerate(second, 1):
            best[i][j] = (
                best[i - 1][j - 1] + 1 if one == two else max(best[i - 1][j], best[i][j - 1])
            )
    return best[len(first)][len(second)]


def same_word(old: str, new: str) -> bool:
    """Whether the new lemma is plausibly the old word spelled another way.

    A derivation keeps most of its letters in order — לאורך and ארך, מסביב and סביב. A
    hallucination does not: הבליח and מבצבץ share one letter between them.
    """
    if not old or not new or "##" in new:
        return False
    need = max(2, min(len(letters(old)), len(letters(new))) - 1)
    return shared(old, new) >= need


def carried(folder: Path) -> dict[str, Any]:
    """What this text already knows its words used to be called, or nothing."""
    try:
        held = json.loads((folder / FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return held if isinstance(held, dict) else {}


def _named(tables: dict[str, Any]) -> dict[str, Any]:
    """The same tables, under a name that changes when they do.

    The reader applies a table once and remembers the name it applied. So the name has to
    come from the content: a text whose moves have grown must be applied again, and one
    rebuilt with nothing new must not.
    """
    body = json.dumps(
        {"lemmas": tables.get("lemmas") or {}, "surfaces": tables.get("surfaces") or {}},
        ensure_ascii=False,
        sort_keys=True,
    )
    return {"id": hashlib.sha256(body.encode()).hexdigest()[:12], **tables}


def keep(folder: Path, now: dict[str, Any]) -> dict[str, Any]:
    """Add what just moved to what had already moved, write it down, and hand it back.

    Without this a text's moves lived exactly one rebuild. The build that re-annotated
    put them in the page; the next build found the annotator unchanged, worked out no
    moves, and rendered the page without them — so a reader who did not open that targum
    in between lost their marks for good, silently, which is the whole failure #141 is
    about. Two rebuilds in one evening is not a hypothetical: it is what a deploy that
    fails halfway and gets run again does.

    Composed rather than merely merged. A word that went אורך → ארך in one rebuild and
    ארך → אורח in the next has to reach a reader still holding אורך as אורך → אורח, or
    the second rebuild strands exactly the marks the first one moved.
    """
    before = carried(folder)
    lemmas: dict[str, str] = dict(before.get("lemmas") or {})
    surfaces: dict[str, str] = dict(before.get("surfaces") or {})
    fresh_lemmas: dict[str, str] = dict(now.get("lemmas") or {})
    fresh_surfaces: dict[str, str] = dict(now.get("surfaces") or {})

    for table in (lemmas, surfaces):
        for was, to in list(table.items()):
            if to in fresh_lemmas:
                table[was] = fresh_lemmas[to]
    lemmas.update(fresh_lemmas)
    surfaces.update(fresh_surfaces)
    # A word that ended up back where it started is not a move, and carrying it would
    # have the reader rename a mark onto itself.
    tables = {
        "lemmas": {was: to for was, to in lemmas.items() if was != to},
        "surfaces": surfaces,
    }
    held = _named(tables)
    if held["lemmas"] or held["surfaces"]:
        (folder / FILE).write_text(json.dumps(held, ensure_ascii=False, indent=1), encoding="utf-8")
    return held


def between(old: Annotation, new: Annotation) -> dict[str, object]:
    """What a mark filed under the old annotation should be called under the new one.

    Two tables, because one cannot answer. `lemmas` is old → new where every occurrence
    agrees, and settles a mark on the lemma alone. `surfaces` is for the words that split:
    `הוא` went to `הוא`, `לו`, `את`, `לי` and `אני` at once under DICTA, and only the
    surface a reader actually marked can say which card is theirs — which the store keeps
    beside every mark.
    """
    went: dict[str, Counter[str]] = defaultdict(Counter)
    surfaced: dict[str, Counter[str]] = defaultdict(Counter)
    filed: dict[str, set[str]] = defaultdict(set)
    for segment, tokens in new.tokens.items():
        before = {(token.start, token.end): token for token in old.tokens.get(segment, [])}
        for token in tokens:
            was = before.get((token.start, token.end))
            if was is None:
                continue
            went[was.lemma][token.lemma] += 1
            surfaced[token.surface][token.lemma] += 1
            filed[token.surface].add(was.lemma)

    moved = {was: where for was, where in went.items() if set(where) != {was}}
    lemmas = {
        was: where.most_common(1)[0][0]
        for was, where in moved.items()
        if len(where) == 1 and same_word(was, where.most_common(1)[0][0])
    }
    split = {was for was, where in moved.items() if len(where) > 1}
    surfaces = {
        surface: where.most_common(1)[0][0]
        for surface, where in surfaced.items()
        # Only the words the lemma alone cannot place. Everything else would be weight in
        # a file the reader has to carry for nothing.
        #
        # Deliberately not screened by spelling, unlike `lemmas`. The screen asks whether
        # two spellings are the same word, and here they are not supposed to be: the old
        # lemma is a collapsed one — Stanza filed אני, לי and בו all under הוא — so every
        # destination differs from it by more than a derivation does, and `same_word`
        # rejects every one of them. What makes this safe is the surface instead: the mark
        # under הוא was made by marking בו, and בו is what says which card is theirs. A
        # wordpiece is still refused, because that is not a word in any language.
        if filed[surface] & split and "##" not in where.most_common(1)[0][0]
    }
    # Unnamed on purpose: `keep` names the tables once it has composed them with whatever
    # this text had already recorded, and the name has to describe what the reader is
    # actually handed rather than this one step of it.
    return {"lemmas": lemmas, "surfaces": surfaces}
