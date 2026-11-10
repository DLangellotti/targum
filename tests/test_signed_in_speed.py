"""Home and Your Progress, signed in, in work that does not grow with the reader
(targum-internal#484, 2026-11-10: "it now takes a very long time to open targum").

On the box both pages went from about 0.6 s to 3–6 s. Two costs, each pinned here by the
calls it made rather than by a clock:

- every unmarked word of the whole shared shelf asked the root lexicon whether it is
  borrowed, a stat or three a word, again for every fresh estimate (one after each sync);
- every text the reader has finished a section of walked every folder of every home to
  find itself, so Progress grew with reading.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum import estimate as est
from targum.annotate import root_card
from targum.serve import Library

WORDS = [f"מילה{n:04d}" for n in range(400)]


@pytest.fixture(autouse=True)
def fresh() -> None:
    est.forget()


def counting_lexicon(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []
    real = root_card.lexicon

    def lexicon(language: str) -> Any:
        asked.append(language)
        return real(language)

    monkeypatch.setattr(root_card, "lexicon", lexicon)
    return asked


def test_a_fresh_estimate_asks_the_root_lexicon_once_not_once_a_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = counting_lexicon(monkeypatch)
    known = est.Estimate("he", 9.0, {})
    first = [known.chance(word) for word in WORDS]
    assert len(asked) <= 1, f"the lexicon was asked {len(asked)} times for {len(WORDS)} words"

    # The next estimate (a sync later) knows every word's difficulty already.
    asked.clear()
    again = est.Estimate("he", 9.0, {})
    assert [again.chance(word) for word in WORDS] == first
    assert len(asked) <= 1


def test_a_kept_difficulty_is_the_one_difficulty_works_out() -> None:
    for word in ("של", "זה", "מקלדת", "קוואזר", *WORDS[:5]):
        est.forget()
        plain = est.difficulty(word, "he")
        assert est.difficulty(word, "he") == plain
        assert est.Estimate("he", 9.0, {}).chance(word) == pytest.approx(
            est.sigmoid(est.SLOPE * (9.0 - plain))
        )


def test_a_new_lexicon_still_changes_a_kept_difficulty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The memo is kept per borrowed-word set: a lexicon read again is a fresh one."""
    plain = est.difficulty("מקלדת", "he")
    file = tmp_path / "roots-he.json"
    rows = {"מקלדת": {"root": None, "borrowed": True}}
    body = {"version": "roots/1", "language": "he", "lemmas": rows}
    file.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TARGUM_ROOTS_HE", str(file))
    assert est.difficulty("מקלדת", "he") == pytest.approx(plain - est.BORROWED)


def built(folder: Path, content_hash: str, language: str = "he") -> Path:
    folder.mkdir(parents=True)
    document = {"title": folder.name, "language": language, "content_hash": content_hash}
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    return folder


def test_finding_each_finished_text_walks_a_home_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = Library(tmp_path / "out")
    homes = [tmp_path / "out" / "p1", library.shared]
    for n in range(40):
        built(homes[0] / f"own{n}", f"own{n}")
        built(library.shared / f"shared{n}", f"shared{n}")

    walked: list[Path] = []
    real = Path.iterdir

    def iterdir(self: Path) -> Any:
        if self in homes:
            walked.append(self)
        return real(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    asked = [f"own{n}" for n in range(40)] + [f"shared{n}" for n in range(40)] + ["gone"] * 5
    found = [library.document_folder(homes, one) for one in asked]
    assert found[:40] == [(homes[0] / f"own{n}", "he") for n in range(40)]
    assert found[40:80] == [(library.shared / f"shared{n}", "he") for n in range(40)]
    assert found[80:] == [None] * 5, "a text since deleted is nobody's"
    assert len(walked) <= len(homes), f"{len(walked)} walks of {len(homes)} homes"


def test_a_home_that_changes_is_walked_again(tmp_path: Path) -> None:
    library = Library(tmp_path / "out")
    home = tmp_path / "out" / "p1"
    built(home / "one", "a")
    assert library.document_folder([home], "a") == (home / "one", "he")
    assert library.document_folder([home], "b") is None

    # A text built since is found at once; the home's listing changed.
    built(home / "two", "b", language="ru")
    assert library.document_folder([home], "b") == (home / "two", "ru")

    # A folder rebuilt in place under a new hash is not found under its old one.
    (home / "one" / "document.json").write_text(
        json.dumps({"language": "he", "content_hash": "c"}), encoding="utf-8"
    )
    assert library.document_folder([home], "a") is None


def test_the_readers_own_home_is_asked_first(tmp_path: Path) -> None:
    library = Library(tmp_path / "out")
    own = tmp_path / "out" / "p1"
    built(own / "mine", "same")
    built(library.shared / "theirs", "same")
    assert library.document_folder([own, library.shared], "same") == (own / "mine", "he")
