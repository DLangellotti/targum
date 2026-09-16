"""How long a build takes, counted rather than guessed (targum-internal#303).

The Add card has always said "Ready in about four minutes". It worked that out from two
constants nobody had ever checked against a clock — a segment takes a twenty-fifth of a
minute, audio runs at six times real time — because until `job.finished` existed there
was no clock to check them against.

What is under test is mostly the refusal: a box that has not finished enough builds says
nothing, and the card falls back to the old guess rather than quoting a middle drawn
from three rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.accounts import Store

MINUTE = 60 * 1000


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def finished(store: Store, n: int, took_ms: int, **extra: object) -> None:
    """`n` builds that each took `took_ms`, made far enough apart to order."""
    for i in range(n):
        made = 1_000_000 + i * 10_000
        fields: dict[str, object] = {
            "id": f"job-{extra.get('tag', 'x')}-{i}",
            "owner": 1,
            "home": "/tmp",
            "source": "test",
            "stage": "done",
            "kind": "build",
            "language": "he",
            "length": 0,
            "made": made,
            "finished": made + took_ms,
        }
        fields.update({k: v for k, v in extra.items() if k != "tag"})
        store.save_job(fields)


def test_nothing_is_quoted_until_enough_have_finished(store: Store) -> None:
    """Three builds are an anecdote, not a rate."""
    finished(store, Store.ENOUGH_TO_QUOTE - 1, 4 * MINUTE)
    assert store.how_long_builds_take() == 0.0
    finished(store, Store.ENOUGH_TO_QUOTE, 4 * MINUTE, tag="more")
    assert store.how_long_builds_take() == pytest.approx(4 * 60)


def test_the_middle_and_not_the_mean(store: Store) -> None:
    """One build stuck behind an annotator rename must not move everybody's estimate."""
    finished(store, Store.ENOUGH_TO_QUOTE, 2 * MINUTE)
    store.save_job(
        {
            "id": "the-slow-one",
            "owner": 1,
            "home": "/tmp",
            "source": "test",
            "stage": "done",
            "kind": "build",
            "language": "he",
            "length": 0,
            "made": 2_000_000,
            "finished": 2_000_000 + 120 * MINUTE,
        }
    )
    # The mean of these is over nine minutes; the middle is still two.
    assert store.how_long_builds_take() == pytest.approx(2 * 60)


def test_rows_from_before_the_column_are_not_instant_builds(store: Store) -> None:
    """A zero in `finished` means "not recorded", never "took no time"."""
    for i in range(50):
        store.save_job(
            {
                "id": f"old-{i}",
                "owner": 1,
                "home": "/tmp",
                "source": "test",
                "stage": "done",
                "kind": "build",
                "language": "he",
                "length": 0,
                "made": 1_000_000 + i,
                "finished": 0,
            }
        )
    assert store.how_long_builds_take() == 0.0


def test_audio_and_text_are_counted_apart(store: Store) -> None:
    """The one division that changes the answer by an order of magnitude."""
    finished(store, Store.ENOUGH_TO_QUOTE, 2 * MINUTE, tag="text", length=0)
    finished(store, Store.ENOUGH_TO_QUOTE, 30 * MINUTE, tag="audio", length=3600)
    assert store.how_long_builds_take(audio=False) == pytest.approx(2 * 60)
    assert store.how_long_builds_take(audio=True) == pytest.approx(30 * 60)


def test_a_language_with_no_history_of_its_own_says_nothing(store: Store) -> None:
    finished(store, Store.ENOUGH_TO_QUOTE, 2 * MINUTE)
    assert store.how_long_builds_take(language="he") == pytest.approx(2 * 60)
    assert store.how_long_builds_take(language="ru") == 0.0


def test_a_build_that_failed_is_not_how_long_one_takes(store: Store) -> None:
    """A build that fell over in ten seconds is not evidence that builds are quick."""
    finished(store, Store.ENOUGH_TO_QUOTE, 4 * MINUTE)
    for i in range(40):
        store.save_job(
            {
                "id": f"failed-{i}",
                "owner": 1,
                "home": "/tmp",
                "source": "test",
                "stage": "failed",
                "kind": "build",
                "language": "he",
                "length": 0,
                "made": 3_000_000 + i,
                "finished": 3_000_000 + i + 10_000,
            }
        )
    assert store.how_long_builds_take() == pytest.approx(4 * 60)


def test_a_clock_that_went_backwards_is_ignored(store: Store) -> None:
    """`finished` before `made` is a wrong row, not a build that took negative time."""
    finished(store, Store.ENOUGH_TO_QUOTE, 4 * MINUTE)
    store.save_job(
        {
            "id": "backwards",
            "owner": 1,
            "home": "/tmp",
            "source": "test",
            "stage": "done",
            "kind": "build",
            "language": "he",
            "length": 0,
            "made": 5_000_000,
            "finished": 4_000_000,
        }
    )
    assert store.how_long_builds_take() == pytest.approx(4 * 60)


def test_a_turn_of_conversation_is_not_a_build(store: Store) -> None:
    finished(store, Store.ENOUGH_TO_QUOTE, 4 * MINUTE)
    finished(store, 40, 2_000, tag="chat", kind="chat")
    assert store.how_long_builds_take() == pytest.approx(4 * 60)
