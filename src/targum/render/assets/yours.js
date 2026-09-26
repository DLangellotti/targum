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

  /* --- sifting the shelf (design.md §12, "Your targums has tabs", 2026-09-26) ----------
   *
   * Two tabs over one shelf — everything of yours, and only what you brought — then
   * chips for where you are with a text, a search, an order, and series folded into one
   * row. The third tab, Playlists, is a page of its own. */
  var view = {
    tab: new URLSearchParams(location.search).get("show") === "uploads" ? "uploads" : "all",
    status: "all",
    query: "",
    order: "read",
    series: "",
  };

  // Chips, search and order are for a shelf long enough to need them.
  var SIFT_FROM = 6;

  /* An episode is read off its title, because nothing else says what a series is: a stem,
     then a separator and a marker with a number — "עברית אנפלאגד - פרק 63 | …", "Part 2",
     "глава 3", "#4". A title that does not follow the pattern is its own row. */
  var EPISODE =
    /^(.*?\S)(?:[\s\-–—|:,.]+(?:פרק|חלק|שיעור|episode|ep\.?|part|chapter|lesson|глава|часть|серия|выпуск|урок)\s*|\s*#)(\d+)/i;

  function episode(title) {
    var found = EPISODE.exec(title || "");
    if (!found) return null;
    var stem = found[1].replace(/[\s\-–—|:,.]+$/, "");
    return stem ? { stem: stem, n: parseInt(found[2], 10) } : null;
  }

  function seriesKey(reader) {
    var found = episode(reader.title);
    return found ? shelf.base(reader.language) + "\n" + found.stem.toLowerCase() : "";
  }

  // Pointing and cantillation left out, so "הספר" finds "הַסֵּפֶר".
  function plainText(text) {
    return String(text || "")
      .replace(/[֑-ׇ]/g, "")
      .toLowerCase();
  }

  function isUpload(reader) {
    return !reader.entry && !reader.shared;
  }

  function onTab(reader) {
    return view.tab === "all" || isUpload(reader);
  }

  function matches(reader) {
    var query = plainText(view.query).trim();
    return !query || plainText(reader.title + " " + (reader.english || "")).indexOf(query) >= 0;
  }

  /* Texts of one series become one row; a series left with one text is that text. */
  function fold(readers) {
    var by = {};
    readers.forEach(function (reader) {
      var at = seriesKey(reader);
      if (at) (by[at] = by[at] || []).push(reader);
    });
    var placed = {};
    var out = [];
    readers.forEach(function (reader) {
      var at = seriesKey(reader);
      if (!at || by[at].length < 2) return out.push(reader);
      if (placed[at]) return;
      placed[at] = true;
      out.push({
        key: at,
        title: episode(reader.title).stem,
        language: reader.language,
        members: by[at],
      });
    });
    return out;
  }

  var CEFR = ["A1", "A1+", "A2", "A2+", "B1", "B1+", "B2", "B2+", "C1", "C2"];

  function difficulty(reader) {
    var at = reader.level && reader.level.cefr ? CEFR.indexOf(reader.level.cefr) : -1;
    return at < 0 ? CEFR.length : at;
  }

  function known(reader) {
    return typeof reader.known === "number" && reader.words ? reader.known : -1;
  }

  // One number per row for each order, a series answering for its best text.
  function measure(thing, of, best) {
    if (!thing.members) return of(thing);
    return thing.members.map(of).reduce(function (a, b) {
      return best(a, b);
    });
  }

  var ORDERS = {
    read: function (a, b) {
      return (
        measure(b, function (r) { return r.opened || 0; }, Math.max) -
          measure(a, function (r) { return r.opened || 0; }, Math.max) ||
        ORDERS.added(a, b)
      );
    },
    added: function (a, b) {
      return (
        measure(b, function (r) { return r.built || 0; }, Math.max) -
        measure(a, function (r) { return r.built || 0; }, Math.max)
      );
    },
    easy: function (a, b) {
      return measure(a, difficulty, Math.min) - measure(b, difficulty, Math.min) || ORDERS.read(a, b);
    },
    known: function (a, b) {
      return measure(b, known, Math.max) - measure(a, known, Math.max) || ORDERS.read(a, b);
    },
  };

  function chip(label, value, count) {
    var press = document.createElement("button");
    press.type = "button";
    press.className = "chip";
    press.setAttribute("aria-pressed", String(view.status === value));
    press.appendChild(document.createTextNode(label + " "));
    var n = document.createElement("span");
    n.className = "chip-n";
    n.textContent = String(count);
    press.appendChild(n);
    return press;
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

      var sift = document.getElementById("sift-shelf");
      var chips = document.getElementById("status-chips");
      var find = document.getElementById("shelf-find");
      var order = document.getElementById("shelf-order");
      var inSeries = document.getElementById("in-series");
      var tabs = document.querySelectorAll("#yours-tabs [data-tab]");

      function drawChips(pool) {
        var counts = { all: pool.length, new: 0, reading: 0, finished: 0 };
        pool.forEach(function (reader) {
          counts[shelf.status(reader).kind] += 1;
        });
        chips.textContent = "";
        [
          ["all", t("yours.sift.all", "All")],
          ["new", t("yours.sift.new", "New")],
          ["reading", t("yours.sift.reading", "Started")],
          ["finished", t("yours.sift.finished", "Finished")],
        ].forEach(function (pair) {
          if (pair[0] !== "all" && !counts[pair[0]]) return;
          var press = chip(pair[1], pair[0], counts[pair[0]]);
          press.onclick = function () {
            view.status = view.status === pair[0] ? "all" : pair[0];
            render();
          };
          chips.appendChild(press);
        });
      }

      function render() {
        var mine = readers.filter(function (reader) {
          return shelf.base(reader.language) === shown && onTab(reader);
        });
        var searched = mine.filter(matches);
        var sifted = searched.filter(function (reader) {
          return view.status === "all" || shelf.status(reader).kind === view.status;
        });
        sift.hidden = mine.length < SIFT_FROM;
        if (!sift.hidden) drawChips(searched);

        var rows;
        var group = null;
        if (view.series) {
          var members = sifted.filter(function (reader) {
            return seriesKey(reader) === view.series;
          });
          if (members.length) {
            group = members;
            rows = members
              .slice()
              .sort(function (a, b) {
                return episode(a.title).n - episode(b.title).n;
              })
              .map(function (reader) {
                var found = episode(reader.title);
                var rest = reader.title.slice(found.stem.length).replace(/^[\s\-–—|:,.]+/, "");
                return Object.assign({}, reader, { shownTitle: rest || reader.title });
              });
          } else {
            view.series = "";
          }
        }
        if (!group) rows = fold(sifted).sort(ORDERS[view.order]);

        inSeries.hidden = !group;
        if (group) {
          var name = document.getElementById("series-name");
          name.textContent = episode(group[0].title).stem;
          name.setAttribute("lang", group[0].language || "und");
        }

        // A build is shown on the whole shelf, before anything is sifted out of it.
        var plain = !group && view.status === "all" && !view.query;
        var empty = "";
        if (!rows.length && mine.length) {
          empty = t("yours.sift.none", "Nothing here matches that.");
        } else if (!rows.length && view.tab === "uploads") {
          empty = t("yours.uploads.empty", "Nothing you've brought yet. What you add is kept here.");
        } else if (!rows.length) {
          // The rows are handed over already sifted, so `shelf.draw` cannot tell an empty
          // language from an empty shelf; this can.
          empty = t("shelf.empty.language", "Nothing in {language} yet.", { language: names[shown] || shown });
        }
        shelf.draw(shown, rows, {
          note: sift.hidden && !group && view.order === "read" ? t("yours.last-read-first", "Last read first.") : "",
          building: plain ? building : [],
          empty: empty,
          onSeries: function (folded) {
            view.series = folded.key;
            render();
            window.scrollTo({ top: 0 });
          },
        });
        shelf.trash(shown, trash);
      }

      function show(code) {
        shown = code;
        view.series = "";
        lang.set(code);
        lang.switcher(document.getElementById("langs"), codes, names, code, show);
        // No ceiling: this page is the whole of it, which is what it is for.
        render();
      }

      Array.prototype.forEach.call(tabs, function (link) {
        if (link.getAttribute("data-tab") === "playlists") return;
        link.addEventListener("click", function (event) {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
          event.preventDefault();
          view.tab = link.getAttribute("data-tab");
          view.series = "";
          Array.prototype.forEach.call(tabs, function (other) {
            if (other === link) other.setAttribute("aria-current", "page");
            else other.removeAttribute("aria-current");
          });
          // The address says the tab, so a reload or a shared link opens on it. Only the
          // query changes: the key in it stays, and so does the path.
          var query = new URLSearchParams(location.search);
          if (view.tab === "uploads") query.set("show", "uploads");
          else query.delete("show");
          var search = query.toString();
          try {
            history.replaceState(null, "", location.pathname + (search ? "?" + search : ""));
          } catch (e) {
            // Nowhere to write it; the tab is still shown.
          }
          render();
        });
      });
      Array.prototype.forEach.call(tabs, function (link) {
        if (link.getAttribute("data-tab") === view.tab) link.setAttribute("aria-current", "page");
        else if (link.getAttribute("data-tab") !== "playlists") link.removeAttribute("aria-current");
      });
      find.addEventListener("input", function () {
        view.query = find.value;
        render();
      });
      order.addEventListener("change", function () {
        view.order = order.value;
        render();
      });
      document.getElementById("series-back").addEventListener("click", function () {
        view.series = "";
        render();
      });

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
              render();
              return follow();
            }
            return ask("/readers").then(function (data) {
              readers = gather(data, stored("targum:opened"));
              trash = (data && data.trash) || trash;
              render();
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
