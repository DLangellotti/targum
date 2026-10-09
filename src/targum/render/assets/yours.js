/* Your targums — which is home since 2026-10-08 — and the lists behind the account.
 *
 * Which list this is comes from `window.TARGUM_LIST`: `texts` is the shelf under home's
 * Continue (`home.js` draws the head), `words` and `phrases` the lists behind the account.
 * The drawing is the same `TargumShelf` and `TargumLists` every page uses, so a row
 * cannot look one way here and another way there.
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
     the lists, on the phrases page: the record, which stands under Your Phrases, and the
     queue, the ones in it the reader has not said they know yet.

     Asked for after the lists are drawn rather than before, so a slow answer never holds
     up the phrases — the record appears a moment later, and a reader with none still
     sees nothing at all. */
  function drawRewrote() {
    if (!lists || !lists.rewrote || which !== "phrases") return;
    ask("/slips")
      .then(function (data) {
        lists.rewrote((data && data.slips) || []);
      })
      .catch(function () {});
    ask("/slips?all=1")
      .then(function (data) {
        lists.record((data && data.slips) || []);
      })
      .catch(function () {});
  }

  /* What the server knows about one language's word list (design.md §12, "Your Words is
     one table and a practice card", 2026-10-09): in how many texts each word was met, a
     line each word being learned was met in, and a row's note. Asked once a language,
     after the rows are drawn, and never in their way; signed out it is refused, and the
     table stands without them. Nothing about it spends. */
  var factsFor = "";

  function drawFacts(code, into) {
    if (which !== "words" || !lists || !lists.facts) return;
    var asked = code + ":" + (into || "");
    if (asked === factsFor) return;
    factsFor = asked;
    ask("/account/words?language=" + encodeURIComponent(code) + (into ? "&into=" + encodeURIComponent(into) : ""))
      .then(function (data) {
        lists.facts(code, data);
      })
      .catch(function () {});
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
   * Two tabs over one shelf — everything of yours, and only what you brought — then a
   * field to find one, and series folded into one row, last read first. The chips and the
   * order went with the cards (P4, 2026-10-09): board Main draws a find field and no
   * more. Playlists is a page of its own, and Subscriptions a table. */
  var view = {
    // Recent, Uploads or Subscriptions, from `?show=` (design.md §12, 2026-10-08); the
    // fourth tab, Playlists, is a page of its own.
    tab: (function () {
      var show = new URLSearchParams(location.search).get("show");
      return show === "uploads" || show === "subscriptions" ? show : "recent";
    })(),
    query: "",
    series: "",
  };

  // The find field is for a shelf long enough to need it.
  var SIFT_FROM = 6;

  /* An episode is read off its title, because nothing else says what a series is: a stem,
     then a separator and a marker with a number — "עברית אנפלאגד - פרק 63 | …", "Part 2",
     "глава 3", "#4", "S01E02", "פרק כג". A title that does not follow the pattern is its
     own row. Read with pointing and direction marks left out, so "פֶּרֶק" is a marker and
     a stray RLM does not split one series in two (targum-internal#376). */
  var MARKER = "(?:פרק|חלק|שיעור|episode|ep\\.?|part|pt\\.?|chapter|lesson|глава|часть|серия|выпуск|урок)";
  var NUMBER = "(\\d+|[א-ת]{1,2}(?![א-ת])|[א-ת]{1,3}[״\"][א-ת]|[א-ת][׳'])";
  var EPISODE = new RegExp(
    "^(.*?\\S)(?:[\\s\\-–—|:,.]+(?:" + MARKER + "\\s*" + NUMBER + "|s(\\d+)\\s*e(\\d+))|\\s*#(\\d+))",
    "i"
  );
  var SECOND = new RegExp(MARKER + "\\s*(\\d+)", "i");
  var GEMATRIA = { א: 1, ב: 2, ג: 3, ד: 4, ה: 5, ו: 6, ז: 7, ח: 8, ט: 9, י: 10, כ: 20, ך: 20,
    ל: 30, מ: 40, ם: 40, נ: 50, ן: 50, ס: 60, ע: 70, פ: 80, ף: 80, צ: 90, ץ: 90, ק: 100,
    ר: 200, ש: 300, ת: 400 };

  function counted(said) {
    if (/^\d+$/.test(said)) return parseInt(said, 10);
    var total = 0;
    said.replace(/[^א-ת]/g, "").split("").forEach(function (letter) {
      total += GEMATRIA[letter] || 0;
    });
    return total;
  }

  function plainTitle(title) {
    return String(title || "")
      .replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, "")
      .replace(/[\u0591-\u05bd\u05bf-\u05c7]/g, "");
  }

  // A stem is a name: two words, or one long one. "The" before "Chapter 11" is not.
  function aName(stem) {
    return stem.split(/\s+/).length >= 2 || stem.replace(/\s/g, "").length >= 8;
  }

  function episode(title) {
    var plain = plainTitle(title);
    var found = EPISODE.exec(plain);
    if (!found) return null;
    var stem = found[1].replace(/[\s\-–—|:,.]+$/, "");
    if (!stem || !aName(stem)) return null;
    var n = found[2] ? counted(found[2]) : found[3] ? parseInt(found[3], 10) * 1000 + parseInt(found[4], 10) : parseInt(found[5], 10);
    // A second marker after the first orders the texts that share it: Part 2, Chapter 3
    // before Part 2, Chapter 10.
    var after = SECOND.exec(plain.slice(found[0].length));
    return { stem: stem, n: n, m: after ? parseInt(after[1], 10) : 0, plain: plain };
  }

  function seriesKey(reader) {
    var found = episode(reader.title);
    return found ? shelf.base(reader.language) + "\n" + found.stem.toLowerCase() : "";
  }

  // Pointing and cantillation left out, so "הספר" finds "הַסֵּפֶר"; the maqaf is a space,
  // so "בית הספר" finds "בית־הספר".
  function plainText(text) {
    return String(text || "")
      .replace(/\u05be/g, " ")
      .replace(/[֑-ׇ]/g, "")
      .toLowerCase();
  }

  function isUpload(reader) {
    return !reader.entry && !reader.shared;
  }

  function onTab(reader) {
    return view.tab !== "uploads" || isUpload(reader);
  }

  function matches(reader) {
    var query = plainText(view.query).trim();
    return !query || plainText(reader.title + " " + (reader.english || "")).indexOf(query) >= 0;
  }

  /* Texts of one series become one row; a series left with one text is that text. A
     chip or a search decides which series show; the row still counts every episode of
     it on this tab, from `whole`, or pressing Finished said "2 episodes, Finished" of a
     series of five (2026-09-27). */
  function fold(readers, whole) {
    var by = {};
    readers.forEach(function (reader) {
      var at = seriesKey(reader);
      if (at) (by[at] = by[at] || []).push(reader);
    });
    var all = {};
    (whole || readers).forEach(function (reader) {
      var at = seriesKey(reader);
      if (at) (all[at] = all[at] || []).push(reader);
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
        members: all[at] || by[at],
      });
    });
    return out;
  }

  // Last read first, a series answering for its latest text; then what came last.
  function latest(thing, of) {
    if (!thing.members) return of(thing);
    return thing.members.map(of).reduce(function (a, b) {
      return Math.max(a, b);
    });
  }

  function byRead(a, b) {
    function opened(r) {
      return r.opened || 0;
    }
    function built(r) {
      return r.built || 0;
    }
    return latest(b, opened) - latest(a, opened) || latest(b, built) - latest(a, built);
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

      /* Home (design.md §12, "Home is Your targums, and Continue leads it", 2026-10-08):
         Continue, one text to try next and the way to upload stand over the shelf, and
         `home.js` draws them. A reader with nothing yet still has a page: it says what
         will appear here, and offers one to start with and the upload. */
      var home = window.TargumHome || null;
      var nothingYet = !readers.length && !building.length;
      var tabStrip = document.getElementById("yours-tabs");
      // Subscriptions answer even with nothing on the shelf: a reader may subscribe
      // before they open anything (design.md §12, 2026-10-09).
      if (tabStrip) tabStrip.hidden = nothingYet && view.tab !== "subscriptions";
      document.getElementById("shelf-panel").hidden = nothingYet;
      var grid = document.querySelector(".home-grid");
      if (grid) grid.classList.toggle("is-empty", nothingYet);
      var shown = "";

      var find = document.getElementById("shelf-find");
      var inSeries = document.getElementById("in-series");
      var tabs = document.querySelectorAll("#yours-tabs [data-tab]");

      /* Subscriptions (design.md §12, "A subscription is the account's", 2026-10-09):
         every subscription as a row, drawn by `subs.js` (`TargumSubs.drawTab`), which
         falls back to `follow.js`'s list of series for a reader signed out. */
      var subsPanel = document.getElementById("subs-panel");
      function drawSubscriptions() {
        var subs = window.TargumSubs;
        if (!subsPanel || !subs) return;
        subs.drawTab(subsPanel);
      }

      /* The one strip of tabs stands in the head of the card of rows on Recent and
         Uploads (board Main), and under the page's title on Subscriptions, which is the
         page's whole width with nothing of Continue's beside it (board SubsTab). */
      var top = document.getElementById("yours-top");
      var head = document.getElementById("yours-head");
      function placeTabs(subscribing) {
        if (!tabStrip || !top || !head) return;
        var host = subscribing ? top : head;
        if (tabStrip.parentNode !== host) host.appendChild(tabStrip);
        top.hidden = !subscribing;
        if (document.body && document.body.classList) document.body.classList.toggle("is-subscribing", subscribing);
      }

      function render() {
        var subscribing = view.tab === "subscriptions";
        if (subsPanel) subsPanel.hidden = !subscribing;
        document.getElementById("shelf-panel").hidden = subscribing || nothingYet;
        if (tabStrip) tabStrip.hidden = nothingYet && !subscribing;
        placeTabs(subscribing);
        if (subscribing) {
          drawSubscriptions();
          return;
        }
        var heading = document.getElementById("shelf-title");
        if (heading) {
          heading.textContent =
            view.tab === "uploads"
              ? t("yours.list.uploads", "Uploaded by you")
              : t("yours.list.all", "All your targums");
        }
        var mine = readers.filter(function (reader) {
          return shelf.base(reader.language) === shown && onTab(reader);
        });
        find.hidden = mine.length < SIFT_FROM;
        // Nothing sifts what cannot be seen: a search typed on All targums went on
        // emptying Your uploads, which draws no box to clear it from (2026-09-27).
        if (find.hidden) {
          view.query = "";
          find.value = "";
        }
        var sifted = mine.filter(matches);

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
                var one = episode(a.title);
                var two = episode(b.title);
                return one.n - two.n || one.m - two.m;
              })
              .map(function (reader) {
                var found = episode(reader.title);
                var rest = found.plain.slice(found.stem.length).replace(/^[\s\-–—|:,.]+/, "");
                return Object.assign({}, reader, { shownTitle: rest || reader.title });
              });
          } else {
            view.series = "";
          }
        }
        if (!group) rows = fold(sifted, mine).sort(byRead);

        inSeries.hidden = !group;
        if (group) {
          var name = document.getElementById("series-name");
          name.textContent = episode(group[0].title).stem;
          name.setAttribute("lang", group[0].language || "und");
        }

        // A build is shown on the whole shelf, before anything is sifted out of it.
        var plain = !group && !view.query;
        var empty = "";
        if (!rows.length && mine.length) {
          empty = t("yours.sift.none-found", "Nothing here matches that. Try another search.");
        } else if (!rows.length && view.tab === "uploads") {
          empty = t("yours.uploads.none", "Nothing you’ve uploaded yet. What you paste, upload or link is kept here.");
        } else if (!rows.length) {
          // The rows are handed over already sifted, so `shelf.draw` cannot tell an empty
          // language from an empty shelf; this can.
          empty = t("shelf.empty.language", "Nothing in {language} yet.", { language: names[shown] || shown });
        }
        shelf.draw(shown, rows, {
          note: "",
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
        if (!nothingYet || view.tab === "subscriptions") render();
        // The head of home, in the same language; the page is shown once it is drawn, so
        // a reader sent on to the arrival never sees it flash first.
        var drawn = home ? home.draw(code, readers, building) : Promise.resolve(true);
        return drawn
          .catch(function () {
            return true;
          })
          .then(function (stay) {
            if (stay === false) return;
            var waiting = document.getElementById("home-waiting");
            if (waiting) waiting.hidden = true;
            document.getElementById("page").hidden = false;
          });
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
          if (view.tab !== "recent") query.set("show", view.tab);
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
              if (home) home.draw(shown, readers, building);
              return follow();
            }
            return ask("/readers").then(function (data) {
              readers = gather(data, stored("targum:opened"));
              trash = (data && data.trash) || trash;
              render();
              // Continue's card for the build becomes the text it built.
              if (home) home.draw(shown, readers, building);
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
      var into = charts.meaningLanguage(shown);
      lists.draw(shown, charts.collect(into)[shown]);
      drawFacts(shown, into);
    });

    var shown = "";

    function show(code) {
      shown = code;
      lang.set(code);
      lang.switcher(document.getElementById("langs"), codes, names, code, show);
      // Re-collected rather than sliced out of `data`: which language the meanings are
      // in is a question about the language being shown, and the answer changes with it.
      var into = charts.meaningLanguage(code);
      lists.draw(code, charts.collect(into)[code]);
      drawFacts(code, into);
    }

    show(lang.current(codes));
    return Promise.resolve();
  }

  var drawing = which === "texts" ? drawTexts() : drawKept();
  // After the lists, and never in their way: the phrases appear first and the record of
  // corrected lines a moment later.
  drawing.then(drawRewrote).catch(function () {});

  drawing.catch(function () {
    // Signed out, or the server went away. The nav is still there to leave by.
    var waiting = document.getElementById("home-waiting");
    if (waiting) waiting.hidden = true;
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
