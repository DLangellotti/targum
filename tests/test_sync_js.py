"""The account sync script, run rather than read, for the one thing in it that deletes."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from targum.render.builder import ASSETS

DOM = Path(__file__).resolve().parent / "js" / "dom.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def test_a_word_taken_off_the_list_takes_its_meanings_with_it() -> None:
    """A meaning belongs to a language pair and a word to a language, so a word has one
    meaning per language it was read in. Left behind when the word went, those kept a
    language in the definitions switcher after the last word learned through it was
    gone — and came back with the word on the next sync, because nothing said they had
    been deleted."""

    def meant(**words: str) -> str:
        return json.dumps(
            {
                term: {"meaning": text, "note": "", "at": 1, "seen": 1}
                for term, text in words.items()
            },
            ensure_ascii=False,
        )

    stored = {
        "targum:meanings:he:en": meant(ספר="book", עיר="city"),
        "targum:meanings:he:ru": meant(ספר="книга"),
        "targum:meanings:ru:en": meant(ספר="not this one"),
    }
    program = """
      const {{ install }} = require({dom});
      const stored = {stored};
      install({{ TARGUM_KEY: "k", stored }});
      require({where});
      window.TargumSync.forgetMeanings("he", "ספר");
      const gone = JSON.parse(stored["targum:gone"] || "{{}}");
      console.log(JSON.stringify({{
        en: Object.keys(JSON.parse(stored["targum:meanings:he:en"])),
        ru: Object.keys(JSON.parse(stored["targum:meanings:he:ru"])),
        other: Object.keys(JSON.parse(stored["targum:meanings:ru:en"])),
        tombstones: Object.keys(gone).sort(),
      }}));
    """.format(
        dom=json.dumps(str(DOM)),
        stored=json.dumps(stored, ensure_ascii=False),
        where=json.dumps(str(ASSETS / "sync.js")),
    )
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    answer = json.loads(done.stdout)

    assert answer["en"] == ["עיר"], "the word is gone from English and its neighbour is not"
    assert answer["ru"] == [], "and from Russian"
    assert answer["other"] == ["ספר"], "a different source language is a different word"
    assert answer["tombstones"] == ["m:he:en:ספר", "m:he:ru:ספר"], "so no sync brings them back"
