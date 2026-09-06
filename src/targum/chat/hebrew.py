"""Conversation in Hebrew, graded to the reader's own words.

This is the slice the roadmap called a thesis change, and it is built from one sentence:
targum will not be a better conversation partner than the free voice session that already
has the modern learner's hour, so it does not try. What it does that nothing else does is
leave a record — every line the model writes comes with its English on the next line,
every line the reader writes in another language is recast into Hebrew first, and the
whole exchange is the shape a targum has (slice 5 reads it back). The contract below is
what makes the record readable and the grading possible; the eval in
`scripts/eval_grading.py` is what says whether the grading claim is true.

**The shape.** Every Hebrew sentence on its own line, pointed. Its English on the line
below, beginning `= `. A recast of the reader's own words begins `> ` (their Hebrew, as
they might have said it), and its `= ` line is what they actually wrote. Nothing else is
in the contract, so `pairs()` can read a turn back with no model in the loop.

**The vocabulary.** The reader's known lemmas from their ledger, and under them a floor
of the commonest words of the language — bands 1 and 2 of the reader's own six-band
scale, which is Zipf 4.8 and up in `annotate/frequency.py`. One new word per sentence at
most, with its English beside it. Whether a model can hold to a list is the open
question; until the eval answers it, no page says "at your level".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..level import NOT_VOCABULARY, Level, describe

if TYPE_CHECKING:
    from ..accounts import Store

#: Bands 1 and 2 — `frequency.CUTS[1]`. A word this common is one every learner meets
#: in their first months, so it is the floor a conversation may stand on whatever the
#: ledger says.
BAND_FLOOR_ZIPF = 4.8

#: How many of the commonest words to hand the model as the floor. Eight hundred is
#: roughly the first ulpan rung's reckoning, and a list a system prompt can carry.
COMMON = 800

#: How many of the reader's own known words to carry. Beyond this the prompt is paying
#: for a list nobody reads; the commonest are the ones a conversation reaches for.
KNOWN_LIMIT = 1500

#: Words a minute, for turning a typed exchange into the seconds the allowance is kept
#: in. Three measured numbers disagreed and had to be reconciled before any of them
#: metered anything: read-aloud literature runs 5,367 words an hour (89 a minute,
#: measured 2026-09-01 over 2.45 hours of LibriVox); `audio.SPEECH_WORDS_PER_MINUTE` is
#: 150, set deliberately on the high side for a cost *estimate*, over a conversational
#: podcast measured within 3% of 120 and scripted narration 30% over; and conversation
#: is the podcast's register, not the novel's. So 120: the one of the three that was
#: measured on speech shaped like this. The direction of error matters the other way
#: round here — a higher rate charges a reader *fewer* seconds, which is the side an
#: allowance should err on — and 120 is the measured middle, not either edge.
CONVERSATION_WORDS_PER_MINUTE = 120

#: What a reply is assumed to run to before it exists, for the reservation the rails
#: take before the first token. Settled to the real count after the last.
ASSUMED_REPLY_WORDS = 80

RECAST = "> "
ENGLISH = "= "

CONTRACT = f"""This conversation is in Hebrew, whatever language the reader writes in.
Every reply, including one that finds, offers or quotes a text, keeps to this:

- Write in Hebrew, with vowel points (nikkud) on every word — on the full spelling the
  reader meets in a newspaper (ktiv male), not the defective spelling pointed text once
  used: לִקְרוֹא and not לִקְרֹא, שׁוּלְחָן and not שֻׁלְחָן. The word should look like the
  one on their ledger, with its vowels added.
- Every Hebrew sentence goes on its own line. Directly under it, on the next line, its
  English, beginning with "{ENGLISH}". Never a Hebrew line without its English line.
- Begin every reply with the reader's own line, in Hebrew: a line beginning "{RECAST}"
  with their sentence — as they wrote it if their Hebrew was right, corrected if it was
  not, and translated into Hebrew if they wrote in English or any other language — then
  a "{ENGLISH}" line with its English, which for a line they wrote in English is what
  they wrote, as they wrote it. Then answer. Do not lecture about a mistake; the
  corrected line is the whole correction.
- Stay inside the reader's known words and the common words listed below. At most one
  word outside them in a sentence, and its English is on the "{ENGLISH}" line like every
  other word's.
- Keep it short: a few Hebrew sentences, and end with one question so the reader has
  something to answer. When you offer texts, one Hebrew line per text with its English,
  and the text's door under it.
- When the reader asks to read a text, its path - exactly as the tool returned it - goes
  on a line of its own between the Hebrew lines, with nothing else on that line and no
  "{ENGLISH}" line under it. The page draws it as a door. Never say a text is open
  when you have not given its path.
- Still never tell the reader they are at a level. You know their words; use them.
"""


@dataclass(frozen=True)
class Pair:
    hebrew: str
    english: str
    recast: bool = False


def pairs(text: str) -> list[Pair]:
    """Read a turn back as (Hebrew, English) lines, by the contract and nothing else.

    A Hebrew line with no `= ` under it is kept with an empty English — the transcript
    should show what was said rather than hide a line the model forgot to translate.
    Lines that are neither (a stray English sentence) are dropped: they are not in the
    record's shape.
    """
    out: list[Pair] = []
    pending: tuple[str, bool] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(ENGLISH):
            if pending is not None:
                out.append(Pair(pending[0], line[len(ENGLISH) :].strip(), pending[1]))
                pending = None
            continue
        if pending is not None:
            out.append(Pair(pending[0], "", pending[1]))
            pending = None
        recast = line.startswith(RECAST)
        body = line[len(RECAST) :].strip() if recast else line
        if _has_hebrew(body):
            pending = (body, recast)
    if pending is not None:
        out.append(Pair(pending[0], "", pending[1]))
    return out


def _has_hebrew(text: str) -> bool:
    return any("א" <= ch <= "ת" for ch in text)


def common_words(n: int = COMMON, language: str = "he") -> list[str]:
    """The commonest words of the language at bands 1 and 2, most common first.

    From wordfreq, the same table the reader's bands come from, so "common" here means
    the same thing it means on their word cards. Empty where the `difficulty` extra is
    not installed — the prompt then stands on the ledger alone, and says nothing false.
    """
    try:
        from wordfreq import top_n_list, zipf_frequency
    except ImportError:
        return []
    code = language.split("-")[0].lower()
    return [
        word for word in top_n_list(code, n * 2) if zipf_frequency(word, code) >= BAND_FLOOR_ZIPF
    ][:n]


def known_words(
    store: Store, person_id: int | None, language: str, limit: int = KNOWN_LIMIT
) -> list[str]:
    """The reader's known lemmas, newest first, names and numbers left out."""
    rows = store.words_with_bands(person_id, language)
    known = [
        (at, lemma)
        for lemma, status, band, at in rows
        if status == 9 and band not in NOT_VOCABULARY and lemma
    ]
    known.sort(reverse=True)
    return [lemma for _, lemma in known[:limit]]


def ledger_block(level: Level, known: list[str], common: list[str]) -> str:
    """The per-reader block: the ledger, then the word lists."""
    parts = [describe(level)]
    if known:
        parts.append(f"The reader's known words ({len(known)}): " + " ".join(known))
    else:
        parts.append("The reader has marked no words known yet; stand on the common words.")
    if common:
        parts.append(f"Common words any learner meets early ({len(common)}): " + " ".join(common))
    return "\n\n".join(parts)


def words_in(*texts: str) -> int:
    return sum(len(text.split()) for text in texts)


def seconds_for(words: int) -> float:
    """How long this many words take to say, at the conversational rate."""
    return max(0.0, words) / CONVERSATION_WORDS_PER_MINUTE * 60.0
