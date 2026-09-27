"""A Telegram bot as a door onto /add (targum-internal#328, slice 1).

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
  first, with a link to the same `/build/<id>` page a connector's quote uses, so the
  press is still the reader's own on targum's page (David, 2026-09-27).
- **Nothing about the message is kept but its content.** A forward carries its original
  sender's name; it is never read, so it can never land in somebody else's library. No
  message log: the update is answered and dropped.
- **The bot only answers.** One reply per message it was sent, never a message first.
- **The hosted Bot API downloads up to 20 MB.** Bigger files are refused by name, with
  the address of the Add page, which takes them.

Links, and the quote button they need, are slice 2: a link today gets one line pointing
at the Add page.
"""

from __future__ import annotations

import hashlib
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
    """The four calls the door makes to Telegram. A protocol, so a test can stand in."""

    def send(self, chat_id: int, text: str) -> None: ...

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
    at its foot is a text; a message that is one address is a link, which is slice 2."""
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

        message = update.get("message")
        if not isinstance(message, dict):
            # An edit, a channel post, a button: nothing slice 1 answers.
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
            said_in(ui, "telegram.linked", "Thanks, this chat is linked to your targum.")
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
                return self._reply(
                    chat_id,
                    said_in(
                        ui,
                        "telegram.links-later",
                        "We can't take links here yet. Paste it on {link}.",
                        link=f"{self.address}/add",
                    ),
                )
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

    def _build(self, chat_id: int, person: Person, ui: str, source: Path) -> None:
        """Price it and, unless it is a long recording, start it: `Library.prepare`, then
        `Library.claim`, then the queue — the three steps `/prepare` and `/build` take,
        in their order, and no second way to the rails."""
        from .render.builder import credits_of
        from .serve import Job
        from .strings import counted
        from .translate.prompts import INTO, READING

        offered = {code for code, _ in INTO}
        reads = self.store.reads(person.id) & offered or offered
        into = "en" if "en" in reads else sorted(reads)[0]
        learning = self.store.language(person.id)
        reading = learning if learning in {code for code, _ in READING} else ""
        job = Job(
            ui=ui,
            id=secrets.token_hex(8),
            source=str(source),
            options={"to": into, "from": reading, "words": True, "gloss": False},
            owner=person.id,
            admin=person.admin,
            home=self.library.home(person),
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        self.library.prepare(job)
        self.library.remember(job)
        press = f"{self.address}/build/{job.id}"
        if job.stage == "failed":
            return self._reply(
                chat_id,
                job.error
                or said_in(
                    ui,
                    "job.unreadable.other",
                    "We couldn't read that. Try again, or paste the text itself.",
                ),
            )
        if job.stage == "blocked":
            return self._reply(chat_id, f"{job.blocked} {self.address}/you".strip())
        if job.audio and job.seconds > ASK_OVER_SECONDS:
            credits = credits_of(job.seconds)
            said = counted(
                "telegram.asks",
                credits,
                ui,
                {
                    "one": "Thanks. This one uses {n} credit. Confirm it here: {link}",
                    "other": "Thanks. This one uses {n} credits. Confirm it here: {link}",
                },
            )
            return self._reply(chat_id, said.format(n=credits, link=press))
        blocked = self.library.claim(job)
        if blocked:
            job.blocked = blocked
            job.stage = "blocked"
            self.library.remember(job)
            return self._reply(chat_id, f"{blocked} {self.address}/you")
        self.library.enqueue(job)
        self._reply(
            chat_id,
            said_in(
                ui,
                "telegram.started",
                "Thanks. We're getting it ready, and it'll be on your shelf: {link}",
                link=press,
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
            "Link your targum account first, from {link}.",
            link=f"{self.address}/you",
        )

    def _what_to_send(self, ui: str) -> str:
        return said_in(
            ui,
            "telegram.what-to-send",
            "Send us a voice note, a video, a picture, a PDF or some text, and we'll put it "
            "on your shelf.",
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
