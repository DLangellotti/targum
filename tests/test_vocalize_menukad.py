"""The ktiv menukad normaliser (targum-internal#563).

Every fixture is a dictionary word or a few words made up here, never a scene's line:
the scenes are proprietary and this repository is public. What the normaliser did to
the two scene sets is measured outside it and reported on the card.
"""

from __future__ import annotations

import json
from pathlib import Path
from unicodedata import normalize

import pytest

from targum.vocalize import menukad


def norm(word: str, names: frozenset[str] = frozenset()) -> str:
    return normalize("NFC", menukad.normalise_word(word, names)[0])


def nfc(text: str) -> str:
    return normalize("NFC", text)


@pytest.mark.parametrize(
    ("full", "standard"),
    [
        ("חִיבּוּר", "חִבּוּר"),  # hiriq + bare yod before dagesh
        ("לִשְׁמוֹעַ", "לִשְׁמֹעַ"),  # qal infinitive
        ("תִּסְגּוֹר", "תִּסְגֹּר"),  # qal future
        ("שְׁנָתַיִים", "שְׁנָתַיִם"),  # -ayim
        ("בִּנְיָין", "בִּנְיָן"),  # doubled consonantal yod
        ("כּוּלָּם", "כֻּלָּם"),  # shuruk before dagesh
        ("בּוֹקֶר", "בֹּקֶר"),  # segolate
        ("הַבּוֹקֶר", "הַבֹּקֶר"),  # segolate behind the article
        ("צֶוֶות", "צֶוֶת"),  # doubled consonantal vav
        ("יֹופִי", "יֹפִי"),  # the menaked's holam with its vav kept bare
        ("מְעֻולֶּה", "מְעֻלֶּה"),  # and its qubuts
        ("שׁוּלְחָן", "שֻׁלְחָן"),  # lexicon: shuruk for qubuts
        ("הַטֵּלֵפוֹן", "הַטֶּלֶפוֹן"),  # lexicon, through the article's dagesh
        ("תּוֹכְנִית", "תׇּכְנִית"),  # lexicon: qamats qatan
        ("לְנִיהוּל", "לְנִהוּל"),  # hiriq + yod before a guttural
        ("הַכּוֹל", "הַכֹּל"),
        ("אֵלַיי", "אֵלַי"),
        ("פּוֹתֵח", "פּוֹתֵחַ"),  # furtive patah
    ],
)
def test_full_spelling_comes_out_standard(full: str, standard: str) -> None:
    assert norm(full) == nfc(standard)


@pytest.mark.parametrize(
    "word",
    [
        "הָיִיתִי",
        "כְּשֶׁהָיִינוּ",
        "חַיִּים",
        "קְצָווֹת",
        "מֵייל",
        "הַיְיטֵק",
        "וַואטְסְאַפּ",
        "סוּפֶּר",
        "קוּרְס",
        "אוֹגוּסְט",
        "בְּטִיחוּת",
        "שְׁלִיחוּת",
        "שָׁלוֹם",
        "הוּא",
        "לִרְחוֹב",
        "אֶתְמוֹל",
        "לִגְזֹם",
        "שָׁמַע",
    ],
)
def test_the_exceptions_are_left_alone(word: str) -> None:
    assert menukad.normalise_word(word) == (word, ())


def test_a_cast_name_is_left_alone() -> None:
    assert menukad.normalise_word("עִידּוֹ", frozenset({"עידו"})) == ("עִידּוֹ", ())
    assert norm("עִידּוֹ") == nfc("עִדּוֹ")


def test_a_short_loanword_is_matched_as_a_word_not_a_stretch() -> None:
    # לגזום holds the letters of זום (Zoom) and is a verb.
    assert norm("לִגְזוֹם") == nfc("לִגְזֹם")
    assert menukad.normalise_word("בַּזּוּם")[1] == ()


def test_normalise_reports_each_change_and_leaves_the_rest_byte_for_byte() -> None:
    line = "שָׁלוֹם, יֹופִי שֶׁל חִיבּוּר."
    out, changes = menukad.normalise(line)
    assert [c.word for c in changes] == ["יֹופִי", "חִיבּוּר"]
    assert out.startswith("שָׁלוֹם, ") and out.endswith(".")
    assert len(out.split()) == len(line.split())


def test_it_is_idempotent() -> None:
    line = "בּוֹקֶר טוֹב, אֲנִי רוֹצֶה לִשְׁמוֹעַ עַל הַתּוֹכְנִית שֶׁל הַצֶּוֶות"
    once, first = menukad.normalise(line)
    twice, second = menukad.normalise(once)
    assert first and not second and once == twice


def test_residue_names_what_is_still_full_spelling() -> None:
    assert menukad.residue("חִיבּוּר") == [("hiriq + bare yod before dagesh", "חִיבּוּר")]
    assert menukad.residue(menukad.normalise("חִיבּוּר יֹופִי")[0]) == []
    assert menukad.residue("הָיִיתִי מֵייל") == []


def test_the_command_prints_and_writes_only_where_asked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scene = {
        "id": "x",
        "cast": {"A": {"name": "דנה"}, "B": {"name": "עידו"}},
        "turns": [{"who": "A", "text": "יֹופִי, עִידּוֹ"}, {"who": "B", "text": "שָׁלוֹם"}],
    }
    path = tmp_path / "x.json"
    path.write_text(json.dumps(scene, ensure_ascii=False), encoding="utf-8")
    assert menukad.main([str(path)]) == 0
    printed = capsys.readouterr().out
    assert "t0" in printed and "holam + bare vav" in printed and "1 rule applications" in printed
    assert json.loads(path.read_text(encoding="utf-8")) == scene  # read only
    out = tmp_path / "out"
    assert menukad.main(["--out", str(out), str(path)]) == 0
    written = json.loads((out / "x.json").read_text(encoding="utf-8"))
    assert nfc(written["turns"][0]["text"]) == nfc("יֹפִי, עִידּוֹ")
