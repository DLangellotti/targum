"""A text the reader brought, written again at their level (targum-internal#535).

LingQ calls this Simplify lesson and keeps it for its top tier. targum already writes the
weekly at three levels; this is the same idea turned on a text the reader brought: an
article a step too hard, written again for the vocabulary they have, as a new text of
their own beside the original and linked to it both ways.

**Which level is targum's to say, from what it already knows.** The rung the reader's
marked words reach, or the one they named on arrival until their words have one
(`level.seed`), placed on the weekly's three levels by its CEFR equivalent (`for_rung`).
The weekly's `LEVELS` are what a level means: the vocabulary it is written for and the
sentence length that, measured, is what actually tells the levels apart. A level at or
under the reader's rung is the point: the rewrite should land on Read it now, 90% of its
words known, where the original did not. The reader may pick another on the page.

**It is a paid build, and the reader presses it** (CLAUDE.md, "A chat turn never spends
without a quoted, consented job"). The page says what it uses before anything is asked
of a model, the press goes through `Library.press` and so `Library.claim`, and the one
job carries both halves: the rewriting, then the ordinary build of what came back. A
chat or a connector gets a link to that page and nothing else (`chat.tools.
quote_rewrite`).

**Only a text the reader brought, and never one whose licence forbids it.** A library
text is everybody's, and its owner is the library (`correct.own_folder`). A text the
reader brought carries no licence targum can read, and its rewrite stays as private as
its translation does; where a licence *is* recorded and says NoDerivatives, a rewrite is
exactly what it forbids, and `refused` says so.

This is the public half. The weekly's own writer and voice are private, and nothing here
imports them: the prompt below is written for a reader's text, not for a newspaper.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import TargumError
from .level import Level, Rung, ladder_for, seed
from .models import BlockKind, Document, read_artifact
from .paths import write_atomic
from .usage import Usage
from .weekly.models import LEVELS
from .weekly.models import Level as Written

NAME = "rewrite/1"
MODEL = "claude-sonnet-5"
TIMEOUT = 300.0

#: Beside the rewrite: which text it was written from, and at which level.
FROM = "rewrite.json"
#: Beside the original: every rewrite made of it, newest last.
MADE = "rewrites.json"

#: The longest text rewritten in one press, in words. An article, a chapter, a long talk;
#: a book is read a chapter at a time, and a whole one at once would be a bill and a wait
#: nobody asked for.
LONGEST = 6000

#: Words a request. Small enough that an answer never nears the output limit, large
#: enough that a paragraph is seldom cut from the one it follows.
CHUNK_WORDS = 1200

#: Tokens a word, each way, measured for Hebrew on claude-sonnet-5 by the punctuator
#: (`transcribe/refine/punctuate.py`); a European language runs lower, so this is the
#: high side the estimate wants.
TOKENS_PER_WORD = 4.0

#: A rewrite for a small vocabulary is longer than its original: who everybody is has to
#: be said, and a long sentence becomes two. The weekly's easy edition ran about a third
#: longer than its native one. Applied to what the build of the rewrite is reserved at.
LONGER = 1.4

#: The instruction the prompt carries before the text, besides what `ask` fills in.
ASK = """Rewrite the {language} text below for somebody learning {language} who knows \
about the {words:,} commonest words of the language. It is for them to read, so it must \
stay {language}: never translate it.

- Keep what it says: the same facts, names, numbers and order. Leave out only detail a \
learner can do without; add nothing that is not in the text.
- Use common words. Where a rare word matters, say it with commoner ones.
- Write sentences of about {short} to {long} words, one thought each.
- Keep the paragraphs, with a blank line between them.{extra}

Answer with the rewritten title on the first line, a blank line, and then the rewritten \
text. Nothing else: no notes, no headings of your own, no quotation marks around it.

<title>{title}</title>
<text>
{text}
</text>"""

#: The same, for every part after the first: there is no title to give back.
ASK_MORE = """Go on rewriting the same {language} text, in the same way, for the same \
learner: about the {words:,} commonest words, sentences of {short} to {long} words, the \
paragraphs kept with a blank line between them.{extra} Answer with the rewritten text and \
nothing else.

<text>
{text}
</text>"""

#: What a language's own writing asks for besides.
EXTRA: dict[str, str] = {
    # The pipeline points it afterwards (`vocalize`), the way it points every modern text,
    # and a model's nikkud is the thing it gets wrong most.
    "he": "\n- Write ordinary modern Hebrew without niqqud.",
    # Stress marks are the reader's, added by the pipeline where it adds them.
    "ru": "\n- Write ordinary Russian, without stress marks.",
}

#: One request: the prompt in, the answer and its input and output tokens out.
Ask = Callable[[str], tuple[str, int, int]]


# -- the level --------------------------------------------------------------------------

#: The levels a text is rewritten at: the weekly's first two. Its third is "Native",
#: not simplified at all, which is what the reader brought.
OFFERED: tuple[Written, ...] = (Written.aleph, Written.bet)

#: The level for a rung, by the rung's CEFR equivalent. At or under the reader, never
#: over: bet (A2, 1,800 words) reads Easy (1,000) rather than Simplified (3,000), because
#: a text written past them is the one they brought. From B1 up it is Simplified.
BY_CEFR: dict[str, Written] = {"A1": Written.aleph, "A2": Written.aleph}


def for_rung(rung: Rung | None) -> Written:
    """The level to write at for a reader on `rung`: Easy where nothing is known yet."""
    if rung is None:
        return Written.aleph
    # An ulpan rung names its CEFR equivalent; a CEFR rung is one, by name.
    return BY_CEFR.get(rung.cefr or rung.name, Written.bet)


def for_reader(level: Level) -> Written:
    """The level for this reader's ledger: the rung their words reach, else the one they
    named on arrival (`level.seed`, Hebrew only), else Easy."""
    return for_rung(level.here or seed(level))


def named(value: str) -> Written | None:
    """A level the page asked for by its id, or None for anything else."""
    try:
        written = Written(value)
    except ValueError:
        return None
    return written if written in OFFERED else None


def rewrites(language: str) -> bool:
    """Whether targum rewrites texts in this language: the ones a ladder measures, since a
    level is a place on one."""
    return ladder_for(language) is not None


# -- whose, and what licence ------------------------------------------------------------


def licence_of(folder: Path) -> str:
    """The licence a text's source is held under, where targum has one written down, or "".

    The one the shelf reads (`promote.licence_of`): a recording's rides in its manifest.
    Then the catalogue, of the source and of where a recording came from. A page from the
    web carries its rights in words nobody parses, so an article has none.
    """
    from . import catalogue as catalogue_module
    from . import promote as promote_module
    from .audio import manifest as manifest_module

    document = read_artifact(Document, folder / "document.json")
    if document is None:
        return ""
    recorded = promote_module.licence_of(folder, document.source)
    if recorded:
        return recorded
    kept = manifest_module.load(folder)
    for address in (document.source, kept.home if kept is not None else ""):
        entry = catalogue_module.matching(address) if address else None
        if entry is not None and entry.licence:
            return entry.licence
    return ""


def refused(licence: str) -> str:
    """Why a text under `licence` may not be rewritten, or "". Only NoDerivatives refuses:
    an unknown licence is a reader's own text, rewritten for them alone like its
    translation."""
    from .licensing import verdict

    if licence and not verdict(licence).derivatives:
        return "This text's licence doesn't allow changing it, so we can't rewrite it."
    return ""


# -- the text ---------------------------------------------------------------------------


def text_of(document: Document) -> tuple[str, list[str]]:
    """A document's title and its paragraphs, as a reader would copy them out. A heading
    that only repeats the title is left out, since the title is asked for on its own."""
    title = (document.title or "").strip()
    paragraphs: list[str] = []
    for block in document.blocks:
        said = block.text.strip()
        if not said:
            continue
        if block.kind == BlockKind.heading and said == title:
            continue
        paragraphs.append(said)
    return title, paragraphs


_WORD = re.compile(r"\w+", re.UNICODE)


def words(text: str) -> int:
    return len(_WORD.findall(text))


def chunks(paragraphs: list[str], most: int = CHUNK_WORDS) -> list[str]:
    """The paragraphs, gathered into requests of up to `most` words. A paragraph longer
    than that is a request of its own rather than one cut in half."""
    out: list[list[str]] = []
    count = 0
    for paragraph in paragraphs:
        size = words(paragraph)
        if out and count + size <= most:
            out[-1].append(paragraph)
            count += size
        else:
            out.append([paragraph])
            count = size
    return ["\n\n".join(group) for group in out]


def prompt(language: str, written: Written, text: str, *, title: str | None = None) -> str:
    """The request for one chunk: the first carries the title, the rest go on from it."""
    from .translate.prompts import language_name

    spec = LEVELS[written]
    short, long = spec.sentence
    fields: dict[str, Any] = {
        "language": language_name(language),
        "words": spec.written_for,
        "short": round(short),
        "long": round(long),
        "extra": EXTRA.get(language.split("-")[0].lower(), ""),
        "text": text,
    }
    if title is None:
        return ASK_MORE.format(**fields)
    return ASK.format(title=title or "(none)", **fields)


@dataclass
class Rewritten:
    title: str
    paragraphs: list[str]
    spent: Usage

    def file(self, language: str) -> str:
        """As a .txt the plain-text ingester reads: front matter naming the title and the
        language, then the paragraphs."""
        safe = self.title.replace("\n", " ").strip()
        head = f"---\ntitle: {json.dumps(safe, ensure_ascii=False)}\nlanguage: {language}\n---\n\n"
        return head + "\n\n".join(self.paragraphs) + "\n"


class Rewriter:
    name = NAME

    def __init__(self, model: str | None = None, ask: Ask | None = None) -> None:
        self.model = model or MODEL
        self._ask = ask

    def available(self) -> tuple[bool, str]:
        if self._ask is not None:
            return True, self.model
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return True, self.model
        return False, "set ANTHROPIC_API_KEY in .env"

    def estimate(self, count: int) -> float:
        """Dollars to rewrite `count` words, on the high side: the instruction each
        request carries, the words in, and a longer text out."""
        from .translate.anthropic_provider import DEFAULT_MODEL, PRICES

        in_price, out_price = PRICES.get(self.model, PRICES[DEFAULT_MODEL])
        requests = max(1, -(-count // CHUNK_WORDS))
        tokens_in = requests * 400 + count * TOKENS_PER_WORD
        tokens_out = count * TOKENS_PER_WORD * LONGER
        return (tokens_in * in_price + tokens_out * out_price) / 1_000_000

    def rewrite(self, document: Document, written: Written) -> Rewritten:
        """The document, written again at `written`. Raises where an answer is empty: a
        rewrite with a hole in it is not one to build and charge for."""
        title, paragraphs = text_of(document)
        spent = Usage()
        out_title = title
        out: list[str] = []
        for number, chunk in enumerate(chunks(paragraphs)):
            first = number == 0
            asked = prompt(document.language, written, chunk, title=title if first else None)
            answer, used_in, used_out = (self._ask or self._request)(asked)
            spent.add(self.model, used_in, used_out)
            pieces = [piece.strip() for piece in answer.strip().split("\n\n") if piece.strip()]
            if first and pieces:
                head, _, rest = pieces[0].partition("\n")
                out_title = _plain(head) or title
                pieces = ([rest.strip()] if rest.strip() else []) + pieces[1:]
            if not pieces:
                raise TargumError(
                    "We couldn't rewrite this text. Nothing was added to your texts.",
                    key="rewrite.empty",
                )
            out.extend(pieces)
        return Rewritten(out_title, out, spent)

    def _request(self, asked: str) -> tuple[str, int, int]:
        import anthropic

        client = anthropic.Anthropic(timeout=TIMEOUT)
        answer = client.messages.create(
            model=self.model,
            max_tokens=12000,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": asked}],
        )
        said = "".join(str(getattr(block, "text", "")) for block in answer.content)
        return said, answer.usage.input_tokens, answer.usage.output_tokens


def _plain(line: str) -> str:
    """A title line as a model might dress it: without a heading's hashes, a label or
    quotation marks."""
    line = line.strip().lstrip("#").strip()
    line = re.sub(r"^(title|כותרת|заголовок|titre|titolo)\s*:\s*", "", line, flags=re.I)
    return line.strip("\"'«»“”„ ").strip()


# -- the links, both ways ---------------------------------------------------------------


def link(rewrite: Path, original: Path, written: Written) -> None:
    """Write down that `rewrite` was made from `original` at `written`, beside each."""
    write_atomic(
        rewrite / FROM,
        json.dumps({"from": original.name, "level": written.value}, ensure_ascii=False),
    )
    made = [one for one in made_of(original) if one.get("name") != rewrite.name]
    made.append({"name": rewrite.name, "level": written.value})
    write_atomic(original / MADE, json.dumps(made, ensure_ascii=False))


def made_from(folder: Path) -> dict[str, str] | None:
    """What this text was rewritten from, or None for a text that is no rewrite."""
    try:
        found = json.loads((folder / FROM).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(found, dict) or not found.get("from"):
        return None
    return {"name": str(found["from"]), "level": str(found.get("level") or "")}


def made_of(folder: Path) -> list[dict[str, str]]:
    """Every rewrite of this text, oldest first."""
    try:
        found = json.loads((folder / MADE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(found, list):
        return []
    return [
        {"name": str(one["name"]), "level": str(one.get("level") or "")}
        for one in found
        if isinstance(one, dict) and one.get("name")
    ]


def stem(original: Path, written: Written) -> str:
    """The new text's file name, and so its folder's: the original's, and the level. A
    second rewrite at the same level is numbered rather than written over the first."""
    base = f"{original.name}-{written.value}"
    name, number = base, 2
    while (original.parent / name).exists():
        name, number = f"{base}-{number}", number + 1
    return name


#: The rung named for a level on the page: the weekly's own words, "Easy · 1,000 words".
def label(written: Written, language: str = "en") -> str:
    from .weekly.models import label_in

    return label_in(written, language)
