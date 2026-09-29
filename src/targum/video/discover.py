"""Finding Creative Commons videos worth curating, through YouTube's own search.

The curated shelf (`video/store.py`) has only ever been filled by hand: somebody finds a
video, reads its licence, runs `targum build --video` and `targum video curate`. That is
the right place for the judgement and the wrong place for the finding. The library is
thin at the bottom of the ladder in every language, and targum-internal#382 asks for a
hundred Easy texts in each of Hebrew, Russian, Italian and French (decided 2026-09-29),
which is more finding than a person does by hand.

**This finds and prices. It does not fetch, build or spend.** What it makes is a list —
title, channel, licence, length, link and what building each one would cost — for
somebody to approve before anything is bought. The build is still `targum build
--video`, and the curation is still `targum video curate` with its credit and licence
checked by hand. Nothing here writes to the shelf.

**The licence is asked twice, and the second answer is the one that counts.**
`search.list` takes `videoLicense=creativeCommon`, but a search filter is a ranking hint
over an index, not a statement about a video. So every hit is asked again through
`videos.list`, whose `status.license` is the video's own field, and anything that does
not say `creativeCommon` there is dropped. The same call is what says the video is
public, embeddable, finished and how long it runs.

**Which licence that is.** YouTube offers one Creative Commons licence, Attribution 3.0
Unported, and `creativeCommon` means that one. A description that names another version
is for the hand check at curation; this writes down what the field grants and no more.

**A third door, and a narrow one.** `ingest/url.py` is targum's door for what a reader
brings and `video/youtube.py` hands YouTube's addresses to yt-dlp. This opens neither.
It asks one literal https host — `www.googleapis.com` — two literal paths, with the key
and the query in the query string, the way `google.py` asks for a token: nothing in the
address comes from a reader, so there is nothing for a guard to vet. It runs on a
laptop, from the command line; the box never calls it.

**Quota is counted, not trusted.** The Data API's default is 10,000 units a day. A search
costs 100 and a `videos.list` of up to fifty ids costs 1, so one careless loop over four
languages and six topics would spend a day's allowance on its first run. A run is given
a budget, stops asking when the next search would overrun it, and says what it used.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from ..errors import OffHere, TargumError
from . import store, youtube

#: Where the key comes from. Kept in 1Password with the others and handed in by
#: `op run --env-file op.env`, never written into a file this repository carries.
KEY_ENV = "TARGUM_YOUTUBE_API_KEY"

#: The one host this module asks, and the two things it asks it.
API = "https://www.googleapis.com/youtube/v3"
SEARCH = f"{API}/search"
VIDEOS = f"{API}/videos"

#: What each call costs against the daily quota, from Google's published table.
SEARCH_UNITS = 100
VIDEOS_UNITS = 1
#: The default allowance for a project, per day.
DAILY_UNITS = 10_000
#: What one run may spend unless told otherwise: a fifth of the day, so a run can go
#: wrong four times and still leave the day's last one to find out why.
DEFAULT_BUDGET = 2_000

#: The most ids one `videos.list` call takes, and the most results one search returns.
PAGE = 50

#: The only licence value that passes, as `status.license` spells it.
CREATIVE_COMMONS = "creativeCommon"
LICENCE = "CC BY 3.0"
LICENCE_URL = "https://creativecommons.org/licenses/by/3.0/"

#: Under thirty seconds is a clip with nothing in it to read; over twenty minutes is
#: past where `videoDuration=medium` stops and past anything #382 is looking for. The
#: Easy spec wants three minutes or less, and a longer video is still kept (decided
#: 2026-09-29: "keep anything CC", shelved at its measured level), so the ceiling is
#: the search's, not the spec's.
MIN_SECONDS = 30
MAX_SECONDS = 20 * 60

#: The languages #382 names, with the codes YouTube may report each under. Hebrew is
#: still `iw` in older metadata, and a regional tag ("fr-CA") is the same language.
LANGUAGES: dict[str, tuple[str, ...]] = {
    "he": ("he", "iw"),
    "ru": ("ru",),
    "it": ("it",),
    "fr": ("fr",),
}

#: What to search for, in each language's own words. Everyday things, because the bottom
#: of the ladder is spoken, modern and about daily life — and a query in English ranks
#: videos *about* the language, which are lessons, not speech.
TOPICS: dict[str, tuple[str, ...]] = {
    "he": ("ולוג", "מתכון", "טיול", "שיחה", "יום בחיים", "קניות"),
    "ru": ("влог", "рецепт", "путешествие", "разговор", "один день из жизни", "покупки"),
    "it": ("vlog", "ricetta", "viaggio", "conversazione", "una giornata", "fare la spesa"),
    "fr": ("vlog", "recette", "voyage", "conversation", "une journée", "faire les courses"),
}

#: Where a language's batch is steered by subject rather than by topic alone: each
#: subject asks its own search terms and gets an even share of the count, so a batch can
#: be read — and balanced — by what it is about. Hebrew's four are everyday life in
#: Israel at the level an oleh arrives at (targum-internal#386, decided 2026-09-29): the
#: first unsteered run came back ten vlogs, none of them about any of this.
SUBJECTS: dict[str, dict[str, tuple[str, ...]]] = {
    "he": {
        "bureaucracy and money": (
            "ביטוח לאומי",
            "ארנונה",
            "משרד הפנים",
            "חשבון בנק",
            "חשבונות בית",
        ),
        "health": ("קופת חולים", "תור לרופא", "בית מרקחת", "הפניה לבדיקה"),
        "kids and school": ("גן ילדים", "אסיפת הורים", "בית ספר יסודי", "חוגים לילדים"),
        "home and work": (
            "שכירת דירה",
            "בעל הבית",
            "ועד בית",
            "תיקונים בבית",
            "תלוש משכורת",
            "ראיון עבודה",
        ),
    },
}

#: The search's own length bands, shortest first: `short` is under four minutes, which is
#: where the Easy spec's three sits, and `medium` is four to twenty. Each is its own
#: search, so each costs its own hundred units, and the short band is asked first.
DURATIONS = ("short", "medium")

#: One GET to the API: an address and its query in, the decoded answer out. A parameter
#: so the tests can answer from recorded responses and never reach a network.
Fetch = Callable[[str, Mapping[str, str]], dict[str, Any]]


class OverBudget(TargumError):
    """The next call would spend more quota than the run was given."""


@dataclass
class Quota:
    """What a run may spend, and what it has."""

    budget: int = DEFAULT_BUDGET
    used: int = 0

    def spend(self, units: int) -> None:
        if self.used + units > self.budget:
            raise OverBudget(
                f"That would take {self.used + units} quota units; this run was given "
                f"{self.budget}.",
                "Pass --quota to give it more. The day's default is 10,000.",
            )
        self.used += units

    def affords(self, units: int) -> bool:
        return self.used + units <= self.budget


@dataclass
class Candidate:
    """One video that passed every check, and what building it would cost."""

    id: str
    language: str
    title: str
    channel: str
    seconds: int
    home: str
    licence: str = LICENCE
    licence_url: str = LICENCE_URL
    #: The topic query that found it, so a batch can be read for what it is short of.
    found_by: str = ""
    #: Which of the language's `SUBJECTS` it was searched for, or "" where none steer.
    subject: str = ""
    transcription: float = 0.0
    translation: float = 0.0

    @property
    def cost(self) -> float:
        return self.transcription + self.translation


@dataclass
class Found:
    """A run's answer: what passed, what was dropped and why, and what it cost to ask."""

    candidates: list[Candidate] = field(default_factory=list)
    #: Why each dropped video was dropped, counted by reason.
    dropped: dict[str, int] = field(default_factory=dict)
    units: int = 0
    #: True when the budget ran out before every language had its count.
    short: bool = False

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    @property
    def total(self) -> float:
        return sum(candidate.cost for candidate in self.candidates)


def key() -> str:
    """The Data API key, or a refusal that says where one comes from."""
    held = os.environ.get(KEY_ENV, "").strip()
    if not held:
        raise OffHere(
            f"No YouTube Data API key: {KEY_ENV} is not set.",
            "It lives in 1Password; run this under `op run --env-file op.env -- ...`.",
        )
    return held


def fetch(address: str, query: Mapping[str, str], *, timeout: float = 20.0) -> dict[str, Any]:
    """One GET to the Data API. The only network call in this module."""
    if not address.startswith(API + "/"):
        raise TargumError(f"Discovery asks {API} and nothing else, not {address}.")
    request = urllib.request.Request(  # noqa: S310 - API is a literal https URL, checked above
        f"{address}?{urllib.parse.urlencode(query)}",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            loaded = json.loads(answer.read().decode("utf-8"))
    except Exception as error:  # noqa: BLE001 - every failure here is the same refusal
        raise TargumError(
            "YouTube's Data API did not answer.",
            "Check the key, and the day's quota in the Google Cloud console.",
        ) from error
    if not isinstance(loaded, dict):
        raise TargumError("YouTube's Data API answered with something that is not JSON.")
    return loaded


_DURATION = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")


def seconds(duration: str) -> int:
    """`PT3M12S` as 192. ISO 8601 as `contentDetails.duration` writes it; 0 if unread."""
    matched = _DURATION.match(duration or "")
    if not matched:
        return 0
    days, hours, minutes, secs = (int(part or 0) for part in matched.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + secs


def speaks(language: str, snippet: Mapping[str, Any]) -> bool:
    """Whether a video's own metadata allows it to be in `language`.

    Most uploads name no language at all, and those pass: the build hears the first
    minute before it buys the rest (`audio.LANGUAGE_PROBE_S`), which is the check that
    knows. What is refused is a video that says it is in something else.
    """
    said = str(snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage") or "")
    if not said:
        return True
    return said.split("-")[0].lower() in LANGUAGES[language]


def estimate(duration_s: int) -> tuple[float, float]:
    """USD to hear a video of this length and to put it into English, on the high side.

    The arithmetic the pipeline prices an imported recording with before it is heard
    (`Pipeline._audio_plan`), so the list David approves quotes the coin the build will
    charge: transcription by the minute at the dearer transcriber, the punctuation a
    paid hearing may come back without, and a translation guessed from a speech rate
    at the model a laptop build translates with.
    """
    from ..audio import SPEECH_WORDS_PER_MINUTE, TOKENS_PER_SPOKEN_WORD, WORDS_PER_SENTENCE
    from ..transcribe import PRICES
    from ..transcribe.refine import Punctuator
    from ..translate.anthropic_provider import AnthropicProvider

    minutes = duration_s / 60
    rate = max(PRICES.values()) if PRICES else 0.0
    hearing = minutes * (rate + (Punctuator().dollars_per_minute() if rate else 0.0))
    provider = AnthropicProvider()
    words = minutes * SPEECH_WORDS_PER_MINUTE
    batches = max(1, math.ceil(words / WORDS_PER_SENTENCE / provider.batch_size))
    translating = provider.estimate_from_counts(words * TOKENS_PER_SPOKEN_WORD, batches)
    return hearing, translating


def _search(
    get: Fetch, api_key: str, language: str, topic: str, duration: str, page: str
) -> tuple[list[str], str]:
    query = {
        "key": api_key,
        "part": "id",
        "type": "video",
        "q": topic,
        "videoLicense": CREATIVE_COMMONS,
        "videoEmbeddable": "true",
        "videoDuration": duration,
        "relevanceLanguage": language,
        "maxResults": str(PAGE),
        "safeSearch": "strict",
    }
    if page:
        query["pageToken"] = page
    answer = get(SEARCH, query)
    ids = [
        str(item.get("id", {}).get("videoId", ""))
        for item in answer.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    return ids, str(answer.get("nextPageToken", ""))


def _details(get: Fetch, api_key: str, ids: list[str]) -> list[dict[str, Any]]:
    """The second asking, for at most `PAGE` ids: `videos.list` refuses more with a 400.

    A search asked for fifty can answer with more — the first real Hebrew run came back
    with 53 (2026-09-29) — so the caller splits, and this refuses rather than trusts it.
    """
    if len(ids) > PAGE:
        raise TargumError(f"videos.list takes at most {PAGE} ids, not {len(ids)}.")
    answer = get(
        VIDEOS,
        {"key": api_key, "part": "status,contentDetails,snippet", "id": ",".join(ids)},
    )
    return list(answer.get("items", []))


def check(item: Mapping[str, Any], language: str) -> str:
    """Why this video cannot be a candidate, or "" when it can. The second asking."""
    status = item.get("status", {})
    snippet = item.get("snippet", {})
    if status.get("license") != CREATIVE_COMMONS:
        return "not Creative Commons"
    if status.get("privacyStatus") != "public":
        return "not public"
    if not status.get("embeddable", False):
        return "not embeddable"
    if status.get("uploadStatus", "processed") != "processed":
        return "not finished uploading"
    if snippet.get("liveBroadcastContent", "none") != "none":
        return "live or upcoming"
    length = seconds(str(item.get("contentDetails", {}).get("duration", "")))
    if length < MIN_SECONDS:
        return "too short"
    if length > MAX_SECONDS:
        return "too long"
    if not str(snippet.get("channelTitle", "")).strip():
        return "names nobody to credit"
    if not speaks(language, snippet):
        return "in another language"
    return ""


def _candidate(item: Mapping[str, Any], language: str, topic: str, subject: str) -> Candidate:
    """A video that passed `check`, priced."""
    length = seconds(str(item["contentDetails"]["duration"]))
    hearing, translating = estimate(length)
    snippet = item["snippet"]
    identifier = str(item["id"])
    return Candidate(
        id=identifier,
        language=language,
        title=str(snippet.get("title", "")),
        channel=str(snippet.get("channelTitle", "")),
        seconds=length,
        home=f"{youtube.WATCH}{identifier}",
        found_by=topic,
        subject=subject,
        transcription=round(hearing, 4),
        translation=round(translating, 4),
    )


def discover(
    languages: Iterable[str],
    count: int,
    *,
    budget: int = DEFAULT_BUDGET,
    get: Fetch | None = None,
    api_key: str | None = None,
    shelf: Iterable[str] | None = None,
) -> Found:
    """Up to `count` new candidates in each language, inside a quota budget.

    Topics are asked in turn, the short band before the medium, a page at a time, until
    the language has its count, the topics run out, or the next search would overrun the
    budget. A language in `SUBJECTS` is asked subject by subject instead, each held to an
    even share of the count, so one easy subject cannot fill the batch alone. Anything
    already on the shelf, or already found this run, is skipped before it is asked about
    again.
    """
    wanted = list(languages)
    for language in wanted:
        if language not in LANGUAGES:
            raise TargumError(
                f"No discovery for '{language}'.", f"One of: {', '.join(sorted(LANGUAGES))}."
            )
    api_key = api_key if api_key is not None else key()
    get = get or fetch
    held = set(store.every() if shelf is None else shelf)
    seen: set[str] = set()
    quota = Quota(budget=budget)
    found = Found()

    for language in wanted:
        if language in SUBJECTS:
            share = -(-count // len(SUBJECTS[language]))
            groups = [(name, terms, share) for name, terms in SUBJECTS[language].items()]
        else:
            groups = [("", TOPICS[language], count)]
        kept = 0
        for subject, terms, allowed in groups:
            limit = min(count, kept + allowed)
            for topic, duration in [(t, d) for t in terms for d in DURATIONS]:
                page = ""
                while kept < limit:
                    if not quota.affords(SEARCH_UNITS + VIDEOS_UNITS):
                        found.short = True
                        break
                    quota.spend(SEARCH_UNITS)
                    ids, page = _search(get, api_key, language, topic, duration, page)
                    fresh = []
                    for identifier in ids:
                        if identifier in held:
                            found.drop("already on the shelf")
                        elif identifier in seen:
                            found.drop("found twice")
                        else:
                            fresh.append(identifier)
                            seen.add(identifier)
                    details: list[dict[str, Any]] = []
                    for start in range(0, len(fresh), PAGE):
                        if start and not quota.affords(VIDEOS_UNITS):
                            found.short = True
                            break
                        quota.spend(VIDEOS_UNITS)
                        details += _details(get, api_key, fresh[start : start + PAGE])
                    for item in details:
                        if kept >= limit:
                            break
                        reason = check(item, language)
                        if reason:
                            found.drop(reason)
                            continue
                        found.candidates.append(_candidate(item, language, topic, subject))
                        kept += 1
                    if not page or found.short:
                        break
                if kept >= limit or found.short:
                    break
            if found.short:
                break
        if found.short:
            break
    found.units = quota.used
    return found


def _clock(total: int) -> str:
    return f"{total // 60}:{total % 60:02d}"


def table(found: Found) -> str:
    """The batch as a markdown table, to paste onto the issue for approval."""
    lines = [
        "| | lang | subject | title | channel | licence | length | est. cost | link |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for candidate in found.candidates:
        title = candidate.title.replace("|", "\\|")
        channel = candidate.channel.replace("|", "\\|")
        lines.append(
            f"| [ ] | {candidate.language} | {candidate.subject or '—'} | {title} | {channel} | "
            f"{candidate.licence} | "
            f"{_clock(candidate.seconds)} | ${candidate.cost:.2f} | {candidate.home} |"
        )
    lines.append("")
    minutes = sum(candidate.seconds for candidate in found.candidates) / 60
    lines.append(
        f"**{len(found.candidates)} candidates, {minutes:.0f} minutes, about "
        f"${found.total:.2f} to build all of them.** Quota used: {found.units} units."
    )
    return "\n".join(lines)


def to_json(found: Found) -> dict[str, Any]:
    return {
        "candidates": [
            asdict(candidate) | {"cost": candidate.cost} for candidate in found.candidates
        ],
        "dropped": found.dropped,
        "units": found.units,
        "short": found.short,
        "total": round(found.total, 4),
    }
