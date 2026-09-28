"""A Telegram bot as a door onto /add (targum-internal#328, slices 1 and 2).

Somebody links a chat from /account, and from then on what they send the bot — a voice
note, a recording, a video, a picture, a PDF, or some text — becomes an ordinary private
import on their shelf, through the same job path the Add page takes: `Library.prepare`
prices it, `Library.claim` spends, and every build is a `job` row the rails see.

**Dark until configured.** With no bot token, webhook secret and bot name in the
environment, `from_environment` answers None, the webhook route answers 404, /account
draws no row, and nothing else changes.

What holds, and why:

- **The webhook is Telegram's alone.** Every update carries the secret given to
  `setWebhook` in `X-Telegram-Bot-Api-Secret-Token`; anything without it is a 404,
  compared in constant time.
- **A stranger's chat is a stranger.** One reply with the /account address, and nothing
  kept, built or spent. It never builds anonymously.
- **The send is the press**, as Send with a file is on the page (2026-09-07), for text,
  pictures, PDFs and any recording up to ten minutes. A longer one is quoted and asks
  first (David, 2026-09-27).
- **A link is quoted, and the reader's press on the Build button is the consent**
  (slice 2). It is priced by the same `Library.prepare` the Add page's `/prepare` calls,
  so every refusal the Add page gives a link — YouTube, Instagram, TikTok, X and the
  rest — comes back here in the same words. The button carries an opaque token bound to
  the chat and the person it was offered to, and the press goes through
  `Library.press`, the one road from a quote to `Library.claim` that `/build` takes
  too. A long recording's quote carries the same button.
- **Nothing about the message is kept but its content.** A forward carries its original
  sender's name; it is never read, so it can never land in somebody else's library. No
  message log: the update is answered and dropped.
- **The bot only answers.** One reply per message it was sent or button pressed, never
  a message first.
- **The hosted Bot API downloads up to 20 MB.** Bigger files are refused by name, with
  the address of the Add page, which takes them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from . import serve as serve_module
    from .accounts import Person, Store
    from .serve import Library

log = logging.getLogger(__name__)

#: Where Telegram posts updates. Given to `setWebhook` once, by hand.
HOOK = "/telegram/hook"

#: The header Telegram sends the webhook secret in.
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

#: What the hosted Bot API will hand over. A local Bot API server lifts it; that is a
#: later slice, if the refusals show up in the counts.
MOST_BYTES = 20 * 1024 * 1024

#: A recording longer than this is quoted and asks before it builds (David, 2026-09-27).
ASK_OVER_SECONDS = 10 * 60

#: The most an update body may be. An update is a few kilobytes; a file is never in it.
MOST_UPDATE_BYTES = 1024 * 1024

#: How many update ids to remember, so an update Telegram sends twice builds once.
REMEMBERED_UPDATES = 1000

#: Where the Bot API lives. Never written into a log: every address on it carries the
#: token.
API = "https://api.telegram.org"

#: The longest a text's title may be, as the Add page titles a paste.
PASTE_TITLE = 60

#: The longest title a quote says before it trails off. A page's title can be a
#: paragraph, and a quote is one line.
QUOTE_TITLE = 120

#: What a Build button's `callback_data` starts with. Telegram allows 64 bytes in all.
PRESS = "b:"


def configured() -> tuple[str, str, str] | None:
    """The bot token, the webhook secret and the bot's name, or None where any is unset.

    All three or nothing: a token without a secret would be a webhook anybody could post
    to, and one without the name has no link to put on /account.
    """
    token = os.environ.get("TARGUM_TELEGRAM_TOKEN", "").strip()
    secret = os.environ.get("TARGUM_TELEGRAM_SECRET", "").strip()
    bot = os.environ.get("TARGUM_TELEGRAM_BOT", "").strip().lstrip("@")
    if not (token and secret and bot):
        return None
    return token, secret, bot


def authentic(given: str | None, secret: str) -> bool:
    """Whether an update came with the webhook's secret. Constant time, and never true
    for an empty secret, which would otherwise match an empty header."""
    if not secret or not given:
        return False
    return secrets.compare_digest(given.encode("utf-8"), secret.encode("utf-8"))


class TooBig(Exception):
    """A file over what the hosted Bot API will hand over."""


class Client(Protocol):
    """The calls the door makes to Telegram. A protocol, so a test can stand in."""

    def send(self, chat_id: int, text: str) -> None: ...

    def offer(self, chat_id: int, text: str, button: str, data: str) -> None:
        """A message with one button under it, whose press comes back as `data`."""

    def answer(self, query_id: str, text: str = "") -> None:
        """Tell Telegram a button's press was heard, so the button stops spinning."""

    def edit(self, chat_id: int, message_id: int, text: str) -> None:
        """Say something else in a message already sent, and take its button away."""

    def typing(self, chat_id: int) -> None: ...

    def download(self, file_id: str, most: int) -> bytes: ...


class BotApi:
    """The hosted Bot API, over httpx. Errors are said without the address they came
    from, because every address here carries the bot's token."""

    def __init__(self, token: str, timeout: float = 60.0) -> None:
        self._token = token
        self._timeout = timeout

    def _call(self, method: str, payload: dict[str, Any]) -> Any:
        import httpx

        try:
            response = httpx.post(
                f"{API}/bot{self._token}/{method}", json=payload, timeout=self._timeout
            )
            answer = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError(f"telegram {method}: {type(error).__name__}") from None
        if not answer.get("ok"):
            raise RuntimeError(f"telegram {method}: {answer.get('description', 'refused')}")
        return answer.get("result")

    def send(self, chat_id: int, text: str) -> None:
        self._call(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "link_preview_options": {"is_disabled": True}},
        )

    def offer(self, chat_id: int, text: str, button: str, data: str) -> None:
        self._call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "link_preview_options": {"is_disabled": True},
                "reply_markup": {"inline_keyboard": [[{"text": button, "callback_data": data}]]},
            },
        )

    def answer(self, query_id: str, text: str = "") -> None:
        payload: dict[str, Any] = {"callback_query_id": query_id}
        if text:
            payload["text"] = text
        self._call("answerCallbackQuery", payload)

    def edit(self, chat_id: int, message_id: int, text: str) -> None:
        # No `reply_markup`, which is what takes the button away.
        self._call(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "link_preview_options": {"is_disabled": True},
            },
        )

    def typing(self, chat_id: int) -> None:
        self._call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    def download(self, file_id: str, most: int) -> bytes:
        import httpx

        found = self._call("getFile", {"file_id": file_id}) or {}
        if int(found.get("file_size") or 0) > most:
            raise TooBig
        path = str(found.get("file_path") or "")
        if not path:
            raise TooBig
        body = bytearray()
        try:
            with httpx.stream(
                "GET", f"{API}/file/bot{self._token}/{path}", timeout=self._timeout
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"telegram file: {response.status_code}")
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > most:
                        raise TooBig
        except httpx.HTTPError as error:
            raise RuntimeError(f"telegram file: {type(error).__name__}") from None
        return bytes(body)


@dataclass(frozen=True)
class Brought:
    """One file a message carries: which, what to call it, how big Telegram says it is,
    and what kind of thing it is (`audio`, `video`, `picture`, `pdf` or `text`)."""

    file_id: str
    name: str
    size: int
    kind: str


def _paste_title(text: str) -> str:
    """A text's title, as the Add page titles a paste (`add.js`, `pasteTitle`): its first
    sentence where that is short enough, and otherwise the words that fit."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    sentence = re.split(r"[.!?׃]\s", first)[0].rstrip(".!?׃")
    if len(sentence) <= PASTE_TITLE:
        title = sentence
    else:
        head = first[: PASTE_TITLE + 1]
        title = re.sub(r"\s+\S*$", "", head) if re.search(r"\s", head) else head[:PASTE_TITLE]
    return re.sub(r'[\\/:*?"<>|]+', " ", title).strip() or "Text"


def _safe_name(name: str, fallback: str) -> str:
    """A file's own name and nothing else: no path, nothing a filesystem minds."""
    base = Path(name.replace("\\", "/")).name.strip()
    base = re.sub(r'[\x00-\x1f:*?"<>|]+', " ", base).strip().lstrip(".")
    return base[:120] or fallback


def _is_only_a_link(message: dict[str, Any]) -> bool:
    """Whether a text message is a link and nothing else. A forwarded post with a link
    at its foot is a text; a message that is one address is a link, and is quoted."""
    text = str(message.get("text") or "").strip()
    if not text or any(char.isspace() for char in text):
        return False
    if re.match(r"(?i)^(https?://|www\.|t\.me/)", text):
        return True
    for entity in message.get("entities") or []:
        if entity.get("type") in {"url", "text_link"} and int(entity.get("length") or 0) >= len(
            text
        ):
            return True
    return False


class Door:
    """The bot's whole behaviour: an update in, at most one reply out."""

    def __init__(
        self,
        library: Library,
        store: Store,
        client: Client,
        address: str,
        bot: str,
        secret: str,
        run: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self.library = library
        self.store = store
        self.client = client
        self.address = address.rstrip("/")
        self.bot = bot
        self.secret = secret
        # How an update is handled once the webhook has answered: on a thread of its own,
        # because reading a picture or pricing a recording can take longer than Telegram
        # waits. A test hands over one that runs it there and then.
        self._run = run or self._on_a_thread
        self._seen: deque[int] = deque(maxlen=REMEMBERED_UPDATES)
        self._seen_lock = threading.Lock()

    # -- the webhook's side -------------------------------------------------------

    def link_for(self, person_id: int) -> str:
        """The one-time deep link /account hands over."""
        return f"https://t.me/{self.bot}?start={self.store.start_telegram_link(person_id)}"

    def accept(self, update: dict[str, Any]) -> None:
        """Take one update from the webhook, once. Telegram sends an update again when it
        did not hear an answer, and a recording sent twice must not build twice."""
        number = update.get("update_id")
        if isinstance(number, int):
            with self._seen_lock:
                if number in self._seen:
                    return
                self._seen.append(number)
        self._run(lambda: self.handle(update))

    def _on_a_thread(self, work: Callable[[], None]) -> None:
        def run() -> None:
            try:
                work()
            finally:
                # The store opens a connection per thread, and a thread-local is not
                # closed when its thread ends (see `Handler.finish`).
                self.store.close()

        threading.Thread(target=run, name="telegram", daemon=True).start()

    # -- one update ---------------------------------------------------------------

    def handle(self, update: dict[str, Any]) -> None:
        """Answer one update, or say nothing where there is nothing to answer."""
        from . import incidents as incidents_module

        query = update.get("callback_query")
        if isinstance(query, dict):
            return self._pressed(query)
        message = update.get("message")
        if not isinstance(message, dict):
            # An edit, a channel post: nothing the bot answers.
            return
        chat = message.get("chat") or {}
        if chat.get("type") != "private" or not isinstance(chat.get("id"), int):
            # In a group the bot would be answering people who never linked anything.
            return
        chat_id = int(chat["id"])
        ui = self._stranger_language(message)
        try:
            self._answer(chat_id, message, ui)
        except Exception as error:  # noqa: BLE001 - one bad update never takes the door down
            incidents_module.record(self.library.incidents, "telegram", error)
            self._reply(
                chat_id,
                said_in(
                    ui,
                    "telegram.failed",
                    "We couldn't take that. Try again, or send it on {link}.",
                    link=f"{self.address}/add",
                ),
            )

    def _answer(self, chat_id: int, message: dict[str, Any], ui: str) -> None:
        text = str(message.get("text") or "")
        command, argument = "", ""
        if text.startswith("/"):
            head, _, rest = text.strip().partition(" ")
            command, argument = head.split("@")[0].lower(), rest.strip()
        if command == "/start" and argument:
            return self._link(chat_id, argument, ui)
        if command == "/stop":
            return self._stop(chat_id, ui)
        person = self.store.telegram_person(chat_id)
        if person is None:
            return self._reply(chat_id, self._link_first(ui))
        ui = self._language(person)
        if command:
            return self._reply(chat_id, self._what_to_send(ui))
        self._bring(chat_id, person, ui, message)

    def _link(self, chat_id: int, token: str, ui: str) -> None:
        person = self.store.finish_telegram_link(token, chat_id)
        if person is None:
            return self._reply(
                chat_id,
                said_in(
                    ui,
                    "telegram.link-expired",
                    "That link has expired. Get a new one from {link}.",
                    link=f"{self.address}/you",
                ),
            )
        ui = self._language(person)
        self._reply(
            chat_id,
            said_in(ui, "telegram.linked", "This chat is now linked to your targum account.")
            + " "
            + self._what_to_send(ui),
        )

    def _stop(self, chat_id: int, ui: str) -> None:
        was = self.store.stop_telegram(chat_id)
        if was is None:
            return self._reply(
                chat_id, said_in(ui, "telegram.not-linked", "This chat isn't linked to targum.")
            )
        self._reply(
            chat_id,
            said_in(
                self._language(was),
                "telegram.stopped",
                "Unlinked. Nothing you send here reaches targum now.",
            ),
        )

    # -- what a linked chat sends -------------------------------------------------

    def _bring(self, chat_id: int, person: Person, ui: str, message: dict[str, Any]) -> None:
        text = str(message.get("text") or "")
        if text.strip():
            if _is_only_a_link(message):
                return self._quote_link(chat_id, person, ui, text.strip())
            return self._text(chat_id, person, ui, text)
        brought = self._file_of(message, ui)
        if brought is None:
            return self._reply(
                chat_id,
                said_in(ui, "telegram.cannot-read", "We can't read that kind of message.")
                + " "
                + self._what_to_send(ui),
            )
        if brought.size > MOST_BYTES:
            return self._reply(chat_id, self._too_big(ui, brought.name))
        self._quietly(lambda: self.client.typing(chat_id))
        try:
            data = self.client.download(brought.file_id, MOST_BYTES)
        except TooBig:
            return self._reply(chat_id, self._too_big(ui, brought.name))
        self._file(chat_id, person, ui, brought, data)

    def _file_of(self, message: dict[str, Any], ui: str) -> Brought | None:
        """The one file a message carries, if it is one targum reads.

        Only the file and its own name. The message's other fields — who forwarded it,
        who wrote it first, the caption — are never read."""
        from .audio import AUDIO_SUFFIXES, DRM_SUFFIXES
        from .video import VIDEO_SUFFIXES
        from .vision import PICTURE_SUFFIXES

        def size(held: dict[str, Any]) -> int:
            return int(held.get("file_size") or 0)

        voice = message.get("voice")
        if isinstance(voice, dict):
            name = said_in(ui, "telegram.name.voice", "Voice note") + ".ogg"
            return Brought(str(voice.get("file_id")), name, size(voice), "audio")
        note = message.get("video_note")
        if isinstance(note, dict):
            name = said_in(ui, "telegram.name.video-note", "Video note") + ".mp4"
            return Brought(str(note.get("file_id")), name, size(note), "video")
        photos = message.get("photo")
        if isinstance(photos, list) and photos:
            # Telegram sends every size it made; the last is the largest.
            biggest = photos[-1]
            name = said_in(ui, "telegram.name.picture", "Picture") + ".jpg"
            return Brought(str(biggest.get("file_id")), name, size(biggest), "picture")
        for field, fallback, kind in (
            ("audio", ".mp3", "audio"),
            ("video", ".mp4", "video"),
            ("document", "", ""),
        ):
            held = message.get(field)
            if not isinstance(held, dict):
                continue
            default = said_in(ui, "telegram.name.file", "File") + fallback
            name = _safe_name(str(held.get("file_name") or ""), default)
            suffix = Path(name).suffix.lower()
            if not suffix and fallback:
                name, suffix = name + fallback, fallback
            if suffix in DRM_SUFFIXES:
                return Brought(str(held.get("file_id")), name, size(held), "protected")
            if suffix in AUDIO_SUFFIXES:
                kind = "audio"
            elif suffix in VIDEO_SUFFIXES:
                kind = "video"
            elif suffix in PICTURE_SUFFIXES:
                kind = "picture"
            elif suffix == ".pdf":
                kind = "pdf"
            elif suffix in {".txt", ".md"}:
                kind = "text"
            else:
                return None
            return Brought(str(held.get("file_id")), name, size(held), kind)
        return None

    def _text(self, chat_id: int, person: Person, ui: str, text: str) -> None:
        """Some text, written down as a paste is, and built."""
        home = self.library.home(person)
        folder = home / "uploads" / secrets.token_hex(8)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{_paste_title(text)}.txt"
        target.write_text(text, encoding="utf-8")
        self._build(chat_id, person, ui, target)

    def _file(self, chat_id: int, person: Person, ui: str, brought: Brought, data: bytes) -> None:
        """A downloaded file, kept where the Add page keeps one, and built."""
        from .errors import TargumError
        from .serve import MEDIA_QUOTA_BYTES
        from .vision import MAX_PAGES

        if brought.kind == "protected":
            return self._reply(
                chat_id,
                said_in(
                    ui,
                    "serve.this-file-is-protected-so-we",
                    "This file is protected, so we can't read it.",
                ),
            )
        home = self.library.home(person)
        media = brought.kind in {"audio", "video"}
        if media:
            self.library.sweep_uploads(home)
            if self.library.used(home) + len(data) > MEDIA_QUOTA_BYTES:
                return self._reply(
                    chat_id,
                    said_in(
                        ui,
                        "serve.over-quota",
                        "That would take your recordings over {size} GB. Delete one and try again.",
                        size=MEDIA_QUOTA_BYTES // (1024 * 1024 * 1024),
                    ),
                )
        folder = home / "uploads" / secrets.token_hex(8)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / brought.name
        target.write_bytes(data)
        self.library._used.pop(home, None)
        source = target
        if media:
            # Marked the way the chunked door marks a finished upload, so the sweep and the
            # twin check treat it as one.
            sha256 = hashlib.sha256(data).hexdigest()
            (folder / ".meta.json").write_text(
                json.dumps({"name": brought.name, "size": len(data), "made": _now()}),
                encoding="utf-8",
            )
            (folder / ".sha256").write_text(sha256, encoding="utf-8")
            twin = self.library.holding(home, sha256, except_for=folder)
            if twin is not None and twin.get("reader"):
                shutil.rmtree(folder, ignore_errors=True)
                reader = str(twin["reader"])
                return self._reply(
                    chat_id,
                    said_in(
                        ui,
                        "telegram.already",
                        "You've sent us this one before. It's here: {link}",
                        link=f"{self.address}/reader/{reader}",
                    ),
                )
        elif brought.kind in {"picture", "pdf"}:
            try:
                if brought.kind == "picture":
                    from . import vision

                    vision.probe(target)
                else:
                    from .ingest import pdf as pdf_module

                    pages = pdf_module.page_count(target)
                    if pages > MAX_PAGES:
                        raise TargumError(
                            f"That PDF has {pages} pages. We can read up to {MAX_PAGES} at a time."
                        )
            except TargumError as error:
                shutil.rmtree(folder, ignore_errors=True)
                from .serve import refused_in

                return self._reply(chat_id, refused_in(ui, error))
            # Numbered as `Handler._gathered` numbers a set of pages, and the folder is the
            # source for a picture as it is there.
            numbered = folder / f"01-{target.name}"
            target.rename(numbered)
            source = folder if brought.kind == "picture" else numbered
        self._build(chat_id, person, ui, source)

    def _quote_link(self, chat_id: int, person: Person, ui: str, text: str) -> None:
        """A link, priced as the Add page prices a pasted one, and offered with a button.

        The same checks `Handler._prepare` makes before it prices anything: a link must
        name something to fetch (`ingest.fetchable`, the rule the Add page's door and the
        chat's quote keep), and a text the library already holds with a translation a
        person published is pointed at rather than bought again. Everything after that is
        `Library.prepare`'s, whose refusals are the Add page's own.
        """
        from . import catalogue as catalogue_module
        from . import ingest as ingest_module

        source = text if re.match(r"(?i)^https?://", text) else f"https://{text}"
        if not ingest_module.fetchable(source) and catalogue_module.matching(source) is None:
            return self._reply(
                chat_id,
                said_in(
                    ui,
                    "telegram.no-address",
                    "We can't fetch that link. Check it, or paste it on {link}.",
                    link=f"{self.address}/add",
                ),
            )
        already = catalogue_module.matching(source)
        if already is not None and already.translations:
            return self._reply(
                chat_id,
                said_in(
                    ui,
                    "telegram.in-library",
                    "{title} is already in the library, with a translation a person "
                    "published. It'll read better than ours: {link}",
                    title=already.title,
                    link=f"{self.address}/library/{already.id}",
                ),
            )
        job = self._prepared(person, ui, source, {"source": source})
        if self._refused(chat_id, ui, job):
            return
        self._offer(chat_id, person, ui, job)

    def _build(self, chat_id: int, person: Person, ui: str, source: Path) -> None:
        """Price it and, unless it is a long recording, start it: `Library.prepare`, then
        `Library.press` — the steps `/prepare` and `/build` take, in their order, and no
        second way to the rails. A long recording is offered with the Build button a link
        gets, and waits for the reader's press."""
        job = self._prepared(person, ui, str(source), {})
        if self._refused(chat_id, ui, job):
            return
        if job.audio and job.seconds > ASK_OVER_SECONDS:
            return self._offer(chat_id, person, ui, job)
        blocked = self.library.press(job)
        if blocked:
            self.library.remember(job)
            return self._reply(chat_id, f"{blocked} {self.address}/you")
        self._reply(chat_id, self._started(ui, job))

    def _prepared(
        self, person: Person, ui: str, source: str, extra: dict[str, Any]
    ) -> serve_module.Job:
        """A job for this person, priced by `Library.prepare` as `/prepare` prices one.

        Its options are the Add page's (`add.js`, `options()`): into the language the
        account reads, from the one it is learning, every word tappable, no glossary."""
        from .serve import Job
        from .translate.prompts import INTO, READING

        offered = {code for code, _ in INTO}
        reads = self.store.reads(person.id) & offered or offered
        into = "en" if "en" in reads else sorted(reads)[0]
        learning = self.store.language(person.id)
        reading = learning if learning in {code for code, _ in READING} else ""
        job = Job(
            ui=ui,
            id=secrets.token_hex(8),
            source=source,
            options={"to": into, "from": reading, "words": True, "gloss": False, **extra},
            owner=person.id,
            admin=person.admin,
            home=self.library.home(person),
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        self.library.prepare(job)
        self.library.remember(job)
        return job

    def _refused(self, chat_id: int, ui: str, job: serve_module.Job) -> bool:
        """Say why `Library.prepare` would not price it, if it would not."""
        if job.stage == "failed":
            self._reply(
                chat_id,
                job.error
                or said_in(
                    ui,
                    "job.unreadable.other",
                    "We couldn't read that. Try again, or paste the text itself.",
                ),
            )
            return True
        if job.stage == "blocked":
            self._reply(chat_id, f"{job.blocked} {self.address}/you".strip())
            return True
        return False

    def _offer(self, chat_id: int, person: Person, ui: str, job: serve_module.Job) -> None:
        """The quote, in one line, with the Build button under it. Nothing is spent until
        the reader presses it."""
        self._quietly(
            lambda: self.client.offer(
                chat_id,
                self._quote(ui, job),
                said_in(ui, "telegram.build", "Open this"),
                PRESS + self._token(chat_id, person.id, job.id),
            )
        )

    def _quote(self, ui: str, job: serve_module.Job) -> str:
        """What the text is and what it uses, in credits and never in money."""
        from .render.builder import credits_of
        from .strings import counted

        title = " ".join((job.title or "").split()) or said_in(ui, "telegram.untitled", "This one")
        if len(title) > QUOTE_TITLE:
            title = title[:QUOTE_TITLE].rsplit(" ", 1)[0] + "…"
        if not job.audio:
            return said_in(
                ui,
                "telegram.quote.text",
                "{title}. It's a text, so it uses none of your credits.",
                title=title,
            )
        credits = credits_of(job.seconds)
        said = counted(
            "telegram.quote",
            credits,
            ui,
            {"one": "{title}. It uses {n} credit.", "other": "{title}. It uses {n} credits."},
        )
        return said.format(title=title, n=credits)

    def _started(self, ui: str, job: serve_module.Job) -> str:
        return said_in(
            ui,
            "telegram.started",
            "Thanks. We're getting it ready, and it'll be in Your targums. Follow it here: {link}",
            link=f"{self.address}/build/{job.id}",
        )

    # -- the Build button ---------------------------------------------------------

    def _token(self, chat_id: int, person_id: int, job_id: str) -> str:
        """What a Build button carries: the job, sealed to the chat and the person it was
        offered to with the webhook's secret.

        Kept nowhere, so a restart does not strand a quote (the job itself is read back
        by `Library._recover`). Unforgeable without the secret, so a button's data typed
        into another chat, or a job id seen in a link, presses nothing; and bound to the
        person as well as the chat, so a chat unlinked and linked to somebody else cannot
        press the quotes it was offered before. The job id rides in it, and is no secret
        from this chat: the reply after a press links `/build/<id>`, which in turn opens
        only for its owner (`Handler._own_job`)."""
        seal = hmac.new(
            self.secret.encode("utf-8"),
            f"press:{chat_id}:{person_id}:{job_id}".encode(),
            hashlib.sha256,
        ).digest()[:16]
        return f"{job_id}:{base64.urlsafe_b64encode(seal).rstrip(b'=').decode('ascii')}"

    def _pressable(self, data: str, chat_id: int, person: Person) -> serve_module.Job | None:
        """The job a button's data names, if it was offered to this chat and this person
        and is still theirs. None for anything else, said the same way whatever it was."""
        if not data.startswith(PRESS):
            return None
        job_id, _, _ = data[len(PRESS) :].partition(":")
        if not re.fullmatch(r"[0-9a-f]{16}", job_id):
            return None
        expected = PRESS + self._token(chat_id, person.id, job_id)
        if not secrets.compare_digest(data.encode("utf-8"), expected.encode("utf-8")):
            return None
        job = self.library.jobs.get(job_id)
        if job is None or job.owner != person.id or job.kind != "build":
            return None
        return job

    def _pressed(self, query: dict[str, Any]) -> None:
        """A press on a Build button: `Library.press`, exactly as `/build` presses.

        The press is the consent, so it is the only thing here that spends. A second
        press of the same quote — a double tap, or the button tapped again before the
        first answer lands — finds the job pressed and leaves it be."""
        from . import incidents as incidents_module

        query_id = str(query.get("id") or "")
        message = query.get("message") or {}
        chat = message.get("chat") or {}
        if chat.get("type") != "private" or not isinstance(chat.get("id"), int):
            return self._quietly(lambda: self.client.answer(query_id))
        chat_id = int(chat["id"])
        ui = self._stranger_language(query)
        try:
            person = self.store.telegram_person(chat_id)
            if person is None:
                self._quietly(lambda: self.client.answer(query_id))
                return self._reply(chat_id, self._link_first(ui))
            ui = self._language(person)
            job = self._pressable(str(query.get("data") or ""), chat_id, person)
            if job is None:
                self._quietly(lambda: self.client.answer(query_id))
                return self._reply(
                    chat_id,
                    said_in(
                        ui,
                        "telegram.press-stale",
                        "That button doesn't work any more. Send it to us again.",
                    ),
                )
            if job.stage in self.library.PRESSED:
                return self._quietly(
                    lambda: self.client.answer(
                        query_id,
                        said_in(ui, "telegram.pressed-already", "We're already getting it ready."),
                    )
                )
            blocked = self.library.press(job)
            self._quietly(lambda: self.client.answer(query_id))
            if blocked:
                # The button stays, so a press after the month turns over still works.
                self.library.remember(job)
                return self._reply(chat_id, f"{blocked} {self.address}/you")
            said = self._quote(ui, job) + "\n" + self._started(ui, job)
            message_id = message.get("message_id")
            if isinstance(message_id, int):
                try:
                    return self.client.edit(chat_id, message_id, said)
                except Exception as error:  # noqa: BLE001 - said as a reply instead
                    log.warning("telegram: %s", error)
            self._reply(chat_id, said)
        except Exception as error:  # noqa: BLE001 - one bad press never takes the door down
            incidents_module.record(self.library.incidents, "telegram", error)
            self._reply(
                chat_id,
                said_in(
                    ui,
                    "telegram.failed",
                    "We couldn't take that. Try again, or send it on {link}.",
                    link=f"{self.address}/add",
                ),
            )

    # -- saying things ------------------------------------------------------------

    def _reply(self, chat_id: int, text: str) -> None:
        self._quietly(lambda: self.client.send(chat_id, text))

    def _quietly(self, call: Callable[[], None]) -> None:
        """A call to Telegram that may fail without taking the update with it. Logged by
        what went wrong, never by the address, which carries the token."""
        try:
            call()
        except Exception as error:  # noqa: BLE001
            log.warning("telegram: %s", error)

    def _link_first(self, ui: str) -> str:
        return said_in(
            ui,
            "telegram.link-first",
            "Link this chat to your targum account first: {link}",
            link=f"{self.address}/you",
        )

    def _what_to_send(self, ui: str) -> str:
        return said_in(
            ui,
            "telegram.what-to-send",
            "Send us a link, a voice note, a video, a picture, a PDF or some text, and we'll "
            "add it to Your targums.",
        )

    def _too_big(self, ui: str, name: str) -> str:
        return said_in(
            ui,
            "telegram.too-big",
            "{name} is over 20 MB, and Telegram won't hand us anything bigger. Send it on {link}.",
            name=name,
            link=f"{self.address}/add",
        )

    def _language(self, person: Person) -> str:
        """The language the account reads the product in, by the desk's own rule."""
        from .strings import drawn_in

        return drawn_in(self.store.reads(person.id))

    @staticmethod
    def _stranger_language(message: dict[str, Any]) -> str:
        """For a chat with no account behind it: the language Telegram says its app is
        in, where targum has words for it, and English where not."""
        from .strings import SOURCE, desk_languages

        sender = message.get("from") or {}
        code = str(sender.get("language_code") or "").split("-")[0].lower()
        return code if code in desk_languages() else SOURCE


def said_in(ui: str, key: str, english: str, **fill: object) -> str:
    """`serve.said_in`, reached lazily: `serve` imports this module."""
    from . import serve

    return serve.said_in(ui, key, english, **fill)


def _now() -> int:
    from .accounts import now

    return now()


def from_environment(library: Library, store: Store, address: str) -> Door | None:
    """The door, where the deployment has given it a bot; None, and the route is a 404,
    where it has not."""
    found = configured()
    if found is None:
        return None
    token, secret, bot = found
    return Door(library, store, BotApi(token), address, bot, secret)
