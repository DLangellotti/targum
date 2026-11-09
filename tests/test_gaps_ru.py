"""Russian grammar on Your Progress (design.md §12, "Russian grammar on Your Progress",
2026-11-09; targum-internal#639): each view's arithmetic on synthetic Russian tokens, in
the shape the free Russian annotator stores them. The page is
`test_progress_russian_browser.py`; the story's answer is `test_touchstones.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum import gaps_ru, occurrences
from targum.coverage import IGNORED, KNOWN
from targum.gaps_ru import aspect_pairs, classify, motion, participle_of, progress, soft_nouns

#: A word still being learned: a step of the learning ladder (1-3).
LEARNING = 2


def tok(surface: str, lemma: str, pos: str, **feats: str) -> dict[str, Any]:
    said = "|".join([f"UPOS={pos}", *(f"{k}={v}" for k, v in feats.items())])
    return {"surface": surface, "lemma": lemma, "pos": pos, "feats": said}


def squares(run: list[dict[str, Any]]) -> list[list[str]]:
    return [[square for square, _form in cells] for cells in classify(run)]


def forms_of(*runs: list[dict[str, Any]], times: int = 1) -> dict[str, dict[tuple[str, str], int]]:
    """What `occurrences.grammar_forms` hands the page, from a few segments."""
    out: dict[str, dict[tuple[str, str], int]] = {}
    for run in runs:
        for token, cells in zip(run, classify(run), strict=True):
            for square, form in cells:
                held = out.setdefault(square, {})
                key = (str(token["lemma"]), form)
                held[key] = held.get(key, 0) + times
    return out


# -- aspect × tense ---------------------------------------------------------------------


def test_a_verb_lands_in_its_aspect_and_tense() -> None:
    run = [
        tok("сказал", "сказать", "VERB", Aspect="Perf", Tense="Past", VerbForm="Fin"),
        tok("говорит", "говорить", "VERB", Aspect="Imp", Tense="Pres", VerbForm="Fin"),
        tok("скажи", "сказать", "VERB", Aspect="Perf", VerbForm="Fin", Mood="Imp"),
        tok("делать", "делать", "VERB", Aspect="Imp", VerbForm="Inf"),
        tok("скажет", "сказать", "VERB", Aspect="Perf", Tense="Fut", VerbForm="Fin"),
    ]
    assert squares(run) == [
        ["aspect:perfective:past"],
        ["aspect:imperfective:present"],
        ["aspect:perfective:imperative"],
        ["aspect:imperfective:infinitive"],
        ["aspect:perfective:future"],
    ]


def test_a_perfective_tagged_present_is_its_future_never_no_such_form() -> None:
    # ling-ru, 2026-11-06: 154 perfective finite verbs are stored Tense=Pres.
    run = [tok("прочитаю", "прочитать", "VERB", Aspect="Perf", Tense="Pres", VerbForm="Fin")]
    assert squares(run) == [["aspect:perfective:future"]]


def test_the_future_is_read_off_bud_and_a_compound_future_counts_once() -> None:
    # будет is stored Tense=Pres; standing alone it is быть's future.
    alone = [tok("будет", "быть", "AUX", Aspect="Imp", Tense="Pres", VerbForm="Fin")]
    assert squares(alone) == [["aspect:imperfective:future"]]
    # буду читать: the infinitive is читать's future, listed as the phrase, and буду is
    # its auxiliary, not a second future.
    run = [
        tok("Буду", "быть", "AUX", Aspect="Imp", Tense="Pres", VerbForm="Fin"),
        tok("читать", "читать", "VERB", Aspect="Imp", VerbForm="Inf"),
    ]
    assert classify(run) == [[], [("aspect:imperfective:future", "буду читать")]]
    # One word between still governs; a perfective infinitive is not a compound future.
    between = [
        tok("будем", "быть", "AUX", Aspect="Imp", Tense="Pres", VerbForm="Fin"),
        tok("долго", "долго", "ADV"),
        tok("ждать", "ждать", "VERB", Aspect="Imp", VerbForm="Inf"),
    ]
    assert squares(between) == [[], [], ["aspect:imperfective:future"]]
    # был is the past, whatever follows.
    past = [tok("был", "быть", "AUX", Aspect="Imp", Tense="Past", VerbForm="Fin")]
    assert squares(past) == [["aspect:imperfective:past"]]


def test_a_verb_with_no_aspect_and_participles_are_not_in_the_aspect_grid() -> None:
    run = [
        tok("женится", "жениться", "VERB", Tense="Pres", VerbForm="Fin"),
        tok("читающий", "читать", "VERB", Aspect="Imp", Case="Nom", VerbForm="Part"),
        tok("сказав", "сказать", "VERB", Aspect="Perf", VerbForm="Conv"),
    ]
    assert squares(run) == [[], ["forms:partact:imperfective"], ["forms:gerund:perfective"]]


def test_the_aspect_grid_and_its_gap() -> None:
    known = [tok("говорил", "говорить", "VERB", Aspect="Imp", Tense="Past", VerbForm="Fin")]
    weak = [
        tok("спросил", "спросить", "VERB", Aspect="Perf", Tense="Past", VerbForm="Fin"),
        tok("сказал", "сказать", "VERB", Aspect="Perf", Tense="Past", VerbForm="Fin"),
    ]
    forms = forms_of(known, weak, times=30)
    marked = {"говорить": KNOWN, "сказать": KNOWN, "спросить": LEARNING}
    said = progress(forms, marked, lambda lemma: "ask" if lemma == "спросить" else "")
    assert said is not None
    rows = {row["row"]: row for row in said["aspect"]["rows"]}
    assert rows["imperfective"]["cells"]["past"]["known"] == 100
    assert rows["perfective"]["cells"]["past"]["known"] == 50
    assert rows["perfective"]["cells"]["present"] is None, "the page hatches it"
    assert rows["perfective"]["cells"]["future"] is None
    gap = said["aspect"]["gap"]
    assert (gap["row"], gap["known"], gap["others"]) == ("perfective", 50, 100)
    assert gap["examples"][0] == {"lemma": "сказать", "form": "сказал", "meaning": ""}
    assert {"lemma": "спросить", "form": "спросил", "meaning": "ask"} in gap["examples"]
    words = rows["perfective"]["cells"]["past"]["words"]
    assert words[0]["form"] in ("сказал", "спросил") and words[0]["count"] == 30
    assert said["lead"] == "aspect"
    # Under the floor nothing is drawn at all.
    assert progress(forms_of(known, weak, times=5), marked) is None


def test_one_aspect_row_draws_the_grid_and_names_no_gap() -> None:
    run = [tok("говорил", "говорить", "VERB", Aspect="Imp", Tense="Past", VerbForm="Fin")]
    said = progress(forms_of(run, times=40), {})
    assert said is not None and said["aspect"]["gap"] is None and said["lead"] is None
    assert said["cases"] is None and said["place"] is None


# -- aspect pairs -----------------------------------------------------------------------


def test_aspect_pairs_both_halves_met_one_known_first() -> None:
    def verb(surface: str, lemma: str, aspect: str) -> dict[str, Any]:
        return tok(surface, lemma, "VERB", Aspect=aspect, Tense="Past", VerbForm="Fin")

    forms = forms_of(
        [
            verb("говорил", "говорить", "Imp"),
            verb("сказал", "сказать", "Perf"),
            verb("делал", "делать", "Imp"),
            verb("сделал", "сделать", "Perf"),
            verb("спрашивал", "спрашивать", "Imp"),
            verb("спросил", "спросить", "Perf"),
            # Only one half of this pair met: not shown.
            verb("понимал", "понимать", "Imp"),
        ],
        times=3,
    )
    marked = {"говорить": KNOWN, "сказать": KNOWN, "спросить": KNOWN}
    said = aspect_pairs(forms, marked)
    assert said is not None
    rows = [(row["imperfective"], row["perfective"], row["known"]) for row in said["rows"]]
    assert rows == [
        ("спрашивать", "спросить", "perfective"),
        ("делать", "сделать", "neither"),
        ("говорить", "сказать", "both"),
    ]
    assert said["met"] == 3 and said["both"] == 1
    assert aspect_pairs({}, {}) is None


# -- case × number, animate, where and where to ----------------------------------------


def test_case_and_number_with_the_animate_accusative_counting_nouns_only() -> None:
    run = [
        tok("руку", "рука", "NOUN", Case="Acc", Number="Sing", Animacy="Inan"),
        tok("брата", "брат", "NOUN", Case="Acc", Number="Sing", Animacy="Anim"),
        # An adjective agreeing with an animate noun: no head is stored, so neither row.
        tok("старого", "старый", "ADJ", Case="Acc", Number="Sing", Animacy="Anim"),
        tok("новую", "новый", "ADJ", Case="Acc", Number="Sing"),
        tok("рукой", "рука", "NOUN", Case="Ins", Number="Sing"),
        tok("чаю", "чай", "NOUN", Case="Par", Number="Sing"),
        tok("Ваня", "ваня", "NOUN", Case="Voc", Number="Sing"),
        tok("его", "он", "PRON", Case="Acc", Number="Sing"),
    ]
    assert squares(run) == [
        ["cases:acc:sing"],
        ["cases:acca:sing"],
        [],
        ["cases:acc:sing"],
        ["cases:ins:sing"],
        ["cases:gen:sing"],
        [],
        [],
    ]


def test_the_case_gap_is_measured_against_the_other_cases_pooled() -> None:
    nom = [tok("дом", "дом", "NOUN", Case="Nom", Number="Sing", Animacy="Inan")]
    ins = [tok("рукой", "рука", "NOUN", Case="Ins", Number="Sing", Animacy="Inan")]
    said = progress(forms_of(nom, ins, times=30), {"дом": KNOWN})
    assert said is not None and said["aspect"] is None
    assert said["cases"]["gap"]["row"] == "ins"
    assert said["lead"] == "cases"
    assert said["pairs"] is None, "a companion comes with its tab's grid only"


def test_where_and_where_to_by_the_case_after_the_preposition() -> None:
    run = [
        tok("в", "в", "ADP"),
        tok("доме", "дом", "NOUN", Case="Loc", Number="Sing"),
        tok("на", "на", "ADP"),
        tok("большую", "большой", "ADJ", Case="Acc", Number="Sing"),
        tok("улицу", "улица", "NOUN", Case="Acc", Number="Sing"),
        tok("под", "под", "ADP"),
        tok("столом", "стол", "NOUN", Case="Ins", Number="Sing"),
        # в with the instrumental is not a case в says "where" with: left out.
        tok("в", "в", "ADP"),
        tok("течением", "течение", "NOUN", Case="Ins", Number="Sing"),
    ]
    cells = classify(run)
    assert ("place:v:where", "в доме") in cells[1]
    assert ("place:na:whereto", "на большую") in cells[3], "the first cased word, as ruled"
    assert not any(square.startswith("place") for square, _ in cells[4])
    assert ("place:pod:where", "под столом") in cells[6]
    assert not any(square.startswith("place") for square, _ in cells[8])


def test_where_and_where_to_is_never_the_gap() -> None:
    nom = [tok("дом", "дом", "NOUN", Case="Nom", Number="Sing")]
    place = [
        tok("в", "в", "ADP"),
        tok("доме", "дом", "NOUN", Case="Loc", Number="Sing"),
        tok("за", "за", "ADP"),
        tok("столом", "стол", "NOUN", Case="Ins", Number="Sing"),
    ]
    said = progress(forms_of(nom, place, times=40), {"дом": KNOWN})
    assert said is not None and said["place"] is not None
    assert said["place"]["gap"] is None
    rows = {row["row"]: row for row in said["place"]["rows"]}
    assert rows["v"]["cells"]["where"]["known"] == 100
    assert rows["za"]["cells"]["where"]["known"] == 0
    assert rows["v"]["cells"]["where"]["words"][0]["form"] == "в доме"


# -- More: motion, -ь nouns, participles ------------------------------------------------


def test_verbs_of_motion_pool_one_way_and_there_and_back_and_list_each_pair() -> None:
    run = [
        tok("шёл", "идти", "VERB", Aspect="Imp", Tense="Past", VerbForm="Fin"),
        tok("ходил", "ходить", "VERB", Aspect="Imp", Tense="Past", VerbForm="Fin"),
        tok("ехал", "ехать", "VERB", Aspect="Imp", Tense="Past", VerbForm="Fin"),
        # Prefixed: an ordinary aspect pair, #600's, not here.
        tok("пришёл", "прийти", "VERB", Aspect="Perf", Tense="Past", VerbForm="Fin"),
    ]
    assert [[s for s in cell if s.startswith("motion")] for cell in squares(run)] == [
        ["motion:all:one"],
        ["motion:all:back"],
        ["motion:all:one"],
        [],
    ]
    said = motion(forms_of(run, times=15), {"идти": KNOWN, "ходить": KNOWN, "ехать": KNOWN})
    assert said is not None
    assert said["cells"]["one"]["known"] == 100 and said["cells"]["back"]["known"] == 100
    assert [(pair["one"], pair["back"], pair["known"]) for pair in said["pairs"]] == [
        ("идти", "ходить", "both"),
        ("ехать", "ездить", "one"),
    ]
    assert motion(forms_of(run, times=5), {}) is None, "under the floor, no section"


def test_nouns_in_soft_sign_by_gender_with_their_commonest_three() -> None:
    run = [
        tok("ночь", "ночь", "NOUN", Case="Nom", Number="Sing", Gender="Fem"),
        tok("день", "день", "NOUN", Case="Nom", Number="Sing", Gender="Masc"),
        tok("дверью", "дверь", "NOUN", Case="Ins", Number="Sing", Gender="Fem"),
        # A neuter -ь noun is tagger noise and left out.
        tok("ночь", "ночь", "NOUN", Case="Nom", Number="Sing", Gender="Neut"),
    ]
    assert [[s for s in cell if s.startswith("soft")] for cell in squares(run)] == [
        ["soft:fem"],
        ["soft:masc"],
        ["soft:fem"],
        [],
    ]
    said = soft_nouns(forms_of(run, times=20), {"ночь": KNOWN})
    assert said is not None
    rows = {row["row"]: row for row in said["rows"]}
    assert rows["fem"]["cells"]["all"]["known"] == 50
    assert rows["fem"]["examples"] == ["дверь", "ночь"]
    assert rows["masc"]["cells"]["all"]["known"] == 0


@pytest.mark.parametrize(
    ("surface", "feats", "row"),
    [
        ("читающий", {"VerbForm": "Part", "Case": "Nom"}, "partact"),
        ("прочитавшего", {"VerbForm": "Part", "Case": "Gen"}, "partact"),
        ("пришедший", {"VerbForm": "Part", "Case": "Nom"}, "partact"),
        ("улыбающаяся", {"VerbForm": "Part", "Case": "Nom"}, "partact"),
        ("должный", {"VerbForm": "Part", "Case": "Nom"}, None),
        ("читаемый", {"VerbForm": "Part", "Case": "Nom"}, "partpass"),
        ("прочитанную", {"VerbForm": "Part", "Case": "Acc"}, "partpass"),
        ("забытый", {"VerbForm": "Part", "Case": "Nom"}, "partpass"),
        ("сделано", {"VerbForm": "Part"}, "short"),
        ("читая", {"VerbForm": "Conv"}, "gerund"),
        ("читал", {"VerbForm": "Fin"}, None),
    ],
)
def test_a_participle_is_sorted_by_its_suffix_or_left_out(
    surface: str, feats: dict[str, str], row: str | None
) -> None:
    assert participle_of(surface, feats) == row


def test_participles_and_gerunds_by_aspect() -> None:
    run = [
        tok("читающий", "читать", "VERB", Aspect="Imp", Case="Nom", VerbForm="Part"),
        tok("сказав", "сказать", "VERB", Aspect="Perf", VerbForm="Conv"),
    ]
    said = progress(
        {
            **forms_of(run, times=30),
            **forms_of(
                [tok("дом", "дом", "NOUN", Case="Nom", Number="Sing")],
                times=30,
            ),
        },
        {"читать": KNOWN},
    )
    assert said is not None and said["forms"] is not None
    rows = {row["row"]: row for row in said["forms"]["rows"]}
    assert rows["partact"]["cells"]["imperfective"]["known"] == 100
    assert rows["gerund"]["cells"]["perfective"]["known"] == 0
    assert said["forms"]["gap"] is None, "only aspect and case rows name the gap"


def test_an_ignored_word_comes_out_of_every_count() -> None:
    run = [tok("дом", "дом", "NOUN", Case="Nom", Number="Sing")]
    assert progress(forms_of(run, times=40), {"дом": IGNORED}) is None


# -- the occurrences cache --------------------------------------------------------------


def _russian_text(folder: Path, runs: dict[int, list[list[dict[str, Any]]]]) -> Path:
    from targum.models import BlockKind, Segment, SegmentedDocument

    folder.mkdir(parents=True)
    segments = []
    tokens: dict[str, list[dict[str, Any]]] = {}
    for number, lines in runs.items():
        segments.append(
            Segment(
                id=f"h{number}",
                block_id=f"b{number}",
                block_index=number,
                index=len(segments),
                text=f"Глава {number}",
                kind=BlockKind.heading,
                level=1,
            )
        )
        for n, line in enumerate(lines):
            sid = f"s{number}-{n}"
            segments.append(
                Segment(
                    id=sid, block_id=f"b{number}", block_index=number, index=len(segments), text="x"
                )
            )
            tokens[sid] = [{"start": 0, "end": 1, **token} for token in line]
    SegmentedDocument(
        document_hash="ru-book", language="ru", segmenter="t/1", segments=segments
    ).write(folder / "segments.json")
    (folder / "annotation.json").write_text(
        json.dumps({"tokens": tokens, "language": "ru"}), encoding="utf-8"
    )
    (folder / "document.json").write_text(
        json.dumps({"title": "Книга", "language": "ru", "content_hash": "ru-book"}),
        encoding="utf-8",
    )
    reader = folder / "reader"
    reader.mkdir()
    for number in runs:
        (reader / f"sec-{number:04d}.html").write_text("<p>x</p>", encoding="utf-8")
    return folder


def test_the_cache_keeps_each_square_with_its_form_met_in_finished_sections(
    tmp_path: Path,
) -> None:
    occurrences._cached.cache_clear()
    folder = _russian_text(
        tmp_path / "book",
        {
            1: [
                [
                    tok("в", "в", "ADP"),
                    tok("доме", "дом", "NOUN", Case="Loc", Number="Sing", Animacy="Inan"),
                    tok("сказал", "сказать", "VERB", Aspect="Perf", Tense="Past", VerbForm="Fin"),
                ]
            ],
            2: [[tok("шёл", "идти", "VERB", Aspect="Imp", Tense="Past", VerbForm="Fin")]],
        },
    )

    def folder_for(document: str) -> tuple[Path, str] | None:
        return (folder, "ru") if document == "ru-book" else None

    read = [("ru-book", "1", 10)]
    assert occurrences.grammar_forms(read, folder_for) == {
        "place:v:where": {("дом", "в доме"): 1},
        "cases:loc:sing": {("дом", "доме"): 1},
        "aspect:perfective:past": {("сказать", "сказал"): 1},
    }
    # Cached and read back the same; a section not finished is not met.
    occurrences._cached.cache_clear()
    again = occurrences.grammar_forms([("ru-book", "1", 10), ("ru-book", "2", 11)], folder_for)
    assert again["motion:all:one"] == {("идти", "шёл"): 1}
    assert occurrences.grammar_forms(read, folder_for, language="he") == {}
    assert gaps_ru.VIEWS == ("aspect", "cases", "place", "motion", "soft", "forms")
