"""Lemmatization through DICTA, which is Hebrew's own and permissively licensed.

Stanza's Hebrew models are trained on UD_Hebrew-HTB, CC BY-NC-SA and drawn from
Ha'aretz, and `LICENSING.md` says in its own table that NonCommercial is "not usable in
a paid offering". So the annotator that produces every dictionary form in the library
could not survive the day targum starts charging. DICTA publishes Hebrew models under
CC BY 4.0, and this reads Hebrew with `dictabert-joint`, which returns the lemma, the
prefix segmentation and the morphology in one pass.

Two things this had to solve that a swap does not look like it would.

**DICTA tags no binyan.** Stanza fills `HebBinyan`, and `hebrew.root_of` undoes the
pattern that feature names to get the root — so taking DICTA at face value would have
dropped the binyan chip and every root in the library without failing a single test.
The binyan is derived here instead, from the lemma rather than from the surface, which
is the form that makes it recoverable: a Hebrew lemma is the third-person masculine
past, and that citation form spells its pattern. `_binyan_of` reads only the shapes
that are unambiguous unpointed and returns None for the rest, which is the same bargain
`root_of` already strikes — a missing root is a gap the Pealim link fills, a wrong one
is a lie told with confidence.

**DICTA declines on words Stanza guesses at.** Where it has no lemma it answers with the
literal string `[BLANK]`, on 3.3% of tokens of 1900s prose (measured on Brenner,
targum-internal#116). The surface form is used there instead. It is never Stanza, even
as a fallback: a NonCommercial model reached for on the words the permissive one found
hardest would put the licence back exactly where the corpus is thinnest.
"""

from __future__ import annotations

import collections
from typing import Any

from ..models import Segment, Token
from ..paths import model_dir
from .hebrew import BINYANIM, CLITIC_GLOSSES, FINALS, binyan_of, kept_feats, root_of

# The one model, named in full because the name rides into every annotation.
MODEL = "dicta-il/dictabert-joint"

# What this annotator knows how to say about a word, in the vocabulary `lemma.py` uses
# for the same list. Identical to Stanza's: the roots survive the swap because the
# binyan is derived rather than read, and dropping "roots" here would claim otherwise.
FEATURES = "roots+everyword+names+grammar"

# What DICTA says when it has no lemma for a word.
BLANK = "[BLANK]"

# And what it says when it half has one. On a rare word the lemma head sometimes returns
# a raw BERT wordpiece — מלבלב came back as ##לבים, קלשון as ##שון — which is not a word
# in any language and would card under that name. 257 lemmas on this shelf were affected
# (targum-internal#141). Treated exactly like a decline, because that is what it is.
PIECE = "##"

# Not a word at all, exactly as `lemma.py` draws the line.
SKIP_POS = frozenset({"PUNCT", "SYM"})

# The prefix letters DICTA hands back as one chunk — ובספר segments as ("וב", "ספר"),
# not as three pieces — so the chunk is spelled out a letter at a time for the card.
PREFIX_LETTERS = frozenset(CLITIC_GLOSSES)

# The closed-class words where DICTA's answer is not the form a vocabulary card wants.
# Measured on 150 sentences of Brenner and then across the shelf (targum-internal#116).
# `היה → היי` alone was 81 of 863 disagreements, and a copula that lemmatizes to an
# imperative is wrong by any reading.
#
# Deliberately not in here: the pronouns. They are the largest block of disagreement and
# DICTA is the one that is right — Stanza's treebank collapses אני, לי and בו all onto
# הוא, which merges every personal pronoun into one vocabulary card, and DICTA keeps them
# apart. The table is for the cases where the permissive model is worse, and it is short
# because those are closed classes: no new Hebrew copula is coming.
OVERRIDES = {
    "היי": "היה",
    "אישה": "איש",
    "יודע": "ידע",
    "בל": "בלי",
    "ניחם": "מנחם",
    # בני is the construct of בן and belongs on בן's card. Guarded by part of speech
    # rather than by spelling, because בני is also a person's name.
    "בני": "בן",
}


# The other half of the same problem, and it cannot be done by lemma. DICTA reads a round
# ten as its unit — עשרים as עשרה, שלושים as שלושה — and reads שני as שנה. Correcting those
# through `OVERRIDES` is impossible: עשרה, שלושה and שנה are the right answer far more
# often than they are the wrong one, so a lemma→lemma table would break the good cases to
# fix the bad. Keyed on the word instead, which is safe because a number is not ambiguous
# with anything, and closed because the tens are all of them there are.
#
# Measured on the shelf against real marks (targum-internal#141): `שני → שנה` was the
# single costliest move in the library, and `עשרים → עשרה` the third.
SURFACES = {
    "עשרים": "עשרים",
    "שלושים": "שלושים",
    "ארבעים": "ארבעים",
    "חמישים": "חמישים",
    "שישים": "שישים",
    "שבעים": "שבעים",
    "שמונים": "שמונים",
    "תשעים": "תשעים",
    "מאתיים": "מאתיים",
    "שני": "שני",
}


def _stanza_feats(feats: dict[str, str] | None) -> str | None:
    """DICTA's morphology in Stanza's pipe format, so `hebrew.py` reads it unchanged."""
    if not feats:
        return None
    return "|".join(f"{key}={value}" for key, value in feats.items()) or None


def _binyan_of(lemma: str) -> str | None:
    """The binyan a lemma spells, or None — which is most of the time, on purpose.

    Only two shapes are read, because only two cannot be something else unpointed:

    - three letters is פעל, where the root is the lemma and the derivation cannot go
      wrong even when the lemma is;
    - הת plus three is התפעל, spelled exactly as `root_of` expects to unwind it.

    Everything else was tried and measured against Stanza on the shelf, and it lied:
    ה plus four read הסתיר as התפעל and gave the root סיר instead of סתר; נ plus three
    read נקבה as נפעל; ה plus three called every הלכה a הפעיל. Seventeen of eighty-four
    overlapping roots came out wrong, which is the failure mode `hebrew.py` opens by
    refusing — a missing root is a gap the Pealim link fills, a wrong one is a lie told
    with confidence. The cost is real and is written down in targum-internal#116: DICTA
    lemmatizes many verbs to the present participle (רוצה, יושב, עומד) and tags no
    binyan, so those keep their card and lose their root until something better than a
    spelling rule is available.
    """
    letters = [ch for ch in lemma.translate(FINALS) if "א" <= ch <= "ת"]
    pattern = None
    if len(letters) == 3:
        pattern = "PAAL"
    elif letters[:2] == ["ה", "ת"] and len(letters) == 5 and letters[3] != "י":
        # הת is not always התפעל: הפעיל spells itself ה + C + C + י + C, so התחיל and
        # התיר open the same way and are hifil. The mater yod in fourth place is what
        # tells them apart, and it read התחיל as התפעל with the root חיל until it did.
        pattern = "HITPAEL"
    # The Hebrew name, not the tag: `root_of` and the card both read what `BINYANIM`
    # maps Stanza's values to, and handing either the raw tag drops the root silently.
    return BINYANIM.get(pattern) if pattern else None


def _pieces_of(seg: list[str], lemma: str, suffix: Any) -> str | None:
    """How a split token is put together, as the card's own line.

    The same shape `hebrew.pieces_of` builds for Stanza — "ו and + ב in + ספר" — from
    DICTA's segmentation instead of from Stanza's word objects. A pronominal suffix is
    named rather than spelled, because DICTA reports that one as a flag and not as a
    form.
    """
    if len(seg) < 2 and not suffix:
        return None
    chunks: list[str] = []
    for piece in seg[:-1]:
        for letter in piece:
            gloss = CLITIC_GLOSSES.get(letter)
            chunks.append(f"{letter} {gloss}" if gloss else letter)
    chunks.append(seg[-1] if seg else lemma)
    if suffix:
        chunks.append("with a pronoun on the end")
    return " + ".join(chunk for chunk in chunks if chunk) or None


class DictaLemmatizer:
    """Hebrew through DICTA; anything else through the lemmatizer it is given.

    Non-Hebrew is delegated rather than refused, because `for_source` picks a lemmatizer
    from where a text came from and not from what language it is in — the language only
    arrives with the segments. The delegate's name is part of this one's name for the
    same reason every other engine is: a box whose Russian would now be read by a
    different Stanza is a box that should read its Russian again.
    """

    def __init__(
        self, *, other: Any = None, auto_download: bool = True, model: str = MODEL
    ) -> None:
        from .lemma import StanzaLemmatizer

        self.auto_download = auto_download
        self.other = other if other is not None else StanzaLemmatizer(auto_download=auto_download)
        # Which DICTA. The joint model unless a scorecard is comparing it with another,
        # and named in full in `name` either way, so two boxes that read with different
        # weights never claim to have produced the same annotation.
        self.model_id = model
        self._model: Any = None
        self._tokenizer: Any = None
        # How often the model declined and the surface stood in, since the last reset.
        # Read by the scorecard; a token cannot say on its own that it was a fallback.
        self.tally: collections.Counter[str] = collections.Counter()

    @property
    def name(self) -> str:
        """What made this annotation, stable before the model is loaded."""
        return f"dicta/{self.model_id}/{FEATURES}+{self.other.name}"

    def model(self) -> tuple[Any, Any]:
        """The weights, loaded once and kept where Stanza's are.

        `HF_HOME` rather than `cache_dir`, so the code `trust_remote_code` fetches lands
        beside the weights instead of in the home directory — one place to back up, one
        place a box without a network has to have been given.
        """
        if self._model is None:
            import os

            os.environ.setdefault("HF_HOME", str(model_dir() / "hf"))
            import torch
            from transformers import AutoModel, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            model = AutoModel.from_pretrained(self.model_id, trust_remote_code=True)
            model.eval()
            torch.set_grad_enabled(False)
            self._model = model
        return self._model, self._tokenizer

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        if not segments:
            return {}
        if language != "he":
            return self.other.lemmas(segments, language)

        import torch

        model, tokenizer = self.model()
        with torch.inference_mode():
            read = model.predict(
                [segment.text for segment in segments], tokenizer, output_style="json"
            )
        return {
            segment.id: _tokens(said, self.tally)
            for segment, said in zip(segments, read, strict=True)
        }


def _tokens(said: dict[str, Any], tally: collections.Counter[str] | None = None) -> list[Token]:
    out: list[Token] = []
    for word in said.get("tokens", []):
        morph = word.get("morph") or {}
        pos = morph.get("pos") or None
        if pos in SKIP_POS:
            continue
        surface = word.get("token") or ""
        seg = list(word.get("seg") or [])
        # The word under whatever prefixes it carries: ועשרים is keyed as עשרים, and a
        # name is never corrected, because בני is a lemma to mend and Benny is a person.
        lex = word.get("lex") or ""
        lemma = _lemma(lex, surface, seg[-1] if seg else surface, pos)
        if tally is not None and declined(lex):
            tally["declined"] += 1
        feats = _stanza_feats(morph.get("feats"))
        binyan = binyan_of(feats) or (_binyan_of(lemma) if pos == "VERB" else None)
        offsets = word.get("offsets") or {}
        out.append(
            Token(
                start=int(offsets.get("start", 0)),
                end=int(offsets.get("end", 0)),
                surface=surface,
                lemma=lemma,
                band=0,
                split=len(seg) > 1,
                pos=pos,
                binyan=binyan,
                root=root_of(lemma, binyan),
                built=_pieces_of(seg, lemma, morph.get("suffix")),
                feats=kept_feats(feats),
            )
        )
    return out


def declined(lex: str) -> bool:
    """Whether DICTA gave no usable lemma: nothing, `[BLANK]`, or a raw wordpiece."""
    lemma = (lex or "").strip()
    return not lemma or lemma == BLANK or PIECE in lemma


def _lemma(lex: str, surface: str, base: str, pos: str | None = None) -> str:
    """The dictionary form, corrected where DICTA is reliably wrong or silent."""
    lemma = (lex or "").strip()
    if declined(lemma):
        return surface.lower()
    if pos == "PROPN":
        return lemma.lower()
    if base in SURFACES:
        return SURFACES[base].lower()
    return OVERRIDES.get(lemma, lemma).lower()
