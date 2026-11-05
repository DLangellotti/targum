"""Multiword units: an idiom is one word to know (design.md §12, "An idiom is one word to
know", 2026-11-05; targum-internal#614)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from targum import coverage, units
from targum.coverage import KNOWN, build_index, measure_running, units_in


def token(surface: str, lemma: str, start: int, pos: str = "ADV", lead: int = 0) -> dict[str, Any]:
    return {
        "start": start,
        "end": start + len(surface),
        "surface": surface,
        "lemma": lemma,
        "pos": pos,
        "entity": None,
        "syntax": {"prefixes": [], "lead": lead},
    }


def sentence(*words: tuple[str, str] | tuple[str, str, str] | tuple[str, str, str, int]) -> list:
    """Tokens one space apart."""
    out = []
    at = 0
    for word in words:
        surface, lemma = word[0], word[1]
        pos = word[2] if len(word) > 2 else "ADV"  # type: ignore[misc]
        lead = word[3] if len(word) > 3 else 0  # type: ignore[misc]
        out.append(token(surface, lemma, at, pos, lead))
        at += len(surface) + 1
    return out


def built(folder: Path, *segments: list[dict[str, Any]], language: str = "he") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    tokens = {f"s{n}": tokens for n, tokens in enumerate(segments)}
    (folder / "annotation.json").write_text(
        json.dumps({"language": language, "tokens": tokens}, ensure_ascii=False),
        encoding="utf-8",
    )
    return folder


AFTERWARDS = sentence(("הוא", "הוא", "PRON"), ("בא", "בא", "VERB"), ("אחר", "אחר"), ("כך", "כך"))


def test_the_list_ships_with_every_key_of_two_words_or_three() -> None:
    found = units.load()
    assert len(found) == 174
    assert all(2 <= len(unit.parts) <= 3 for unit in found)
    assert "אחר כך" in units.keys()


def test_a_sentence_with_achar_kach_counts_one_unit_not_two(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    counts = coverage.tally(folder)
    assert counts == {"הוא": 1, "בא": 1, "אחר": 1, "כך": 1}, "a word's own count is unchanged"
    assert units_in(folder) == {"אחר כך": 1}
    marked = dict.fromkeys(counts, KNOWN)
    measured = measure_running(counts, marked, units=units_in(folder))
    assert measured.total == 3, "three running words: הוא, בא, and אחר כך"
    assert measured.known == pytest.approx(2 / 3), "the expression is not marked"
    kept = units.with_phrases(marked, ["אַחַר כָּךְ"])
    assert measure_running(counts, kept, units=units_in(folder)).known == 1.0
    assert coverage.running_against(folder, kept) == measure_running(
        counts, kept, units=units_in(folder)
    )


def test_coverage_moves_as_the_unit_and_its_words_are_known(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    counts = coverage.tally(folder)
    joined = units_in(folder)
    nothing = measure_running(counts, {}, units=joined)
    assert nothing.known == 0.0 and nothing.total == 3
    words = measure_running(counts, {"הוא": KNOWN, "בא": KNOWN}, units=joined)
    assert words.known == pytest.approx(2 / 3)
    before = measure_running(counts, {"הוא": KNOWN, "בא": KNOWN})
    assert before.known == 0.5 and before.total == 4, "as it was, counted as words"


def test_the_estimate_gives_a_unit_the_product_of_its_words_chances(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    counts = coverage.tally(folder)

    class Guess:
        def chance(self, lemma: str) -> float:
            return {"אחר": 0.8, "כך": 0.5}.get(lemma, 1.0)

    marked = {"הוא": KNOWN, "בא": KNOWN}
    measured = measure_running(counts, marked, Guess(), units_in(folder))
    assert measured.expected == pytest.approx((2 + 0.8 * 0.5) / 3)
    one_known = measure_running(counts, {**marked, "כך": KNOWN}, Guess(), units_in(folder))
    assert one_known.expected == pytest.approx((2 + 0.8) / 3), "a mark on a word wins"
    learning = measure_running(counts, {**marked, "כך": 2}, Guess(), units_in(folder))
    assert learning.expected == pytest.approx(2 / 3)


def test_the_catalogue_index_counts_a_unit_as_one_word(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    counts = coverage.tally(folder)
    index = build_index({"t": list(counts)}, {"t": counts}, {"t": units_in(folder)})
    assert "אחר כך" in index.words and "אחר כך" not in index.lemmas_for("t")
    assert index.count_in("t", "אחר") == 1, "a word's own count is unchanged"
    marked = dict.fromkeys(counts, KNOWN)
    running = index.running("t", marked)
    assert running is not None and running.total == 3 and running.known == pytest.approx(2 / 3)
    kept = units.with_phrases(marked, ["אחר כך"])
    running = index.running("t", kept)
    assert running is not None and running.known == 1.0
    chances = [0.5] * len(index.words)
    statuses = index.statuses({"הוא": KNOWN, "בא": KNOWN})
    assert index.expected("t", statuses, chances) == pytest.approx((2 + 0.25) / 3)
    written = tmp_path / "lemmas.json"
    coverage.write_index(written, index)
    assert coverage.read_index(written).units == index.units


def test_a_key_that_needs_its_prefix_matches_only_with_it() -> None:
    with_it = sentence(("מכל", "כול", "DET", 1), ("מקום", "מקום", "NOUN"))
    without = sentence(("כל", "כול", "DET"), ("מקום", "מקום", "NOUN"))
    assert [unit.key for _, unit in units.match(with_it)] == ["כול מקום"]
    assert units.match(without) == []
    school = sentence(("ובית", "בית", "NOUN", 1), ("הספר", "ספר", "NOUN", 1))
    assert [unit.key for _, unit in units.match(school)] == ["בית ספר"], "a prefix is allowed"


def test_a_unit_is_never_matched_across_punctuation() -> None:
    apart = [token("אחר", "אחר", 0), token("כך", "כך", 5)]
    assert units.match(apart) == []
    joined = [token("אחר", "אחר", 0), token("כך", "כך", 4)]
    assert len(units.match(joined)) == 1


def test_a_word_not_counted_stays_out_of_the_unit(tmp_path: Path) -> None:
    """DICTA tags the אחד of אף אחד a numeral, which no count keeps."""
    folder = built(tmp_path / "t", sentence(("אף", "אף"), ("אחד", "אחד", "NUM"), ("בא", "בא")))
    counts = coverage.tally(folder)
    assert counts == {"אף": 1, "בא": 1}
    assert units_in(folder) == {"אף אחד|אף": 1}
    measured = measure_running(counts, {"אף": KNOWN, "בא": KNOWN}, units=units_in(folder))
    assert measured.total == 2 and measured.known == 0.5
    kept = units.with_phrases({"אף": KNOWN, "בא": KNOWN}, ["אַף אֶחָד"])
    assert measure_running(counts, kept, units=units_in(folder)).known == 1.0


def test_a_kept_phrase_is_matched_by_its_written_form_with_a_prefix() -> None:
    assert units.from_phrases(["ובכל זאת,"]) >= {"כול זה", "כל זאת"}
    assert units.from_phrases(["על פי"]) == {"על פה"}
    assert units.from_phrases(["בעל פה"]) == {"על פה"}, "one key, two meanings"
    assert units.from_phrases(["ספר טוב"]) == frozenset()


def test_another_language_has_no_units(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS, language="ru")
    assert units_in(folder) == {}


def test_a_count_cached_before_units_is_counted_again(tmp_path: Path) -> None:
    folder = built(tmp_path / "t", AFTERWARDS)
    stat = (folder / "annotation.json").stat()
    (folder / "lemmas.json").write_text(
        json.dumps(
            {
                "stamp": [stat.st_mtime_ns, stat.st_size],
                "lemmas": ["אחר", "בא", "הוא", "כך"],
                "counts": {"הוא": 1, "בא": 1, "אחר": 1, "כך": 1},
            }
        ),
        encoding="utf-8",
    )
    assert units_in(folder) == {"אחר כך": 1}


def test_a_text_with_no_units_is_measured_as_before() -> None:
    counts = {"בית": 3, "ספר": 1}
    plain = measure_running(counts, {"בית": KNOWN})
    assert measure_running(counts, {"בית": KNOWN}, units={}) == plain
    assert math.isclose(plain.known, 0.75)


# French and Russian (targum-internal#636): the same matcher, on lists of their own.

FR = (
    "lemmas\tsurface\tgloss_en\tregister\tnote\tneeds\n"
    "de abord\td'abord\tfirst\tmodern\t\t\n"
    "tout à coup\ttout à coup\tsuddenly\tmodern\t\t\n"
    "parce que\tparce que/parce qu'\tbecause\tmodern\t\t\n"
    "ce est-à-dire\tc'est-à-dire\tthat is\tmodern\t\t\n"
    "de coup\tdu coup\tso\tmodern\t\t\n"
    "ne que\tne… que\tonly\tstandard\tdiscontinuous\t|~6\n"
    "ne plus\tne… plus\tno longer\tstandard\tdiscontinuous\t|~6\n"
    "ni ni\tni… ni\tneither… nor\tstandard\tdiscontinuous\t|~6,\n"
    "le un le autre\tl'un l'autre\teach other\tstandard\t\t\n"
    "être que\test-ce que\t(question)\tstandard\t\t=est-ce|\n"
    "se rendre compte\tse rendre compte\tto realise\tstandard\t\t\n"
)
RU = (
    "lemmas\tsurface\tgloss_en\tregister\tnote\tneeds\n"
    "иметь в вид\tиметь в виду\tto mean\tmodern\t\t\n"
    "в конец конец\tв конце концов\tin the end\tmodern\t\t\n"
    "всё равно\tвсё равно\tall the same\tmodern\t\t\n"
    "не только но и\tне только… но и\tnot only… but also\tstandard\tdiscontinuous\t||~6,|\n"
    "у быть\tу меня есть\t(I) have\tstandard\tdiscontinuous\t|~6\n"
    "мочь быть\tможет быть\tmaybe\tstandard\t\t=может|\n"
)


@pytest.fixture
def lists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "lists"
    folder.mkdir()
    (folder / "units-fr.tsv").write_text(FR, encoding="utf-8")
    (folder / "units-ru.tsv").write_text(RU, encoding="utf-8")
    monkeypatch.setattr(units, "FOLDER", folder)
    units.clear()
    yield folder
    units.clear()


def keyed(tokens: list[dict[str, Any]], language: str) -> list[str]:
    return [unit.key for _, unit in units.match(tokens, language)]


def test_hebrew_reads_its_own_list_whatever_the_others_are(lists: Path) -> None:
    assert len(units.load()) == 174 and units.load() == units.load(language="he")
    assert keyed(AFTERWARDS, "he") == ["אחר כך"]
    assert units.stamps() == units.stamp() + (
        f"+fr:{units.stamp(lists / 'units-fr.tsv')}+ru:{units.stamp(lists / 'units-ru.tsv')}"
    )


def test_hebrew_stamp_is_as_it_was_without_other_lists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(units, "FOLDER", tmp_path)
    units.clear()
    try:
        assert units.stamps() == units.stamp()
    finally:
        units.clear()


def test_a_french_elided_word_is_matched_on_its_full_form(lists: Path) -> None:
    # l'annotateur keeps the apostrophe on the first part: d' then abord, no gap.
    first = [token("D'", "de", 0), token("abord", "abord", 2)]
    assert keyed(first, "fr") == ["de abord"]
    curly = [token("d’", "d’", 0), token("abord", "abord", 2)]
    assert keyed(curly, "fr") == ["de abord"], "a lemma left elided is folded too"
    because = [token("parce", "parce", 0), token("qu'", "que", 6), token("il", "il", 9)]
    assert keyed(because, "fr") == ["parce que"]
    so = sentence(("du", "de", "ADP"), ("coup", "coup", "NOUN"))
    assert keyed(so, "fr") == ["de coup"]


def test_a_french_hyphenated_unit_matches_as_one_token_or_its_pieces(lists: Path) -> None:
    whole = [token("c'", "ce", 0), token("est-à-dire", "est-à-dire", 2)]
    assert keyed(whole, "fr") == ["ce est-à-dire"]
    cut = [
        token("c'", "ce", 0),
        token("est", "être", 2, "AUX"),
        token("à", "à", 6, "ADP"),
        token("dire", "dire", 8, "VERB"),
    ]
    assert keyed(cut, "fr") == ["ce est-à-dire"], "the pieces, one hyphen apart"
    apart = [token("tout", "tout", 0), token("à", "à", 6), token("coup", "coup", 8)]
    assert keyed(apart, "fr") == [], "never across punctuation"


def test_a_russian_unit_is_matched_however_it_is_inflected(lists: Path) -> None:
    mean = sentence(("имею", "иметь", "VERB"), ("в", "в", "ADP"), ("виду", "вид", "NOUN"))
    assert keyed(mean, "ru") == ["иметь в вид"]
    meant = sentence(("Имели", "иметь", "VERB"), ("в", "в", "ADP"), ("виду", "вид", "NOUN"))
    assert keyed(meant, "ru") == ["иметь в вид"]
    end = sentence(("в", "в"), ("конце", "конец"), ("концов", "конец"))
    assert keyed(end, "ru") == ["в конец конец"]
    yo = sentence(("все", "все"), ("равно", "равно"))
    assert keyed(yo, "ru") == ["все равно"], "ё is read as е on both sides"
    view = sentence(("в", "в", "ADP"), ("виде", "вид", "NOUN"))
    assert keyed(view, "ru") == []


def test_a_french_text_counts_its_unit_as_one_word(lists: Path, tmp_path: Path) -> None:
    said = sentence(("Il", "il", "PRON"), ("part", "partir", "VERB"))
    said += [token("d'", "de", 8, "ADP"), token("abord", "abord", 10)]
    folder = built(tmp_path / "t", said, language="fr")
    counts = coverage.tally(folder)
    assert units_in(folder) == {"de abord": 1}
    kept = units.with_phrases(dict.fromkeys(counts, KNOWN), ["D’abord"], "fr")
    assert kept["de abord"] == KNOWN
    assert measure_running(counts, kept, units=units_in(folder)).total == 3


def test_a_kept_phrase_is_matched_in_its_own_language_only(lists: Path) -> None:
    assert units.from_phrases(["Parce qu'"], "fr") == {"parce que"}
    assert units.from_phrases(["c'est-à-dire"], "fr") == {"ce est-à-dire"}
    assert units.from_phrases(["В конце концов!"], "ru") == {"в конец конец"}
    assert units.from_phrases(["в конце концов"], "fr") == frozenset()
    assert units.from_phrases(["в конце концов"]) == frozenset(), "Hebrew is the default"


def test_a_language_without_a_list_has_no_units(lists: Path, tmp_path: Path) -> None:
    (lists / "units-ru.tsv").unlink()
    units.clear()
    folder = built(
        tmp_path / "t", sentence(("в", "в"), ("конце", "конец"), ("концов", "конец")), language="ru"
    )
    assert units_in(folder) == {}
    assert units.from_phrases(["в конце концов"], "ru") == frozenset()


def test_a_discontinuous_unit_takes_its_parts_and_leaves_the_words_between(
    lists: Path, tmp_path: Path
) -> None:
    only = sentence(("je", "je"), ("n'", "ne"), ("ai", "avoir"), ("que", "que"), ("dix", "dix"))
    hits = units.found(only, "fr")
    assert [(at, unit.key) for at, unit in hits] == [((1, 3), "ne que")]
    folder = built(tmp_path / "t", only, language="fr")
    assert units_in(folder) == {"ne que": 1}
    closest = sentence(("ne", "ne"), ("mange", "manger"), ("plus", "plus"), ("que", "que"))
    assert [unit.key for _, unit in units.found(closest, "fr")] == ["ne plus"]
    far = sentence(("ne", "ne"), *[("mot", "mot")] * 7, ("que", "que"))
    assert units.found(far, "fr") == [], "six words between at most"
    both = [
        token("не", "не", 0),
        token("только", "только", 3),
        token("дома", "дом", 10),
        token("но", "но", 16),
        token("и", "и", 19),
        token("здесь", "здесь", 21),
    ]
    assert [(at, unit.key) for at, unit in units.found(both, "ru")] == [
        ((0, 1, 3, 4), "не только но и")
    ], "a comma may stand inside the gap"


def test_a_french_reflexive_se_is_said_by_any_person(lists: Path) -> None:
    for pronoun in ("me", "te", "se", "nous", "vous"):
        said = sentence((pronoun, pronoun), ("rends", "rendre"), ("compte", "compte"))
        assert [unit.key for _, unit in units.match(said, "fr")] == ["se rendre compte"]
    elided = [token("m'", "me", 0), token("en", "en", 2)]
    assert units.match(elided, "fr") == []
    said = sentence(("nous", "nous"), ("nous", "nous"), ("rendons", "rendre"), ("compte", "compte"))
    assert [at for at, _ in units.match(said, "fr")] == [1]
    other = sentence(("le", "le"), ("rends", "rendre"), ("compte", "compte"))
    assert units.match(other, "fr") == []


def test_a_word_held_to_its_written_form_matches_only_in_it(lists: Path) -> None:
    question = sentence(("Est-ce", "être"), ("que", "que"))
    assert [unit.key for _, unit in units.match(question, "fr")] == ["être que"]
    assert units.match(sentence(("est", "être"), ("que", "que")), "fr") == []
    maybe = sentence(("может", "мочь"), ("быть", "быть"))
    assert [unit.key for _, unit in units.match(maybe, "ru")] == ["мочь быть"]
    assert units.match(sentence(("могут", "мочь"), ("быть", "быть")), "ru") == []


@pytest.mark.parametrize("language", ["fr", "ru"])
def test_the_shipped_list_reads_whole(language: str) -> None:
    units.clear()
    path = units.path_for(language)
    rows = path.read_text(encoding="utf-8").splitlines()
    assert rows[0].split("\t")[0] == "lemmas", "no line above the header"
    found = units.load(language=language)
    assert {unit.key for unit in found} >= {
        " ".join(units.words(r.split("\t")[0])) for r in rows[1:]
    }
    for line in rows[1:]:
        cells = line.split("\t")
        if "discontinuous" in cells[4]:
            key = " ".join(units.words(cells[0]))
            assert any(sum(unit.gaps) for unit in found if unit.key == key), key


def spaced(*words: tuple[str, str], comma_after: int = -1) -> list[dict[str, Any]]:
    """`sentence`, with a comma after the word at `comma_after`."""
    out = []
    at = 0
    for n, (surface, lemma) in enumerate(words):
        out.append(token(surface, lemma, at))
        at += len(surface) + (2 if n == comma_after else 1)
    return out


def test_a_gap_after_ne_stops_at_another_negation(lists: Path) -> None:
    """qa-claude on targum#1114: ne… pas que and ne… pas plus are not ne… que, ne… plus."""
    think = spaced(
        ("Je", "je"),
        ("ne", "ne"),
        ("crois", "croire"),
        ("pas", "pas"),
        ("que", "que"),
        ("tu", "tu"),
        ("viennes", "venir"),
    )
    assert units.found(think, "fr") == []
    more = spaced(
        ("Il", "il"),
        ("ne", "ne"),
        ("mange", "manger"),
        ("pas", "pas"),
        ("plus", "plus"),
        ("que", "que"),
        ("moi", "moi"),
    )
    assert units.found(more, "fr") == []
    only = spaced(("Il", "il"), ("ne", "ne"), ("mange", "manger"), ("que", "que"), ("ça", "ça"))
    assert [unit.key for _, unit in units.found(only, "fr")] == ["ne que"]


def test_a_gap_stops_at_punctuation_unless_the_unit_is_a_correlative(lists: Path) -> None:
    because = spaced(("Il", "il"), ("ne", "ne"), ("vient", "venir"), ("que", "que"), comma_after=2)
    assert units.found(because, "fr") == [], "il ne vient, que…"
    near = spaced(("у", "у"), ("дома", "дом"), ("где", "где"), ("было", "быть"), comma_after=1)
    assert units.found(near, "ru") == [], "у дома, где было: not у… есть"
    has = spaced(("у", "у"), ("меня", "я"), ("было", "быть"))
    assert [unit.key for _, unit in units.found(has, "ru")] == ["у быть"]
    neither = spaced(("ni", "ni"), ("lui", "lui"), ("ni", "ni"), ("moi", "moi"), comma_after=1)
    assert [unit.key for _, unit in units.found(neither, "fr")] == ["ni ni"]


def test_a_discontinuous_unit_counts_the_words_it_is_made_of(lists: Path, tmp_path: Path) -> None:
    """A numeral between ne and que is not counted, and the que after it is."""
    said = sentence(("ne", "ne"), ("2", "2", "NUM"), ("que", "que"))
    folder = built(tmp_path / "t", said, language="fr")
    assert units_in(folder) == {"ne que": 1}
    said = sentence(("ne", "ne"), ("vu", "voir"), ("2", "2", "NUM"))
    said[1]["lemma"], said[2]["lemma"], said[2]["surface"] = "voir", "que", "que"
    folder = built(tmp_path / "u", said, language="fr")
    assert units_in(folder) == {"ne que|ne": 1}, "the que tagged a numeral stays out"


def test_a_token_in_one_unit_is_never_in_another(lists: Path) -> None:
    said = sentence(("ne", "ne"), ("vient", "venir"), ("parce", "parce"), ("que", "que"))
    assert [(at, unit.key) for at, unit in units.found(said, "fr")] == [((0, 3), "ne que")]


def test_an_elided_lemma_is_folded_to_its_full_form(lists: Path) -> None:
    said = [
        token("l'", "l'", 0),
        token("un", "un", 2),
        token("l'", "l'", 5),
        token("autre", "autre", 7),
    ]
    assert [unit.key for _, unit in units.match(said, "fr")] == ["le un le autre"]
