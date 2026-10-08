/* The arrival — what a new reader is asked, on a page of its own (design.md §12,
 * "Home is Your targums, and Continue leads it", 2026-10-08).
 *
 * It was the top of Learn until Learn was taken apart. The questions are the same ones —
 * the language a reader reads, a welcome, what they are interested in, how much Hebrew
 * they have, and the way into Claude and ChatGPT where they can take it up — asked one a
 * screen, as the FirstRun boards draw them. The last answer opens the text it chose; where
 * the shelf has nothing to open, the reader goes home, where "One to start with" offers
 * the same pick.
 *
 * Home sends a reader here only when there is nothing of theirs to show (`home.js`), and
 * this page says the last word: somebody who has answered already, or opened anything in
 * Hebrew, is sent straight back.
 */
(function () {
  "use strict";

  // The page's words in the reader's language, from `strings.js` (targum-internal#184).
  var words = window.TargumStrings;
  var t = words.t;
  var tn = words.tn;

  var key = window.TARGUM_KEY;
  /* Hosted there is no start-up key: the session cookie identifies the reader, and a key
     riding in every URL is a bearer token in browser history, on a shared screen, and in
     a Referer. Local it stays, because there it proves the page came from the terminal
     that started the process. Both cases are this one branch. */
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }
  var charts = window.TargumCharts;
  var shelf = window.TargumShelf;
  var lang = window.TargumLang;
  var names = window.TARGUM_LANGUAGES || {};

  function el(tag, className, text) {
    return charts.el(tag, className, text);
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }


  /* --- what you have already ------------------------------------------------ */

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  var base = shelf.base;

  // Every language a text can be read in: Daniel's Hebrew and Aramaic, a Torah book's
  // Hebrew and the Onkelos beside it (2026-09-14). A row from before has its one.
  function inLanguage(thing, code) {
    var all = thing.languages && thing.languages.length ? thing.languages : [thing.language];
    for (var n = 0; n < all.length; n++) if (base(all[n]) === code) return true;
    return false;
  }

  var scenes = window.TargumScenes || null;

  function sceneOf(reader) {
    return scenes && reader ? scenes.numberOf(reader.entry) : 0;
  }


  // Where a door goes. The box is the link, so this is the only href on it. A step up
  // past the sequence is a text not yet built, and this door is a link rather than a
  // button: it goes to the library row, which is where building is pressed for.
  function hrefOf(reader, door) {
    if (door.href) {
      // The key rides in the query, and a query belongs before the fragment.
      var parts = door.href.split("#");
      return keyed(parts[0]) + (parts[1] ? "#" + parts[1] : "");
    }
    if (door.src) return keyed(door.src);
    return keyed("/reader/" + readerPath(reader, door));
  }


  // The reader's own path under `/reader/`: the text's opening page, or the page the
  // conversation offered (`<name>/reader/<file>`), each segment encoded on its own.
  function readerPath(reader, door) {
    var path = door.path || reader.name + "/reader/index.html";
    return path.split("/").map(encodeURIComponent).join("/");
  }


  /* Whether to tell this reader about the connector at all: while it is open, to a
     signed-in reader holding no connection (design.md §12, 2026-09-24 and 2026-09-28).
     The banner and the arrival's last card ask the same question. */
  function offersConnector() {
    if (!window.TARGUM_CONNECTOR) return false;
    // `who` is null until `/account/me` answers, and for a reader who is not signed in.
    // Neither is somebody to invite.
    if (!who || !who.signedIn) return false;
    return !(who.connections || []).length;
  }

  /* The two steps, the first of them one press: the address in a well and Copy beside
     it, then where it goes (design.md §12, "The connector is met on the way in"). The
     address is this site's own `/mcp`, the one `/connect` shows. `where` names the
     place for the count, and nothing else goes with it. */
  function connectSteps(where) {
    var origin = (window.location && window.location.origin) || "";
    var address = origin + "/mcp";
    var list = el("ol", "connect-steps");
    var one = el("li", "connect-step");
    one.appendChild(el("span", "connect-step-say", t("learn.connect.step-copy", "Copy this address")));
    var well = el("span", "connect-address");
    well.appendChild(el("code", "connect-url", address));
    var copy = el("button", "connect-copy", t("learn.connect.copy", "Copy"));
    copy.type = "button";
    copy.addEventListener("click", function () {
      counted(where + "-copy");
      try {
        window.navigator.clipboard.writeText(address).then(function () {
          copy.textContent = t("learn.connect.copied", "Copied");
        });
      } catch (e) {}
    });
    well.appendChild(copy);
    one.appendChild(well);
    list.appendChild(one);
    list.appendChild(
      el("li", "connect-step", t("learn.connect.step-add", "Add it as a connector in Claude or ChatGPT."))
    );
    return list;
  }


  /* What was pressed, and nothing else about it (targum-internal#127). A `control` event
     carries a name and the window's width — never which text, never where in it, never
     the time. Learn had no counting at all until today, which is why §12's own request
     for "a look at whether the reading doors' press rate moves" could not be answered:
     no door on this page has ever been counted. */
  function counted(name) {
    if (window.TargumEvents) window.TargumEvents.note({ kind: "control", control: name });
  }


  /* --- the arrival (targum-internal#294, rewritten as subjects 2026-09-17) --- */

  /* The one question a new reader is asked: what they are interested in.
   *
   * **Subjects, in a person's own words.** The first version asked in the library's
   * terms — "Everyday Hebrew, spoken", "The week's Torah portion", "Something to watch"
   * — which are a register, a collection and a file format. Nobody thinks of themselves
   * that way. They think they like sport, or history, or archaeology. The shelf is the
   * thing that should do the translating, and this is where it starts.
   *
   * **Three at least.** One subject is a label and two is a preference; three is the
   * first number that describes somebody. It also stops the answer being a route: with
   * one door the next press had to land on a text, so a door with nothing behind it was
   * a dead end and was left out. Three is a profile, a profile may name something the
   * library has not got, and that it was named is the most useful thing anybody can
   * say about what to build next. So every subject is offered, including the empty
   * ones, and the texts are filed behind them as they arrive.
   *
   * **Still not a level.** Nobody is asked how good they are, and nothing is stored
   * about which rung they are on. That question is real — the reader who already reads
   * Hebrew meets a beginner's shelf and nothing on the first screen has been marked yet
   * to tell them apart — and it is open as targum-internal#306 rather than settled here.
   * Until it is answered the claim grid below is the only thing that sets a count, and
   * it sets it by measuring.
   */
  var INTERESTS = [
    // `tags` are `catalogue.Tag` values carried on the shelf row; `kinds` are `Kind`s,
    // for the subjects the catalogue files by form rather than by topic. A subject
    // matches a row if any of either does.
    { id: "everyday", kinds: ["dialogue"] },
    { id: "israel", tags: ["israel"] },
    { id: "judaism", tags: ["tanakh", "judaica"] },
    { id: "news", tags: ["journalism"] },
    { id: "sport", tags: ["sport"] },
    { id: "stories", kinds: ["story", "novel", "play"] },
    { id: "poetry", kinds: ["poetry"] },
    { id: "history", tags: ["history"] },
    { id: "archaeology", tags: ["archaeology"] },
    { id: "science", tags: ["science"] },
    { id: "technology", tags: ["technology"] },
    { id: "health", tags: ["health"] },
    { id: "food", tags: ["food"] },
    { id: "travel", tags: ["travel"] },
    { id: "music", tags: ["music"] },
    { id: "art", tags: ["art"] },
    { id: "politics", tags: ["politics"] },
    { id: "business", tags: ["business"] },
    { id: "philosophy", tags: ["philosophy"] },
    { id: "language", tags: ["language"] },
  ];

  //: How many subjects the reader is held to. Matches `accounts.Store.INTERESTS_WANTED`.
  var WANTED = 3;

  /* **A rung is asked, and kept** (targum-internal#306, 2026-09-19; design.md §12, "The
     arrival is two questions, a screen each, and the second one is kept").

     This is the fifth state of one question. The arrival asked how much Hebrew a reader
     had, used the answer once and kept it nowhere (2026-09-17); that was taken out the
     next day as the worst half of both — a reader stopped on their first visit for an
     answer thrown away before the page is drawn again — on the ground that every level
     `design.md` sanctions is measured. David reopened it and chose the variant nobody had
     built: the answer is **kept on the account**, it **seeds** the three things that have
     nothing to go on at a first visit (which text opens first, here; the Library's band;
     how hard the conversation writes), and the first measurement **outvotes** it —
     `charts.seed` answers "" the moment the reader's own marked words reach aleph. It is
     never shown back as a letter: nothing on any page says "you said gimel". The You
     page offers it to change, in these same words (2026-10-07).

     The ulpan ladder `level.py` climbs, aleph to vav. Anybody who studied Hebrew in
     Israel knows which kitah they were in; anybody who did not reads the plain words and
     ignores the letter. The words say what a person can *follow*, not what they can
     read: many come to listen and to watch (targum-internal#337). */
  var LEVELS = [
    { id: "aleph", letter: "א" },
    { id: "aleph-plus", letter: "א+" },
    { id: "bet", letter: "ב" },
    { id: "bet-plus", letter: "ב+" },
    { id: "gimel", letter: "ג" },
    { id: "dalet", letter: "ד" },
    { id: "hey", letter: "ה" },
    { id: "vav", letter: "ו" },
  ];

  function levelLabels() {
    return {
      aleph: t("learn.level.aleph", "Just starting"),
      "aleph-plus": t("learn.level.aleph-plus", "I know some words"),
      bet: t("learn.level.bet", "I can hold a simple conversation"),
      "bet-plus": t("learn.level.bet-plus", "I follow slow Hebrew with help"),
      gimel: t("learn.level.gimel", "I follow the news with a dictionary"),
      dalet: t("learn.level.dalet", "I follow most things comfortably"),
      hey: t("learn.level.hey", "I follow almost anything"),
      vav: t("learn.level.vav", "Hebrew is a language I live in"),
    };
  }

  /* Which of the texts a subject can answer to open, given the rung. Sorted by the
     difficulty each row already carries, and the rung says how far along to land: aleph
     takes the easiest of them, vav the hardest, the rest in between. It is a coarse rule
     on purpose — it decides one text, once, and the reader's own marked words decide
     everything after it. No rung, and the order the shelf already has is the order.

     Where the rows say what rung each was written for (`level.name`, the ladder
     `level.py` climbs), that is read first, and the position rule is only for a shelf
     that does not say (2026-09-28). By position alone one row is every rung's answer, so
     a reader who said "Just starting" was opened on a vav article because it was the
     only one filed under their subject. The pick is the hardest text at or under the
     rung they named — one they can follow — and where nothing is that easy, the easiest
     there is. */
  function rungOf(reader) {
    var name = reader && reader.level && reader.level.name;
    return name ? charts.DECLARED_RUNGS.indexOf(String(name).replace(/ /g, "-")) : -1;
  }

  function pickByRung(rows, rung) {
    if (!rows.length) return null;
    if (!rung) return rows[0];
    var said = charts.DECLARED_RUNGS.indexOf(rung);
    var leveled = rows.filter(function (reader) {
      return rungOf(reader) >= 0;
    });
    if (said >= 0 && leveled.length) {
      var under = leveled.filter(function (reader) {
        return rungOf(reader) <= said;
      });
      var pool = under.length ? under : leveled;
      var best = pool[0];
      pool.forEach(function (reader) {
        var here = rungOf(reader);
        var there = rungOf(best);
        if (under.length ? here > there : here < there) best = reader;
      });
      return best;
    }
    var sorted = rows.slice().sort(function (a, b) {
      return (a.difficulty || 0) - (b.difficulty || 0);
    });
    var at = Math.round(charts.seedFraction(rung) * (sorted.length - 1));
    return sorted[at] || sorted[0];
  }

  function interestLabels() {
    return {
      everyday: t("learn.arrival.everyday", "Everyday conversation"),
      israel: t("learn.arrival.israel", "Life in Israel: money, health, school, home"),
      judaism: t("learn.arrival.judaism", "Torah and Judaism"),
      news: t("learn.arrival.news", "News"),
      sport: t("learn.arrival.sport", "Sport"),
      stories: t("learn.arrival.stories", "Stories and novels"),
      poetry: t("learn.arrival.poetry", "Poetry"),
      history: t("learn.arrival.history", "History"),
      archaeology: t("learn.arrival.archaeology", "Archaeology"),
      science: t("learn.arrival.science", "Science and nature"),
      technology: t("learn.arrival.technology", "Technology"),
      health: t("learn.arrival.health", "Health and medicine"),
      food: t("learn.arrival.food", "Food and cooking"),
      travel: t("learn.arrival.travel", "Travel and places"),
      music: t("learn.arrival.music", "Music and songs"),
      art: t("learn.arrival.art", "Art"),
      politics: t("learn.arrival.politics", "Politics"),
      business: t("learn.arrival.business", "Business and money"),
      philosophy: t("learn.arrival.philosophy", "Philosophy and ideas"),
      language: t("learn.arrival.language", "The Hebrew language itself"),
    };
  }

  //: Whether one shelf row is a thing this subject asks for. Any tag, or any kind.
  function wanted(reader, want) {
    var i;
    var carried = reader.tags || [];
    if (want.tags) {
      for (i = 0; i < want.tags.length; i++) {
        if (carried.indexOf(want.tags[i]) !== -1) return true;
      }
    }
    if (want.kinds) {
      for (i = 0; i < want.kinds.length; i++) {
        if (reader.kind === want.kinds[i]) return true;
      }
    }
    return false;
  }

  function interestOf(id) {
    for (var i = 0; i < INTERESTS.length; i++) if (INTERESTS[i].id === id) return INTERESTS[i];
    return null;
  }

  /* What this reader said, kept on the account so it travels between devices the way the
     rest of the profile does. The browser holds a copy so the row does not flash back on
     a page drawn before `/account/me` answers. A comma-separated list since the answer
     stopped being one word. */
  var ARRIVED = "targum:arrived";

  function readList(key) {
    var raw = "";
    try {
      raw = localStorage.getItem(key) || "";
    } catch (e) {
      raw = "";
    }
    var out = [];
    raw.split(",").forEach(function (word) {
      var id = word.replace(/^\s+|\s+$/g, "");
      if (id && interestOf(id)) out.push(id);
    });
    return out;
  }

  var arrived = readList(ARRIVED);
  //: Answered or skipped on this visit. A reader who skipped both screens has said
  //: nothing to keep, and is not asked twice on one page for it.
  var arrivalOver = false;

  function keep(key, value) {
    try {
      if (window.targumKeep) window.targumKeep(key, value);
      else localStorage.setItem(key, value);
    } catch (e) {
      /* nowhere to keep it; the account still has it */
    }
  }

  function post(where, body) {
    fetch(keyed(where), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(function () {
      /* the browser's copy still decides this visit */
    });
  }

  /* --- which language they read (2026-09-20) ---------------------------------
   *
   * The arrival's first question, and the only one asked in more than one language at
   * once. `reads` on the account decides two things — the language of the line under
   * each Hebrew one, and the language this page speaks — and until today a new account
   * was English in both whatever the person read, with the way out on a profile page or
   * behind a question the conversation asks once. So a reader is asked, before they are
   * asked anything they would have to read.
   *
   * Asked only of somebody who has never said. Every one of these is an answer already:
   * the account has rows (its own, or the operator's mark on an invited address), this
   * page arrived in another language, the browser holds a choice (the reader's picker,
   * or a press on the front door carried through sign-in), or the conversation asked.
   * The same two keys `first.js` keeps, so neither asks after the other.
   */
  var ASKED_READ = "targum:asked-read";
  //: This visit's flag: the page is loaded again when the answer changes its language,
  //: and the arrival has to come back as the second of three and not the first of two.
  var TONGUE_ASKED = "targum:arrival-tongue";
  //: Each language in its own name. Not from the page's strings: those are in one
  //: language, and this is the screen that cannot assume which.
  var TONGUES = {
    // "Native language" and not "which do you read" (David, 2026-09-20): it is the
    // question a person has an answer to without thinking, and what it decides — the
    // language under each line, and the desk's — is what a native language is for.
    en: { name: "English", asks: "What is your native language?" },
    ru: { name: "Русский", asks: "Какой у вас родной язык?" },
  };
  //: The last row: neither of them. In every language the question is asked in.
  var OTHER_TONGUE = "Other · Другой";
  //: `/account/me`, once it has answered; null until then and for nobody.
  var who = null;

  function held(key) {
    try {
      return localStorage.getItem(key) || "";
    } catch (e) {
      return "";
    }
  }

  function thisVisit(value) {
    try {
      if (value === undefined) return window.sessionStorage.getItem(TONGUE_ASKED) || "";
      window.sessionStorage.setItem(TONGUE_ASKED, value);
    } catch (e) {
      /* no session store: the step count starts again, and nothing else is lost */
    }
    return "";
  }

  function offered() {
    return (window.TARGUM_INTO || []).filter(function (code) {
      return !!TONGUES[code];
    });
  }

  function pageTongue() {
    var said = (document.documentElement && document.documentElement.lang) || "en";
    return String(said).split("-")[0].toLowerCase() || "en";
  }

  function readsInto() {
    return (lang && lang.into && lang.into()) || "";
  }

  /* Whether this browser gives any sign its reader may read Russian (design.md §12,
     "Russian is shown to somebody who may read it", 2026-09-28): one of its languages is
     Russian, or a language of the countries where Russian is the language people share.
     Nobody else is shown a word of Cyrillic by the arrival. It is a sign and not an
     answer — the question is still asked — and a reader it misses has the EN · RU
     switch, which is Latin letters. */
  var RUSSIAN_WORLD = ["ru", "uk", "be", "kk", "ky", "uz", "tg"];

  function mayReadRussian() {
    var nav = window.navigator || (typeof navigator !== "undefined" ? navigator : null);
    if (!nav) return false;
    var said = nav.languages && nav.languages.length ? nav.languages : [nav.language || ""];
    for (var i = 0; i < said.length; i++) {
      var code = String(said[i] || "").split("-")[0].toLowerCase();
      if (RUSSIAN_WORLD.indexOf(code) >= 0) return true;
    }
    return false;
  }

  //: Whether the reader has said, or the page knows, which language they read.
  function tongueSaid() {
    if (held(ASKED_READ) || readsInto()) return true;
    if (pageTongue() !== "en") return true;
    return !!(who && who.signedIn && who.readsSaid);
  }

  function asksTongue() {
    if (offered().length < 2) return false;
    if (thisVisit()) return true;
    if (tongueSaid()) return false;
    return mayReadRussian();
  }

  /* The way in for a Russian reader the browser did not give away — an olah whose phone
     is set to Hebrew or English, the reader the question was first asked for (2026-09-20).
     Two codes in the corner of the arrival, the front door's own EN · RU, so nothing in
     it is Cyrillic. Drawn while the question is not asked and nothing has been said;
     pressing RU is the answer the question would have taken. */
  function drawTongueSwitch(host) {
    if (!host) return;
    host.textContent = "";
    host.hidden = true;
    if (offered().indexOf("ru") < 0 || tongueSaid()) return;
    [
      ["en", "EN", "English"],
      ["ru", "RU", t("learn.arrival.switch-russian", "Russian")],
    ].forEach(function (one, at) {
      if (at) host.appendChild(el("span", "arrival-switch-dot", "\u00b7"));
      var press = el("button", "arrival-switch-key", one[1]);
      press.type = "button";
      press.setAttribute("aria-label", one[2]);
      press.setAttribute("aria-pressed", one[0] === "en" ? "true" : "false");
      if (one[0] === "ru") {
        press.addEventListener("click", function () {
          counted("arrival-switch-ru");
          sayTongue("ru", function () {
            if (window.location.reload) window.location.reload();
          });
        });
      }
      host.appendChild(press);
    });
    host.hidden = false;
  }

  /* The account hears it the way the profile page's boxes say it: the whole set. Then
     the page is loaded again where the answer changed the language it should be in,
     because a desk page is drawn by the server in one language. `then` is what to do
     where nothing has to be loaded again. */
  function sayTongue(code, then) {
    keep(ASKED_READ, "1");
    if (lang && lang.into) lang.into(code);
    if (!who || !who.signedIn) return then();
    ask("/account/languages", { learning: who.learning || ["he"], reads: [code] })
      .then(function (answer) {
        if (answer && !answer.error && code !== pageTongue() && window.location.reload) {
          window.location.reload();
          return;
        }
        then();
      })
      .catch(then);
  }

  /* A choice this browser already holds and the account has never heard: a press on the
     front door's switcher, carried through sign-in (`signin.js`). Handed over here, at
     the one moment it is certainly a new reader's, rather than on every page for every
     account — an account that has said nothing in a browser that reads Russian is not
     this page's to re-file. */
  function handOverTongue() {
    var code = readsInto();
    if (!who || !who.signedIn || who.readsSaid) return;
    if (!code || offered().indexOf(code) < 0) return;
    who.readsSaid = true;
    sayTongue(code, function () {});
  }

  function remember(ids) {
    arrived = ids.slice();
    keep(ARRIVED, arrived.join(","));
    post("/account/interest", { interest: arrived });
  }

  //: The rung, kept the way the subjects are: the account has it, the browser holds a copy.
  function rememberLevel(id) {
    keep(charts.DECLARED, id);
    post("/account/level", { level: id });
  }

  /* The first text for a reader who has opened nothing: the first of their subjects the
     shelf can answer, and within it the row nearest the rung they named. Most of the
     nineteen subjects have nothing behind them yet, on purpose — the answer is a profile,
     not a route — so this looks for the first that does rather than assuming the first
     named does. A reader who named a rung and no subject gets the modern shelf at that
     rung, which is what keeps somebody at gimel who skipped the first screen off Scene 1. */
  /* A first text that can be heard, where the subject has one (targum-internal#335). The
     second thing a new reader should find out is that the page has a voice, and they
     cannot find that out on a silent text. Where nothing in the subject is voiced, the
     subject still wins: it is what they asked for. */
  function voiced(rows) {
    var heard = rows.filter(function (reader) {
      return reader.spoken || reader.video;
    });
    return heard.length ? heard : rows;
  }

  /* A first text with their language under it, where any of their subjects has one. The
     shelf is English throughout and Russian in places (beta), so a reader who has just
     said Русский would otherwise open a page in Russian with English under every line.
     Across all their subjects and not only the first: three were asked for and none was
     ranked. Where none has it, the ordinary pick below — what they asked for, honestly
     in the language it exists in. */
  function inTheirs(rows) {
    var code = readsInto();
    if (!code || code === "en") return [];
    return rows.filter(function (reader) {
      return (reader.targets || []).indexOf(code) >= 0;
    });
  }

  /* Whether a row is one this reader can follow, by the rung they named: written for
     it, under it, or one above — a stretch, not a wall. A subject is what they will
     enjoy only where they can read it; a vav article is not "Food and cooking" to
     somebody just starting, so a subject whose rows are all past reach gives way to
     the next, and the rung decides where none is left (2026-09-28). A row that does
     not say its rung, and a reader who named none, are never ruled out by this. */
  function inReach(reader, rung) {
    var said = rung ? charts.DECLARED_RUNGS.indexOf(rung) : -1;
    var at = rungOf(reader);
    return said < 0 || at < 0 || at <= said + 1;
  }

  function firstText(handed, code) {
    var store = charts.collect(charts.meaningLanguage(code))[code];
    var rung = charts.seed(store && store.words, code);
    for (var r = 0; r < arrived.length; r++) {
      var asked = interestOf(arrived[r]);
      if (!asked) continue;
      var theirs = inTheirs(
        handed.filter(function (reader) {
          return wanted(reader, asked) && inReach(reader, rung);
        })
      );
      if (theirs.length) return pickByRung(voiced(theirs), rung);
    }
    for (var w = 0; w < arrived.length; w++) {
      var came = interestOf(arrived[w]);
      if (!came) continue;
      var rows = handed.filter(function (reader) {
        return wanted(reader, came) && inReach(reader, rung);
      });
      if (rows.length) return pickByRung(voiced(rows), rung);
    }
    // And heard here too: a reader who named a rung and no subject is as new as one who
    // named three, and the voice is as much the second thing they should find. So is a
    // reader whose subjects the shelf cannot answer yet (2026-09-28): the track's own
    // start knows nothing of the rung, and "Just starting" was handed whatever stood
    // first on it. The rung is the one answer left to go on, so it decides.
    if (rung) {
      // Reach before voice: a voice is the second thing to find, and it is found on a
      // page the reader can follow — a heard vav article is not one, over a silent aleph
      // text that is. Where nothing on the modern shelf is in reach, the easiest there is.
      var modern = handed.filter(function (reader) {
        return reader.register === "modern";
      });
      var near = modern.filter(function (reader) {
        return inReach(reader, rung);
      });
      return pickByRung(voiced(near.length ? near : modern), rung);
    }
    return null;
  }

  /* The row itself. Shown only to a reader who has opened nothing in Hebrew and
     answered nothing — so it is asked once, it never interrupts somebody who is already
     reading, and answering it makes it go away for good.

     Every subject is drawn, whether or not the shelf can answer it yet. The rule this
     drops — a door with nothing seeded behind it is left out rather than drawn and
     disappointing — belonged to the version where one answer routed straight to a text.
     Nothing is routed on a press now: the reader picks three, says where they are, and
     the sheet underneath is chosen from whichever of their subjects the shelf can
     actually satisfy. */
  function drawArrival(asking, readers, shared, again, open) {
    var host = document.getElementById("arrival");
    var row = document.getElementById("arrival-doors");
    var rungs = document.getElementById("arrival-levels");
    var done = document.getElementById("arrival-done");
    var skip = document.getElementById("arrival-skip");
    var back = document.getElementById("arrival-back");
    var count = document.getElementById("arrival-count");
    var where = document.getElementById("arrival-step");
    var tongues = document.getElementById("arrival-tongues");
    var asksIn = document.getElementById("arrival-asks-language");
    var screenOf = {
      tongue: document.getElementById("arrival-language"),
      subjects: document.getElementById("arrival-subjects"),
      level: document.getElementById("arrival-level"),
      connect: document.getElementById("arrival-connect"),
      welcome: document.getElementById("arrival-welcome"),
    };
    if (!host || !row || !rungs || !done || !skip || !screenOf.subjects || !screenOf.level) return;
    if (!asking) {
      host.hidden = true;
      document.body.classList.remove("arriving");
      return;
    }
    var labels = interestLabels();
    var said = levelLabels();
    var picked = [];
    /* The screens, in order. The language comes first where it is asked at all
       (2026-09-20), and a visit that has already answered it — the page was loaded again
       in the language chosen — comes back on the second of three, not the first of two. */
    var withTongue = !!(screenOf.tongue && tongues && asksIn && asksTongue());
    var order = withTongue ? ["tongue", "subjects", "level"] : ["subjects", "level"];
    /* The welcome, before the first question it can be written in (2026-09-28): after
       the language, which decides what language it is in, and before the subjects. */
    var nameRow = document.getElementById("arrival-name-row");
    var nameField = document.getElementById("arrival-name");
    if (screenOf.welcome) {
      order.splice(withTongue ? 1 : 0, 0, "welcome");
      if (nameRow) nameRow.hidden = !(who && who.signedIn);
      if (nameField && who && who.name) nameField.value = who.name;
    }
    /* And last, where the reader can take it up, the way into Claude and ChatGPT
       (design.md §12, "The connector is met on the way in"): a card that tells rather
       than asks, with the address to copy, and Open as its filled press so the text the
       answers chose is still one press away. Counted in the bars like the others. */
    var connectHost = document.getElementById("arrival-connect-steps");
    if (screenOf.connect && connectHost && offersConnector()) {
      order.push("connect");
      connectHost.textContent = "";
      connectHost.appendChild(connectSteps("arrival"));
    }
    var step = withTongue && thisVisit() ? 1 : 0;
    // Only the questions are counted: the welcome says where they are and asks nothing,
    // and the connector's card is optional — counted, it read as a step that had to be
    // taken (2026-09-28: "this makes it seem like installing the MCP is mandatory").
    function counted() {
      return order.filter(function (name) {
        return name !== "welcome" && name !== "connect";
      });
    }
    row.textContent = "";
    rungs.textContent = "";
    if (tongues) tongues.textContent = "";
    if (!withTongue) handOverTongue();
    drawTongueSwitch(withTongue ? null : document.getElementById("arrival-switch"));

    /* One question a screen (David, 2026-09-19). The step is said in words, in the
       resting colour; Next belongs to the subjects alone, because on the second screen
       pressing a row *is* the answer and a second button would be a second question. */
    function settle() {
      var now = order[step];
      ["tongue", "welcome", "subjects", "level", "connect"].forEach(function (name) {
        if (screenOf[name]) screenOf[name].hidden = name !== now;
      });
      var asking = now !== "welcome" && now !== "connect";
      if (where) where.hidden = !asking;
      if (where && asking) {
        var questions = counted();
        var at = questions.indexOf(now);
        /* And drawn, as a bar a step in leaf (design.md §12, 2026-09-28). The bars carry
           no text, so what is read aloud, and what `textContent` says, is the words. */
        var bars = document.createElement("span");
        bars.className = "arrival-bars";
        bars.setAttribute("aria-hidden", "true");
        for (var b = 0; b < questions.length; b++) {
          var bar = document.createElement("span");
          bar.className = b <= at ? "arrival-bar is-done" : "arrival-bar";
          bars.appendChild(bar);
        }
        var words = document.createElement("span");
        words.textContent = t("learn.arrival.step", "{n} of {of}")
          .replace("{n}", String(at + 1))
          .replace("{of}", String(questions.length));
        where.textContent = "";
        where.appendChild(bars);
        where.appendChild(words);
      }
      var passing = now === "welcome" || now === "connect";
      done.hidden = now !== "subjects" && !passing;
      done.disabled = now === "subjects" && picked.length < WANTED;
      /* Continue on the two cards that ask nothing: the welcome, and the connector's,
         which is optional and must read as optional (2026-09-28). A Skip beside it did
         the same thing and made the card read as a step to get past. */
      done.textContent = passing
        ? t("learn.arrival.continue", "Continue")
        : t("learn.arrival.next", "Next");
      skip.hidden = passing;
      if (back) back.hidden = step === 0;
      if (!count) return;
      var short = WANTED - picked.length;
      count.textContent =
        now === "subjects" && short > 0
          ? t("learn.arrival.pick-more", "Pick {n} more").replace("{n}", String(short))
          : "";
    }

    /* The last answer opens the text it chose — the reader, not this page with a card to
       find (design.md §12). Where the shelf has nothing to open, the page is drawn again
       and says what it has. */
    function finish() {
      host.hidden = true;
      document.body.classList.remove("arriving");
      if (open && open()) return;
      if (again) again();
    }

    /* A new screen starts at its top. Nineteen subjects scroll on a phone, and the
       second question was drawn wherever the first had been left — its own words and
       its first row under the bar (found by opening it, 2026-09-19). Focus goes to the
       screen's first press without the browser scrolling to it on its own account. */
    function arrive() {
      settle();
      if (window.scrollTo) window.scrollTo(0, 0);
      var now = order[step];
      var first =
        now === "level" ? rungs.children[0] : now === "tongue" ? tongues.children[0] : null;
      if (now === "subjects") first = done.disabled ? row.children[0] : done;
      if (now === "connect") first = done;
      if (now === "welcome") first = nameRow && !nameRow.hidden ? nameField : done;
      if (first && first.focus) first.focus({ preventScroll: true });
    }

    function onward() {
      if (step < order.length - 1) {
        step += 1;
        arrive();
        return;
      }
      finish();
    }

    INTERESTS.forEach(function (want) {
      var press = document.createElement("button");
      press.type = "button";
      press.className = "arrival-door";
      press.setAttribute("aria-pressed", "false");
      press.textContent = labels[want.id] || want.id;
      press.addEventListener("click", function () {
        var at = picked.indexOf(want.id);
        if (at === -1) picked.push(want.id);
        else picked.splice(at, 1);
        var on = at === -1;
        press.setAttribute("aria-pressed", on ? "true" : "false");
        press.classList.toggle("is-picked", on);
        settle();
      });
      row.appendChild(press);
    });

    /* The language, a row each in its own name; pressing one is the answer, as on the
       ladder. The question is said once in every language offered, a line each and each
       marked as what it is, so a screen reader reads Russian in a Russian voice. */
    if (withTongue) {
      asksIn.textContent = "";
      offered().forEach(function (code) {
        var line = document.createElement("span");
        line.setAttribute("lang", code);
        line.textContent = TONGUES[code].asks;
        asksIn.appendChild(line);
        var tongue = document.createElement("button");
        tongue.type = "button";
        tongue.className = "arrival-rung";
        tongue.setAttribute("lang", code);
        tongue.textContent = TONGUES[code].name;
        tongue.addEventListener("click", function () {
          thisVisit("1");
          sayTongue(code, onward);
        });
        tongues.appendChild(tongue);
      });
      /* And a row for everybody else (David, 2026-09-20). "What is your native language?"
         with two answers is a question most of the world cannot answer, and Skip is not
         an answer — it says "not now", and this reader means "neither". Said in both
         languages, since it is the one row that is nobody's own name. What it sets is
         English, which is the only other language there is to read into; what it is for
         is that they were asked, answered truly, and are not asked again. */
      var other = document.createElement("button");
      other.type = "button";
      other.className = "arrival-rung";
      other.textContent = OTHER_TONGUE;
      other.addEventListener("click", function () {
        thisVisit("1");
        sayTongue("en", onward);
      });
      tongues.appendChild(other);
    }

    LEVELS.forEach(function (level) {
      var rung = document.createElement("button");
      rung.type = "button";
      rung.className = "arrival-rung";
      // The letter beside the words, not instead of them: it is the whole label to a
      // reader who did an ulpan and noise to everybody else, so it is the smaller half.
      rung.appendChild(document.createTextNode(said[level.id] || level.id));
      var letter = document.createElement("span");
      letter.className = "arrival-rung-letter";
      letter.setAttribute("lang", "he");
      letter.textContent = level.letter;
      rung.appendChild(letter);
      rung.addEventListener("click", function () {
        rememberLevel(level.id);
        onward();
      });
      rungs.appendChild(rung);
    });

    done.onclick = function () {
      if (order[step] === "welcome") {
        var name = nameField ? String(nameField.value || "").trim() : "";
        if (name && who && who.signedIn) {
          post("/account/name", { name: name });
          who.name = name;
        }
        onward();
        return;
      }
      if (order[step] === "connect") {
        counted("arrival-open");
        finish();
        return;
      }
      if (picked.length < WANTED) return;
      remember(picked);
      onward();
    };
    // A question a reader may not decline is a gate, and the arrival is not one.
    skip.onclick = onward;
    /* And a question a reader may not go back to is a one-way door (2026-09-20). The
       subjects are as they were left — what was pressed is still pressed — and Next
       keeps them again if they change. Focus goes to Next, or to the first subject
       where Next is asleep because the question was skipped. */
    if (back) {
      back.onclick = function () {
        if (step === 0) return;
        step -= 1;
        arrive();
      };
    }
    settle();
    host.hidden = false;
    document.body.classList.add("arriving");
  }


  function trackDoor(code, register, readers, shared) {
    var docs = stored("targum:docs");
    function ofHere(list) {
      return list.filter(function (reader) {
        return base(reader.language) === code && reader.register === register;
      });
    }
    function done(reader) {
      return !!(scenes && scenes.finished(reader, docs));
    }
    var own = ofHere(readers);
    var pool = ofHere(shared);
    var numbered = pool.filter(function (reader) {
      return sceneOf(reader) > 0;
    });
    var sequence = pool;
    if (register === "modern" && numbered.length && scenes) {
      sequence = scenes
        .ordered(
          numbered.map(function (reader) {
            return { id: reader.entry, reader: reader };
          })
        )
        .map(function (item) {
          return item.reader;
        });
    }
    // The text last opened: any of the reader's own, or a shared one they have opened.
    // An upload never opened is still theirs, and newest of those wins over a sequence
    // they have not started.
    var last = null;
    own.concat(
      pool.filter(function (reader) {
        return reader.opened > 0;
      })
    ).forEach(function (reader) {
      if (!last || reader.opened > last.opened || (reader.opened === last.opened && reader.built > last.built)) {
        last = reader;
      }
    });
    var next = null;
    for (var i = 0; i < sequence.length; i++) {
      if (!done(sequence[i])) {
        next = sequence[i];
        break;
      }
    }
    var anyDone = own.concat(pool).some(done);
    var door = {
      register: register,
      total: numbered.length,
      opened: last ? last.opened : 0,
      reader: null,
      // The sequence's next unfinished text, whatever the door shows: the row of doors
      // offers it as Up next beside a text being carried on with (2026-09-11).
      next: next,
      state: "up",
    };
    if (last && !done(last)) {
      door.state = "carry";
      door.reader = last;
    } else if (next) {
      // Finished on another device, where `opened` never synced: any finish at all
      // means this is not a start.
      door.state = last || anyDone ? "next" : "start";
      door.reader = next;
    }
    return door;
  }

  /* --- putting it together --------------------------------------------------- */

  //: Set for this visit when the arrival is over, answered or not, so home does not send
  //: the reader straight back here. Read by `home.js`.
  var OVER = "targum:arrival-over";

  function over() {
    try {
      window.sessionStorage.setItem(OVER, "1");
    } catch (e) {
      /* no session store: home asks this page again, and this page sends them back */
    }
  }

  // Home, with the key where there is one. `replace`, so Back does not land here again.
  function home() {
    over();
    // Only from a page a server is behind: opened off the disk there is no home to go to.
    var served = !window.location.protocol || /^https?:$/.test(window.location.protocol);
    if (served && window.location.replace) window.location.replace(keyed("/"));
  }

  /* What the account already holds, adopted before anything is decided: the subjects and
     the rung belong to the person, so somebody who answered on a phone is not asked again
     on a laptop. Only ever adopted, never cleared from here — an answer this browser has
     and the account has not is one that has not reached the server yet
     (targum-internal#294). */
  function adopt(me) {
    var theirs = (me && me.signedIn && me.interest) || [];
    var same =
      theirs.length === arrived.length &&
      theirs.every(function (word, at) {
        return word === arrived[at];
      });
    if (theirs.length && !same) {
      arrived = theirs.slice();
      keep(ARRIVED, arrived.join(","));
    }
    var rung = (me && me.signedIn && me.declared) || "";
    if (rung && rung !== held(charts.DECLARED)) keep(charts.DECLARED, rung);
  }

  var opened = stored("targum:opened");

  var whoAsked = ask("/account/me").catch(function () {
    return null;
  });

  ask("/readers")
    .then(function (data) {
      return whoAsked.then(function (me) {
        who = me;
        adopt(me);
        return data;
      });
    })
    .then(function (data) {
      var readers = (data && data.readers) || [];
      var shared = (data && data.shared) || [];
      readers.concat(shared).forEach(function (reader) {
        reader.opened = opened[reader.document] || 0;
      });
      // The arrival is Hebrew's: the subjects, the rungs and the first texts are.
      var code = lang.HOME;
      var handed = shared.filter(function (reader) {
        return inLanguage(reader, code);
      });
      var modern = trackDoor(code, "modern", readers, shared);
      var biblical = trackDoor(code, "biblical", readers, shared);
      var asking = !arrived.length && !modern.opened && !biblical.opened;
      var waiting = document.getElementById("arrival-waiting");
      if (waiting) waiting.hidden = true;
      if (!asking) return home();
      drawArrival(true, readers, shared, home, function () {
        // Straight into the text the answers chose, or the track's own start where they
        // chose nothing the shelf can answer.
        var first = firstText(handed, code);
        var via = first ? { state: "start" } : modern.reader ? modern : biblical;
        var target = first || via.reader;
        if (!target) return false;
        /* Into the text, not onto its contents page. A book's own address is its list
           of chapters, and a new reader who has just answered two questions was landed
           on a page with a title, a button and four links — one more press from a line
           of Hebrew (found by QA, 2026-09-20). The first chapter that is ready is where
           "Start reading" on that page goes anyway. */
        var opening = (target.chapters || []).filter(function (chapter) {
          return chapter && chapter.ready && chapter.file;
        })[0];
        if (opening && !via.path && !via.href && !via.src) {
          via = { state: via.state, path: target.name + "/reader/" + opening.file };
        }
        over();
        window.location.href = hrefOf(target, via);
        return true;
      });
    })
    .catch(function () {
      // Signed out on a box that wants an account, or the server went away: there is
      // nothing to ask with, and home says what it can.
      home();
    });

  // Exposed for the tests and for nothing else: the pick the last answer opens.
  window.TargumArrival = { firstText: firstText, over: OVER };
})();
