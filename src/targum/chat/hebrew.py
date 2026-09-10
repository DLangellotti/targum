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
scale, which is Zipf 4.8 and up in `annotate/frequency.py`. Natural Hebrew first
(decided 2026-09-06, on the first live conversations): the lists are what to prefer, not
a wall, and a sentence is never bent to stay inside them; two or three new words a
reply, brought in on purpose and used again, with their English beside them. Whether a
model can hold near a list is the open question; every turn records how far outside it
fell (`record.outside_share`), and until the eval answers, no page says "at your level".
"""

from __future__ import annotations

import re
import time
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

#: How far back "lately" reaches for the words brought back into a conversation, in
#: the milliseconds the ledger keeps `at` in. A week: the research this rests on says a
#: saved word wants eight to twelve more meetings, spread out, and a week is spread out.
LATELY_MS = 7 * 24 * 3600 * 1000

#: How many of the reader's words come back into one reply's list, by status — the
#: whole ledger, a few at a time, not only what was saved this week (decided 2026-09-07:
#: the conversation is where a word is met again when the reader is not reading). A
#: word met once needs the most meetings and a nearly-known one the fewest, and a few
#: known words from long ago stay alive. Rotated by conversation since 2026-09-10
#: (targum-internal#239): a slice that moved every turn moved the block the model is
#: given every turn, and everything after it in the prompt — the whole history — fell
#: out of the cache with it. One conversation now sees one slice; the next conversation
#: sees the next.
BRING_BACK = {1: 5, 2: 4, 3: 3}
KNOWN_BACK = 3
BRING_BACK_PHRASES = 6
#: How common a word has to be to count as one a modern conversation can carry back.
#: Band 4 is Zipf 3.4 and up in `annotate/frequency.py`: a word a newspaper uses. A word
#: saved in Judges that no newspaper uses stays in Judges.
MODERN_BAND = 4

RECAST = "> "
ENGLISH = "= "
#: One line, at most one a reply, directly under the recast's English, only when the
#: recast changed something: what changed and the rule, in the reader's language
#: (2026-09-10, targum-internal#242). The correction used to be silent — the recast
#: rendered the same whether or not anything was changed — and the notes of that day
#: asked for "a correction and an explanation". Folded on the page; a text written
#: from the conversation drops it.
WHY = "~ "

#: How many Hebrew sentences a reply may run to, and how many lines when the answer is a
#: list. Numbers rather than "a few" since 2026-09-10 (targum-internal#236): measured on
#: the stored conversations, "a few" was a median of 36 Hebrew words over five lines,
#: ten with their English, and the notes of that day called it too much to read.
MOST_SENTENCES = 3
MOST_LISTED = 6

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
  not, and said in Hebrew if they wrote in English or any other language — then a
  "{ENGLISH}" line with its English, which for a line they wrote in English is what
  they wrote, as they wrote it. The recast is what they meant, said the way a Hebrew
  speaker says it: correct and idiomatic, in Hebrew word order, in one clean sentence
  or two. Never carry their grammar mistakes, their slips or their English word order
  into it — the recast is the correction, and a wrong recast becomes the line of record.
  If the recast changed anything the reader wrote in Hebrew — a wrong form, a missing
  word, English word order — one line beginning "{WHY}" directly under the recast's
  "{ENGLISH}" line: one sentence in the reader's language naming what changed and the
  rule, like "{WHY}Past tense: הָלַכְתִּי, not הָלַךְ." Never on a line that was right,
  never for a line written in English or another language, never a second sentence,
  and nowhere else in the reply. Then answer. Do not lecture about a mistake in the
  body; the corrected line is the correction, and the one "{WHY}" line is the whole
  explanation.
- Write your own lines in Hebrew first, as a Hebrew speaker would say them to a
  friend: the idiom, the word order and the register of spoken Israeli Hebrew, and the
  plain words. Do not think of an English sentence and translate it — no calques: not
  "אָז נַגִּיד אֶת זֶה יָשִׁיר" for "let's say it straight", not "אֲנִי מֵבִיא מִילִים"
  for "I bring words", not "הַצָּעָה לְטֶקְסְט" for "a suggestion for a text", not
  "מַדָּף הַתְחָלָה מְשׁוּתָּף" for "a shared starter shelf". If a sentence would only
  make sense to someone who knows the English under it, it is not Hebrew yet. The
  "{ENGLISH}" line under each of your lines is the English for the Hebrew you wrote,
  and may read a little differently from how you would have put it in English; that is
  right.
- Punctuate like Hebrew, not like English prose. No em dashes between clauses — a
  comma, a full stop or a new sentence instead; a hyphen only inside a compound
  (אָלֶף־בֵּית). No colon lead-ins that announce what is coming: not "וְעוֹד דָּבָר:",
  not "שִׂים לֵב:", not "בַּמִּסְפָּרִים שֶׁלְּךָ:", not "הָרִאשׁוֹן: … הַשֵּׁנִי: …",
  not "וְעַכְשָׁיו אֵלֶיךָ:" — say the thing. Small numbers as words: שְׁנֵי הַיָּמִים,
  not "2 הַיָּמִים". Use the right word, not the nearest one: the narration of a video is
  הֶסְבֵּר, not הַסְבָּרָה.
- No English inside a Hebrew line, not even in brackets: never "נִשְׁמֶרֶת (is saved)".
  The English lives on the "{ENGLISH}" line and nowhere else. A word Israelis say in
  English is written in Hebrew letters (פּוֹדְקָאסְט), and an English verb never gets
  Hebrew clothes: לִלְחוֹץ עַל מִילָּה, never "לְקַלֵּק". The one exception is a title
  that is in English, a video's name, which stands as it is.
- Do not end every reply the same way. Ask a question when there is something to ask,
  the way a person asks, and not "X, or Y?" every time; a reply may also simply end.
- Natural first. Prefer the reader's known words and the common words listed below
  wherever a natural sentence allows, so that most of what you write is theirs already —
  but never bend a sentence to avoid a word: a stilted line inside the list is worse
  than a natural one a little outside it. Bring new words in on purpose, two or three in
  a reply and not more, chosen because the reader will meet them again — each is on its
  "{ENGLISH}" line like every other word — and use a word you brought in again a few
  lines later. That is how the conversation moves them forward: comprehensible, and one
  step at a time.
- Keep it short: at most {MOST_SENTENCES} Hebrew sentences in a reply, after the
  "{RECAST}" line, which does not count. A reply that hands over a text — a door, a
  card — is one sentence and the door. More only when the reader asks for more, or asks
  a question whose answer is a list, and then at most {MOST_LISTED} lines. (Until
  2026-09-08 this line also said "and give the reader something to answer", and every
  reply ended in homework built from the bring-back words; until 2026-09-10 it said "a
  few Hebrew sentences", and a few was five lines, ten with their English, which the
  notes of that day called too much to read.) When you offer texts, one Hebrew line per
  text with its English, and the text's door under it.
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
    #: Why the recast changed what the reader wrote, from the "~ " line, or nothing.
    why: str = ""


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
        if line.startswith(WHY):
            # Belongs to the recast just closed, and to nothing else: a "~ " anywhere
            # else in a reply is the contract broken, and is dropped.
            if pending is None and out and out[-1].recast and not out[-1].why:
                out[-1] = Pair(out[-1].hebrew, out[-1].english, True, line[len(WHY) :].strip())
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


def length(text: str) -> int:
    """How many Hebrew words a reply is, the way a reader meets them: over the model's
    own lines, the "> " recast left out because it is the reader's sentence said back.
    A word is a run of Hebrew letters and points; the number is what the cap in the
    contract is about, and what `scripts/eval_grading.py` and
    `scripts/measure_reply_length.py` count."""
    return sum(len(_WORD.findall(pair.hebrew)) for pair in pairs(text) if not pair.recast)


_WORD = re.compile(r"[\u05d0-\u05ea][\u05b0-\u05c7\u05d0-\u05ea\u05f3\u05f4\"']*")


def common_words(n: int = COMMON, language: str = "he") -> list[str]:
    """The commonest words of the language at bands 1 and 2, most common first.

    From wordfreq, the same table the reader's bands come from, so "common" here means
    the same thing it means on their word cards. Empty where the `difficulty` extra is
    not installed — the prompt then stands on the ledger alone, and says nothing false.

    **And empty for a language wordfreq has no list for**, which is the same situation
    and was not the same code. wordfreq raises `LookupError` there rather than answering
    nothing, and Aramaic is such a language: since the scripture path learned to read
    Daniel and Ezra, a reader who opens either is learning `arc`, and a conversation in
    `arc` reached this and killed the worker thread that was answering it
    (targum-internal#228). A missing list is a fact about wordfreq, not about the reader.
    """
    try:
        from wordfreq import top_n_list, zipf_frequency
    except ImportError:
        return []
    code = language.split("-")[0].lower()
    try:
        return [
            word
            for word in top_n_list(code, n * 2)
            if zipf_frequency(word, code) >= BAND_FLOOR_ZIPF
        ][:n]
    except LookupError:
        return []


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


@dataclass(frozen=True)
class Returning:
    """The reader's own words coming back into a conversation, by where they stand."""

    #: Status 1: met once and marked, not known yet.
    new: list[str]
    #: Status 2.
    learning: list[str]
    #: Status 3: nearly there.
    nearly: list[str]
    #: Known, and marked known longest ago — the ones a reader stops meeting.
    known: list[str]
    #: Phrases kept lately.
    phrases: list[str]

    def words(self) -> list[str]:
        return self.new + self.learning + self.nearly + self.known

    def __bool__(self) -> bool:
        return bool(self.words() or self.phrases)


NOTHING_RETURNING = Returning([], [], [], [], [])


def rotate(pool: list[str], want: int, seed: int) -> list[str]:
    """`want` of `pool`, starting `want` further along for each `seed` and wrapping, so
    two conversations see two slices and the ledger is walked across them. Until
    2026-09-10 the seed was the turn number, and every turn's slice was different;
    that cost the cache the whole conversation each turn (targum-internal#239)."""
    if not pool or want <= 0:
        return []
    want = min(want, len(pool))
    start = (seed * want) % len(pool)
    return [pool[(start + i) % len(pool)] for i in range(want)]


def bring_back(
    store: Store,
    person_id: int | None,
    language: str,
    now_ms: int | None = None,
    seed: int = 0,
) -> Returning:
    """The reader's words, for the conversation to carry back — the one thing the
    chat-first products never do, and the thing the research says a saved word needs.

    From the whole ledger, by status: the words met once first, then the ones being
    learnt, then the nearly known, each status a share of one reply's list and any
    share a status cannot fill passed down the line; and a few known words marked known
    longest ago, so that what was learnt stays met. Kept to the words a modern
    conversation can carry: a word saved in Judges returns only if a newspaper would use
    it. Phrases are the ones kept lately.
    """
    from ..annotate.frequency import FrequencyBands

    bands = FrequencyBands()
    modern = bands.supports(language)
    pools: dict[int, list[tuple[int, str]]] = {1: [], 2: [], 3: [], 9: []}
    for lemma, status, band, at in store.words_with_bands(person_id, language):
        if status not in pools or not lemma or band in NOT_VOCABULARY:
            continue
        if modern and bands.band(lemma, language) > MODERN_BAND:
            continue
        pools[status].append((at, lemma))
    # The learning ones newest first, so a word saved yesterday is met tomorrow; the
    # known ones oldest first, since a word ticked off last month is the one at risk.
    learning = {s: [lemma for _, lemma in sorted(pools[s], reverse=True)] for s in (1, 2, 3)}
    picked = {s: rotate(learning[s], BRING_BACK[s], seed) for s in (1, 2, 3)}
    left = sum(BRING_BACK.values()) - sum(len(got) for got in picked.values())
    for status in (1, 2, 3):
        if left <= 0:
            break
        rest = [lemma for lemma in learning[status] if lemma not in picked[status]]
        more = rotate(rest, left, seed)
        picked[status] = picked[status] + more
        left -= len(more)
    since = (now_ms if now_ms is not None else int(time.time() * 1000)) - LATELY_MS
    return Returning(
        new=picked[1],
        learning=picked[2],
        nearly=picked[3],
        known=rotate([lemma for _, lemma in sorted(pools[9])], KNOWN_BACK, seed),
        phrases=store.recent_phrases(person_id, since, limit=BRING_BACK_PHRASES),
    )


def ledger_block(
    level: Level,
    known: list[str],
    common: list[str],
    returning: Returning | None = None,
) -> str:
    """The per-reader block: the ledger, then the word lists, then what comes back."""
    parts = [describe(level)]
    if known:
        parts.append(f"The reader's known words ({len(known)}): " + " ".join(known))
    else:
        # Nobody has a ledger on their first day. Words are marked while reading, so
        # the way to a ledger is a text, and the first question is the one the research
        # notes give: what they have read, never what level they are.
        parts.append(
            "The reader has marked no words known yet. Stand on the commonest of the common "
            "words, keep every sentence short, and in your first reply ask what they have "
            "read in Hebrew so far - never what level they are - and offer them one short "
            "text to start with (suggest_next), because words are marked while reading and "
            "that is how their ledger begins."
        )
    if common:
        parts.append(f"Common words any learner meets early ({len(common)}): " + " ".join(common))
    back = returning or NOTHING_RETURNING
    if back.words():
        lines = ["The reader's own words to carry back into your Hebrew, by where they stand:"]
        if back.new:
            lines.append(
                f"- met once, not yet known ({len(back.new)}): {' '.join(back.new)}. Use each "
                "in a sentence whose meaning is clear from the rest of it; its English is on "
                'the "= " line like any word.'
            )
        if back.learning:
            lines.append(
                f"- learning ({len(back.learning)}): {' '.join(back.learning)}. Use them "
                "plainly, so they start to feel familiar."
            )
        if back.nearly:
            lines.append(
                f"- nearly known ({len(back.nearly)}): {' '.join(back.nearly)}. Use them "
                "without fuss."
            )
        if back.known:
            lines.append(
                f"- known, from a while ago ({len(back.known)}): {' '.join(back.known)}. Let "
                "them simply appear."
            )
        lines.append(
            "Bring them back where they fit naturally, a few in a reply and never all of "
            "them, and once in the conversation ask the reader to use two of the ones they "
            "are learning. Never list them, never name this as an exercise, and never say a "
            "word's status or that you are bringing anything back."
        )
        parts.append("\n".join(lines))
    if back.phrases:
        parts.append(f"Phrases they kept lately ({len(back.phrases)}): " + " | ".join(back.phrases))
    return "\n\n".join(parts)


def words_in(*texts: str) -> int:
    return sum(len(text.split()) for text in texts)


def seconds_for(words: int) -> float:
    """How long this many words take to say, at the conversational rate."""
    return max(0.0, words) / CONVERSATION_WORDS_PER_MINUTE * 60.0
