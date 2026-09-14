"""OpenRussian's tables, looked up for a Russian card (targum-internal#259).

Offline: a few rows written in the tables' own shape. What is under test is what the card
may say — a partner, a stress line — and that it says nothing where the dictionary is
unsure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.annotate import openrussian
from targum.errors import TargumError

NOUNS = [
    "bare accented translations_en translations_de gender partner animate indeclinable sg_only "
    "pl_only sg_nom sg_gen sg_dat sg_acc sg_inst sg_prep pl_nom pl_gen pl_dat pl_acc pl_inst "
    "pl_prep",
    "рука рука' hand Hand f  0 0 0 0 рука' руки' руке' ру'ку руко'й,~руко'ю руке' ру'ки ру'к "
    "рука'м ру'ки рука'ми рука'х",
    "замок за'мок castle Schloss m  0 0 0 0 за'мок за'мка за'мку за'мок за'мком за'мке за'мки "
    "за'мков за'мкам за'мки за'мками за'мках",
    "замок замо'к lock Schloss m  0 0 0 0 замо'к замка' замку' замо'к замко'м замке' замки' "
    "замко'в замка'м замки' замка'ми замка'х",
    "книга кни'га book Buch f  0 0 0 0 кни'га кни'ги кни'ге кни'гу кни'гой кни'ге кни'ги кни'г "
    "кни'гам кни'ги кни'гами кни'гах",
]
VERBS = [
    "bare accented translations_en translations_de aspect partner imperative_sg imperative_pl "
    "past_m past_f past_n past_pl presfut_sg1 presfut_sg2 presfut_sg3 presfut_pl1 presfut_pl2 "
    "presfut_pl3",
    "сказать сказа'ть say sagen perfective говорить скажи' скажи'те сказа'л сказа'ла сказа'ло "
    "сказа'ли скажу' ска'жешь ска'жет ска'жем ска'жете ска'жут",
    "говорить говори'ть speak sprechen imperfective сказать;поговорить говори' говори'те "
    "говори'л говори'ла говори'ло говори'ли говорю' говори'шь говори'т говори'м говори'те "
    "говоря'т",
    "писать писа'ть write schreiben imperfective написать пиши' пиши'те писа'л писа'ла писа'ло "
    "писа'ли пишу' пи'шешь пи'шет пи'шем пи'шете пи'шут",
    "писать пи'сать pee pinkeln imperfective пописать пи'сай пи'сайте пи'сал пи'сала пи'сало "
    "пи'сали пи'саю пи'саешь пи'сает пи'саем пи'саете пи'сают",
]


def table(rows: list[str]) -> str:
    # Written with spaces for reading; the tables are tab-separated, and a cell's own
    # space is written `~`.
    return "\n".join("\t".join(cell.replace("~", " ") for cell in row.split(" ")) for row in rows)


@pytest.fixture
def lexicon(tmp_path: Path) -> openrussian.Lexicon:
    header = {"adjectives": "bare accented translations_en", "others": "bare accented"}
    (tmp_path / "nouns.csv").write_text(table(NOUNS) + "\n", encoding="utf-8")
    (tmp_path / "verbs.csv").write_text(table(VERBS) + "\n", encoding="utf-8")
    for name, head in header.items():
        (tmp_path / f"{name}.csv").write_text(head.replace(" ", "\t") + "\n", encoding="utf-8")
    openrussian.load.cache_clear()
    try:
        yield openrussian.load(tmp_path)
    finally:
        openrussian.load.cache_clear()


def test_a_verb_names_its_partner_stressed(lexicon: openrussian.Lexicon) -> None:
    assert lexicon.partners("сказать") == ["говори́ть"]
    assert lexicon.partners("говорить") == ["сказа́ть", "поговорить"], "unknown stays bare"
    assert lexicon.aspect("сказать") == "perfective"


def test_a_spelling_that_is_two_words_gets_no_partner_and_no_line(
    lexicon: openrussian.Lexicon,
) -> None:
    """писать is two verbs in the tables and замок two nouns: the card says nothing about
    either, because a learner believes what a card says."""
    assert lexicon.partners("писать") == []
    assert lexicon.stress_line("писать") == []
    assert lexicon.stress_line("замок") == []
    assert lexicon.headword("замок") == ""


def test_a_stress_line_shows_where_the_stress_moves(lexicon: openrussian.Lexicon) -> None:
    assert lexicon.stress_line("рука") == ["рука́", "ру́ку"]
    assert lexicon.stress_line("сказать") == ["сказа́ть", "ска́жешь"]
    assert lexicon.stress_line("книга") == [], "stress that never moves says nothing"
    assert lexicon.stress_line("говорить") == []


def test_a_tagged_form_is_looked_up_by_its_case_and_number(lexicon: openrussian.Lexicon) -> None:
    assert lexicon.form("рука", "UPOS=NOUN|Case=Acc|Number=Sing") == ["ру́ку"]
    assert lexicon.form("рука", "Case=Ins|Number=Sing") == ["руко́й", "руко́ю"]
    assert lexicon.form("рука", "Case=Acc") == []
    assert lexicon.spellings[openrussian.fold("руки")] == {"руки'", "ру'ки"}


def test_nothing_is_read_where_nothing_was_fetched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    assert openrussian.available() is False and openrussian.lexicon() is None
    with pytest.raises(TargumError, match="not downloaded"):
        openrussian.load(tmp_path / "nowhere")


def test_no_row_of_the_tables_is_in_the_repository() -> None:
    """Looked up, never shipped: the tables live in the model directory and nowhere in the
    tree the wheel is built from."""
    root = Path(__file__).resolve().parents[1]
    for path in [*root.glob("src/**/*.csv"), *root.glob("src/**/*.tsv")]:
        head = path.read_text(encoding="utf-8", errors="ignore")[:200]
        assert not head.startswith("bare\taccented"), path
