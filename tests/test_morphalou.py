"""Morphalou, looked up for how a French word is said, and the count of how much of the
French shelf it reaches (targum-internal#266).

Offline: a few rows written in the table's own shape. What is under test is the lookup —
which spelling finds a transcription, when a form is said two ways and what decides it —
and the measurement's idea of a word, which is the denominator of the number the owner
decides on.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from targum.annotate import morphalou
from targum.errors import TargumError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure_pronunciation.py"

#: The table's preamble, its two header rows, and then a lemma's first row carrying its
#: spelling and category, its other forms carrying only their own columns.
TABLE = """\
---------------------------------------------------------------------------
Morphalou3.1 : Lexique morphologique ouvert du français
---------------------------------------------------------------------------
LEMME;;;;;;;;;FLEXION;;;;;;;;
GRAPHIE;ID;CATÉGORIE;SOUS CATÉGORIE;LOCUTION;GENRE;AUTRES LEMMES LIÉS;PHONÉTIQUE;ORIGINES;\
GRAPHIE;ID;NOMBRE;MODE;GENRE;TEMPS;PERSONNE;PHONÉTIQUE;ORIGINES
homme;1;Nom commun;;;masculine;;O m @;m;homme;1;singular;-;-;-;-;O m @;m
;;;;;;;;;hommes;2;plural;-;-;-;-;O m @;m
le;2;Déterminant;;;-;;l @;m;le;3;singular;-;masculine;-;-;l @;m
;;;;;;;;;l';4;singular;-;-;-;-;l;m
être;3;Verbe;;;-;;E t R @;m;est;5;singular;indicative;-;present;thirdPerson;e OU E/;m
est;4;Nom commun;;;masculine;;E s t;m;est;6;singular;-;-;-;-;E s t;m
il;5;Pronom;;;-;;i l;m;il;7;singular;-;masculine;-;thirdPerson;i l;m
dire;6;Verbe;;;-;;d i R @;m;dit;8;singular;indicative;-;present;thirdPerson;d i;m
œil;7;Nom commun;;;masculine;;;m;œil;9;singular;-;-;-;-;;m
oeil;8;Nom commun;;;masculine;;9 j;m;oeil;10;singular;-;-;-;-;9 j;m
aujourd'hui;9;Adverbe;;;-;;;m;aujourd'hui;11;invariable;-;-;-;-;;m
là;10;Adverbe;;;-;;l a;m;là;12;invariable;-;-;-;-;l a;m
bas;11;Adverbe;;;-;;b a;m;bas;13;invariable;-;-;-;-;b a;m
jour;12;Nom commun;;;masculine;;Z u R;m;jour;14;singular;-;-;-;-;Z u R;m
avoir;13;Verbe;;;-;;a v w a R;m;a;15;singular;indicative;-;present;thirdPerson;a;m
"""


@pytest.fixture
def lexicon() -> morphalou.Lexicon:
    return morphalou.parse(TABLE.splitlines())


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("measure_pronunciation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass looks its module up while it is made
    spec.loader.exec_module(module)
    return module


def test_a_form_is_found_as_written_in_lower_case_and_with_its_ligature_spelled_out(
    lexicon: morphalou.Lexicon,
) -> None:
    assert lexicon.transcriptions("hommes") == [frozenset({"O m @"})]
    assert lexicon.transcriptions("Homme") == [frozenset({"O m @"})], "a capital is not a miss"
    assert lexicon.transcriptions("l’") == [frozenset({"l"})], "the curly apostrophe is read"
    assert lexicon.transcriptions("Œil") == [frozenset({"9 j"})], "œil has none, oeil has one"


def test_a_form_listed_without_a_transcription_is_listed_and_not_covered(
    lexicon: morphalou.Lexicon,
) -> None:
    assert lexicon.transcriptions("aujourd'hui") == []
    assert lexicon.listed("aujourd'hui") and not lexicon.listed("Seguin")


def test_a_form_said_two_ways_is_decided_by_its_lemma_or_part_of_speech(
    lexicon: morphalou.Lexicon,
) -> None:
    assert len(lexicon.transcriptions("est")) == 2, "the verb and the east"
    assert lexicon.transcriptions("est", pos="AUX") == [frozenset({"e", "E/"})]
    assert lexicon.transcriptions("est", lemma="est", pos="NOUN") == [frozenset({"E s t"})]
    assert len(lexicon.transcriptions("est", pos="ADV")) == 2, "nothing agrees: all of it"


def test_features_that_disagree_with_a_row_drop_it(lexicon: morphalou.Lexicon) -> None:
    found = lexicon.transcriptions("est", feats="Mood=Ind|Tense=Pres|Person=3|Number=Sing")
    assert found == [frozenset({"e", "E/"})], "the east has no mood, but the verb has this one"


def test_nothing_is_read_where_nothing_was_fetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    morphalou.load.cache_clear()
    assert morphalou.available() is False and morphalou.lexicon() is None
    with pytest.raises(TargumError, match="not downloaded"):
        morphalou.load(tmp_path / "nowhere")


def test_no_row_of_the_table_is_in_the_repository() -> None:
    """Looked up, never committed: the table lives in the model directory and nowhere in
    the tree the wheel is built from."""
    root = Path(__file__).resolve().parents[1]
    for path in [*root.glob("src/**/*.csv"), *root.glob("src/**/*.json")]:
        head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
        assert "Morphalou3" not in head, path


def test_a_word_is_split_the_way_the_reader_splits_it(lexicon: morphalou.Lexicon) -> None:
    script = load_script()
    said = [word.surface for word in script.words("L’homme dit-il, aujourd'hui.", lexicon)]
    assert said == ["L'", "homme", "dit", "il", "aujourd'hui"]
    said = [word.surface for word in script.words("a-t-il ce jour-là, là-bas", lexicon)]
    assert said == ["a", "il", "ce", "jour", "là", "là-bas"], "the euphonic t is no word"
    said = [word.surface for word in script.words("« 1885 » — M. Loisel !", lexicon)]
    assert said == ["1885", "M", "Loisel"], "punctuation is no word, a number is"


def test_a_miss_is_filed_under_what_kind_of_word_it_is(lexicon: morphalou.Lexicon) -> None:
    script = load_script()
    kinds = {
        word: script.kind(word, lexicon)
        for word in ["1885", "XII", "M", "qu'", "Loisel", "là-bas", "aujourd'hui", "tiiit"]
    }
    assert kinds == {
        "1885": "number",
        "XII": "number",
        "M": "abbreviation",
        "qu'": "elision",
        "Loisel": "capitalised",
        "là-bas": "hyphenated",
        "aujourd'hui": "listed, no transcription",
        "tiiit": "not listed",
    }
    assert script.by_parts("là-bas", lexicon) and not script.by_parts("mère-grand", lexicon)


def test_coverage_is_counted_over_tokens_and_over_types(lexicon: morphalou.Lexicon) -> None:
    script = load_script()
    one = script.tally(script.words("L'homme est là. L'homme dit : Loisel.", lexicon), lexicon)
    assert (one.tokens, one.covered) == (8, 7)
    assert one.token_share() == pytest.approx(7 / 8)
    assert (len(one.types), len(one.covered_types)) == (6, 5), "a type is its lower case"
    assert one.ambiguous == 1 and one.undecided == {"est": 1}
    assert one.misses == {"loisel": 1} and one.kinds == {"capitalised": 1}


def test_a_reader_token_that_carries_its_grammar_decides_between_two_readings(
    lexicon: morphalou.Lexicon,
) -> None:
    script = load_script()
    one = script.tally([script.Word("est", "être", "AUX", "Mood=Ind")], lexicon)
    assert (one.covered, one.resolved, one.ambiguous) == (1, 1, 0)


LICENCE = "GNU Lesser General Public License for Linguistic Resources\n"


def _zipped(table: str) -> bytes:
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"Morphalou3.1_formatCSV_toutEnUn/{morphalou.TABLE}", table)
    return bundle.getvalue()


class _Answer:
    """A streamed answer, as httpx gives it: no `.content`, so a fetch that reads the whole
    body at once fails here rather than passing."""

    def __init__(self, body: bytes, chunks: list[int]) -> None:
        self.body, self.chunks = body, chunks

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self, size: int) -> Iterator[bytes]:
        self.chunks.append(size)
        for start in range(0, len(self.body), 7):  # small, so the hash spans many chunks
            yield self.body[start : start + 7]


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """Morphalou's two files served from memory, pinned to their own checksums: no test
    reaches ORTOLANG."""
    import httpx

    files = {
        morphalou.SOURCE: _zipped(TABLE),
        morphalou.LICENCE_SOURCE: LICENCE.encode("utf-8"),
    }
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(morphalou, "SHA256", hashlib.sha256(files[morphalou.SOURCE]).hexdigest())
    monkeypatch.setattr(
        morphalou,
        "LICENCE_SHA256",
        hashlib.sha256(files[morphalou.LICENCE_SOURCE]).hexdigest(),
    )
    chunks: list[int] = []

    @contextmanager
    def stream(method: str, url: str, **_kwargs: Any) -> Iterator[_Answer]:
        assert method == "GET"
        yield _Answer(files[url], chunks)

    monkeypatch.setattr(httpx, "stream", stream)
    morphalou.load.cache_clear()
    yield files
    morphalou.load.cache_clear()


def test_the_fetch_streams_the_zip_to_disk_and_the_table_out_of_it(
    served: dict[str, bytes],
) -> None:
    """targum-internal#682: the 38 MB zip was held in memory and the 106 MB table decoded
    and re-encoded out of it, ~790 MB at the peak, beside the service on every deploy."""
    assert morphalou.available() is False
    size = morphalou.fetch()
    folder = morphalou.directory()
    assert (folder / morphalou.TABLE).read_text(encoding="utf-8") == TABLE
    assert size == len(TABLE.encode("utf-8"))
    assert (folder / morphalou.LICENCE_FILE).read_text(encoding="utf-8") == LICENCE
    assert sorted(path.name for path in folder.iterdir()) == sorted(
        [morphalou.TABLE, morphalou.LICENCE_FILE]
    ), "the zip and the partial files are gone"
    assert morphalou.available() and morphalou.lexicon() is not None
    assert morphalou.lexicon().transcriptions("hommes") == [frozenset({"O m @"})]


def test_a_zip_that_is_not_the_pinned_one_writes_nothing(
    served: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(morphalou, "SHA256", "0" * 64)
    with pytest.raises(TargumError, match="not the file this version of targum pins"):
        morphalou.fetch()
    assert morphalou.available() is False
    assert list(morphalou.directory().iterdir()) == [], "no table, no licence, no partial file"
