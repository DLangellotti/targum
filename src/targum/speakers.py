"""Who says each line, and whether a model knows well enough to voice it (targum-internal#77).

The card's rule is that a line switches from the narrator to a dialogue voice only above
a confidence threshold, because a wrong voice is worse than one voice. Before anything is
voiced that threshold has to be a number, and a number needs gold. Plays are gold for
free: every turn is labelled with its speaker. So a play is parsed into its lines and
who said them, the names are taken off, the text is shown to a model as dialogue among
the stage directions that were there, and the model is asked who says each line and how
sure it is. What comes back is scored as a precision–coverage curve over the confidence.

**A play is the easy case.** Its turns are explicit and they alternate: every numbered
line is somebody's speech, nothing is narration, and in a two-hander the answer is the
speaker two lines back. Prose has none of that. What is measured here is an upper bound
for prose, not an estimate of it, and `alternation` is printed beside it to say how much
of the number the form gives away.

Nothing here is voiced and nothing reaches the reader. The model call is the only part
that spends, and every answer is cached on disk by the exact request, so a rerun costs
nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .usage import Usage
from .vocalize.base import is_mark

#: The tier the card prices attribution at: it rides on the translation pass, and the
#: hosted build's model is Sonnet.
MODEL = "claude-sonnet-5"

#: What a line comes back as when the model will not name anybody. Never a voice.
UNKNOWN = "?"

#: A line of scene heading: an act, a scene, a picture. It ends whatever turn was open.
_HEADING = re.compile(r"^(מחזה|תמונה|מערכה)\s")

#: A line that is nothing but a rule or an ornament: `* * *`, `־־־־`, `_____`.
_RULE = re.compile(r"^[\s*_\-־–—.]*$")


@dataclass(frozen=True)
class Line:
    """One paragraph of a play: a turn of speech, or a stage direction.

    `speaker` is the gold — the name the play gave, mapped onto the cast — and None for a
    stage direction. `id` is set only on speech, because only speech is asked about.
    """

    text: str
    speaker: str | None = None
    id: str = ""


def _bare(line: str) -> tuple[str, list[int]]:
    """The line without its points, and where each bare character sits in the original."""
    bare: list[str] = []
    where: list[int] = []
    for index, char in enumerate(line):
        if not is_mark(char, bare[-1] if bare else ""):
            bare.append(char)
            where.append(index)
    where.append(len(line))
    return "".join(bare), where


def _label(cast: Mapping[str, str]) -> re.Pattern[str]:
    """A speaker's name at the head of a line, as plays print it.

    `לוקא: …`, `אמא. …`, `תמר (מתאדמת קצת). …`, `יוסף ( מתעורר ): …`, and with an
    aside the stop may be left out: `יוסף (נכנס בחפזון) הֶהָיוּ …`. Longest names
    first, so `הדודה הראשונה` is not read as a shorter name that happens to begin it.
    Matched on the bare letters, so a pointed name and an unpointed one are one name.
    """
    names = "|".join(re.escape(name) for name in sorted(cast, key=len, reverse=True))
    return re.compile(rf"^\s*(?P<name>{names})\s*(?P<aside>\([^)]*\))?\s*(?:[:.]|(?<=\)))\s*")


def _midline(cast: Mapping[str, str]) -> re.Pattern[str]:
    """A second turn run on in the same line of the file, after the first one ends.

    `…לא. ילד א: למה הנה באת` and `(יוצאות.) האלמנה (מופיעה על הסף): רימיתי`. Only after
    a stop or a closing parenthesis and only with a colon, so `כה אמר מרדכי:` inside a
    speech is still speech.
    """
    names = "|".join(re.escape(name) for name in sorted(cast, key=len, reverse=True))
    return re.compile(rf"(?<=[.!?…)])\s+(?=(?:{names})\s*(?:\([^)]*\))?\s*:)")


#: How many rows an open parenthesis may run over before it is taken for a stray.
_WRAP = 6


def _unwrap(rows: list[str]) -> list[str]:
    """Rows joined wherever a parenthesis opened on one and closed on a later one.

    The files wrap at a width, so `האלמנה (מופיעה על הסף … מסתכלת` / `מסביב): רימיתי`
    is one label split over two rows, and the label is only read once they are one. An
    open parenthesis that has not closed within `_WRAP` rows is left as it was.
    """
    out: list[str] = []
    index = 0
    while index < len(rows):
        row = rows[index].strip()
        end = index
        while _depth(row) > 0 and end + 1 < len(rows) and end - index < _WRAP:
            end += 1
            row = f"{row} {rows[end].strip()}"
        if _depth(row) > 0:
            row, end = rows[index].strip(), index
        out.append(row)
        index = end + 1
    return out


def _split(row: str, midline: re.Pattern[str]) -> list[str]:
    """The row cut where another speaker's label begins inside it."""
    bare, where = _bare(row)
    cuts = [where[found.end()] for found in midline.finditer(bare)]
    if not cuts:
        return [row]
    edges = [0, *cuts, len(row)]
    return [row[a:b].strip() for a, b in zip(edges, edges[1:], strict=False) if row[a:b].strip()]


def _depth(text: str) -> int:
    return text.count("(") - text.count(")")


def _spoken(text: str) -> str:
    """What is left of a turn once its asides are taken out."""
    return re.sub(r"[\s.:;,…–—\-!?]+", "", re.sub(r"\([^)]*\)", "", text))


def parse_play(
    text: str, cast: Mapping[str, str], *, opening: str = "", prefix: str = "l"
) -> list[Line]:
    """A play's text as its lines, each turn with the speaker the play gave it.

    `cast` maps every name the play prints onto the one the gold uses, so `בני-ישראל`
    and `בני ישראל` are one speaker. Everything before the first line containing
    `opening` is skipped — the title and the list of characters, which would otherwise
    read as turns. A turn is a labelled line and the unlabelled lines that follow it,
    which is how the files wrap. A line that is a stage direction on its own is kept as
    one; a labelled line with nothing spoken in it (`האלמנה (יושבת על שרפרף).`) is a stage
    direction too, and keeps its name, because that is what the page says.
    """
    label = _label(cast)
    midline = _midline(cast)
    raw = text.replace("\r", "").split("\n")
    if opening:
        want = _bare(opening)[0]
        start = next((i for i, row in enumerate(raw) if want in _bare(row)[0]), None)
        if start is None:
            raise ValueError(f"opening {opening!r} is not in the text")
        raw = raw[start:]
    raw = [piece for row in _unwrap(raw) for piece in _split(row, midline)]

    # Paragraphs, before they are told apart: (speaker or None, text).
    paragraphs: list[tuple[str | None, str]] = []
    speaker: str | None = None
    open_turn = False
    pending = ""  # a stage direction whose parenthesis has not closed yet
    for row in raw:
        row = row.strip()
        if pending:
            pending = f"{pending} {row}".strip()
            if _depth(pending) <= 0:
                paragraphs.append((None, pending))
                pending = ""
            continue
        if not row:
            continue
        if _HEADING.match(row) or _RULE.match(row):
            speaker, open_turn = None, False
            continue
        bare, where = _bare(row)
        found = label.match(bare)
        if found:
            speaker = cast[found.group("name")]
            aside = ""
            if found.group("aside"):
                aside = row[where[found.start("aside")] : where[found.end("aside")]]
            body = row[where[found.end()] :].strip()
            # `הלנה: (בהחלטה): הריני` — an aside after the colon, with a colon of its own.
            body = re.sub(r"^(\([^)]*\))\s*[:.]\s*", r"\1 ", body)
            paragraphs.append((speaker, f"{aside} {body}".strip()))
            open_turn = True
            continue
        if row.startswith("("):
            if _depth(row) > 0:
                pending = row
                continue
            if not _spoken(row):
                paragraphs.append((None, row))
                open_turn = False
                continue
        if speaker is None:
            paragraphs.append((None, row))
        elif open_turn:
            said, before = paragraphs[-1]
            paragraphs[-1] = (said, f"{before} {row}".strip())
        else:
            # Speech again after a direction on its own line, and no new name: the same
            # speaker going on.
            paragraphs.append((speaker, row))
            open_turn = True
    if pending:
        paragraphs.append((None, pending))

    lines: list[Line] = []
    count = 0
    for said, body in paragraphs:
        if said is not None and _spoken(body):
            lines.append(Line(text=body, speaker=said, id=f"{prefix}{count:04d}"))
            count += 1
        elif said is not None:
            name = next(name for name, who in cast.items() if who == said)
            lines.append(Line(text=f"{name} {body}".strip()))
        else:
            lines.append(Line(text=body))
    return lines


def speakers(cast: Mapping[str, str]) -> list[str]:
    """The cast as the gold names it, in the order the play first gave them."""
    return list(dict.fromkeys(cast.values()))


def present(lines: Sequence[Line], *, ids: bool = True) -> str:
    """The lines as dialogue in prose: speech on a dash, directions as they were.

    Hebrew prose sets a line of dialogue as a paragraph opening with a dash, so that is
    how speech is shown. The speaker's name is gone; an aside that sat beside the name
    (`(מתאדמת קצת)`) stays with the line, because a stage direction is exactly the kind
    of cue prose gives — "she said, blushing" — and taking it out would make the play
    harder than a novel rather than easier.
    """
    out = []
    for line in lines:
        if line.speaker is None:
            out.append(line.text)
        elif ids:
            out.append(f"[{line.id}] – {line.text}")
        else:
            out.append(f"– {line.text}")
    return "\n".join(out)


def windows(
    lines: Sequence[Line], size: int, *, before: int = 6, after: int = 4
) -> Iterator[tuple[list[Line], list[Line], list[Line]]]:
    """Batches of at most `size` spoken lines, each with the paragraphs either side.

    The shape the translation pass already has — a batch and the text around it — since
    that is where attribution would ride. The context is shown without ids or names: the
    model is not told who said the lines it is not asked about.
    """
    spoken = [index for index, line in enumerate(lines) if line.speaker is not None]
    for start in range(0, len(spoken), size):
        chunk = spoken[start : start + size]
        first, last = chunk[0], chunk[-1]
        yield (
            list(lines[max(0, first - before) : first]),
            list(lines[first : last + 1]),
            list(lines[last + 1 : last + 1 + after]),
        )


SYSTEM = """You attribute lines of dialogue in Hebrew fiction to the characters who speak them.

You are given the cast, and a passage of the text: numbered lines of dialogue, each
opening with a dash, among unnumbered narration and stage directions. For every
numbered line, name the character who says it, choosing only from the cast, and give
your confidence that the attribution is right as a probability between 0 and 1.

Be calibrated: 0.9 should mean you are wrong about one time in ten. Use Hebrew grammar
(the gender and number of verbs and pronouns), who is addressed by name, who was just
spoken to, and the stage directions. If you cannot tell at all, answer "?" with a low
confidence. Answer every numbered line exactly once, by its id."""


class Attribution(BaseModel):
    id: str
    speaker: str
    confidence: float


class Attributions(BaseModel):
    lines: list[Attribution]


def message(
    cast: Sequence[str], before: Sequence[Line], batch: Sequence[Line], after: Sequence[Line]
) -> str:
    parts = ["Cast: " + ", ".join(cast)]
    if before:
        parts.append("Text before (context only):\n" + present(before, ids=False))
    parts.append("Lines to attribute:\n" + present(batch))
    if after:
        parts.append("Text after (context only):\n" + present(after, ids=False))
    return "\n\n".join(parts)


def _key(model: str, effort: str, system: str, user: str) -> str:
    return hashlib.sha256(json.dumps([model, effort, system, user]).encode()).hexdigest()[:24]


def ask(
    client: Any,
    cast: Sequence[str],
    before: Sequence[Line],
    batch: Sequence[Line],
    after: Sequence[Line],
    *,
    model: str = MODEL,
    effort: str = "medium",
    usage: Usage | None = None,
    cache: Path | None = None,
) -> dict[str, tuple[str, float]]:
    """One batch's attributions, from the cache if this exact request was made before.

    Kept by the request rather than by the play, so a changed prompt, window or model is
    a new question and never reads an old answer. A name outside the cast comes back as
    `UNKNOWN` with no confidence: a voice is only ever one the map has.
    """
    from .translate.anthropic_provider import output_config

    user = message(cast, before, batch, after)
    path = cache / f"{_key(model, effort, SYSTEM, user)}.json" if cache else None
    if path is not None and path.exists():
        answer = json.loads(path.read_text(encoding="utf-8"))
    else:
        response = client.messages.parse(
            model=model,
            max_tokens=16000,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_format=Attributions,
            **output_config(model, effort),
        )
        spent = getattr(response, "usage", None)
        tokens = (
            int(getattr(spent, "input_tokens", 0) or 0),
            int(getattr(spent, "output_tokens", 0) or 0),
        )
        if usage is not None:
            usage.add(model, *tokens)
        parsed = response.parsed_output
        if not isinstance(parsed, Attributions):
            raise ValueError("the model returned no structured output for a batch")
        answer = {
            "lines": [line.model_dump() for line in parsed.lines],
            "tokens": list(tokens),
        }
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
    wanted = {line.id for line in batch}
    out: dict[str, tuple[str, float]] = {}
    for row in answer["lines"]:
        if row["id"] not in wanted:
            continue
        name = str(row["speaker"]).strip()
        if name not in cast:
            out[row["id"]] = (UNKNOWN, 0.0)
        else:
            out[row["id"]] = (name, min(1.0, max(0.0, float(row["confidence"]))))
    return out


def alternation(lines: Sequence[Line]) -> dict[str, str]:
    """The baseline a play hands over: each line said by whoever spoke two turns back.

    Stage directions are skipped, so it is two *turns* back. The first two lines have no
    such speaker and are left out, which counts them as wrong.
    """
    spoken = [line for line in lines if line.speaker is not None]
    return {
        line.id: str(spoken[index - 2].speaker) for index, line in enumerate(spoken) if index >= 2
    }


@dataclass(frozen=True)
class Point:
    """What one threshold gives: how many lines switch voice, and how many of them rightly."""

    threshold: float
    switched: int
    correct: int
    total: int

    @property
    def coverage(self) -> float:
        return self.switched / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        return self.correct / self.switched if self.switched else 1.0


THRESHOLDS = (0.0, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97, 0.99, 1.0)


def curve(
    gold: Mapping[str, str],
    guessed: Mapping[str, tuple[str, float]],
    thresholds: Sequence[float] = THRESHOLDS,
) -> list[Point]:
    """Precision and coverage at each threshold, over every gold line.

    A line switches voice when its confidence is at or above the threshold and it named
    somebody; otherwise it stays with the narrator. A line with no answer never switches.
    Coverage is over all the gold lines, so a batch that failed counts against it.
    """
    points = []
    for threshold in thresholds:
        switched = correct = 0
        for line_id, speaker in gold.items():
            name, confidence = guessed.get(line_id, (UNKNOWN, 0.0))
            if name == UNKNOWN or confidence < threshold:
                continue
            switched += 1
            correct += name == speaker
        points.append(Point(threshold, switched, correct, len(gold)))
    return points


def accuracy(gold: Mapping[str, str], guessed: Mapping[str, str]) -> float:
    """The share of gold lines named rightly, a missing answer counting as wrong."""
    if not gold:
        return 0.0
    return sum(guessed.get(line_id) == speaker for line_id, speaker in gold.items()) / len(gold)


def lowest(points: Sequence[Point], precision: float) -> Point | None:
    """The lowest threshold whose switched lines are right at least `precision` of the time.

    Each point already counts every line at or above its threshold, so its precision is
    the precision of the voice the reader would hear at that setting. A higher threshold
    can dip below the bar on a handful of lines — five lines at 0.97, one of them wrong —
    and that does not make the lower setting wrong; it is the lower setting's lines that
    are heard.
    """
    for point in sorted(points, key=lambda point: point.threshold):
        if point.switched and point.precision >= precision:
            return point
    return None
