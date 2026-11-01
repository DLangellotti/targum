"""The ship scripts write into targum's tree as targum, never as root (targum-internal#515).

`/var/lib/targum/...` belongs to the service, so anything in it, a symlink included, may
have been put there by the service, and a root rsync, mv, rm or `chown -R` following one
writes or hands over whatever it points at; a symlinked parent redirects a root command
the same way. deploy.sh closed this for the covers in targum#889 (targum-internal#512),
and these five scripts follow it: the receiving rsync is started as targum
(`--rsync-path`), the remote mkdir, mv and rm run as targum, and no root chown follows.

Text tests, since running a ship needs the box: each command that reaches the box is
read out of the script and checked for who runs it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
SCRIPTS = ["ship-parasha.sh", "ship-daily.sh", "ship-weekly.sh", "ship-shared.sh", "ship-audio.sh"]
AS_TARGUM = 'AS_TARGUM="runuser -u targum --"'
RSYNC_PATH = '--rsync-path="$AS_TARGUM rsync"'


def code(name: str) -> list[str]:
    """The script's lines with comments dropped, continuations joined."""
    text = (DEPLOY / name).read_text(encoding="utf-8").replace("\\\n", " ")
    return [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]


@pytest.mark.parametrize("name", SCRIPTS)
def test_it_parses(name: str) -> None:
    subprocess.run(["bash", "-n", str(DEPLOY / name)], check=True)


@pytest.mark.parametrize("name", SCRIPTS)
def test_no_root_chown_of_targum_s_tree(name: str) -> None:
    assert not [line for line in code(name) if "chown" in line]


@pytest.mark.parametrize("name", SCRIPTS)
def test_the_box_side_is_the_service_account(name: str) -> None:
    assert AS_TARGUM in code(name)


@pytest.mark.parametrize("name", SCRIPTS)
def test_every_rsync_to_the_box_is_received_as_targum(name: str) -> None:
    sends = [line for line in code(name) if re.match(r"\s*rsync\b", line) and "$HOST:" in line]
    assert sends, "the script sends nothing with rsync"
    for line in sends:
        assert RSYNC_PATH in line, line


@pytest.mark.parametrize("name", SCRIPTS)
def test_nothing_is_copied_into_targum_s_tree_by_scp(name: str) -> None:
    """scp has no way to run its far end as targum, so it carries only what root places
    itself (the catalogue, through /tmp into /etc/targum)."""
    for line in code(name):
        if re.match(r"\s*scp\b", line):
            assert "$HOST:/tmp/" in line, line


def remote_commands(name: str) -> list[str]:
    """The command strings handed to `ssh "$HOST"` on a single line."""
    found = []
    for line in code(name):
        match = re.search(r'ssh "\$HOST" "(.*)"\s*$', line)
        if match:
            found.append(match.group(1))
    return found


@pytest.mark.parametrize("name", SCRIPTS)
def test_remote_file_operations_run_as_targum(name: str) -> None:
    ops = 0
    for command in remote_commands(name):
        for step in re.split(r"&&|\|\||;", command):
            words = step.split()
            if not words:
                continue
            if words[0] in {"mkdir", "mv", "rm", "rmdir", "install", "ln", "cp", "touch"}:
                if "/etc/targum" in step or " /tmp/" in step:
                    continue  # root's own upload and folder, handled by root on purpose
                pytest.fail(f"{name}: root runs `{step.strip()}`")
            if words[0] == "$AS_TARGUM":
                ops += 1
    assert ops, f"{name}: no remote step runs as targum"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ship-parasha.sh", ["mkdir -p '$REMOTE/read'", "mv '$REMOTE/index.json.new'"]),
        ("ship-daily.sh", ["mkdir -p '$REMOTE/read'", "mv '$REMOTE/index.json.new'"]),
        (
            "ship-weekly.sh",
            [
                "mkdir -p '$REMOTE/.staging'",
                "rm -rf '$REMOTE/.staging/$folder'",
                "rm -rf '$REMOTE/$WEEK'",
                "mv '$REMOTE/.staging/$WEEK'",
                "rm -rf '$REMOTE/$folder'",
                "mv '$REMOTE/.staging/$folder'",
                "mv '$REMOTE/index.json.new'",
                "rmdir '$REMOTE/.staging'",
            ],
        ),
        ("ship-shared.sh", ["mkdir -p '$REMOTE'"]),
        ("ship-audio.sh", ["install -d -m 0755 '$REMOTE_RECORDINGS'"]),
    ],
)
def test_each_named_step_is_prefixed(name: str, expected: list[str]) -> None:
    joined = "\n".join(remote_commands(name))
    for step in expected:
        assert f"$AS_TARGUM {step}" in joined, step


def test_the_audio_heredoc_keeps_only_root_s_own_work() -> None:
    """The env file and the restart stay root, and name no path in targum's tree."""
    text = (DEPLOY / "ship-audio.sh").read_text(encoding="utf-8")
    block = text.split('echo "== point the service at it =="', 1)[1].split("EOF", 2)[1]
    assert "chown" not in block
    assert "systemctl restart targum" in block
    for line in block.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "targum.env" not in stripped:
            assert stripped == "systemctl restart targum", stripped


def test_a_folder_named_with_a_slash_is_shipped_as_the_folder(tmp_path: Path) -> None:
    """`ship-shared.sh */` hands rsync `book/`, which copies what is inside the folder into
    the shelf's own directory. On 2026-11-01 that left a document.json loose in the shared
    shelf, the restart took the whole shelf for a pre-homes build and moved it into
    local/, and the shared texts were gone until it was moved back by hand."""
    for name in ("one", "two"):
        (tmp_path / name / "reader").mkdir(parents=True)
        (tmp_path / name / "reader" / "index.html").write_text("<p>", encoding="utf-8")
        (tmp_path / name / "document.json").write_text("{}", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sent = tmp_path / "rsync-args"
    for tool, body in (
        ("ssh", "exit 0"),
        ("rsync", f'printf "%s\\n" "$@" > "{sent}"'),
        ("curl", "echo '{\"ok\": true}'"),
    ):
        (bin_dir / tool).write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        (bin_dir / tool).chmod(0o755)
    subprocess.run(
        ["bash", str(DEPLOY / "ship-shared.sh"), "one/", "two/"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "TARGUM_HOST": "box"},
    )
    args = sent.read_text(encoding="utf-8").splitlines()
    assert "one" in args and "two" in args
    assert not [arg for arg in args if arg.endswith("/") and ":" not in arg]


def test_the_directory_the_folders_sit_in_is_refused(tmp_path: Path) -> None:
    done = subprocess.run(
        ["bash", str(DEPLOY / "ship-shared.sh"), "./"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "TARGUM_HOST": "box"},
    )
    assert done.returncode != 0
    assert "name each folder" in done.stderr
