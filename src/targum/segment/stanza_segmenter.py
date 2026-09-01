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
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
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


def is_downloaded(language: str, processor: str = "tokenize", package: str | None = None) -> bool:
    """Whether one processor's model is on disk.

    Segmentation needs the tokenizer; difficulty bands also need the part-of-speech
    and lemma models, which are separate files beside it. A processor Stanza ships
    several builds of is asked for by name, since any one of them on disk says nothing
    about whether the one wanted is.
    """
    path = model_path(language) / processor
    if package:
        return bool((path / f"{package}.pt").is_file())
    return bool(path.is_dir() and any(path.glob("*.pt")))


def downloaded_languages() -> list[str]:
    root = model_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and any(p.rglob("*.pt")))


def has_processors(
    language: str, processors: str, packages: Mapping[str, str] | None = None
) -> bool:
    """Whether every processor named is on disk — by build, where one is named."""
    return all(
        is_downloaded(language, processor, (packages or {}).get(processor))
        for processor in processors.split(",")
        # mwt exists only for some languages, and stanza adds it when it applies.
        if processor not in {"mwt"}
    )


#: Who to tell that a model is being fetched, for as long as somebody is listening.
#:
#: A first build on a fresh box stops for minutes here, and until this the page said
#: whatever it had said before — "Finding each word's dictionary form…" — while a few
#: hundred megabytes came down a wire. A line that has not changed in four minutes reads
#: as a hang, and the reader's next move is to close the tab on a build that was working.
#:
#: A context variable rather than an argument, because the three callers are a segmenter,
#: a lemmatizer and the CLI, and threading a callback through all of them to reach one
#: `stanza.download` would touch four constructors to say one sentence. Per-context
#: rather than a module global because a hosted box builds in threads, and one reader's
#: progress line has no business arriving in another reader's build.
_TELLING: ContextVar[Callable[[str], None] | None] = ContextVar("_TELLING", default=None)


@contextmanager
def telling(say: Callable[[str], None]) -> Iterator[None]:
    """Announce model downloads to `say` for the duration."""
    token = _TELLING.set(say)
    try:
        yield
    finally:
        _TELLING.reset(token)


def download(
    language: str, processors: str = "tokenize", packages: Mapping[str, str] | None = None
) -> None:
    """Fetch models for one language. Loud on failure, quiet on success.

    `packages` names a build for a processor, as `annotate.lemma` does for the Hebrew
    tokenizer; every processor it leaves unnamed comes as Stanza's default.
    """
    import stanza

    # Local, because `translate.prompts` reaches back into this package and a top-level
    # import would close the circle.
    from ..translate.prompts import language_name

    code = stanza_code(language)
    say = _TELLING.get()
    if say is not None:
        # Said before the wait, not after it, and it names the one thing that makes the
        # wait bearable: that it happens once. Callers reach here only when the model is
        # genuinely absent — `has_processors` and `is_downloaded` gate every call site —
        # so this never appears on a build that is not actually waiting for a download.
        say(f"Fetching the {language_name(code)} language model. This happens once.")
    ensure(model_dir())
    try:
        stanza.download(
            code,
            model_dir=str(model_dir()),
            processors=processors,
            package=dict(packages or {}),
            verbose=True,
        )
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
