"""A real voice for a word: Lingua Libre's recordings, kept beside the voice's own clips
(targum-internal#610; David, 2026-10-31; design.md §12, "A word is said by a person where
one recorded it").

Lingua Libre puts a person's recording of a single word on Wikimedia Commons, one file a
word, named by the word: `LL-Q9288 (heb)-YaronSh-אֶחָד.wav`. Hebrew has about 3,600 of
them, pointed. Where one says the word a card asks for, `/say-word` answers with it rather
than with the voice, and the voice says everything else as before.

Three things here are easy to undo by accident:

- **A reader never fetches from Commons.** `fetch` copies each file once, on the laptop,
  into `folder()`, which sits in the cache beside `said/`; deploy carries the folder to the
  box, and `/say-word` answers from it as it answers with the voice's clips. A file the
  manifest names that is not on disk is not offered (`Index.find`).
- **Only CC0 and CC BY-SA pass** (`licence`), read per file off its Commons page, never
  assumed from the speaker. Anything else is skipped and counted, so a speaker who changes
  licence mid-way loses only the files that changed.
- **The manifest is private and the credits are public.** The manifest lives with the
  files, out of the repository. Every recording's speaker, licence and Commons page is
  listed at `/credits` (`credits`), and a card that plays one names the speaker and the
  licence under Hear: BY-SA asks for that on the file itself, and CC0 gets it as thanks.
"""

from __future__ import annotations

import html
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

#: The source's name, and the folder under `folder()` its files are kept in.
SOURCE = "lingualibre"

#: The Commons category each language's recordings are filed under.
CATEGORIES = {"he": "Category:Lingua_Libre_pronunciation-heb"}

API = "https://commons.wikimedia.org/w/api.php"
#: Commons asks a client to name itself and say how to reach whoever runs it.
USER_AGENT = "targum/0.1 (+https://targum.page; hello@targum.page) lingualibre-fetch"
#: Seconds between two requests to Commons: one a second, well inside what it asks of a
#: client that is not a bot account.
PAUSE = 1.0

#: Lingua Libre's file names: the language's Wikidata item, its code, the speaker, the word.
_TITLE = re.compile(
    r"^(?:File:)?LL-Q\d+ \((?P<code>[a-z]{3})\)-(?P<rest>.+)\.(?:wav|ogg|mp3|flac)$"
)
#: The speaker as the file's description page names them: "Speaker: <a …>YaronSh</a>".
_SPEAKER = re.compile(r"Speaker:\s*(?:<a [^>]*>)?(?P<name>[^<]+)")
_TAGS = re.compile(r"<[^>]+>")

#: A Hebrew letter. A file without one (Uziel302's "Apache HTTP Server") is not a
#: Hebrew word, whatever category it is in.
_HEBREW = re.compile(r"[א-ת]")
#: Marks that do not change how a word is said for this purpose: cantillation, meteg,
#: rafe, and the upper dot of a variant. A Tanakh word keeps its te'amim; the file does not.
_NOT_SAID = re.compile(r"[֑-ֽֿׅ֯ׄ]")
#: Every mark: the vowels and dagesh and shin/sin dots as well.
_MARKS = re.compile(r"[֑-ׇ]")
#: What a word can be cut with that is not the word.
_EDGES = " \t\n־׀׃.,;:!?\"'()[]–—"


def folder(language: str = "he") -> Path:
    """Where one language's recordings and their manifest are kept: in the cache, beside
    the voice's clips (`serve.said_clip`), which on the box is `/var/lib/targum/cache`."""
    from .paths import cache_dir

    return cache_dir() / "voices" / SOURCE / language


def manifest_path(language: str = "he") -> Path:
    return folder(language) / "manifest.json"


def pointed(text: str) -> str:
    """A word as matched with its vowels: NFC, edges off, cantillation and meteg off."""
    word = unicodedata.normalize("NFC", text).strip(_EDGES)
    return unicodedata.normalize("NFC", _NOT_SAID.sub("", word))


def bare(text: str) -> str:
    """A word as matched without its vowels: every mark off."""
    return _MARKS.sub("", pointed(text))


def is_pointed(text: str) -> bool:
    return bare(text) != pointed(text)


@dataclass(frozen=True)
class Licence:
    """One of the two licences that pass, as the credits say it."""

    name: str
    url: str

    @property
    def attribution_required(self) -> bool:
        return self.name != "CC0"


def licence(meta: Mapping[str, Any]) -> Licence | None:
    """The file's licence if it is CC0 or CC BY-SA, else None.

    Read off the file's own description page (`extmetadata`), never off its speaker:
    `License` is the template Commons parsed (`cc0`, `cc-by-sa-4.0`), and the short name
    and URL are what the credits print.
    """

    def value(key: str) -> str:
        entry = meta.get(key)
        return str(entry.get("value") or "") if isinstance(entry, Mapping) else ""

    code = value("License").strip().lower()
    short = html.unescape(_TAGS.sub("", value("LicenseShortName"))).strip()
    url = value("LicenseUrl").strip()
    if url.startswith("//"):
        url = "https:" + url
    if code == "cc0":
        return Licence("CC0", url or "https://creativecommons.org/publicdomain/zero/1.0/")
    found = re.fullmatch(r"cc-by-sa-(\d\.\d)", code)
    if found:
        version = found.group(1)
        return Licence(
            short or f"CC BY-SA {version}",
            url or f"https://creativecommons.org/licenses/by-sa/{version}/",
        )
    return None


def speaker(meta: Mapping[str, Any], title: str) -> str:
    """Who said it: the description page's "Speaker:", else the name in the file's title."""
    entry = meta.get("Artist")
    artist = str(entry.get("value") or "") if isinstance(entry, Mapping) else ""
    found = _SPEAKER.search(artist)
    if found:
        return html.unescape(found.group("name")).strip()
    parsed = _TITLE.match(title)
    return parsed.group("rest").split("-", 1)[0] if parsed else ""


def word_of(title: str, said_by: str) -> str:
    """The word a file is named by, or "" for a title that is not Lingua Libre's."""
    parsed = _TITLE.match(unicodedata.normalize("NFC", title.replace("_", " ")))
    if not parsed:
        return ""
    rest = parsed.group("rest")
    if said_by and rest.startswith(said_by + "-"):
        return rest[len(said_by) + 1 :].strip()
    return rest.split("-", 1)[1].strip() if "-" in rest else ""


@dataclass(frozen=True)
class Recording:
    """One person saying one word, as the manifest keeps it."""

    word: str
    file: str
    title: str
    page: str
    licence: str
    licence_url: str
    speaker: str
    source: str = ""
    sha1: str = ""
    seconds: float = 0.0

    @property
    def attribution(self) -> str:
        """The credit for the file, as BY-SA asks for it: title, author, source, licence."""
        name = self.title.removeprefix("File:")
        return f"“{name}” by {self.speaker}, Lingua Libre, Wikimedia Commons, {self.licence}"

    def path(self, language: str = "he") -> Path:
        return folder(language) / self.file


@dataclass
class Manifest:
    """Every recording kept for one language, and what was left out and why."""

    language: str
    fetched: str = ""
    recordings: list[Recording] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        data = {
            "source": SOURCE,
            "language": self.language,
            "fetched": self.fetched,
            "skipped": dict(sorted(self.skipped.items())),
            "recordings": [
                {**asdict(one), "attribution": one.attribution} for one in self.recordings
            ],
        }
        return json.dumps(data, ensure_ascii=False, indent=1) + "\n"

    @classmethod
    def from_json(cls, raw: str) -> Manifest:
        data = json.loads(raw)
        names = set(Recording.__dataclass_fields__)
        return cls(
            language=str(data.get("language") or "he"),
            fetched=str(data.get("fetched") or ""),
            skipped={str(k): int(v) for k, v in (data.get("skipped") or {}).items()},
            recordings=[
                Recording(**{k: v for k, v in one.items() if k in names})
                for one in data.get("recordings") or []
            ],
        )


def load(language: str = "he") -> Manifest | None:
    """The manifest kept for a language, or None where nothing has been fetched."""
    path = manifest_path(language)
    try:
        return Manifest.from_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


class Index:
    """Which recording says a word: the exact pointed form first, then the bare form where
    one pointed word has it.

    A pointed word that matches no file is not looked up bare: its vowels say which word
    it is, and a file of another word with the same letters would say the wrong one. A
    bare word (modern text is written bare) takes the file only where the letters belong
    to a single recorded word; where two recorded words share them (סֵפֶר and סַפָּר), the
    voice says it as before.
    """

    def __init__(self, recordings: Iterable[Recording]) -> None:
        listed = list(recordings)
        counts = Counter(one.speaker for one in listed)

        def rank(one: Recording) -> tuple[int, int, str]:
            # CC0 first (nothing asked of it), then the speaker with most words (one
            # voice across a card's words), then by title, so the choice never wavers.
            return (one.licence != "CC0", -counts[one.speaker], one.title)

        self.by_pointed: dict[str, Recording] = {}
        for one in sorted(listed, key=rank):
            self.by_pointed.setdefault(pointed(one.word), one)
        self.by_bare: dict[str, set[str]] = {}
        for key in self.by_pointed:
            self.by_bare.setdefault(bare(key), set()).add(key)

    def match(self, text: str) -> tuple[Recording | None, str]:
        """The recording for a word and how it was found: "pointed", "bare", "ambiguous"
        (bare, and more than one word has those letters) or "none"."""
        key = pointed(text)
        if not key or not _HEBREW.search(key):
            return None, "none"
        if key in self.by_pointed:
            return self.by_pointed[key], "pointed"
        if is_pointed(key):
            return None, "none"
        candidates = self.by_bare.get(key, set())
        if len(candidates) == 1:
            return self.by_pointed[next(iter(candidates))], "bare"
        return None, "ambiguous" if candidates else "none"


@cache
def _index(language: str, where: str, stamp: float, size: int) -> Index | None:
    manifest = load(language)
    return Index(manifest.recordings) if manifest else None


def index(language: str = "he") -> Index | None:
    """The index for a language, read again whenever its manifest changes on disk, so a
    copy deployed to the box is heard without a restart."""
    path = manifest_path(language)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _index(language, str(path), stat.st_mtime, stat.st_size)


def find(text: str, language: str = "he") -> Recording | None:
    """The person's recording of this word, if there is one and its file is on disk."""
    code = (language or "").split("-")[0].lower()
    if code not in CATEGORIES:
        return None
    found = index(code)
    if found is None:
        return None
    one, _how = found.match(text)
    if one is None or not one.path(code).is_file():
        return None
    return one


# --- credits ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Speaker:
    """One person on the credits page: their name, licence, and the words they said."""

    name: str
    licence: str
    licence_url: str
    recordings: tuple[Recording, ...]


def credits(language: str = "he") -> list[Speaker]:
    """Every speaker whose recordings targum keeps, most words first, with each file:
    what `/credits` lists. A speaker under two licences is two rows."""
    manifest = load(language)
    if manifest is None:
        return []
    groups: dict[tuple[str, str, str], list[Recording]] = {}
    for one in manifest.recordings:
        if one.path(language).is_file():
            groups.setdefault((one.speaker, one.licence, one.licence_url), []).append(one)
    rows = [
        Speaker(name, name_licence, url, tuple(sorted(found, key=lambda r: r.word)))
        for (name, name_licence, url), found in groups.items()
    ]
    return sorted(rows, key=lambda row: (-len(row.recordings), row.name, row.licence))


# --- fetching (the laptop, once) ---------------------------------------------------------

#: A GET to Commons: (url) -> body. Swapped for a fake in the tests, which never connect.
Get = Callable[[str], bytes]


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - https only
        body: bytes = response.read()
    return body


def pages(category: str, get: Get = _get, pause: float = PAUSE) -> Iterable[dict[str, Any]]:
    """Every file in a category with its licence, author, size and MP3 copy, fifty at a
    time, one request a `pause`."""
    params: dict[str, str] = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "categorymembers",
        "gcmtitle": category,
        "gcmtype": "file",
        "gcmlimit": "50",
        "prop": "imageinfo|videoinfo",
        "iiprop": "url|sha1|extmetadata",
        "iiextmetadatafilter": "License|LicenseShortName|LicenseUrl|Artist",
        "viprop": "derivatives",
    }
    carry: dict[str, str] = {}
    while True:
        url = API + "?" + urllib.parse.urlencode({**params, **carry})
        data = json.loads(get(url))
        yield from (data.get("query") or {}).get("pages") or []
        follow = data.get("continue")
        if not isinstance(follow, dict):
            return
        carry = {str(k): str(v) for k, v in follow.items()}
        time.sleep(pause)


def read(page: Mapping[str, Any], language: str = "he") -> tuple[Recording | None, str]:
    """One Commons file as a recording, or None and why it was left out."""
    title = str(page.get("title") or "")
    infos = page.get("imageinfo") or []
    info = infos[0] if infos and isinstance(infos[0], Mapping) else {}
    meta = info.get("extmetadata") or {}
    said_by = speaker(meta, title)
    word = word_of(title, said_by)
    if not word:
        return None, "not-lingualibre"
    if language == "he" and not _HEBREW.search(word):
        return None, "not-hebrew"
    found = licence(meta)
    if found is None:
        return None, "licence"
    videos = page.get("videoinfo") or []
    derived = (
        videos[0].get("derivatives") if videos and isinstance(videos[0], Mapping) else []
    ) or []
    mp3 = next(
        (
            str(d.get("src"))
            for d in derived
            if isinstance(d, Mapping) and d.get("type") == "audio/mpeg"
        ),
        "",
    )
    original = str(info.get("url") or "").split("?", 1)[0]
    source = mp3 or original
    if not source:
        return None, "no-file"
    sha1 = str(info.get("sha1") or "")
    suffix = ".mp3" if mp3 else Path(urllib.parse.urlparse(original).path).suffix.lower()
    return (
        Recording(
            word=unicodedata.normalize("NFC", word),
            file=f"{(sha1 or str(page.get('pageid') or ''))[:16]}{suffix}",
            title=title,
            page=str(info.get("descriptionurl") or ""),
            licence=found.name,
            licence_url=found.url,
            speaker=said_by,
            source=source,
            sha1=sha1,
            seconds=float(info.get("duration") or 0.0),
        ),
        "",
    )


def fetch(
    language: str = "he",
    *,
    get: Get = _get,
    pause: float = PAUSE,
    download: bool = False,
    say: Callable[[str], None] = print,
) -> Manifest:
    """Read the category, write the manifest, and with `download` copy each file not
    already on disk. The manifest is written before any file is, so a run stopped
    half-way has lost nothing it read; a file already kept is not fetched again."""
    from .paths import write_atomic

    manifest = Manifest(language=language, fetched=date.today().isoformat())
    skipped: Counter[str] = Counter()
    for page in pages(CATEGORIES[language], get=get, pause=pause):
        one, why = read(page, language)
        if one is None:
            skipped[why] += 1
            continue
        manifest.recordings.append(one)
    manifest.recordings.sort(key=lambda r: (r.word, r.speaker, r.title))
    manifest.skipped = dict(skipped)
    write_atomic(manifest_path(language), manifest.to_json())
    say(f"{len(manifest.recordings)} recordings kept, skipped: {dict(skipped) or 'none'}")
    if download:
        made = 0
        for one in manifest.recordings:
            path = one.path(language)
            if path.is_file() and path.stat().st_size:
                continue
            body = get(one.source)
            part = path.with_name(path.name + ".part")
            part.write_bytes(body)
            part.replace(path)
            made += 1
            if made % 200 == 0:
                say(f"{made} files downloaded")
            time.sleep(pause)
        say(f"{made} files downloaded")
    return manifest


def coverage(found: Index, lemmas: Iterable[str]) -> Counter[str]:
    """How the lemmas are matched: "pointed", "bare", "ambiguous" or "none" each."""
    return Counter(found.match(lemma)[1] for lemma in lemmas)
