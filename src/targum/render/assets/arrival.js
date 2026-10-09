/* The arrival — what a new reader is asked, on a page of its own, `/welcome`.
 *
 * Three questions, a screen each, as the FirstRun and Onboard boards draw them (David,
 * 2026-10-09: the boards win; design.md §12, "The arrival is three plain questions"):
 *
 *   1. Which language are you learning? — six, each in its own greeting and wearing how
 *      far along it is (Beta, Alpha, Experimental).
 *   2. What do you like to read about? — a few subjects, as many or as few as they like.
 *   3. How much <language> can you read? — four or so plain sentences in that language's
 *      own texts, and "I'm not sure, show me a page".
 *
 * Before them, and only for a browser that may read Russian, the language the page
 * speaks (2026-09-20, 2026-09-28): the OnboardRuUi boards' "1 of 4".
 *
 * The last answer opens a text in the language chosen, at the level said and on a
 * subject they like where the shelf has one; where the shelf has nothing in that
 * language, home in that language, which is upload-first.
 *
 * Home sends a reader here only when there is nothing of theirs to show (`home.js`), and
 * this page says the last word: somebody who has answered already, or opened anything,
 * is sent straight back.
 */
(function () {
  "use strict";

  // The page's words in the reader's language, from `strings.js` (targum-internal#184).
  var words = window.TargumStrings;
  var t = words.t;

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


  // Where a door goes. The box is the link, so this is the only href on it.
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


  /* What was pressed, and nothing else about it (targum-internal#127). A `control` event
     carries a name and the window's width — never which text, never where in it, never
     the time. */
  function counted(name) {
    if (window.TargumEvents) window.TargumEvents.note({ kind: "control", control: name });
  }


  /* --- 1. which language they are learning ------------------------------------ */

  /* The six, in the boards' order, each said in its own greeting. The greeting is the
     language's own word and not a string of the page's: it is the one thing on the card a
     learner of that language should be able to recognise before they can read a word of
     it. The name beside it is in the page's language (`TARGUM_LANGUAGES`), and the badge
     is `lang.js`'s own (design.md §12, "A language wears how far along it is"). */
  var LEARNABLE = [
    { code: "he", greeting: "שָׁלוֹם", rtl: true },
    { code: "ru", greeting: "Здравствуйте" },
    { code: "fr", greeting: "Bonjour" },
    { code: "it", greeting: "Ciao" },
    { code: "arc", greeting: "בְּקַדְמִין", rtl: true },
    { code: "yi", greeting: "אַ גוטן טאָג", rtl: true },
  ];

  function nameOf(code) {
    return names[code] || code.toUpperCase();
  }


  /* --- 2. what they like ------------------------------------------------------ */

  /* Every subject an account may hold, by the vocabulary `accounts.Store.INTERESTS`
     keeps. An answer given when nineteen were offered is still read, and still picks a
     first text; only `OFFERED` is drawn. */
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

  /* A few, not twenty (David, 2026-10-09). Eight a reader takes in at a glance, each
     with something behind it on more than one shelf, and none of them a promise about one
     country: "Life in Israel" is a Hebrew reader's subject and the question is asked of
     six languages now. Pressing none is an answer too: "nothing in particular". */
  var OFFERED = ["everyday", "news", "stories", "history", "judaism", "science", "travel", "food"];

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


  /* --- 3. how much they read ---------------------------------------------------- */

  /* In plain words, and in each language's own texts: what a person can read, never a
     letter or a code (the review's "level codes leak", 2026-10-09). The wording is the
     Onboard boards'.

     **Hebrew's answer is kept**, as the rung it always was (design.md §12, "The arrival is
     two questions…", 2026-09-19): each sentence stands for one of the ulpan ladder's ids
     `accounts.Store.DECLARED` keeps, so the Library's first band, the first text and how
     hard the conversation writes read it exactly as before, and the first measurement
     still outvotes it. Four sentences cover the ladder at aleph, bet, gimel and dalet;
     the You page still offers all eight to a reader who wants the finer step.

     **Every other language's answer picks the first text and is kept nowhere.** Nothing
     reads a level for Russian, French, Italian, Aramaic or Yiddish yet — `charts.seed` is
     Hebrew's — and a column for an answer nothing reads would be storage for its own
     sake. The answer places the first text along that shelf by difficulty: the first
     sentence the easiest, the last the hardest. */
  function levelsOf(code) {
    var L = function (id, say, rung) {
      return { id: id, say: say, rung: rung || "" };
    };
    if (code === "ru") {
      return [
        L("talk", t("welcome.level.ru.talk", "I can follow a short video")),
        L("story", t("welcome.level.ru.story", "I can read a short story (Chekhov)")),
        L("news", t("welcome.level.ru.news", "I can read a news article (РБК)")),
        L("novel", t("welcome.level.ru.novel", "I can read a novel (Tolstoy)")),
      ];
    }
    if (code === "it") {
      return [
        L("picture", t("welcome.level.it.picture", "I can read a picture book")),
        L("talk", t("welcome.level.it.talk", "I can follow a short video")),
        L("story", t("welcome.level.it.story", "I can read a short story")),
        L("news", t("welcome.level.it.news", "I can read a news article")),
      ];
    }
    if (code === "fr") {
      return [
        L("starting", t("welcome.level.fr.starting", "I’m just starting")),
        L("story", t("welcome.level.fr.story", "I can read a short story")),
      ];
    }
    if (code === "arc") {
      return [
        L("new", t("welcome.level.arc.new", "I’m new to Aramaic")),
        L("onkelos", t("welcome.level.arc.onkelos", "I can read Onkelos")),
        L("jonathan", t("welcome.level.arc.jonathan", "I can read Jonathan on the Prophets")),
      ];
    }
    if (code === "yi") {
      return [
        L("starting", t("welcome.level.yi.starting", "I’m just starting")),
        L("sentences", t("welcome.level.yi.sentences", "I can read short, simple sentences")),
        L("most", t("welcome.level.yi.most", "I read most things without help")),
      ];
    }
    return [
      L("letters", t("welcome.level.he.letters", "I’m learning the letters"), "aleph"),
      L("sentences", t("welcome.level.he.sentences", "I can read short, simple sentences"), "bet"),
      L("news", t("welcome.level.he.news", "I read the news with a dictionary nearby"), "gimel"),
      L("most", t("welcome.level.he.most", "I read most things without help"), "dalet"),
    ];
  }

  function levelAsks(code) {
    if (code === "ru") return t("welcome.level.asks.ru", "How much Russian can you read?");
    if (code === "fr") return t("welcome.level.asks.fr", "How much French can you read?");
    if (code === "it") return t("welcome.level.asks.it", "How much Italian can you read?");
    if (code === "arc") return t("welcome.level.asks.arc", "How much Aramaic can you read?");
    if (code === "yi") return t("welcome.level.asks.yi", "How much Yiddish can you read?");
    return t("welcome.level.asks.he", "How much Hebrew can you read?");
  }


  /* --- the first text ----------------------------------------------------------- */

  /* Which of the texts a subject can answer to open, given the rung. Where the rows say
     what rung each was written for (`level.name`, the ladder `level.py` climbs), that is
     read first: the hardest text at or under the rung they named — one they can follow —
     and where nothing is that easy, the easiest there is. A shelf that does not say is
     placed by difficulty along the ladder. No rung, and the order the shelf already has
     is the order. */
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
    return pickByShare(rows, charts.seedFraction(rung));
  }

  //: The row `share` of the way along these, easiest first, by the difficulty each carries.
  function pickByShare(rows, share) {
    if (!rows.length) return null;
    var sorted = rows.slice().sort(function (a, b) {
      return (a.difficulty || 0) - (b.difficulty || 0);
    });
    var at = Math.round(Math.max(0, Math.min(1, share)) * (sorted.length - 1));
    return sorted[at] || sorted[0];
  }

  /* A first text that can be heard, where there is one (targum-internal#335). The second
     thing a new reader should find out is that the page has a voice, and they cannot find
     that out on a silent text. */
  function voiced(rows) {
    var heard = rows.filter(function (reader) {
      return reader.spoken || reader.video;
    });
    return heard.length ? heard : rows;
  }

  /* A first text with their language under it, where any of their subjects has one. The
     shelf is English throughout and Russian in places, so a reader who has just said
     Русский would otherwise open a page with English under every line. */
  function inTheirs(rows) {
    var code = readsInto();
    if (!code || code === "en") return [];
    return rows.filter(function (reader) {
      return (reader.targets || []).indexOf(code) >= 0;
    });
  }

  /* Whether a row is one this reader can follow, by the rung they named: written for
     it, under it, or one above — a stretch, not a wall (2026-09-28). */
  function inReach(reader, rung) {
    var said = rung ? charts.DECLARED_RUNGS.indexOf(rung) : -1;
    var at = rungOf(reader);
    return said < 0 || at < 0 || at <= said + 1;
  }

  /* The first text for a reader who has opened nothing, in Hebrew: the first of their
     subjects the shelf can answer, and within it the row nearest the rung they named.
     A reader who named a rung and no subject gets the modern shelf at that rung. */
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
    if (rung) {
      // Reach before voice: a voice is the second thing to find, and it is found on a
      // page the reader can follow.
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

  /* The first text in any other language: a subject they like where that shelf has one,
     placed along it by how much they said they read. `share` is 0 for the first sentence
     and 1 for the last, and 0 for "I'm not sure", which shows the easiest page there is. */
  function firstElsewhere(handed, share) {
    var liked = handed.filter(function (reader) {
      return arrived.some(function (id) {
        var want = interestOf(id);
        return want && wanted(reader, want);
      });
    });
    var pool = liked.length ? liked : handed;
    var theirs = inTheirs(pool);
    return pickByShare(voiced(theirs.length ? theirs : pool), share);
  }


  /* --- what is kept ------------------------------------------------------------- */

  /* What this reader said, kept on the account so it travels between devices the way the
     rest of the profile does. The browser holds a copy so the row does not flash back on
     a page drawn before `/account/me` answers. */
  var ARRIVED = "targum:arrived";
  //: That the questions were answered on this browser, whatever the answers were: liking
  //: nothing in particular and not being sure are answers, and are not asked again.
  var WELCOMED = "targum:welcomed";

  function readList(name) {
    var raw = "";
    try {
      raw = localStorage.getItem(name) || "";
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

  function keep(name, value) {
    try {
      if (window.targumKeep) window.targumKeep(name, value);
      else localStorage.setItem(name, value);
    } catch (e) {
      /* nowhere to keep it; the account still has it */
    }
  }

  // `keepalive`, because the last answer is posted on the way out of the page.
  function post(where, body) {
    fetch(keyed(where), {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(function () {
      /* the browser's copy still decides this visit */
    });
  }

  function remember(ids) {
    arrived = ids.slice();
    keep(ARRIVED, arrived.join(","));
    post("/account/interest", { interest: arrived });
  }

  //: The rung, kept the way the subjects are: the account has it, the browser holds a
  //: copy. "" takes an earlier answer back.
  function rememberLevel(id) {
    keep(charts.DECLARED, id);
    post("/account/level", { level: id });
  }

  /* The language they are learning, the way the top bar's menu keeps it: in this browser,
     and on the account as the language they are in now, turned on where it was not
     (`/account/language` with `add`, design.md §12, 2026-10-07). Never the profile's
     wholesale form: an account with no rows is learning Hebrew by default, and writing
     one row of Russian there would drop the Hebrew (`Store.also_learning` writes the
     whole set down the first time anything is added). */
  function sayLearning(code) {
    if (lang && lang.set) lang.set(code);
    if (!who || !who.signedIn) {
      if (code !== "he") keep("targum:learning", JSON.stringify(["he", code]));
      return;
    }
    ask("/account/language", { language: code, add: true })
      .then(function (answer) {
        if (answer && answer.learning && answer.learning.length) {
          keep("targum:learning", JSON.stringify(answer.learning));
        }
      })
      .catch(function () {
        /* the browser's choice still decides this visit */
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


  /* --- the screens ------------------------------------------------------------- */

  /* One question a screen (David, 2026-09-19), and every screen a question: the step is
     said in words in the head, "1 of 3", and the welcome card, the name and the
     connector's card are gone with the boards that did not draw them (2026-10-09). A
     pressed answer is marked the boards' way — the primary's ring and wash — and
     Continue is the one filled press. Back on every screen but the first. */
  function drawArrival(readers, shared, finish) {
    var host = document.getElementById("arrival");
    var langs = document.getElementById("arrival-langs");
    var row = document.getElementById("arrival-doors");
    var rungs = document.getElementById("arrival-levels");
    var unsure = document.getElementById("arrival-unsure");
    var done = document.getElementById("arrival-done");
    var back = document.getElementById("arrival-back");
    var backMark = document.getElementById("arrival-back-mark");
    var where = document.getElementById("arrival-step");
    var note = document.getElementById("arrival-foot-note");
    var tongues = document.getElementById("arrival-tongues");
    var asksIn = document.getElementById("arrival-asks-language");
    var asksLevel = document.getElementById("arrival-asks-level");
    var screenOf = {
      tongue: document.getElementById("arrival-language"),
      learning: document.getElementById("arrival-learning"),
      subjects: document.getElementById("arrival-subjects"),
      level: document.getElementById("arrival-level"),
    };
    if (!host || !langs || !row || !rungs || !done || !screenOf.learning) return;
    var labels = interestLabels();
    var picked = arrived.filter(function (id) {
      return OFFERED.indexOf(id) >= 0;
    });
    var learning = (lang && lang.current && lang.current([])) || "he";
    if (!LEARNABLE.some(function (one) {
      return one.code === learning;
    })) learning = "he";
    var level = null;

    var withTongue = !!(screenOf.tongue && tongues && asksIn && asksTongue());
    var order = withTongue
      ? ["tongue", "learning", "subjects", "level"]
      : ["learning", "subjects", "level"];
    var step = withTongue && thisVisit() ? 1 : 0;
    if (!withTongue) handOverTongue();
    drawTongueSwitch(withTongue ? null : document.getElementById("arrival-switch"));

    function mark(list, on) {
      Array.prototype.forEach.call(list.children, function (press) {
        var yes = on(press);
        press.classList.toggle("is-on", yes);
        if (press.getAttribute("role") === "radio") {
          press.setAttribute("aria-checked", yes ? "true" : "false");
        } else {
          press.setAttribute("aria-pressed", yes ? "true" : "false");
        }
      });
    }

    function settle() {
      var now = order[step];
      Object.keys(screenOf).forEach(function (name) {
        if (screenOf[name]) screenOf[name].hidden = name !== now;
      });
      if (where) {
        where.textContent = t("learn.arrival.step", "{n} of {of}")
          .replace("{n}", String(step + 1))
          .replace("{of}", String(order.length));
      }
      // The language question answers itself on a press, as it always did; the rest
      // wait for Continue, which wakes when there is an answer to take.
      done.hidden = now === "tongue";
      done.disabled = now === "level" && !level;
      if (back) back.hidden = step === 0;
      if (backMark) backMark.hidden = step === 0;
      if (note) {
        note.textContent =
          now === "learning"
            ? t("welcome.learning.later", "You can add a second language later.")
            : "";
        note.hidden = now !== "learning";
      }
      document.body.setAttribute("data-step", now);
    }

    function arrive() {
      settle();
      if (window.scrollTo) window.scrollTo(0, 0);
      var now = order[step];
      var first = null;
      if (now === "tongue") first = tongues.children[0];
      if (now === "learning") first = langs.querySelector(".is-on") || langs.children[0];
      if (now === "subjects") first = row.children[0];
      if (now === "level") first = rungs.querySelector(".is-on") || rungs.children[0];
      if (first && first.focus) first.focus({ preventScroll: true });
    }

    function onward() {
      if (step < order.length - 1) {
        step += 1;
        arrive();
        return;
      }
      finish(learning, level);
    }

    /* 1. The six languages: greeting, name and badge, the one pressed in the primary.
       The language the browser is already in is pressed to start with — Hebrew for
       nearly everybody — so Continue is never asleep on the first screen. */
    LEARNABLE.forEach(function (one) {
      var press = document.createElement("button");
      press.type = "button";
      press.className = "arrival-lang";
      press.classList.add("arrival-opt");
      press.setAttribute("role", "radio");
      press.setAttribute("data-code", one.code);
      var greeting = el("span", "arrival-greeting" + (one.rtl ? " is-rtl" : ""), one.greeting);
      greeting.setAttribute("lang", one.code);
      if (one.rtl) greeting.setAttribute("dir", "rtl");
      var said = el("span", "arrival-lang-name");
      said.appendChild(el("span", "arrival-lang-word", nameOf(one.code)));
      var badge = lang && lang.badge ? lang.badge(one.code) : null;
      if (badge) said.appendChild(badge);
      press.appendChild(greeting);
      press.appendChild(said);
      press.addEventListener("click", function () {
        learning = one.code;
        level = null;
        mark(langs, function (p) {
          return p.getAttribute("data-code") === learning;
        });
      });
      langs.appendChild(press);
    });
    mark(langs, function (p) {
      return p.getAttribute("data-code") === learning;
    });

    // 2. A few subjects, any number of them, a press each to put on and take off.
    OFFERED.forEach(function (id) {
      var press = document.createElement("button");
      press.type = "button";
      press.className = "arrival-door";
      press.classList.add("arrival-opt");
      press.setAttribute("data-id", id);
      press.textContent = labels[id] || id;
      press.addEventListener("click", function () {
        var at = picked.indexOf(id);
        if (at === -1) picked.push(id);
        else picked.splice(at, 1);
        mark(row, function (p) {
          return picked.indexOf(p.getAttribute("data-id")) >= 0;
        });
      });
      row.appendChild(press);
    });
    mark(row, function (p) {
      return picked.indexOf(p.getAttribute("data-id")) >= 0;
    });

    // 3. Drawn for the language chosen, each time the screen comes up.
    function drawLevels() {
      rungs.textContent = "";
      if (asksLevel) asksLevel.textContent = levelAsks(learning);
      levelsOf(learning).forEach(function (one, at, all) {
        var press = document.createElement("button");
        press.type = "button";
        press.className = "arrival-rung";
        press.classList.add("arrival-opt");
        press.setAttribute("role", "radio");
        press.setAttribute("data-id", one.id);
        press.textContent = one.say;
        press.addEventListener("click", function () {
          level = { id: one.id, rung: one.rung, share: all.length > 1 ? at / (all.length - 1) : 0 };
          mark(rungs, function (p) {
            return p.getAttribute("data-id") === one.id;
          });
          settle();
        });
        rungs.appendChild(press);
      });
      mark(rungs, function (p) {
        return !!level && p.getAttribute("data-id") === level.id;
      });
    }

    /* The interface language, a row each in its own name; pressing one is the answer.
       The question is said once in every language offered, a line each and each marked
       as what it is, so a screen reader reads Russian in a Russian voice. */
    if (withTongue) {
      asksIn.textContent = "";
      offered().forEach(function (code) {
        var line = document.createElement("span");
        line.setAttribute("lang", code);
        line.textContent = TONGUES[code].asks;
        asksIn.appendChild(line);
        var tongue = document.createElement("button");
        tongue.type = "button";
        tongue.className = "arrival-opt arrival-rung";
        tongue.setAttribute("lang", code);
        tongue.textContent = TONGUES[code].name;
        tongue.addEventListener("click", function () {
          thisVisit("1");
          sayTongue(code, onward);
        });
        tongues.appendChild(tongue);
      });
      /* And a row for everybody else (David, 2026-09-20): it sets English, the only other
         language there is to read into, and it is an answer, so they are not asked again. */
      var other = document.createElement("button");
      other.type = "button";
      other.className = "arrival-opt arrival-rung";
      other.textContent = OTHER_TONGUE;
      other.addEventListener("click", function () {
        thisVisit("1");
        sayTongue("en", onward);
      });
      tongues.appendChild(other);
    }

    done.onclick = function () {
      var now = order[step];
      if (now === "learning") {
        counted("welcome-learning");
        sayLearning(learning);
        drawLevels();
      } else if (now === "subjects") {
        counted("welcome-likes");
        remember(picked);
      } else if (now === "level" && !level) {
        return;
      }
      onward();
    };
    // Not sure is an answer too: no level is kept, and the easiest page there is opens.
    if (unsure) {
      unsure.onclick = function () {
        counted("welcome-unsure");
        level = null;
        finish(learning, null);
      };
    }
    function goBack() {
      if (step === 0) return;
      step -= 1;
      arrive();
    }
    if (back) back.onclick = goBack;
    if (backMark) backMark.onclick = goBack;
    if (order[step] === "level") drawLevels();
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

  // Only from a page a server is behind: opened off the disk there is nowhere to go.
  function served() {
    return !window.location.protocol || /^https?:$/.test(window.location.protocol);
  }

  /* Home, with the key where there is one, and in the language just chosen where it is
     not Hebrew (`?learning=`, which `lang.js` takes as the menu takes a press).
     `replace`, so Back does not land here again. */
  function home(code) {
    over();
    var to = code && code !== "he" ? "/?learning=" + encodeURIComponent(code) : "/";
    if (served() && window.location.replace) window.location.replace(keyed(to));
  }

  /* What the account already holds, adopted before anything is decided: the subjects and
     the rung belong to the person, so somebody who answered on a phone is not asked again
     on a laptop. Only ever adopted, never cleared from here (targum-internal#294). */
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
      var modern = trackDoor("he", "modern", readers, shared);
      var biblical = trackDoor("he", "biblical", readers, shared);
      var reading = readers.concat(shared).some(function (reader) {
        return reader.opened > 0;
      });
      var answered =
        arrived.length || held(WELCOMED) || !!(who && who.signedIn && who.declared);
      var asking = !answered && !reading && !modern.opened && !biblical.opened;
      var waiting = document.getElementById("arrival-waiting");
      if (waiting) waiting.hidden = true;
      if (!asking) return home();
      drawArrival(readers, shared, function (code, level) {
        keep(WELCOMED, "1");
        over();
        var handed = shared.filter(function (reader) {
          return inLanguage(reader, code);
        });
        var target = null;
        var via = { state: "start" };
        if (code === "he") {
          // The rung is Hebrew's to keep: "I'm not sure" takes an earlier one back.
          rememberLevel(level && level.rung ? level.rung : "");
          target = firstText(handed, code);
          if (!target) {
            // Nothing their answers can choose: the track's own start, the page the
            // FirstRun board's "One to start with" offers.
            var track = modern.reader ? modern : biblical;
            target = track.reader;
          }
        } else {
          target = firstElsewhere(handed, level ? level.share : 0);
        }
        if (!target) return home(code);
        /* Into the text, not onto its contents page (found by QA, 2026-09-20). The first
           chapter that is ready is where "Start reading" on that page goes anyway. */
        var opening = (target.chapters || []).filter(function (chapter) {
          return chapter && chapter.ready && chapter.file;
        })[0];
        if (opening) via = { state: "start", path: target.name + "/reader/" + opening.file };
        window.location.href = hrefOf(target, via);
      });
    })
    .catch(function () {
      // Signed out on a box that wants an account, or the server went away: there is
      // nothing to ask with, and home says what it can.
      home();
    });

  // Exposed for the tests and for nothing else: the picks the last answer opens.
  window.TargumArrival = {
    firstText: firstText,
    firstElsewhere: firstElsewhere,
    levels: levelsOf,
    offered: OFFERED,
    over: OVER,
  };
})();
