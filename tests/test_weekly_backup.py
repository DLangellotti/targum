"""The weekly is the one thing here that cannot be remade.

The cache can be re-bought and a reader rebuilt from it. An issue is what a model wrote
on a particular morning from feeds that have since moved on, and asking the same model
the same question tomorrow does not return it. Losing a week loses it permanently, which
is why this rides with the nightly copy rather than waiting to be thought of.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from targum.backup import archive_weekly, check_archive, restore_weekly


def make(root: Path, week: str = "2026-w36") -> Path:
    issue = root / week
    issue.mkdir(parents=True, exist_ok=True)
    (issue / f"weekly-{week}-bet.md").write_text("# השבוע\n\nטקסט.\n", encoding="utf-8")
    (issue / "brief.json").write_text(f'{{"week": "{week}"}}', encoding="utf-8")
    (root / "index.json").write_text('{"index_version": 1, "issues": []}', encoding="utf-8")
    # A built reader, which is not worth copying: it is rebuilt from the markdown free.
    built = root / f"weekly-{week}-bet-he" / "reader"
    built.mkdir(parents=True, exist_ok=True)
    (built / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return root


def test_nothing_yet_is_not_an_error(tmp_path: Path) -> None:
    assert archive_weekly(tmp_path / "absent", tmp_path / "into") is None
    (tmp_path / "empty").mkdir()
    assert archive_weekly(tmp_path / "empty", tmp_path / "into") is None


def test_the_composed_hebrew_and_the_index_are_kept(tmp_path: Path) -> None:
    root = make(tmp_path / "weekly")
    archive = archive_weekly(root, tmp_path / "into")
    assert archive is not None
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
    assert "index.json" in names
    assert "2026-w36/weekly-2026-w36-bet.md" in names
    assert "2026-w36/brief.json" in names, "what it was written from, for the audit"


def test_the_built_readers_are_left_out(tmp_path: Path) -> None:
    """They are rebuilt from the markdown for nothing, and copying them nightly would
    bury the kilobytes that actually matter."""
    root = make(tmp_path / "weekly")
    archive = archive_weekly(root, tmp_path / "into")
    assert archive is not None
    with zipfile.ZipFile(archive) as bundle:
        assert not [name for name in bundle.namelist() if "reader" in name]


def test_the_copy_is_checked_as_it_is_taken(tmp_path: Path) -> None:
    """A zip written while something was deleted underneath it is a zip that fails on
    the night it is needed."""
    archive = archive_weekly(make(tmp_path / "weekly"), tmp_path / "into")
    assert archive is not None
    assert check_archive(archive) == ""


def test_it_is_named_so_restore_can_tell_the_two_archives_apart(tmp_path: Path) -> None:
    archive = archive_weekly(make(tmp_path / "weekly"), tmp_path / "into")
    assert archive is not None
    assert archive.name.startswith("weekly-") and archive.suffix == ".zip"


def test_restoring_is_additive(tmp_path: Path) -> None:
    """An issue published since the copy was taken survives being restored onto — the
    same rule the cache follows, and for the same reason."""
    root = make(tmp_path / "weekly")
    archive = archive_weekly(root, tmp_path / "into")
    assert archive is not None

    later = root / "2026-w37"
    later.mkdir()
    (later / "weekly-2026-w37-bet.md").write_text("# מאוחר\n", encoding="utf-8")

    written = restore_weekly(archive, root)
    assert written
    assert (later / "weekly-2026-w37-bet.md").is_file(), "the newer issue was not wiped"
    assert (root / "2026-w36" / "weekly-2026-w36-bet.md").is_file()


def listed(root: Path) -> list[str]:
    loaded = json.loads((root / "index.json").read_text(encoding="utf-8"))
    return [one["id"] for one in loaded["issues"]]


def note(root: Path, *ids: str, state: str = "published") -> None:
    """Write an index listing these issues, which is what a real weekly has."""
    issues = [{"id": one, "state": state, "editions": []} for one in ids]
    (root / "index.json").write_text(
        json.dumps({"index_version": 1, "issues": issues}), encoding="utf-8"
    )


def test_a_week_published_since_the_copy_stays_in_the_index(tmp_path: Path) -> None:
    """The file surviving is not enough — an issue missing from the index is gone.

    The index is the only member of the archive that is a list rather than one issue's
    own file, so unpacking it plainly would replace what is standing with what was true
    on the night of the copy. This is the failure the archive exists to prevent, arriving
    during the restore meant to prevent it.
    """
    root = make(tmp_path / "weekly")
    note(root, "2026-w36")
    archive = archive_weekly(root, tmp_path / "into")
    assert archive is not None

    note(root, "2026-w36", "2026-w40")
    restore_weekly(archive, root)
    assert listed(root) == ["2026-w36", "2026-w40"], "the newer week fell out of the index"


def test_a_withdrawn_issue_is_not_put_back_on_sale(tmp_path: Path) -> None:
    """What is standing wins a tie: it is the more recent account of the same issue."""
    root = make(tmp_path / "weekly")
    note(root, "2026-w36")
    archive = archive_weekly(root, tmp_path / "into")
    assert archive is not None

    note(root, "2026-w36", state="withdrawn")
    restore_weekly(archive, root)
    loaded = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert loaded["issues"][0]["state"] == "withdrawn"


def test_a_total_loss_takes_the_index_from_the_archive(tmp_path: Path) -> None:
    """Nothing standing, so there is nothing to merge and the copy is the whole truth."""
    root = make(tmp_path / "weekly")
    note(root, "2026-w36")
    archive = archive_weekly(root, tmp_path / "into")
    assert archive is not None

    shutil.rmtree(root)
    restore_weekly(archive, root)
    assert listed(root) == ["2026-w36"]


def test_an_unreadable_index_does_not_veto_the_archive(tmp_path: Path) -> None:
    """An index nobody can parse is what somebody is restoring to get away from."""
    root = make(tmp_path / "weekly")
    note(root, "2026-w36")
    archive = archive_weekly(root, tmp_path / "into")
    assert archive is not None

    (root / "index.json").write_text("{ this is not json", encoding="utf-8")
    restore_weekly(archive, root)
    assert listed(root) == ["2026-w36"]


def test_a_broken_archive_is_refused_rather_than_half_unpacked(tmp_path: Path) -> None:
    bad = tmp_path / "weekly-2026.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ValueError, match="not usable"):
        restore_weekly(bad, tmp_path / "weekly")
