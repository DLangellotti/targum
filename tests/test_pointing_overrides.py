"""The hand-kept pointing table (`vocalize.overrides`, targum-internal#689): קולה is cola,
קוֹלָה, where the words around it say so, and stays קוֹלָהּ, "her voice", everywhere else."""

from __future__ import annotations

from pathlib import Path

from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
    Vocalization,
)
from targum.vocalize import strip_nikkud
from targum.vocalize.overrides import overridden, table

COLA = "קוֹלָה"
VOICE = "קוֹלָהּ"


def _text(*lines: tuple[str, str]) -> tuple[SegmentedDocument, Vocalization, Annotation]:
    """Segments from (bare, pointed) pairs, all pointed by a model, with an annotation
    reading every קולה as DICTA does: lemma קול, a noun with her on the end."""
    segments, pointed, tokens = [], {}, {}
    for at, (bare, dotted) in enumerate(lines):
        sid = f"s{at}"
        segments.append(Segment(id=sid, block_id=f"b{at}", block_index=at, index=0, text=bare))
        pointed[sid] = dotted
        start = bare.find("קולה")
        if start >= 0:
            front = 0
            while start - front > 0 and bare[start - front - 1] not in " ":
                front += 1
            tokens[sid] = [
                Token(
                    start=start - front,
                    end=start + 4,
                    surface=bare[start - front : start + 4],
                    lemma="קול",
                    band=1,
                    pos="NOUN",
                    feats="Gender=Masc|Number=Sing|Gender[psor]=Fem|Number[psor]=Sing|Person[psor]=3",
                )
            ]
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="t/1", segments=segments
    )
    vocalization = Vocalization(
        document_hash="h",
        language="he",
        vocalizer="dicta/menaked",
        segments=pointed,
        machine=list(pointed),
    )
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="dicta/t",
        method="frequency",
        method_note="a test",
        tokens=tokens,
    )
    return segmented, vocalization, annotation


def test_the_table_spells_its_words() -> None:
    for entry in table():
        assert strip_nikkud(entry.pointed)[0] == entry.bare


def test_cola_in_a_bottle_is_cola() -> None:
    segmented, vocalization, annotation = _text(
        ("קניתי בקבוק קולה בקיוסק", f"קָנִיתִי בַּקְבּוּק {VOICE} בַּקִּיּוֹסְק"),
    )
    out = overridden(vocalization, segmented, annotation)
    assert out is not None
    assert out.segments["s0"] == f"קָנִיתִי בַּקְבּוּק {COLA} בַּקִּיּוֹסְק"
    # The file keeps what the diacritizer said.
    assert vocalization.segments["s0"].count(VOICE) == 1


def test_her_voice_stays_her_voice() -> None:
    """The lemma is קול with her on the end and nothing around it says drink: DICTA's
    pointing stands, and the same object comes back."""
    segmented, vocalization, annotation = _text(
        ("וקולה היה נעים", f"וְ{VOICE} הָיָה נָעִים"),
        ("שמעתי את קולה", f"שָׁמַעְתִּי אֶת {VOICE}"),
    )
    assert overridden(vocalization, segmented, annotation) is vocalization


def test_one_text_one_sense() -> None:
    """Once a cue says cola and nothing says voice, every קולה in the text is cola, the
    article's dagesh kept: Kan's video says "small cola" far more often than "bottle"."""
    segmented, vocalization, annotation = _text(
        ("למה קולה קטן עולה יותר מקולה גדול?", f"לָמָּה {VOICE} קָטָן עוֹלֶה יוֹתֵר מִ{VOICE} גָּדוֹל?"),
        ("בקבוק קטן של קולה", f"בַּקְבּוּק קָטָן שֶׁל {VOICE}"),
        ("על הקולה הגדול מפסידים", "עַל הַקּוֹלָהּ הַגָּדוֹל מַפְסִידִים"),
    )
    out = overridden(vocalization, segmented, annotation)
    assert out is not None
    assert out.segments["s0"] == f"לָמָּה {COLA} קָטָן עוֹלֶה יוֹתֵר מִ{COLA} גָּדוֹל?"
    assert out.segments["s1"] == f"בַּקְבּוּק קָטָן שֶׁל {COLA}"
    assert out.segments["s2"] == "עַל הַקּוֹלָה הַגָּדוֹל מַפְסִידִים"


def test_a_voice_in_the_text_keeps_the_rest_as_they_were() -> None:
    """A text where one קולה is somebody's voice is not one sense: only the cued one
    moves."""
    segmented, vocalization, annotation = _text(
        ("היא שתתה קולה", f"הִיא שָׁתְתָה {VOICE}"),
        ("קולה הצעיר רעד", f"{VOICE} הַצָּעִיר רָעַד"),
        ("קולה קטן", f"{VOICE} קָטָן"),
    )
    out = overridden(vocalization, segmented, annotation)
    assert out is not None
    assert out.segments["s0"] == f"הִיא שָׁתְתָה {COLA}"
    assert out.segments["s1"] == vocalization.segments["s1"]
    assert out.segments["s2"] == vocalization.segments["s2"]


def test_a_cue_across_a_full_stop_is_no_cue() -> None:
    segmented, vocalization, annotation = _text(
        ("היא פתחה בקבוק. קולה רעד", f"הִיא פָּתְחָה בַּקְבּוּק. {VOICE} רָעַד"),
    )
    assert overridden(vocalization, segmented, annotation) is vocalization


def test_another_lemma_or_the_editions_pointing_is_left_alone() -> None:
    segmented, vocalization, annotation = _text(
        ("בקבוק קולה", f"בַּקְבּוּק {VOICE}"),
    )
    other = annotation.model_copy(
        update={"tokens": {"s0": [annotation.tokens["s0"][0].model_copy(update={"lemma": "קלה"})]}}
    )
    assert overridden(vocalization, segmented, other) is vocalization
    edition = vocalization.model_copy(update={"machine": []})
    assert overridden(edition, segmented, annotation) is edition


def test_the_reader_shows_cola(tmp_path: Path) -> None:
    """Through `render`, as a free `targum rebuild` writes a page."""
    from targum.render import render

    segmented, vocalization, annotation = _text(
        ("קניתי בקבוק קולה", f"קָנִיתִי בַּקְבּוּק {VOICE}"),
    )
    text = segmented.segments[0].text
    pages = render(
        Document(
            source="memory",
            title="Cola",
            language="he",
            blocks=[Block(id="b0", kind=BlockKind.paragraph, text=text)],
            content_hash="h",
        ),
        segmented,
        [
            Translation(
                name="English",
                document_hash="h",
                source_language="he",
                target_language="en",
                provider="null",
                segments={"s0": "I bought a bottle of cola."},
            )
        ],
        tmp_path / "reader",
        annotation=annotation,
        vocalization=vocalization,
    )
    html = "".join(page.read_text(encoding="utf-8") for page in pages)
    # קוֹלָה is קוֹלָהּ less its mapiq, so the one is found and the other is not.
    assert COLA in html
    assert VOICE not in html
