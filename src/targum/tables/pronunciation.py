"""Table 3, `pronunciation`: how a pointed word is said, kept so a word fixed once is said
right in every later line (targum-internal#584; spec §3).

Gemini ignores nikkud, so the speech engine reads Hebrew from context and is sometimes
wrong, and the only lever is an instruction in the prompt
(`dialogue.checks.pronunciation_hints`). Until now an instruction given by hand
(`voice_shelf.py --hint`) reached one turn and was forgotten: the same word in the next
scene was said wrong again. This builds a dictionary, pointed form → what to say about
it, that the hint builder reads beside the gender hints it works out itself.

**Two inputs, one dictionary.**

- **Corrected.** Every `correction` row (#585) of stage `voice`, `asr`, `human` or
  `author` and kind `stress`, `nikkud` or `pronunciation`, that is *settled*: by the
  author's or an editor's own hand, or accepted by a person. An ASR flag is written
  `proposed` and stays out until a human ear settles it (spec, Q5) — an ASR row counts
  only once it is `accepted`, whoever wrote it. A refused row never counts.
- **Observed.** The stress and qamats qatan the pronouncer (`annotate/pronounce.py`)
  gave a pointed form, tallied under the `pronunciation` table of the language tables
  with `variant = observed_variant(stress, qatan)`. **The fold that writes these rows is
  not built yet**; until it is, this table is empty and the dictionary is corrections
  only. An observation is used only past `FLOOR_SEEN` occurrences agreeing at
  `FLOOR_SHARE` (David, 2026-11-08, on targum#1133: ten occurrences, 95% agreeing;
  the spec said only "a floor of agreement"), and it is said only where the spelling
  is genuinely ambiguous: when another pointed form of the same letters is observed,
  past the same floor, with a different stress. That is the rule the gender hints
  already keep: only what the letters leave open gets a hint.

**A correction outranks an observation**: where both speak of one form, the correction
is what is said, and the observation is kept only as evidence.

**Where a correction lands.** A voice hint's row is the whole line before and the
instruction after (`Read עוֹשָׂה as "osa", the feminine`). The form is the word of the
line whose letters the instruction names; an instruction that names no Hebrew word is
placed on the line's only word, and one that cannot be placed is counted and left out,
never guessed.

`pronunciation.json` is written to the tables directory (`yardstick.directory()`:
`/var/lib/targum/tables` on the box, `~/.targum/tables` elsewhere), never the repo. It
holds pointed forms and instructions, never a line, a scene or a reader.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..accounts import Store as AccountStore
    from .store import Store as TablesStore

PRONUNCIATION = "pronunciation"
FILE = "pronunciation.json"

#: The version of the building rule below. A change to what is kept is a new number.
RULE = "pronunciation/1"

#: The stages whose fixes are about how a word is said.
STAGES = ("voice", "asr", "human", "author")

#: The kinds of fix that speak to pronunciation. `pronunciation` is not one of
#: `fixes.KINDS` (a row filed so is kept as `other`); it is here so a row filed under it
#: by hand, outside `record`, is still read.
KINDS = ("stress", "nikkud", "pronunciation")

#: The hands whose own fix is settled without anybody accepting it (`fixes.GOLD_HANDS`).
SETTLED_HANDS = ("author", "editor")

#: An observation is used only once a form was seen this often…
FLOOR_SEEN = 10
#: …and this share of those occurrences agree on its stress and qamats.
FLOOR_SHARE = 0.95

#: The imperative an instruction opens with, dropped where it is said in a list that
#: already opens "Read …" (`voice_scenes.GUIDE`).
_OPENING = re.compile(r"^\s*(?:read|say|pronounce)\s+", re.IGNORECASE)

_ORDINAL = {1: "last", 2: "second-to-last", 3: "third-to-last"}


@dataclass(frozen=True)
class Entry:
    """What is known about how one pointed form is said."""

    #: Syllables from the end the stress falls on (1 the last), where known.
    stress: int | None = None
    #: Whether its qamats is a qamats qatan, said "o", where known.
    qatan: bool | None = None
    #: The instruction the hint builder says, word included; empty says nothing.
    say: str = ""
    #: How many places (corrections) or occurrences (observations) stand behind it.
    evidence: int = 0
    #: "correction" or "observed".
    source: str = ""


def form(word: str) -> str:
    """A pointed word as the dictionary keys it: NFC, chanting marks off, vowels kept."""
    from ..vocalize.base import strip_taamim

    return unicodedata.normalize("NFC", strip_taamim(unicodedata.normalize("NFC", word)))


def observed_variant(stress: int, qatan: bool) -> str:
    """The `variant` an observation is tallied under: stress from the end, and "o" for a
    qamats qatan. The fold that writes these is the half of #584 still to build."""
    return f"{stress}{'o' if qatan else ''}"


def _parse_variant(value: str) -> tuple[int, bool] | None:
    found = re.fullmatch(r"(\d+)(o?)", value.strip())
    if found is None or int(found.group(1)) < 1:
        return None
    return int(found.group(1)), bool(found.group(2))


# --- corrected -----------------------------------------------------------------------


def _settled(row: Mapping[str, Any]) -> bool:
    state = str(row["state"] or "")
    if state == "accepted":
        return True
    if state:
        return False
    # An ASR flag waits for a human ear whoever filed it (spec, Q5).
    return str(row["stage"]) != "asr" and str(row["who"]) in SETTLED_HANDS


def _said(instruction: str, word: str) -> str:
    """The instruction as the hint builder says it, with the word in it."""
    said = _OPENING.sub("", instruction.strip()).rstrip(" .")
    from ..dialogue.checks import bare

    if bare(word) not in bare(said):
        said = f"{word}: {said}"
    return said


def placed(before: str, after: str) -> list[str]:
    """The words of `before` an instruction `after` is about, as they are pointed there.

    The words of the line whose letters the instruction names; or, where it names no
    Hebrew word at all, the line's only word. Anything else is [] — not placed."""
    from ..dialogue.checks import bare, words_of

    line = list(words_of(before))
    named = {bare(word) for word in words_of(after)}
    if named:
        return list(dict.fromkeys(word for word in line if bare(word) in named))
    return line if len(line) == 1 else []


@dataclass
class Corrected:
    entries: dict[str, Entry]
    #: Settled rows whose word could not be found in their line.
    unplaced: int = 0
    #: Rows left out because nobody has settled them yet (an ASR flag, a model's fix).
    unsettled: int = 0


def corrected(store: AccountStore, language: str = "he") -> Corrected:
    """The settled pronunciation fixes, by pointed form. Where two disagree about one
    form, the one made in more places is said; between equals, the later."""
    stages = ", ".join("?" for _ in STAGES)
    kinds = ", ".join("?" for _ in KINDS)
    rows = store.db.execute(
        f"SELECT * FROM correction WHERE stage IN ({stages}) AND kind IN ({kinds})"  # noqa: S608
        " AND language = ? AND after <> '' AND before <> after ORDER BY at, id",
        (*STAGES, *KINDS, language),
    ).fetchall()
    places: dict[str, Counter[str]] = {}
    latest: dict[str, dict[str, int]] = {}
    unplaced = unsettled = 0
    seen: set[tuple[str, str, str, str]] = set()
    for order, row in enumerate(rows):
        if not _settled(row):
            if str(row["state"] or "") != "rejected":
                unsettled += 1
            continue
        before, after = str(row["before"]), str(row["after"])
        one = (str(row["stage"]), str(row["span"]), before, after)
        if one in seen:
            # A proposal and the row that accepted it are one fix.
            continue
        seen.add(one)
        words = placed(before, after)
        if not words:
            unplaced += 1
            continue
        for word in words:
            key = form(word)
            say = _said(after, key)
            places.setdefault(key, Counter())[say] += 1
            latest.setdefault(key, {})[say] = order
    entries: dict[str, Entry] = {}
    for key, said in places.items():
        say = max(said, key=lambda s: (said[s], latest[key][s]))
        entries[key] = Entry(say=say, evidence=said[say], source="correction")
    return Corrected(entries, unplaced, unsettled)


# --- observed ------------------------------------------------------------------------


def observed(counts: Mapping[str, Mapping[str, int]]) -> dict[str, Entry]:
    """The observations past the floor, from {pointed form: {variant: n}}. An entry has
    something to `say` only where another form of the same letters, also past the
    floor, is stressed elsewhere."""
    from ..dialogue.checks import bare

    agreed: dict[str, tuple[int, bool, int]] = {}
    for key, variants in counts.items():
        parsed = [(v, _parse_variant(v), int(n)) for v, n in variants.items()]
        total = sum(n for _, p, n in parsed if p is not None)
        if total < FLOOR_SEEN:
            continue
        _, best, n = max(((v, p, n) for v, p, n in parsed if p is not None), key=lambda x: x[2])
        if best is None or n / total < FLOOR_SHARE:
            continue
        agreed[form(key)] = (best[0], best[1], total)
    stresses: dict[str, set[int]] = {}
    for key, (stress, _, _) in agreed.items():
        stresses.setdefault(bare(key), set()).add(stress)
    out: dict[str, Entry] = {}
    for key, (stress, qatan, total) in agreed.items():
        say = ""
        if len(stresses[bare(key)]) > 1:
            say = f"{key}: stressed on the {_ORDINAL.get(stress, f'{stress}th-from-last')} syllable"
            if qatan:
                say += ', its qamats said "o"'
        out[key] = Entry(stress=stress, qatan=qatan, say=say, evidence=total, source="observed")
    return out


def observations(store: TablesStore | None) -> dict[str, dict[str, int]]:
    """Every current observation in the language tables, or {} where they are off."""
    return store.keyed(PRONUNCIATION) if store is not None else {}


# --- the dictionary ------------------------------------------------------------------


@dataclass
class Built:
    lexicon: dict[str, Any]
    corrections: int
    observations: int
    unplaced: int
    unsettled: int


def build(
    account: AccountStore,
    seen: Mapping[str, Mapping[str, int]] | None = None,
    now: datetime | None = None,
) -> Built:
    """The dictionary: corrections over observations."""
    fixed = corrected(account)
    heard = observed(seen or {})
    forms: dict[str, Entry] = dict(heard)
    for key, entry in fixed.entries.items():
        under = heard.get(key)
        if under is not None:
            # The correction is said; what was observed stays as what it knew.
            entry = Entry(under.stress, under.qatan, entry.say, entry.evidence, entry.source)
        forms[key] = entry
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    lexicon = {
        "rule": RULE,
        "made_at": stamp,
        "floor": {"seen": FLOOR_SEEN, "share": FLOOR_SHARE},
        "forms": {key: asdict(forms[key]) for key in sorted(forms)},
    }
    return Built(lexicon, len(fixed.entries), len(heard), fixed.unplaced, fixed.unsettled)


def _inside_the_repo(path: Path) -> bool:
    root = Path(__file__).resolve().parents[3]
    if not (root / ".git").exists():
        return False
    resolved = path.expanduser().resolve()
    return resolved == root or root in resolved.parents


def write(lexicon: Mapping[str, Any], folder: Path) -> Path:
    """Write `pronunciation.json` into the tables directory, atomically. A folder inside
    the source tree is refused: the dictionary is private, and the repo is public."""
    if _inside_the_repo(folder):
        raise ValueError(f"{folder} is inside the repository; the tables never go there")
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / FILE
    partial = file.with_suffix(".json.partial")
    partial.write_text(json.dumps(lexicon, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    partial.replace(file)
    return file


# --- reading it back -----------------------------------------------------------------

_LOADED: dict[Path, tuple[int, dict[str, Entry]]] = {}


def load(folder: Path | None = None) -> dict[str, Entry]:
    """The dictionary as the hint builder reads it, or {} where none is written (CI, a
    fresh laptop) or it cannot be read. Read again only when the file changes."""
    from .yardstick import directory

    file = (folder or directory()) / FILE
    try:
        stamp = file.stat().st_mtime_ns
    except OSError:
        return {}
    held = _LOADED.get(file)
    if held is not None and held[0] == stamp:
        return held[1]
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
        entries = {
            form(key): Entry(**{k: v for k, v in value.items() if k in _FIELDS})
            for key, value in (raw.get("forms") or {}).items()
            if isinstance(value, dict)
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {}
    _LOADED[file] = (stamp, entries)
    return entries


_FIELDS = frozenset(Entry.__dataclass_fields__)


def looked_up(word: str, lexicon: Mapping[str, Entry]) -> Entry | None:
    """The entry for one word as a line has it, or for it without a leading conjunction:
    וְעוֹשָׂה is still עוֹשָׂה."""
    from ..dialogue.checks import units

    key = form(word)
    entry = lexicon.get(key)
    if entry is not None:
        return entry
    parts = units(key)
    if len(parts) > 2 and parts[0][0] == "ו":
        rest = key[len(parts[0][0]) + len(parts[0][1]) :]
        return lexicon.get(rest)
    return None


def says(words: Iterable[str], lexicon: Mapping[str, Entry]) -> dict[str, str]:
    """{word as written: what to say} for the words the dictionary has something on."""
    out: dict[str, str] = {}
    for word in words:
        entry = looked_up(word, lexicon)
        if entry is not None and entry.say:
            out[word] = entry.say
    return out
