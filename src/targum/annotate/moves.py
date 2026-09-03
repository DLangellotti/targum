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
from collections import Counter, defaultdict

from ..models import Annotation

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
    return {
        # Named so a reader applies one text's moves once, and so a rebuilt text with
        # different moves is applied again rather than skipped.
        "id": hashlib.sha256(
            f"{old.annotator}|{new.annotator}|{new.document_hash}".encode()
        ).hexdigest()[:12],
        "lemmas": lemmas,
        "surfaces": surfaces,
    }
