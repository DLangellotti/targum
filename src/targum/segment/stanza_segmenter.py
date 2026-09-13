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

#: The Stanza models targum may load: a language, and for each processor the build that
#: was checked. **Empty, on purpose (2026-09-13).**
#:
#: Stanza's code is Apache-2.0 and its models are not; each is trained on a Universal
#: Dependencies treebank with a licence of its own, and `LICENSING.md` holds that a
#: NonCommercial or ShareAlike term on what a model was trained on reaches the model. The
#: Hebrew treebank was found NonCommercial and Hebrew left Stanza for it
#: (targum-internal#116) — and every other language stayed, on the assumption that only
#: Hebrew's was. It was not: the English default includes GUM and the Russian default is
#: SynTagRus, both CC BY-NC-SA, as are the Italian, Arabic and Latin defaults, and French,
#: Spanish and German are ShareAlike. None passes, so nothing is listed, and a language
#: whose treebank is checked and clean is added here with the build that was checked —
#: never Stanza's default, which a Stanza release can repoint at another treebank.
AUDITED: dict[str, dict[str, str]] = {}

_NONCOMMERCIAL_HEBREW = (
    "Hebrew is not read by Stanza: its Hebrew models are NonCommercial.",
    "Hebrew words are DICTA's and Hebrew sentences are drawn by rule.",
)


def audited(language: str, processors: str) -> dict[str, str]:
    """The checked build for each processor asked for, or a refusal that says why.

    Every door to a Stanza model goes through this: the download, the tokenizer and the
    lemmatizer. `mwt` is Stanza's to add where a tokenizer needs it, so it is pinned when
    listed and not demanded when not.
    """
    code = stanza_code(language)
    if code == "he":
        raise TargumError(*_NONCOMMERCIAL_HEBREW)
    pinned = AUDITED.get(code, {})
    wanted = [processor for processor in processors.split(",") if processor != "mwt"]
    if not pinned or any(processor not in pinned for processor in wanted):
        raise TargumError(
            f"targum does not read '{code}' with Stanza: its models are not cleared for "
            f"a paid offering.",
            "LICENSING.md says which treebanks have been checked.",
        )
    return {
        processor: pinned[processor] for processor in processors.split(",") if processor in pinned
    }


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

    Only builds listed in `AUDITED`: whatever `packages` a caller names, the checked build
    is what is fetched, and a language with none is refused before anything is asked of
    the network.
    """
    code = stanza_code(language)
    packages = audited(code, processors)

    import stanza

    # Local, because `translate.prompts` reaches back into this package and a top-level
    # import would close the circle.
    from ..translate.prompts import language_name

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


def installed_version() -> str:
    """Stanza's version without importing it, which is most of a second and torch."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("stanza")
    except PackageNotFoundError:
        return "unknown"


class StanzaSegmenter:
    """Sentence splitting via Stanza's tokenizer, for a language listed in `AUDITED`.

    Which today is none. `HebrewSegmenter` holds one of these and hands it only a language
    that is listed; everything else is drawn by rule in `hebrew.py` and `cased.py`.
    """

    def __init__(self, *, auto_download: bool = True) -> None:
        self.auto_download = auto_download
        self._pipelines: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return f"stanza/{installed_version()}"

    def pipeline(self, language: str) -> Any:
        code = stanza_code(language)
        if code in self._pipelines:
            return self._pipelines[code]
        packages = audited(code, "tokenize")

        import stanza

        if not is_downloaded(code, "tokenize", packages.get("tokenize")):
            if not self.auto_download:
                raise ModelMissing(
                    f"The {code} language model is not downloaded.",
                    f"targum models fetch {code}",
                )
            download(code, "tokenize", packages)

        logging.getLogger("stanza").setLevel(logging.ERROR)
        try:
            # Stanza greets stdout on load; the CLI owns that space.
            with contextlib.redirect_stdout(io.StringIO()):
                self._pipelines[code] = stanza.Pipeline(
                    lang=code,
                    processors="tokenize",
                    package=packages,
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
