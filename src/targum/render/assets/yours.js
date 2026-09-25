/* One of Learn's lists, whole.
 *
 * Learn caps every list it shows and points here for the rest. Which list this is comes
 * from `window.TARGUM_LIST`; the drawing is the same `TargumShelf` and `TargumLists` that
 * Learn uses, so a row cannot look one way there and another way here.
 *
 * The language switcher is the same one too, and it decides what a list holds: words are
 * kept per language, and a shelf of Hebrew is not a shelf of Russian.
 */

(function () {
  "use strict";

  /* Words said through the page's `TargumStrings`, looked up when a thing is said: this
     file runs before the page has handed its strings over. Where there are none, the
     English here (targum-internal#184). */
  function t(key, english, fill) {
    var said = window.TargumStrings;
    if (said) return said.t(key, english, fill);
    return english.replace(/\{(\w+)\}/g, function (all, name) {
      return fill && Object.prototype.hasOwnProperty.call(fill, name) ? String(fill[name]) : all;
    });
  }
  function tn(key, count, one, other, fill) {
    var said = window.TargumStrings;
    if (said) return said.tn(key, count, one, other, fill);
    var values = { n: count };
    for (var name in fill || {}) values[name] = fill[name];
    return t(key, count === 1 ? one : other, values);
  }

  var key = window.TARGUM_KEY;

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  var which = window.TARGUM_LIST || "words";
  var charts = window.TargumCharts;
  var lists = window.TargumLists;
  var shelf = window.TargumShelf;
  var lang = window.TargumLang;
  var names = window.TARGUM_LANGUAGES || {};

  Array.prototype.forEach.call(
    document.querySelectorAll(".site-nav a, .upload, [data-back]"),
    function (link) {
      link.href = keyed(link.getAttribute("href"));
    }
  );

  function ask(path) {
    return fetch(keyed(path), { headers: keyHeaders({ "Content-Type": "application/json" }) }).then(
      function (response) {
        return response.json();
      }
    );
  }

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  /* The lines that came back changed (targum-internal#290), fetched once and handed to
     the lists. Twice on the words page and once on the phrases page: the queue, which is
     the fold's Phrases tab and exists only where the fold does, and the record, which
     stands under Your Phrases wherever that list is.

     Asked for after the lists are drawn rather than before, so a slow answer never holds
     up the words — the fold appears with its words and gains its lines a moment later,
     and a reader with neither still sees nothing at all. */
  function drawRewrote() {
    if (!lists || !lists.rewrote) return;
    if (which === "words") {
      ask("/slips")
        .then(function (data) {
          lists.rewrote((data && data.slips) || []);
        })
        .catch(function () {});
    }
    if (which === "words" || which === "phrases") {
      ask("/slips?all=1")
        .then(function (data) {
          lists.record((data && data.slips) || []);
        })
        .catch(function () {});
    }
  }

  /* --- the shelf ------------------------------------------------------------- */

  /* Everything of yours (design.md §12, "Yours and everyone's", 2026-09-25): what you
     built, what you brought, what is being built right now, and the shared texts this
     browser has opened. The builds come from `/jobs`, the same answer the bell reads. */
  function gather(data, opened) {
    var readers = ((data && data.readers) || []).slice();
    var have = {};
    readers.forEach(function (reader) {
      reader.opened = opened[reader.document] || 0;
      have[reader.document] = true;
      if (reader.entry) have["entry:" + reader.entry] = true;
    });
    /* The shared shelf is the Library's until you open one of it. After that it is
       something you started, and this is where a reader goes back to what they started.
       "Opened" is this browser's record (`targum:opened`), the same one every "last
       read" on the site reads. A shared row offers nothing to delete: `shelf.js` knows
       it by `shared`. */
    ((data && data.shared) || []).forEach(function (reader) {
      var when = opened[reader.document] || 0;
      if (!when || have[reader.document] || (reader.entry && have["entry:" + reader.entry])) return;
      reader.opened = when;
      readers.push(reader);
    });
    readers.sort(function (a, b) {
      return b.opened - a.opened || b.built * 1000 - a.built * 1000;
    });
    return readers;
  }

  function drawTexts() {
    var opened = stored("targum:opened");
    var jobs = function () {
      return ask("/jobs").catch(function () {
        return {};
      });
    };
    return Promise.all([ask("/readers"), jobs()]).then(function (both) {
      var readers = gather(both[0], opened);
      var trash = (both[0] && both[0].trash) || [];
      var building = shelf.building((both[1] && both[1].jobs) || []);

      var codes = [lang.HOME];
      readers.concat(building).forEach(function (thing) {
        var code = shelf.base(thing.language);
        if (code && codes.indexOf(code) < 0) codes.push(code);
      });
      codes = lang.order(codes, names);

      if (!readers.length && !building.length) {
        document.getElementById("nothing").hidden = false;
        return;
      }
      document.getElementById("page").hidden = false;
      var shown = "";

      function show(code) {
        shown = code;
        lang.set(code);
        lang.switcher(document.getElementById("langs"), codes, names, code, show);
        // No ceiling: this page is the whole of it, which is what it is for.
        shelf.draw(code, readers, {
          note: t("yours.last-read-first", "Last read first."),
          building: building,
        });
        shelf.trash(code, trash);
      }

      show(lang.current(codes));

      /* While anything is building, ask again every three seconds, and only while: a page
         left open overnight should not ask a question every three seconds until morning.
         When a build finishes, `/readers` has the text it became, so both are asked for
         and the build's row turns into the ordinary one in the same draw. */
      function follow() {
        if (!building.length) return;
        setTimeout(function () {
          jobs().then(function (answer) {
            var now = shelf.building((answer && answer.jobs) || []);
            var still = {};
            now.forEach(function (job) {
              still[job.id] = true;
            });
            // By id rather than by count: a build started while another finished is the
            // same count and a different shelf.
            var finished = building.some(function (job) {
              return !still[job.id];
            });
            building = now;
            if (!finished) {
              show(shown);
              return follow();
            }
            return ask("/readers").then(function (data) {
              readers = gather(data, stored("targum:opened"));
              trash = (data && data.trash) || trash;
              show(shown);
              follow();
            });
          })
          // A dropped poll is a dropped poll: the build carries on without this page.
          .catch(follow);
        }, 3000);
      }
      follow();
    });
  }

  /* --- the words and the phrases ---------------------------------------------- */

  function drawKept() {
    if (window.TargumVocab) window.TargumVocab.migrate();
    var data = charts.collect();
    var codes = lang.order(Object.keys(data), names);
    if (!codes.length) {
      document.getElementById("nothing").hidden = false;
      return Promise.resolve();
    }
    document.getElementById("page").hidden = false;

    lists.mount({
      languages: names,
      // The ledger changed under the list — a page of common words marked known — so
      // the rows are collected again rather than drawn from a store that is now stale.
      onChanged: function () {
        if (shown) show(shown);
      },
    });
    // Picking another language for the meanings redraws the same rows with the other
    // answer in them. The words themselves do not move: they are the same words.
    lists.onMeaningLanguage(function () {
      lists.draw(shown, charts.collect(charts.meaningLanguage(shown))[shown]);
    });

    var shown = "";

    function show(code) {
      shown = code;
      lang.set(code);
      lang.switcher(document.getElementById("langs"), codes, names, code, show);
      // Re-collected rather than sliced out of `data`: which language the meanings are
      // in is a question about the language being shown, and the answer changes with it.
      lists.draw(code, charts.collect(charts.meaningLanguage(code))[code]);
    }

    show(lang.current(codes));
    return Promise.resolve();
  }

  var drawing = which === "texts" ? drawTexts() : drawKept();
  // After the lists, and never in their way: the fold appears with its words and gains
  // its rewritten lines a moment later.
  drawing.then(drawRewrote).catch(function () {});

  drawing.catch(function () {
    // Signed out, or the server went away. The nav is still there to leave by.
    document.getElementById("nothing").hidden = false;
  });

  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (changed) location.reload();
    });
    window.TargumSync.start().then(function () {
      if (lists) lists.offerExports(!!window.TargumSync.who);
    });
  }
})();
