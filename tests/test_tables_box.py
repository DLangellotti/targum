"""The language tables on the box: the nightly sweep's unit, the guard that keeps a model
out of it, and the laptop's rows carried over by an import that is safe to run twice
(targum-internal#587).

There is no way to run a timer without a box, so the unit is read as text. Every row
here is synthetic: placeholder lemmas, no sentence of any text, no reader.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import tables
from targum.cli import app
from targum.tables.store import Contribution, Store

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
H = {name: name * 64 for name in "abcdef"}


def _unit(name: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for line in (DEPLOY / name).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), []).append(value.strip())
    return fields


# -- the unit ---------------------------------------------------------------------------


def test_the_sweep_runs_nightly_as_targum_with_the_ledger_and_a_low_priority() -> None:
    timer = _unit("targum-tables.timer")
    assert timer["OnCalendar"] == ["*-*-* 02:30:00 UTC"], "a quiet hour, before the backup"
    assert timer["Persistent"] == ["true"]
    backup = _unit("targum-backup.timer")["OnCalendar"][0]
    assert backup > timer["OnCalendar"][0], "the night's rows are in the night's backup"
    service = _unit("targum-tables.service")
    assert service["ExecStart"] == [
        # The account database says whose material the imports pool may read (2026-11-01).
        "/usr/local/bin/targum tables sweep --library /var/lib/targum/targums"
        " --store /var/lib/targum/targum.db",
        # The yardsticks after it, once a month by their own rule (targum-internal#579).
        "/usr/local/bin/targum tables snapshot --out /var/lib/targum/tables",
    ]
    assert service["User"] == ["targum"] and service["Group"] == ["targum"], "never root"
    assert service["EnvironmentFile"] == ["/etc/targum/targum.env"], "TARGUM_LEDGER is there"
    assert service["Type"] == ["oneshot"]
    assert service["Nice"] == ["19"]
    assert service["IOSchedulingClass"] == ["idle"]
    assert service["CPUSchedulingPolicy"] == ["idle"]
    assert service["ReadWritePaths"] == ["/var/lib/targum"]


def test_the_sweep_has_a_memory_cap_of_its_own() -> None:
    service = _unit("targum-tables.service")
    assert service["MemoryMax"] == ["1G"]
    assert service["MemoryHigh"] == ["600M"], "throttled before it is killed"
    assert service["MemorySwapMax"] == ["0"], "and it cannot crowd the service into swap"
    assert "MemoryMax" not in _unit("targum.service"), "the cap is the sweep's, not the server's"


def test_every_deploy_carries_and_enables_the_timer() -> None:
    script = (DEPLOY / "deploy.sh").read_text(encoding="utf-8")
    assert "deploy/targum-tables.service deploy/targum-tables.timer" in script, "copied"
    loop = next(line for line in script.splitlines() if line.strip().startswith("for unit in"))
    assert "targum-tables.service targum-tables.timer" in loop, "installed"
    enable = next(line for line in script.splitlines() if "systemctl enable --now --quiet" in line)
    assert "targum-tables.timer" in enable, "and enabled"


def test_restore_says_the_ledger_holds_what_no_cache_does() -> None:
    page = (DEPLOY / "RESTORE.md").read_text(encoding="utf-8")
    assert "#587" in page and "external backfills" in page


# -- no model ---------------------------------------------------------------------------


def test_the_guard_refuses_a_model_package() -> None:
    gone = {name: sys.modules.pop(name) for name in list(sys.modules) if name == "stanza"}
    try:
        with tables.no_models(), pytest.raises(ImportError, match="never runs one"):
            __import__("stanza")
    finally:
        sys.modules.update(gone)
    assert not any(isinstance(f, tables._NoModels) for f in sys.meta_path), "and lets go"


def _built(folder: Path, document_hash: str) -> None:
    folder.mkdir(parents=True)
    document = {"content_hash": document_hash, "source": f"test:{document_hash[:4]}"}
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    token = {"start": 0, "end": 1, "surface": "w1", "lemma": "w1", "pos": "NOUN", "band": 1}
    annotation = {
        "schema_version": 1,
        "document_hash": document_hash,
        "language": "he",
        "annotator": "dicta/test/1",
        "tokens": {"s0": [token, {**token, "lemma": "w2", "surface": "w2"}]},
    }
    (folder / "annotation.json").write_text(json.dumps(annotation), encoding="utf-8")


def test_a_sweep_in_a_fresh_process_imports_no_model(tmp_path: Path) -> None:
    """What the timer starts: a fresh `targum tables sweep`. Nothing it reaches may be a
    model package, so the guard has nothing to refuse."""
    library = tmp_path / "library"
    _built(library / "shared" / "x", H["a"])
    probe = (
        "import sys\n"
        "from targum.cli import app\n"
        "try:\n"
        f"    app(['tables', 'sweep', '--library', {str(library)!r}])\n"
        "except SystemExit as stop:\n"
        "    assert not stop.code, stop.code\n"
        "heavy = sorted(m for m in sys.modules if m.split('.')[0] in"
        " __import__('targum.tables', fromlist=['x']).MODEL_PACKAGES)\n"
        "print('HEAVY', heavy)\n"
    )
    env = {"TARGUM_LEDGER": str(tmp_path / "corpus.db"), "PATH": "/usr/bin:/bin"}
    env.update({key: os.environ[key] for key in ("PYTHONPATH", "HOME") if key in os.environ})
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "Counted 1 texts" in done.stdout
    assert "HEAVY []" in done.stdout


def test_a_pooling_sweep_in_a_fresh_process_imports_no_model(tmp_path: Path) -> None:
    """The same, with the imports pool on (2026-11-01): reading readers' homes, and the
    account database for whose, reaches no model package either."""
    library = tmp_path / "library"
    _built(library / "p1" / "x", H["a"])
    probe = (
        "import sys\n"
        "from targum.cli import app\n"
        "try:\n"
        f"    app(['tables', 'sweep', '--library', {str(library)!r},"
        f" '--store', {str(tmp_path / 'targum.db')!r}])\n"
        "except SystemExit as stop:\n"
        "    assert not stop.code, stop.code\n"
        "heavy = sorted(m for m in sys.modules if m.split('.')[0] in"
        " __import__('targum.tables', fromlist=['x']).MODEL_PACKAGES)\n"
        "print('HEAVY', heavy)\n"
    )
    env = {
        "TARGUM_LEDGER": str(tmp_path / "corpus.db"),
        "TARGUM_IMPORT_COUNTS": "1",
        "PATH": "/usr/bin:/bin",
    }
    env.update({key: os.environ[key] for key in ("PYTHONPATH", "HOME") if key in os.environ})
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env, check=False
    )
    assert done.returncode == 0, done.stderr
    assert "Pooled 0 texts from 0 readers, 1 left out" in done.stdout
    assert "HEAVY []" in done.stdout


# -- the laptop's rows ------------------------------------------------------------------


def _contribution(unit: str, tool: str = "dicta/test/1") -> Contribution:
    return Contribution(
        table="words",
        register="modern",
        unit=unit,
        source=f"test:{unit[:4]}",
        licence="CC BY 4.0",
        tool=tool,
        rule="words/1",
    )


@pytest.fixture
def laptop(tmp_path: Path) -> Store:
    store = Store(tmp_path / "laptop" / "corpus.db")
    store.file.parent.mkdir()
    store.write(_contribution(H["a"]), {("w1", "NOUN"): 3, ("w2", "VERB"): 1})
    store.write(_contribution(H["b"]), {("w1", "NOUN"): 2})
    # A rename on the laptop: the old count stays as history.
    store.write(_contribution(H["b"], tool="dicta/test/2"), {("w1", "NOUN"): 5})
    return store


@pytest.fixture
def box(tmp_path: Path) -> Store:
    (tmp_path / "box").mkdir()
    return Store(tmp_path / "box" / "corpus.db")


def _dump(file: Path) -> list[tuple[Any, ...]]:
    with sqlite3.connect(file) as db:
        rows = db.execute("SELECT * FROM contribution ORDER BY id").fetchall()
        rows += db.execute("SELECT * FROM tally ORDER BY contribution_id, key").fetchall()
    return rows


def test_the_laptop_is_the_laptop(laptop: Store) -> None:
    assert laptop.origin() == "laptop", "so its rows are the ones a push carries"


def test_a_push_run_twice_changes_nothing(laptop: Store, box: Store) -> None:
    lines = list(laptop.export("laptop"))
    assert len(lines) == 3, "current and superseded alike"
    first = box.import_rows(lines)
    assert (first.added, first.history, first.unchanged, first.refused) == (2, 1, 0, 0)
    assert box.total("words") == laptop.total("words") == 3 + 1 + 5
    before = _dump(box.file)
    again = box.import_rows(lines)
    assert (again.added, again.history, again.unchanged, again.refused) == (0, 0, 3, 0)
    assert _dump(box.file) == before, "not one row moved"


def test_the_rows_arrive_as_the_laptop_wrote_them(laptop: Store, box: Store) -> None:
    box.import_rows(laptop.export("laptop"))
    with sqlite3.connect(box.file) as db:
        origins = {row[0] for row in db.execute("SELECT origin FROM contribution")}
    assert origins == {"laptop"}
    assert box.top("words", "modern") == laptop.top("words", "modern")


def test_the_newer_count_of_a_unit_wins_and_neither_counts_twice(laptop: Store, box: Store) -> None:
    # The box swept the same text under an older name before the push arrived.
    box.write(_contribution(H["a"], tool="dicta/test/0"), {("w1", "NOUN"): 100})
    with sqlite3.connect(box.file) as db:
        db.execute("UPDATE contribution SET written_at = '2000-01-01T00:00:00+00:00'")
    box.import_rows(laptop.export("laptop"))
    assert box.total("words") == 9, "the laptop's newer count replaced the box's"

    # And the other way: the box's own count is newer than what the laptop sends.
    other = Store(box.file.parent / "other.db")
    other.write(_contribution(H["c"], tool="dicta/test/9"), {("w1", "NOUN"): 7})
    old = Store(laptop.file.parent / "old.db")
    old.write(_contribution(H["c"]), {("w1", "NOUN"): 1})
    with sqlite3.connect(old.file) as db:
        db.execute("UPDATE contribution SET written_at = '2000-01-01T00:00:00+00:00'")
    result = other.import_rows(old.export("laptop"))
    assert (result.added, result.history) == (0, 1)
    assert other.total("words") == 7, "kept as history, not counted"


def test_the_box_refuses_its_own_rows_a_private_unit_and_a_broken_line(
    laptop: Store, box: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines = list(laptop.export("laptop"))
    public = next(line for line in lines if json.loads(line)["contribution"]["unit"] == H["b"])
    forged = json.loads(public)
    forged["contribution"]["origin"] = "box"
    forged["contribution"]["id"] = "f" * 64
    doubled = json.loads(public)
    doubled["contribution"]["id"] = "e" * 64
    doubled["tally"].append(doubled["tally"][0])
    monkeypatch.setattr(
        "targum.ledger.Ledger.is_private", lambda self, document_hash: document_hash == H["a"]
    )
    result = box.import_rows([json.dumps(forged), json.dumps(doubled), "{not json", *lines])
    assert result.refused == 4, "forged, doubled, broken, and the private unit's own row"
    assert box.total("words") == 5, "only the public unit's current count"


def test_the_cli_round_trip_is_idempotent(laptop: Store, box: Store, tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "rows.jsonl"
    exported = runner.invoke(
        app, ["tables", "export", "--out", str(out)], env={"TARGUM_LEDGER": str(laptop.file)}
    )
    assert exported.exit_code == 0, exported.output
    said = []
    for _ in range(2):
        done = runner.invoke(app, ["tables", "import", str(out), "--ledger", str(box.file)])
        assert done.exit_code == 0, done.output
        said.append(" ".join(done.output.split()))
    assert "Imported 2 contributions, 1 as history, 0 already here, 0 refused" in said[0]
    assert "Imported 0 contributions, 0 as history, 3 already here, 0 refused" in said[1]


def test_push_imports_over_ssh_as_targum(
    laptop: Store, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}

    def run(command: list[str], *, stdin: Any, check: bool) -> subprocess.CompletedProcess[str]:
        seen["command"] = command
        seen["lines"] = stdin.read().splitlines()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    done = CliRunner().invoke(
        app,
        ["tables", "push", "--host", "root@box.example"],
        env={"TARGUM_LEDGER": str(laptop.file)},
    )
    assert done.exit_code == 0, done.output
    ssh, *_, remote = seen["command"]
    assert ssh == "ssh" and "root@box.example" in seen["command"]
    assert remote.startswith("sudo -u targum /usr/local/bin/targum tables import"), "not root"
    assert "--ledger /var/lib/targum/corpus.db -" in remote
    assert len(seen["lines"]) == 3
