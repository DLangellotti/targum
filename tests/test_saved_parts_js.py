"""A book kept in parts says how much of it is saved (targum-internal#720, P2 8).

Opening a book's contents page keeps that page alone (David, 2026-10-10), and the Saved
page took `pages - 1 = 0` for "text", so the row read as the whole book saved while every
chapter was "Not on this device". The row now says "Contents only", or "{n} of {total}
parts", counted from the same `files` the reader marks its chapters from. Run in node
against `offline.js`'s `partsOf` and `saved.js`'s `keptWord`, in English and Russian;
the browser half, where Keep saves the rest, is in `test_offline_browser.py`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

ROOT = Path(__file__).resolve().parents[1] / "src" / "targum"
ASSETS = ROOT / "render" / "assets"
BASE = "http://x/reader/book-he/reader/"


def function(name: str, file: str) -> str:
    text = (ASSETS / file).read_text(encoding="utf-8")
    found = re.search(rf"\n  function {name}\(.*?\n  }}\n", text, re.S)
    assert found, f"{file} has a function {name}"
    return found.group(0)


def said(items: list[dict[str, Any]], language: str) -> list[str]:
    strings = json.loads((ROOT / "strings" / f"{language}.json").read_text(encoding="utf-8"))
    script = f"""
    const said = {json.dumps(strings if language != "en" else {})};
    const language = {json.dumps(language)};
    function fillIn(text, fill) {{
      return text.replace(/\\{{(\\w+)\\}}/g, (all, k) => (k in fill ? String(fill[k]) : all));
    }}
    function t(key, english, fill) {{
      return fillIn(typeof said[key] === "string" ? said[key] : english, fill || {{}});
    }}
    function tn(key, count, one, other, fill) {{
      const form = new Intl.PluralRules(language).select(count);
      let text = said[key + "." + form];
      if (typeof text !== "string") text = said[key + ".other"];
      return fillIn(typeof text === "string" ? text : count === 1 ? one : other,
                    Object.assign({{ n: count }}, fill || {{}}));
    }}
    {function("partsOf", "offline.js")}
    const offline = {{ parts: partsOf }};
    {function("keptWord", "saved.js")}
    const items = {json.dumps(items)};
    process.stdout.write(JSON.stringify(items.map(keptWord)));
    """
    done = subprocess.run(
        # On stdin: the strings are too long for an argument list (CI, Errno 7).
        ["node", "-"],
        input=script,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def kept(*chapters: int, whole: int = 0, **more: Any) -> dict[str, Any]:
    files = [f"{BASE}index.html"] + [f"{BASE}sec-{n:04d}.html" for n in chapters]
    return {
        "id": "/reader/book-he/reader/",
        "kind": "novel",
        "part": True,
        "pages": len(files),
        "whole": whole,
        "files": files + [f"{BASE}audio/part-001.mp3"],
        **more,
    }


def test_a_contents_page_alone_says_contents_only() -> None:
    assert said([kept(whole=15)], "en") == ["Contents only"]
    assert said([kept(whole=15)], "ru") == ["Только оглавление"]


def test_parts_say_how_many_of_how_many() -> None:
    rows = [kept(2, whole=15), kept(1, 2, whole=15), kept(1, 2, 3, whole=4), kept(1, whole=22)]
    assert said(rows, "en") == ["1 of 14 parts", "2 of 14 parts", "3 of 3 parts", "1 of 21 parts"]
    assert said(rows, "ru") == [
        "1 из 14 частей",
        "2 из 14 частей",
        "3 из 3 частей",
        "1 из 21 части",
    ]


def test_a_chapter_opened_on_its_own_counts_without_the_contents_page() -> None:
    alone = kept(5, whole=15)
    alone["files"] = [f"{BASE}sec-0005.html"]
    assert said([alone], "en") == ["1 of 14 parts"]


def test_a_copy_kept_before_the_count_says_only_what_it_has() -> None:
    """Kept before the server told `whole`: the count it has, never a whole it lacks."""
    rows = [kept(1, 2), kept(3)]
    assert said(rows, "en") == ["2 parts saved", "1 part saved"]
    assert said(rows, "ru") == ["Сохранены 2 части", "Сохранена 1 часть"]


def test_a_book_kept_whole_still_says_its_parts_and_media() -> None:
    whole = {"kind": "novel", "pages": 5, "sound": True, "files": []}
    assert said([whole], "en") == ["4 parts, text and recording"]
    assert said([{"kind": "article", "pages": 1}], "en") == ["text"]
