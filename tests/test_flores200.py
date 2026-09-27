"""FLORES-200 as the recast eval's reference for Yiddish: the archived predecessor of
FLORES+, fetched without a token, kept to the two files a run needs, and refused rather
than zipped short when its files disagree (targum-internal#361)."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum.chat import flores200
from targum.cli import app
from targum.errors import TargumError


def a_tarball(lines: int = 3) -> bytes:
    """The archive's layout, with every language FLORES-200 has standing in for its two
    hundred: more members than a run wants, so keeping only two is something to check."""
    names = [*flores200.FILES.values(), "deu_Latn", "arb_Arab", "jpn_Jpan"]
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        for split in flores200.SPLITS:
            for name in names:
                body = "\n".join(f"{name} {split} {n}" for n in range(1, lines + 1)).encode()
                member = tarfile.TarInfo(f"./flores200_dataset/{split}/{name}.{split}")
                member.size = len(body)
                archive.addfile(member, io.BytesIO(body))
    return out.getvalue()


class Answer:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(flores200, "root", lambda: tmp_path / "gold")
    return tmp_path / "gold"


@pytest.fixture
def fetched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every address asked for, answered with the tarball and never the network."""
    import httpx

    asked: list[str] = []

    def get(url: str, **_: object) -> Answer:
        asked.append(url)
        return Answer(a_tarball())

    monkeypatch.setattr(httpx, "get", get)
    return asked


def test_the_fetch_keeps_only_the_files_asked_for(home: Path, fetched: list[str]) -> None:
    """The archive holds four hundred files and a run needs two; the box has had half a
    gigabyte free. Read in memory, and only English and the language written out."""
    assert flores200.fetch(["yi"]) == 2
    assert sorted(path.name for path in home.iterdir()) == [
        "flores200-devtest-en.txt",
        "flores200-devtest-yi.txt",
    ]
    assert flores200.load("yi")[0] == flores200.Pair(
        "1", "eng_Latn devtest 1", "ydd_Hebr devtest 1"
    )
    assert fetched == [flores200.SOURCE]


def test_a_second_fetch_asks_for_nothing(home: Path, fetched: list[str]) -> None:
    flores200.fetch(["yi"])
    flores200.fetch(["yi"])
    assert len(fetched) == 1


def test_a_language_the_module_does_not_carry_is_refused_by_name(
    home: Path, fetched: list[str]
) -> None:
    for door in (lambda: flores200.fetch(["de"]), lambda: flores200.load("de")):
        with pytest.raises(TargumError) as refused:
            door()
        assert "for de" in refused.value.message
    assert fetched == [], "refused before anything is downloaded"


def test_files_of_unequal_length_are_refused_and_not_zipped_short() -> None:
    """Off by one from the first gap onward, every score after it would be of the wrong
    sentence."""
    with pytest.raises(TargumError) as refused:
        flores200.parse("one\ntwo\nthree", "אחת\nשתיים", "yi")
    assert "3 English lines, 2 yi" in refused.value.message


def test_not_downloaded_names_a_command_that_exists(home: Path) -> None:
    with pytest.raises(TargumError) as refused:
        flores200.load("yi")
    assert refused.value.hint == "Run: targum models fetch flores200 --language yi"


def test_the_command_it_names_fetches(home: Path, fetched: list[str]) -> None:
    ran = CliRunner().invoke(app, ["models", "fetch", "flores200", "--language", "yi"])
    assert ran.exit_code == 0, ran.output
    assert flores200.available("yi")
    again = CliRunner().invoke(app, ["models", "fetch", "flores200", "--language", "yi"])
    assert "already downloaded" in again.output and len(fetched) == 1


def test_the_command_refuses_a_language_it_does_not_carry(home: Path, fetched: list[str]) -> None:
    ran = CliRunner().invoke(app, ["models", "fetch", "flores200", "--language", "de"])
    assert ran.exit_code != 0
    assert fetched == []


def test_the_module_says_it_is_not_flores_plus() -> None:
    assert "It is not FLORES+" in (flores200.__doc__ or "")
