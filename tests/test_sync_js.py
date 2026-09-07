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


def test_a_title_from_another_device_does_not_drop_a_finished_chapter() -> None:
    """targum-internal#173. A targum finishes at the end of a chapter, so which chapters
    are finished lives in the document's own record — and `applyDocs` rewrites that
    record wholesale whenever the row it is handed is newer. Written without carrying
    the chapters across, a title arriving from another device threw away a morning's
    reading, silently, on a page nobody was looking at.

    The chapters themselves merge one row at a time, which is the other half of the same
    argument: the account keeps whichever version of a *record* is newer, so a map of
    them pushed from a phone that had not heard about the laptop's would replace the
    laptop's whole.
    """
    stored = {
        "targum:docs": json.dumps(
            {"gen": {"title": "", "language": "he", "updated": 10, "sections": {"1": 100}}},
            ensure_ascii=False,
        ),
        "targum:sync": json.dumps({"email": "reader@example.com", "revision": 1, "pushed": 1}),
    }
    # What the account hands back: a newer row for the document, and a chapter finished
    # on the other device that this browser has never seen.
    answer = {
        "revision": 2,
        "words": [],
        "meanings": [],
        "phrases": [],
        "days": [],
        "docs": [{"hash": "gen", "title": "Genesis", "language": "he", "updated": 99, "done": 0}],
        "sections": [{"hash": "gen", "section": "2", "at": 200, "seen": 200, "gone": 0}],
    }
    program = """
      const {{ install }} = require({dom});
      const stored = {stored};
      install({{ TARGUM_KEY: "", stored }});
      const answer = {answer};
      let sent = null;
      global.fetch = function (url, options) {{
        const reply = String(url).indexOf("/account/me") >= 0
          ? {{ signedIn: true, email: "reader@example.com", reads: [], learning: [] }}
          : answer;
        if (options && options.body) sent = JSON.parse(options.body);
        return Promise.resolve({{ ok: true, status: 200, json: () => Promise.resolve(reply) }});
      }};
      require({where});
      window.TargumSync.start().then(function () {{
        console.log(JSON.stringify({{
          docs: JSON.parse(stored["targum:docs"] || "{{}}"),
          sent: sent,
        }}));
      }});
    """.format(
        dom=json.dumps(str(DOM)),
        stored=json.dumps(stored, ensure_ascii=False),
        answer=json.dumps(answer, ensure_ascii=False),
        where=json.dumps(str(ASSETS / "sync.js")),
    )
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    seen = json.loads(done.stdout)

    record = seen["docs"]["gen"]
    assert record["title"] == "Genesis", "the newer row won, as it should"
    assert record["sections"] == {"1": 100, "2": 200}, "and both chapters survived it"

    # And the chapter this browser knew about went up as its own row, not as a column.
    pushed = {(row["hash"], row["section"]) for row in seen["sent"]["sections"]}
    assert ("gen", "1") in pushed


def test_a_word_that_moved_here_does_not_come_back_under_its_old_name_from_the_account() -> None:
    """The annotator changed and `vocab.js` moved a mark to the word's new name, leaving
    the old one as a tombstone (targum-internal#141). The account, or a device that has
    not opened that text yet, still holds the old name; on the next pull it must not be
    put back beside the new one, or one word is two again. The rule is the one the
    account applies on a push, applied on the way in: the newer edit stands."""
    stored = {
        "targum:sync": json.dumps({"email": "r@example.com", "revision": 3, "pushed": 250}),
        "targum:vocab:he": json.dumps(
            {"ארך": {"status": 2, "surface": "לאורך", "band": 4, "at": 100, "seen": 300}},
            ensure_ascii=False,
        ),
        "targum:gone": json.dumps({"w:he:לאורך": 300, "m:he:en:לאורך": 300}, ensure_ascii=False),
        "targum:meanings:he:en": json.dumps(
            {"ארך": {"meaning": "along", "note": "", "at": 5, "seen": 300}}, ensure_ascii=False
        ),
    }
    answers = {
        "/account/me": {"signedIn": True, "email": "r@example.com", "reads": [], "learning": []},
        "/sync": {
            "revision": 4,
            "words": [
                # The old name, from the account: older than the tombstone, so it stays gone.
                {
                    "language": "he",
                    "lemma": "לאורך",
                    "status": 2,
                    "surface": "לאורך",
                    "band": 4,
                    "learned": 0,
                    "at": 100,
                    "seen": 150,
                    "gone": 0,
                },
                # A word touched on another device after this one's tombstones: it lands.
                {
                    "language": "he",
                    "lemma": "ספר",
                    "status": 9,
                    "surface": "ספר",
                    "band": 1,
                    "learned": 0,
                    "at": 90,
                    "seen": 400,
                    "gone": 0,
                },
            ],
            "meanings": [
                {
                    "source": "he",
                    "target": "en",
                    "term": "לאורך",
                    "meaning": "along",
                    "note": "",
                    "at": 5,
                    "seen": 150,
                    "gone": 0,
                },
            ],
            "phrases": [],
            "docs": [],
            "days": [],
            "sections": [],
        },
    }
    program = """
      const {{ install }} = require({dom});
      const stored = {stored};
      install({{ TARGUM_KEY: "k", stored }});
      const answers = {answers};
      const sent = [];
      global.fetch = window.fetch = function (url, options) {{
        const path = String(url).split("?")[0];
        if (options && options.body) sent.push(JSON.parse(options.body));
        const json = () => Promise.resolve(answers[path]);
        return Promise.resolve({{ ok: true, status: 200, json }});
      }};
      require({where});
      window.TargumSync.start().then(function () {{
        console.log(JSON.stringify({{
          words: JSON.parse(stored["targum:vocab:he"]),
          meanings: JSON.parse(stored["targum:meanings:he:en"]),
          pushed: sent[0].words.map((w) => [w.lemma, w.gone || 0]).sort(),
        }}));
      }});
    """.format(
        dom=json.dumps(str(DOM)),
        stored=json.dumps(stored, ensure_ascii=False),
        answers=json.dumps(answers, ensure_ascii=False),
        where=json.dumps(str(ASSETS / "sync.js")),
    )
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    answer = json.loads(done.stdout)
    assert set(answer["words"]) == {"ארך", "ספר"}, "the old name stayed gone; the newer word landed"
    assert set(answer["meanings"]) == {"ארך"}
    # And what went up: the moved record under its new name, and the old name as gone.
    assert answer["pushed"] == [["ארך", 0], ["לאורך", 1]]
