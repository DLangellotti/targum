"""The publishers the chat may look at: private data, public code, an empty default."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from targum.chat import sources


def registry(tmp_path: Path, monkeypatch: Any, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"publishers": rows}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TARGUM_SOURCES", str(path))
    return path


def test_no_file_means_no_publishers_and_only_the_public_hosts(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setenv("TARGUM_SOURCES", str(tmp_path / "missing.json"))
    assert sources.load() == []
    hosts = sources.allowed_domains()
    assert "www.sefaria.org" in hosts and "www.youtube.com" in hosts
    assert len(hosts) == len(set(hosts))


def test_publishers_are_read_and_their_hosts_lead_the_domain_list(
    monkeypatch: Any, tmp_path: Path
) -> None:
    registry(
        tmp_path,
        monkeypatch,
        [
            {
                "key": "kan",
                "name": "כאן חדשות",
                "publisher": "Kan",
                "feed": "https://www.kan.org.il/rss/news.xml",
                "homepage": "https://www.kan.org.il/",
                "kind": "news",
                "licence": "",
            },
            {
                "key": "odd",
                "name": "Odd",
                "feed": "https://feeds.example.org/x",
                "kind": "not-a-kind",
            },
            {"no": "key"},
        ],
    )
    found = sources.load()
    assert [one.key for one in found] == ["kan", "odd"], "a row with no key is skipped"
    assert found[1].kind == "news", "an unknown kind falls back rather than failing"
    hosts = sources.allowed_domains()
    assert hosts[:2] == ["www.kan.org.il", "feeds.example.org"], "publishers first"
    assert "www.sefaria.org" in hosts
    assert sources.by_key("kan") is not None and sources.by_key("nope") is None


def test_the_domain_list_is_capped_at_what_the_api_takes(monkeypatch: Any, tmp_path: Path) -> None:
    registry(
        tmp_path,
        monkeypatch,
        [
            {"key": f"p{n}", "name": f"p{n}", "feed": f"https://site{n}.example/feed"}
            for n in range(90)
        ],
    )
    assert len(sources.allowed_domains()) == sources.MAX_DOMAINS


def test_a_broken_file_is_an_empty_list(monkeypatch: Any, tmp_path: Path) -> None:
    path = tmp_path / "sources.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("TARGUM_SOURCES", str(path))
    assert sources.load() == []
