"""Refinement: from words heard to text a reader can follow, clocks intact."""

from __future__ import annotations

from targum.transcribe.models import Transcript, Word
from targum.transcribe.refine.anthropic import AnthropicRefiner
from targum.transcribe.refine.rules import RuleRefiner


def heard(text: str, step: float = 1.0, speaker: str = "") -> list[Word]:
    return [
        Word(text=piece, start=round(n * step, 3), end=round(n * step + 0.8, 3), speaker=speaker)
        for n, piece in enumerate(text.split())
    ]


def test_a_long_pause_breaks_a_paragraph_and_a_short_one_does_not() -> None:
    words = heard("one two")
    words += [Word(text="three", start=5.0, end=5.5)]
    refined = RuleRefiner().refine(
        Transcript(provider="null", language="he", duration=6.0, words=words)
    )
    assert [p.text for p in refined.paragraphs] == ["one two", "three"]


def test_a_paragraph_nobody_paused_in_is_cut_at_its_longest_pause() -> None:
    """Someone talking over music never stops for 1.2 s. A 57-minute video came back as
    paragraphs of hundreds of words, each one line of the reader and one call to the
    lemmatizer, which cut it off at 512 tokens (2026-09-14)."""
    from targum.transcribe.refine.rules import (
        LEAST_PARAGRAPH_WORDS,
        MAX_PARAGRAPH_WORDS,
    )

    words = heard(" ".join(f"מילה{n}" for n in range(300)), step=0.5)
    # The breaths a speaker takes: longer every so often, never a paragraph's pause.
    for n in range(37, 300, 37):
        for later in words[n:]:
            later.start = round(later.start + 0.6, 3)
            later.end = round(later.end + 0.6, 3)
    refined = RuleRefiner().refine(
        Transcript(provider="test", language="he", duration=200.0, words=words)
    )
    lengths = [len(p.words) for p in refined.paragraphs]
    assert sum(lengths) == 300, "every word is kept"
    assert max(lengths) <= MAX_PARAGRAPH_WORDS
    assert min(lengths) >= LEAST_PARAGRAPH_WORDS
    assert refined.paragraphs[1].words[0].text == "מילה37", "the cut is at the breath"
    assert [w for p in refined.paragraphs for w in p.words] == words, "clocks untouched"


def test_a_cut_after_a_sentence_beats_a_longer_pause_inside_one() -> None:
    words = heard(" ".join(f"מילה{n}" for n in range(50)), step=0.5)
    words[19].text += "."
    for later in words[30:]:
        later.start = round(later.start + 0.9, 3)
        later.end = round(later.end + 0.9, 3)
    refined = RuleRefiner().refine(
        Transcript(provider="test", language="he", duration=30.0, words=words)
    )
    assert [len(p.words) for p in refined.paragraphs] == [20, 30]


def test_a_hearing_the_last_rules_refined_is_not_redone(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """rules/2 differs from rules/1 only in long paragraphs. Redoing a rules/1 part
    would re-cut its segments, buy its translation again and move its reader's place."""
    from targum.ingest.audio import refined_path
    from targum.pipeline import Build
    from targum.transcribe.models import Refined
    from targum.transcribe.models import write as write_model

    workspace = tmp_path / "audio"
    for number, refiner in ((1, "rules/1"), (2, "rules/2"), (3, "none")):
        write_model(
            refined_path(workspace, number),
            Refined(refiner=refiner, provider="openai/whisper-1", language="he", paragraphs=[]),
        )
    build = Build(str(tmp_path / "talk.mp3"), target_language="en", out_root=tmp_path / "out")
    assert not build._needs_hearing(workspace, 1)
    assert not build._needs_hearing(workspace, 2)
    assert build._needs_hearing(workspace, 3), "a refiner it does not keep is still redone"
    assert build._needs_hearing(workspace, 4), "and a part never heard is heard"


def test_the_model_backed_refiner_maps_every_kept_word_back_to_its_clock() -> None:
    """The one hard rule: timing is never guessed. A repunctuated word keeps the clock
    of the word it was; the ad break the model dropped takes its clocks with it."""
    transcript = Transcript(
        provider="test",
        language="he",
        duration=8.0,
        words=heard("שלום לכם היום נדבר על חורף"),
    )
    written = "שלום לכם.\n\nהיום נדבר על חורף."
    refined = AnthropicRefiner()._mapped(transcript, list(transcript.words), written)
    assert [p.text for p in refined.paragraphs] == ["שלום לכם.", "היום נדבר על חורף."]
    first = refined.paragraphs[0].words
    assert first[0].start == 0.0
    assert first[1].start == 1.0
    second = refined.paragraphs[1].words
    assert second[0].start == 2.0  # "היום" keeps its own clock across the break


def test_a_word_the_model_invented_borrows_its_neighbours_clock() -> None:
    transcript = Transcript(
        provider="test", language="he", duration=3.0, words=heard("אחת שתיים שלוש")
    )
    refined = AnthropicRefiner()._mapped(transcript, list(transcript.words), "אחת בערך שתיים שלוש")
    words = refined.paragraphs[0].words
    assert words[0].start == 0.0
    invented = words[1]
    assert invented.text == "בערך"
    assert invented.start == words[0].end  # borrowed, not guessed
    assert invented.confidence < 1.0


def test_dropped_advertising_takes_its_clocks_with_it() -> None:
    transcript = Transcript(
        provider="test",
        language="he",
        duration=6.0,
        words=heard("תוכן אמיתי פרסומת ארוכה כאן חוזרים לתוכן"),
    )
    refined = AnthropicRefiner()._mapped(
        transcript, list(transcript.words), "תוכן אמיתי\n\nחוזרים לתוכן"
    )
    assert [p.text for p in refined.paragraphs] == ["תוכן אמיתי", "חוזרים לתוכן"]
    assert refined.paragraphs[1].words[0].start == 5.0


def test_a_replaced_refiner_redoes_its_half_without_paying_to_hear_again(
    fake_audio, tmp_path, monkeypatch
) -> None:
    """The transcript is cached; a better refiner's arrival re-reads it for nothing
    and rewrites only the refinement — the seam the moat is built on."""

    from targum.pipeline import Build
    from targum.transcribe.null import NullTranscriber

    class Splits:
        name = "fake/1"

        def split(self, texts: list[str], language: str) -> list[list[str]]:
            return [[t] for t in texts]

    fake_audio.duration = 600.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")

    def build() -> Build:
        return Build(
            str(source),
            target_language="en",
            source_language="en",
            provider_name="null",
            segmenter=Splits(),
            transcriber=NullTranscriber(text="one two three", language="en"),
            out_root=tmp_path / "out",
        )

    first = build()
    first.run()
    folder = first.resolved_out
    refined = folder / "audio" / "refined" / "part-001.json"
    import json

    assert json.loads(refined.read_text())["refiner"] == "rules/3"

    monkeypatch.setenv("TARGUM_REFINER", "none")  # the null refiner stands in for a new one
    second = build()
    second.run()
    assert json.loads(refined.read_text())["refiner"] == "none"
    # Nothing was heard twice: the transcript came from the cache.
    assert second.spent.seconds_by_model.get("null", 0.0) == 0.0


# -- punctuation -------------------------------------------------------------------------

#: What whisper-1 made of the opening of a Hebrew talk (2026-09-15): not one mark.
UNMARKED = (
    "היום אני אשתדל לא להתלהב יותר מידי כי אני נמצא במסגד מאוד מאוד פנסי "
    "אבל יכול להיות שאני אתלהב והכל שלי יעלה המוסד הזה הוא אחד המוסדות הדתיים "
    "הכי חשובים באסלאם הסוני כבר יותר מאלף שנים"
)

#: What claude-sonnet-5 answered for it, abridged: marks, a paragraph, and every word.
MARKED = (
    "היום אני אשתדל לא להתלהב יותר מידי, כי אני נמצא במסגד מאוד מאוד פנסי. "
    "אבל יכול להיות שאני אתלהב והכל שלי יעלה.\n\nהמוסד הזה הוא אחד המוסדות הדתיים "
    "הכי חשובים באסלאם הסוני כבר יותר מאלף שנים."
)


def stub(answer: str) -> tuple[list[str], object]:
    asked: list[str] = []

    def ask(prompt: str) -> tuple[str, int, int]:
        asked.append(prompt)
        return answer, 100, 90

    return asked, ask


def test_a_transcript_heard_without_marks_is_told_from_one_that_has_them() -> None:
    from targum.transcribe.refine.punctuate import needs_punctuation

    assert needs_punctuation(heard(UNMARKED))
    assert not needs_punctuation(heard(MARKED.replace("\n\n", " ")))
    assert not needs_punctuation(heard("שלום לכם")), "too short to need a full stop"


def test_punctuation_adds_marks_and_never_changes_a_word() -> None:
    """The model may be asked for marks; it is not trusted to have given only marks."""
    from targum.transcribe.refine.punctuate import transfer

    spoken = "אלום הנבואות האלו כבר קראו".split() + UNMARKED.split()
    # It corrected a misheard word, added one, and punctuated the rest.
    marked, opens = transfer(spoken, "אילו הנבואות, האלו כבר באמת קראו? " + UNMARKED)
    assert marked == {1: "הנבואות,", 4: "קראו?"}
    assert 0 not in marked, "a word the model corrected keeps the heard spelling"
    assert opens == set()


def test_a_mark_that_is_part_of_a_word_is_not_taken_as_punctuation() -> None:
    from targum.transcribe.refine.punctuate import transfer

    marked, _ = transfer("אמר ד ר כהן".split() + UNMARKED.split(), 'אמר ד"ר, כהן. ' + UNMARKED)
    assert marked == {3: "כהן."}


def test_an_answer_that_is_not_the_transcript_gives_no_marks() -> None:
    from targum.transcribe.refine.punctuate import transfer

    marked, opens = transfer(UNMARKED.split(), "זה סיכום קצר של ההרצאה.\n\nותו לא.")
    assert (marked, opens) == ({}, set())


def test_the_rules_punctuate_a_bare_hearing_and_every_clock_stands() -> None:
    from targum.transcribe.refine.punctuate import Punctuator

    asked, ask = stub(MARKED)
    words = heard(UNMARKED, step=0.5)
    refiner = RuleRefiner(Punctuator(ask=ask))  # type: ignore[arg-type]
    refined = refiner.refine(Transcript(provider="openai/whisper-1", language="he", words=words))

    assert refined.refiner == "rules/3+punctuate/1"
    assert len(asked) == 1 and "Hebrew" in asked[0]
    assert [p.text for p in refined.paragraphs] == MARKED.split("\n\n")
    kept = [word for p in refined.paragraphs for word in p.words]
    assert [(w.start, w.end) for w in kept] == [(w.start, w.end) for w in words]
    assert refiner.spent.calls == 1


def test_a_punctuated_hearing_is_left_as_it_came_and_costs_nothing() -> None:
    from targum.transcribe.refine.punctuate import Punctuator

    asked, ask = stub("")
    RuleRefiner(Punctuator(ask=ask)).refine(  # type: ignore[arg-type]
        Transcript(provider="elevenlabs/scribe_v2", language="he", words=heard(MARKED))
    )
    assert asked == []


def test_in_punctuated_speech_a_breath_mid_sentence_is_not_a_paragraph() -> None:
    words = heard("זה משפט אחד שלם. והנה משפט שני שנמשך", step=0.5)
    for later in words[6:]:  # a long pause after "שני", mid-sentence
        later.start += 2.0
        later.end += 2.0
    refined = RuleRefiner().refine(Transcript(provider="test", language="he", words=words))
    assert len(refined.paragraphs) == 1

    for later in words[4:]:  # and one after the full stop
        later.start += 2.0
        later.end += 2.0
    refined = RuleRefiner().refine(Transcript(provider="test", language="he", words=words))
    assert [p.text for p in refined.paragraphs] == ["זה משפט אחד שלם.", "והנה משפט שני שנמשך"]


def test_only_an_unpunctuated_part_is_redone_once_punctuation_can_be_bought() -> None:
    """A rules/2 part that reads is kept: redoing it moves a reader's place and buys its
    translation again. One that never stops is the text a learner could not read."""
    from targum.transcribe.models import Refined, RefinedParagraph
    from targum.transcribe.refine.punctuate import Punctuator

    def part(text: str, refiner: str = "rules/2") -> Refined:
        words = heard(text)
        return Refined(
            refiner=refiner,
            paragraphs=[RefinedParagraph(text=text, words=words)],
        )

    _, ask = stub("")
    buying = RuleRefiner(Punctuator(ask=ask))  # type: ignore[arg-type]
    assert not buying.keeps(part(UNMARKED)), "a bare hearing is redone"
    assert buying.keeps(part(MARKED)), "one that punctuates stands"
    assert buying.keeps(part(UNMARKED, "rules/3+punctuate/1"))
    assert not buying.keeps(part(MARKED, "none")), "a refiner that is not rules is redone"
    assert RuleRefiner().keeps(part(UNMARKED)), "without a key, nothing is redone"


def test_punctuating_an_old_part_buys_marks_and_never_the_hearing(
    fake_audio, tmp_path, monkeypatch
) -> None:
    from targum.pipeline import Build
    from targum.transcribe.null import NullTranscriber
    from targum.transcribe.refine.punctuate import Punctuator

    class Splits:
        name = "fake/1"

        def split(self, texts: list[str], language: str) -> list[list[str]]:
            return [[t] for t in texts]

    class Deaf(NullTranscriber):
        def transcribe(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("the part was heard again")

    fake_audio.duration = 600.0
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"audio")

    def build(transcriber: NullTranscriber) -> Build:
        return Build(
            str(source),
            target_language="en",
            source_language="he",
            provider_name="null",
            segmenter=Splits(),
            transcriber=transcriber,
            out_root=tmp_path / "out",
        )

    first = build(NullTranscriber(text=UNMARKED, language="he"))
    first.run()
    import json

    refined = first.resolved_out / "audio" / "refined" / "part-001.json"
    assert json.loads(refined.read_text())["refiner"] == "rules/3"
    # The cache is gone and the box names another transcriber: only the file beside the
    # part says what was heard.
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "elsewhere"))

    _, ask = stub(MARKED)
    monkeypatch.setattr(
        Build, "_refiner", lambda self: RuleRefiner(Punctuator(ask=ask))  # type: ignore[arg-type]
    )
    second = build(Deaf(text="", language="he"))
    second.run()
    written = json.loads(refined.read_text())
    assert written["refiner"] == "rules/3+punctuate/1"
    assert "פנסי." in written["paragraphs"][0]["text"]
    assert second.spent.calls >= 1, "the marks are on the receipt"
