"""One search, everywhere (design.md §12, "One search, everywhere", 2026-10-09).

The folding and the table in `search.py`, and the server's two answers: what a typed line
finds, grouped and counted (`/search.json`), and a word's sentences (`/search/word.json`),
with the door that opens a text at one of them (`/sentence/`).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import quote

import pytest

from targum import search, serve
from targum.accounts import Store

# -- spelling ------------------------------------------------------------------------


def test_full_and_defective_spelling_meet() -> None:
    """ירושלים and ירושלם are one city; a pointed title meets an unpointed line."""
    assert search.skeleton(search.fold("ירושלים")) == search.skeleton(search.fold("ירושלם"))
    assert search.fold("יְרוּשָׁלַיִם") == search.fold("ירושלים")
    assert search.Matcher.of("ירושלים").score("ירושלם החדשה")
    assert search.Matcher.of("ירושלם").score("הוצתו משרדי בית״ר ירושלים")
    assert not search.Matcher.of("ירושלים").score("תל אביב")


def test_quotation_marks_and_final_letters_do_not_split_a_name() -> None:
    assert search.fold("צ׳כוב") == search.fold("צ'כוב") == search.fold("צכוב")
    assert search.fold("תנ״ך") == search.fold('תנ"ך')
    assert search.fold("ёлка") == search.fold("елка")


def test_a_transliteration_is_looked_up() -> None:
    """ "tehillim" is Psalms, however it is spelled; "Chekhov" is the Hebrew shelf's
    צ׳כוב and the Russian shelf's Чехов."""
    for typed in ("tehillim", "Tehilim", "t'hillim"):
        assert search.Matcher.of(typed).score("תהילים", "Psalms"), typed
    chekhov = search.Matcher.of("Chekhov")
    assert chekhov.score("הדוב", "The Bear", "אנטון צ׳כוב")
    assert chekhov.score("Каштанка", "Kashtanka", "Антон Чехов")
    assert search.Matcher.of("Чехов").score("הדוב", "The Bear", "אנטון צ׳כוב")


def test_a_title_that_is_the_line_comes_before_one_that_holds_it() -> None:
    match = search.Matcher.of("רות")
    assert match.score("רות") > match.score("רות ונעמי") > match.score("ספר", "about רות")


def test_an_english_line_finds_only_a_word_on_the_readers_list() -> None:
    """David, 2026-10-08: English finds a Hebrew word only where the reader kept it."""
    kept = [("ירושלים", "Jerusalem", 9), ("עיר", "city", 1), ("כלב", "", 2)]
    assert search.matching_words("city", kept) == ["עיר"]
    assert search.matching_words("jerusalem", kept) == ["ירושלים"]
    assert search.matching_words("dog", kept) == [], "no meaning was kept for כלב"
    assert search.matching_words("ירושלם", kept) == ["ירושלים"], "and in its own letters"
    assert search.matching_words("cit", kept) == [], "a whole word, not a piece of one"


def test_the_bands_are_the_librarys() -> None:
    assert [search.band(k) for k in (0.95, 0.9, 0.8, 0.75, 0.5)] == [
        "now",
        "now",
        "stretch",
        "stretch",
        "hard",
    ]
    assert search.band(None) == ""


# -- the server ----------------------------------------------------------------------

STORE: list[Path] = []


@pytest.fixture(scope="module")
def hosted(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, Path]:
    """A server with somebody signed in, two texts of theirs and one on the shared
    shelf, and three words on their list."""
    tmp = tmp_path_factory.mktemp("search")
    store_path = tmp / "targum.db"
    STORE.append(store_path)
    store = Store(store_path)
    token = store.start_sign_in("reader@example.com")
    signed_in = store.finish_sign_in(token)
    assert signed_in is not None
    person = store.whoever(signed_in[1])
    assert person is not None
    home = tmp / "out" / f"p{person.id}"
    _built(home / "ירושלם-he", "ירושלם של מעלה", ["ירושלים", "עיר"], ["בירושלים", "עיר"])
    _built(home / "upload-he", "שיר על הים", ["ים"], ["ים"])
    _built(tmp / "out" / "shared" / "shared-he", "סיפור", ["ירושלים"], ["לירושלים"])
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": "ירושלים", "status": 9, "at": 1, "seen": 1},
                {"language": "he", "lemma": "עיר", "status": 2, "at": 1, "seen": 1},
            ]
        },
    )
    store.db.execute(
        "UPDATE word SET meaning = 'city' WHERE person = ? AND lemma = 'עיר'", (person.id,)
    )
    store.db.commit()
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp / "out",
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address="https://targum.page",
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        try:
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    return port, signed_in[1], tmp


def _built(folder: Path, title: str, lemmas: list[str], surfaces: list[str]) -> None:
    """A built text with one sentence a word, and the word annotated."""
    (folder / "reader").mkdir(parents=True, exist_ok=True)
    (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
    (folder / "reader" / "sec-0001.html").write_text(
        "".join(f'<div class="pair" data-id="s{n}"></div>' for n in range(len(lemmas))),
        encoding="utf-8",
    )
    (folder / "document.json").write_text(
        json.dumps({"title": title, "language": "he", "content_hash": folder.name}),
        encoding="utf-8",
    )
    (folder / "segments.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"id": f"s{n}", "text": f"הנה {surface} כאן"}
                    for n, surface in enumerate(surfaces)
                ]
            }
        ),
        encoding="utf-8",
    )
    (folder / "annotation.json").write_text(
        json.dumps(
            {
                "tokens": {
                    f"s{n}": [{"lemma": lemma, "surface": surfaces[n]}]
                    for n, lemma in enumerate(lemmas)
                }
            }
        ),
        encoding="utf-8",
    )


def ask(port: int, path: str, session: str = "") -> tuple[int, dict, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", "targum.page")
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    conn.close()
    try:
        answer = json.loads(body)
    except ValueError:
        answer = {}
    return response.status, answer, dict(response.getheaders())


def _group(answer: dict, name: str) -> dict:
    return next(group for group in answer["groups"] if group["id"] == name)


def test_signed_out_there_is_nobody_to_search_for(hosted: tuple[int, str, Path]) -> None:
    port, _, _ = hosted
    status, answer, _ = ask(port, "/search.json?q=x")
    assert status == 401 and answer["signIn"] == "/account/signin"


def test_a_line_finds_a_text_of_yours_in_either_spelling(hosted: tuple[int, str, Path]) -> None:
    port, session, _ = hosted
    for typed in ("ירושלים", "ירושלם"):
        status, answer, _ = ask(port, "/search.json?lang=he&q=" + quote(typed), session)
        assert status == 200
        yours = _group(answer, "yours")
        assert [row["title"] for row in yours["rows"]] == ["ירושלם של מעלה"], typed
        row = yours["rows"][0]
        assert row["tag"] == "uploads", "a text with no catalogue entry is an upload"
        assert row["href"].startswith("/reader/")
        # One of its two words is known: measured, and banded in the Library's words.
        assert row["known"] == 0.5 and row["band"] == "hard"
        assert row["bandWord"] == "Hard for now"


def test_a_transliteration_finds_the_library(hosted: tuple[int, str, Path]) -> None:
    port, session, _ = hosted
    status, answer, _ = ask(port, "/search.json?lang=he&q=tehillim", session)
    assert status == 200
    library = _group(answer, "library")
    psalms = next(row for row in library["rows"] if row["entry"] == "psalms")
    assert psalms["href"] == "/open/psalms", "a Library row is its door, never a build"
    assert psalms["what"] == "Poetry"
    assert library["rows"][0]["entry"] == "psalms", "the best match first"


def test_a_search_is_held_to_the_language_and_says_what_the_others_hold(
    hosted: tuple[int, str, Path],
) -> None:
    """ "bereshit" in Hebrew is the Hebrew shelf's Genesis; Onkelos on it is Aramaic, and
    is counted, and a few shown, for "Search all languages"."""
    port, session, _ = hosted
    _, held, _ = ask(port, "/search.json?lang=he&q=bereshit", session)
    assert all(row["language"].startswith("he") for row in _group(held, "library")["rows"])
    assert held["elsewhere"]["language"] == "arc"
    assert held["elsewhere"]["rows"][0]["entry"] == "onkelos-genesis"
    _, every, _ = ask(port, "/search.json?lang=all&q=bereshit", session)
    assert every["language"] == "all" and every["elsewhere"] == {}
    assert {one["code"] for one in every["languages"]} >= {"he", "arc"}
    assert _group(every, "library")["count"] > _group(held, "library")["count"]
    _, aramaic, _ = ask(port, "/search.json?lang=arc&q=bereshit", session)
    assert [row["entry"] for row in _group(aramaic, "library")["rows"]] == ["onkelos-genesis"]


def test_words_in_hebrew_and_in_english(hosted: tuple[int, str, Path]) -> None:
    port, session, _ = hosted
    _, answer, _ = ask(port, "/search.json?lang=he&q=" + quote("עיר"), session)
    words = _group(answer, "words")["rows"]
    assert [word["lemma"] for word in words] == ["עיר"]
    assert words[0]["meaning"] == "city" and words[0]["stage"] == 2
    _, english, _ = ask(port, "/search.json?lang=he&q=city", session)
    assert [word["lemma"] for word in _group(english, "words")["rows"]] == ["עיר"]
    _, sea, _ = ask(port, "/search.json?lang=he&q=sea", session)
    assert _group(sea, "words")["rows"] == [], "ים is on the shelf but not on their list"


def test_nothing_found_is_every_group_empty(hosted: tuple[int, str, Path]) -> None:
    port, session, _ = hosted
    _, answer, _ = ask(port, "/search.json?lang=he&q=" + quote("עגנוןןןן"), session)
    assert all(group["count"] == 0 for group in answer["groups"])
    assert answer["languages"] == [] and answer["elsewhere"] == {}


def test_with_nothing_typed_it_offers_the_languages(hosted: tuple[int, str, Path]) -> None:
    port, session, _ = hosted
    _, answer, _ = ask(port, "/search.json?lang=he", session)
    assert answer["q"] == "" and answer["opened"] == []
    assert answer["learning"][0]["code"] == "he"


def test_texts_with_this_word(hosted: tuple[int, str, Path]) -> None:
    """Every sentence with the word, on the reader's shelf and on the shared one, counted,
    each with the forms it takes there and a door that opens the text at it."""
    port, session, _ = hosted
    status, answer, _ = ask(port, "/search/word.json?lang=he&lemma=" + quote("ירושלים"), session)
    assert status == 200
    assert answer["sentences"] == 2 and answer["texts"] == 2
    assert set(answer["forms"]) == {"בירושלים", "לירושלים"}
    assert answer["stage"] == 9
    mine = answer["yours"]["sentences"][0]
    assert mine["forms"] == ["בירושלים"] and mine["sentence"] == "הנה בירושלים כאן"
    assert mine["href"].startswith("/sentence/")
    shared = answer["library"]["sentences"][0]
    assert shared["href"].endswith("&shared=1")

    status, _, headers = ask(port, mine["href"], session)
    assert status == 302
    assert headers["Location"].endswith("/reader/sec-0001.html#s0")
    status, _, headers = ask(port, shared["href"], session)
    assert status == 302 and "shared-he" in headers["Location"]


def test_a_sentence_door_never_leaves_the_readers_own_shelf(
    hosted: tuple[int, str, Path],
) -> None:
    port, session, _ = hosted
    for name in ("..", "%2E%2E%2Fp1", "nothing-here"):
        status, _, headers = ask(port, f"/sentence/{name}?at=s0", session)
        assert status in (302, 404)
        if status == 302:
            assert headers["Location"] in ("/", "/?k="), headers["Location"]
