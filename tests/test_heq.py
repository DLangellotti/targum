"""HeQ as the reference for the chat's answers about a text: fetched plainly, read on
SQuAD's shape, and scored on the span (targum-internal#223)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from targum.chat import heq
from targum.errors import TargumError


def a_file() -> str:
    return json.dumps(
        {
            "version": "v1.1",
            "data": [
                {
                    "title": "רבי שמעון בר יוחאי",
                    "source": "Wikipedia",
                    "paragraphs": [
                        {
                            "context": 'התחבאו רשב"י ובנו רבי אלעזר 12 שנים במערה. ',
                            "qas": [
                                {
                                    "question": "מיהו בנו של רשב״י?",
                                    "id": "q1",
                                    "answers": [
                                        {"text": "רבי אלעזר", "answer_start": 20},
                                        {"text": "רבי אלעזר ", "answer_start": 20},
                                        {"text": "אלעזר", "answer_start": 24},
                                    ],
                                    "is_impossible": False,
                                },
                                {
                                    "question": "כמה שנים?",
                                    "id": "q2",
                                    "answers": [{"text": "12", "answer_start": 30}],
                                    "is_impossible": True,
                                },
                            ],
                        }
                    ],
                }
            ],
        },
        ensure_ascii=False,
    )


def test_the_file_is_read_on_squads_shape_with_every_accepted_span() -> None:
    first, second = heq.parse(a_file())
    assert first.id == "q1" and first.source == "Wikipedia"
    assert first.title == "רבי שמעון בר יוחאי"
    assert first.context == 'התחבאו רשב"י ובנו רבי אלעזר 12 שנים במערה.'
    assert first.answers == ("רבי אלעזר", "אלעזר"), "stripped, deduplicated, main span first"
    assert first.answerable
    assert not second.answerable, "an unanswerable question keeps no span"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(heq, "root", lambda: tmp_path / "gold")
    return tmp_path / "gold"


class Answer:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_the_fetch_takes_val_and_test_plainly_and_is_idempotent(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def get(url: str, **kwargs: object) -> Answer:
        asked.append(url)
        assert "headers" not in kwargs, "HeQ is not gated: no token travels"
        return Answer(a_file())

    monkeypatch.setattr("httpx.get", get)
    assert heq.fetch() == 2
    assert [url.rsplit("/", 1)[1] for url in asked] == ["val%20v1.1.json", "test%20v1.1.json"]
    assert heq.available(heq.SPLITS)
    assert heq.fetch() == 2 and len(asked) == 2, "files already here are left alone"


def test_loading_keeps_the_answerable_questions_unless_asked_otherwise(home: Path) -> None:
    home.mkdir()
    (home / "heq-test.json").write_text(a_file(), encoding="utf-8")
    assert [one.id for one in heq.load()] == ["q1"]
    assert [one.id for one in heq.load(answerable=False)] == ["q1", "q2"]


def test_loading_before_fetching_names_the_command(home: Path) -> None:
    with pytest.raises(TargumError) as refused:
        heq.load()
    assert refused.value.hint == "Run: targum models fetch heq"


def test_a_split_that_does_not_exist_is_refused_by_name(home: Path) -> None:
    with pytest.raises(TargumError, match="No such HeQ split"):
        heq.fetch(splits=("dev",))


@pytest.fixture(scope="module")
def eval_ask():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "eval_ask", Path(__file__).parent.parent / "scripts" / "eval_ask.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_span_is_found_through_points_and_punctuation(eval_ask) -> None:  # type: ignore[no-untyped-def]
    """The reply is English about the text with the Hebrew quoted where it helps, and a
    learner's Hebrew comes pointed: the span is the same span with or without them."""
    answers = ("רבי אלעזר",)
    assert eval_ask.span_found("His son was רַבִּי אֶלְעָזָר, who hid with him.", answers)
    assert eval_ask.span_found('The text says "רבי אלעזר".', answers)
    assert not eval_ask.span_found("His son was אלעזר.", answers), "a part of the span is not it"
    assert not eval_ask.span_found("", answers)


def test_an_answer_in_latin_or_digits_can_be_found_at_all(eval_ask) -> None:  # type: ignore[no-untyped-def]
    """HeQ's answers are full of Latin names and bare numbers — Fiverr, Azure, 2018 —
    and a pattern that kept only Hebrew letters reduced every one of them to nothing.
    `span_found` then had no span to look for and answered False whatever the chat said:
    16 of the first 200 questions were scored a miss by construction
    (targum-internal#223, measured 2026-09-21)."""
    assert eval_ask.span_found("היא הופיעה בתוכנית Stream Elements.", ("Stream Elements",))
    assert eval_ask.span_found("בְּ-2018 — הטקסט אומר כך.", ("2018",))
    assert eval_ask.span_found("פיבר (Fiverr) הוא הסטארטאפ הרביעי.", ("Fiverr",))
    assert not eval_ask.span_found("היא הופיעה שם.", ("Stream Elements",))


def test_a_word_keeps_the_marks_inside_it_and_drops_the_ones_after(eval_ask) -> None:  # type: ignore[no-untyped-def]
    """Widening the pattern must not lose why it was narrow: HeQ keeps רשב"י as one
    word, and the same gershayim after the last letter is the sentence's quotation."""
    assert eval_ask.plain('רשב"י') == 'רשב"י'
    assert eval_ask.plain('אמר "שלום".') == "אמר שלום"
    assert eval_ask.plain("Stream Elements.") == "Stream Elements"


def test_the_ktiv_blind_comparison_reads_the_two_spellings_as_one(eval_ask) -> None:  # type: ignore[no-untyped-def]
    """HeQ's spans are ktiv male and the chat answers in pointed Hebrew, which is ktiv
    haser once the points come off — so the same word reaches the comparison spelled two
    ways. Measured over 200 questions on 2026-09-21: 157 strict, 179 ktiv-blind."""
    assert not eval_ask.span_found("הַתַּהֲלִיךְ נִקְרָא הַבְּרֵרָה הַטִּבְעִית.", ("הברירה הטבעית",))
    assert eval_ask.span_found_ktiv("הַתַּהֲלִיךְ נִקְרָא הַבְּרֵרָה הַטִּבְעִית.", ("הברירה הטבעית",))
    assert eval_ask.span_found_ktiv("הטקסט אומר שכיהן כרבה של ליפניק.", ("לייפניק",)), (
        "a doubled yod"
    )
    assert eval_ask.span_found_ktiv("פריסקופ שייך לטויטר, כלומר טויטר.", ("טוויטר",))
    # …but only where the bare word is there: a prefix is a letter this rule keeps, so
    # "בליפניק" alone does not answer "לייפניק". Both of the replies above really do
    # carry the bare form further along, which is why they counted.
    assert not eval_ask.span_found_ktiv("הוא כיהן בליפניק.", ("לייפניק",))
    assert not eval_ask.span_found_ktiv("הוא ענה משהו אחר.", ("הברירה הטבעית",))
    assert not eval_ask.span_found_ktiv("", ("הברירה הטבעית",))


def test_the_loose_comparison_only_ever_adds(eval_ask) -> None:  # type: ignore[no-untyped-def]
    """Whatever the strict comparison accepts, the ktiv-blind one accepts too: it maps
    every word of both sides through the same function, so a sequence that matched still
    matches. The two numbers can therefore only be read one way round, and a run where
    the loose share came out below the strict one would mean the harness is broken."""
    cases = [
        ("רַבִּי אֶלְעָזָר הסתתר במערה.", ("רבי אלעזר",)),
        ("The text says Stream Elements.", ("Stream Elements",)),
        ("בְּ-2018 קרה הדבר.", ("2018",)),
        ("הַתַּהֲלִיךְ נִקְרָא הַבְּרֵרָה הַטִּבְעִית.", ("הברירה הטבעית",)),
        ("הוא ענה משהו אחר לגמרי.", ("הברירה הטבעית",)),
    ]
    for reply, answers in cases:
        if eval_ask.span_found(reply, answers):
            assert eval_ask.span_found_ktiv(reply, answers), reply


def test_a_word_initial_vav_is_a_letter_and_is_never_dropped(eval_ask) -> None:  # type: ignore[no-untyped-def]
    """The rule is blind to a mater *inside* a word only. A vav or yod at the front is a
    consonant — most often the conjunction — and dropping it would make "and he wrote"
    and "he wrote" the same word, which is the whole hazard of loosening the match."""
    assert eval_ask.ktiv("וכתב") == "וכתב"
    assert eval_ask.ktiv("כתב") == "כתב"
    assert eval_ask.ktiv("וכתב") != eval_ask.ktiv("כתב")
    assert eval_ask.ktiv("אומר") == "אמר"
    assert eval_ask.ktiv("") == ""
    assert not eval_ask.span_found_ktiv("וכתב את הספר.", ("כתב את הספר",))


def test_token_f1_is_squads_over_the_hebrew_words_and_the_best_span(eval_ask) -> None:  # type: ignore[no-untyped-def]
    answers = ("רבי אלעזר", "אלעזר")
    assert eval_ask.token_f1("רבי אלעזר", answers) == 1.0
    assert eval_ask.token_f1("The son, אלעזר, hid too.", answers) == 1.0, "the best span wins"
    assert eval_ask.token_f1("ובנו רבי אלעזר במערה", answers) == pytest.approx(2 * 0.5 * 1 / 1.5)
    assert eval_ask.token_f1("He hid in a cave.", answers) == 0.0
    assert eval_ask.token_f1("במערה", ()) == 0.0


def test_the_turn_is_framed_the_way_the_page_frames_it(eval_ask) -> None:  # type: ignore[no-untyped-def]
    """The eval measures the Ask path, so it composes the note `session.framed` composes:
    the article is the text, the paragraph is the sentence, and the question is theirs."""
    from targum.chat.session import framed

    one = heq.Question("q1", "Wikipedia", "כותרת", "פסקה.", "שאלה?", ("תשובה",))
    seen: dict[str, object] = {}

    class Client:
        class messages:  # noqa: N801 - the SDK's own shape
            @staticmethod
            def create(**kwargs: object) -> object:
                seen.update(kwargs)

                class Reply:
                    content = [type("Block", (), {"text": "The answer is תשובה."})()]
                    usage = type("Usage", (), {"input_tokens": 10, "output_tokens": 5})()

                return Reply()

    from targum.usage import Usage

    got = eval_ask.ask(Client(), [{"type": "text", "text": "system"}], one, Usage())
    assert got == "The answer is תשובה."
    assert seen["messages"] == [
        {"role": "user", "content": framed("שאלה?", {"document": "כותרת", "sentence": "פסקה."})}
    ]
    assert "The reader is reading the text כותרת." in str(seen["messages"])
