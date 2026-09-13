"""Sentences in a script with capitals, drawn by rule rather than by Stanza's tokenizer.

Stanza split every language but Hebrew until 2026-09-13, and every one of its tokenizers
is trained on a treebank that fails `LICENSING.md`: English's default includes GUM and
Russian's is SynTagRus, both CC BY-NC-SA, and French, Spanish and German are ShareAlike.
It mattered more than it looks. A published English translation is split into sentences
before it is lined up against the Hebrew, so every build of a Global Voices article or a
declaration ran the NonCommercial English model — on the one text in the pair that nobody
had checked (see `stanza_segmenter.AUDITED`).

**Why the Hebrew rules nearly do.** `hebrew.py` already reads what matters in any script:
a run of terminal marks, a closing quote or bracket that keeps the outer sentence going,
a dash that keeps a speech tag with its speech, an initial, and a mark inside a number or
a word. What a cased script adds is the thing its docstring says Hebrew lacks: a full
stop that abbreviates. So these are those rules, called with two more:

- **A capital starts a sentence.** A full stop followed by a small letter did not end one
  (`approx. five`, `etc. and`), and an ellipsis followed by a capital did (`I don't
  know... Maybe.`), where in Hebrew an ellipsis is only ended by a dash or a quote.
- **A word on the language's list keeps going.** `Dr. Cohen` is not two sentences. The
  lists below are the abbreviations that close with a full stop and are followed by a
  capital often enough to matter — titles, `St.`, `No.`, months — plus the common ones
  that end in a lowercase continuation anyway, because a list is cheaper to read than a
  rule. A word that is not on it and is followed by a capital ends the sentence; that
  is a mis-split of `Prof. Smith` in a language nobody listed, and the price of not
  shipping a model.

A block in a script with no capitals at all — Arabic, Chinese — is not guessed at: it is
one segment, whole. That is honest and never wrong about a boundary, only coarse.

Like `hebrew.py`, the name is recorded in segments.json and is not a cache key: a text
already on a shelf keeps the segmentation it was translated under. The one place a
boundary is keyed is the alignment of a supplied translation (`Build.aligned`), which is
redone for nothing because the aligner runs on the machine.
"""

from __future__ import annotations

from .hebrew import sentences as _sentences

#: Recorded in every segments.json this draws. Bump it when a rule or a list changes.
NAME = "cased-rules/1"

_TITLES_EN = "mr mrs ms dr prof sr jr st rev hon gen col lt sgt capt mt ft"
_MONTHS_EN = "jan feb mar apr jun jul aug sep sept oct nov dec"
_REFERENCE_EN = "no nos vol vols ch chap p pp fig figs ed eds est approx dept univ inc ltd co"

#: By language, lowercase, without the final full stop. A dot inside is kept: `e.g`.
ABBREVIATIONS: dict[str, frozenset[str]] = {
    "en": frozenset(f"{_TITLES_EN} {_MONTHS_EN} {_REFERENCE_EN} vs etc e.g i.e cf al viz".split()),
    "fr": frozenset(
        "m mm mme mmes mlle mlles dr pr st ste me mgr etc cf p pp vol ch chap no env av "
        "apr j.-c boul bd éd fig".split()
    ),
    "it": frozenset(
        "sig sigg sig.ra sig.na dott dott.ssa dr prof ing avv arch geom ecc pag pagg vol "
        "cap es s ss sant sto sta n nr fig".split()
    ),
    "es": frozenset(
        "sr sra srta sres dr dra ud uds lic prof etc pág págs vol cap fig núm av avda".split()
    ),
    "de": frozenset(
        "dr prof hr fr str nr ca vgl evtl bzw usw z.b d.h u.a s.o u.ä inkl ggf abs jh".split()
    ),
    "ru": frozenset(
        "т.е т.д т.п т.к т.н др пр проф акад г гг им ул д стр см тыс млн млрд руб коп "
        "в вв ок чел доц".split()
    ),
    "uk": frozenset("т.д т.п проф акад ім вул стор див тис млн млрд грн коп ст".split()),
}


def cased(text: str) -> bool:
    """Whether the text has any letter with a capital form at all."""
    return any(char.isupper() or char.islower() for char in text)


def sentences(text: str, language: str) -> list[str]:
    """One block's sentences, by the Hebrew rules taught case and the language's list."""
    if not cased(text):
        whole = text.strip()
        return [whole] if whole else []
    return _sentences(text, cased=True, abbreviations=ABBREVIATIONS.get(language, frozenset()))
