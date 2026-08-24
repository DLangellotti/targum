"""Everything that has to be true before a stranger is given the address.

A deployment fails in one of two places: at deploy, where nobody is watching and it costs
a minute, or at somebody's first sign-in, where it costs the only alpha reader there is.
This moves as much as possible into the first. Every check says what to do about itself,
because a check that only reports a state is a check somebody has to go and interpret.

Nothing here spends money or sends mail. It resolves and connects, and stops there.
"""

from __future__ import annotations

import os
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Stanza and LaBSE are the bulk of it, and a box that fills up mid-build leaves a
# half-written reader behind. Five gigabytes is room for the models plus working space.
LEAST_DISK_GB = 5.0
SMTP_TIMEOUT = 5.0


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


def check_account_required() -> Check:
    if _env("TARGUM_REQUIRE_ACCOUNT").lower() in {"1", "true", "yes"}:
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


def check_invitations(store: Path) -> Check:
    """Whether anybody may open an account here.

    Hosted, an empty list means nobody can — which is the right default but the wrong
    thing to discover from a reader saying the link never came. A warning rather than a
    failure: a box with nobody invited yet is a normal state on the way to inviting
    somebody, and refusing to start would leave no way to run the command that fixes it.
    """
    if _env("TARGUM_REQUIRE_ACCOUNT").lower() not in {"1", "true", "yes"}:
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
    checks.append(check_invitations(store))
    checks += check_paths(store, out)
    checks += [check_disk(store.parent), check_port(port)]
    return checks


def fatal(checks: list[Check]) -> list[Check]:
    return [c for c in checks if not c.ok and c.fatal]
