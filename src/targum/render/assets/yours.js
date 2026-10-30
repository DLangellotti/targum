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

  /* What home's head already asked for (`home-early.js`, targum-internal#555), each taken
     once and only by `askFirst`: every later ask, a build's poll among them, is fresh. */
  var askedEarly = window.TARGUM_HOME_ASKED || {};
  function early(path) {
    var going = askedEarly[path];
    delete askedEarly[path];
    return going;
  }
  function askFirst(path) {
    return ask(path, early(path));
  }

  /* A refusal is not an answer (home QA, 2026-10-18): a 500 whose body happened to be
     JSON was read as a shelf with nothing on it, and home told a reader with six texts
     "Nothing here yet". Every caller catches, so a refusal lands where a dropped
     connection does. */
  function ask(path, sent) {
    var going = sent || fetch(keyed(path), { headers: keyHeaders({ "Content-Type": "application/json" }) });
    return going.then(
      function (response) {
        if (!response.ok) {
          var refused = new Error(String(response.status));
          refused.answered = true;
          throw refused;
        }
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
  function gather(data, opened, places) {
    var readers = ((data && data.readers) || []).slice();
    var have = {};
    /* Opened on another device counts as opened here (home QA, 2026-10-18): Continue
       said "Pick up at chapter 3" from the account's place while the row under it said
       New, because "opened" was only ever this browser's record. The account's place is
       when it was last read, so it orders Recent too. */
    var read = {};
    (places || []).forEach(function (place) {
      if (!place || !place.hash) return;
      read[place.hash] = Math.max(read[place.hash] || 0, Number(place.at || 0));
    });
    opened = Object.assign({}, opened);
    Object.keys(read).forEach(function (hash) {
      opened[hash] = Math.max(Number(opened[hash] || 0), read[hash]);
    });
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

  /* Texts read that are on no shelf (known-issues 1.17): a Torah portion and a daily
     page are cut once for everybody and served from their own addresses, so `/readers`
     never lists them and Recent left out the portion home said was finished. Their places
     name them — the account's rows carry the title, and this browser's own record of the
     text names it where the account has not yet heard (targum#768) — so each is a row
     here too, newest place first, opening where the reader left off. Only addresses that
     are not a reader folder: a folder's text is on the shelf or was taken off it, and a
     text taken off stays off. */
  var KINDS_BY_PATH = [
    [/^\/parasha\//, "prose"],
    [/^\/(tanakh-yomi|nach-yomi)\//, "prose"],
    [/^\/tehillim\//, "poetry"],
  ];

  function away(theirs, readers) {
    var places = stored("targum:places");
    var docs = stored("targum:docs");
    var all = {};
    Object.keys(places).forEach(function (hash) {
      all[hash] = Object.assign({}, places[hash] || {});
    });
    (theirs || []).forEach(function (row) {
      if (!row || !row.hash) return;
      var mine = all[row.hash];
      if (!mine || Number(row.at || 0) > Number(mine.at || 0)) {
        all[row.hash] = Object.assign({}, row, {
          title: row.title || (mine && mine.title) || "",
          language: row.language || (mine && mine.language) || "",
        });
      } else {
        mine.title = mine.title || row.title || "";
        mine.language = mine.language || row.language || "";
      }
    });
    var have = {};
    readers.forEach(function (reader) {
      if (reader.document) have[reader.document] = true;
    });
    var rows = [];
    Object.keys(all).forEach(function (hash) {
      var place = all[hash] || {};
      var path = String(place.path || "");
      if (have[hash] || !path || path.indexOf("/reader/") === 0 || path.charAt(0) !== "/") return;
      var doc = docs[hash] || {};
      var title = place.title || doc.title || "";
      var language = place.language || doc.language || "";
      if (!title || !language) return;
      var kind = "";
      KINDS_BY_PATH.forEach(function (pair) {
        if (!kind && pair[0].test(path)) kind = pair[1];
      });
      rows.push({
        document: hash,
        name: "",
        title: title,
        language: language,
        kind: kind,
        href: path,
        opened: Number(place.at || 0) || Number(doc.updated || 0),
        shared: true,
        away: true,
      });
    });
    return rows;
  }

  function accountPlaces() {
    // Home asked the same question as the page opened (`home.js`, #484): read its answer.
    var home = window.TargumHome;
    if (home && home.asked) return home.asked();
    return ask("/account/places?limit=20")
      .then(function (answer) {
        return (answer && answer.places) || [];
      })
      .catch(function () {
        // Signed out, or the box went away: this browser's own places are all there are.
        return [];
      });
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
    // Every row, once Show more is pressed; the first few until then (audit Q7).
    all: false,
  };

  // How many rows the shelf draws before Show more (board Main draws a short list), and
  // how many it must be hiding before the press is worth drawing at all.
  var SHOW_FIRST = 8;
  var SHOW_MORE_FROM = 3;

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

  /* The account hears what this browser holds before the shelf is measured against it
     (QA, 2026-10-12). The first Done in a language comes straight here, and its marks were
     still on their way: the line said "+79 known · 98%" over a card that said "You know
     0%". Only when something is owed, so a home with nothing new asks at once, and never
     for longer than a few seconds: a slow push costs the figure, not the page.

     Only words owed (targum-internal#555): the figures are measured against the account's
     words and nothing else, and a place or an opened text is owed by every reader back
     from a text, which held the shelf a round trip or two behind the account. Null when
     nothing is waited for, so the shelf the page's head asked for is the one used. Before
     the account has answered, the push is the one its first answer makes (`settled`),
     rather than a second start of its own. */
  var CAUGHT_UP_MS = 4000;
  function caughtUp() {
    var sync = window.TargumSync;
    var owed = 0;
    try {
      owed = sync && sync.flush ? (sync.owedWords ? sync.owedWords() : sync.owed ? sync.owed() : 0) : 0;
    } catch (e) {
      owed = 0;
    }
    if (!owed) return null;
    var pushing = !sync.who && sync.settled ? sync.settled() : sync.flush();
    return Promise.race([
      Promise.resolve(pushing).catch(function () {}),
      new Promise(function (resolve) {
        setTimeout(resolve, CAUGHT_UP_MS);
      }),
    ]);
  }

  /* Home drawn again in place once the account has answered (2026-10-18). A browser that
     had never synced reloaded the whole page when `/sync` came back, and with a big shelf
     that made a first visit about five seconds: two loads, the second of everything the
     first had just drawn. What the answer changes is in this browser's own store (which
     texts were opened, the places, the words), so the shelf, Continue and the counts are
     drawn again from it, and nothing the server already answered is asked again. Set
     once home is drawn; an answer that comes before then is kept for it. */
  var redrawHome = null;
  var owedRedraw = false;

  /* Subscriptions shown on its own answer (targum-internal#555). Nothing of the shelf is
     on that tab: Continue, the side and the welcome back stand down under `is-subscribing`
     (home.css), and the table is `subs.js`'s, from `/subscriptions.json`, which is asked
     as the page opens. So it waited on `/readers` for nothing. The page is shown here with
     the tab and its table as they will be once the shelf is in, and the shelf's own draw
     after it leaves the table as it found it.

     Not where home may yet send this reader on to the arrival (`home.js`, `arriving`),
     which takes the shelf to decide: a page shown and then left is a flash. */
  var subsDrawnFirst = false;
  function subscriptionsFirst() {
    if (view.tab !== "subscriptions") return;
    var home = window.TargumHome;
    var subs = window.TargumSubs;
    var panel = document.getElementById("subs-panel");
    if (!home || !home.mayArrive || home.mayArrive() || !subs || !panel) return;
    var tabStrip = document.getElementById("yours-tabs");
    var top = document.getElementById("yours-top");
    panel.hidden = false;
    document.getElementById("shelf-panel").hidden = true;
    if (tabStrip) {
      tabStrip.hidden = false;
      if (top && tabStrip.parentNode !== top) top.appendChild(tabStrip);
    }
    if (top) top.hidden = false;
    if (document.body && document.body.classList) document.body.classList.add("is-subscribing");
    Array.prototype.forEach.call(document.querySelectorAll("#yours-tabs [data-tab]"), function (link) {
      if (link.getAttribute("data-tab") === view.tab) link.setAttribute("aria-current", "page");
      else if (link.getAttribute("data-tab") !== "playlists") link.removeAttribute("aria-current");
    });
    subs.drawTab(panel);
    subsDrawnFirst = true;
    var waiting = document.getElementById("home-waiting");
    if (waiting) waiting.hidden = true;
    document.getElementById("page").hidden = false;
  }

  function drawTexts() {
    var opened = stored("targum:opened");
    var jobs = function (first) {
      return (first ? askFirst : ask)("/jobs").catch(function () {
        return {};
      });
    };
    // The shelf asked by the page's head, unless words are owed: then that answer was
    // measured before them, and the shelf is asked again once they are pushed.
    var pushing = caughtUp();
    var shelfAnswer = pushing
      ? (early("/readers"),
        pushing.then(function () {
          return ask("/readers");
        }))
      : askFirst("/readers");
    subscriptionsFirst();
    return Promise.all([shelfAnswer, jobs(true), accountPlaces()]).then(function (both) {
      var theirPlaces = both[2];
      var readers = gather(both[0], opened, theirPlaces);
      var trash = (both[0] && both[0].trash) || [];
      var building = shelf.building((both[1] && both[1].jobs) || []);
      // Portions and daily pages, for Recent only: home draws its own Continue from the
      // places, so they are kept out of the readers it is handed.
      var elsewhere = away(both[2], readers);

      var codes = [lang.HOME];
      readers.concat(building, elsewhere).forEach(function (thing) {
        var code = shelf.base(thing.language);
        if (code && codes.indexOf(code) < 0) codes.push(code);
      });
      codes = lang.order(codes, names);

      /* Home (design.md §12, "Home is Your targums, and Continue leads it", 2026-10-08):
         Continue, one text to try next and the way to upload stand over the shelf, and
         `home.js` draws them. A reader with nothing yet still has a page: it says what
         will appear here, and offers one to start with and the upload. */
      var home = window.TargumHome || null;
      var nothingYet = !readers.length && !building.length && !elsewhere.length;
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
        // Drawn already, on the same answer, before the shelf came in.
        if (subsDrawnFirst) {
          subsDrawnFirst = false;
          return;
        }
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
        var mine = readers.concat(elsewhere).filter(function (reader) {
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
        // The first rows, and the rest behind Show more; a search or a series is shown
        // whole, since there the reader has already said what they want.
        var moreRows = document.getElementById("shelf-more-rows");
        var capped = !group && !view.query && !view.all && rows.length >= SHOW_FIRST + SHOW_MORE_FROM;
        if (capped) rows = rows.slice(0, SHOW_FIRST);
        if (moreRows) moreRows.hidden = !capped;
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
        view.all = false;
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
          view.all = false;
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
      var moreButton = document.getElementById("shelf-more-rows");
      if (moreButton) {
        moreButton.addEventListener("click", function () {
          view.all = true;
          render();
        });
      }

      show(lang.current(codes));

      redrawHome = function () {
        readers = gather(both[0], stored("targum:opened"), theirPlaces);
        elsewhere = away(theirPlaces, readers);
        var found = [lang.HOME];
        readers.concat(building, elsewhere).forEach(function (thing) {
          var code = shelf.base(thing.language);
          if (code && found.indexOf(code) < 0) found.push(code);
        });
        codes = lang.order(found, names);
        nothingYet = !readers.length && !building.length && !elsewhere.length;
        if (tabStrip) tabStrip.hidden = nothingYet && view.tab !== "subscriptions";
        document.getElementById("shelf-panel").hidden = nothingYet;
        if (grid) grid.classList.toggle("is-empty", nothingYet);
        // In the language the account last chose, as the reload opened in.
        return show(lang.current(codes));
      };
      if (owedRedraw) {
        owedRedraw = false;
        redrawHome();
      }

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
              readers = gather(data, stored("targum:opened"), theirPlaces);
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
      // Not before the account has answered (2026-10-10): on a browser just signed in,
      // the words are on their way, and "nothing yet" read as everything deleted.
      var sync = window.TargumSync;
      var answered = sync && sync.settled ? sync.settled() : Promise.resolve(false);
      awaitingAccount = true;
      return answered.then(function (changed) {
        awaitingAccount = false;
        /* What the account brought is in this browser now, so it is drawn from here
           rather than by loading the page again: on a phone the reload took a first visit
           to Your Words from 1.3 s to 3.2 s (Your Words QA, 2026-10-20). */
        if (changed) {
          var brought = lang.order(Object.keys(charts.collect()), names);
          if (brought.length) return drawLists(brought);
        }
        /* Your Words QA (2026-10-20): the account answered and holds nothing in any
           language, which is every new reader — the page itself, empty, with the line
           that says what fills it and the commonest words to start from. Where the
           account never answered (a refusal, a dropped connection, offline), the list
           is not known to be empty, and the page says it could not load. */
        if (sync && !sync.reached) {
          var failed = new Error("unanswered");
          failed.answered = true; // said as ours to load, whichever way it failed
          throw failed;
        }
        var learning = (sync && sync.who && sync.who.learning) || [];
        var first = lang.current(learning.length ? lang.order(learning, names) : ["he"]);
        return drawLists([first]);
      });
    }
    return drawLists(codes);
  }

  //: True while a page with nothing in this browser waits on the account's first answer,
  //: which it draws itself; a change announced meanwhile is not a reason to reload.
  var awaitingAccount = false;

  function drawLists(codes) {
    var waiting = document.getElementById("home-waiting");
    if (waiting) waiting.hidden = true;
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
      lists.draw(code, charts.collect(into)[code] || { words: [], phrases: [] });
      drawFacts(code, into);
    }

    show(lang.current(codes));
    return Promise.resolve();
  }

  // The Grammar and Sentences tabs draw themselves (`grammar.js`, `sentences.js`) from the
  // server: there is nothing of them in the browser's lists to draw first.
  var drawing =
    which === "grammar"
      ? (window.TargumGrammar && window.TargumGrammar.loaded) || Promise.resolve()
      : which === "sentences"
        ? (window.TargumSentences && window.TargumSentences.loaded) || Promise.resolve()
        : which === "texts"
          ? drawTexts()
          : drawKept();
  // After the lists, and never in their way: the phrases appear first and the record of
  // corrected lines a moment later.
  drawing.then(drawRewrote).catch(function () {});

  drawing.catch(function (why) {
    // Signed out, or the server went away. The nav is still there to leave by.
    clearTimeout(slowly);
    var waiting = document.getElementById("home-waiting");
    if (waiting) waiting.hidden = true;
    couldNot(why);
    document.getElementById("nothing").hidden = false;
  });

  /* Home's wait, said again past three seconds (design.md §14, line 1; home QA,
     2026-10-18): "Opening your texts…" alone for twenty seconds on a cold box read as a
     page that had stopped. The lists say theirs the same way (Your Words QA, 2026-10-20). */
  // Each said through a literal t(), which is how a page's strings are found for it.
  function stillOpening() {
    if (which === "texts") return t("home.still-opening", "We're still opening your texts.");
    if (which === "phrases") return t("lists.still-opening.phrases", "We're still opening your phrases.");
    if (which === "grammar") return t("practice.page.still-opening", "We're still opening your practice.");
    if (which === "sentences") return t("sentences.page.still-opening", "We're still opening your sentences.");
    return t("lists.still-opening.words", "We're still opening your words.");
  }
  var slowly = setTimeout(function () {
    var waiting = document.getElementById("home-waiting");
    if (waiting && !waiting.hidden) waiting.textContent = stillOpening();
  }, 3000);
  drawing.then(function () {
    clearTimeout(slowly);
  }, function () {});

  /* What home says when it could not load, and the press that asks again. Offline says
     so, and asks again by itself once the connection is back; a server that answered
     with a refusal, or did not answer at all, is ours to own (§6). */
  function couldNot(why) {
    var lede = document.getElementById("nothing-lede");
    var says = document.getElementById("nothing-says");
    var again = document.getElementById("nothing-again");
    var offline = typeof navigator !== "undefined" && navigator.onLine === false;
    if (lede && says) {
      if (offline) {
        lede.textContent = t("home.offline.lede", "You're offline.");
        says.textContent =
          which === "texts"
            ? t(
                "home.offline.says",
                "Your texts will open when you're back online. Everything you've read is still here."
              )
            : which === "grammar" || which === "sentences"
              ? t("practice.page.offline", "Your practice opens when you're back online.")
              : t("lists.offline.says", "Your list opens when you're back online. Everything you've marked is still here.");
      } else if (!(why && why.answered)) {
        lede.textContent = t("home.unreachable.lede", "We can't reach targum.");
      }
    }
    function retry() {
      if (window.location && window.location.reload) window.location.reload();
    }
    if (again && !again.getAttribute("data-bound")) {
      again.setAttribute("data-bound", "1");
      again.addEventListener("click", retry);
    }
    // Offline, the bar's banner (`fault.js`) already says so with its own Try again, and
    // one press is enough; the page asks again by itself when the connection is back.
    if (again) again.hidden = offline;
    // Tell us goes with it: what it sends needs the connection too.
    var tell = document.getElementById("nothing-tell");
    if (tell) tell.hidden = offline;
    if (offline) window.addEventListener("online", retry, { once: true });
  }

  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (!changed) return;
      // Your Words and Your Phrases are drawn again by the load, as they were.
      if (which !== "texts") return awaitingAccount ? undefined : location.reload();
      if (redrawHome) return redrawHome();
      // Home has not drawn yet, and draws again once it has. If it could not draw at
      // all, the page is the refusal, and the load asks again, as it did before.
      owedRedraw = true;
      drawing.catch(function () {
        owedRedraw = false;
        location.reload();
      });
    });
    (window.TargumSync.settled ? window.TargumSync.settled() : window.TargumSync.start()).then(
      function () {
        if (lists) lists.offerExports(!!window.TargumSync.who);
      }
    );
  }
})();
