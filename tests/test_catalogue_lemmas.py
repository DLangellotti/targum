"""Known% on every catalogue row, built or not (targum-internal#293).

The front door sells the shelf as "sorted by the words you already know", and the
library could only answer for a text this reader had already built — which for somebody
who has just arrived is none of them. The index beside the catalogue carries every
text's dictionary forms so the same intersection answers for a row nobody has opened.

What is under test is mostly what it refuses to say: an entry with no lemmas is *not
measured*, which is a different claim from 0% known, and the one this number must never
make about a book nobody has counted.
"""

from __future__ import annotations

import json
from pathlib import Path

from targum.coverage import (
    EMPTY,
    INDEX_VERSION,
    KNOWN,
    Index,
    build_index,
    read_index,
    write_index,
)


def test_the_shared_table_holds_each_word_once() -> None:
    index = build_index(
        {
            "genesis": ["אור", "ארץ", "שמים"],
            "recipe": ["ארץ", "מחבת"],
        }
    )
    assert index.words == ("אור", "ארץ", "מחבת", "שמים")
    assert sorted(index.lemmas_for("genesis")) == ["אור", "ארץ", "שמים"]
    assert sorted(index.lemmas_for("recipe")) == ["ארץ", "מחבת"]


def test_a_repeated_word_counts_once_in_a_text() -> None:
    """The denominator is dictionary forms, not running words."""
    index = build_index({"one": ["ארץ", "ארץ", "אור"]})
    assert len(index.texts["one"]) == 2


def test_measuring_against_what_the_reader_marked() -> None:
    index = build_index({"genesis": ["אור", "ארץ", "שמים", "רקיע"]})
    marked = {"אור": KNOWN, "ארץ": KNOWN, "שמים": 2}
    measured = index.against("genesis", marked)
    assert measured is not None
    assert measured.known == 0.5
    # Halfway through learning is not knowing, and `שמים` has been met, so one is fresh.
    assert measured.fresh == 1
    assert measured.total == 4


def test_a_text_not_in_the_index_is_not_measured_rather_than_zero(tmp_path: Path) -> None:
    index = build_index({"genesis": ["אור"]})
    assert index.against("nothing-here", {}) is None
    # And an empty index measures nothing at all, which is what a box without one does.
    assert EMPTY.against("genesis", {}) is None


def test_a_reader_who_knows_none_of_it_is_still_measured() -> None:
    """Nought known is a real answer; not being in the index is the absent one."""
    index = build_index({"genesis": ["אור", "ארץ"]})
    measured = index.against("genesis", {})
    assert measured is not None
    assert measured.known == 0.0
    assert measured.fresh == 2


def test_the_index_survives_a_round_trip(tmp_path: Path) -> None:
    index = build_index({"genesis": ["אור", "ארץ"], "recipe": ["מחבת"]})
    path = tmp_path / "lemmas.json"
    write_index(path, index)
    back = read_index(path)
    assert back.words == index.words
    assert back.texts == index.texts
    assert back.against("genesis", {"אור": KNOWN}) == index.against("genesis", {"אור": KNOWN})


def test_an_index_from_another_version_is_ignored(tmp_path: Path) -> None:
    """Rather than misread: the encoding is what the version is about."""
    path = tmp_path / "lemmas.json"
    path.write_text(
        json.dumps({"version": INDEX_VERSION + 1, "words": ["אור"], "texts": {"a": [0]}}),
        encoding="utf-8",
    )
    assert read_index(path) == EMPTY


def test_a_missing_or_broken_index_is_an_empty_one(tmp_path: Path) -> None:
    """A box with no index measures what it can and says nothing about the rest."""
    assert read_index(None) == EMPTY
    assert read_index(tmp_path / "not-here.json") == EMPTY
    broken = tmp_path / "lemmas.json"
    broken.write_text("{not json", encoding="utf-8")
    assert read_index(broken) == EMPTY


def test_a_position_past_the_table_is_dropped_rather_than_raising() -> None:
    """A truncated index is a bad index, not a crashed library page."""
    index = Index(words=("אור",), texts={"genesis": (0, 7)})
    assert index.lemmas_for("genesis") == ["אור"]


def test_an_entry_with_no_words_is_left_out_of_the_index() -> None:
    index = build_index({"genesis": ["אור"], "empty": [], "blank": [""]})
    assert "genesis" in index.texts
    assert "empty" not in index.texts
    assert "blank" not in index.texts
    assert "" not in index.words


def test_a_rewritten_index_is_read_again(tmp_path: Path) -> None:
    """The parse is cached on the file's stamp, so a rebuild must not serve the old one."""
    path = tmp_path / "lemmas.json"
    write_index(path, build_index({"genesis": ["אור"]}))
    assert read_index(path).lemmas_for("genesis") == ["אור"]
    write_index(path, build_index({"genesis": ["אור", "ארץ"]}))
    assert sorted(read_index(path).lemmas_for("genesis")) == ["אור", "ארץ"]
