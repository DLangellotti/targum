"""An outside corpus counted into the language tables (targum-internal#580, #581): the
conversation and classic-literature registers' backfills.

The text is on the laptop only while it is counted. This reads it a chunk of sentences
at a time, annotates each chunk with the annotator a build uses for Hebrew (DICTA, read
through `annotate.Annotator`, so a lemma here is the lemma a reader's word is filed
under), folds the tokens with the same rule as a built text (`words.count`,
`roots.count`), and writes counts with the corpus's provenance. No sentence is kept: a
contribution's unit is a hash of its chunk, and a tally holds lemmas and counts.

A chunk is the checkpoint. Its contributions are written when it is done, and a chunk
already counted under the same annotator is passed over, so a run that stops — a crash,
a full disk, a sample cut short — picks up where it stopped when started again on the
same file. Phrases are written pre-pruned, as the spec has external corpora: a run of
lemmas seen fewer than `PHRASE_FLOOR` times in a chunk is not kept.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from . import roots
from .registers import BIBLE, CONVERSATION, LITERATURE
from .store import Contribution, Store
from .words import PHRASES, RULE, WORDS, count

#: Sentences to a chunk: a checkpoint about every twenty minutes through DICTA on the
#: laptop, and the unit the phrase floor is applied in.
CHUNK = 10_000

#: A phrase seen fewer times than this in a chunk is not written.
PHRASE_FLOOR = 3

#: The registers an outside corpus may be filed under: the yardsticks a backfill feeds.
#: News is counted from the feeds by its own job, never from a downloaded corpus.
REGISTERS = (CONVERSATION, LITERATURE, BIBLE)

#: The longest line handed over, in characters; a longer one is cut at spaces. A line
#: past this is a paragraph nobody split, and the model's batch is sized by its longest.
LINE_CHARS = 600


@dataclass
class CorpusResult:
    """What one run did, chunk by chunk."""

    #: Chunks annotated and written now.
    counted: int = 0
    #: Chunks already counted under this annotator: what makes a restart cheap.
    held: int = 0
    sentences: int = 0
    #: Words counted, by the words table, over every chunk this run wrote or held.
    tokens: int = 0
    lemmas: set[str] = field(default_factory=set)
    #: Why the run stopped before the end of the file, or "".
    stopped: str = ""


def lines_of(raw: Iterable[str]) -> Iterator[str]:
    """Each non-empty line, stripped, with a long one cut at spaces into pieces."""
    for line in raw:
        text = " ".join(line.split())
        while len(text) > LINE_CHARS:
            cut = text.rfind(" ", 0, LINE_CHARS)
            cut = cut if cut > 0 else LINE_CHARS
            yield text[:cut]
            text = text[cut:].lstrip()
        if text:
            yield text


def chunks(raw: Iterable[str], size: int = CHUNK) -> Iterator[list[str]]:
    """The corpus in runs of `size` lines, the last one short."""
    held: list[str] = []
    for line in lines_of(raw):
        held.append(line)
        if len(held) == size:
            yield held
            held = []
    if held:
        yield held


def unit_of(source: str, chunk: list[str]) -> str:
    """A chunk's unit: the corpus and a hash of its lines, so the same chunk read again
    is the same unit, and no sentence is in the row."""
    digest = hashlib.sha256("\n".join(chunk).encode("utf-8")).hexdigest()[:32]
    return f"{source}:{digest}"


def _rule(table: str) -> str:
    if table == roots.ROOTS:
        return roots.rule()
    if table == PHRASES:
        return f"{RULE}+floor{PHRASE_FLOOR}"
    return RULE


TABLES = (WORDS, PHRASES, roots.ROOTS)


def contributions(
    unit: str, *, register: str, source: str, licence: str, tool: str
) -> dict[str, Contribution]:
    """What one chunk is filed as, table by table."""
    return {
        table: Contribution(
            table=table,
            register=register,
            unit=unit,
            source=source,
            licence=licence,
            tool=tool,
            rule=_rule(table),
        )
        for table in TABLES
    }


def default_annotator() -> Any:
    """The annotator a build reads modern Hebrew with, less the pronouncer, which adds
    readings and no lemma. Built lazily: nothing is loaded until a chunk is read."""
    from ..annotate import Annotator
    from ..annotate.lemma import for_source

    return Annotator(lemmatizer=for_source("corpus:he", language="he"))


def tally(chunk: list[str], annotator: Any, unit: str) -> dict[str, Counter[tuple[str, str]]]:
    """One chunk's counts, table by table. The sentences live only inside this call."""
    from ..models import Segment, SegmentedDocument

    document = SegmentedDocument(
        document_hash=unit.rsplit(":", 1)[-1],
        language="he",
        segmenter="corpus",
        segments=[
            Segment(id=f"s{at}", block_id=f"b{at}", block_index=at, index=0, text=line)
            for at, line in enumerate(chunk)
        ],
    )
    annotation = annotator.annotate(document)
    tokens = {
        segment: [token.model_dump() for token in run] for segment, run in annotation.tokens.items()
    }
    counted = count(tokens)
    phrases = Counter({key: n for key, n in counted[PHRASES].items() if n >= PHRASE_FLOOR})
    return {WORDS: counted[WORDS], PHRASES: phrases, roots.ROOTS: roots.count(tokens, "he")}


def count_corpus(
    raw: Iterable[str],
    store: Store,
    *,
    register: str,
    source: str,
    licence: str,
    annotator: Any = None,
    size: int = CHUNK,
    tokens: int | None = None,
    stop: Callable[[], str] | None = None,
    say: Callable[[str], None] | None = None,
) -> CorpusResult:
    """Count a corpus, one line a sentence, into `register`. Returns what was done.

    `tokens` ends the run once that many words are counted, whole chunks only, so a
    sample can be grown later by running again with a larger figure. `stop` is asked
    before each chunk is annotated and ends the run when it returns a reason.
    """
    if register not in REGISTERS:
        raise ValueError(f"an outside corpus is filed under {REGISTERS}, not {register}")
    if not source or not licence:
        raise ValueError("every contribution names its source and its licence")
    annotator = annotator if annotator is not None else default_annotator()
    tool = str(annotator.name)
    result = CorpusResult()
    for at, chunk in enumerate(chunks(raw, size)):
        if tokens is not None and result.tokens >= tokens:
            result.stopped = f"the sample reached {result.tokens} words"
            break
        unit = unit_of(source, chunk)
        filed = contributions(unit, register=register, source=source, licence=licence, tool=tool)
        if all(store.is_current(one.id) for one in filed.values()):
            result.held += 1
            result.sentences += len(chunk)
            words = store.counted(filed[WORDS].id)
            result.tokens += sum(words.values())
            result.lemmas.update(words)
            continue
        reason = stop() if stop is not None else ""
        if reason:
            result.stopped = reason
            break
        counted = tally(chunk, annotator, unit)
        for table, one in filed.items():
            store.write(one, counted[table])
        result.counted += 1
        result.sentences += len(chunk)
        result.tokens += sum(counted[WORDS].values())
        result.lemmas.update(key for key, _ in counted[WORDS])
        if say is not None:
            say(
                f"chunk {at + 1}: {len(chunk)} lines, {sum(counted[WORDS].values())} words;"
                f" {result.tokens} so far"
            )
    return result
