"""Aramaic's free groundwork (ling-arc's plan, 2026-10-25): a frequency list counted from
the shelf's own Aramaic, the difficulty and ladder that stand on it (G1), and the
Talmud's abbreviations (G8) and argument terms (G9) as hand tables."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from targum import levelmap, touchstones
from targum.annotate import aramaic, aramaic_frequency, closed
from targum.annotate.difficulty import band_of, hard_share
from targum.models import Annotation, Segment

#: Onkelos, Genesis 1:1–3 and Exodus 15:1, public domain, as Sefaria prints them.
ONKELOS = (
    "בְּקַדְמִין בְּרָא יְיָ יָת שְׁמַיָּא וְיָת אַרְעָא",
    "וְאַרְעָא הֲוָת צַדְיָא וְרֵקַנְיָא וַחֲשׁוֹכָא עַל אַפֵּי תְהוֹמָא",
    "וַאֲמַר יְיָ יְהֵי נְהוֹרָא וַהֲוָה נְהוֹרָא",
)
#: Targum Job 3:8, from the hardest family the count measured.
JOB = "יְלַטְטוּן לֵילְיָא לִיטֵי יוֹמָא דַעֲתִידִין לְאַרְמָא אִלְיְתָן"


def _annotation(lines: tuple[str, ...]) -> Annotation:
    tokens = {
        f"s{i}": aramaic.tokens(
            Segment(id=f"s{i}", block_id="b", block_index=0, index=i, text=line)
        )
        for i, line in enumerate(lines)
    }
    return Annotation(
        document_hash="test",
        language="arc",
        annotator=aramaic.NAME,
        method="frequency",
        method_note="",
        tokens=tokens,
    )


def test_the_list_is_counted_from_the_shelf() -> None:
    assert aramaic_frequency.available(), "aramaic_frequency.json ships beside its module"
    # The object marker and the divine name are the commonest words of any Targum.
    assert aramaic_frequency.rank("ית") == 1
    assert aramaic_frequency.band("יי") == 1
    assert aramaic_frequency.band("ארעא") <= 2
    assert aramaic_frequency.band("אבגדהוזחט") >= 4, "a word never met is looked up"


def test_aramaic_is_measured_where_it_measured_zero() -> None:
    """wordfreq has no Aramaic, so every Aramaic text measured 0 (design.md, 2026-10-08)."""
    assert band_of("ית", "arc") == 1
    onkelos = hard_share(_annotation(ONKELOS), "arc")
    job = hard_share(_annotation((JOB,)), "arc")
    assert 0 < onkelos < job


def test_the_level_map_places_onkelos() -> None:
    """Onkelos's books measured 9 to 13 with sentences of 13 to 16 words (2026-10-25):
    placed, where a 0 left them unmeasured."""
    onkelos = hard_share(_annotation(ONKELOS), "arc")
    assert levelmap.place(onkelos, 14.0) is not None
    assert levelmap.place(12, 14.0) is not None


@dataclass(frozen=True)
class _Entry:
    id: str
    source: str
    difficulty: int
    language: str = "arc"


#: The 2026-10-25 measure of a few books from each family.
MEASURED = (
    _Entry("onkelos-genesis", "sefaria:arc:Genesis", 12),
    _Entry("onkelos-numbers", "sefaria:arc:Numbers", 9),
    _Entry("onkelos-deuteronomy", "sefaria:arc:Deuteronomy", 13),
    _Entry("tj-joshua", "sefaria:arc:Targum Jonathan on Joshua", 13),
    _Entry("tj-i-kings", "sefaria:arc:Targum Jonathan on I Kings", 12),
    _Entry("tj-judges", "sefaria:arc:Targum Jonathan on Judges", 14),
    _Entry("tj-genesis", "sefaria:arc:Targum Jonathan on Genesis", 18),
    _Entry("tj-isaiah", "sefaria:arc:Targum Jonathan on Isaiah", 22),
    _Entry("tj-hosea", "sefaria:arc:Targum Jonathan on Hosea", 19),
    _Entry("t-job", "sefaria:arc:Aramaic Targum to Job", 29),
    _Entry("t-proverbs", "sefaria:arc:Aramaic Targum to Proverbs", 37),
    _Entry("t-ruth", "sefaria:arc:Aramaic Targum to Ruth", 20),
    _Entry("unmeasured", "sefaria:arc:Targum Jonathan on Obadiah", 0),
    _Entry("hebrew", "sefaria:Genesis", 5, language="he"),
)


def test_the_ladder_places_onkelos_first() -> None:
    rungs = touchstones.aramaic_ladder(MEASURED)
    assert [rung.kind for rung in rungs] == [
        "onkelos",
        "former-prophets",
        "jonathan-torah",
        "latter-prophets",
        "writings",
    ]
    assert set(rungs[0].texts) == {"onkelos-genesis", "onkelos-numbers", "onkelos-deuteronomy"}
    assert "hebrew" not in {text for rung in rungs for text in rung.texts}


def test_every_aramaic_source_has_a_family() -> None:
    for book in ("Genesis", "Deuteronomy"):
        assert touchstones.aramaic_family(f"sefaria:arc:{book}") == "onkelos"
    assert touchstones.aramaic_family("sefaria:arc:Targum Jonathan on II Samuel") == (
        "former-prophets"
    )
    assert touchstones.aramaic_family("sefaria:arc:Targum Jonathan on Malachi") == (
        "latter-prophets"
    )
    assert touchstones.aramaic_family("sefaria:arc:Targum of I Chronicles") == "writings"
    assert touchstones.aramaic_family("sefaria:Genesis") is None


def test_the_page_climbs_the_aramaic_ladder() -> None:
    """design.md §12, "Aramaic gets a ladder, from our own counts" (2026-10-25), reverses
    "Aramaic gets no ladder" (2026-10-08): `ladder` hands Aramaic its Targum rungs."""
    assert "arc" not in touchstones.NO_LADDER
    assert touchstones.ladder(MEASURED, "arc") == touchstones.aramaic_ladder(MEASURED)
    assert touchstones.ladder(MEASURED, "arc")[0].kind == "onkelos"


def test_every_aramaic_rung_has_its_words_on_the_page() -> None:
    """Each rung's name on the ladder and its three sentences, in English and in Russian
    (design.md §12, "Your level leads with what you can read", 2026-10-28)."""
    import json
    from pathlib import Path

    import targum

    page = (Path(targum.__file__).parent / "render" / "assets" / "progress.js").read_text()
    strings = Path(targum.__file__).parent / "strings"
    english = json.loads((strings / "en.json").read_text(encoding="utf-8"))
    russian = json.loads((strings / "ru.json").read_text(encoding="utf-8"))
    for family, _ in touchstones.ARAMAIC_FAMILIES:
        assert f'"{family}": {{' in page, family
        for key in ("rung", "level.can", "level.next", "level.start"):
            name = f"progress.{key}.{family}"
            assert english.get(name) and russian.get(name), name


@pytest.mark.parametrize("form", sorted(closed.TALMUD_ABBREVIATIONS))
def test_every_abbreviation_expands(form: str) -> None:
    entry = closed.TALMUD_ABBREVIATIONS[form]
    assert closed.abbreviation(form) is entry
    # Written with ASCII quotes, with a full stop after it, and with ו or ד before it.
    ascii_form = form.replace("״", '"').replace("׳", "'")
    assert closed.abbreviation(ascii_form) is entry
    assert closed.abbreviation(form + ".") is entry
    for prefix in "וד":
        if prefix + form not in closed.TALMUD_ABBREVIATIONS:
            assert closed.abbreviation(prefix + form) is entry
    assert entry.readings
    for full, sense in entry.readings:
        assert full and "״" not in full, f"{form}: the full form is written out"
        assert sense and sense == sense.strip()
    assert entry.page == 0 or 287 <= entry.page <= 293, "Mielziner's key is pp. 287–293"


def test_an_ambiguous_abbreviation_is_marked_for_checking() -> None:
    for form, entry in closed.TALMUD_ABBREVIATIONS.items():
        if len(entry.readings) > 1 or not entry.page:
            assert entry.to_check, form
    assert closed.abbreviation("שלום") is None
    assert closed.abbreviation("") is None


def test_the_table_holds_berakhots_commonest() -> None:
    """ling-arc's Berakhot count, top of the list (2026-10-25)."""
    for form in ("ר׳", "ה׳", "א״ר", "א״ל", "וגו׳", "ת״ר", "ק״ש", "הקב״ה", "שנא׳", "אפי׳"):
        assert closed.abbreviation(form) is not None, form
    for form in ("מ״ט", "קמ״ל", "ת״ש", "אע״ג", "ת״ח"):
        assert closed.abbreviation(form) is not None, form


def test_every_argument_term_is_found_and_has_a_move() -> None:
    assert 55 <= len(closed.TALMUD_TERMS) <= 80
    for term, entry in closed.TALMUD_TERMS.items():
        assert entry.move in closed.MOVES, term
        assert entry.gloss
        found = closed.argument_term(term.split())
        assert found is not None and found[0] == term and found[2] == len(term.split())


def test_a_phrase_wins_over_its_first_word_and_a_short_form_answers() -> None:
    assert closed.argument_term(["מאי", "טעמא", "דרבי"])[0] == "מאי טעמא"  # type: ignore[index]
    assert closed.argument_term(["מאי", "דרבי"])[0] == "מאי"  # type: ignore[index]
    found = closed.argument_term(["ת״ש", "מהא"])
    assert found is not None and found[0] == "תא שמע" and found[2] == 1
    assert closed.argument_term(["קמ״ל"])[1].move == "answer"  # type: ignore[index]
    assert closed.argument_term(["אברהם"]) is None
    assert closed.argument_term([]) is None
