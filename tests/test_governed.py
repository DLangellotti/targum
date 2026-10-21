"""Which preposition a Hebrew verb takes, read off the stored syntax (design.md §12,
"Governed prepositions on the card", 2026-10-13): the fourth hard spot."""

from __future__ import annotations

from targum.annotate import gold
from targum.annotate.governed import Governed, governed, takes
from targum.annotate.score import Scorecard
from targum.models import Syntax, Token


def _token(
    surface: str,
    lemma: str,
    pos: str,
    head: int,
    relation: str,
    prefixes: tuple[str, ...] = (),
    lead: int = 0,
    start: int = 0,
) -> Token:
    return Token(
        start=start,
        end=start + len(surface),
        surface=surface,
        lemma=lemma,
        band=0,
        pos=pos,
        syntax=Syntax(head=head, relation=relation, prefixes=prefixes, lead=lead),
    )


# What DICTA said on 2026-10-13, as the annotator stores it.
WAITED = [
    _token("חיכיתי", "חיכה", "VERB", -1, "root"),
    _token("לָאוֹטוֹבּוּס", "אוטובוס", "NOUN", 0, "obl", ("DET", "ADP"), 1),
    _token("הרבה", "הרבה", "DET", 3, "det"),
    _token("זמן", "זמן", "NOUN", 0, "obl:tmod"),
]
TALKED = [
    _token("הוא", "הוא", "PRON", 1, "nsubj"),
    _token("דיבר", "דיבר", "VERB", -1, "root"),
    _token("עם", "עם", "ADP", 3, "case"),
    _token("המנהל", "מנהל", "NOUN", 1, "obl", ("DET",), 1),
    _token("על", "על", "ADP", 5, "case"),
    _token("הבעיה", "בעיה", "NOUN", 1, "obl", ("DET",), 1),
]
SAW = [
    _token("ראיתי", "ראה", "VERB", -1, "root"),
    _token("את", "את", "ADP", 2, "case:acc"),
    _token("הסרט", "סרט", "NOUN", 0, "obj", ("DET",), 1),
]


def test_a_letter_on_the_front_is_the_verbs_preposition() -> None:
    assert governed(WAITED) == [Governed(verb=0, argument=1, preposition="ל")]


def test_a_word_of_its_own_is_the_preposition_and_names_its_marker() -> None:
    assert governed(TALKED) == [
        Governed(verb=1, argument=3, preposition="עם", marker=2),
        Governed(verb=1, argument=5, preposition="על", marker=4),
    ]
    assert [pair.preposition for pair in takes(TALKED)[1]] == ["עם", "על"]


def test_et_marks_a_definite_object() -> None:
    assert governed(SAW) == [Governed(verb=0, argument=2, preposition="את", marker=1)]


def test_a_pronoun_on_the_preposition_is_the_argument() -> None:
    """לו, אותו: the annotator files them under the preposition (`dicta.CARRIED`)."""
    had = [
        _token("שיש", "יש", "VERB", -1, "root"),
        _token("לו", "ל", "ADP", 0, "obl"),
    ]
    assert governed(had) == [Governed(verb=0, argument=1, preposition="ל")]


def test_time_a_noun_head_and_a_broken_head_are_not_governed() -> None:
    assert governed(WAITED[2:]) == []
    noun_headed = [
        _token("ספר", "ספר", "NOUN", -1, "root"),
        _token("על", "על", "ADP", 2, "case"),
        _token("ים", "ים", "NOUN", 0, "nmod"),
    ]
    assert governed(noun_headed) == []
    broken = [_token("הלכתי", "הלך", "VERB", -1, "root"), _token("לים", "ים", "NOUN", 7, "obl")]
    assert governed(broken) == []


def test_the_long_tail_is_meaning_and_not_government() -> None:
    because = [
        _token("נסגר", "נסגר", "VERB", -1, "root"),
        _token("בשל", "בשל", "ADP", 2, "case"),
        _token("המלחמה", "מלחמה", "NOUN", 0, "obl", ("DET",), 1),
    ]
    assert governed(because) == []


GOLD = """# sent_id = t1
# text = חיכיתי לאוטובוס.
1\tחיכיתי\tחיכה\tVERB\t_\tHebBinyan=PIEL\t0\troot\t_\t_
2-4\tלאוטובוס\t_\t_\t_\t_\t_\t_\t_\t_
2\tל\tל\tADP\t_\t_\t4\tcase\t_\t_
3\tה\tה\tDET\t_\t_\t4\tdet\t_\t_
4\tאוטובוס\tאוטובוס\tNOUN\t_\t_\t1\tobl\t_\t_
5\t.\t.\tPUNCT\t_\t_\t1\tpunct\t_\t_

"""


def test_the_treebank_says_its_triples() -> None:
    (sentence,) = gold.parse(GOLD)
    assert sentence.governed == ((0, 6, "ל", 7, 15),)
    assert [token.surface for token in sentence.tokens] == ["חיכיתי", "לאוטובוס"]


def test_the_scorecard_counts_precision_and_recall() -> None:
    card = Scorecard(annotator="a", corpus="c")
    card.add_governed(
        {(0, 6, "ל", 7, 15), (0, 6, "את", 20, 24)}, {(0, 6, "ל", 7, 15), (0, 6, "ב", 7, 15)}
    )
    rates = card.rates()
    assert rates["governed_precision"] == 0.5
    assert rates["governed_recall"] == 0.5


def test_the_builder_says_it_on_the_grammar_line() -> None:
    from targum.render.builder import _governed_lines

    lines = _governed_lines(TALKED)
    assert lines[id(TALKED[1])] == "Takes=עם,על"
    assert lines[id(TALKED[3])] == "Governor=דיבר|Prep=עם"
    assert lines[id(TALKED[2])] == "Governor=דיבר|Prep=עם"
    assert lines[id(TALKED[5])] == "Governor=דיבר|Prep=על"
    assert id(TALKED[0]) not in lines
    assert _governed_lines([_token("x", "x", "NOUN", -1, "")]) == {}


def test_a_word_read_past_does_not_move_the_heads_after_it() -> None:
    """An English name inside the Hebrew is read past (`in_script`), which shortened the
    list every `Syntax.head` counts, so a preposition landed on the next word over."""
    from targum.annotate import Annotator
    from targum.models import Segment, SegmentedDocument

    text = "ראיתי Netflix ואז חיכיתי לאוטובוס"

    class Said:
        name = "said/1"

        def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
            words = [
                ("ראיתי", "ראה", "VERB", -1, "root", (), 0),
                ("Netflix", "netflix", "PROPN", 0, "obj", (), 0),
                ("ואז", "אז", "ADV", 3, "advmod", ("CCONJ",), 1),
                ("חיכיתי", "חיכה", "VERB", 0, "conj", (), 0),
                ("לאוטובוס", "אוטובוס", "NOUN", 3, "obl", ("DET", "ADP"), 1),
            ]
            out = []
            for surface, lemma, pos, head, relation, prefixes, lead in words:
                start = text.index(surface)
                out.append(_token(surface, lemma, pos, head, relation, prefixes, lead, start))
            return {segments[0].id: out}

    class Flat:
        name = "flat/1"
        method = "curated:test"
        note = "A test list."

        def supports(self, language: str) -> bool:
            return True

        def band(self, lemma: str, language: str) -> int:
            return 0

    document = SegmentedDocument(
        document_hash="h",
        language="he",
        segmenter="x",
        segments=[Segment(id="s", block_id="b", block_index=0, index=0, text=text)],
    )
    tokens = Annotator(lemmatizer=Said(), bands=Flat()).annotate(document).tokens["s"]
    assert [token.surface for token in tokens] == ["ראיתי", "ואז", "חיכיתי", "לאוטובוס"]
    assert [token.syntax.head for token in tokens if token.syntax] == [-1, 2, 0, 2]
    assert governed(tokens) == [Governed(verb=2, argument=3, preposition="ל")]
