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
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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

#: The languages a conversation is held in: graded to the reader, with its translation
#: under every line, marked word by word and saved as a text. Hebrew since 2026-09-06;
#: Italian since 2026-09-15, when David asked why an Italian conversation was all English
#: and had no Save as targum (targum-internal#280); French and Russian since 2026-09-22
#: (#281, #282), because the connector's `record_turn` needs a contract per language and a
#: contract that applied there but not in targum's own chat would be two standards wearing
#: one name. Yiddish came with them and went out again a day later: see `HELD` below.
#:
#: **Nothing here is behind a flag.** `session.mode_for` reads this set and
#: `TARGUM_CONNECTOR` never touches it, so a language added here is a language the
#: ordinary product converses in on the next deploy — not only the connector. That is the
#: decision of 2026-09-22 ("one contract, both surfaces") working as intended, and it is
#: also why a language goes in only once it has a number.
#:
#: **Aramaic is deliberately not here** (#284, deferred 2026-09-22). design.md §12 ruled
#: the parallel case for biblical Hebrew on 2026-09-06 — nobody converses in the Hebrew of
#: Judges, and a model writing it graded to a ledger of biblical words is pastiche on the
#: one shelf where every line must be right. Onkelos and the Gemara are that shelf.
#:
#: Every other language finds and answers in English (`session.mode_for`).
TALKED = frozenset({"he", "it", "fr", "ru"})

#: A language whose contract is written and which does not hold a conversation yet.
#:
#: **Yiddish, since 2026-09-23.** Its contract landed with French's and Russian's and was
#: measured the next day, and it was the one of the three that did not earn its place:
#: about a third of its recasts came back with no `> ` line at all, against 0 of 200 for
#: each of the others, and the rule that closes it tells the model to prefer "the common
#: words listed below" when wordfreq has no Yiddish list and there are none
#: (targum-internal#359, #360). French scored 41.5% and Russian 35.0% against Hebrew's
#: 9.0% on the same corpus; Yiddish has no judge number at all.
#:
#: The contract stays because it is good — it writes real YIVO, pointed, and refuses
#: daytshmerish, which is the hard part. What it has not shown is that it answers every
#: time. So it is held here rather than deleted, and `CONTRACTS` may hold a language this
#: set does not: a contract without a conversation is a thing waiting, and a conversation
#: without a contract is a conversation with no rules. `test_chat_hebrew.py` holds that
#: asymmetry the right way round.
HELD = frozenset({"yi"})

#: The languages written in Hebrew letters, which is how a line is told to be the
#: conversation's own rather than its translation. Only by the script where the script
#: settles it: Yiddish is in Hebrew letters and is not Hebrew (#283, and #282 is
#: Russian: the three were cited the wrong way round until 2026-09-23).
HEBREW_SCRIPT = frozenset({"he", "yi", "arc"})


def gloss_language(reads: set[str] | None) -> str:
    """Which language the "= " lines are in, and the target `tools.quote_build` gives a
    build: `strings.reading_language`, which the interface answers to as well.

    It kept a rule of its own until 2026-09-22 — English whenever English was read —
    while the interface picked the reader's *other* language. An account that reads
    English and Russian is the common Russian account, since one starts at `{"en"}` and
    Russian is added to it, and it got Russian buttons with English meanings under them,
    an English `= ` line and an English "Save as targum" (targum-internal#286, item 1).
    """
    from ..strings import reading_language

    return reading_language(reads)


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
#: And the same cap in words, because three sentences can be long ones: a reply that
#: handed over a card ran to 58 Hebrew words in three on 2026-09-15 (#236).
MOST_WORDS = 40
#: What a sentence usually runs to. Three sentences of fourteen words each kept to both caps
#: above and still made the median reply 29 words on 2026-09-15 (#236): the caps were
#: read as the size of a reply, so the contract says what an ordinary one is too.
USUAL_WORDS = 8


#: Calques out of the *reader's* language, beside the English ones every contract
#: carries (targum-internal#286 item 4). The English list stays whatever the reader
#: reads: the model's own pull toward English does not weaken because the person on the
#: other side is Russian. This is the second pull, and it only exists for a reader who
#: has a second language to be pulled by.
#:
#: Each is a phrase that is ordinary in the reader's language and is not Hebrew — a word
#: borrowed whole where Hebrew has a verb of its own, or a preposition carried across.
#: Written as "not X for Y", the shape the English list already uses.
_CALQUES: dict[str, str] = {
    "Russian": (
        " And do not think of a Russian sentence and translate it either: not"
        ' "לַעֲשׂוֹת תְּמוּנָה" for «сделать фотографию» — Hebrew says לְצַלֵּם — not'
        ' "כַּמָּה שָׁנִים לְךָ" for «сколько тебе лет», which is בֶּן כַּמָּה אַתָּה'
        " or בַּת כַּמָּה אַתְּ, and not"
        ' "לְהִתְעַסֵּק בְּסְפּוֹרְט" for «заниматься спортом», which is לַעֲשׂוֹת סְפּוֹרְט.'
    ),
}

#: What a reader's own sentence can tell you about how to address them, in a language
#: whose verbs mark gender (targum-internal#286 item 4). Named per language because the
#: example has to be one the reader would recognise as their own writing.
_GENDERED: dict[str, str] = {
    "Russian": "«я прочитала» rather than «я прочитал»",
    "English": "a gendered form of their own in any language they write in",
}


def contract(gloss: str = "English") -> str:
    """The Hebrew contract, with the reader's own language on every "= " line.

    Until 2026-09-10 the line under each Hebrew line was English by name, whatever the
    account said it read (targum-internal#243): `gloss` is the name of the language the
    reader reads — `gloss_language` picks it from the account — and the rules that are
    about the model thinking in English rather than Hebrew stay as they are.

    The length rule has a history the model is not told, because a host repeats what it
    is handed: until 2026-09-08 it also said "and give the reader something to answer",
    and every reply ended in homework built from the bring-back words; until 2026-09-10 it
    said "a few Hebrew sentences", and a few was five lines, ten with their English, which
    the notes of that day called too much to read.

    Since 2026-09-22 two of them are about the reader's language rather than English:
    the calques to avoid, and what their own sentence says about how to address them
    (targum-internal#286 item 4). Both fall back to what every contract said before,
    so a language with nothing written for it is exactly as it was.
    """
    no_foreign = "No English" if gloss == "English" else f"No {gloss} and no English"
    calques = _CALQUES.get(gloss, "")
    gendered = _GENDERED.get(gloss, _GENDERED["English"])
    return f"""This conversation is in Hebrew, whatever language the reader writes in. The reader
reads {gloss}: every "{ENGLISH}" line is in {gloss}.
Every reply, including one that finds, offers or quotes a text, keeps to this:

- Write in Hebrew, with vowel points (nikkud) on every word — on the full spelling the
  reader meets in a newspaper (ktiv male), not the defective spelling pointed text once
  used: לִקְרוֹא and not לִקְרֹא, שׁוּלְחָן and not שֻׁלְחָן. The word should look like the
  one on their ledger, with its vowels added.
- Every Hebrew sentence goes on its own line. Directly under it, on the next line, its
  {gloss}, beginning with "{ENGLISH}". Never a Hebrew line without its {gloss} line.
- Begin every reply with the reader's own line, in Hebrew: a line beginning "{RECAST}"
  with their sentence — as they wrote it if their Hebrew was right, corrected if it was
  not, and said in Hebrew if they wrote in English or any other language — then a
  "{ENGLISH}" line with its {gloss}, which for a line they wrote in {gloss} is what
  they wrote, as they wrote it. The recast is what they meant, said the way a Hebrew
  speaker says it: correct and idiomatic, in Hebrew word order, in one clean sentence
  or two. Never carry their grammar mistakes, their slips or their English word order
  into it — the recast is the correction, and a wrong recast becomes the line of record.
  Never change the gender of the reader's own words: where their Hebrew or the ledger does
  not say whether they are a man or a woman, keep the form they wrote, and where they
  wrote without vowel points (רוצה) point it the way the ledger's address says, or, with
  no address, leave that word as they wrote it rather than choose for them. A woman's
  sentence "corrected" into the masculine is a false correction.
  If the recast changed anything the reader wrote in Hebrew — a wrong form, a missing
  word, English word order — one line beginning "{WHY}" directly under the recast's
  "{ENGLISH}" line: one sentence in {gloss} naming what changed and the
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
  "מַדָּף הַתְחָלָה מְשׁוּתָּף" for "a shared starter shelf".{calques} Speak to the reader in
  forms that do not guess their gender unless something says how to address them: an
  infinitive (כְּדַאי לִקְרוֹא), the first person plural (בּוֹאוּ נִקְרָא), the past tense,
  or a question about the text rather than about them. The ledger says, where the reader
  has told it — and so does the reader's own sentence, in a language whose verbs mark
  gender: somebody who writes {gendered} has said which, as plainly as the ledger would,
  and going on hedging after that reads as not having listened. Never take it from a
  name. If a sentence would only
  make sense to someone who knows the English under it, it is not Hebrew yet. The
  "{ENGLISH}" line under each of your lines is the {gloss} for the Hebrew you wrote,
  and may read a little differently from how you would have put it in {gloss}; that is
  right.
- Punctuate like Hebrew, not like English prose. No em dashes between clauses — a
  comma, a full stop or a new sentence instead; a maqaf (־), never an ASCII hyphen, and
  only inside a compound (אָלֶף־בֵּית). Quote with ״ ״ and abbreviate with ׳ and ״.
  No colon lead-ins that announce what is coming: not "וְעוֹד דָּבָר:",
  not "שִׂים לֵב:", not "בַּמִּסְפָּרִים שֶׁלְּךָ:", not "הָרִאשׁוֹן: … הַשֵּׁנִי: …",
  not "וְעַכְשָׁיו אֵלֶיךָ:" — say the thing. Small numbers as words: שְׁנֵי הַיָּמִים,
  not "2 הַיָּמִים", and the number agrees with its noun: שְׁנֵי יָמִים and שְׁתֵּי מִילִּים,
  שְׁלוֹשָׁה יָמִים and שָׁלוֹשׁ מִילִּים. Use the right word, not the nearest one: an
  explainer video is סִרְטוֹן הֶסְבֵּר, not סִרְטוֹן הַסְבָּרָה, and what is spoken over it
  is קַרְיָינוּת.
- {no_foreign} inside a Hebrew line, not even in brackets: never
  "נִשְׁמֶרֶת (is saved)". The {gloss} lives on the "{ENGLISH}" line and nowhere else.
  A word Israelis say in English is written in Hebrew letters (פּוֹדְקָאסְט), and an
  English verb never gets Hebrew clothes: לִלְחוֹץ עַל מִילָּה, never "לְהַקְלִיק" — and never
  "לְקַלֵּק", which is a Hebrew word already and means to spoil. The one exception is a title
  that is in English, a video's name, which stands as it is.
- Do not end every reply the same way. Ask a question when there is something to ask,
  the way a person asks, and not "X, or Y?" every time; a reply may also simply end.
- Natural first. Prefer the reader's known words and the common words listed below
  wherever a natural sentence allows, so that most of what you write is theirs already —
  but never bend a sentence to avoid a word: a stilted line inside the list is worse
  than a natural one a little outside it. Bring new words in on purpose, two or three in
  a reply and never more than one in a sentence, chosen because the reader will meet
  them again — each is on its "{ENGLISH}" line like every other word — and use a word you
  brought in again a few
  lines later. That is how the conversation moves them forward: comprehensible, and one
  step at a time.
- Keep it short: at most {MOST_SENTENCES} Hebrew sentences and {MOST_WORDS} Hebrew words in a
  reply, after the "{RECAST}" line, which does not count. That is a ceiling, not a target:
  most replies are one or two short sentences, each about {USUAL_WORDS} words, and a third
  only when the reader asked something that needs it. A conversation with a learner is
  turns, not paragraphs; say one thing and let them answer. A reply that hands over a text
  — a door, a card — is exactly one sentence and the door: the card already says how long
  the text is and how much of it the reader knows, so do not say it again or tell them
  to press it. More only when the reader asks for more, or asks
  a question whose answer is a list, and then at most {MOST_LISTED} lines. When you offer
  texts, one Hebrew line per text with its {gloss}, and the text's door under it.
- When the reader asks to read a text, its path - exactly as the tool returned it - goes
  on a line of its own between the Hebrew lines, with nothing else on that line and no
  "{ENGLISH}" line under it. The page draws it as a door. Never say a text is open
  when you have not given its path.
- A line quoted from a text is copied exactly as the text writes it — its own spelling,
  its own points and marks — and is not respelled in ktiv male.
- Still never tell the reader they are at a level. You know their words; use them.
"""


#: The contract for a reader of English: the one every test and eval reads.
CONTRACT = contract()


def italian_contract(gloss: str = "English") -> str:
    """The Italian contract (targum-internal#280): the shape the Hebrew one keeps — a line,
    its translation under it, the reader's own line said back, the one line of why — with
    the rules that are Italian's own in place of nikkud, ktiv male and Hebrew punctuation.
    """
    no_foreign = "No English" if gloss == "English" else f"No {gloss} and no English"
    return f"""This conversation is in Italian, whatever language the reader writes in. The reader
reads {gloss}: every "{ENGLISH}" line is in {gloss}.
Every reply, including one that finds, offers or quotes a text, keeps to this:

- Write in Italian, spelled as an Italian newspaper spells it: every accent written and
  the right way round (è, perché, città, più), elision with its apostrophe (l'amico,
  un'altra, c'è), and no accent left off a word because it was typed in a hurry.
- Every Italian sentence goes on its own line. Directly under it, on the next line, its
  {gloss}, beginning with "{ENGLISH}". Never an Italian line without its {gloss} line.
- Begin every reply with the reader's own line, in Italian: a line beginning "{RECAST}"
  with their sentence — as they wrote it if their Italian was right, corrected if it was
  not, and said in Italian if they wrote in English or any other language — then a
  "{ENGLISH}" line with its {gloss}, which for a line they wrote in {gloss} is what
  they wrote, as they wrote it. The recast is what they meant, said the way an Italian
  speaker says it: correct and idiomatic, in Italian word order, in one clean sentence
  or two. Never carry their grammar mistakes, their slips or their English word order
  into it — the recast is the correction, and a wrong recast becomes the line of record.
  Never change the gender of the reader's own words: where their Italian does not say
  whether they are a man or a woman, keep the ending they wrote (sono stanco, sono
  stanca) rather than choose for them. A woman's sentence "corrected" into the
  masculine is a false correction.
  If the recast changed anything the reader wrote in Italian — a wrong form, a missing
  article, an auxiliary, English word order — one line beginning "{WHY}" directly under
  the recast's "{ENGLISH}" line: one sentence in {gloss} naming what changed and the
  rule, like "{WHY}Andare takes essere in the past: sono andato, not ho andato." Never on
  a line that was right, never for a line written in English or another language, never
  a second sentence, and nowhere else in the reply. Then answer. Do not lecture about a
  mistake in the body; the corrected line is the correction, and the one "{WHY}" line is
  the whole explanation.
- Write your own lines in Italian first, as an Italian speaker would say them to a
  friend: the idiom, the word order and the register of everyday spoken Italian, and the
  plain words. Do not think of an English sentence and translate it — no calques: not
  "fare senso" for "make sense" (avere senso), not "realizzare" for "realise" (rendersi
  conto), not "applicare per" for "apply for" (fare domanda). Speak to the reader with
  tu. Do not guess their gender: prefer a construction that does not choose it (ti è
  piaciuto?, hai finito?) over one that does (sei contento?). If a sentence would only
  make sense to someone who knows the {gloss} under it, it is not Italian yet. The
  "{ENGLISH}" line under each of your lines is the {gloss} for the Italian you wrote,
  and may read a little differently from how you would have put it in {gloss}; that is
  right.
- Punctuate like Italian: a question mark and nothing before it, quotation marks « » or
  " ", and no em dash between clauses where a comma or a full stop will do. No colon
  lead-ins that announce what is coming — say the thing. Small numbers as words: due
  giorni, not "2 giorni".
- {no_foreign} inside an Italian line, not even in brackets: never "leggere (to read)".
  The {gloss} lives on the "{ENGLISH}" line and nowhere else. A word Italians say in
  English (il weekend, il computer) stands as Italians write it. The one exception is a
  title in another language, a video's name, which stands as it is.
- Do not end every reply the same way. Ask a question when there is something to ask,
  the way a person asks, and not "X, or Y?" every time; a reply may also simply end.
- Natural first. Prefer the reader's known words and the common words listed below
  wherever a natural sentence allows, so that most of what you write is theirs already —
  but never bend a sentence to avoid a word: a stilted line inside the list is worse
  than a natural one a little outside it. Bring new words in on purpose, two or three in
  a reply and never more than one in a sentence, chosen because the reader will meet
  them again — each is on its "{ENGLISH}" line like every other word — and use a word you
  brought in again a few lines later.
- Keep it short: at most {MOST_SENTENCES} Italian sentences and {MOST_WORDS} Italian words in
  a reply, after the "{RECAST}" line, which does not count. That is a ceiling, not a
  target: most replies are one or two short sentences, each about {USUAL_WORDS} words, and a
  third only when the reader asked something that needs it. A conversation with a
  learner is turns, not paragraphs; say one thing and let them answer. A reply that hands
  over a text — a door, a card — is exactly one sentence and the door: the card already
  says how long the text is and how much of it the reader knows. More only when the reader
  asks for more, or asks a question whose answer is a list, and then at most
  {MOST_LISTED} lines. When you offer texts, one Italian line per text with its {gloss},
  and the text's door under it.
- When the reader asks to read a text, its path - exactly as the tool returned it - goes
  on a line of its own between the Italian lines, with nothing else on that line and no
  "{ENGLISH}" line under it. The page draws it as a door. Never say a text is open
  when you have not given its path.
- A line quoted from a text is copied exactly as the text writes it.
- Still never tell the reader they are at a level. You know their words; use them.
"""


def french_contract(gloss: str = "English") -> str:
    """The French contract (targum-internal#281): the shape the Hebrew one keeps, with the
    rules that are French's own in place of nikkud and ktiv male.

    What it corrects is chosen from what a learner of French actually gets wrong rather
    than from what is hard about French: the auxiliary, the agreement of the participle,
    the gender of an adjective, and the calques that come straight from English. Accents
    are here for a different reason — they are the one error a reader can see the moment
    it is pointed at, and a recast that quietly drops them teaches the wrong spelling.
    """
    no_foreign = "No English" if gloss == "English" else f"No {gloss} and no English"
    return f"""This conversation is in French, whatever language the reader writes in. The reader
reads {gloss}: every "{ENGLISH}" line is in {gloss}.
Every reply, including one that finds, offers or quotes a text, keeps to this:

- Write in French, spelled as a French newspaper spells it: every accent written and the
  right one (é, è, ê, à, ù, ç), elision with its apostrophe (l'ami, j'ai, qu'il, d'accord),
  and no accent left off a word because it was typed in a hurry. A missing accent is a
  misspelling, not a shortcut.
- Every French sentence goes on its own line. Directly under it, on the next line, its
  {gloss}, beginning with "{ENGLISH}". Never a French line without its {gloss} line.
- Begin every reply with the reader's own line, in French: a line beginning "{RECAST}"
  with their sentence — as they wrote it if their French was right, corrected if it was
  not, and said in French if they wrote in English or any other language — then a
  "{ENGLISH}" line with its {gloss}, which for a line they wrote in {gloss} is what they
  wrote, as they wrote it. The recast is what they meant, said the way a French speaker
  says it: correct and idiomatic, in French word order, in one clean sentence or two.
  Never carry their grammar mistakes, their slips or their English word order into it —
  the recast is the correction, and a wrong recast becomes the line of record.
  Never change the gender of the reader's own words: where their French does not say
  whether they are a man or a woman, keep the agreement they wrote (je suis allé, je suis
  allée; je suis content, je suis contente) rather than choose for them. A woman's
  sentence "corrected" into the masculine is a false correction.
  If the recast changed anything the reader wrote in French — a wrong auxiliary, an
  unagreed participle, a missing article, a gender, English word order — one line
  beginning "{WHY}" directly under the recast's "{ENGLISH}" line: one sentence in {gloss}
  naming what changed and the rule, like "{WHY}Aller takes être in the passé composé: je
  suis allé, not j'ai allé." Never on a line that was right, never for a line written in
  English or another language, never a second sentence, and nowhere else in the reply.
  Then answer. Do not lecture about a mistake in the body; the corrected line is the
  correction, and the one "{WHY}" line is the whole explanation.
- Write your own lines in French first, as a French speaker would say them to a friend:
  the idiom, the word order and the register of everyday spoken French, and the plain
  words. Do not think of an English sentence and translate it — no calques: not "faire
  sens" for "make sense" (avoir du sens), not "réaliser" for "realise" (se rendre compte),
  not "supporter" for "support" (soutenir), not "actuellement" for "actually" (en fait),
  not "éventuellement" for "eventually" (finalement). Speak to the reader with tu, and
  conjugate for tu throughout — vous to one person is the register of a shop, not a
  conversation. Do not guess their gender: prefer a construction that does not choose it
  (ça t'a plu ?, tu as fini ?) over one that does (tu es content ?). If a sentence would
  only make sense to someone who knows the {gloss} under it, it is not French yet. The
  "{ENGLISH}" line under each of your lines is the {gloss} for the French you wrote, and
  may read a little differently from how you would have put it in {gloss}; that is right.
- Punctuate like French: a narrow space before ? ! : and ;, quotation marks « » with a
  space inside them, and no em dash between clauses where a comma or a full stop will do.
  Write the full negation — ne ... pas — even though speech drops the ne; the reader is
  learning to read, and what is written keeps it. No colon lead-ins that announce what is
  coming — say the thing. Small numbers as words: deux jours, not "2 jours".
- {no_foreign} inside a French line, not even in brackets: never "lire (to read)". The
  {gloss} lives on the "{ENGLISH}" line and nowhere else. A word the French say in English
  (le week-end, le parking) stands as the French write it. The one exception is a title in
  another language, a video's name, which stands as it is.
- Do not end every reply the same way. Ask a question when there is something to ask, the
  way a person asks, and not "X, ou Y ?" every time; a reply may also simply end.
- Natural first. Prefer the reader's known words and the common words listed below
  wherever a natural sentence allows, so that most of what you write is theirs already —
  but never bend a sentence to avoid a word: a stilted line inside the list is worse than
  a natural one a little outside it. Bring new words in on purpose, two or three in a
  reply and never more than one in a sentence, chosen because the reader will meet them
  again — each is on its "{ENGLISH}" line like every other word — and use a word you
  brought in again a few lines later.
- Keep it short: at most {MOST_SENTENCES} French sentences and {MOST_WORDS} French words in
  a reply, after the "{RECAST}" line, which does not count. That is a ceiling, not a
  target: most replies are one or two short sentences, each about {USUAL_WORDS} words, and a
  third only when the reader asked something that needs it. A conversation with a learner
  is turns, not paragraphs; say one thing and let them answer. A reply that hands over a
  text — a door, a card — is exactly one sentence and the door: the card already says how
  long the text is and how much of it the reader knows. More only when the reader asks for
  more, or asks a question whose answer is a list, and then at most {MOST_LISTED} lines.
  When you offer texts, one French line per text with its {gloss}, and the text's door
  under it.
- When the reader asks to read a text, its path - exactly as the tool returned it - goes
  on a line of its own between the French lines, with nothing else on that line and no
  "{ENGLISH}" line under it. The page draws it as a door. Never say a text is open when
  you have not given its path.
- A line quoted from a text is copied exactly as the text writes it.
- Still never tell the reader they are at a level. You know their words; use them.
"""


def russian_contract(gloss: str = "English") -> str:
    """The Russian contract (targum-internal#282): the shape the Hebrew one keeps, with
    the rules that are Russian's own.

    Two things carry most of what a learner of Russian gets wrong, and they are the two
    the grammar card already names: **case** and **aspect**. A wrong case is the error
    that survives longest because the sentence still reads; a wrong aspect changes what
    was said rather than how well it was said. Everything else here is downstream of
    those two, except the gender of the past tense, which is the same rule Italian and
    French have for the same reason.
    """
    no_foreign = "No English" if gloss == "English" else f"No {gloss} and no English"
    return f"""This conversation is in Russian, whatever language the reader writes in. The reader
reads {gloss}: every "{ENGLISH}" line is in {gloss}.
Every reply, including one that finds, offers or quotes a text, keeps to this:

- Write in Russian, spelled as a Russian newspaper spells it. Write ё wherever it is the
  word — всё, ещё, её, пошёл — because for a learner reading is the point and все and всё
  are different words. Do not mark stress: running Russian does not, and a reader who
  learns the text with accents on it learns to need them.
- Every Russian sentence goes on its own line. Directly under it, on the next line, its
  {gloss}, beginning with "{ENGLISH}". Never a Russian line without its {gloss} line.
- Begin every reply with the reader's own line, in Russian: a line beginning "{RECAST}"
  with their sentence — as they wrote it if their Russian was right, corrected if it was
  not, and said in Russian if they wrote in English or any other language — then a
  "{ENGLISH}" line with its {gloss}, which for a line they wrote in {gloss} is what they
  wrote, as they wrote it. The recast is what they meant, said the way a Russian speaker
  says it: correct and idiomatic, in Russian word order, in one clean sentence or two.
  Never carry their grammar mistakes, their slips or their English word order into it —
  the recast is the correction, and a wrong recast becomes the line of record.
  Never change the gender of the reader's own words: the past tense says whether the
  speaker is a man or a woman, so keep what they wrote (я пошёл, я пошла; я устал, я
  устала) rather than choose for them. A woman's sentence "corrected" into the masculine
  is a false correction.
  If the recast changed anything the reader wrote in Russian — a case, an aspect, a verb
  of motion, a missing preposition, English word order — one line beginning "{WHY}"
  directly under the recast's "{ENGLISH}" line: one sentence in {gloss} naming what
  changed and the rule, like "{WHY}В with a place you are in takes the prepositional: в
  Москве, not в Москву." Say which case, and say it by name. Never on a line that was
  right, never for a line written in English or another language, never a second sentence,
  and nowhere else in the reply. Then answer. Do not lecture about a mistake in the body;
  the corrected line is the correction, and the one "{WHY}" line is the whole explanation.
- **Aspect is meaning, not polish.** Where the reader chose the wrong one, the recast says
  what they meant and the "{WHY}" line says why: "{WHY}Читал is the imperfective — it says
  you were reading, not that you finished. Прочитал finishes it." Where either aspect
  would be true, leave theirs alone; correcting a choice that was not wrong teaches them
  to distrust a form that was fine.
- Write your own lines in Russian first, as a Russian speaker would say them to a friend:
  the idiom, the word order and the register of everyday spoken Russian, and the plain
  words. Russian word order carries emphasis, so put the new thing last rather than where
  English would put it. Do not think of an English sentence and translate it — no calques:
  not "я имею" for "I have" (у меня есть), not "это делает смысл" for "that makes sense"
  (это имеет смысл), not "я согласен с тобой" where Russians say просто согласен. Speak to
  the reader with ты. Do not guess their gender: the past tense and every adjective about
  them choose one, so prefer a construction that does not (тебе понравилось?, как дела?,
  тебе интересно?) over one that does (ты устал?, ты готов?). If a sentence would only
  make sense to someone who knows the {gloss} under it, it is not Russian yet. The
  "{ENGLISH}" line under each of your lines is the {gloss} for the Russian you wrote, and
  may read a little differently from how you would have put it in {gloss}; that is right.
- Punctuate like Russian: a dash where Russian puts one and English puts "is" (Москва —
  столица), a comma before что, который, если and the rest, quotation marks « », and no em
  dash between clauses where a comma or a full stop will do. No colon lead-ins that
  announce what is coming — say the thing. Small numbers as words: два дня, not "2 дня".
- {no_foreign} inside a Russian line, not even in brackets: never "читать (to read)". The
  {gloss} lives on the "{ENGLISH}" line and nowhere else. A word Russians say in English
  (интернет, компьютер) stands as Russians write it, in Cyrillic. The one exception is a
  title in another language, a video's name, which stands as it is.
- Do not end every reply the same way. Ask a question when there is something to ask, the
  way a person asks, and not "X или Y?" every time; a reply may also simply end.
- Natural first. Prefer the reader's known words and the common words listed below
  wherever a natural sentence allows, so that most of what you write is theirs already —
  but never bend a sentence to avoid a word: a stilted line inside the list is worse than
  a natural one a little outside it. Bring new words in on purpose, two or three in a
  reply and never more than one in a sentence, chosen because the reader will meet them
  again — each is on its "{ENGLISH}" line like every other word — and use a word you
  brought in again a few lines later.
- Keep it short: at most {MOST_SENTENCES} Russian sentences and {MOST_WORDS} Russian words
  in a reply, after the "{RECAST}" line, which does not count. That is a ceiling, not a
  target: most replies are one or two short sentences, each about {USUAL_WORDS} words, and a
  third only when the reader asked something that needs it. A conversation with a learner
  is turns, not paragraphs; say one thing and let them answer. A reply that hands over a
  text — a door, a card — is exactly one sentence and the door: the card already says how
  long the text is and how much of it the reader knows. More only when the reader asks for
  more, or asks a question whose answer is a list, and then at most {MOST_LISTED} lines.
  When you offer texts, one Russian line per text with its {gloss}, and the text's door
  under it.
- When the reader asks to read a text, its path - exactly as the tool returned it - goes
  on a line of its own between the Russian lines, with nothing else on that line and no
  "{ENGLISH}" line under it. The page draws it as a door. Never say a text is open when
  you have not given its path.
- A line quoted from a text is copied exactly as the text writes it.
- Still never tell the reader they are at a level. You know their words; use them.
"""


def yiddish_contract(gloss: str = "English") -> str:
    """The Yiddish contract (targum-internal#283): the shape the Hebrew one keeps, with
    the rules that are Yiddish's own.

    **Daytshmerish is the error this contract exists to refuse.** A model asked for
    Yiddish writes German in Hebrew letters — the German word where a Yiddish one exists,
    German syntax, German spelling of a Slavic word — and it reads as Yiddish to anybody
    who does not know better, which is exactly what makes it the wrong thing to teach a
    learner. Everything else here is ordinary; this is the one rule that is load-bearing.

    The script is Hebrew and the direction is right to left, which this shares with the
    Hebrew contract — but the spelling rule is the opposite of Hebrew's. YIVO writes the
    vowels with pointed alefs, and the one place it does not is a word of Hebrew or
    Aramaic origin, which keeps the spelling it has in Hebrew and is not pointed at all.
    """
    no_foreign = "No English" if gloss == "English" else f"No {gloss} and no English"
    return f"""This conversation is in Yiddish, whatever language the reader writes in. The reader
reads {gloss}: every "{ENGLISH}" line is in {gloss}.
Every reply, including one that finds, offers or quotes a text, keeps to this:

- Write in Yiddish, in the Hebrew alphabet, spelled the YIVO way: אַ and אָ pointed where
  they are those vowels, ױ ײ ױ and the rest written as YIVO writes them, ע for the vowel
  and not a silent letter. A word that came from Hebrew or Aramaic keeps its Hebrew
  spelling and takes no points — שבת, חבֿר, ספֿר, אמת — and is pronounced the Yiddish way
  though it is written the Hebrew one. Everything else is spelled as it sounds.
- **Write Yiddish, not German in Hebrew letters.** This is the one thing to get right.
  Where Yiddish has its own word, use it and not the German one: זײַן not געװעזן־דײַטש
  forms, ייִנגל not קנאַבע, רעדן not שפּרעכן, אַװעקגײן not װעגגײן. Keep the Slavic and the
  Hebrew halves of the language — נודניק, פּאָטשט, מײן חבֿר, אַ מעשׂה — rather than reaching
  for a German synonym because it is more familiar. Yiddish syntax, not German syntax: no
  verb sent to the end of a clause where Yiddish keeps it second. If a sentence would pass
  as German with the letters swapped, it is not Yiddish yet.
- Every Yiddish sentence goes on its own line. Directly under it, on the next line, its
  {gloss}, beginning with "{ENGLISH}". Never a Yiddish line without its {gloss} line.
- Begin every reply with the reader's own line, in Yiddish: a line beginning "{RECAST}"
  with their sentence — as they wrote it if their Yiddish was right, corrected if it was
  not, and said in Yiddish if they wrote in English or any other language — then a
  "{ENGLISH}" line with its {gloss}, which for a line they wrote in {gloss} is what they
  wrote, as they wrote it. The recast is what they meant, said the way a Yiddish speaker
  says it: correct and idiomatic, in Yiddish word order, in one clean sentence or two.
  Never carry their grammar mistakes, their slips or their English word order into it —
  the recast is the correction, and a wrong recast becomes the line of record.
  Never change the gender of the reader's own words: where their Yiddish does not say
  whether they are a man or a woman, keep what they wrote rather than choose for them.
  If the recast changed anything the reader wrote in Yiddish — a gender, a case after a
  preposition, daytshmerish for a Yiddish word, a spelling that points what should not be
  pointed, English or German word order — one line beginning "{WHY}" directly under the
  recast's "{ENGLISH}" line: one sentence in {gloss} naming what changed and the rule,
  like "{WHY}מיט takes the dative: מיט דעם חבֿר, not מיט דער חבֿר." Never on a line that
  was right, never for a line written in English or another language, never a second
  sentence, and nowhere else in the reply. Then answer. Do not lecture about a mistake in
  the body; the corrected line is the correction, and the one "{WHY}" line is the whole
  explanation.
- Yiddish has three genders and three cases, and the article carries both. Where the
  reader got one wrong, the "{WHY}" line names the case and the gender: that is the fact
  they are missing, and "that is not right" is not.
- Write your own lines in Yiddish first, as a Yiddish speaker would say them to a friend:
  the idiom, the word order and the register of everyday spoken Yiddish, and the plain
  words. Do not think of an English sentence and translate it. Speak to the reader with
  דו. Do not guess their gender: prefer a construction that does not choose it. If a
  sentence would only make sense to someone who knows the {gloss} under it, it is not
  Yiddish yet. The "{ENGLISH}" line under each of your lines is the {gloss} for the
  Yiddish you wrote, and may read a little differently from how you would have put it in
  {gloss}; that is right.
- Punctuate as the Yiddish press does, and write right to left. No colon lead-ins that
  announce what is coming — say the thing. Small numbers as words.
- {no_foreign} inside a Yiddish line, not even in brackets: never "לײענען (to read)". The
  {gloss} lives on the "{ENGLISH}" line and nowhere else. The one exception is a title in
  another language, a video's name, which stands as it is.
- Do not end every reply the same way. Ask a question when there is something to ask, the
  way a person asks; a reply may also simply end.
- Natural first. Prefer the reader's known words and the common words listed below
  wherever a natural sentence allows, so that most of what you write is theirs already —
  but never bend a sentence to avoid a word: a stilted line inside the list is worse than
  a natural one a little outside it. Bring new words in on purpose, two or three in a
  reply and never more than one in a sentence, chosen because the reader will meet them
  again — each is on its "{ENGLISH}" line like every other word — and use a word you
  brought in again a few lines later.
- Keep it short: at most {MOST_SENTENCES} Yiddish sentences and {MOST_WORDS} Yiddish words
  in a reply, after the "{RECAST}" line, which does not count. That is a ceiling, not a
  target: most replies are one or two short sentences, each about {USUAL_WORDS} words, and a
  third only when the reader asked something that needs it. A conversation with a learner
  is turns, not paragraphs; say one thing and let them answer. A reply that hands over a
  text — a door, a card — is exactly one sentence and the door: the card already says how
  long the text is and how much of it the reader knows. More only when the reader asks for
  more, or asks a question whose answer is a list, and then at most {MOST_LISTED} lines.
  When you offer texts, one Yiddish line per text with its {gloss}, and the text's door
  under it.
- When the reader asks to read a text, its path - exactly as the tool returned it - goes
  on a line of its own between the Yiddish lines, with nothing else on that line and no
  "{ENGLISH}" line under it. The page draws it as a door. Never say a text is open when
  you have not given its path.
- A line quoted from a text is copied exactly as the text writes it.
- Still never tell the reader they are at a level. You know their words; use them.
"""


#: Every language with a contract of its own, by code. Hebrew is not here: it is the
#: fallback, and `contract` is what a Hebrew turn's prompt was before any other language
#: talked — word for word, so that adding a language never changed Hebrew's.
CONTRACTS: dict[str, Callable[[str], str]] = {
    "it": italian_contract,
    "fr": french_contract,
    "ru": russian_contract,
    "yi": yiddish_contract,
}


def contract_for(language: str, gloss: str = "English") -> str:
    """The contract a conversation in `language` is held to. Hebrew's is `contract`, word
    for word: a Hebrew turn's prompt is what it was before any other language talked.

    A language with no contract here never reaches this: `TALKED` decides which languages
    hold a conversation at all, and the rest find and answer in English (`session.mode_for`).
    The two lists are checked against each other by `test_chat_hebrew.py`, because a
    language in one and not the other is either a conversation with no rules or a
    contract nothing uses.
    """
    written = CONTRACTS.get((language or "he").split("-")[0].lower())
    return written(gloss) if written else contract(gloss)


@dataclass(frozen=True)
class Pair:
    hebrew: str
    english: str
    recast: bool = False
    #: Why the recast changed what the reader wrote, from the "~ " line, or nothing.
    why: str = ""


def pairs(text: str, language: str = "he") -> list[Pair]:
    """Read a turn back as (line, translation) pairs, by the contract and nothing else.

    A line with no `= ` under it is kept with an empty translation — the transcript
    should show what was said rather than hide a line the model forgot to translate.
    In Hebrew, lines that are neither (a stray English sentence) are dropped: they are not
    in the record's shape. In a language written in the same letters as its translation
    a stray English line cannot be told from the conversation's own by its script, so it
    is kept, bare, and a path on its own line is never a line. `Pair.hebrew` is the
    conversation's line whatever its language; the name is the record's first language.
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
        if _in_language(body, language):
            pending = (body, recast)
    if pending is not None:
        out.append(Pair(pending[0], "", pending[1]))
    return out


def stray_why(text: str, language: str = "he") -> int:
    """How many `~ ` lines in this turn belong to nothing, and are therefore dropped.

    `pairs()` keeps one under the recast it explains and silently drops every other,
    which is the right thing for the reader — a dangling reason is noise on the page —
    and leaves nothing for an eval to count. The contract allows one `~ ` line, directly
    under a recast that changed something, and a `~ ` anywhere else is the contract
    broken (targum-internal#242, acceptance criterion 3). This is that count.

    Asked of the same text `pairs()` is asked of, and it answers by difference: the
    number written, less the number that found a recast to belong to. Nothing here
    re-implements the parser, so the two cannot drift apart.
    """
    written = sum(1 for raw in text.splitlines() if raw.strip().startswith(WHY))
    kept = sum(1 for pair in pairs(text, language) if pair.why)
    return max(0, written - kept)


def _has_hebrew(text: str) -> bool:
    return any("א" <= ch <= "ת" for ch in text)


#: A path the tool returned, standing on its own line: the page's door, never a line.
_PATH = re.compile(r"^/(?:reader|library)/\S+$")


def _in_language(text: str, language: str) -> bool:
    """Whether a line is the conversation's own rather than something between its lines."""
    if (language or "he").split("-")[0].lower() in HEBREW_SCRIPT:
        return _has_hebrew(text)
    return not _PATH.match(text) and any(ch.isalpha() for ch in text)


#: The languages written in Cyrillic, told apart from a Latin-script line the same way
#: Hebrew is: by the letters.
CYRILLIC_SCRIPT = frozenset({"ru"})


def written_in(text: str, language: str) -> bool:
    """Whether a line the reader wrote is in `language` at all, before anything is spent
    checking it (design.md §12, "A scope is a press that lasts": a question asked in
    English spends nothing).

    By the script where the script settles it. French and Italian share English's
    letters, so there a line is refused only when most of its words are far commoner in
    English than in the language: "what does this mean" is English, "ciao, come stai" is not.
    Where wordfreq is not installed nothing can be told apart, and the line is checked.
    """
    code = (language or "he").split("-")[0].lower()
    if code in HEBREW_SCRIPT:
        return _has_hebrew(text)
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    if code in CYRILLIC_SCRIPT:
        return any("\u0400" <= ch <= "\u04ff" for ch in letters)
    latin = sum(1 for ch in letters if ch.isascii() or "\u00c0" <= ch <= "\u024f")
    if latin * 2 < len(letters):
        return False
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        return True
    words = _LATIN_WORD.findall(text.lower())
    if not words:
        return False
    english = sum(
        1 for word in words if zipf_frequency(word, "en") - zipf_frequency(word, code) >= 1.0
    )
    return english * 2 <= len(words)


def for_host(words: list[str], language: str) -> list[str]:
    """A word list as a host is handed it: the language's own words, two letters or
    more. The ledger holds what a reader tapped, and on a Hebrew shelf that includes
    "and", "the", digits and stray letters, which a host told "these are the words they
    know" would write with."""
    code = (language or "he").split("-")[0].lower()
    pattern = _WORD if code in HEBREW_SCRIPT else _LATIN_WORD
    out = []
    for word in words:
        found = pattern.fullmatch(word.strip())
        if found is None:
            continue
        letters = [ch for ch in word if ch.isalpha()]
        if code in HEBREW_SCRIPT:
            letters = [ch for ch in letters if "\u05d0" <= ch <= "\u05ea"]
        if len(letters) >= 2:
            out.append(word.strip())
    return out


def length(text: str, language: str = "he") -> int:
    """How many words a reply is, the way a reader meets them: over the model's own lines,
    the "> " recast left out because it is the reader's sentence said back. A Hebrew word
    is a run of Hebrew letters and points, and any other language's a run of letters
    joined by an apostrophe; the number is what the cap in the contract is about, and what
    `scripts/eval_grading.py` and `scripts/measure_reply_length.py` count."""
    word = _WORD if (language or "he").split("-")[0].lower() in HEBREW_SCRIPT else _LATIN_WORD
    return sum(len(word.findall(pair.hebrew)) for pair in pairs(text, language) if not pair.recast)


_WORD = re.compile(r"[\u05d0-\u05ea][\u05b0-\u05c7\u05d0-\u05ea\u05f3\u05f4\"']*")
_LATIN_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")


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
        from wordfreq import available_languages, top_n_list, zipf_frequency
    except ImportError:
        return []
    code = language.split("-")[0].lower()
    # Asked before the list is read, because not every missing language raises: asked for
    # Yiddish, wordfreq answers with its fallback list, which is English, and a Yiddish
    # reader would have been offered "the" and "of" as words they may already know
    # (2026-09-13).
    if code not in available_languages():
        return []
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


#: How many recurring mistakes the conversation may be told about at once
#: (targum-internal#290). Three, and the number is the whole of the restraint: a model
#: handed a list of everything a reader has ever got wrong writes a grammar lesson, which
#: is the thing this must never become. Three is enough to drift toward a weak spot and
#: too few to teach from.
RULES_BACK = 3

#: How many slips are read to find them. A recurring mistake is one that recurs, and the
#: last few dozen lines are where "recurring" can be seen.
SLIPS_READ = 60


def recurring(slips: list[dict[str, Any]], most: int = RULES_BACK) -> list[str]:
    """The reasons that came up more than once, commonest first, at most `most`.

    The model writes a one-sentence reason on a corrected line — the `~ ` line — and it
    is the only part of a slip that generalises: the changed token is this sentence's,
    and the reason is the rule. A reason seen once is a slip; a reason seen three times
    is something the reader keeps doing.

    Once is not enough on purpose. Everybody gets a line wrong once, and a conversation
    that bent itself toward every single mistake would be a conversation about mistakes.
    """
    seen: dict[str, int] = {}
    for slip in slips:
        why = str(slip.get("why") or "").strip()
        if not why:
            continue
        seen[why] = seen.get(why, 0) + 1
    over = [(count, why) for why, count in seen.items() if count > 1]
    over.sort(key=lambda pair: (-pair[0], pair[1]))
    return [why for _, why in over[:most]]


def ledger_block(
    level: Level,
    known: list[str],
    common: list[str],
    returning: Returning | None = None,
    rules: list[str] | None = None,
    shared: bool = True,
) -> str:
    """The per-reader block: the ledger, then the word lists, then what comes back.

    `shared` is False for a connector that was not granted the reader's record. Then
    there is no ledger to describe, and the first-day branch would be false: a reader
    with thousands of words would be told they had marked none, and asked what they have
    read. The host is told the plain thing instead — it cannot see the list.
    """
    from ..translate.prompts import language_name

    named = language_name((level.language or "he").split("-")[0].lower())
    if not shared:
        parts = [
            f"The reader is learning {named}. This connection doesn't share the reader's "
            "word list. Grade to the common words below, and don't ask what they know. "
            "Never tell the reader they are at a level."
        ]
        if common:
            parts.append(
                f"Common words any learner meets early ({len(common)}): " + " ".join(common)
            )
        return "\n\n".join(parts)
    parts = [describe(level)]
    if known:
        parts.append(f"The reader's known words ({len(known)}): " + " ".join(known))
    else:
        # Nobody has a ledger on their first day. Words are marked while reading, so
        # the way to a ledger is a text, and the first question is the one the research
        # notes give: what they have read, never what level they are.
        # In the conversation's own language. This said Hebrew whatever the ledger was,
        # and an Italian conversation on its first day asked what the reader had read in
        # Hebrew and offered them a Hebrew text (2026-09-15).
        parts.append(
            "The reader has marked no words known yet. Stand on the commonest of the common "
            "words, keep every sentence short, and in your first reply ask what they have "
            f"read in {named} so far - never what level they are - and offer them one short "
            f"{named} text to start with (suggest_next), because words are marked while "
            f"reading and that is how their ledger begins. If they say they already read "
            f"{named}, tell them once that Learn has a list called Words you may already "
            "know, where marking the common words they know lets you write with them."
        )
    if common:
        parts.append(f"Common words any learner meets early ({len(common)}): " + " ".join(common))
    back = returning or NOTHING_RETURNING
    if back.words():
        lines = [f"The reader's own words to carry back into your {named}, by where they stand:"]
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
    if rules:
        # What they keep getting wrong (targum-internal#290), as context and never as a
        # lesson. "anki srs is kinda dumb in the sense it doesnt really know what you get
        # wrong beyond what you tell it" — this is the half a scheduler cannot have, and
        # the way to waste it is to announce it. So: steer the sentences, say nothing.
        parts.append(
            "\n".join(
                [
                    "What this reader has had corrected more than once "
                    f"({len(rules[:RULES_BACK])}):",
                    *(f"- {rule}" for rule in rules[:RULES_BACK]),
                    "Let your own sentences use these forms correctly and often, so they "
                    "meet the right one in passing. Never mention this list, never say "
                    "they keep getting something wrong, never set an exercise on it and "
                    "never correct a line that is already right. The one-line reason on a "
                    "corrected line is still the whole of what you say about a mistake.",
                ]
            )
        )
    return "\n\n".join(parts)


def words_in(*texts: str) -> int:
    return sum(len(text.split()) for text in texts)


def seconds_for(words: int) -> float:
    """How long this many words take to say, at the conversational rate."""
    return max(0.0, words) / CONVERSATION_WORDS_PER_MINUTE * 60.0
