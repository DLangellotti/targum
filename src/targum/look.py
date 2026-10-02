"""What the front door's box says about a pasted link (targum-internal#399).

A stranger pastes a link under the headline and is told what is at the end of it, in
one sentence, before they join. This is `describe_source`'s describing half and nothing
more: no `claim`, no job, no model. The reading is metadata — what yt-dlp knows without
fetching, an article read once through the fetch door with its cap and its SSRF guard —
and it is the same reading Add makes a moment before it prices anything, so a link the
box can describe is a link Add can build.

What is said differs from what the model is told. `_describe`'s advice lines are written
for the model, in English, and count credits; a stranger has no credits and may not read
English, and the page never shows them a price. So the facts are taken from the reading
and said again here through the catalogue, in the page's language.

There is no percentage. "You know 80% of this" needs a record of the words somebody
knows, and a stranger has none: that number is what joining gets them (decided
2026-09-30), and the page says so beside the answer instead.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .strings import counted, text

#: The longest link kept. A real share link is well under this; anything longer is
#: refused rather than truncated into a different address.
LONGEST_LINK = 2048


def kept_link(said: str) -> str:
    """A link worth keeping on a waiting row, or empty.

    http or https, with a host, no user or password in it, and not absurdly long. It is
    only ever handed back to the address that pasted it, inside Add's own box, which
    refuses anything else again at its end; this keeps the column from becoming a place
    to store whatever a form says.
    """
    link = said.strip()
    if not link or len(link) > LONGEST_LINK:
        return ""
    parsed = urlparse(link)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    return link


def _medium(url: str) -> str:
    """Which kind of place the link is from, by its address. Names the sentence only;
    `_describe` decides whether it can be read."""
    from .ingest import x as x_module
    from .video import facebook as facebook_module
    from .video import instagram as instagram_module
    from .video import tiktok as tiktok_module
    from .video import youtube as youtube_module

    checks: tuple[tuple[str, Any], ...] = (
        ("youtube", youtube_module.is_youtube),
        ("reel", instagram_module.is_reel),
        ("instagram", instagram_module.is_post),
        ("tiktok", tiktok_module.is_tiktok),
        ("facebook", facebook_module.is_facebook),
        ("x", x_module.is_x),
    )
    for name, check in checks:
        try:
            if check(url):
                return name
        except Exception:  # noqa: BLE001 — a check that cannot decide is not this one
            continue
    return ""


def _minutes(seconds: float, language: str) -> str:
    whole = max(1, round(seconds / 60))
    return counted(
        "landing.look.minutes", whole, language, {"one": "{n} minute", "other": "{n} minutes"}
    ).format(n=whole)


def _about(words: int) -> int:
    """A word count as a person would say it: exact when small, then to the nearest
    hundred. "About 1462 words" is a number pretending to a precision it has not got."""
    return words if words < 200 else round(words, -2)


def _number(n: int, language: str) -> str:
    """Thousands set apart as the language does: 1,500 in English, 1 500 in Russian."""
    said = f"{n:,}"
    return said.replace(",", "\u00a0") if language.split("-")[0] == "ru" else said


def _wait(minutes: int, language: str) -> str:
    """How long it would take to get ready, said the way Add says it."""
    if minutes <= 1:
        return text("landing.look.wait.minute", language)
    if minutes <= 4:
        return text("landing.look.wait.few", language)
    return text("landing.look.wait.minutes", language, n=str(minutes))


def look(url: str, language: str = "en") -> dict[str, Any]:
    """`{"ok": True, "title", "said", "wait", "link"}`, or `{"ok": False, "said"}`."""
    from .chat import tools as tools_module

    link = kept_link(url)
    if not link:
        return {"ok": False, "said": text("landing.look.not-a-link", language)}
    try:
        found = tools_module._describe(None, {"url": link})
    except Exception:  # noqa: BLE001 — a stranger is told plainly, never shown a trace
        found = {"error": "unreadable"}
    if found.get("error") or found.get("kind") in (None, "fetcher"):
        return {"ok": False, "said": text("landing.look.unreadable", language)}

    medium = _medium(link)
    kind = str(found.get("kind") or "")
    seconds = float(found.get("seconds") or 0)
    said: list[str] = []
    if kind in ("video", "recording") and seconds:
        length = _minutes(seconds, language)
        key = {
            "youtube": "landing.look.youtube",
            "reel": "landing.look.reel",
            "tiktok": "landing.look.tiktok",
            "facebook": "landing.look.facebook",
        }.get(medium, "landing.look.video" if kind == "video" else "landing.look.recording")
        said.append(text(key, language, length=length))
        said.append(
            text("landing.look.subtitled", language)
            if found.get("hebrew_subtitles")
            else text("landing.look.spoken", language)
        )
        # The wait Add would quote: hearing it, then translating it (`bring.js`'s `wait`).
        listening = 0 if found.get("hebrew_subtitles") else max(1, round(seconds / 360))
        minutes = listening + 1
    elif kind == "post":
        words = int(found.get("caption_words") or 0)
        said.append(
            counted(
                "landing.look.post",
                words,
                language,
                {
                    "one": "That’s an Instagram post, with {n} word in its caption.",
                    "other": "That’s an Instagram post, with {n} words in its caption.",
                },
            ).format(n=_number(words, language))
        )
        minutes = 1
    elif kind == "article":
        words = _about(int(found.get("words") or 0))
        if float(found.get("hebrew_share") or 0) < 0.5:
            return {"ok": False, "said": text("landing.look.not-hebrew", language)}
        key = "landing.look.x" if medium == "x" else "landing.look.article"
        said.append(
            counted(
                key,
                words,
                language,
                {
                    "one": "That’s a page with {n} word of Hebrew.",
                    "other": "That’s a page with about {n} words of Hebrew.",
                },
            ).format(n=_number(words, language))
        )
        minutes = max(1, round(words / 300))
    else:
        said.append(text("landing.look.readable", language))
        minutes = 2
    return {
        "ok": True,
        "title": str(found.get("title") or "").strip()[:200],
        "said": " ".join(said),
        "wait": _wait(minutes, language),
        "link": str(found.get("quote_with") or link),
    }
