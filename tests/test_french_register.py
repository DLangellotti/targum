"""French register, *ne* dropped and *on* for "we" (`annotate/french_register.py`):
French's seventh hard spot in `stages.HARD_SPOTS`, shown on the card as register and
not as error (D5, 2026-11-05)."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from targum import evals, stages
from targum.annotate.french_register import Word, lines, ne_dropped, ons, words_of
from targum.models import Annotation, Document, Segment, SegmentedDocument, Token, Translation
from targum.render import render

ROOT = Path(__file__).parent.parent


def _drops(sentence: str) -> list[tuple[str, str]]:
    words = words_of(sentence)
    return [(words[one.negator].surface, one.formal) for one in ne_dropped(sentence, words)]


def _we(sentence: str) -> list[bool]:
    return [one.we for one in ons(sentence, words_of(sentence))]


@pytest.mark.parametrize(
    ("sentence", "said"),
    [
        ("Je sais pas où il est.", [("pas", "Je ne sais pas")]),
        ("J'ai jamais compris pourquoi.", [("jamais", "Je n'ai jamais")]),
        ("C’est pas grave.", [("pas", "Ce n’est pas")]),
        ("Il y a plus rien.", [("plus", "Il n'y a plus")]),
        ("On a pas le temps.", [("pas", "On n'a pas")]),
        ("Il m'a dit qu'il viendrait pas.", [("pas", "il ne viendrait pas")]),
        ("J'en peux plus.", [("plus", "Je n'en peux plus")]),
        ("T'as pas vu mes clés ?", [("pas", "Tu n'as pas")]),
        # One ne for the clause, named at its first negator.
        ("J'ai jamais rien vu.", [("jamais", "Je n'ai jamais")]),
    ],
)
def test_a_negation_without_ne_is_named_with_its_formal_clause(
    sentence: str, said: list[tuple[str, str]]
) -> None:
    assert _drops(sentence) == said


@pytest.mark.parametrize(
    "sentence",
    [
        "Je ne sais pas où il est.",
        "Je n'ai rien vu et je ne veux rien savoir.",
        "Il ne faut jamais dire jamais.",
        "Rien ne va plus.",
        "Personne n'est venu.",
        # Not negation at all.
        "J'ai fait un pas vers la porte.",
        "Une personne m'a appelé ce matin.",
        "Il fait plus chaud qu'hier.",
        "Il y a plus de monde qu'hier.",
        "Je veux plus de café, s'il te plaît.",
        "Je t'aimerai à jamais.",
        "Si jamais tu le vois, dis-lui bonjour.",
        "Elle est partie sans rien dire.",
        "De rien, c'est normal.",
        "— Non, je l’appelle le Cocu, c’est plus gentil.",
        # No verb, so nothing dropped.
        "Pas de souci, je m'en occupe.",
        "Plus jamais ça.",
    ],
)
def test_a_kept_ne_or_no_negation_says_nothing(sentence: str) -> None:
    assert _drops(sentence) == []


def test_a_negator_the_tagger_calls_a_noun_is_not_one() -> None:
    text = "Je fais pas"
    words = [Word(0, 2, "Je"), Word(3, 7, "fais"), Word(8, 11, "pas")]
    assert ne_dropped(text, words)
    words[2] = Word(8, 11, "pas", "NOUN")
    assert ne_dropped(text, words) == []


@pytest.mark.parametrize(
    ("sentence", "we"),
    [
        ("Nous, on est pas d'accord.", [True]),
        ("On est partis vers huit heures.", [True]),
        ("Ça fait longtemps qu'on s'est pas vus.", [True]),
        ("Toi et moi, on part demain.", [True]),
        ("On y va ?", [True]),
        ("Et si on allait au cinéma ?", [True]),
        ("On rentre chez nous.", [True]),
        ("On dit que l'hiver sera rude.", [False]),
        ("On est prié de fermer la porte.", [False]),
        ("Quand on est jeune, on croit tout savoir.", [False, False]),
        ("Peut-on fumer ici ?", [False]),
        ("Tu verras ce que l’on gagne à vouloir vivre libre.", [False]),
    ],
)
def test_on_is_we_only_where_the_sentence_says_so(sentence: str, we: list[bool]) -> None:
    assert _we(sentence) == we


def test_the_lines_are_what_the_card_reads() -> None:
    text = "Nous, on sait pas."
    words = words_of(text)
    assert lines(text, words) == {1: "On=We", 3: "Reg=NeDrop|Formal=on ne sait pas"}
    text = "On dit que c'est fini."
    assert lines(text, words_of(text)) == {0: "On=Open"}


def test_the_builder_says_it_on_the_grammar_line() -> None:
    from targum.render.builder import _register_lines

    text = "Je sais pas."
    tokens = [
        Token(start=0, end=2, surface="Je", lemma="je", band=0, pos="PRON"),
        Token(start=3, end=7, surface="sais", lemma="savoir", band=0, pos="VERB"),
        Token(start=8, end=11, surface="pas", lemma="pas", band=0, pos="ADV"),
    ]
    assert _register_lines(text, tokens) == {id(tokens[2]): "Reg=NeDrop|Formal=Je ne sais pas"}


def test_a_french_reader_carries_the_lines_and_another_does_not(tmp_path: Path) -> None:
    text = "On sait pas."
    segment = Segment(id="0000.000-aaaaaa", block_id="b0000", block_index=0, index=0, text=text)
    tokens = [
        Token(start=0, end=2, surface="On", lemma="on", band=1, pos="PRON", feats="UPOS=PRON"),
        Token(start=3, end=7, surface="sait", lemma="savoir", band=1, pos="VERB"),
        Token(start=8, end=11, surface="pas", lemma="pas", band=1, pos="ADV", feats="UPOS=ADV"),
    ]

    def grammar(language: str) -> list[str]:
        segmented = SegmentedDocument(
            document_hash="h", language=language, segmenter="fake/1", segments=[segment]
        )
        document = Document(source="m", title="T", language=language, blocks=[], content_hash="h")
        translation = Translation(
            name="English",
            document_hash="h",
            source_language=language,
            target_language="en",
            provider="null",
            segments={segment.id: "We don't know."},
        )
        annotation = Annotation(
            document_hash="h",
            language=language,
            annotator="t",
            method="frequency",
            method_note="note",
            tokens={segment.id: tokens},
        )
        html = render(
            document, segmented, [translation], tmp_path / language, annotation=annotation
        )[0].read_text(encoding="utf-8")
        found = re.search(r'id="targum-data"[^>]*>(.*?)</script>', html, re.S)
        assert found is not None
        data: dict[str, Any] = json.loads(found.group(1))
        return [data["grammar"][row[8]] for row in data["words"][segment.id]]

    said = grammar("fr")
    assert said[0] == "UPOS=PRON|On=Open"
    assert said[2] == "UPOS=ADV|Reg=NeDrop|Formal=On ne sait pas"
    assert not any("Reg=" in line or "On=" in line for line in grammar("it"))


def test_the_card_says_both_lines_in_english_and_russian() -> None:
    from targum import strings

    script = (ROOT / "src" / "targum" / "render" / "assets" / "reader.js").read_text("utf-8")
    assert 'feat(takesLine, "Reg") === "NeDrop"' in script
    assert 'feat(takesLine, "On")' in script
    for key in ("informal", "ne-dropped", "on-we", "on-who", "on-open"):
        assert strings.catalogue("en")[f"reader.card.{key}"]
        assert strings.catalogue("ru")[f"reader.card.{key}"]


def _eval_register() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "eval_register", ROOT / "scripts" / "eval_register.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_ledger_holds_what_the_gold_scores_now() -> None:
    """The rule and the gold as committed score what the ledger says, so a change to either
    that moves a number has to record it, and the floors read the new number."""
    scorer = _eval_register()
    rows = [json.loads(line) for line in scorer.GOLD.read_text(encoding="utf-8").splitlines()]
    assert len(rows) >= 60
    assert {row["register"] for row in rows} == {"formal", "neutral", "informal"}
    scored = scorer.score(rows, quiet=True)
    latest = evals.latest(evals.read(ROOT / "evals" / "ledger.jsonl"))
    for metric, (value, n) in scored.items():
        row = latest[(scorer.STAGE, scorer.CORPUS, metric)]
        assert (row.score, row.n) == (round(value, 4), n), metric


def test_the_gold_marks_every_on_and_each_drop_where_its_word_is() -> None:
    for line in (ROOT / "evals" / "french-register-gold.jsonl").read_text("utf-8").splitlines():
        row = json.loads(line)
        sentence = row["sentence"]
        for start, end, word, formal in row["ne_dropped"]:
            assert sentence[start:end] == word and " n" in f" {formal}", sentence
        marked = [sentence[start:end].lower() for start, end, _ in row["on"]]
        assert marked == ["on"] * len(re.findall(r"(?i)(?<![\w-])on\b|-on\b", sentence))


def test_the_spot_is_covered() -> None:
    spot = next(one for one in stages.HARD_SPOTS["fr"] if one.name.startswith("register"))
    assert spot.floor == ("register-rule", "fr-register-own", "nedrop_precision")
    assert stages._covered(spot, evals.floors(ROOT / "evals" / "floors.json"))
    held = {
        (row["system"], row["corpus"], row["metric"])
        for row in json.loads((ROOT / "evals" / "floors.json").read_text(encoding="utf-8"))
    }
    assert ("register-rule", "fr-register-own", "on_we_precision") in held
