"""The words to know before a chapter (targum-internal#97).

*The 40 words you will need in Ruth 1*: the Learning Biblical Hebrew Workbook's shape, a
list at the head of a passage of the words in it worth learning first. The card was gated
on readers being seen building it by hand from the export, and there are no readers to be
seen doing anything yet; David decided on 2026-09-28 to build it anyway, **behind a switch
that is off**, so it can be looked at on the box before anybody reads with it.

**Nothing here is new about which words.** A word is on the list by the rule the printed
edition's list keeps (`printed.listed_word`): never a name or a number, only with a meaning
to set beside it, and — because a page on the shared shelf is built once for everybody and
cannot know who will open it — in the looked-up bands. What the page adds is the reader's
own ledger, in the browser: a word they have marked known or put aside is taken off the
list as the page opens (`preread.js`), and the next one comes up in its place, so a
reader who knows half the chapter is shown the half they do not.

**The order is how often a word comes round in the chapter**, the first appearance
breaking a tie: a word met eleven times earns its place before one met once. The count is
the page's own, off the same annotation the reader's words are drawn from, and is not the
occurrence index (`occurrences.py`), which answers the question across a text and a
library rather than inside one page.

**While `TARGUM_PREREAD` is unset, nothing is drawn and nothing is carried**: the reader
is byte for byte what it was. It is decided when the page is written, because a reader is
a file that works off a disk; turning it on reaches a text when its reader is next
written (`targum rebuild`), and turning it off does not take it out of a page already
written with it.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..models import Annotation, Glossary, Translation
from .printed import _glossary, listed_word

#: The switch, off unless the deployment says otherwise.
ENV = "TARGUM_PREREAD"

#: How many the list shows at once: the card's number, and a page of a workbook.
SHOWN = 40

#: How many it carries, so there is a next word to bring up for every one the reader
#: already knows. A chapter of Psalms has fewer hard words than this; a long chapter of
#: prose is cut here rather than made to carry every word it has.
CARRIED = 160


def is_on() -> bool:
    """Whether a reader written now carries the list. Off unless the deployment says so."""
    return os.environ.get(ENV, "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True, slots=True)
class Word:
    """One line of the list: the dictionary form the reader's ledger files it under, the
    form the page shows, its first sense, and how often it comes round here."""

    lemma: str
    form: str
    meaning: str
    count: int


def chapter_words(
    segment_ids: Iterable[str],
    annotation: Annotation | None,
    glossaries: Mapping[str, Glossary] | None,
    translation: Translation,
    translations: list[Translation],
) -> list[Word]:
    """The chapter's words to know first, the commonest first, at most `CARRIED`.

    The meanings are in the language of the rendering the page opens on, found the way
    the printed page finds them. Nothing where the text has no annotation or no meanings:
    a list of words with nothing beside them is a list a reader can do nothing with.
    """
    if annotation is None or not glossaries:
        return []
    glossary = _glossary(glossaries, translation, translations)
    if glossary is None:
        return []
    first: dict[str, tuple[str, str, str]] = {}
    counts: dict[str, int] = {}
    for sid in segment_ids:
        for token in annotation.tokens.get(sid) or ():
            key = token.glossed_as
            if key in first:
                counts[key] += 1
                continue
            word = listed_word(token, glossary, None)
            if word is None:
                continue
            first[key] = (token.lemma, word.form, word.meaning)
            counts[key] = 1
    # Stable, so a tie keeps the order the chapter met the words in.
    ordered = sorted(first, key=lambda key: -counts[key])[:CARRIED]
    return [Word(*first[key], count=counts[key]) for key in ordered]
