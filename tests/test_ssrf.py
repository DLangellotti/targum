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
    import httpx

    hops: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hops.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/"})

    monkeypatch.setattr(httpx.Client, "stream", _streamer(handler), raising=True)
    with pytest.raises(TargumError, match="private network"):
        get("https://example.com/article")
    # It made the first request and refused the second before sending it.
    assert hops == ["https://example.com/article"]


def test_a_body_that_never_ends_is_cut_off(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (MAX_BYTES + 1024))

    monkeypatch.setattr(httpx.Client, "stream", _streamer(handler), raising=True)
    with pytest.raises(TargumError, match="too big"):
        get("https://example.com/huge")


def test_too_many_redirects_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://example.com/again"})

    monkeypatch.setattr(httpx.Client, "stream", _streamer(handler), raising=True)
    with pytest.raises(TargumError) as caught:
        get("https://example.com/start")
    assert f"More than {MAX_REDIRECTS} redirects" == caught.value.hint


def _streamer(handler):  # type: ignore[no-untyped-def]
    """Swap httpx's network for a handler, keeping the streaming context manager shape."""
    import contextlib

    import httpx

    @contextlib.contextmanager
    def stream(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
        request = httpx.Request(method, url, params=kwargs.get("params"))
        response = handler(request)
        response.request = request
        yield response

    return stream
