"""Everything that has to be true before a stranger is given the address.

A deployment fails in one of two places: at deploy, where nobody is watching and it costs
a minute, or at somebody's first sign-in, where it costs the only alpha reader there is.
This moves as much as possible into the first. Every check says what to do about itself,
because a check that only reports a state is a check somebody has to go and interpret.

Nothing here spends money or sends mail. It resolves and connects, and stops there.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

# Stanza and LaBSE are the bulk of it, and a box that fills up mid-build leaves a
# half-written reader behind. Five gigabytes is room for the models plus working space.
LEAST_DISK_GB = 5.0
SMTP_TIMEOUT = 5.0
# The minter is on the loopback and answers a ping out of memory. A second is
# generous; anything slower is a provider that is not going to serve a fetch either.
POT_TIMEOUT = 2.0


@dataclass(frozen=True)
class Check:
    """One thing that is true or is not, and what to do when it is not."""

    name: str
    ok: bool
    detail: str
    fix: str = ""
    # A warning is something that will work and probably should not ship: a fatal is
    # something that will present a reader with a broken product.
    fatal: bool = True

    @property
    def state(self) -> str:
        return "ok" if self.ok else ("FAIL" if self.fatal else "warn")


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _writable(path: Path) -> bool:
    """Whether we could actually put something there, rather than whether we may.

    `os.access` answers about permission bits and is wrong on a read-only mount, which
    is exactly the failure a deployment produces.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".targum-write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def check_address() -> Check:
    address = _env("TARGUM_PUBLIC_ADDRESS")
    if not address:
        return Check(
            "public address",
            False,
            "TARGUM_PUBLIC_ADDRESS is not set.",
            "Set TARGUM_PUBLIC_ADDRESS=https://targum.page. Sign-in links are built from "
            "it, and without it they point at the server's own loopback address.",
        )
    parsed = urlparse(address)
    if parsed.scheme != "https":
        return Check(
            "public address",
            False,
            f"{address} is not https.",
            "A sign-in link is a bearer token in a URL. Serve it over TLS.",
        )
    if not parsed.hostname:
        return Check("public address", False, f"{address} names no host.", "Use the full address.")
    return Check("public address", True, address)


def _hosted() -> bool:
    """Whether this is the box: `TARGUM_REQUIRE_ACCOUNT` set is what hosted means, and
    every check that needs to know reads it here so that no two of them can disagree."""
    return _env("TARGUM_REQUIRE_ACCOUNT").lower() in {"1", "true", "yes"}


def check_account_required() -> Check:
    if _hosted():
        return Check("hosted mode", True, "every route asks for an account")
    return Check(
        "hosted mode",
        False,
        "TARGUM_REQUIRE_ACCOUNT is not set.",
        "Set it to 1. Without it every signed-out visitor shares one home directory and "
        "reads everybody else's library.",
    )


def check_mail(connect: bool = True) -> list[Check]:
    """The four SMTP values, and whether the host is actually reachable from here.

    Reachability matters more than it looks: a provider that is fine from a laptop can be
    blocked outbound by a VPS host, and the symptom is a sign-in link that is never sent
    to a reader who is standing at a door that will not open.
    """
    host = _env("TARGUM_SMTP_HOST")
    if not host:
        return [
            Check(
                "email",
                False,
                "TARGUM_SMTP_HOST is not set.",
                "targum sends exactly one email and it is the whole product at the door. "
                "See the deployment runbook for Resend.",
            )
        ]
    out = [Check("email", True, f"{host} configured")]
    for name in ("TARGUM_SMTP_USER", "TARGUM_SMTP_PASSWORD", "TARGUM_SMTP_FROM"):
        if not _env(name):
            out.append(Check(f"email · {name}", False, "not set.", f"Set {name}."))
    if connect:
        port = int(_env("TARGUM_SMTP_PORT") or 587)
        try:
            with socket.create_connection((host, port), timeout=SMTP_TIMEOUT):
                out.append(Check("email · reachable", True, f"{host}:{port} answers"))
        except OSError as error:
            out.append(
                Check(
                    "email · reachable",
                    False,
                    f"cannot reach {host}:{port} — {error}",
                    "Some hosts block outbound SMTP by default. Check the provider's "
                    "firewall before blaming the credentials.",
                )
            )
    return out


def check_api_key() -> Check:
    if _env("ANTHROPIC_API_KEY"):
        return Check("api key", True, "present")
    # A warning, not a failure, and the reason is in its own text: without a key the
    # catalogue, the cache and every targum already built still work. Refusing to start
    # over this would take a working library offline to protect a feature.
    return Check(
        "api key",
        False,
        "ANTHROPIC_API_KEY is not set.",
        "Catalogue texts and everything already built still work; nothing new can be translated.",
        fatal=False,
    )


def check_ffmpeg() -> Check:
    """Whether audio can be imported at all. A warning: a box that reads only text is
    a working product, and the /add page simply does not offer what the box cannot do."""
    from .audio import ffmpeg_available

    usable, fix = ffmpeg_available()
    if usable:
        return Check("ffmpeg", True, "audio imports are on")
    return Check("ffmpeg", False, "ffmpeg is not installed.", f"apt-get {fix}", fatal=False)


def check_ytdlp() -> Check:
    """Whether a YouTube address can be fetched, which a box now needs as much as a
    laptop: `Library.prepare` opens the paste to a hosted fetch, so a box without yt-dlp
    is one where every YouTube import fails at the button. A warning like ffmpeg's, and
    never fatal — nothing else about the server depends on it."""
    from .video import ytdlp_available

    usable, fix = ytdlp_available()
    if usable:
        return Check("yt-dlp", True, "YouTube imports are on")
    # Not fatal on a box either: a reader pasting a YouTube address is told this box
    # cannot fetch one, and every other door — files, links, text, the library — is
    # untouched. A server without it is diminished, not broken.
    return Check("yt-dlp", False, "YouTube imports are off without yt-dlp.", fix, fatal=False)


def check_fetch_egress(connect: bool = True) -> Check:
    """Whether the exit a refused page is retried through is listening.

    Silent when nothing is set: a fetch that finds no proxy simply is not retried, and
    on a laptop that is the ordinary thing. Set and not listening is the loud case, the
    same shape `check_ytdlp_proxy` is loud about, and for the same reason. The address is
    never printed as given — a residential proxy is bought with a username and a password
    in the URL, and this line goes over SSH and into the journal.
    """
    from .ingest import url as url_module

    where = url_module.egress()
    if not where:
        return Check("Fetch egress", True, "refused pages are not retried", fatal=False)
    parsed = urlparse(where)
    if not parsed.hostname:
        return Check("Fetch egress", False, "the proxy names no host.", "Use scheme://host:port.")
    port = parsed.port or (1080 if "socks" in (parsed.scheme or "") else 8080)
    named = f"{parsed.hostname}:{port}"
    if not connect:
        return Check("Fetch egress", True, f"{named}, not knocked on", fatal=False)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=POT_TIMEOUT):
            pass
    except OSError as error:
        return Check(
            "Fetch egress",
            False,
            f"{named} did not answer — {error}",
            "Every refused page stays refused until it does.",
            fatal=False,
        )
    return Check("Fetch egress", True, f"{named} answers", fatal=False)


def check_ytdlp_proxy(connect: bool = True) -> Check:
    """Whether the egress YouTube is fetched through is listening.

    On a datacenter box this is the whole of whether YouTube works: the address itself
    is flagged, and nothing installed on the box answers that. So an unset proxy is
    worth saying on a hosted box — it means every YouTube paste will fail — while on a
    laptop it means the ordinary thing and is silent.

    Set and not listening is the one that must be loud, and it is the shape a tunnel
    fails in: the machine at the other end closed its lid, and the door that worked
    yesterday now refuses every reader.
    """
    from .video import youtube as youtube_module

    where = youtube_module.proxy()
    if not where:
        if not _hosted():
            return Check("YouTube egress", True, "fetched from here", fatal=False)
        return Check(
            "YouTube egress",
            False,
            "no proxy, and a datacenter address is flagged by YouTube.",
            f"Every YouTube paste fails at the button. Set {youtube_module.YTDLP_PROXY_ENV} "
            "to an egress YouTube trusts, or the /add page should stop offering the door.",
            fatal=False,
        )
    parsed = urlparse(where)
    if not parsed.hostname:
        return Check("YouTube egress", False, "the proxy names no host.", "Use scheme://host:port.")
    # Never the address as given. A residential proxy is bought with a username and a
    # password in the URL, and this line is printed by the deploy over SSH and again
    # into the journal — which is how a credential ends up somewhere nobody thinks to
    # look for one. The host and port are the whole of what a reader of this check needs.
    port = parsed.port or (1080 if "socks" in (parsed.scheme or "") else 8080)
    named = f"{parsed.hostname}:{port}"
    if not connect:
        return Check("YouTube egress", True, f"{named}, not knocked on", fatal=False)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=POT_TIMEOUT):
            pass
    except OSError as error:
        return Check(
            "YouTube egress",
            False,
            f"{named} did not answer — {error}",
            "Until it does, every YouTube import fails. A tunnel's far end is usually "
            "the machine that went to sleep.",
            fatal=False,
        )
    return Check("YouTube egress", True, f"{named} answers")


#: A public reel from Kan's news account, the one the Instagram door was measured on
#: (2026-09-18). If it is ever deleted this check reads as a refusal; swap in another.
INSTAGRAM_CONTROL = "https://www.instagram.com/reel/DSkLv4UE196/"


def check_instagram(connect: bool = True) -> Check:
    """Whether Instagram still shows this box a public reel.

    Nothing about the box changes when this fails — Instagram does, or the extractor
    falls behind it, and both happen without notice. So it asks the real question, one
    `yt-dlp -J` on a known reel through the service's own egress, where the socket knock
    `check_ytdlp_proxy` does would say "fine" to a door that refuses every reader.

    On a hosted box only: a laptop's own address is not the one readers are fetched
    from, and a serve that started by asking Instagram something would start slowly.
    """
    from .errors import TargumError
    from .video import instagram as instagram_module
    from .video import ytdlp_available

    if not _hosted() or not ytdlp_available()[0]:
        # No yt-dlp is `check_ytdlp`'s to say, once.
        return Check("Instagram", True, "not asked from here", fatal=False)
    if not connect:
        return Check("Instagram", True, "not asked", fatal=False)
    try:
        info = instagram_module.describe(INSTAGRAM_CONTROL)
    except TargumError as error:
        return Check(
            "Instagram",
            False,
            f"the control reel was refused — {error.message}",
            "Pasted reels fail at the button until it answers. A newer yt-dlp is the "
            "usual fix; a deleted control reel reads the same way.",
            fatal=False,
        )
    return Check("Instagram", True, f"the control reel answers ({round(info['duration'])} s)")


#: A public TikTok from a Hebrew-teaching account, measured from the box on 2026-09-18.
#: If it is ever deleted this check reads as a refusal; swap in another.
TIKTOK_CONTROL = "https://www.tiktok.com/@yiramne/video/7485073076758007056"


def check_tiktok(connect: bool = True) -> Check:
    """Whether TikTok still shows this box a public video, directly.

    `check_instagram`'s reasons, and one more: this door does not go through the proxy,
    so the proxy's own check says nothing about it. TikTok serves the box's address and
    refuses the residential pool; the day that turns round, this is where it shows.
    """
    from .errors import TargumError
    from .video import tiktok as tiktok_module
    from .video import ytdlp_available

    if not _hosted() or not ytdlp_available()[0]:
        return Check("TikTok", True, "not asked from here", fatal=False)
    if not connect:
        return Check("TikTok", True, "not asked", fatal=False)
    try:
        info = tiktok_module.describe(TIKTOK_CONTROL)
    except TargumError as error:
        return Check(
            "TikTok",
            False,
            f"the control video was refused — {error.message}",
            "Pasted TikToks fail at the button until it answers. A newer yt-dlp is the "
            "usual fix; a deleted control video reads the same way.",
            fatal=False,
        )
    return Check(
        "TikTok", True, f"the control video answers ({round(info.get('duration') or 0)} s)"
    )


def check_pot(connect: bool = True) -> Check:
    """Whether the token minter is answering, which on a box is what makes yt-dlp work.

    YouTube asks an unfamiliar address to prove it is a browser, and a datacenter IP is
    the definition of unfamiliar. Without a minter every YouTube paste on the box fails
    at the button — and it fails late, after the spinner, which is the shape of failure
    this check exists to move to deploy time.

    Unset is a laptop, where the home IP is proof enough and nothing needs minting. Set
    and silent is the one that has to be said out loud: somebody meant to run the
    provider and it is not there.
    """
    from .video import youtube as youtube_module

    provider = youtube_module.pot_provider()
    if not provider:
        return Check("YouTube tokens", True, "no minter, so YouTube is asked directly", fatal=False)
    fix = (
        "start the provider — systemctl start bgutil-pot — or unset "
        f"{youtube_module.POT_PROVIDER_ENV}."
    )
    if not connect:
        return Check("YouTube tokens", True, f"{provider}, not knocked on", fatal=False)
    try:
        with urlopen(f"{provider.rstrip('/')}/ping", timeout=POT_TIMEOUT) as answer:
            version = json.loads(answer.read().decode("utf-8", "replace")).get("version", "")
    except (OSError, ValueError) as error:
        # Never fatal, for `check_ytdlp`'s reason: every other door is untouched, and a
        # box that cannot fetch YouTube is diminished rather than broken.
        return Check("YouTube tokens", False, f"{provider} did not answer — {error}", fix, False)
    named = f"{provider} ({version})" if version else provider
    return Check("YouTube tokens", True, f"{named} is minting")


def check_scripture() -> Check:
    """Whether the Hebrew Bible is read from the hand tagging or guessed at by a model.

    A warning rather than a failure: a box without the tagging still builds a Tanakh,
    but every verse of it is read by DICTA, which spells its lemmas its own way and, until
    the register line learnt to hold its tongue, called the first word of Nitzavim modern
    (targum-internal#156). `for_source()` wraps the model only when the data is on disk
    under the process's own model directory, and the service's directory is not the
    deployer's — so the question is asked here, in the service's environment, where the
    answer is the one that matters.
    """
    from .annotate import oshb

    where = oshb.root()
    if oshb.available():
        return Check("scripture", True, f"the Hebrew Bible tagging is at {where}", fatal=False)
    return Check(
        "scripture",
        False,
        f"no Hebrew Bible tagging at {where}; scripture will be read by a model.",
        "targum models fetch scripture, as the service user",
        fatal=False,
    )


def check_shelf(out: Path) -> Check:
    """How many built texts are behind the annotator this code would use.

    A warning, not a failure: a shelf a version behind serves perfectly good pages, and
    `deploy.sh` runs `rebuild --words` right after this, which is what closes the gap. The
    point is that the number is *said*. Three fixes were merged, closed and believed
    shipped on 2026-09-03 and reached no built page — the register fix that stopped the
    Tanakh calling `נִצָּבִים` modern, the binyan the hand tagging had written down all
    along, and the recounted Tanakh table the difficulty bands sort on. Nothing was done
    wrong; there was simply no line anywhere that printed "411 of 418 behind", so a stale
    shelf and a current one looked the same (targum-internal#207, #208).

    `scripts/shelf_versions.py` is the same survey with the detail — which component, by
    home, and the ingester's separate and sharper version of the question.

    The line says "with artifacts", because that is the population the survey walks: a
    text with an `annotation.json` beside it. The parasha corpus keeps none, so this
    line said "all 164 Hebrew texts on the current annotator" over a box whose fifty-four
    portions were the stalest thing on it (targum-internal#227). `check_parasha` counts
    those; this one now says out loud what it does not.
    """
    from .annotate.versions import survey

    if not out.is_dir():
        return Check("shelf", True, f"nothing built at {out} yet", fatal=False)
    shelf = survey(out)
    if not shelf.total:
        return Check("shelf", True, f"no Hebrew texts built at {out}", fatal=False)
    if not shelf.behind:
        return Check(
            "shelf",
            True,
            f"all {shelf.total} Hebrew texts with artifacts on the current annotator",
            fatal=False,
        )
    moved = ", ".join(list(shelf.moved())[:3])
    return Check(
        "shelf",
        False,
        f"{len(shelf.behind)} of {shelf.total} Hebrew texts with artifacts are behind the "
        "current annotator" + (f" ({moved})" if moved else ""),
        "targum rebuild --words — and note it re-annotates, which on a box without a GPU "
        "is about a text a minute. scripts/shelf_versions.py --list names them.",
        fatal=False,
    )


def reader_stylesheet() -> str:
    """The stylesheet a reader page inlines today, exactly as `render` bakes it in."""
    from .render.builder import _asset

    return str(_asset("reader.css"))


def shelf_of(reader: Path, out: Path) -> str:
    """Which shelf a reader page belongs to, as a deploy would name it: the path from the
    out directory down to the text's own folder. `parasha/read/lech-lecha/reader/index.html`
    is `parasha/read`, and `library/רות-he/reader/index.html` is `library`."""
    try:
        parts = reader.relative_to(out).parts
    except ValueError:
        return ""
    # …/<shelf…>/<text>/reader/<page>.html — drop the page, `reader`, and the text.
    return "/".join(parts[:-3])


def carries(page: Path, css: str) -> bool:
    """Whether this page has today's stylesheet in it.

    Read from the `<style>` the head opens rather than whole: a reader page is a hundred
    kilobytes and a box has thousands of them, and everything before that tag is a title
    and an icon. Asked of the bytes, not of a timestamp — a wheel may or may not stamp
    one, and a page that was copied or rsynced carries whatever mtime the copy gave it.
    """
    wanted = css.encode("utf-8")
    try:
        with page.open("rb") as handle:
            head = handle.read(16384)
            at = head.find(b"<style>")
            if at == -1:
                return False
            at += len(b"<style>")
            handle.seek(at)
            return handle.read(len(wanted)) == wanted
    except OSError:
        return False


def check_stale_readers(out: Path, current: str | None = None) -> Check:
    """How many reader pages on this box do not carry the stylesheet they would be
    rendered with today.

    `targum rebuild` rewrites what has artifacts beside it. The parasha corpus and the
    daily window keep none, and the four shared Russian texts are skipped by design
    (their lemmas are only in the laptop's cache, targum#282). So after any change to
    reader CSS or JS those stay exactly as they were cut, and `deploy.sh` said "done"
    over them three times: targum-internal#227, then `languages/3` on 2026-09-18, then
    929 of 2,208 reader files left on the old theme on 2026-09-20 (#344, #345).

    `check_shelf` and `check_parasha` ask whether a page is behind the *annotator*, which
    a re-annotation moves. This asks the question they both miss, because a theme change
    moves no annotation and is invisible to either: whether the page has today's look in
    it. A reader carries its stylesheet in its own bytes — nothing on the page fetches —
    so the page itself is the evidence, and no timestamp has to be trusted.

    A warning, not a failure: an older page is still a page, and what fixes it is a
    re-cut on a machine that has the books, which is not this one.
    """
    if not out.is_dir():
        return Check("stale readers", True, f"nothing built at {out} yet", fatal=False)
    css = reader_stylesheet() if current is None else current
    counts: dict[str, int] = {}
    total = 0
    for page in out.glob("**/reader/*.html"):
        total += 1
        if carries(page, css):
            continue
        shelf = shelf_of(page, out)
        counts[shelf] = counts.get(shelf, 0) + 1
    if not total:
        return Check("stale readers", True, f"no reader pages under {out}", fatal=False)
    if not counts:
        return Check(
            "stale readers",
            True,
            f"all {total} reader pages carry the stylesheet they would be built with today",
            fatal=False,
        )
    stale = sum(counts.values())
    named = " · ".join(f"{shelf or out.name} {n}" for shelf, n in sorted(counts.items()))
    return Check(
        "stale readers",
        False,
        f"{stale} of {total} reader pages are on an older theme: {named}",
        "A rebuild reaches only what keeps artifacts beside it. The parasha corpus and "
        "the daily window keep none: re-cut them (targum parasha build, from the main "
        "checkout) and ship. deploy/README.md says why the working directory matters.",
        fatal=False,
    )


def parasha_root(out: Path) -> Path:
    """Where the parasha corpus is, asked the way the server asks (`parasha.calendar.root`)
    and falling back beside the shelf rather than to the working directory, because a
    preflight is run from wherever the deploy happens to be standing."""
    named = os.environ.get("TARGUM_PARASHA_DIR", "").strip()
    return Path(named).expanduser() if named else out / "parasha"


def check_parasha(out: Path) -> Check:
    """How many readings of the parasha corpus are behind the books they were cut from.

    The portions are the free door, and they keep no artifact: `rebuild --words` cannot
    reach one, and the deploy that re-annotated every book on the shelf on 2026-09-08
    left Nitzavim serving verbs with no binyan and no grammar line, under a shelf line
    that read as an all-clear (targum-internal#227). What moves a portion is
    `targum parasha build` on a machine whose library is current, and
    `deploy/ship-parasha.sh` — so that is what the fix says, rather than the rebuild.

    A warning, not a failure, for the reason the shelf's is: an older page is still a
    page. A corpus cut before the index recorded its annotator cannot be read either
    way, and is said as such rather than counted as current.
    """
    from .annotate.versions import survey_corpus

    corpus = parasha_root(out)
    if not (corpus / "index.json").is_file():
        return Check("parasha", True, f"no parasha corpus at {corpus}", fatal=False)
    shelf = survey_corpus(corpus, out / "library")
    if not shelf.total:
        return Check("parasha", True, f"the corpus at {corpus} lists nothing built", fatal=False)
    recut = (
        "targum parasha build, on a machine whose library is on the current annotator, "
        "then deploy/ship-parasha.sh. The corpus keeps no artifacts, so rebuild --words "
        "cannot reach it."
    )
    if shelf.behind:
        moved = ", ".join(list(shelf.moved())[:3])
        return Check(
            "parasha",
            False,
            f"{len(shelf.behind)} of {shelf.total} readings were cut from an older annotation "
            "than the shelf carries now" + (f" ({moved})" if moved else ""),
            recut,
            fatal=False,
        )
    if shelf.unjudged:
        return Check(
            "parasha",
            True,
            f"{shelf.unjudged} of {shelf.total} readings name the annotator they were cut "
            "with, and the books they were cut from are not on this machine — so whether a "
            "re-cut would change them cannot be judged here",
            "The books live where the shelf is built, not where it is served. Run this "
            "on the machine that cuts the corpus to get an answer.",
            fatal=False,
        )
    if shelf.unknown:
        return Check(
            "parasha",
            False,
            f"{shelf.unknown} of {shelf.total} readings were cut before the corpus recorded "
            "its annotator; whether they are behind cannot be read off the disk",
            recut + " A re-cut also writes the name down.",
            fatal=False,
        )
    return Check(
        "parasha",
        True,
        f"all {shelf.total} readings cut from the annotation the shelf carries now",
        fatal=False,
    )


def check_daily(out: Path) -> Check:
    """How many days of the daily window are behind the books they were cut from.

    The parasha's question, asked of the other corpus that keeps no artifact: Mishna
    Yomi, Nach Yomi and Tanakh Yomi are cut nightly on a laptop from that laptop's shelf
    and shipped (`deploy/ship-daily.sh`), so a box whose shelf was just re-annotated
    still serves the days as they were cut. `check_parasha` says why the line exists;
    the remedy here is the nightly build run from a current shelf, not the rebuild.
    """
    from .annotate.versions import survey_daily

    corpus = parasha_root(out) / "daily"
    if not (corpus / "index.json").is_file():
        return Check("daily", True, f"no daily corpus at {corpus}", fatal=False)
    shelf = survey_daily(corpus, out / "library")
    if not shelf.total:
        return Check("daily", True, f"the window at {corpus} holds no days", fatal=False)
    recut = (
        "targum daily build, on a machine whose library is on the current annotator, "
        "then deploy/ship-daily.sh. The window keeps no artifacts, so rebuild --words "
        "cannot reach it."
    )
    if shelf.behind:
        moved = ", ".join(list(shelf.moved())[:3])
        return Check(
            "daily",
            False,
            f"{len(shelf.behind)} of {shelf.total} days were cut from an older annotation "
            "than the shelf carries now" + (f" ({moved})" if moved else ""),
            recut,
            fatal=False,
        )
    if shelf.unjudged:
        return Check(
            "daily",
            True,
            f"{shelf.unjudged} of {shelf.total} days name the annotator they were cut with, "
            "and the books they were cut from are not on this machine — so whether a re-cut "
            "would change them cannot be judged here",
            "The window is cut on a laptop from that laptop's shelf. Ask there.",
            fatal=False,
        )
    if shelf.unknown:
        return Check(
            "daily",
            False,
            f"{shelf.unknown} of {shelf.total} days were cut before the window recorded its "
            "annotator; whether they are behind cannot be read off the disk",
            recut + " The next nightly build writes the name down.",
            fatal=False,
        )
    return Check(
        "daily",
        True,
        f"all {shelf.total} days cut from the annotation the shelf carries now",
        fatal=False,
    )


def check_transcriber() -> Check:
    """Whether a recording without a transcript can be heard, and on whose key."""
    from .transcribe import build, default_name

    try:
        chosen = build(default_name())
    except Exception:  # noqa: BLE001 - a misnamed transcriber is the same warning
        chosen = None
    if chosen is not None:
        usable, detail = chosen.available()
        if usable:
            return Check("transcriber", True, chosen.name)
    return Check(
        "transcriber",
        False,
        "No transcriber key.",
        "Set ELEVENLABS_API_KEY or OPENAI_API_KEY. Audio without a transcript is off until one is.",
        fatal=False,
    )


def check_covers() -> Check:
    """Whether a cover can be drawn, which is a thing to know rather than a thing to fix.

    Two halves, and either one missing means the same thing to a reader: the shelf draws
    each text's own first letter. That is the designed resting state — the page never
    offers to draw what it cannot — so this never fails a deploy. It says which half is
    absent, because "covers are off" and "covers are off because nobody installed Pillow"
    are different afternoons.
    """
    from .covers import can_shrink

    key = bool(_env("OPENAI_API_KEY"))
    pillow = can_shrink()
    if key and pillow:
        return Check("covers", True, "a key and something to shrink with")
    missing = []
    if not key:
        missing.append("OPENAI_API_KEY is not set")
    if not pillow:
        missing.append("Pillow is not installed")
    return Check(
        "covers",
        False,
        f"{' and '.join(missing)}.",
        "The shelf draws each text's first letter, which is the ordinary state.",
        fatal=False,
    )


def check_backups_leave() -> Check:
    """Whether the nightly copy goes anywhere but the disk it is a copy of.

    A warning rather than a failure: refusing to start over this would take a working
    library offline to protect against a disk that has not died yet. But it is the one
    thing on this list that is invisible until it matters, and the day it matters there
    is nothing to be done about it.
    """
    from .backup import destination

    where = destination()
    if not where:
        return Check(
            "backups leave the box",
            False,
            "TARGUM_BACKUP_TO is not set, so copies sit beside the database.",
            "Set it in /etc/cron.d/targum-backup to an rclone remote.",
            fatal=False,
        )
    if shutil.which("rclone") is None:
        return Check(
            "backups leave the box",
            False,
            f"{where} is set but rclone is not installed, so nothing has left.",
            "apt-get install rclone",
            fatal=False,
        )
    return Check("backups leave the box", True, where)


def check_invitations(store: Path) -> Check:
    """Whether anybody may open an account here.

    Hosted, an empty list means nobody can — which is the right default but the wrong
    thing to discover from a reader saying the link never came. A warning rather than a
    failure: a box with nobody invited yet is a normal state on the way to inviting
    somebody, and refusing to start would leave no way to run the command that fixes it.
    """
    if not _hosted():
        return Check("invitations", True, "not hosted, so no guest list", fatal=False)
    try:
        from .accounts import Store

        people = Store(store).invitations()
    except Exception as error:  # noqa: BLE001 - a missing or unreadable store
        return Check("invitations", False, f"cannot read the list — {error}", fatal=False)
    if not people:
        return Check(
            "invitations",
            False,
            "nobody is invited, so nobody can sign up.",
            "targum invite someone@example.com",
            fatal=False,
        )
    return Check("invitations", True, f"{len(people)} invited")


def check_paths(store: Path, out: Path) -> list[Check]:
    checks = []
    for label, path in (
        ("word store", store.parent),
        ("targums", out),
        ("backups", store.parent / "backups"),
    ):
        ok = _writable(path)
        checks.append(
            Check(
                f"writable · {label}",
                ok,
                str(path) if ok else f"cannot write to {path}",
                "" if ok else "Check the unit's User= and ReadWritePaths=.",
            )
        )
    return checks


def check_disk(path: Path) -> Check:
    try:
        free_gb = shutil.disk_usage(path).free / 1024**3
    except OSError as error:
        return Check("disk", False, f"cannot measure {path} — {error}")
    ok = free_gb >= LEAST_DISK_GB
    return Check(
        "disk",
        ok,
        f"{free_gb:.1f} GB free",
        "" if ok else f"Under {LEAST_DISK_GB:.0f} GB. Stanza's models alone are most of that.",
    )


def check_port(port: int) -> Check:
    """Whether the port is free — which, on a running box, means it is *not*.

    So this is a warning rather than a failure: during a redeploy the old process still
    holds it, and that is the normal case rather than the broken one.
    """
    with socket.socket() as probe:
        probe.settimeout(1.0)
        taken = probe.connect_ex(("127.0.0.1", port)) == 0
    if taken:
        return Check(
            "port",
            False,
            f"{port} is already answering",
            "Expected during a redeploy; a second copy otherwise.",
            fatal=False,
        )
    return Check("port", True, f"{port} is free", fatal=False)


def preflight(store: Path, out: Path, port: int = 8420, connect: bool = True) -> list[Check]:
    """Every check, in the order somebody would want to read them."""
    checks = [check_address(), check_account_required()]
    checks += check_mail(connect=connect)
    checks.append(check_api_key())
    checks.append(check_covers())
    checks.append(check_ffmpeg())
    checks.append(check_ytdlp())
    checks.append(check_ytdlp_proxy(connect=connect))
    checks.append(check_fetch_egress(connect=connect))
    checks.append(check_pot(connect=connect))
    checks.append(check_instagram(connect=connect))
    checks.append(check_tiktok(connect=connect))
    checks.append(check_transcriber())
    checks.append(check_scripture())
    checks.append(check_shelf(out))
    checks.append(check_stale_readers(out))
    checks.append(check_parasha(out))
    checks.append(check_daily(out))
    checks.append(check_backups_leave())
    checks.append(check_invitations(store))
    checks += check_paths(store, out)
    checks += [check_disk(store.parent), check_port(port)]
    return checks


def fatal(checks: list[Check]) -> list[Check]:
    return [c for c in checks if not c.ok and c.fatal]
