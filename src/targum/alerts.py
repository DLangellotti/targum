"""Telling the operator when the box is in trouble (targum-internal#20, #16).

Two things on the box used to fail in silence: `/health` answered every five minutes
with nobody asking, and the nightly backup wrote its failures to a journal nobody reads.
Both now mail one address, through the same mailer that sends sign-in links — so there is
no second provider to pay for or to let lapse.

Off until `TARGUM_ALERT_TO` names somebody. Unset, the watch says "not configured" and
exits cleanly, and a failed backup is a line in the journal as it always was.

**It watches from the box, which is its limit.** A box that is powered off, or cut off
from the network, sends nothing, and nothing here can change that: this catches the
service, Caddy, the certificate and the database going wrong on a machine that is still
up. The outside half — a monitor somewhere else that notices the silence — is the
UptimeRobot line on the same card, and it is still worth having.

One mail per outage rather than one per failed check: an alert after `THRESHOLD`
consecutive failures, a reminder every `REMIND` while it stays down, and one mail when it
comes back. A restart takes one check's worth of 502s, and that is not news.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .mail import Mailer, from_environment

#: Who hears about it. One address; unset means nobody, and nothing is sent.
ALERT_ENV = "TARGUM_ALERT_TO"

#: Where the watch knocks. Unset, `TARGUM_PUBLIC_ADDRESS` + /health — through Caddy and
#: the certificate, the way a reader arrives, rather than the loopback port behind them.
HEALTH_URL_ENV = "TARGUM_HEALTH_URL"

#: Consecutive failed checks before anybody is told. Two at five minutes apart is ten
#: minutes down, which a deploy's restart never is.
THRESHOLD = 2

#: While it stays down, a reminder this often and no more.
REMIND = timedelta(hours=6)

#: One knock's patience. `/health` answers in a fifth of a second when it is well.
TIMEOUT = 10.0

STAMP = "%Y-%m-%d %H:%M UTC"


def recipient() -> str:
    return os.environ.get(ALERT_ENV, "").strip()


def health_url() -> str:
    given = os.environ.get(HEALTH_URL_ENV, "").strip()
    if given:
        return given
    public = os.environ.get("TARGUM_PUBLIC_ADDRESS", "").strip().rstrip("/")
    return f"{public}/health" if public else ""


def tell(subject: str, body: str, *, mailer: Mailer | None = None, to: str = "") -> bool:
    """Mail the operator. False if nobody is configured to hear it; raises if the mail
    itself fails, so the caller decides whether that is worth a non-zero exit."""
    address = to or recipient()
    if not address:
        return False
    (mailer or from_environment()).notify(address, subject, body)
    return True


def probe(url: str, *, timeout: float = TIMEOUT) -> str:
    """What is wrong with `/health` at `url`, or "" if it answered ok."""
    request = urllib.request.Request(url, headers={"User-Agent": "targum-watch-health"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            status = answer.status
            raw = answer.read(4096)
    except urllib.error.HTTPError as error:
        return f"HTTP {error.code}"
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        return f"no answer ({reason})"
    if status != 200:
        return f"HTTP {status}"
    try:
        said = json.loads(raw)
    except ValueError:
        return "an answer that is not JSON"
    if not isinstance(said, dict) or said.get("ok") is not True:
        return f"ok is not true: {raw[:200].decode('utf-8', 'replace')}"
    return ""


@dataclass
class Watch:
    """What the last checks found, kept between runs in one small JSON file."""

    failures: int = 0
    down_since: str = ""
    alerted_at: str = ""
    last_problem: str = ""


def load(path: Path) -> Watch:
    """The saved state, or a fresh one. An unreadable file starts over rather than
    stopping the watch: the worst that costs is one alert sent twice."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Watch()
    if not isinstance(raw, dict):
        return Watch()
    known = {key: raw[key] for key in Watch.__dataclass_fields__ if key in raw}
    try:
        return Watch(**known)
    except TypeError:
        return Watch()


def save(path: Path, watch: Watch) -> None:
    """Written whole and moved into place, so a kill mid-write leaves the old state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = path.with_name(f".{path.name}.tmp")
    fresh.write_text(json.dumps(asdict(watch), indent=2), encoding="utf-8")
    fresh.replace(path)


def _when(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp)
    except ValueError:
        return None


def step(
    before: Watch, problem: str, now: datetime, url: str
) -> tuple[Watch, tuple[str, str] | None]:
    """The next state, and the mail to send if one is due. Pure, so the rules are tested
    without a clock, a network or a mailer."""
    if not problem:
        if before.alerted_at:
            since = _when(before.down_since)
            lasted = f", down since {since.strftime(STAMP)}" if since else ""
            return Watch(), (
                "targum: /health is answering again",
                f"{url} answered ok at {now.strftime(STAMP)}{lasted}.\n\n"
                f"The last thing it said while down: {before.last_problem}\n",
            )
        return Watch(), None

    after = Watch(
        failures=before.failures + 1,
        down_since=before.down_since or now.isoformat(),
        alerted_at=before.alerted_at,
        last_problem=problem,
    )
    if after.failures < THRESHOLD:
        return after, None
    last = _when(before.alerted_at)
    if last is not None and now - last < REMIND:
        return after, None
    since = _when(after.down_since) or now
    again = "still " if last is not None else ""
    after.alerted_at = now.isoformat()
    return after, (
        f"targum: /health {again}failing since {since.strftime(STAMP)}",
        f"{url} has failed {after.failures} checks in a row, five minutes apart.\n\n"
        f"Last answer: {problem}\n\n"
        "On the box:\n"
        "  systemctl status targum\n"
        "  journalctl -u targum -n 80 --no-pager\n\n"
        f"Another mail comes when it answers again, and a reminder every "
        f"{int(REMIND.total_seconds() // 3600)} hours until then.\n",
    )


def watch(
    state: Path,
    url: str,
    *,
    now: datetime | None = None,
    knock: Callable[[str], str] | None = None,
    send: Callable[[str, str], object] | None = None,
) -> str:
    """One check: knock, update the state, mail if a mail is due. Returns a line for the
    journal. Raises if a due mail could not be sent — after saving a state that will try
    again on the next check, so an outage is never marked as told when it was not."""
    # Looked up when called rather than bound as defaults, so the module's own two can
    # be replaced as a whole.
    knock = knock or probe
    send = send or tell
    moment = now or datetime.now(UTC)
    before = load(state)
    problem = knock(url)
    after, mail = step(before, problem, moment, url)
    if mail is None:
        save(state, after)
        return f"ok ({url})" if not problem else f"failing {after.failures}x: {problem}"
    try:
        send(*mail)
    except Exception:
        # Down and untold: keep counting, leave `alerted_at` as it was, so the next check
        # owes the same mail. Recovered and untold: keep the whole down state, so the
        # next healthy check owes the recovery mail.
        if problem:
            after.alerted_at = before.alerted_at
            save(state, after)
        else:
            save(state, before)
        raise
    save(state, after)
    return f"mailed: {mail[0]}"
