"""A transcript is read only from where the server writes one (ops, 2026-11-17).

`/prepare` keeps an allow-list of what a page may send (`PREPARE_FIELDS`, targum-internal
#706), so a request cannot name `transcript` at all; `test_source_shown` pins that. These
pin the second lock, at the one place the option becomes a file read (`Library._builder`
→ `Build(transcript=…)` → `ingest.load`): a transcript outside the job's own home is not
read, whoever wrote it on the job. And the doors that do write one still work.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from test_finds import home  # noqa: F401 - the served fixture
from test_serve import call, sign_in

from targum.serve import Job, Library


@pytest.fixture
def library(tmp_path: Path) -> Library:
    out = tmp_path / "out"
    out.mkdir()
    return Library(out)


def job(library: Library, transcript: str, where: str = "p1") -> Job:
    return Job(
        id="t",
        source="https://www.youtube.com/watch?v=abc123",
        options={"to": "en", "transcript": transcript},
        owner=1,
        home=library.out / where,
    )


def test_a_transcript_outside_the_home_is_not_read(library: Library, tmp_path: Path) -> None:
    secret = tmp_path / "elsewhere" / "secret.vtt"
    secret.parent.mkdir()
    secret.write_text("WEBVTT\n", encoding="utf-8")
    assert library._builder(job(library, str(secret))).transcript is None
    assert library._builder(job(library, "/etc/hosts")).transcript is None


def test_another_readers_file_is_not_read(library: Library) -> None:
    theirs = library.out / "p2" / "uploads" / "x" / "talk.vtt"
    theirs.parent.mkdir(parents=True)
    theirs.write_text("WEBVTT\n", encoding="utf-8")
    assert library._builder(job(library, str(theirs))).transcript is None
    # Nor by walking out of their own home.
    sneaky = library.out / "p1" / ".." / "p2" / "uploads" / "x" / "talk.vtt"
    assert library._builder(job(library, str(sneaky))).transcript is None


def test_the_upload_doors_own_transcript_is_read(library: Library) -> None:
    mine = library.out / "p1" / "uploads" / "x" / "talk.vtt"
    mine.parent.mkdir(parents=True)
    mine.write_text("WEBVTT\n", encoding="utf-8")
    assert str(library._builder(job(library, str(mine))).transcript) == str(mine.resolve())


def test_a_build_with_no_transcript_names_none(library: Library) -> None:
    assert library._builder(job(library, "")).transcript is None


def test_prepare_strips_a_forged_transcript_and_keeps_the_uploaded_one(
    home: Any,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the door: a `transcript` a request names never reaches the job, and the
    file is never opened; one the reader uploads (`transcriptName`, `transcriptContent`)
    is written into their own home and is the one the build reads."""
    cookie = sign_in(home.port, home.postbox)
    seen: list[Job] = []
    opened: list[str] = []

    def prepare(job: Job) -> None:
        seen.append(job)
        job.stage = "ready"

    real_open = Path.open

    def watched(self: Path, *args: Any, **kwargs: Any) -> Any:
        if str(self) == "/etc/hosts":
            opened.append(str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(home.library, "prepare", prepare)
    monkeypatch.setattr(Path, "open", watched)
    source = "https://www.youtube.com/watch?v=abc123"
    answered = call(
        home.port,
        "POST",
        "/prepare",
        {"source": source, "to": "en", "transcript": "/etc/hosts"},
        cookie=cookie,
    )
    assert seen, answered
    assert "transcript" not in seen[0].options
    assert home.library._builder(seen[0]).transcript is None
    assert not opened

    seen.clear()
    call(
        home.port,
        "POST",
        "/prepare",
        {
            "source": source,
            "to": "en",
            "transcriptName": "talk.vtt",
            "transcriptContent": base64.b64encode(
                "WEBVTT\n\n00:00.000 --> 00:01.000\nשלום\n".encode()
            ).decode(),
        },
        cookie=cookie,
    )
    assert seen
    kept = seen[0].options["transcript"]
    assert Path(kept).is_file()
    assert str(home.library._builder(seen[0]).transcript) == str(Path(kept).resolve())
