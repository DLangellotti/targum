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


def test_a_language_pressed_while_the_account_answers_is_not_put_back() -> None:
    """The account's answer to `/account/me` was written over the browser's language on
    every page. A press made on the page while that answer was on its way was undone by
    it, and the next page opened in the language just left (2026-09-14). And the press
    itself is sent kept alive: the conversation reloads on it, and a request cut off by
    the page going never reached the account."""
    program = """
      const {{ install }} = require({dom});
      const stored = {{ "targum:language": "he" }};
      install({{ TARGUM_KEY: "", stored }});
      let answerMe = null;
      const sent = [];
      global.fetch = function (url, options) {{
        sent.push({{ url: String(url), keepalive: !!(options && options.keepalive) }});
        if (String(url).indexOf("/account/me") >= 0) {{
          return new Promise(function (resolve) {{
            answerMe = function () {{
              resolve({{ ok: true, status: 200, json: () => Promise.resolve({{
                signedIn: true, email: "r@example.com", reads: [], learning: ["he", "arc"],
                language: "he",
              }}) }});
            }};
          }});
        }}
        return Promise.resolve({{ ok: true, status: 200, json: () => Promise.resolve({{}}) }});
      }};
      require({where});
      const started = window.TargumSync.start();
      // The reader presses Aramaic in the menu before the account has answered.
      localStorage.setItem("targum:language", "arc");
      answerMe();
      started.then(function () {{
        return window.TargumSync.language("arc");
      }}).then(function () {{
        console.log(JSON.stringify({{
          language: localStorage.getItem("targum:language"),
          pressed: sent.filter((r) => r.url.indexOf("/account/language") >= 0),
        }}));
      }});
    """.format(dom=json.dumps(str(DOM)), where=json.dumps(str(ASSETS / "sync.js")))
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    seen = json.loads(done.stdout)
    assert seen["language"] == "arc", "the press stands over the account's older answer"
    assert seen["pressed"] and all(row["keepalive"] for row in seen["pressed"])


def test_a_language_carried_out_of_a_text_is_told_to_the_account() -> None:
    """design.md §12, 2026-10-07. A page arrived at from the corner of a Russian text is in
    Russian, and the account's older answer — Hebrew, and a list without Russian — is not
    written over it. The account is told instead, with leave to turn Russian on, and its
    answer's list is mirrored for the next page."""
    program = """
      const {{ install }} = require({dom});
      const stored = {{ "targum:language": "ru", "targum:learning": "[\\"he\\",\\"ru\\"]" }};
      install({{ TARGUM_KEY: "", stored, TargumLang: {{ carried: () => "ru" }} }});
      const sent = [];
      global.fetch = function (url, options) {{
        const body = options && options.body ? JSON.parse(options.body) : null;
        sent.push({{ url: String(url), body: body, keepalive: !!(options && options.keepalive) }});
        let answer = {{}};
        if (String(url).indexOf("/account/me") >= 0) {{
          answer = {{ signedIn: true, email: "r@example.com", reads: [], learning: ["he"],
                     language: "he" }};
        }} else if (String(url).indexOf("/account/language") >= 0) {{
          answer = {{ signedIn: true, language: "ru", learning: ["he", "ru"] }};
        }}
        return Promise.resolve({{ ok: true, status: 200, json: () => Promise.resolve(answer) }});
      }};
      require({where});
      window.TargumSync.start().then(function () {{
        return new Promise((resolve) => setTimeout(resolve, 20));
      }}).then(function () {{
        console.log(JSON.stringify({{
          language: localStorage.getItem("targum:language"),
          learning: JSON.parse(localStorage.getItem("targum:learning")),
          told: sent.filter((r) => r.url.indexOf("/account/language") >= 0),
        }}));
      }});
    """.format(dom=json.dumps(str(DOM)), where=json.dumps(str(ASSETS / "sync.js")))
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    seen = json.loads(done.stdout)
    assert seen["language"] == "ru", "the account's older Hebrew is not written over it"
    assert [row["body"] for row in seen["told"]] == [{"language": "ru", "add": True}]
    assert all(row["keepalive"] for row in seen["told"])
    assert seen["learning"] == ["he", "ru"], "the list the account answered with"


def test_a_claimed_word_keeps_its_source_across_a_sync() -> None:
    """targum-internal#245. `sync.js` rebuilds a word from a named list on the way in and
    writes a named list on the way out, so a field nobody named is dropped on every
    sync. `source` is named at both ends, or a word ticked off on "Words you may already
    know" would come back from the account as an ordinary one."""
    stored = {
        "targum:sync": json.dumps({"email": "r@example.com", "revision": 3, "pushed": 250}),
        "targum:vocab:he": json.dumps(
            {"שולחן": {"status": 9, "surface": "שולחן", "source": "claimed", "at": 1, "seen": 400}},
            ensure_ascii=False,
        ),
    }
    answers = {
        "/account/me": {"signedIn": True, "email": "r@example.com", "reads": [], "learning": []},
        "/sync": {
            "revision": 4,
            "words": [
                {
                    "language": "he",
                    "lemma": "כיסא",
                    "status": 9,
                    "surface": "כיסא",
                    "band": 1,
                    "learned": 0,
                    "source": "claimed",
                    "at": 90,
                    "seen": 500,
                    "gone": 0,
                },
            ],
            "meanings": [],
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
          pushed: sent[0].words.map((w) => [w.lemma, w.source || ""]).sort(),
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
    assert answer["pushed"] == [["שולחן", "claimed"]], "it goes up as what it is"
    assert answer["words"]["כיסא"]["source"] == "claimed", "and comes back down as it"
    assert answer["words"]["שולחן"]["source"] == "claimed", "and the one already here keeps it"


def test_a_place_is_kept_at_once_and_pushed_at_most_every_half_minute() -> None:
    """targum-internal#430. The reader writes its place as it reads — a scroll settles
    every second, a recording moves every five — and every write lands in this browser at
    once. The account hears on the next exchange, then at most once every thirty seconds,
    and once more, kept alive, when the page is put down. A place that did not move
    writes nothing. A newer place from another device wins on the way in."""
    stored = {
        "targum:sync": json.dumps({"email": "reader@example.com", "revision": 1, "pushed": 1}),
        "targum:places": json.dumps(
            {"ruth": {"section": "1", "path": "", "segment": "b1", "seconds": 0, "at": 10}}
        ),
    }
    answer = {
        "revision": 2,
        "places": [
            {"hash": "ruth", "section": "2", "path": "/r/sec-2.html", "segment": "b5",
             "seconds": 7.5, "at": 99, "seen": 99, "gone": 0},
        ],
    }  # fmt: skip
    program = """
      const {{ install }} = require({dom});
      const stored = {stored};
      install({{ TARGUM_KEY: "", stored }});
      const answer = {answer};
      const timers = [];
      global.setTimeout = function (run, wait) {{
        timers.push({{ run, wait, live: true }});
        return timers.length;
      }};
      global.clearTimeout = function (id) {{ if (timers[id - 1]) timers[id - 1].live = false; }};
      const syncs = [];
      global.fetch = function (url, options) {{
        const me = String(url).indexOf("/account/me") >= 0;
        if (!me) syncs.push({{ body: JSON.parse(options.body), keepalive: !!options.keepalive }});
        const reply = me
          ? {{ signedIn: true, email: "reader@example.com", reads: [], learning: [] }}
          : answer;
        return Promise.resolve({{ ok: true, status: 200, json: () => Promise.resolve(reply) }});
      }};
      require({where});
      const sync = window.TargumSync;
      sync.start().then(function () {{
        const pulled = sync.placeOf("ruth");
        sync.place("gen", {{ section: "3", path: "/g/sec-3.html", segment: "b1" }});
        const first = JSON.parse(stored["targum:places"]).gen.at;
        sync.place("gen", {{ section: "3", segment: "b1" }});
        const unmoved = JSON.parse(stored["targum:places"]).gen.at === first;
        sync.place("gen", {{ section: "3", segment: "b2" }});
        sync.place("gen", {{ section: "3", seconds: 12.345 }});
        const kept = sync.placeOf("gen");
        sync.place("gen", {{ section: "4" }});
        const moved = sync.placeOf("gen");
        const waiting = timers.filter((t) => t.live).map((t) => t.wait);
        const before = syncs.length;
        document.visibilityState = "hidden";
        document.fire("visibilitychange");
        setImmediate(function () {{
          console.log(JSON.stringify({{
            pulled, unmoved, kept, moved, waiting, before,
            after: syncs.length,
            last: syncs[syncs.length - 1],
            live: timers.filter((t) => t.live).length,
            recent: sync.places(1).map((p) => p.hash),
          }}));
        }});
      }});
    """.format(
        dom=json.dumps(str(DOM)),
        stored=json.dumps(stored),
        answer=json.dumps(answer),
        where=json.dumps(str(ASSETS / "sync.js")),
    )
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    seen = json.loads(done.stdout)

    assert seen["pulled"]["section"] == "2" and seen["pulled"]["segment"] == "b5", (
        "the account's newer place replaced this browser's"
    )
    assert seen["unmoved"], "a place that did not move is not written again"
    assert seen["kept"]["segment"] == "b2" and seen["kept"]["seconds"] == 12.35
    assert seen["kept"]["path"] == "/g/sec-3.html", "what a call leaves out is kept"
    assert seen["moved"]["segment"] == "" and seen["moved"]["seconds"] == 0, (
        "a different part starts at its own top"
    )
    assert seen["waiting"] == [30000], "one push owed, half a minute out"
    assert seen["before"] == 1, "four places written, and only the opening exchange sent"
    assert seen["after"] == 2 and seen["live"] == 0, "putting the page down sends the rest"
    assert seen["last"]["keepalive"] is True
    [sent] = [row for row in seen["last"]["body"]["places"] if row["hash"] == "gen"]
    assert sent["section"] == "4" and sent["seen"] == sent["at"]
    assert seen["recent"] == ["gen"]


def test_a_place_is_kept_for_somebody_signed_out() -> None:
    """No account, no push — and still a place, for this browser's Continue."""
    program = """
      const {{ install }} = require({dom});
      const stored = {{}};
      install({{ TARGUM_KEY: "", stored }});
      let posts = 0;
      global.fetch = function (url, options) {{
        if (options && options.method === "POST") posts += 1;
        const reply = {{ signedIn: false }};
        return Promise.resolve({{ ok: true, status: 200, json: () => Promise.resolve(reply) }});
      }};
      require({where});
      window.TargumSync.start().then(function () {{
        window.TargumSync.place("gen", {{ section: "2", segment: "b3" }});
        document.visibilityState = "hidden";
        document.fire("visibilitychange");
        console.log(JSON.stringify({{ posts, place: window.TargumSync.placeOf("gen") }}));
      }});
    """.format(dom=json.dumps(str(DOM)), where=json.dumps(str(ASSETS / "sync.js")))
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    seen = json.loads(done.stdout)
    assert seen["posts"] == 0
    assert seen["place"]["section"] == "2" and seen["place"]["segment"] == "b3"
