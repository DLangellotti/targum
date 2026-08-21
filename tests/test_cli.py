from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum.cli import app

runner = CliRunner()


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "declaration.md"
    path.write_text("# הכרזה\n\nבארץ־ישראל קם העם היהודי בשנת 1897.\n", encoding="utf-8")
    return path


@pytest.mark.stanza
def test_build_writes_a_reader(source: Path, tmp_path: Path, needs_hebrew_model: None) -> None:
    out = tmp_path / "out"
    result = runner.invoke(
        app, ["build", str(source), "--to", "en", "--provider", "null", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert (out / "reader" / "index.html").exists()
    assert "he → en" in result.output


def test_pdf_gets_a_message_not_a_traceback(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = runner.invoke(app, ["build", str(pdf), "--to", "en", "--provider", "null"])
    assert result.exit_code == 1
    assert "PDF ingest is not supported yet" in result.output
    assert "Traceback" not in result.output


def test_missing_key_is_reported_before_any_work(source: Path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    result = runner.invoke(app, ["build", str(source), "--to", "en"])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output


def test_providers_lists_both(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    assert "anthropic" in result.output and "null" in result.output


def test_models_list_when_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    result = runner.invoke(app, ["models", "list"])
    assert result.exit_code == 0
    assert "targum models fetch" in result.output


def test_cache_clear_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    result = runner.invoke(app, ["cache", "clear"])
    assert result.exit_code == 0
    assert "Cleared" in result.output


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    for command in ("build", "providers", "models", "cache"):
        assert command in result.output


def test_sources_lists_what_can_be_read() -> None:
    result = runner.invoke(app, ["sources"])
    assert result.exit_code == 0
    assert ".epub" in result.output and "gutenberg:" in result.output


def test_fetch_writes_an_editable_file(tmp_path: Path, epub_source: Path) -> None:
    # fetch and build share one ingest path, so a local file exercises the command
    # without reaching the network.
    out = tmp_path / "book.md"
    result = runner.invoke(app, ["fetch", str(epub_source), "--out", str(out)])
    assert result.exit_code == 0
    written = out.read_text(encoding="utf-8")
    assert written.startswith("---")
    assert "author: A Nineteenth Century Author" in written
    assert "# Chapter One" in written
    assert "targum build" in result.output


def test_fetch_reports_a_bad_identifier() -> None:
    result = runner.invoke(app, ["fetch", "archive:12345"])
    assert result.exit_code == 1
    assert "gutenberg" in result.output
    assert "Traceback" not in result.output
