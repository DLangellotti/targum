"""Two diacritizers on the same held-out Hebrew, mark by mark (targum-internal#148).

`vocalize/nakdimon.py` was chosen for one behaviour — it returns the letters it was
given — and never for its accuracy, which was measured once, on classical Hebrew, at
55-73%. DICTA's `dictabert-large-char-menaked` claims state of the art on modern text and
has a `mark_matres_lectionis` option that keeps the letters, which answers the objection
that ruled its family out. Before anything is swapped, this measures the two on text
neither was trained on.

**Two held-out sets**, chosen with `--corpus`:

- `dicta-modern`: the modern third of DICTA's own `hebrew-diacritization-test-corpora`
  (github.com/Dicta-Israel-Center-for-Text-Analysis): a random selection of Hebrew
  Wikipedia articles, fully pointed by hand, offered "up to the public domain" in its
  README. The repository carries no LICENSE file; the README's sentence is the licence.
  It is a *test* corpus, published for exactly this comparison, so the menaked was not
  trained on it — and Nakdimon, trained before it existed on a different pointed
  corpus, was not either. The rabbinic and poetry thirds are left out on purpose: the
  menaked's card says it is not for them, and the Mishnah and siddur stay on Nakdimon
  whatever this finds.
- `ben-yehuda`: pointed works from Project Ben-Yehuda's public domain dump
  (github.com/projectbenyehuda/public_domain_dump, LICENSE: "The data files in this
  repository are in the public domain"; credit asked for, not required, to "Project
  Ben-Yehuda volunteers"). The site's API is free but wants a key and at most fifty
  requests a minute, so the dump is read instead. **Held out by author**: Nakdimon's
  training set (github.com/elazarg/hebrew_diacritized) names its Ben-Yehuda authors —
  Bialik, Tchernichovsky, Dushman, Regelson, Porat, Zviri, Kaplan, Ofek, Berkman — and
  none of them is here. The menaked's card says only "modern Hebrew texts manually
  diacritized by linguistic experts", so its authors cannot be excluded, only noted. The
  works are in `BEN_YEHUDA_WORKS`: prose from Katzenelson, Barash, Frank, Frischmann and
  Yehuda Steinberg; poetry from Rachel, Karni, Bergstein, Lensky, Gordon, Elisheva and
  Yaakov Steinberg. Prose and poetry both, because pointed prose is what the shelf has
  and the poetry is where the menaked's card says it is weakest. This is the Hebrew of
  1880-1940, not a newspaper's: harder for both models, and the second opinion the first
  corpus needs, since that one is DICTA's own house style.

**What each model is given** is the bare text: marks removed, letters as the edition
spells them. In the DICTA corpus a mater lectionis is marked in angle brackets
(`דִּ<י>בֵּר`) and the brackets go too; the reference keeps the letter carrying nothing,
which is the pointing a diacritizer that keeps the letters ought to produce. The menaked
is asked with `mark_matres_lectionis=""`, which keeps the letter and marks it with
nothing. A Ben-Yehuda work is read paragraph by paragraph, only the fully pointed ones
are kept, and consecutive ones are joined into lines of at least `CHUNK_WORDS` words so
a line is a paragraph's worth of text for both corpora; at most `PER_WORK` lines per
work, spread through it, so no one novel outweighs the poets.

**What is scored**, per line, after the production skeleton check in `vocalize/base.py`:

- `skeleton_kept`: the share of lines `splice()` accepts. The issue's gate: a model that
  fails this on any line is out regardless of what follows. The maqaf is part of the
  skeleton; the DICTA corpus has none, the Ben-Yehuda editions have many.
- `letter_vowel`: per Hebrew letter, the vowel marks match exactly. Qamats qatan
  (U+05C7) counts as its own vowel. `letter_vowel_folded` is the same with U+05C7 read
  as U+05B8 — the number a model that never emits the qatan deserves on the vowel itself.
- `letter_dagesh`: per letter, dagesh present where the reference has it and absent
  where it does not.
- `shin_dot`: per shin the reference dots, the shin or sin dot matches. A shin the
  reference leaves bare — the Ben-Yehuda editions dot only the sin — is not scored on
  its dot at all, in the word either.
- `qamats_qatan_recall` and `_precision`: of the letters the reference marks U+05C7, how
  many the model did; of the ones the model marked, how many were right. Not recorded
  for a model that emits none — that is a base of zero, not a score of zero.
- `word_exact`: per word (a run of Hebrew letters), every vowel, dagesh and shin dot on
  every letter matches. Meteg and rafe, which an older edition may carry, are neither
  scored nor held against a model.
- Stress (U+05AB) is counted in the output and reported in the table. Neither model
  emits it and the references do not carry it, so it is never a ledger row. That is
  #132's problem and this script exists to give it a baseline, not to solve it.

The letter and word metrics are computed only on lines whose skeleton survived, because
a line whose letters changed cannot be aligned with its reference; `n` on each row says
how many letters, shins or words were actually compared.

Each number is appended to `evals/ledger.jsonl` as stage `vocalize`, under the corpus
name, with the system and the version of it that ran. Models are loaded one at a time
and freed before the next: this is an eight-gigabyte laptop and the menaked is 1.2 GB of
weights. Each corpus is fetched once to the gold directory beside the IAHLT treebanks,
for evaluation and nothing else. Nothing here spends money.

    PYTHONPATH=src .venv/bin/python scripts/measure_pointing.py [--corpus ben-yehuda] \\
        [--limit 250] [--show 8]
"""

from __future__ import annotations

import argparse
import dataclasses
import gc
import importlib.metadata
import re
import sys
import time
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.errors import SkeletonChanged, TargumError  # noqa: E402
from targum.paths import ensure, model_dir, write_atomic  # noqa: E402
from targum.vocalize.base import (  # noqa: E402
    LETTERS,
    MARKS,
    is_fully_pointed,
    splice,
    strip_nikkud,
)
from targum.vocalize.dicta import MODEL as MENAKED  # noqa: E402

#: The vowels proper: sheva, the three hatafs, hiriq through qubuts, and qamats qatan.
VOWELS = frozenset(range(0x05B0, 0x05BC)) | {0x05C7}
DAGESH = 0x05BC
SHIN_DOTS = frozenset({0x05C1, 0x05C2})
#: Everything a word is scored on. Meteg (U+05BD) and rafe (U+05BF) are outside it.
SCORED = VOWELS | {DAGESH} | SHIN_DOTS
QAMATS, QAMATS_QATAN = 0x05B8, 0x05C7
STRESS = 0x05AB


class Line(NamedTuple):
    """One line of a corpus: the reference pointing, and what the models see."""

    gold: str
    bare: str


# --- the DICTA test corpus ------------------------------------------------------------

DICTA_SOURCE = (
    "https://raw.githubusercontent.com/Dicta-Israel-Center-for-Text-Analysis/"
    "hebrew-diacritization-test-corpora/master/ModernTestCorpus-HebrewWiki1.txt"
)
#: An article header in the corpus file: ` ** !! ** $0001$ title ** !! **`.
_HEADER = "** !! **"
_BRACKETS = re.compile(r"[<>]")


def bare_of(gold: str) -> str:
    return "".join(char for char in gold if ord(char) not in MARKS)


def parse_dicta(text: str) -> list[Line]:
    lines: list[Line] = []
    for raw in text.splitlines():
        if not raw.strip() or _HEADER in raw:
            continue
        gold = _BRACKETS.sub("", raw.strip())
        lines.append(Line(gold, bare_of(gold)))
    return lines


def fetch_dicta(say: Callable[[str], None]) -> list[Line]:
    path = gold_dir() / "dicta-diacritization-modern.txt"
    if not path.is_file():
        say("Fetching dicta-modern…")
        write_atomic(path, _get(DICTA_SOURCE))
    return parse_dicta(path.read_text(encoding="utf-8"))


# --- Project Ben-Yehuda ---------------------------------------------------------------

BEN_YEHUDA_SOURCE = (
    "https://raw.githubusercontent.com/projectbenyehuda/public_domain_dump/master/txt/{path}.txt"
)
#: (author, genre, path in the dump). Chosen 2026-09-07 from the pseudocatalogue by
#: probing each candidate author's works for a body that is actually pointed, since a
#: pointed title says nothing about the text under it. Authors in Nakdimon's training
#: set are absent by construction; see the module docstring.
BEN_YEHUDA_WORKS: tuple[tuple[str, str, str], ...] = (
    ("יצחק קצנלסון", "prose", "p440/m42219"),  # חֲבֵרִים
    ("יצחק קצנלסון", "prose", "p440/m52755"),  # הָאָדָם (אגדה)
    ("יצחק קצנלסון", "prose", "p440/m39144"),  # יַלְדַי הַפְּרָחִים
    ("אשר ברש", "prose", "p1274/m39524"),  # פֶּרֶק רְבִיעִי: עַל מַיִם רַבִּים
    ("אשר ברש", "prose", "p1274/m46211"),  # טַלִּיסְמָא מְדַבֶּרֶת
    ("אשר ברש", "prose", "p1274/m57811"),  # הַמַּצָּה הַחַמָּה
    ("עזריאל נתן פרנק", "prose", "p87/m20910"),  # לֵדָתוֹ שֶל רַבִּי יִשְׂרָאֵל בַּעַל־שֵם
    ("עזריאל נתן פרנק", "prose", "p87/m20931"),  # בִּרְכַּת הֶדְיוֹט
    ("דוד פרישמן", "prose", "p142/m11442"),  # תִּתְחַדֵּשׁ
    ("יהודה שטיינברג", "prose", "p117/m44548"),  # פְּנֵי מֹשֶׁה
    ("יהודה שטיינברג", "prose", "p117/m44564"),  # חֶמְדָּן הַיָּפֶה
    ("יהודה שטיינברג", "prose", "p117/m53497"),  # נֵס חֲנֻכָּה
    ("רחל בלובשטיין", "poetry", "p141/m4339"),  # כָּאן עַל פְּנֵי הָאֲדָמָה
    ("רחל בלובשטיין", "poetry", "p141/m1685"),  # עֵץ אַגָּס
    ("רחל בלובשטיין", "poetry", "p141/m19"),  # הֲלָךְ נֶפֶשׁ
    ("יהודה קרני", "poetry", "p609/m17036"),  # אֶל בַּלְפוּר
    ("יהודה קרני", "poetry", "p609/m16802"),  # לְחֹדֶשׁ הַהַצָּלָה
    ("פניה ברגשטיין", "poetry", "p814/m24325"),  # שִׁיר לְיָעֵל
    ("חיים לנסקי", "poetry", "p726/m20521"),  # בַּקֻּפֶּה אַפְלוּלִית
    ("חיים לנסקי", "poetry", "p726/m20690"),  # אִגֶּרֶת א' לְרוֹבֶּרְט לֶוִין
    ("יהודה ליב גורדון", "poetry", "p46/m7786"),  # חַג לַאדֹנָי
    ("יהודה ליב גורדון", "poetry", "p46/m92"),  # חִידוֹת בְּמִלּוֹת יְחִידוֹת
    ("אלישבע", "poetry", "p611/m43335"),  # מַה קְּטַנִּים הָיוּ
    ("אלישבע", "poetry", "p611/m43383"),  # וּבְכֵן, אֵשֵׁב
    ("יעקב שטיינברג", "poetry", "p388/m10146"),  # בִּדְלֹק הַמְּנוֹרָה
    ("יעקב שטיינברג", "poetry", "p388/m10423"),  # בַּלָּדוֹת
)
#: Every dump file ends with a credit block that begins with this.
_FOOTER = "פרויקט בן־יהודה"
#: A line is at least this many Hebrew words, so a verse of four does not stand alone.
CHUNK_WORDS = 20
#: Lines kept per work, spread through it.
PER_WORK = 30


def hebrew_words(text: str) -> int:
    return sum(1 for word in text.split() if any(ord(char) in LETTERS for char in word))


def parse_ben_yehuda(text: str) -> list[Line]:
    """A work's fully pointed paragraphs, joined into lines of `CHUNK_WORDS` or more.

    The first paragraph is the title and the credit block at the end is the project's,
    so both are dropped. An unpointed paragraph — a section label, a quotation the
    editor left bare — ends the line being built rather than joining it, and a short
    tail that never reached the size is kept if it has at least four words: a poem's
    last stanza is still the poet's Hebrew.
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()][1:]
    lines: list[Line] = []
    run: list[str] = []
    for paragraph in paragraphs:
        if _FOOTER in paragraph:
            break
        if not is_fully_pointed(paragraph) or hebrew_words(paragraph) < 2:
            if run and hebrew_words(" ".join(run)) >= 4:
                lines.append(_line(run))
            run = []
            continue
        run.append(paragraph)
        if hebrew_words(" ".join(run)) >= CHUNK_WORDS:
            lines.append(_line(run))
            run = []
    if run and hebrew_words(" ".join(run)) >= 4:
        lines.append(_line(run))
    return lines


def _line(run: list[str]) -> Line:
    gold = " ".join(run)
    return Line(gold, bare_of(gold))


def fetch_ben_yehuda(say: Callable[[str], None]) -> list[Line]:
    lines: list[Line] = []
    for _author, _genre, work in BEN_YEHUDA_WORKS:
        path = ensure(gold_dir() / "ben-yehuda") / (work.replace("/", "_") + ".txt")
        if not path.is_file():
            say(f"Fetching ben-yehuda {work}…")
            write_atomic(path, _get(BEN_YEHUDA_SOURCE.format(path=work)))
        lines.extend(spread(parse_ben_yehuda(path.read_text(encoding="utf-8")), PER_WORK))
    return lines


# --- both -----------------------------------------------------------------------------


class Corpus(NamedTuple):
    credit: str
    licence: str
    load: Callable[[Callable[[str], None]], list[Line]]


CORPORA: dict[str, Corpus] = {
    "dicta-modern": Corpus(
        "DICTA, hebrew-diacritization-test-corpora (modern: Hebrew Wikipedia)",
        "public domain, per the repository README; no LICENSE file",
        fetch_dicta,
    ),
    "ben-yehuda": Corpus(
        "Project Ben-Yehuda volunteers, public_domain_dump "
        f"({len(BEN_YEHUDA_WORKS)} works, {len({a for a, _, _ in BEN_YEHUDA_WORKS})} authors)",
        "public domain, per the dump's LICENSE",
        fetch_ben_yehuda,
    ),
}


def gold_dir() -> Path:
    """Beside the IAHLT treebanks and for the same reason: fetched once, read by a
    laptop, never shipped and never trained on."""
    return ensure(model_dir() / "gold")


def _get(url: str) -> str:
    import httpx

    try:
        answer = httpx.get(url, timeout=180.0, follow_redirects=True)
        answer.raise_for_status()
    except Exception as bad:  # noqa: BLE001 - network and HTTP both land here
        raise TargumError(f"Could not fetch {url}.", str(bad)) from bad
    return answer.text


def units(text: str) -> list[tuple[str, frozenset[int]]]:
    """Each base character with the set of marks that follow it. Order-blind, because
    the two models and the reference write dagesh, shin dot and vowel in three orders."""
    out: list[tuple[str, set[int]]] = []
    for char in text:
        if ord(char) in MARKS:
            if out:
                out[-1][1].add(ord(char))
        else:
            out.append((char, set()))
    return [(base, frozenset(marks)) for base, marks in out]


def word_spans(bases: Sequence[str]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(bases):
        if ord(bases[start]) not in LETTERS:
            start += 1
            continue
        end = start
        while end < len(bases) and ord(bases[end]) in LETTERS:
            end += 1
        spans.append((start, end))
        start = end
    return spans


def spread(lines: list[Line], limit: int) -> list[Line]:
    """`limit` lines spaced evenly through the list, so a cheap run still crosses
    articles rather than reading the first one twice over."""
    if limit <= 0 or limit >= len(lines):
        return lines
    step = len(lines) / limit
    return [lines[int(i * step)] for i in range(limit)]


def _fold(marks: frozenset[int]) -> frozenset[int]:
    return frozenset(QAMATS if mark == QAMATS_QATAN else mark for mark in marks)


@dataclasses.dataclass
class Tally:
    """Counts, so that lines add and a rate is computed once at the end."""

    lines: int = 0
    skeleton_kept: int = 0
    failed: int = 0
    letters: int = 0
    vowel_ok: int = 0
    vowel_folded_ok: int = 0
    dagesh_ok: int = 0
    shins: int = 0
    shin_ok: int = 0
    qatan_gold: int = 0
    qatan_hit: int = 0
    qatan_emitted: int = 0
    words: int = 0
    word_ok: int = 0
    stress_emitted: int = 0
    seconds: float = 0.0
    misses: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    #: Lines the skeleton check refused: the bare input beside what came back, stripped,
    #: so the letter that changed can be read rather than inferred from a count.
    broken: list[tuple[str, str]] = dataclasses.field(default_factory=list)

    def rates(self) -> dict[str, tuple[float | None, int]]:
        """Metric to (score, n). None where there was nothing to measure."""

        def rate(hit: int, base: int) -> float | None:
            return None if base == 0 else hit / base

        return {
            "skeleton_kept": (rate(self.skeleton_kept, self.lines), self.lines),
            "letter_vowel": (rate(self.vowel_ok, self.letters), self.letters),
            "letter_vowel_folded": (rate(self.vowel_folded_ok, self.letters), self.letters),
            "letter_dagesh": (rate(self.dagesh_ok, self.letters), self.letters),
            "shin_dot": (rate(self.shin_ok, self.shins), self.shins),
            "qamats_qatan_recall": (rate(self.qatan_hit, self.qatan_gold), self.qatan_gold),
            "qamats_qatan_precision": (
                rate(self.qatan_hit, self.qatan_emitted),
                self.qatan_emitted,
            ),
            "word_exact": (rate(self.word_ok, self.words), self.words),
        }


def score(line: Line, output: str | None, tally: Tally, keep: int = 0) -> None:
    """Add one line's result to the tally.

    The skeleton check is the production one: `splice` refuses an output whose base
    characters differ from the input's, and that refusal is what is counted. A model that
    produced nothing for the line — an exception, a refusal — fails the line too, since a
    reader would have had no pointing either way.
    """
    tally.lines += 1
    if output is None:
        tally.failed += 1
        return
    try:
        merged, _ = splice(line.bare, output)
    except SkeletonChanged:
        tally.failed += 1
        if len(tally.broken) < keep:
            tally.broken.append((line.bare, strip_nikkud(output)[0]))
        return
    tally.skeleton_kept += 1
    tally.stress_emitted += sum(1 for char in merged if ord(char) == STRESS)

    gold, got = units(line.gold), units(merged)
    assert [base for base, _ in gold] == [base for base, _ in got]
    bases = [base for base, _ in gold]
    for (base, want), (_, have) in zip(gold, got, strict=True):
        if ord(base) not in LETTERS:
            continue
        tally.letters += 1
        want_v, have_v = want & VOWELS, have & VOWELS
        tally.vowel_ok += want_v == have_v
        tally.vowel_folded_ok += _fold(want_v) == _fold(have_v)
        tally.dagesh_ok += (DAGESH in want) == (DAGESH in have)
        # A shin the reference leaves undotted is not a shin read as sin: editions of
        # the Ben-Yehuda period write the plain shin bare and dot only the sin. So the
        # dot is compared only where the reference took a position, and a bare shin in
        # the reference is not scored on its dot, in the word either.
        if base == "ש" and want & SHIN_DOTS:
            tally.shins += 1
            tally.shin_ok += (want & SHIN_DOTS) == (have & SHIN_DOTS)
        if QAMATS_QATAN in want:
            tally.qatan_gold += 1
            tally.qatan_hit += QAMATS_QATAN in have
        if QAMATS_QATAN in have:
            tally.qatan_emitted += 1
    for start, end in word_spans(bases):
        tally.words += 1
        if all(
            want & SCORED == have & _scored(want)
            for (_, want), (_, have) in zip(gold[start:end], got[start:end], strict=True)
        ):
            tally.word_ok += 1
        elif len(tally.misses) < keep:
            tally.misses.append(
                (
                    line.gold[_at(gold, start) : _at(gold, end)],
                    merged[_at(got, start) : _at(got, end)],
                )
            )


def _scored(want: frozenset[int]) -> frozenset[int]:
    """What a model's letter is compared on: everything scored, minus the shin dot
    where the reference has none."""
    return SCORED if want & SHIN_DOTS else SCORED - SHIN_DOTS


def _at(pointed: list[tuple[str, frozenset[int]]], index: int) -> int:
    """The string offset of unit `index` in the text the units came from."""
    return sum(1 + len(marks) for _, marks in pointed[:index])


# --- the models -----------------------------------------------------------------------


def run_nakdimon(lines: list[Line], say: Callable[[str], None]) -> tuple[str, list[str | None]]:
    """Through the production vocalizer, sentence by sentence, exactly as a build does."""
    from nakdimon.predict import load_cached_model

    from targum.models import Segment
    from targum.vocalize.nakdimon import NakdimonVocalizer

    engine = NakdimonVocalizer()
    segments = [
        Segment(id=f"s{i}", block_id=f"b{i}", block_index=i, index=0, text=line.bare)
        for i, line in enumerate(lines)
    ]
    version = importlib.metadata.version("nakdimon")
    say(f"{engine.name} (nakdimon {version}) over {len(lines)} lines…")
    got = engine.vocalize(segments, "he")
    load_cached_model.cache_clear()
    return version, [got.get(segment.id) for segment in segments]


def run_menaked(lines: list[Line], say: Callable[[str], None]) -> tuple[str, list[str | None]]:
    """DICTA's menaked through `vocalize/dicta.py`, which is what a build runs.

    The weights are CC BY 4.0 on the model card; this is the local run that licence
    permits, and not the hosted Nakdan, which is NonCommercial by DICTA's terms and is
    never called. Fetched here if absent, since a measurement is not a build.
    """
    import torch

    from targum.vocalize.dicta import DictaVocalizer, point

    say(f"loading {MENAKED}…")
    model, tokenizer = DictaVocalizer(auto_download=True).load()
    # `/walk` names the assembly in `dicta.assemble`, which walks the input rather than
    # the tokens as the card's `predict` does, so its rows never pass for the card's.
    version = str(getattr(model.config, "_commit_hash", None) or "unknown")[:12] + "/walk"
    say(f"{MENAKED} @ {version} over {len(lines)} lines…")
    out: list[str | None] = []
    with torch.inference_mode():
        for i, line in enumerate(lines):
            try:
                out.append(point(model, tokenizer, line.bare))
            except Exception as error:  # noqa: BLE001 - a third-party model, not our code
                say(f"  line {i}: {type(error).__name__}: {str(error)[:120]}")
                out.append(None)
    del model, tokenizer
    gc.collect()
    return version, out


RUNNERS: dict[str, tuple[str, Callable[..., tuple[str, list[str | None]]]]] = {
    "nakdimon": ("nakdimon/2", run_nakdimon),
    "menaked": (MENAKED, run_menaked),
}


# --- the report -----------------------------------------------------------------------


def table(results: dict[str, tuple[str, Tally]]) -> str:
    names = list(results)
    head = f"{'metric':24}" + "".join(f"{name:>22}" for name in names)
    rows = [head, "-" * len(head)]
    metrics = list(next(iter(results.values()))[1].rates())
    for metric in metrics:
        cells = []
        for name in names:
            score_, n = results[name][1].rates()[metric]
            cells.append(f"{'—':>14} n={n:<6}" if score_ is None else f"{score_:14.4f} n={n:<6}")
        rows.append(f"{metric:24}" + "".join(f"{cell:>22}" for cell in cells))
    for label, field in (
        ("lines failed", "failed"),
        ("qamats qatan emitted", "qatan_emitted"),
        ("stress U+05AB emitted", "stress_emitted"),
    ):
        cells = [f"{getattr(results[name][1], field):>22}" for name in names]
        rows.append(f"{label:24}" + "".join(cells))
    rows.append(f"{'seconds':24}" + "".join(f"{results[name][1].seconds:22.1f}" for name in names))
    rows.append(f"{'version':24}" + "".join(f"{results[name][0][:20]:>22}" for name in names))
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--corpus", choices=sorted(CORPORA), default="dicta-modern")
    parser.add_argument("--limit", type=int, default=0, help="lines to score, 0 for all")
    parser.add_argument(
        "--model",
        action="append",
        choices=sorted(RUNNERS),
        help="which to run (default both, Nakdimon first)",
    )
    parser.add_argument("--show", type=int, default=6, help="mismatched words listed per model")
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--dry-run", action="store_true", help="print, append nothing")
    args = parser.parse_args()

    say: Callable[[str], None] = lambda message: print(message, file=sys.stderr)  # noqa: E731
    corpus = CORPORA[args.corpus]
    lines = spread(corpus.load(say), args.limit)
    say(
        f"{args.corpus}: {len(lines)} lines, {sum(hebrew_words(line.bare) for line in lines)} words"
    )

    results: dict[str, tuple[str, Tally]] = {}
    for name in args.model or ["nakdimon", "menaked"]:
        system, runner = RUNNERS[name]
        tally = Tally()
        started = time.monotonic()
        try:
            version, outputs = runner(lines, say)
        except Exception as error:  # noqa: BLE001 - report the failure, score the rest
            say(f"{system} could not run: {type(error).__name__}: {error}")
            continue
        tally.seconds = time.monotonic() - started
        for line, output in zip(lines, outputs, strict=True):
            score(line, output, tally, keep=args.show)
        results[name] = (f"{system} @ {version}", tally)
        gc.collect()

    if not results:
        raise SystemExit("nothing ran")
    print(f"\n{args.corpus} — {corpus.credit}; {corpus.licence}\n")
    print(table(results))
    for system, tally in results.values():
        if tally.broken:
            print(f"\n{system}, lines whose letters changed (input → output, marks off):")
            for bare, got in tally.broken:
                print(f"  {bare[:70]!r}\n  {got[:70]!r}")
        if tally.misses:
            print(f"\n{system}, first mismatched words (reference → model):")
            for want, have in tally.misses:
                print(f"  {want}  →  {have}")

    today = date.today().isoformat()
    rows: list[evals.Row] = []
    for system_at, tally in results.values():
        system, _, version = system_at.partition(" @ ")
        note = f"limit={args.limit or 'all'} lines={tally.lines} failed={tally.failed}"
        for metric, (score_, n) in tally.rates().items():
            if score_ is None:
                continue
            rows.append(
                evals.Row(
                    today,
                    "vocalize",
                    system,
                    version,
                    metric,
                    round(score_, 4),
                    n,
                    corpus=args.corpus,
                    note=note,
                )
            )
    if args.dry_run:
        print(f"\n(dry run: {len(rows)} rows not appended)")
        return
    evals.append(rows, args.ledger)
    print(f"\nappended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
