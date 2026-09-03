"""Lemmatization through Stanza.

Surface-form lookup fails on most tokens in both v1 target languages, so this runs
before any band is assigned. Hebrew is the harder case: the same string can be one
word or a prefix plus a word, and Stanza resolves that by splitting a token into
several words. That reading is a decision rather than a fact, so every token it
splits is marked, and the reader can see which words rest on one.
"""

from __future__ import annotations

import contextlib
import io
import logging
from typing import Any

from ..errors import TargumError
from ..models import Segment, Token, is_biblical
from ..paths import model_dir
from ..segment.stanza_segmenter import download, has_processors, stanza_code
from .base import Lemmatizer
from .hebrew import binyan_of, kept_feats, pieces_of, root_of

# Multi-word tokens are not asked for by name. Only some languages have an mwt model,
# and naming it for one that does not, Russian among them, fails the download outright.
# Stanza adds it itself wherever the language's tokenizer needs it, which is how Hebrew
# still gets its prefixes split.
PROCESSORS = "tokenize,pos,lemma"

# What the annotator knows how to say about a word, beyond its dictionary form. It goes
# into the name, and so into every annotation.json, which is what lets the pipeline spot
# a file written before a feature existed and redo it. Redoing one is free: Stanza runs
# on the machine, so nothing is fetched and nothing is spent.
FEATURES = "roots+everyword+names+grammar"

# Stanza's Hebrew tokenizer comes in two builds, one with a character language model
# trained on the modern web behind it and one without, and the tokenizer is where a
# clitic is or is not split off: the lemmatizer only ever sees what it is handed. Stanza's
# default is the one without, and on common modern verbs it hands over the whole string
# — שרוצים, שיעשה, שראה, שלקח — which the lemmatizer then reads as a word that does not
# exist and returns as one that does. שרוצים came back as שרץ, and a line of dialogue was
# banded hard, given the root of "to swarm", and told it was quoting Leviticus. The build
# with the character model splits every one of those. It is not right everywhere — it
# takes הֶרְגֵּל for the foot and שָׁמוּר for myrrh — but over eighteen thousand words of
# modern prose the two disagreed on one token in thirty-five, and read by hand
# (2026-08-30, 131 of them) the character model was right three times for every one it
# was wrong.
#
# Scripture keeps the default, on purpose. The character model is modern, and on the
# Tanakh it misses ו on the verbs — ואשר, וראה, ורעה stay whole — where the default does
# not; and `biblical.py`'s table was counted with the default, so a lemma the table was
# built without would band as unknown. Each register is read with the tokenizer it does
# better with, and the name says which, so only the texts whose reading changed are read
# again.
MODERN_TOKENIZERS = {"he": "combined_charlm"}

# Not a word at all. Everything else is a token the reader can tap, names and numerals
# included: this set used to hold NUM, PROPN and X as "not vocabulary", and dropping
# them here, before the content word was chosen, had two costs. A token made only of
# them was never emitted, so a tenth of Esther was untappable and looked exactly like a
# word already known. Worse, Stanza tags titles and definite nouns PROPN constantly, so
# הַמֶּלֶךְ split into ה + PROPN, the PROPN was thrown away, and the lemma of "the king"
# was ה — mark it known and every הָעִיר and הַפּוּר in the language went plain at once.
# The reader has a key for a name, and it is `i`.
SKIP_POS = frozenset({"PUNCT", "SYM"})

# Function words that attach as prefixes in Hebrew. When a token splits, the content
# word is the one that is not one of these.
FUNCTION_POS = frozenset({"ADP", "DET", "CCONJ", "SCONJ", "PART", "AUX", "PRON"})


def _installed_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("stanza")
    except PackageNotFoundError:
        return "unknown"


class StanzaLemmatizer:
    def __init__(self, *, auto_download: bool = True, scripture: bool = False) -> None:
        self.auto_download = auto_download
        # Read with Stanza's default tokenizer, the one the Tanakh table was counted
        # with. Everything else gets `MODERN_TOKENIZERS`.
        self.scripture = scripture
        self._pipelines: dict[str, Any] = {}
        self._version: str | None = None

    @property
    def name(self) -> str:
        """What made this annotation, stable before the model is loaded.

        The version comes from the package metadata rather than from the imported
        module, because the name is read to decide whether an existing annotation can
        be reused — and importing Stanza to answer that would pay most of the cost the
        reuse is there to avoid.

        The scripture name is the one every annotation carried before the tokenizer
        was chosen by register, because scripture is read exactly as it was: no Tanakh
        is redone for a change that would read it the same.
        """
        base = f"stanza/{self._version or _installed_version()}/{PROCESSORS}+{FEATURES}"
        return base if self.scripture else f"{base}+charlm"

    def packages(self, language: str) -> dict[str, str]:
        """The builds asked for by name, beside Stanza's defaults for the rest."""
        code = stanza_code(language)
        if self.scripture or code not in MODERN_TOKENIZERS:
            return {}
        return {"tokenize": MODERN_TOKENIZERS[code]}

    def pipeline(self, language: str) -> Any:
        code = stanza_code(language)
        if code in self._pipelines:
            return self._pipelines[code]

        import stanza

        self._version = stanza.__version__
        known = supported_languages()
        if known and code not in known:
            raise TargumError(
                f"targum has no word models for '{code}'.",
                "Build it without --words to read it with the translation only.",
            )

        # The lemma and part-of-speech models are extra files beside the tokenizer, so
        # a language fetched for segmentation alone is still missing them — and so is
        # one fetched with the default tokenizer when a named build is wanted.
        packages = self.packages(code)
        if not has_processors(code, PROCESSORS, packages):
            if not self.auto_download:
                raise TargumError(
                    f"The {code} lemmatizer is not downloaded.",
                    f"targum models fetch {code}",
                )
            download(code, processors=PROCESSORS, packages=packages)

        logging.getLogger("stanza").setLevel(logging.ERROR)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self._pipelines[code] = stanza.Pipeline(
                    lang=code,
                    processors=PROCESSORS,
                    package=packages,
                    dir=str(model_dir()),
                    download_method=None,
                    verbose=False,
                )
        except Exception as exc:
            raise TargumError(
                f"Could not load the {code} lemmatizer.",
                f"targum models remove {code} && targum models fetch {code}",
            ) from exc
        return self._pipelines[code]

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        if not segments:
            return {}
        nlp = self.pipeline(language)
        documents = nlp.bulk_process([segment.text for segment in segments])
        return {
            segment.id: _tokens(document)
            for segment, document in zip(segments, documents, strict=True)
        }


def for_source(source: object, *, auto_download: bool = True) -> Lemmatizer:
    """The lemmatizer for a text, by where the text came from.

    Hebrew is read by DICTA, under CC BY 4.0, and not by Stanza's Hebrew models, which
    are trained on a NonCommercial treebank that `LICENSING.md` says a paid offering
    cannot use (targum-internal#116). Stanza stays for every other language it serves.

    The register still decides how the Stanza delegate is built, so a non-Hebrew text
    reads exactly as it did. It no longer decides anything for Hebrew: the tokenizer the
    Tanakh was counted with was Stanza's, and Stanza no longer sees a Hebrew word.

    And where the Hebrew Bible has been fetched, scripture is not read by a model at all:
    it is looked up in the hand tagging, with this as the fallback for the verses the
    lookup cannot line up and for everything that is not scripture. Wrapped only when the
    tagging is actually on disk, so the name an annotation records is the name of what
    ran — a box without the data says so rather than claiming a lookup it never made.
    """
    # Hebrew is DICTA's; everything else stays Stanza's, and `DictaLemmatizer` holds the
    # second one because the language is not known here — `for_source` decides from where
    # a text came from, and the language only arrives with the segments.
    from .dicta import DictaLemmatizer

    model = DictaLemmatizer(
        other=StanzaLemmatizer(auto_download=auto_download, scripture=is_biblical(source)),
        auto_download=auto_download,
    )
    if not is_biblical(source):
        return model
    from . import oshb
    from .scripture import ScriptureLemmatizer

    return ScriptureLemmatizer(model) if oshb.available() else model


def _tokens(document: Any) -> list[Token]:
    out: list[Token] = []
    for sentence in document.sentences:
        for token in sentence.tokens:
            words = list(token.words)
            content = _content_word(words)
            if content is None:
                continue
            surface = token.text
            lemma = (content.lemma or content.text or surface).lower()
            # Free, and already computed: Stanza tags the binyan as it lemmatizes. Any
            # language without the feature simply has none, and gets no root either.
            binyan = binyan_of(content.feats)
            # A split token keeps its whole surface span. Guessing where the prefix
            # ends inside the original string would be inventing precision.
            out.append(
                Token(
                    start=token.start_char,
                    end=token.end_char,
                    surface=surface,
                    lemma=lemma,
                    band=0,
                    split=len(words) > 1,
                    pos=content.upos or None,
                    binyan=binyan,
                    root=root_of(lemma, binyan),
                    built=pieces_of(words, content),
                    feats=kept_feats(content.feats),
                )
            )
    return out


def supported_languages() -> set[str]:
    """Languages Stanza has models for, from the catalogue it downloads first."""
    catalogue = model_dir() / "resources.json"
    if not catalogue.is_file():
        return set()
    try:
        import json

        return {
            code
            for code, entry in json.loads(catalogue.read_text(encoding="utf-8")).items()
            if isinstance(entry, dict) and "lemma" in entry
        }
    except (json.JSONDecodeError, OSError):
        return set()


def _content_word(words: list[Any]) -> Any | None:
    usable = [word for word in words if (word.upos or "") not in SKIP_POS]
    if not usable:
        return None
    if len(usable) == 1:
        return usable[0]
    lexical = [word for word in usable if (word.upos or "") not in FUNCTION_POS]
    # X is what Stanza says when it cannot say, and it is outside FUNCTION_POS, so a
    # scrap of garbage would beat a real noun on length. Only when nothing else is left.
    real = [word for word in lexical if word.upos != "X"]
    for candidates in (real, lexical, usable):
        if candidates:
            return max(candidates, key=lambda word: len(word.lemma or word.text or ""))
    return None
