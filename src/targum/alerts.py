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


# -- a provider out of credit ------------------------------------------------------------
#
# OpenAI ran dry on 2026-10-09 and 10-10 and Anthropic on 09-29, and each time the first
# anybody heard of it was a reader whose build failed with the provider's JSON on it
# (known issues 1.10). The reader is now told a sentence (`serve.told`); this tells the
# operator, once per provider per `CREDIT_REMIND`, from the process that met it.

#: What a provider says when the account behind it has run out, lowercased. Rate limits
#: are deliberately not here: they pass on their own, and nobody needs mailing about them.
CREDIT_SIGNS = (
    "credit balance is too low",  # Anthropic, 400 invalid_request_error
    "no credits remaining",  # OpenAI, 429 insufficient_quota
    "insufficient_quota",  # OpenAI
    "exceeded your current quota",  # OpenAI, older wording
    "billing_hard_limit_reached",  # OpenAI
    "billing_not_active",  # OpenAI
    "quota_exceeded",  # ElevenLabs
    "billing_disabled",  # Google (Gemini, Vertex)
    "requires billing to be enabled",  # Google
    "purchase credits",  # Anthropic, the same message's second half
)

#: Who said it, by what the error carries: a name, a host, a header.
PROVIDER_SIGNS = (
    ("anthropic", "Anthropic"),
    ("openai", "OpenAI"),
    ("elevenlabs", "ElevenLabs"),
    ("googleapis", "Google"),
    ("gemini", "Google"),
    ("vertex", "Google"),
)

#: One mail per provider this often while the credit stays out.
CREDIT_REMIND = timedelta(hours=4)


def out_of_credit(said: str) -> str:
    """The provider whose account ran out, if `said` is that refusal, else "".

    "a provider" where the refusal is plain but says nobody's name."""
    low = said.lower()
    if not any(sign in low for sign in CREDIT_SIGNS):
        return ""
    for sign, name in PROVIDER_SIGNS:
        if sign in low:
            return name
    return "a provider"


def credit_due(state: Path, provider: str, now: datetime) -> bool:
    """Whether this provider's running out is news, and marks it told if so.

    Kept in a file rather than in memory, because a deploy restarts the process and
    there were 32 restarts on 2026-10-09: an in-memory limit would have mailed on each."""
    try:
        told = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        told = {}
    if not isinstance(told, dict):
        told = {}
    last = _when(str(told.get(provider) or ""))
    if last is not None and now - last < CREDIT_REMIND:
        return False
    told[provider] = now.isoformat()
    try:
        save_json(state, told)
    except OSError:
        pass  # better a second mail than none
    return True


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = path.with_name(f".{path.name}.tmp")
    fresh.write_text(json.dumps(value, indent=2), encoding="utf-8")
    fresh.replace(path)


@dataclass
class CreditWatch:
    """Where a credit alert goes: the state file and how to send. Configured once, by
    the hosted server (`serve.start`); unconfigured, an alert is a log line only, which
    is what every test and every laptop gets."""

    state: Path | None = None
    send: Callable[[str, str], object] | None = None


CREDIT = CreditWatch()


def credit_ran_out(provider: str, detail: str, *, now: datetime | None = None) -> bool:
    """Tell the operator `provider` is out of credit, unless they were told lately.

    True if a mail went. Never raises: this runs inside a reader's failing build, and a
    mail that did not go must not change what the reader is told."""
    if CREDIT.state is None or CREDIT.send is None or not recipient():
        return False
    moment = now or datetime.now(UTC)
    if not credit_due(CREDIT.state, provider, moment):
        return False
    try:
        CREDIT.send(
            f"targum: {provider} is out of credit",
            f"A build or a turn failed at {moment.strftime(STAMP)} because {provider} "
            "refused for want of credit. Readers are told it is on our side and to try "
            "again in a few hours.\n\n"
            f"What it said: {detail[:600]}\n\n"
            f"Top up the account, then nothing else is needed. Another mail comes after "
            f"{int(CREDIT_REMIND.total_seconds() // 3600)} hours if it is still out.\n",
        )
    except Exception:  # noqa: BLE001 - see above
        return False
    return True


# -- a page that breaks in readers' browsers -------------------------------------------
#
# A reader who meets a broken page usually leaves without telling anyone
# (targum-internal#457). Each browser now reports the error to `/errors`, and the
# operator is mailed when one message is reported `FAULT_THRESHOLD` times within an hour:
# once, and not again about the same message for `FAULT_REMIND`, so a page broken for
# everybody is one mail rather than one per reader.

#: Reports of one message within an hour before anybody is told.
FAULT_THRESHOLD = 5

#: Once told about a message, quiet about it this long.
FAULT_REMIND = timedelta(hours=24)

#: Where a fault alert goes: hosted only, configured beside `CREDIT` (`serve.start`).
FAULTS = CreditWatch()


def page_broke(
    message: str, count: int, page: str = "", place: str = "", *, now: datetime | None = None
) -> bool:
    """Tell the operator a page keeps breaking, once `count` reaches the threshold.

    True if a mail went. Never raises: this runs inside the request that carried the
    report, and the browser that sent it is owed a plain answer whatever the mail did."""
    if count < FAULT_THRESHOLD:
        return False
    if FAULTS.state is None or FAULTS.send is None or not recipient():
        return False
    moment = now or datetime.now(UTC)
    key = message[:300]
    # What was told long enough ago to be told again is forgotten, so the file stays small.
    told: dict[str, str] = {}
    for each, when in load_told(FAULTS.state).items():
        seen = _when(when)
        if seen is not None and moment - seen < FAULT_REMIND:
            told[each] = when
    if key in told:
        return False
    told[key] = moment.isoformat()
    try:
        save_json(FAULTS.state, told)
    except OSError:
        pass  # better a second mail than none
    try:
        FAULTS.send(
            "targum: a page is breaking in readers' browsers",
            f"This has been reported {count} times in the last hour, as of "
            f"{moment.strftime(STAMP)}.\n\n"
            f"Message: {message[:300]}\n"
            f"Page: {page[:300] or 'not said'}\n"
            f"Where in the script: {place[:300] or 'not said'}\n\n"
            "Every report is counted under Operations in the back office. No more mail "
            f"about this message for {int(FAULT_REMIND.total_seconds() // 3600)} hours.\n",
        )
    except Exception:  # noqa: BLE001 - see above
        return False
    return True


def load_told(path: Path) -> dict[str, str]:
    """What has been told and when, or nothing if the file cannot be read."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
