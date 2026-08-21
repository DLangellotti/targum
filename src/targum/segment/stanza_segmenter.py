"""Stanza, loaded and downloaded only when a run actually needs it.

Stanza pulls torch and a per-language model of a few hundred megabytes. Neither is
touched at import time: the pipeline is built on first use, and `targum models fetch`
exists so the download can happen before a long job rather than during one.
"""

from __future__ import annotations

import contextlib
import io
import logging
import shutil
from typing import Any

from ..errors import ModelMissing, TargumError
from ..paths import ensure, model_dir

# Stanza's own tag for a language, where it differs from the BCP-47 primary subtag.
_STANZA_CODE = {"iw": "he", "ji": "yi"}


def stanza_code(language: str) -> str:
    primary = language.split("-")[0].lower()
    return _STANZA_CODE.get(primary, primary)


def model_path(language: str) -> Any:
    return model_dir() / stanza_code(language)


def is_downloaded(language: str, processor: str = "tokenize") -> bool:
    """Whether one processor's model is on disk.

    Segmentation needs the tokenizer; difficulty bands also need the part-of-speech
    and lemma models, which are separate files beside it.
    """
    path = model_path(language) / processor
    return path.is_dir() and any(path.glob("*.pt"))


def downloaded_languages() -> list[str]:
    root = model_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and any(p.rglob("*.pt")))


def has_processors(language: str, processors: str) -> bool:
    return all(
        is_downloaded(language, processor)
        for processor in processors.split(",")
        # mwt exists only for some languages, and stanza adds it when it applies.
        if processor not in {"mwt"}
    )


def download(language: str, processors: str = "tokenize") -> None:
    """Fetch models for one language. Loud on failure, quiet on success."""
    import stanza

    code = stanza_code(language)
    ensure(model_dir())
    try:
        stanza.download(code, model_dir=str(model_dir()), processors=processors, verbose=True)
    except Exception as exc:  # stanza raises a mix of its own and network errors
        raise TargumError(f"Could not download the {code} language model.", str(exc)) from exc


def remove(language: str) -> bool:
    path = model_path(language)
    if not path.is_dir():
        return False
    shutil.rmtree(path)
    return True


class StanzaSegmenter:
    """Sentence splitting via Stanza's tokenizer.

    Abbreviations, quoted dialogue, initials and ellipses all break a regex on periods,
    and Hebrew geresh and gershayim (׳ ״) look like quote marks without being them.
    """

    def __init__(self, *, auto_download: bool = True) -> None:
        self.auto_download = auto_download
        self._pipelines: dict[str, Any] = {}
        self._loaded_version: str | None = None

    @property
    def name(self) -> str:
        return f"stanza/{self._loaded_version or 'unloaded'}"

    def pipeline(self, language: str) -> Any:
        code = stanza_code(language)
        if code in self._pipelines:
            return self._pipelines[code]

        import stanza

        self._loaded_version = stanza.__version__
        if not is_downloaded(code):
            if not self.auto_download:
                raise ModelMissing(
                    f"The {code} language model is not downloaded.",
                    f"targum models fetch {code}",
                )
            download(code)

        logging.getLogger("stanza").setLevel(logging.ERROR)
        try:
            # Stanza greets stdout on load; the CLI owns that space.
            with contextlib.redirect_stdout(io.StringIO()):
                self._pipelines[code] = stanza.Pipeline(
                    lang=code,
                    processors="tokenize",
                    dir=str(model_dir()),
                    download_method=None,
                    verbose=False,
                )
        except Exception as exc:
            raise TargumError(
                f"Could not load the {code} language model.",
                f"targum models remove {code} && targum models fetch {code}",
            ) from exc
        return self._pipelines[code]

    def split(self, texts: list[str], language: str) -> list[list[str]]:
        if not texts:
            return []
        nlp = self.pipeline(language)
        # One call for the whole document: loading dominates, per-block calls do not.
        docs = nlp.bulk_process([text for text in texts])
        return [[sentence.text.strip() for sentence in doc.sentences] for doc in docs]
