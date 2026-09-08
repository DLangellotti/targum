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
