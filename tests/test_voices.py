"""A real voice for a word: Lingua Libre's recordings (targum-internal#610; design.md §12,
"A word is said by a person where one recorded it", 2026-10-31).

Every manifest here is synthetic and every Commons answer is a fake: the suite never
connects, and no recording leaves the test's own folder.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
from pathlib import Path
from typing import Any

import pytest
from test_chat_serve import call as chat_call
from test_chat_serve import chatting  # noqa: F401 - the fixture, used by name
from test_serve import call, hosted

from targum import voices
from targum.voices import Index, Manifest, Recording

CC0 = {
    "License": {"value": "cc0"},
    "LicenseShortName": {"value": "CC0"},
    "LicenseUrl": {"value": "http://creativecommons.org/publicdomain/zero/1.0/deed.en"},
}
BY_SA = {
    "License": {"value": "cc-by-sa-4.0"},
    "LicenseShortName": {"value": "CC BY-SA 4.0"},
    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
}
BY = {
    "License": {"value": "cc-by-4.0"},
    "LicenseShortName": {"value": "CC BY 4.0"},
    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/4.0"},
}


def artist(name: str) -> dict[str, Any]:
    return {
        "Artist": {
            "value": f'<ul><li>Speaker: <a href="//lingualibre.org/wiki/Q1">{name}</a></li>'
            f'<li>Recorder: <a href="//commons.wikimedia.org/wiki/User:{name}">{name}</a></li></ul>'
        }
    }


def page(word: str, speaker: str, terms: dict[str, Any], n: int) -> dict[str, Any]:
    title = f"File:LL-Q9288 (heb)-{speaker}-{word}.wav"
    return {
        "pageid": n,
        "title": title,
        "imageinfo": [
            {
                "url": f"https://upload.wikimedia.org/x/{n}.wav?utm_source=x",
                "descriptionurl": f"https://commons.wikimedia.org/wiki/{title}",
                "sha1": f"{n:040x}",
                "duration": 1.2,
                "extmetadata": {**terms, **artist(speaker)},
            }
        ],
        "videoinfo": [
            {
                "derivatives": [
                    {"src": f"https://upload.wikimedia.org/t/{n}.wav.mp3", "type": "audio/mpeg"}
                ]
            }
        ],
    }


def recording(word: str, speaker: str = "YaronSh", licence: str = "CC0", n: int = 1) -> Recording:
    return Recording(
        word=word,
        file=f"{n:016x}.mp3",
        title=f"File:LL-Q9288 (heb)-{speaker}-{word}.wav",
        page=f"https://commons.wikimedia.org/wiki/File:{n}",
        licence=licence,
        licence_url="https://creativecommons.org/",
        speaker=speaker,
    )


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A cache with a synthetic manifest and its files: three words, two speakers."""
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    manifest = Manifest(
        language="he",
        recordings=[
            recording("אֶחָד", n=1),
            recording("סֵפֶר", n=2),
            recording("סַפָּר", "Buffer", "CC BY-SA 4.0", n=3),
            recording("שָׁלוֹם", "Buffer", "CC BY-SA 4.0", n=4),
            recording("שָׁלוֹם", n=5),
        ],
    )
    folder = voices.folder("he")
    folder.mkdir(parents=True)
    voices.manifest_path("he").write_text(manifest.to_json(), encoding="utf-8")
    for one in manifest.recordings:
        (folder / one.file).write_bytes(b"ID3" + one.word.encode())
    return folder


# -- reading Commons -----------------------------------------------------------------


def test_only_cc0_and_by_sa_pass_read_per_file() -> None:
    assert voices.licence(CC0) == voices.Licence("CC0", CC0["LicenseUrl"]["value"])
    assert voices.licence(BY_SA) is not None and voices.licence(BY_SA).name == "CC BY-SA 4.0"
    assert voices.licence(BY) is None, "BY without SA is not on this card's list"
    assert voices.licence({"License": {"value": "cc-by-nc-sa-4.0"}}) is None
    assert voices.licence({}) is None


def test_a_file_is_read_into_its_word_speaker_and_mp3() -> None:
    one, why = voices.read(page("אֶחָד", "YaronSh", CC0, 7))
    assert why == "" and one is not None
    assert one.word == "אֶחָד" and one.speaker == "YaronSh" and one.licence == "CC0"
    assert one.source == "https://upload.wikimedia.org/t/7.wav.mp3", "Commons' MP3 copy"
    assert one.file.endswith(".mp3") and "/" not in one.file
    assert "YaronSh" in one.attribution and "CC0" in one.attribution
    # A speaker with a hyphen in their name keeps the whole word.
    two, _ = voices.read(page("בַּיִת", "Ab-Cd", BY_SA, 8))
    assert two is not None and two.word == "בַּיִת" and two.speaker == "Ab-Cd"


def test_what_is_left_out_is_said_why() -> None:
    assert voices.read(page("Apache HTTP Server", "Uziel302", CC0, 1)) == (None, "not-hebrew")
    assert voices.read(page("כֶּלֶב", "Cyber124", BY, 2)) == (None, "licence")
    assert voices.read({"title": "File:Something else.wav"}) == (None, "not-lingualibre")


def test_fetch_pages_politely_writes_the_manifest_then_the_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    asked: list[str] = []
    first = {
        "continue": {"gcmcontinue": "next", "continue": "gcmcontinue||"},
        "query": {"pages": [page("אֶחָד", "YaronSh", CC0, 1), page("כֶּלֶב", "X", BY, 2)]},
    }
    second = {"query": {"pages": [page("שְׁתַּיִם", "Buffer", BY_SA, 3)]}}

    def get(url: str) -> bytes:
        asked.append(url)
        if url.startswith(voices.API):
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            return json.dumps(second if "gcmcontinue" in query else first).encode()
        return b"ID3 " + url.encode()

    manifest = voices.fetch("he", get=get, pause=0, download=True, say=lambda _: None)
    assert [one.word for one in manifest.recordings] == ["אֶחָד", "שְׁתַּיִם"]
    assert manifest.skipped == {"licence": 1}
    kept = voices.load("he")
    assert kept is not None and [r.speaker for r in kept.recordings] == ["YaronSh", "Buffer"]
    assert all(one.path("he").read_bytes().startswith(b"ID3") for one in kept.recordings)
    assert all("upload.wikimedia.org" in url or url.startswith(voices.API) for url in asked)
    # A second run fetches no file it already has.
    asked.clear()
    voices.fetch("he", get=get, pause=0, download=True, say=lambda _: None)
    assert all(url.startswith(voices.API) for url in asked)


# -- matching ------------------------------------------------------------------------


def test_a_pointed_word_matches_exactly_and_a_bare_one_only_alone() -> None:
    index = Index([recording("אֶחָד", n=1), recording("סֵפֶר", n=2), recording("סַפָּר", n=3)])
    assert index.match("אֶחָד")[1] == "pointed"
    # Cantillation and meteg are not part of how the file names it.
    assert index.match("אֶ֖חָֽד")[1] == "pointed"
    assert index.match("אחד") == (index.by_pointed["אֶחָד"], "bare")
    assert index.match("ספר") == (None, "ambiguous"), "two words have those letters"
    # Pointed another way is another word: no bare fallback.
    assert index.match("אֶחַד") == (None, "none")
    assert index.match("בית") == (None, "none")
    assert index.match("hello") == (None, "none")


def test_cc0_and_the_bigger_speaker_win_a_word_two_people_said() -> None:
    index = Index(
        [
            recording("שָׁלוֹם", "Buffer", "CC BY-SA 4.0", n=1),
            recording("שָׁלוֹם", "Small", "CC0", n=2),
            recording("מַיִם", "Big", "CC0", n=3),
            recording("מַיִם", "Small", "CC0", n=4),
            recording("לֶחֶם", "Big", "CC0", n=5),
        ]
    )
    assert index.match("שָׁלוֹם")[0].speaker == "Small"
    assert index.match("מַיִם")[0].speaker == "Big"


def test_coverage_counts_each_way_a_lemma_is_found() -> None:
    index = Index([recording("אֶחָד", n=1), recording("סֵפֶר", n=2), recording("סַפָּר", n=3)])
    found = voices.coverage(index, ["אֶחָד", "אחד", "ספר", "בַּיִת"])
    assert found == {"pointed": 1, "bare": 1, "ambiguous": 1, "none": 1}


def test_find_offers_only_a_file_on_disk(kept: Path) -> None:
    assert voices.find("אחד", "he") is not None
    assert voices.find("אחד", "fr") is None
    (kept / voices.find("אחד", "he").file).unlink()  # type: ignore[union-attr]
    assert voices.find("אחד", "he") is None, "a manifest line with no file is not offered"


def test_no_manifest_means_the_voice_as_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "empty"))
    assert voices.find("אחד") is None and voices.credits() == []


# -- serving -------------------------------------------------------------------------


def test_a_recorded_word_is_said_by_the_person_free_and_credited(
    chatting: Any,  # noqa: F811
    kept: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum import speech

    port, key, store, chats = chatting

    def render(*_: Any, **__: Any) -> Any:
        raise AssertionError("a recorded word never reaches the voice")

    monkeypatch.setattr(speech, "render", render)
    monkeypatch.delenv(speech.KEY, raising=False)
    monkeypatch.delenv(speech.VERTEX_KEY, raising=False)
    before = store.committed(0)
    status, body, _ = chat_call(
        port, "POST", f"/say-word?k={key}", {"text": "אחד", "language": "he"}
    )
    assert status == 200 and body["audio"].startswith("data:audio/mpeg;base64,")
    assert base64.b64decode(body["audio"].split(",", 1)[1]) == b"ID3" + "אֶחָד".encode()
    assert body["by"] == {"speaker": "YaronSh", "licence": "CC0", "credits": "/credits#voices"}
    assert store.committed(0) == pytest.approx(before), "nothing claimed"
    assert not [job for job in chats.library.jobs.values() if job.source == "word:he"]
    # A word nobody recorded goes to the voice as before, with no credit.
    status, body, _ = chat_call(
        port, "POST", f"/say-word?k={key}", {"text": "ספר", "language": "he"}
    )
    assert "by" not in body


def test_the_credits_page_is_open_and_names_every_speaker(tmp_path: Path, kept: Path) -> None:
    port, _, server = hosted(tmp_path)
    try:
        status, body, _ = call(port, "GET", "/credits")
        assert status == 200
        page_text = body if isinstance(body, str) else body.decode()
        assert "Coming soon" not in page_text
        assert 'id="voices"' in page_text
        assert "YaronSh" in page_text and "Buffer" in page_text
        assert "CC BY-SA 4.0" in page_text and "CC0" in page_text
        assert "אֶחָד" in page_text and "https://commons.wikimedia.org/wiki/File:1" in page_text
        # The yardsticks' sources (design.md §12, 2026-11-01): the citation OPUS asks for
        # with its link, the volunteers Ben-Yehuda asks to be named, and OSHB's licence.
        assert 'id="word-counts"' in page_text
        assert "Lison and J. Tiedemann, 2016" in page_text
        assert 'href="https://www.opensubtitles.org"' in page_text
        assert "Project Ben-Yehuda volunteers" in page_text
        assert 'href="https://benyehuda.org"' in page_text
        assert "Open Scriptures Hebrew Bible Project" in page_text
        assert "Westminster Leningrad Codex" in page_text
    finally:
        server.shutdown()
