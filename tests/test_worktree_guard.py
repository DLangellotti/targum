"""The guard that stops a worktree testing the main checkout (targum-internal#181).

A guard with no test of its own is a guard that can stop guarding without anybody
noticing, which is the same shape as the bug it is here to catch.
"""

from __future__ import annotations

from pathlib import Path

import conftest
import pytest


def test_the_run_that_is_happening_now_passes_its_own_guard() -> None:
    """Whatever tree this is, the package came out of it — or pytest would have refused
    to start and none of this would be running."""
    conftest._the_package_under_test_is_this_checkout()


def test_a_package_from_another_tree_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The silent version of this cost about six rounds of debugging on targum#76: an
    edit to `reader.js` looked like dead code, and every observation about it was true
    of the file the browser had actually loaded. Loud now, and it says which two trees."""
    monkeypatch.setattr(conftest, "CHECKOUT", Path("/nowhere/near/here"))
    monkeypatch.delenv(conftest.ANY_PACKAGE, raising=False)

    with pytest.raises(pytest.UsageError) as refused:
        conftest._the_package_under_test_is_this_checkout()

    said = str(refused.value)
    assert "/nowhere/near/here" in said, "it names the tree the tests are in"
    assert "targum" in said, "and the one the package came from"
    # And what to type. A message that says only that something is wrong is the failure
    # this replaces, which pointed at the change rather than at the run.
    assert "PYTHONPATH=" in said and "-m pytest" in said


def test_it_can_be_overruled_on_purpose(monkeypatch: pytest.MonkeyPatch) -> None:
    """A loud wrong answer to argue with, not a wall to take apart. Nothing in the
    repository sets this; it is here for the run nobody has thought of yet."""
    monkeypatch.setattr(conftest, "CHECKOUT", Path("/nowhere/near/here"))
    monkeypatch.setenv(conftest.ANY_PACKAGE, "1")
    conftest._the_package_under_test_is_this_checkout()


def test_the_guard_runs_before_any_test_does() -> None:
    """It is wired into `pytest_configure` rather than into a fixture, because a fixture
    fires after collection — and collection is when a browser test has already been
    built against the wrong `src/targum/render/assets/`."""
    import inspect

    source = inspect.getsource(conftest.pytest_configure)
    assert "_the_package_under_test_is_this_checkout()" in source
