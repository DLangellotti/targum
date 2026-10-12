/* What a press at the foot of a text did, said on the page it led to (design.md §12,
 * "The foot is one block", 2026-09-25, and "The first finish goes home", 2026-10-12).
 *
 * A press that leaves the page — Next in a playlist, or the first Done in a language,
 * which goes to Your targums — carries what it did in this tab's store. The page it lands
 * on says it once, briefly, "Finished <title> · +12 known · 96% · 3 looked up", with the
 * one Undo that takes back the finish and the words it marked. The press left the page,
 * so this is where the Undo can be.
 *
 * Shared by the reader, where a playlist's next item lands, and home, where the first
 * finish lands. What is page-local — the reader's own copies of its meanings, its counts
 * — stays with the page: `undo` answers which words it took back so the page can follow.
 */
(function () {
  "use strict";

  var LEFT = "targum:foot:left";
  var DOCS = "targum:docs";
  //: The status a word marked known carries (`reader.js`, `vocab.js`).
  var KNOWN = 9;
  //: A press is news on the page it led to, not on a page opened ten minutes later.
  var FRESH_MS = 10 * 60 * 1000;

  function words() {
    return (
      window.TargumStrings || {
        t: function (key, english) {
          return english;
        },
        tn: function (key, count, one, other) {
          return count === 1 ? one : other;
        },
      }
    );
  }

  function fill(text, values) {
    return String(text).replace(/\{(\w+)\}/g, function (all, name) {
      return values && values[name] !== undefined ? String(values[name]) : all;
    });
  }

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
  }

  function keep(name, value) {
    try {
      if (window.targumKeep) window.targumKeep(name, value);
      else localStorage.setItem(name, value);
    } catch (e) {}
  }

  /* Carried by the press, in the tab's own store: it is about this sitting and nothing
     else, so a second tab or tomorrow's visit is told nothing. */
  function carry(record) {
    try {
      sessionStorage.setItem(LEFT, JSON.stringify(record));
    } catch (e) {}
  }

  /* Read once and taken out of the store at once, so a reload does not say it twice. */
  function take() {
    var said = null;
    try {
      said = JSON.parse(sessionStorage.getItem(LEFT) || "null");
      sessionStorage.removeItem(LEFT);
    } catch (e) {
      said = null;
    }
    if (!said) return null;
    if (Date.now() - Number(said.at || 0) > FRESH_MS) return null;
    return said;
  }

  function shareOf(tally) {
    return tally && tally.of ? Math.round((tally.here / tally.of) * 100) : 0;
  }

  /* "Finished <title> · +12 known · 96% · 3 looked up": the finished box's three figures,
     in the same order, on one line (§12, "The finished box is three figures"). The title
     is isolated, since it may run right to left inside a line that runs left to right. */
  function say(node, said) {
    var w = words();
    node.textContent = "";
    var line = w.t("reader.arrived.finished", "Finished {title}");
    var cut = line.indexOf("{title}");
    if (cut < 0) node.appendChild(document.createTextNode(line));
    else {
      node.appendChild(document.createTextNode(line.slice(0, cut)));
      var name = document.createElement("bdi");
      name.setAttribute("dir", "auto");
      name.textContent = String(said.title || "");
      node.appendChild(name);
      node.appendChild(document.createTextNode(line.slice(cut + 7)));
    }
    var tally = said.tally;
    if (tally) {
      node.appendChild(
        document.createTextNode(
          " · " +
            fill(w.t("reader.arrived.figures", "+{known} known · {share}% · {looked} looked up"), {
              known: Number(tally.known || 0),
              share: shareOf(tally),
              looked: Number(tally.looked || 0),
            })
        )
      );
    } else if (said.counted) {
      node.appendChild(
        document.createTextNode(
          " · " +
            fill(
              w.tn("reader.rest.done", said.counted, "{n} word marked known", "{n} words marked known"),
              { n: said.counted }
            )
        )
      );
    }
  }

  /* The section that press finished, and the words it marked, in whichever language's
     list they went to. The page that marked them is gone, so this goes to the stores
     directly, the way `sync.js` sweeps them, and leaves a tombstone as a dropped word does
     so another device does not push them back. A word said something else about since
     the press is left alone. Answers the words taken back, by language. */
  function undo(said) {
    var taken = {};
    if (!said) return taken;
    // Grouped by language, so each list and each store of meanings is read and written
    // once rather than once a word: a long chapter marks a few thousand.
    var byTongue = {};
    (said.words || []).forEach(function (pair) {
      var tongue = String((pair && pair[0]) || "");
      var word = String((pair && pair[1]) || "");
      if (tongue && word) (byTongue[tongue] = byTongue[tongue] || []).push(word);
    });
    Object.keys(byTongue).forEach(function (tongue) {
      var name = "targum:vocab:" + tongue;
      var theirs = read(name, "{}");
      var gone = byTongue[tongue].filter(function (word) {
        var record = theirs[word];
        if (!record || record.status !== KNOWN || record.learned) return false;
        delete theirs[word];
        return true;
      });
      if (!gone.length) return;
      taken[tongue] = gone;
      keep(name, JSON.stringify(theirs));
      // Their meanings, in the browser's stores.
      var head = "targum:meanings:" + tongue + ":";
      var names = [];
      try {
        for (var i = 0; i < localStorage.length; i++) {
          var key = localStorage.key(i) || "";
          if (key.indexOf(head) === 0) names.push(key);
        }
      } catch (e) {}
      names.forEach(function (key) {
        var records = read(key, "{}");
        gone.forEach(function (word) {
          delete records[word];
        });
        keep(key, JSON.stringify(records));
      });
      if (window.TargumSync) {
        gone.forEach(function (word) {
          window.TargumSync.forgetWord(tongue, word);
        });
      }
    });
    var all = read(DOCS, "{}");
    var record = all[said.document];
    if (record) {
      if (record.sections && typeof record.sections === "object") delete record.sections[String(said.section)];
      if (Number(said.sections) === 1) record.done = 0;
      record.updated = Date.now();
      all[said.document] = record;
      keep(DOCS, JSON.stringify(all));
    }
    if (window.TargumSync) {
      if (window.TargumSync.forgetSection) window.TargumSync.forgetSection(said.document, String(said.section));
      window.TargumSync.touched();
    }
    return taken;
  }

  window.TargumLanded = { carry: carry, take: take, say: say, undo: undo };
})();
