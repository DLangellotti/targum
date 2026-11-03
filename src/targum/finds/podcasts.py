"""The nightly round over Hebrew podcasts (targum-internal#621; plan §1.3; David,
2026-10-31).

New episodes of a reviewed list of Hebrew shows (`podcasts.json` beside this file, each
with its licence and what its robots.txt said), scored on what was said in them, so Home's
card and "More that fit you" can offer them as `podcast` finds. Any licence: a find is
personal reading, built as the reader's own import when they press Listen
(`serve.Handler._open_find`, a pasted link's press on the episode's audio, on their
credits), and never shelved.

One round, on a timer on the box (`targum finds podcasts`, `targum-finds-podcasts.timer`):

1. **The feeds**, each read once, direct, after its robots.txt says yes (`robots`). The
   newest `PER_FEED` episodes of the last thirty days that the pool does not hold yet,
   past a gate that costs nothing: one the feed marks explicit, one under three minutes
   or over two hours or of no stated length, one whose title or summary the screen
   refuses (`screen.passes`), and one whose audio host's robots.txt says no are dropped.
2. **A transcript first.** Where the feed points at an SRT or VTT transcript
   (`podcast:transcript`), its words are read and scored, which costs nothing.
3. **Otherwise two minutes from the middle.** A stretch of the audio is asked for by
   byte range (`ingest.url.window`), never the episode; two minutes of it are cut and
   transcribed by whisper (`transcribe.openai_whisper`) on targum's budget, at about 1.2¢,
   at most `DAY_SAMPLES` a day and `MONTH_SAMPLES` a month, and inside
   `TARGUM_FINDS_BUDGET_USD` with the other sources. The cap stops the sampling and says
   so on the round; an episode left over is not pooled, so one never measured is never
   offered, and a later night may still sample it.
4. **Scored and let go.** The words are screened again, scored (`score.Forms.score`)
   and dropped with the folder they were in: the pool keeps the lemma counts and the
   words a minute heard (`pool.add`, `rate`), never a transcript and never a sound.

**Off unless the box says so** (`TARGUM_FINDS_PODCASTS`): the timer runs every night and
does nothing until then.

**Counted into the language tables as counts** (David, 2026-11-01): the nightly sweep
folds each kept episode's lemma counts into the `podcasts` register (`tables.finds`),
never its words, which were never kept.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import chips, news, pool, screen
from . import score as score_module
from .robots import ROBOTS, Robots

if TYPE_CHECKING:
    from ..accounts import Store

log = logging.getLogger(__name__)

FLAG = "TARGUM_FINDS_PODCASTS"

SOURCE = "podcast"

#: The reviewed list of shows, shipped with the code.
SHOWS = Path(__file__).with_name("podcasts.json")

#: The newest episodes a show offers a night, of those the pool does not hold yet.
PER_FEED = 2

#: How far back an episode counts as new, in days, and how long a find stays (`pool`).
FRESH_DAYS = 30

#: An episode under three minutes is a trailer; over two hours is past a sitting.
MIN_SECONDS = 3 * 60
MAX_SECONDS = 2 * 60 * 60

#: How much is transcribed of an episode with no transcript, from its middle.
SAMPLE_SECONDS = 120

#: The most samples a day and a month: 30 a night and 600 a month (David, 2026-11-03;
#: plan §1.3 and §4 began at 10 and 300). At 1.2¢ a sample that is at most 36¢ a night and
#: $7.20 a month, inside `TARGUM_FINDS_BUDGET_USD` with the other sources.
DAY_SAMPLES = 30
MONTH_SAMPLES = 600

#: The transcriber the samples go to: whisper, the box's own (memory "Box transcribes with
#: OpenAI whisper"), the cheaper of the two priced ones.
TRANSCRIBER = "openai/whisper-1"

#: Bytes a second of audio, where the feed states no size to divide by: 128 kbps, the
#: commonest podcast rate.
BYTES_A_SECOND = 16_000

#: Seconds read either side of the two minutes, so the cut lands on whole frames.
PAD_SECONDS = 10

#: Samples not heard in a row (the audio would not come, or ffmpeg could not cut it)
#: after which a round stops sampling.
UNHEARD_MOST = 5

#: A show's words, a minute: speech under this is mostly music, and is not offered.
LEAST_RATE = 30.0

#: The languages a round runs for: those the scorer has a map for.
LANGUAGES = ("he",)

_TIMED_TYPES = ("application/x-subrip", "application/srt", "text/srt", "text/vtt")


def on() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


def whisper_usd_a_minute() -> float:
    from ..transcribe import PRICES

    return float(PRICES.get(TRANSCRIBER, 0.006))


def sample_cost() -> float:
    """What one sample costs targum in dollars, at whisper's list price."""
    return SAMPLE_SECONDS / 60 * whisper_usd_a_minute()


# -- the shows -----------------------------------------------------------------------


@dataclass(frozen=True)
class Show:
    key: str
    name: str
    publisher: str
    feed: str
    #: What the card names as the site; the feed's own site where the list gives none.
    site: str
    #: What an episode of it carries in its `topics`: `chips.tag` of each chip code.
    tags: tuple[str, ...] = ()
    licence: str = ""
    language: str = "he"


def _show(row: dict[str, Any]) -> Show | None:
    from ..chat.sources import site

    feed = str(row.get("feed") or "")
    if not row.get("key") or not feed.startswith(("http://", "https://")):
        return None
    codes = [str(code) for code in row.get("chips") or () if str(code) in chips.BY_CODE]
    return Show(
        key=str(row["key"]),
        name=str(row.get("name") or row["key"]),
        publisher=str(row.get("publisher") or ""),
        feed=feed,
        site=str(row.get("site") or site(feed)),
        tags=tuple(chips.tag(code) for code in codes),
        licence=str(row.get("licence") or ""),
        language=str(row.get("language") or "he"),
    )


def shows(path: Path | None = None) -> list[Show]:
    """The reviewed shows, in the list's order, then any `kind: podcast` publisher the
    box's sources.json adds (a curator's later approval) that the list does not have."""
    from ..chat import sources

    out: list[Show] = []
    try:
        listed = json.loads((path or SHOWS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        listed = {}
    for row in listed.get("feeds") or () if isinstance(listed, dict) else ():
        if isinstance(row, dict):
            made = _show(row)
            if made is not None:
                out.append(made)
    held = {show.feed for show in out}
    for publisher in sources.load():
        if publisher.kind != "podcast" or not publisher.feed or publisher.feed in held:
            continue
        made = _show(
            {
                "key": publisher.key,
                "name": publisher.name,
                "publisher": publisher.publisher,
                "feed": publisher.feed,
                "site": sources.site(publisher.homepage or publisher.feed),
                "licence": publisher.licence,
                "language": publisher.language,
            }
        )
        if made is not None:
            out.append(made)
            held.add(made.feed)
    return out


# -- the episodes --------------------------------------------------------------------


@dataclass
class Episode:
    """One new episode through the gate, waiting to be heard."""

    show: Show
    audio: str
    title: str
    published: int
    seconds: float
    #: The enclosure's stated size in bytes, or 0.
    length: int = 0
    transcript: str = ""
    transcript_type: str = ""

    @property
    def url(self) -> str:
        """The address the pool holds and Listen builds from: the episode's audio, as a
        subscription's item is (`subscriptions.podcast_item`)."""
        from ..weekly.feeds import link_key

        return link_key(self.audio)

    @property
    def timed(self) -> bool:
        """Whether the feed's transcript has timings, which is the kind that is read."""
        if not self.transcript:
            return False
        suffix = self.transcript.lower().split("?", 1)[0].rsplit(".", 1)[-1]
        return self.transcript_type.lower() in _TIMED_TYPES or suffix in ("srt", "vtt")


def gate(item: Any, show: Show, robots: Robots) -> str:
    """Why an episode is dropped before anything of it is fetched, or ""."""
    if getattr(item, "explicit", False):
        return "age"
    seconds = float(getattr(item, "seconds", 0) or 0)
    if not MIN_SECONDS <= seconds <= MAX_SECONDS:
        return "gate"
    why = screen.passes(show.site, str(item.title or ""), str(item.summary or ""))
    if why:
        return why
    if not robots.allowed(str(item.enclosure)):
        return "robots"
    return ""


@dataclass(frozen=True)
class Heard:
    """What was said in an episode: the words, how many seconds they took, and what
    hearing them cost targum in dollars."""

    text: str = ""
    seconds: float = 0.0
    cost: float = 0.0

    @property
    def rate(self) -> float:
        """Words a minute."""
        if self.seconds <= 0:
            return 0.0
        return len(self.text.split()) / (self.seconds / 60)


#: A feed's body, from its address.
Pull = Callable[[str], bytes]
#: A transcript's text, from its address.
Read = Callable[[str], str]
#: Two minutes of an episode, transcribed.
Hear = Callable[[Episode], Heard]


def pull(feed: str) -> bytes:
    """A feed, through the door, direct: a feed is for any podcast app to read."""
    from ..ingest.url import fetch

    got = fetch(feed, proxy=False)
    return got.raw or got.text.encode("utf-8")


def read(url: str) -> str:
    from ..ingest.url import fetch

    return fetch(url, proxy=False).text


def from_transcript(text: str) -> Heard:
    """An SRT or VTT transcript's words, and the seconds from its first cue to its last."""
    from ..ingest.base import normalize
    from ..ingest.subtitles import parse

    cues = parse(normalize(text))
    if not cues:
        return Heard()
    words = "\n".join(cue.text for cue in cues if cue.text.strip())
    return Heard(text=words, seconds=max(0.0, cues[-1].end - cues[0].start))


#: The share of a transcript's words that must be in the show's script for it to be read
#: as the episode's words, rather than a machine's guess in another language.
LEAST_IN_SCRIPT = 0.6


def in_language(text: str, episode: Episode) -> bool:
    """Whether a transcript is written in the show's language's letters, mostly."""
    import re

    from ..video.discover import SCRIPTS

    letters = SCRIPTS.get(score_module.code(episode.show.language))
    words = text.split()
    if not letters or not words:
        return bool(words)
    written = sum(1 for word in words if re.search(f"[{letters}]", word))
    return written / len(words) >= LEAST_IN_SCRIPT


def window_of(episode: Episode) -> tuple[int, int, float]:
    """Where the two minutes are in the file: the first byte to ask for, how many, and
    the seconds into that stretch the cut starts. The middle of the episode, by the
    feed's own size over its own length, or a common bit rate where it gives no size."""
    rate = BYTES_A_SECOND
    if episode.length > 0 and episode.seconds > 0:
        rate = max(4_000, int(episode.length / episode.seconds))
    wanted = max(0.0, episode.seconds / 2 - SAMPLE_SECONDS / 2)
    begin = max(0.0, wanted - PAD_SECONDS)
    lead = wanted - begin
    return int(begin * rate), int((lead + SAMPLE_SECONDS + PAD_SECONDS) * rate), lead


def ready() -> str:
    """Why no sample can be heard on this machine, or ""."""
    from ..transcribe.openai_whisper import WhisperTranscriber

    able, why = WhisperTranscriber().available()
    return "" if able else f"no transcriber ({why})"


class Unheard(Exception):  # noqa: N818 - a sample that was not heard, not an error class
    """A sample that could not be heard, and at which step: `fetch` (the stretch of audio),
    `cut` (ffmpeg on it) or `transcriber` (whisper). `why` is short enough for a log line
    and a run's note.

    A `transcriber` refusal is targum's, not the episode's: on 2026-11-02 the first run on
    the box had all ten samples refused by OpenAI with a 429, `credit_balance_exhausted`,
    and the round dropped ten good episodes as unreadable and counted them against the
    day's cap. It now stops the sampling, says why, and leaves the episodes for another
    night. Nothing is charged for a refusal."""

    def __init__(self, where: str, why: str) -> None:
        super().__init__(f"{where}: {why}")
        self.where = where
        self.why = why


def _why(error: BaseException) -> str:
    """One line of what went wrong: a provider's own code where it gave one, ffmpeg's last
    words, or the error itself."""
    import re

    hint = str(getattr(error, "hint", "") or "")
    said = hint or str(error)
    status = re.match(r"(\w+ \d{3})", said)
    code = re.search(r'"code"\s*:\s*"([^"]+)"', said)
    if status and code:
        return f"{status.group(1)} {code.group(1)}"
    cause = error.__cause__
    stderr = getattr(cause, "stderr", b"") if cause is not None else b""
    if isinstance(stderr, bytes) and stderr.strip():
        last = stderr.decode("utf-8", "replace").strip().splitlines()[-1]
        return f"{error}: {last}"[:200]
    return " ".join(said.split())[:200] or type(error).__name__


def hear(episode: Episode) -> Heard:
    """Two minutes from the middle of an episode, transcribed by whisper, in a folder
    that is then deleted with the sound and the words in it. Raises `Unheard`, naming the
    step that failed."""
    from ..audio import tools
    from ..ingest.url import window
    from ..transcribe.openai_whisper import WhisperTranscriber

    start, most, lead = window_of(episode)
    with tempfile.TemporaryDirectory(prefix="targum-podcast-") as folder:
        stretch = Path(folder) / "stretch.mp3"
        try:
            window(episode.audio, stretch, start, most)
        except Exception as error:
            raise Unheard("fetch", _why(error)) from error
        sample = Path(folder) / "sample.mp3"
        try:
            tools.cut(stretch, sample, lead, lead + SAMPLE_SECONDS)
        except Exception as error:
            raise Unheard("cut", _why(error)) from error
        try:
            heard = WhisperTranscriber().transcribe(sample, "he", hint=episode.title)
        except Exception as error:
            raise Unheard("transcriber", _why(error)) from error
        text = " ".join(word.text for word in heard.words if word.text.strip())
        seconds = float(heard.duration or 0.0)
        return Heard(text=text, seconds=seconds, cost=seconds / 60 * whisper_usd_a_minute())


# -- one round ----------------------------------------------------------------------


@dataclass
class Round(news.Round):
    """What one night did, with the samples it heard and the transcripts it read."""

    sampled: int = 0
    transcripts: int = 0
    feeds: int = 0
    failed: int = 0
    left: list[str] = field(default_factory=list)
    #: Samples not heard, by step and reason ("fetch: HTTP 403"), for the run's note.
    unheard: Counter[str] = field(default_factory=Counter)

    def __str__(self) -> str:
        return (
            f"{super().__str__()}, {self.feeds} feeds read"
            + (f" ({self.failed} failed)" if self.failed else "")
            + f", {self.transcripts} transcripts, {self.sampled} samples"
            + (
                "; not heard: " + "; ".join(f"{n} × {why}" for why, n in self.unheard.items())
                if self.unheard
                else ""
            )
        )


def sampled_since(store: Store, since: int) -> int:
    """Samples the rounds started since `since` have heard: off their own rows."""
    total = 0
    for (note,) in store.db.execute(
        "SELECT note FROM find_run WHERE source = ? AND started >= ?", (SOURCE, since)
    ):
        try:
            said = json.loads(note or "{}")
        except ValueError:
            continue
        if isinstance(said, dict):
            total += int(said.get("sampled") or 0)
    return total


def _start(store: Store) -> int:
    """Where tonight's shows start: one on from where the last round started, so the
    samples a cap leaves over fall to a different show each night."""
    row = store.db.execute(
        "SELECT note FROM find_run WHERE source = ? AND finished > 0 ORDER BY id DESC LIMIT 1",
        (SOURCE,),
    ).fetchone()
    try:
        said = json.loads(row[0] or "{}") if row else {}
    except ValueError:
        said = {}
    return int(said.get("next") or 0) if isinstance(said, dict) else 0


def refresh(
    store: Store,
    *,
    listed: Sequence[Show] | None = None,
    pull: Pull = pull,
    read: Read = read,
    hear: Hear = hear,
    ready: Callable[[], str] = ready,
    robots: Robots = ROBOTS,
    forms_for: Callable[[str], score_module.Forms | None] = score_module.load,
    at: int | None = None,
) -> Round:
    """One night: read the feeds, gate, score each new episode on its transcript or a
    sample, and pool what passes. Each episode is written as it is done, and each
    sample's cost as it is spent, so a killed round has kept what it found and said
    what it cost."""
    from ..weekly import feeds

    when = pool.now_ms() if at is None else at
    pool.expire(store, when)
    found = Round()
    every = list(shows() if listed is None else listed)
    run = pool.start_run(store, SOURCE, when)
    start = _start(store)
    note: dict[str, Any] = {"next": (start + 1) % max(1, len(every))}

    def checkpoint() -> None:
        note.update(sampled=found.sampled, transcripts=found.transcripts, feeds=found.feeds)
        if found.unheard:
            note["unheard"] = dict(found.unheard)
        pool.finish_run(
            store,
            run,
            seen=found.seen,
            kept=found.kept,
            dropped=found.dropped,
            note={**note, **({"stopped": found.stopped} if found.stopped else {})},
            at=when,
        )

    def dropped(url: str, why: str, show: Show) -> None:
        found.dropped[why] += 1
        pool.drop(
            store,
            language=score_module.code(show.language),
            source=SOURCE,
            url=url,
            reason=why,
            host=show.site,
            at=when,
        )

    maps: dict[str, score_module.Forms | None] = {}

    def forms_of(language: str) -> score_module.Forms | None:
        code = score_module.code(language)
        if code not in maps:
            maps[code] = forms_for(code) if code in score_module.POOLED else None
        return maps[code]

    # -- the feeds: each show's newest new episodes, through the gate --
    fresh_after = when - FRESH_DAYS * pool.DAY_MS
    by_show: list[list[Episode]] = []
    at_show = start % len(every) if every else 0
    for show in [*every[at_show:], *every[:at_show]]:
        if forms_of(show.language) is None:
            continue
        if not robots.allowed(show.feed):
            found.dropped["robots"] += 1
            continue
        try:
            body = pull(show.feed)
        except Exception as error:  # noqa: BLE001 - one feed down is not the round down
            log.info("finds: the feed of %s did not answer: %s", show.key, error)
            found.failed += 1
            continue
        found.feeds += 1
        mine: list[Episode] = []
        dated = [
            (int(item.published.timestamp() * 1000), item)
            for item in feeds.parse(body)
            if item.enclosure and item.published is not None
        ]
        dated.sort(key=lambda pair: pair[0], reverse=True)
        for published, item in dated:
            if len(mine) >= PER_FEED:
                break
            if published < fresh_after:
                break
            episode = Episode(
                show=show,
                audio=item.enclosure,
                title=item.title,
                published=published,
                seconds=float(item.seconds or 0),
                length=int(getattr(item, "length", 0) or 0),
                transcript=item.transcript,
                transcript_type=item.transcript_type,
            )
            if pool.known(store, episode.url):
                continue
            found.seen += 1
            why = gate(item, show, robots)
            if why:
                dropped(episode.url, why, show)
                continue
            mine.append(episode)
        by_show.append(mine)
    checkpoint()

    # -- one from each show in turn, so every show has its share of the samples --
    queue: list[Episode] = []
    while any(by_show):
        for mine in by_show:
            if mine:
                queue.append(mine.pop(0))

    day_from = (when // pool.DAY_MS) * pool.DAY_MS
    day_room = max(0, DAY_SAMPLES - sampled_since(store, day_from))
    month_room = max(0, MONTH_SAMPLES - sampled_since(store, pool.month_from(when)))
    why_not = ""
    #: Samples tried since the last one heard: a host or ffmpeg failing every time stops
    #: the round's sampling rather than walking the whole queue.
    tries = 0

    def may_sample() -> str:
        """Why no more samples tonight, or ""."""
        nonlocal why_not
        if why_not:
            return why_not
        if tries >= UNHEARD_MOST:
            why_not = f"{UNHEARD_MOST} samples not heard in a row"
        elif found.sampled >= month_room:
            why_not = f"the month's {MONTH_SAMPLES} samples"
        elif found.sampled >= day_room:
            why_not = f"the day's {DAY_SAMPLES} samples"
        elif pool.left(store, when) < sample_cost():
            why_not = "the month's discovery budget"
        else:
            why_not = ready()
        return why_not

    for episode in queue:
        forms = forms_of(episode.show.language)
        assert forms is not None
        heard: Heard | None = None
        if episode.timed and robots.allowed(episode.transcript):
            try:
                heard = from_transcript(read(episode.transcript))
            except Exception as error:  # noqa: BLE001 - no transcript is a sample's turn
                log.info("finds: no transcript for %s: %s", episode.url, error)
                heard = None
            if heard is not None and heard.text.strip() and in_language(heard.text, episode):
                found.transcripts += 1
            else:
                # None, empty, or in another language: Buzzsprout's machine transcripts of
                # Hebrew shows came back in English (2026-11-02). A sample's turn.
                heard = None
        if heard is None:
            if may_sample():
                # Not pooled and not dropped: a later night may still hear it.
                found.left.append(episode.url)
                continue
            found.fetched += 1
            try:
                heard = hear(episode)
            except Exception as error:  # noqa: BLE001 - one episode never stops a round
                unheard = error if isinstance(error, Unheard) else Unheard("other", _why(error))
                found.unheard[f"{unheard.where}: {unheard.why}"] += 1
                log.warning("finds: no sample of %s: %s", episode.url, unheard)
                if unheard.where == "transcriber":
                    # targum's refusal, not the episode's: nothing heard, nothing charged,
                    # nothing counted against the cap, and the episode waits.
                    why_not = f"the transcriber refused ({unheard.why})"
                    found.left.append(episode.url)
                else:
                    tries += 1
                    dropped(episode.url, "unreadable", episode.show)
                checkpoint()
                continue
            # Only a sample whisper heard counts against the day's and the month's caps.
            found.sampled += 1
            tries = 0
            found.spent += heard.cost
            pool.spend(store, run, heard.cost)
        _keep(store, episode, heard, forms, found, dropped, when)
        checkpoint()
    if found.left and why_not:
        found.stopped = why_not
    note["left"] = len(found.left)
    checkpoint()
    return found


def _keep(
    store: Store,
    episode: Episode,
    heard: Heard,
    forms: score_module.Forms,
    found: Round,
    dropped: Callable[[str, str, Show], None],
    when: int,
) -> None:
    from ..chat.tools import credits_for

    show = episode.show
    if not heard.text.strip():
        dropped(episode.url, "short", show)
        return
    if screen.term_in(f"{episode.title}\n{heard.text}"):
        dropped(episode.url, "words", show)
        return
    if heard.rate and heard.rate < LEAST_RATE:
        dropped(episode.url, "short", show)
        return
    scored = forms.score(f"{episode.title}\n{heard.text}")
    if scored.tokens < news.LEAST_WORDS:
        dropped(episode.url, "short", show)
        return
    fingerprint = news.digest(heard.text)
    if pool.known_digest(store, fingerprint):
        dropped(episode.url, "same", show)
        return
    added = pool.add(
        store,
        language=score_module.code(show.language),
        source=SOURCE,
        url=episode.url,
        bag=scored.bag,
        tokens=scored.tokens,
        unresolved=scored.unresolved,
        rung=forms.rung_of(scored),
        digest=fingerprint,
        title=episode.title,
        host=show.site,
        publisher=show.name,
        published=episode.published,
        medium="podcast",
        seconds=episode.seconds,
        # What Listen will quote: a credit a minute of the episode (`Handler._open_find`
        # builds nothing where the quote is higher than the card).
        credits=credits_for(episode.seconds),
        topics=show.tags,
        rate=heard.rate,
        # The licence the show states for every episode, as the reviewed list records it
        # off its feed (design.md §12, 2026-11-02).
        licence=show.licence,
        licence_url=show.feed if show.licence else "",
        licence_from="publisher" if show.licence else "",
        at=when,
    )
    if added:
        found.kept += 1
