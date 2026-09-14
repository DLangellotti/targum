"""Russian stress marks, placed only where two sources agree (targum-internal#260).

Offline: silero is a fake that answers with `+` marks from a table, and the dictionary is
a handful of rows. Under test is the rule — what is marked, what is left alone — and that
the letters never change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from targum.annotate import openrussian
from targum.models import Annotation, BlockKind, Segment, SegmentedDocument, Token
from targum.vocalize import russian, stress
from targum.vocalize.base import has_nikkud, splice, strip_nikkud

A = stress.ACUTE
Y = stress.DIAERESIS


def entry(kind: str, written: str, **forms: list[str]) -> openrussian.Entry:
    return openrussian.Entry(kind, written, forms=dict(forms))


@pytest.fixture
def lexicon() -> openrussian.Lexicon:
    table = openrussian.Lexicon()
    rows = {
        "рука": [
            entry(
                "noun",
                "рука'",
                sg_nom=["рука'"],
                sg_gen=["руки'"],
                sg_acc=["ру'ку"],
                pl_nom=["ру'ки"],
            )
        ],
        "замок": [
            entry("noun", "за'мок", sg_nom=["за'мок"], pl_nom=["за'мки"]),
            entry("noun", "замо'к", sg_nom=["замо'к"], pl_nom=["замки'"]),
        ],
        "болеть": [entry("verb", "боле'ть", past_f=["боле'ла"])],
        "ещё": [entry("other", "ещё")],
        "все": [entry("other", "все")],
        "всё": [entry("other", "всё")],
        "кале": [entry("noun", "ка'ле")],
    }
    table.entries = rows
    for items in rows.values():
        for row in items:
            for written in [row.written, *(v for vs in row.forms.values() for v in vs)]:
                table.spellings.setdefault(openrussian.fold(written), set()).add(written)
    return table


class FakeSilero:
    """Stresses every vowel it is told to, and restores ё where it is told to."""

    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers

    def __call__(self, text: str) -> str:
        out = text
        for bare, marked in self.answers.items():
            out = out.replace(bare, marked)
        return out


def marked(text: str, answers: dict[str, str], lexicon: openrussian.Lexicon, tokens=()) -> str:
    proposals = stress.read_proposal(text, FakeSilero(answers)(text))
    assert proposals is not None
    return stress.mark(text, proposals, lexicon, tokens)


def test_a_word_is_marked_only_where_both_sources_agree(lexicon) -> None:
    text = "Рука болела, руку."
    out = marked(text, {"Рука": "Рук+а", "болела": "бол+ела", "руку": "рук+у"}, lexicon)
    assert out == f"Рука{A} боле{A}ла, руку."
    assert strip_nikkud(out)[0] == text, "the letters never change"


def test_a_homograph_stays_bare_unless_its_tags_settle_it(lexicon) -> None:
    text = "замки руки"
    answers = {"замки": "замк+и", "руки": "рук+и"}
    assert marked(text, answers, lexicon) == text, "two stresses in the tables: no mark"
    tagged = [
        Token(
            start=6,
            end=10,
            surface="руки",
            lemma="рука",
            band=1,
            feats="UPOS=NOUN|Case=Gen|Number=Sing",
        ),
    ]
    assert marked(text, answers, lexicon, tagged) == f"замки руки{A}"
    wrong = [
        Token(
            start=6,
            end=10,
            surface="руки",
            lemma="рука",
            band=1,
            feats="UPOS=NOUN|Case=Nom|Number=Plur",
        ),
    ]
    assert marked(text, answers, lexicon, wrong) == text, "silero and the tag disagree"


def test_yo_is_restored_as_a_mark_where_the_tables_allow_one_spelling(lexicon) -> None:
    out = marked("еще все", {"еще": "ещ+ё", "все": "вс+ё"}, lexicon)
    assert out == f"еще{Y} все", "всё and все are both words: left alone"
    assert strip_nikkud(out)[0] == "еще все"


def test_names_one_vowel_words_and_halves_are_never_marked(lexicon) -> None:
    text = "Кале рука-кале"
    tokens = [Token(start=0, end=4, surface="Кале", lemma="Кале", band=1, pos="PROPN")]
    out = marked(text, {"Кале": "К+але", "рука": "рук+а", "кале": "к+але"}, lexicon, tokens)
    assert out == f"Кале рука-ка{A}ле"


def test_a_sentence_silero_changed_is_left_unmarked() -> None:
    assert stress.read_proposal("рука", "рука!") is None
    assert stress.read_proposal("рука", "рук+а") is not None


def test_the_marks_splice_like_vowel_points_and_keep_a_source_s_own() -> None:
    source = f"ру{A}ку рука"
    model = f"руку{A} рука{A}"
    merged, from_model = splice(source, model)
    assert merged == f"ру{A}ку рука{A}" and from_model
    assert has_nikkud(merged) and not has_nikkud("cafe" + A)


def test_the_engine_says_what_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
    engine = russian.StressVocalizer(accentor=FakeSilero({}))
    usable, why = engine.available()
    assert not usable and "openrussian" in why
    assert engine.name.startswith("stress/silero-stress-") and openrussian.NAME in engine.name


def test_a_build_marks_russian_after_its_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lexicon
) -> None:
    """The stage runs after the annotation, records what settled it, is reused while that
    holds, and is marked again when the words are read again."""
    from targum.pipeline import Build

    monkeypatch.setattr(openrussian, "available", lambda: True)
    monkeypatch.setattr(openrussian, "load", lambda folder=None: lexicon)
    segment = Segment(
        id="0000.000-a",
        block_id="b",
        block_index=0,
        index=0,
        kind=BlockKind.paragraph,
        text="Рука болела.",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="ru", segmenter="t", segments=[segment]
    )
    silero: Any = FakeSilero({"Рука": "Рук+а", "болела": "бол+ела"})
    engine = russian.StressVocalizer(accentor=silero)
    build = Build(
        "x.md", target_language="en", provider_name="null", out=tmp_path, vocalizer=engine
    )
    build._resolved_out = tmp_path / "out"
    build.resolved_out.mkdir(parents=True, exist_ok=True)
    first = Annotation(
        document_hash="h",
        language="ru",
        annotator="words/1",
        method="m",
        method_note="n",
        tokens={},
    )
    marked_once = build.stress(segmented, first)
    assert marked_once is not None
    assert marked_once.segments == {segment.id: f"Рука{A} боле{A}ла."}
    assert marked_once.machine == [segment.id]
    assert marked_once.model and marked_once.model.endswith("· words/1")
    assert build.stress(segmented, first) is not None and "stress" in build.reused
    second = first.model_copy(update={"annotator": "words/2"})
    again = build.stress(segmented, second)
    assert again is not None and again.model and again.model.endswith("· words/2")
    hebrew = segmented.model_copy(update={"language": "he"})
    assert build.stress(hebrew, first) is None
