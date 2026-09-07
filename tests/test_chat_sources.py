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


def test_a_feed_host_is_reduced_to_the_site_it_belongs_to() -> None:
    """The papers' feeds live on rss. and rcs. hosts; a search allowed only there would
    read RSS servers and never a page anybody prints."""
    assert sources.site("https://rss.walla.co.il/feed/1") == "walla.co.il"
    assert sources.site("https://rcs.mako.co.il/rss/news-israel.xml") == "mako.co.il"
    assert sources.site("https://www.ynet.co.il/Integration/StoryRss2.xml") == "ynet.co.il"
    assert sources.site("https://main.knesset.gov.il/News/rss.aspx") == "knesset.gov.il"
    assert sources.site("https://www.israelhayom.co.il/rss.xml") == "israelhayom.co.il"
    assert sources.site("https://feeds.example.org/x") == "example.org"
    assert sources.site("https://benyehuda.org/") == "benyehuda.org"
    assert sources.site("https://www.gov.il/he/api/news/rss") == "gov.il", "www. is not a site"
    assert sources.site("not an address") == ""


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
    assert hosts[:2] == ["kan.org.il", "example.org"], "publishers first, by their site"
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
