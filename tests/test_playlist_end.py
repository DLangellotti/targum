"""The end of a playlist (targum-internal#367, design.md §12).

After the last item a playlist says what the set held and offers one next set — once. What
must stay true underneath: the counts are real ones, read from the texts' own annotation;
the next set is quoted the first time and the same one comes back every time after; the
quote spends nothing; and a playlist's end is nobody's but its owner's.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from targum.accounts import Person, Store
from targum.chat import tools
from targum.serve import Handler, Library, desk_languages


def signed_in(store: Store, email: str) -> tuple[Person, str]:
    signed = store.finish_sign_in(store.start_sign_in(email))
    assert signed is not None
    return signed


def built(home: Path, name: str, lemmas: list[str]) -> str:
    """A built text with word-level annotation, the shape `coverage.lemmas` reads."""
    folder = home / name
    folder.mkdir(parents=True)
    (folder / "document.json").write_text(
        json.dumps({"language": "he", "source": f"https://example.com/{name}"}), encoding="utf-8"
    )
    tokens = [{"lemma": lemma, "pos": "NOUN"} for lemma in lemmas]
    (folder / "annotation.json").write_text(
        json.dumps({"tokens": {"s1": tokens}}, ensure_ascii=False), encoding="utf-8"
    )
    return name


@pytest.fixture
def door(tmp_path: Path) -> Iterator[tuple[int, Library, Store, Person, str, str]]:
    out = tmp_path / "out"
    out.mkdir()
    store = Store(tmp_path / "words.db")
    library = Library(out, store=store)
    person, mine = signed_in(store, "one@example.com")
    _, theirs = signed_in(store, "two@example.com")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "EndHandler",
        (Handler,),
        {
            "library": library,
            "store": store,
            "token": "test-key",
            "require_account": True,
            "address": f"http://127.0.0.1:{port}",
            "translated": {code: {} for code in desk_languages()},
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, library, store, person, mine, theirs
    finally:
        server.shutdown()
        server.server_close()


def get(port: int, path: str, session: str) -> tuple[int, Any]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(
        "GET",
        f"{path}?k=test-key",
        headers={"Cookie": f"targum_session={session}", "X-Targum-Key": "test-key"},
    )
    response = conn.getresponse()
    got = response.read()
    conn.close()
    return response.status, json.loads(got)


def finished_playlist(library: Library, store: Store, person: Person) -> int:
    home = library.home(person)
    made = store.make_playlist(person.id, "Reels")
    assert made is not None
    for name, lemmas in (("one", ["בית", "ספר", "ילד"]), ("two", ["ילד", "ים"])):
        store.add_to_playlist(person.id, int(made["id"]), name, reader=built(home, name, lemmas))
    return int(made["id"])


def test_the_end_counts_the_words_the_set_held(door, monkeypatch) -> None:
    port, library, store, person, mine, _ = door
    monkeypatch.setattr(tools, "suggest_next", lambda ctx, args: {"suggestions": []})
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": "בית", "status": 9, "band": "easy", "at": 1, "seen": 1}
            ]
        },
    )
    status, said = get(
        port, f"/playlists/{finished_playlist(library, store, person)}/end.json", mine
    )
    assert status == 200
    # Four distinct words across two texts (ילד in both), one of them already theirs.
    assert said["words"] == {"met": 4, "new": 3}
    assert said["next"] is None, "nothing to suggest, so nothing is offered"


def test_the_next_set_is_quoted_once_and_the_same_one_comes_back(door, monkeypatch) -> None:
    port, library, store, person, mine, _ = door
    playlist = finished_playlist(library, store, person)
    monkeypatch.setattr(
        tools,
        "suggest_next",
        lambda ctx, args: {"suggestions": [{"id": "ruth", "title": "Ruth"}]},
    )
    quoted: list[dict[str, Any]] = []

    def quote(ctx: tools.Ctx, args: dict[str, Any]) -> dict[str, Any]:
        quoted.append(args)
        made = store.make_playlist(person.id, str(args["name"]), made_by="chat")
        assert made is not None
        store.add_to_playlist(person.id, int(made["id"]), "Ruth", job="j1")
        return {"set": {"id": made["id"], "name": made["name"]}, "open": f"/set/{made['id']}"}

    monkeypatch.setattr(tools, "quote_set", quote)

    def forbidden(*_: object) -> Any:
        raise AssertionError("the end card must not spend")

    for name in ("claim", "claim_set", "enqueue"):
        monkeypatch.setattr(library, name, forbidden)

    _, first = get(port, f"/playlists/{playlist}/end.json", mine)
    _, second = get(port, f"/playlists/{playlist}/end.json", mine)
    assert len(quoted) == 1, "the end offers more once, and never refills itself"
    assert quoted[0]["items"] == [{"catalogue_id": "ruth", "title": "Ruth"}]
    assert first["next"] == second["next"]
    assert first["next"]["open"] == f"/set/{first['next']['id']}"
    assert first["next"]["count"] == 1 and first["next"]["name"] == "After Reels"
    assert store.next_set(person.id, playlist) == first["next"]["id"]


def test_a_set_that_could_not_be_quoted_is_not_tried_again(door, monkeypatch) -> None:
    port, library, store, person, mine, _ = door
    playlist = finished_playlist(library, store, person)
    asked: list[int] = []

    def nothing(ctx: tools.Ctx, args: dict[str, Any]) -> dict[str, Any]:
        asked.append(1)
        return {"suggestions": []}

    monkeypatch.setattr(tools, "suggest_next", nothing)
    get(port, f"/playlists/{playlist}/end.json", mine)
    get(port, f"/playlists/{playlist}/end.json", mine)
    assert asked == [1] and store.next_set(person.id, playlist) == 0


def test_a_next_set_the_reader_took_away_is_not_offered(door, monkeypatch) -> None:
    port, library, store, person, mine, _ = door
    playlist = finished_playlist(library, store, person)
    other = store.make_playlist(person.id, "After Reels", made_by="chat")
    assert other is not None
    assert store.offer_next_set(person.id, playlist, int(other["id"]))
    assert not store.offer_next_set(person.id, playlist, 999), "the first offer is kept"
    store.drop_playlist(person.id, int(other["id"]))
    _, said = get(port, f"/playlists/{playlist}/end.json", mine)
    assert said["next"] is None


def test_another_accounts_end_is_not_found(door, monkeypatch) -> None:
    port, library, store, person, _, theirs = door
    monkeypatch.setattr(tools, "suggest_next", lambda ctx, args: {"suggestions": []})
    status, _ = get(
        port, f"/playlists/{finished_playlist(library, store, person)}/end.json", theirs
    )
    assert status == 404
    assert get(port, "/playlists/nope/end.json", theirs)[0] == 404


def test_a_text_with_no_annotation_is_not_counted_as_zero(door, monkeypatch) -> None:
    port, library, store, person, mine, _ = door
    monkeypatch.setattr(tools, "suggest_next", lambda ctx, args: {"suggestions": []})
    home = library.home(person)
    (home / "bare").mkdir(parents=True)
    (home / "bare" / "document.json").write_text('{"language": "he"}', encoding="utf-8")
    made = store.make_playlist(person.id, "Bare")
    assert made is not None
    store.add_to_playlist(person.id, int(made["id"]), "Bare", reader="bare")
    _, said = get(port, f"/playlists/{made['id']}/end.json", mine)
    assert said["words"] is None
