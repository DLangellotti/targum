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
import re
import threading
from collections.abc import Iterator
from typing import Any

from ..errors import TargumError
from ..models import Segment, Syntax, Token
from ..paths import settle_hf_home
from ..segment.pieces import at_spaces
from ..segment.stanza_segmenter import stanza_code
from ..vocalize.base import strip_nikkud
from .hebrew import BINYANIM, CLITIC_GLOSSES, FINALS, binyan_of, kept_feats, root_of

# The one model, named in full because the name rides into every annotation.
MODEL = "dicta-il/dictabert-joint"
#: The commit of `MODEL` this code runs, pinned (2026-09-27). The model is loaded with
#: `trust_remote_code`, so an unpinned load runs whatever modeling code DICTA last pushed —
#: and it pushed some on 2026-09-09 and 2026-09-15 — on the first cold start after a cache
#: is cleared. This is the revision the box and the laptop both hold. Moving it is an
#: annotator change like any other: read the diff, then rename.
REVISION = "3c3c27067bb73a45e99c36bd90b3b3dbc10fda12"

# What this annotator knows how to say about a word, in the vocabulary `lemma.py` uses
# for the same list. The roots survive the swap because the binyan is derived rather
# than read, and dropping "roots" here would claim otherwise.
#
# "entities" where Stanza's list says "names", since targum-internal#149: which word is a
# person or a place is read off the model's named-entity head rather than off PROPN.
# The same weights have always returned it — `dictabert-joint` runs its NER head on
# every call and this threw the answer away — so the change costs no download and no
# extra pass. It does change what every Hebrew annotation says, and this string is in
# the annotator's name, so changing it is what re-reads the library: once, on purpose.
#
# "syntax" and "grammar/3" since targum-internal#134: DICTA's syntax head is kept on every
# word (`Token.syntax`), and the head of a construct chain says `Definite=Cons` in its
# grammar line. The same call has always returned the syntax and this threw it away, so
# again no new weights and no extra pass; and again a rename, which re-reads the library.
#
# "grammar/4" since 2026-10-12 (known issues 1.1-1.3, 2.5): each personal pronoun on its
# own card rather than all on הוא's, a preposition with a pronoun on the end on the
# preposition's, wife and women on אישה's rather than "man", two on שניים's rather than
# "three", and עולה and לקחה on their own verbs. A version number rather than a new piece,
# because `versions.compare` only sees a text as behind on a piece both names carry.
#
# "grammar/5" in the same undeployed release (2026-10-13): a pointed מוֹכֵר is a seller,
# not "familiar". See `SELLER`. The box never ran grammar/4, so it reads the library once.
#
# "grammar/6" since 2026-10-13 (after the long deploy): grammar/5's seller never fired,
# because `Annotator.annotate` strips the marks before this class sees a word, so the
# check now runs there, on the pointed word (`mend_pointed`); and היא, הם and הן as the
# copula, which DICTA tags AUX and files under הוא, go on their own cards like the
# pronouns they are.
FEATURES = "roots+everyword+entities+syntax+grammar/6"

# Sentences handed to the model at once. One call pads every sentence in it to the
# longest, so asking for a whole book in one go builds a tensor the size of the longest
# line times the number of lines: `targum rebuild --words` on the box peaked at 7.1 GB on
# a 7.7 GB machine and was OOM-killed, twice, before this existed. Sixteen holds a book
# of four thousand segments inside 1.5 GB, and the throughput difference against a batch
# ten times larger is not measurable next to what the box does with the rest of a rebuild.
BATCH = 16

# And never more padded tokens than this in one call, however few sentences that is.
# Sixteen assumed a book's sentences. A pasted recording's transcript has almost no
# sentence ends, so a segment runs to the model's 512 tokens, and the lemma head sorts a
# 128,000-wide row for every padded token: measured on 2026-09-14 at about 1 GB a long
# segment, 2 GB for two, 4.6 GB for four. Sixteen of them OOM-killed the box at this
# stage four times in an hour. A thousand tokens is two such segments, about 2 GB, and
# a book's lines are short enough that it still sends them sixteen at a time.
TOKENS = 1024

# Characters to a token, low on purpose. Counted on 7,593 Hebrew segments of the local
# shelf: the median is 5.0 and 99% are above 2.46, so a length read at 2 guesses high and
# a batch comes out smaller than it could be, never larger. The model's tokenizer would
# be exact at the price of tokenizing every segment twice.
CHARS_PER_TOKEN = 2

# What the model reads of one call's sentence; the rest is cut off, and pads nothing.
MAX_TOKENS = 512

# The longest piece of a segment handed over, cut at a space. A segment past the model's
# 512 tokens used to come back with its tail unread — no dictionary form, no card — and a
# transcript nobody punctuated is all tail. 800 characters stays under 512 tokens even at
# the fewest characters a token was counted at on the shelf (1.62), and a sentence is
# nowhere near it, so only a runaway segment is ever cut.
PIECE_CHARS = 800

# What DICTA says when it has no lemma for a word.
BLANK = "[BLANK]"

# And what it says when it half has one. On a rare word the lemma head sometimes returns
# a raw BERT wordpiece — מלבלב came back as ##לבים, קלשון as ##שון — which is not a word
# in any language and would card under that name. 257 lemmas on this shelf were affected
# (targum-internal#141). Treated exactly like a decline, because that is what it is.
PIECE = "##"

# Not a word at all, exactly as `lemma.py` draws the line.
SKIP_POS = frozenset({"PUNCT", "SYM"})

# The link DICTA puts on the governed noun of a construct chain: in בֵּית הַסֵּפֶר it is on
# הַסֵּפֶר, pointing at בֵּית. DICTA's morphology never says `Definite=Cons`, so this is
# the only place the construct state is said at all.
SMIXUT = "compound:smixut"

# What can stand at the head of a chain, as the card names it. A number after a noun is
# filed as a chain too — בָּעַמּוּד מָאתַיִים, page two hundred — and is a label, not one.
CONSTRUCT_POS = frozenset({"NOUN", "ADJ", "NUM"})

# What the NER says about a word that belongs to no entity. Written only where it
# overrules the tag — on a PROPN the NER left outside every entity — because that is
# the one place a reader of the token could otherwise take the tag's word for it. On
# a sample of the shelf (targum-internal#149) those were mostly not names at all:
# בחמישי, ובדיו, הדפתרא, the setumah ס.
OUTSIDE = "O"

# The prefix letters DICTA hands back as one chunk — ובספר segments as ("וב", "ספר"),
# not as three pieces — so the chunk is spelled out a letter at a time for the card.
PREFIX_LETTERS = frozenset(CLITIC_GLOSSES)

# The closed-class words where DICTA's answer is not the form a vocabulary card wants.
# Measured on 150 sentences of Brenner and then across the shelf (targum-internal#116).
# `היה → היי` alone was 81 of 863 disagreements, and a copula that lemmatizes to an
# imperative is wrong by any reading.
#
# The pronouns are not in here, and not because DICTA keeps them apart: it does not. This
# comment used to say it did, and the shelf said otherwise (known issues 1.1, 2026-10-12):
# DICTA lemmatizes אתה, היא, הם, הן and אתן to הוא, and בה, בהם and מהם too, so one card
# said "he; it" for all of them. A lemma→lemma table cannot undo that — הוא is the right
# answer for הוא — so they are mended by the word, in `PRONOUNS` and `CARRIED` below.
#
# Nor is איש↔אישה any longer (2026-10-12). `"אישה": "איש"` was here for DICTA reading
# איש as אישה on Brenner, and it filed every wife and every woman under "man" instead —
# ואשתו, אשתי, נשים. The word says which it is, so `_man_or_woman` asks the word.
OVERRIDES = {
    "היי": "היה",
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
    # The ordinal, "second", and the construct of שנים, "years of": never שנה.
    "שני": "שני",
}

# Two, in each of its spellings, on two's own card (known issues 1.3, 2026-10-12). DICTA
# read שתי המפלגות as שלושה, "three", and declined שתי elsewhere; שתיים, שני and שניים it
# files under שניים, which is the dictionary's form, so that is the card. Only where DICTA
# says it is a number: שני is also "second" and "years of", which keep `SURFACES`' answer.
# "Both of them" too — שתיהן went to שלושה as well — since it is two with a pronoun on.
TWO = "שניים"
TWOS = frozenset(
    {"שתי", "שתיים", "שתים", "שני", "שניים", "שניהם", "שניהן", "שתיהן", "שתיהם", "שנינו"}
)

# The personal pronouns, each its own card (known issues 1.1). Keyed on the word under its
# prefixes — שאתה is אתה — and only where DICTA tagged it a pronoun or the copula, because
# אתן is also "I will give" and את the object marker. Their own spelling is their dictionary form.
PRONOUNS = frozenset(
    {
        "אני",
        "אנוכי",
        "אנכי",
        "אנחנו",
        "אנו",
        "אתה",
        "את",
        "אתם",
        "אתן",
        "הוא",
        "היא",
        "הם",
        "הן",
        "המה",
    }
)

# A preposition with a pronoun on the end, which DICTA sometimes tags a pronoun and files
# under whatever it likes — בו under בו, בה under הוא, לכם under לי, מכם under מי. Where
# it tags one an `ADP` it files it under the preposition — אותו under את, שלו under של,
# עליו under על — and the card says "with a pronoun on the end". These go the same way,
# so בו is on ב's card, לי on ל's and ממנו on מן's: the preposition is the word to learn,
# and the ending is the same handful of pronouns on every one of them.
#
# Not the feminine plurals לכן, בכן and מכן: in modern prose they are קודם לכן, "before
# that", בכן, "so", and לאחר מכן, "after that" — כן with a preposition, not you — and DICTA
# tags the first a pronoun all the same (the weekly, 2026-10-12).
CARRIED = {
    **dict.fromkeys(("לי", "לך", "לו", "לה", "לנו", "לכם", "להם", "להן"), "ל"),
    **dict.fromkeys(("בי", "בך", "בו", "בה", "בנו", "בכם", "בהם", "בהן"), "ב"),
    **dict.fromkeys(("ממני", "ממך", "ממנו", "ממנה", "מכם", "מהם", "מהן"), "מן"),
    # Tagged a preposition and still misfiled: ממנו under הוא, ממנה and עמו declined.
    **dict.fromkeys(("עמי", "עמך", "עמו", "עמה", "עמנו", "עמם", "עמהם"), "עם"),
}
# And the same word cut differently: DICTA hands מהם back as the prefix מ and הם. The
# letter that is the preposition, and the card it goes on.
CARRYING = {"ב": "ב", "ל": "ל", "מ": "מן"}

# The verbs whose every form DICTA was seen filing under another verb, keyed on the word
# (known issues 2.5). A verb spelled עולה is the present of עלה whatever the sentence —
# the hif'il would open with מ — and DICTA said העלה, "raised", and עוול. A verb opening
# לקח is a form of לקח, and DICTA said קיבל, "received". Only these two, because only
# these two have a spelling that settles it.
VERBS = {
    **dict.fromkeys(("עולה", "עולים", "עולות"), "עלה"),
    **dict.fromkeys(("לקח", "לקחה", "לקחו", "לקחתי", "לקחת", "לקחנו", "לקחתם"), "לקח"),
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


#: The weights, once per process. Twenty seconds and 1.5 GB to load, and read-only once
#: loaded, so a second instance — the weekly's gauge builds an annotator per attempt —
#: shares them rather than paying again.
_LOADED: dict[str, tuple[Any, Any]] = {}

#: One load and one call at a time, across every thread in the process. The build worker,
#: the quote a request prices, and the chat's record all reach these weights, and each
#: call can hold gigabytes while it runs: two at once is two spikes, and two loads racing
#: is two copies. The chat's own lock serialised only the chat.
_LOCK = threading.Lock()


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
        with _LOCK:
            return self._load()

    def _load(self) -> tuple[Any, Any]:
        if self._model is None and MODEL in _LOADED:
            self._model, self._tokenizer = _LOADED[MODEL]
        if self._model is None:
            settle_hf_home()
            try:
                import torch
                from transformers import AutoModel, AutoTokenizer
            except ImportError as missing:  # pragma: no cover — a broken install only
                raise TargumError(
                    "The Hebrew annotator needs transformers, which is not installed.",
                    "pip install 'transformers>=4.40'",
                ) from missing

            pinned = REVISION if self.model_id == MODEL else None

            def load(local: bool) -> tuple[Any, Any]:
                tokenizer = AutoTokenizer.from_pretrained(
                    self.model_id, revision=pinned, local_files_only=local
                )
                weights = AutoModel.from_pretrained(
                    self.model_id, trust_remote_code=True, revision=pinned, local_files_only=local
                )
                return tokenizer, weights

            # From the disk first, and from the hub only if the disk has not got it
            # (2026-10-06). Asked plainly, the loader asks the hub about the model before
            # it reads a byte of the copy it already holds — on the box that was a `GET
            # huggingface.co/api/models/dicta-il/dictabert-joint` at every service start,
            # a start that waited on Hugging Face answering and, with the hub down, a
            # start that could not read Hebrew at all. The revision is pinned to a commit,
            # so the copy on disk is exactly what the hub would hand over. A box that has
            # never had the weights still gets them: the first load finds nothing local
            # and goes to the hub, as it always did.
            try:
                self._tokenizer, model = load(local=True)
            except Exception:  # noqa: BLE001 — the loader raises whatever it likes
                self._tokenizer, model = load(local=False)
            model.eval()
            torch.set_grad_enabled(False)
            self._model = model
            _LOADED[MODEL] = (model, self._tokenizer)
        return self._model, self._tokenizer

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        if not segments:
            return {}
        # By the code and never the raw tag: a text tagged `he-IL` or `iw` is Hebrew, and
        # handing it to the delegate would read it with the NonCommercial model this
        # class exists to keep it away from (targum-internal#146).
        if stanza_code(language) != "he":
            return self.other.lemmas(segments, language)

        import torch

        model, tokenizer = self.model()
        # Every segment as the pieces the model reads whole: itself, unless it runs past
        # `PIECE_CHARS`. Each piece keeps where it starts, so its words land back in place.
        # A piece after the first starts at the space it was cut on, which is dropped, so
        # the model's offsets are counted from the first letter it was actually given.
        pieces = []
        for segment in segments:
            for start, end in at_spaces(segment.text, PIECE_CHARS):
                text = segment.text[start:end]
                lead = len(text) - len(text.lstrip()) if start else 0
                pieces.append((segment.id, start + lead, text[lead:]))
        out: dict[str, list[Token]] = {segment.id: [] for segment in segments}
        with torch.inference_mode():
            for batch in _batches([text for _, _, text in pieces]):
                with _LOCK:
                    read = model.predict(
                        [pieces[at][2] for at in batch], tokenizer, output_style="json"
                    )
                for at, said in zip(batch, read, strict=True):
                    segment_id, start, _ = pieces[at]
                    # A later piece's heads count from its own first word; the segment's
                    # list already holds the words before it.
                    before = len(out[segment_id])
                    out[segment_id].extend(
                        _moved(token, start, before) if start else token
                        for token in _tokens(said, self.tally)
                    )
        return out


def _moved(token: Token, start: int, before: int) -> Token:
    """A word of a later piece, placed in its segment: its offsets from the piece's start,
    and its head from the words of the segment ahead of the piece."""
    update: dict[str, Any] = {"start": token.start + start, "end": token.end + start}
    if token.syntax is not None and token.syntax.head >= 0:
        update["syntax"] = token.syntax.model_copy(update={"head": token.syntax.head + before})
    return token.model_copy(update=update)


def _tokens_in(text: str) -> int:
    """A high guess at how many tokens the model will read of one piece."""
    return min(MAX_TOKENS, len(text) // CHARS_PER_TOKEN + 2)


def _batches(texts: list[str]) -> Iterator[list[int]]:
    """Which texts go together, in the order they came, cut wherever the next would pad
    past `TOKENS`.

    In order rather than sorted by length, so a text of short lines is handed over in
    exactly the batches it always was, and reads back exactly as it did.
    """
    batch: list[int] = []
    longest = 0
    for at, text in enumerate(texts):
        size = _tokens_in(text)
        if batch and (len(batch) == BATCH or (len(batch) + 1) * max(longest, size) > TOKENS):
            yield batch
            batch, longest = [], 0
        batch.append(at)
        longest = max(longest, size)
    if batch:
        yield batch


def _entities(said: dict[str, Any]) -> dict[int, str]:
    """Each word the NER placed in an entity, as its label in BIO form: `B-PER` on the
    word that opens a name, `I-PER` on each word after it.

    By the model's own word index, which counts punctuation, so it is read before any
    word is skipped. The maqaf in תל־אביב is a word of its own to the model and sits
    inside the entity; the word after it still continues it.
    """
    out: dict[int, str] = {}
    for entity in said.get("ner_entities") or []:
        label = str(entity.get("label") or "")
        try:
            first, last = int(entity["token_start"]), int(entity["token_end"])
        except (KeyError, TypeError, ValueError):
            continue
        if not label or last < first:
            continue
        for at in range(first, last + 1):
            out[at] = ("B-" if at == first else "I-") + label
    return out


def _syntax(said: dict[str, Any]) -> tuple[dict[int, int], set[int]]:
    """Where each kept word lands among the tokens, by the model's word index, and which
    words head a construct chain.

    The model counts punctuation and the tokens do not, so a head is renumbered rather
    than copied. A word heads a chain when another hangs off it as `compound:smixut` —
    unless that other is a number, which makes the first a label (page two hundred).
    """
    words = said.get("tokens") or []
    kept: dict[int, int] = {}
    for at, word in enumerate(words):
        if ((word.get("morph") or {}).get("pos") or None) not in SKIP_POS:
            kept[at] = len(kept)
    heads: set[int] = set()
    for word in words:
        syntax = word.get("syntax") or {}
        if syntax.get("dep_func") != SMIXUT:
            continue
        if ((word.get("morph") or {}).get("pos") or "") == "NUM":
            continue
        try:
            head = int(syntax.get("dep_head_idx", -1))
        except (TypeError, ValueError):
            continue
        if 0 <= head < len(words):
            if ((words[head].get("morph") or {}).get("pos") or "") in CONSTRUCT_POS:
                heads.add(head)
    return kept, heads


def _governed(word: dict[str, Any], kept: dict[int, int]) -> Syntax | None:
    """The word's link, by token index, with its prefixes; None where DICTA said none."""
    syntax = word.get("syntax")
    if not syntax:
        return None
    try:
        head = int(syntax.get("dep_head_idx", -1))
    except (TypeError, ValueError):
        head = -1
    seg = list(word.get("seg") or [])
    return Syntax(
        head=kept.get(head, -1),
        relation=str(syntax.get("dep_func") or ""),
        prefixes=tuple(str(tag) for tag in (word.get("morph") or {}).get("prefixes") or ()),
        lead=len("".join(seg[:-1])) if len(seg) > 1 else 0,
    )


def _tokens(said: dict[str, Any], tally: collections.Counter[str] | None = None) -> list[Token]:
    out: list[Token] = []
    entities = _entities(said)
    kept, heads = _syntax(said)
    for at, word in enumerate(said.get("tokens", [])):
        morph = word.get("morph") or {}
        pos = morph.get("pos") or None
        if pos in SKIP_POS:
            continue
        entity = entities.get(at)
        if entity is None and pos == "PROPN":
            entity = OUTSIDE
        surface = word.get("token") or ""
        seg = list(word.get("seg") or [])
        suffix = morph.get("suffix")
        feats = _stanza_feats(morph.get("feats"))
        # The word under whatever prefixes it carries: ועשרים is keyed as עשרים, and a
        # name is never corrected, because בני is a lemma to mend and Benny is a person.
        lex = word.get("lex") or ""
        lemma = _lemma(lex, surface, seg[-1] if seg else surface, pos)
        offsets = word.get("offsets") or {}
        carried = _carried(seg, pos)
        if carried is not None:
            # בו as DICTA reads אותו: the preposition, with a pronoun on the end. The
            # person, gender and number DICTA read stay: they are the pronoun's, and the
            # pronoun is still on the end.
            lemma, seg = carried
            pos, suffix = "ADP", True
        if tally is not None and declined(lex):
            tally["declined"] += 1
        if at in heads:
            # The construct state, said where `kept_feats` and the card already look.
            feats = "|".join(part for part in (feats, "Definite=Cons") if part)
        binyan = binyan_of(feats) or (_binyan_of(lemma) if pos == "VERB" else None)
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
                built=_pieces_of(seg, lemma, suffix),
                feats=kept_feats(feats, pos),
                entity=entity,
                syntax=_governed(word, kept),
            )
        )
    return out


def declined(lex: str) -> bool:
    """Whether DICTA gave no usable lemma: nothing, `[BLANK]`, or a raw wordpiece."""
    lemma = (lex or "").strip()
    return not lemma or lemma == BLANK or PIECE in lemma


# A seller, where the pointing says so (the gym dialogue, 2026-10-13). DICTA reads
# unpointed, so מוֹכֵר, "salesman", and מוּכָּר, "familiar", reach it as the same מוכר,
# and it filed the salesman under הוכר, "was recognized", as an adjective. Only the
# annotator still holds the marks — it strips them before any lemmatizer sees the text,
# which is why grammar/5's check in here never fired — so it asks `mend_pointed` once the
# word is back in its own pointed coordinates. A holam on the vav after the mem (מוֹ) is
# the seller, or the selling: מכר's participle, filed under מוכר as DICTA already files
# מוֹכְרִים and הַמּוֹכֶרֶת. Familiar is spelled with a shuruq (מוּ), and an unpointed word
# says neither, so both keep DICTA's answer. Only DICTA's הוכר is mended, so a lemma the
# hand tagging of scripture gave is never touched.
SELLER = "מוכר"
SELLERS = frozenset({"מוכר", "מוכרת", "מוכרים", "מוכרות"})
MISREAD_SELLER = "הוכר"
HOLAM_AFTER_MEM = re.compile("מ[\u0591-\u05c7]*ו[\u05b9\u05ba]")
# The letters a seller can carry in front: וְהַמּוֹכֵר, לַמּוֹכְרִים, שֶׁמּוֹכֶרֶת.
SELLER_PREFIXES = frozenset("ובהכלמש")


def mend_pointed(lemma: str, pos: str | None, pointed: str) -> tuple[str, str | None]:
    """The lemma and pos of a Hebrew word, mended where its own pointing settles what the
    unpointed reading could not; else as given. `pointed` is the word as it stands in
    the text, prefixes and marks and all."""
    if lemma != MISREAD_SELLER or not HOLAM_AFTER_MEM.search(pointed):
        return lemma, pos
    bare, _ = strip_nikkud(pointed)
    for seller in SELLERS:
        head = bare[: len(bare) - len(seller)]
        if bare.endswith(seller) and len(head) <= 3 and set(head) <= SELLER_PREFIXES:
            return SELLER, "NOUN" if pos == "ADJ" else pos
    return lemma, pos


def _lemma(lex: str, surface: str, base: str, pos: str | None = None) -> str:
    """The dictionary form, corrected where DICTA is reliably wrong or silent."""
    lemma = (lex or "").strip()
    if pos == "NUM" and base in TWOS:
        # Before the decline: DICTA declines שתי as often as it misreads it.
        return TWO
    if declined(lemma):
        return surface.lower()
    if pos == "PROPN":
        return lemma.lower()
    if pos in ("PRON", "AUX") and base in PRONOUNS:
        # AUX too: היא, הם and הן as the copula — המצרכים הם מיץ — which DICTA tags AUX
        # and files under הוא, so "they are" said "he; it" (known issues 1.1, 2026-10-13).
        return base
    if pos == "VERB" and base in VERBS:
        return VERBS[base]
    if base in SURFACES:
        return SURFACES[base].lower()
    if pos == "NOUN":
        lemma = _man_or_woman(lemma, base)
    return OVERRIDES.get(lemma, lemma).lower()


def _man_or_woman(lemma: str, base: str) -> str:
    """איש or אישה, as the word itself spells it.

    DICTA was seen reading איש as אישה on Brenner, and נשים as נש; the word settles both.
    איש, אישים and every form of אנשים are a man's; everything else DICTA files under
    אישה — אשה, אשת, אשתו, אשתי — is a woman's, and stays where it put it.
    """
    if lemma == "אישה" and (base in ("איש", "אישים") or base.startswith("אנש")):
        return "איש"
    if base in ("נשים", "נשי", "נשות"):
        return "אישה"
    return lemma


def _carried(seg: list[str], pos: str | None) -> tuple[str, list[str]] | None:
    """The preposition a pronoun-tagged word really is, and the word cut that way; None
    for a word that is not one. See `CARRIED`. A word tagged a preposition is asked too,
    because DICTA tags ממנו one and still files it under הוא — but only a preposition or
    a pronoun: עמו the noun is "his people", and בנו the noun "his son"."""
    if pos not in ("PRON", "ADP") or not seg:
        return None
    base = seg[-1]
    if base in CARRIED:
        return CARRIED[base], seg
    if pos != "PRON":
        return None
    prefix = "".join(seg[:-1])
    if base in ("הם", "הן") and prefix and prefix[-1] in CARRYING:
        # מהם cut as מ + הם: the מ is the preposition, so it goes back on the word.
        return CARRYING[prefix[-1]], [*([prefix[:-1]] if prefix[:-1] else []), prefix[-1] + base]
    return None
