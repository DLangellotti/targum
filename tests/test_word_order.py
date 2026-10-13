"""A Russian subject after its verb (`annotate/word_order.py`), Russian's word-order hard
spot in `stages.HARD_SPOTS`, shown on a lens (design.md §12, "Subjects after their verb,
on a lens", 2026-10-13)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from targum import stages
from targum.annotate.word_order import Inverted, inverted
from targum.models import Token


def _tokens(text: str, said: list[tuple[str, str, str]]) -> list[Token]:
    """Tokens placed in `text` in order: (surface, part of speech, grammar)."""
    out, cursor = [], 0
    for surface, pos, feats in said:
        start = text.index(surface, cursor)
        cursor = start + len(surface)
        out.append(
            Token(
                start=start,
                end=cursor,
                surface=surface,
                lemma=surface.lower(),
                band=0,
                pos=pos,
                feats=f"UPOS={pos}|{feats}" if feats else f"UPOS={pos}",
            )
        )
    return out


WROTE = "Книгу написал Толстой."
WROTE_SAID = [
    ("Книгу", "NOUN", "Case=Acc|Gender=Fem|Number=Sing"),
    ("написал", "VERB", "Gender=Masc|Number=Sing|Aspect=Perf|Tense=Past|VerbForm=Fin"),
    ("Толстой", "PROPN", "Case=Nom|Gender=Masc|Number=Sing"),
]


def test_the_subject_after_its_verb_is_found() -> None:
    assert inverted(WROTE, _tokens(WROTE, WROTE_SAID)) == [Inverted(verb=1, subject=2)]


def test_a_subject_before_its_verb_is_not() -> None:
    text = "Толстой написал книгу."
    said = [
        ("Толстой", "PROPN", "Case=Nom|Gender=Masc|Number=Sing"),
        ("написал", "VERB", "Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin"),
        ("книгу", "NOUN", "Case=Acc|Gender=Fem|Number=Sing"),
    ]
    assert inverted(text, _tokens(text, said)) == []


def test_the_verb_must_agree_with_it() -> None:
    """A plural verb is not a singular noun's, nor a feminine past a masculine one's."""
    text = "Пришли гости, пришла мама, пришёл мама."
    said = [
        ("Пришли", "VERB", "Number=Plur|Tense=Past|VerbForm=Fin"),
        ("гости", "NOUN", "Case=Nom|Gender=Masc|Number=Plur"),
        ("пришла", "VERB", "Gender=Fem|Number=Sing|Tense=Past|VerbForm=Fin"),
        ("мама", "NOUN", "Case=Nom|Gender=Fem|Number=Sing"),
        ("пришёл", "VERB", "Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin"),
        ("мама", "NOUN", "Case=Nom|Gender=Fem|Number=Sing"),
    ]
    assert inverted(text, _tokens(text, said)) == [Inverted(0, 1), Inverted(2, 3)]


def test_a_comma_ends_the_clause_and_a_short_participle_is_a_verb() -> None:
    text = "Он сказал, дом построен, и был построен дом."
    said = [
        ("Он", "PRON", "Case=Nom|Gender=Masc|Number=Sing|Person=3"),
        ("сказал", "VERB", "Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin"),
        ("дом", "NOUN", "Case=Nom|Gender=Masc|Number=Sing"),
        ("построен", "VERB", "Gender=Masc|Number=Sing|VerbForm=Part"),
        ("и", "CCONJ", ""),
        ("был", "AUX", "Gender=Masc|Number=Sing|Tense=Past|VerbForm=Fin"),
        ("построен", "VERB", "Gender=Masc|Number=Sing|VerbForm=Part"),
        ("дом", "NOUN", "Case=Nom|Gender=Masc|Number=Sing"),
    ]
    assert inverted(text, _tokens(text, said)) == [Inverted(6, 7)]


def test_a_first_person_verb_takes_no_noun_and_only_the_first_nominative_counts() -> None:
    text = "Читаю книга. Стоят дом и сад."
    said = [
        ("Читаю", "VERB", "Number=Sing|Person=1|Tense=Pres|VerbForm=Fin"),
        ("книга", "NOUN", "Case=Nom|Gender=Fem|Number=Sing"),
        ("Стоят", "VERB", "Number=Plur|Person=3|Tense=Pres|VerbForm=Fin"),
        ("дом", "NOUN", "Case=Nom|Gender=Masc|Number=Sing"),
        ("сад", "NOUN", "Case=Nom|Gender=Masc|Number=Sing"),
    ]
    assert inverted(text, _tokens(text, said)) == []


def test_the_builder_says_it_on_the_grammar_line() -> None:
    from targum.render.builder import _order_lines

    tokens = _tokens(WROTE, WROTE_SAID)
    assert _order_lines(WROTE, tokens) == {id(tokens[2]): "Order=VS"}


def _eval_lemma() -> ModuleType:
    script = Path(__file__).parent.parent / "scripts" / "eval_lemma.py"
    spec = importlib.util.spec_from_file_location("eval_lemma", script)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass looks its own module up by name.
    sys.modules["eval_lemma"] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def test_the_gold_is_a_treebank_subject_whose_verb_stands_before_it(tmp_path: Path) -> None:
    conllu = tmp_path / "dev.conllu"
    conllu.write_text(
        "# text = Книгу написал Толстой.\n"
        "1\tКнигу\tкнига\tNOUN\t_\tCase=Acc\t2\tobj\t_\t_\n"
        "2\tнаписал\tнаписать\tVERB\t_\tTense=Past\t0\troot\t_\t_\n"
        "3\tТолстой\tТолстой\tPROPN\t_\tCase=Nom\t2\tnsubj\t_\t_\n"
        "4\t.\t.\tPUNCT\t_\t_\t2\tpunct\t_\t_\n"
        "\n"
        "# text = Он врач.\n"
        "1\tОн\tон\tPRON\t_\tCase=Nom\t2\tnsubj\t_\t_\n"
        "2\tврач\tврач\tNOUN\t_\tCase=Nom\t0\troot\t_\t_\n"
        "3\t.\t.\tPUNCT\t_\t_\t2\tpunct\t_\t_\n"
        "\n",
        encoding="utf-8",
    )
    module = _eval_lemma()
    (wrote, doctor) = module.sentences(conllu)
    assert module.subjects_after(module.spans(*wrote)) == {(14, 21)}
    assert module.subjects_after(module.spans(*doctor)) == set()


def test_word_order_is_covered_and_russian_owes_it_no_longer() -> None:
    known = stages.facts("ru")
    assert known.covered["word order"], known.covered
    short = stages.shortfall(known, stages.Stage.alpha)
    assert "hard spot not covered: word order" not in short, short
