"""The URL fetcher is the one place a reader's input becomes an outbound request.

Hosted, it runs on a box with a private network around it and a metadata endpoint
handing out credentials on 169.254.169.254. These are the routes in, and they are
tested rather than reasoned about because the interesting ones — a public address that
redirects somewhere private, a body that never ends — look fine right up until they
are not.
"""

from __future__ import annotations

import pytest

from targum.errors import TargumError
from targum.ingest.url import MAX_BYTES, MAX_REDIRECTS, get


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # AWS, GCP and Azure metadata
        "http://metadata.google.internal/",
        "http://127.0.0.1:8420/",
        "http://localhost/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "http://0.0.0.0/",
    ],
)
def test_a_private_address_is_refused(url: str) -> None:
    with pytest.raises(TargumError):
        get(url)


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "gopher://x/", "ftp://x/", "data:text/html,x"]
)
def test_only_web_pages(url: str) -> None:
    with pytest.raises(TargumError, match="only reads web pages"):
        get(url)


def test_a_redirect_into_the_private_network_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one that matters. A public address is allowed to say "go here instead"."""
    hops: list[str] = []

    def handler(url: str) -> Answer:
        hops.append(url)
        return Answer(302, {"location": "http://169.254.169.254/latest/"})

    answering(monkeypatch, handler)
    with pytest.raises(TargumError, match="private network"):
        get("https://example.com/article")
    # It made the first request and refused the second before sending it.
    assert hops == ["https://example.com/article"]


def test_a_body_that_never_ends_is_cut_off(monkeypatch: pytest.MonkeyPatch) -> None:
    answering(monkeypatch, lambda url: Answer(200, body=b"x" * (MAX_BYTES + 1024)))
    with pytest.raises(TargumError, match="too big"):
        get("https://example.com/huge")


def test_too_many_redirects_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    answering(monkeypatch, lambda url: Answer(302, {"location": "https://example.com/again"}))
    with pytest.raises(TargumError) as caught:
        get("https://example.com/start")
    assert f"More than {MAX_REDIRECTS} redirects" == caught.value.hint


class Answer:
    """One scripted response, shaped like the browser client's.

    The door stopped being httpx's on 2026-09-08 — it impersonates a browser now, since
    six of the seven Hebrew hosts recorded as refusing targum were serving a bot check to
    any client whose TLS handshake is not one (targum-internal#226). These tests patched
    `httpx.Client.stream`, so after the swap they stopped intercepting anything and made
    real requests to example.com, which answered 404 and passed for a while.
    """

    def __init__(self, status: int = 200, headers: dict[str, str] | None = None, body: bytes = b""):
        self.status_code = status
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}
        self._body = body
        self.charset = "utf-8"
        self.encoding = None

    def iter_content(self, chunk_size: int | None = None):  # type: ignore[no-untyped-def]
        yield self._body

    def close(self) -> None:
        return None


def answering(monkeypatch: pytest.MonkeyPatch, handler):  # type: ignore[no-untyped-def]
    """Swap the browser client for a handler, and make sure nothing waits or retries."""
    from targum.ingest import url as url_module

    class Client:
        def get(self, url: str, **kw: object) -> Answer:
            return handler(str(url))

    monkeypatch.setattr(url_module, "POLITE_S", 0.0)
    monkeypatch.setattr(url_module, "_session", lambda proxy="": Client())
    for name in (url_module.FETCH_PROXY_ENV, "TARGUM_YTDLP_PROXY"):
        monkeypatch.delenv(name, raising=False)
