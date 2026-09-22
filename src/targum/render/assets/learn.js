/* Learn — the page you land on, and everything you are learning.
 *
 * How many words you know, then the row of doors — carry on, what is suggested, what you
 * read lately, what you follow — over the sheet. The count is one line rather
 * than a panel of numbers: engagement is welcome and arcade is not (design.md §1), and
 * the charts that make an account of it live on Your Progress. That rule used to be
 * written "the reader is a reader rather than a player"; the sentence was withdrawn on
 * 2026-09-03 when a text that carries media began opening as its media, but the half of
 * it that keeps a scoreboard off this page still stands.
 *
 * Everything here is drawn from what already exists. `targum:opened` says which text you
 * had open last and already syncs; `/readers` says what is on your shelf and, since
 * today, how much of each one's vocabulary you have already marked known. Nothing new is
 * tracked to make this page possible.
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

  function post(path, body) {
    return ask(path, body).then(function (answer) {
      if (answer && answer.error) throw new Error(answer.error);
      return answer;
    });
  }

  function reload() {
    location.reload();
  }

  Array.prototype.forEach.call(
    document.querySelectorAll(".site-nav a, .doors a[data-door]"),
    function (link) {
      link.href = keyed(link.getAttribute("href"));
    }
  );

  /* How many texts the Recently read menu holds (2026-09-11: the shelf under the sheet
     became a menu in the row, "the last few and a link to full history"). Learn is
     where you land, not where you study: the top of the list and the way to the rest. */
  var RECENT = 5;

  /* --- folding a panel away --------------------------------------------------
   *
   * Three lists on one page is a long page, and which of them somebody wants open is
   * theirs to decide rather than ours to guess. Kept in this browser: it is a state of a
   * screen, not a fact about a person.
   */

  var FOLDED = "targum:folded";

  function folded() {
    try {
      return JSON.parse(localStorage.getItem(FOLDED) || "{}");
    } catch (e) {
      return {};
    }
  }

  function folds() {
    var shut = folded();
    Array.prototype.forEach.call(document.querySelectorAll(".fold"), function (press) {
      var panel = press.closest("section");
      var body = panel && panel.querySelector(".fold-body");
      if (!body) return;
      press.setAttribute("aria-controls", body.id);

      function show(open) {
        press.setAttribute("aria-expanded", open ? "true" : "false");
        body.hidden = !open;
      }

      show(!shut[body.id]);
      press.addEventListener("click", function () {
        var open = press.getAttribute("aria-expanded") !== "true";
        show(open);
        var now = folded();
        if (open) delete now[body.id];
        else now[body.id] = 1;
        try {
          localStorage.setItem(FOLDED, JSON.stringify(now));
        } catch (e) {}
      });
    });
  }

  folds();

  function named(code) {
    return names[code] || (code || "").toUpperCase();
  }

  /* --- what you have already ------------------------------------------------ */

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  var ago = shelf.ago;
  var base = shelf.base;

  // Every language a text can be read in: Daniel's Hebrew and Aramaic, a Torah book's
  // Hebrew and the Onkelos beside it (2026-09-14). A row from before has its one.
  function inLanguage(thing, code) {
    var all = thing.languages && thing.languages.length ? thing.languages : [thing.language];
    for (var n = 0; n < all.length; n++) if (base(all[n]) === code) return true;
    return false;
  }

  /* Languages this reader has words in. Signed out with nothing kept, this is empty
     and the switcher does not appear, which is the intended resting state. */
  function kept() {
    var found = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var name = localStorage.key(i) || "";
        if (name.indexOf("targum:vocab:") === 0) {
          found.push({ language: name.slice("targum:vocab:".length) });
        }
      }
    } catch (e) {}
    return found;
  }


  /* --- what you came back for ------------------------------------------------ */

  function share(reader) {
    // `known` is absent for a targum built without word-level annotation, which is a
    // normal state rather than a fault. Saying nothing beats saying "0% known", because
    // "not measured" and "you know none of this" are very different claims about a book.
    if (typeof reader.known !== "number") return "";
    // "0% of its words" on the first card a new reader sees is true and unkind; the
    // line starts once there is something to say.
    if (!reader.known) return "";
    return t("learn.known-share", "You know {share}%", { share: Math.round(reader.known * 100) });
  }

  // The title in English under the Hebrew one, where the catalogue has one. An upload
  // has none and the line stays away.
  function english(id, text) {
    var line = document.getElementById(id);
    if (!line) return;
    line.hidden = !text;
    line.textContent = text || "";
  }

  /* --- the doors ---------------------------------------------------------------
   *
   * Two Hebrews, two doors. Readers of modern Hebrew and readers of the Bible are two
   * cohorts with little crossover, each with its beginners, its false beginners and its
   * advanced readers; so the page always shows both tracks, Modern on the left and
   * Biblical on the right, each carrying its own next step. The track is the register,
   * never a level: nobody is asked how good they are, and nothing is stored about which
   * track they are "on". What tells a beginner from a false beginner is what they have
   * marked, which the app already measures.
   *
   * A door's state is one word. Start here: nothing of this Hebrew opened yet, and the
   * first of its sequence waits. Continue: the text last opened, unfinished. Up next:
   * the last one is finished and the sequence has more. A step up: the sequence is done
   * and the catalogue's nearest harder text is offered instead.
   */
  var TRACKS = {
    modern: t("learn.track.modern", "Modern Hebrew"),
    biblical: t("learn.track.biblical", "Biblical Hebrew"),
  };
  /* The verb follows the medium (targum-internal#337, 2026-09-19; design.md §6). "Copy of
     buttons and various features in the app assumes the reader is there to read — but
     many will be there to listen and watch." A row says what it is — `video` where it
     kept its pictures, `heard` where it began as a recording — so a control names what
     the person will do with *this* thing.

     Not `spoken`: that is true of most of the shelf. The Tanakh has a reading attached and
     every scene is voiced, and both are texts somebody reads with a voice beside them; a
     first cut keyed on it told a reader halfway through a scene to "Continue listening"
     (caught by the tests, 2026-09-19). */
  function mediumOf(reader) {
    if (reader && reader.video) return "watch";
    return reader && reader.heard ? "listen" : "read";
  }

  var CONTINUE = t("learn.state.carry", "Continue reading");
  var CARRY = {
    read: CONTINUE,
    listen: t("learn.state.carry-listening", "Continue listening"),
    watch: t("learn.state.carry-watching", "Continue watching"),
  };
  var BEGIN = {
    read: t("learn.card.read", "Read"),
    listen: t("learn.card.listen", "Listen"),
    watch: t("learn.card.watch", "Watch"),
  };
  var HERE = {
    read: t("learn.page.read-here-or-go-full-screen", "Read here, or go full screen."),
    listen: t("learn.page.listen-here-or-go-full-screen", "Listen here, or go full screen."),
    watch: t("learn.page.watch-here-or-go-full-screen", "Watch here, or go full screen."),
  };

  //: What a door says of itself, over the text it leads to.
  function stateOf(door, reader) {
    if (door.heading) return door.heading;
    if (door.state === "carry" || !STATES[door.state]) return CARRY[mediumOf(reader)];
    return STATES[door.state];
  }

  var STATES = {
    start: t("learn.state.start", "Start here"),
    carry: CONTINUE,
    next: t("learn.state.next", "Up next"),
    up: t("learn.state.up", "A step up"),
  };

  var scenes = window.TargumScenes || null;

  function sceneOf(reader) {
    return scenes && reader ? scenes.numberOf(reader.entry) : 0;
  }

  // The facts under a title: which scene of how many, how much is left, how long it
  // is, whether it can be heard. Never "ready" — build vocabulary — and never a share
  // of zero.
  function facts(reader, door) {
    var out = [];
    var number = sceneOf(reader);
    if (number) {
      out.push(
        door.total
          ? t("learn.scene-of", "Scene {n} of {total}", { n: number, total: door.total })
          : t("learn.scene", "Scene {n}", { n: number })
      );
      if (door.state === "carry" && typeof reader.fresh === "number" && reader.fresh > 0) {
        out.push(tn("learn.words-left", reader.fresh, "{n} word left", "{n} words left"));
      } else if (reader.words) {
        out.push(tn("learn.words", reader.words, "{n} words", "{n} words"));
      }
    } else if (reader.chapters && reader.chapters.length > 1) {
      // "4 of 4" is a fraction with nothing left to say; "2 of 4 translated" says what
      // the fraction is a fraction of.
      out.push(
        reader.readyChapters === reader.chapters.length
          ? tn("learn.chapters", reader.chapters.length, "{n} chapters", "{n} chapters")
          : t("learn.chapters-translated", "{done} of {total} translated", {
              done: reader.readyChapters,
              total: reader.chapters.length,
            })
      );
    } else if (reader.sections > 1) {
      out.push(tn("learn.parts", reader.sections, "{n} parts", "{n} parts"));
    } else if (reader.minutes && door.state !== "carry") {
      out.push(t("learn.minutes", "{n} min", { n: reader.minutes }));
    }
    // One word, as on the library's rows: a video can be heard too, and saying both
    // says less than "video" does.
    if (reader.video) out.push(t("learn.video", "video"));
    else if (reader.spoken) out.push(t("learn.audio", "audio"));
    if (door.state === "carry" && !number) {
      // How long is left, from what the reader records of the sections finished and
      // the text's own length (2026-09-11): "about 12 min left" says where you are
      // without a word more.
      var left = minutesLeft(reader);
      if (left) out.push(left);
      out.push(
        reader.opened
          ? t("learn.opened", "opened {when}", { when: ago(reader.opened) })
          : t("learn.not-opened", "not opened yet")
      );
    }
    return out.join(" · ");
  }

  // The share of a text's sections the reader has finished, 0 to 1, off `targum:docs`
  // as the reader writes it: a map of the sections done, or the one old timestamp that
  // stood for the whole document.
  function progress(reader) {
    if (!reader || !reader.document) return 0;
    var record = stored("targum:docs")[reader.document];
    if (!record) return 0;
    var total = (reader.chapters && reader.chapters.length) || reader.sections || 1;
    if (record.sections && typeof record.sections === "object") {
      var done = 0;
      Object.keys(record.sections).forEach(function (part) {
        if (record.sections[part]) done += 1;
      });
      return Math.min(1, done / total);
    }
    return record.done ? 1 : 0;
  }

  function minutesLeft(reader) {
    if (!reader || !reader.minutes) return "";
    var share = progress(reader);
    if (share >= 1) return t("learn.finished", "finished");
    var left = Math.max(1, Math.round(reader.minutes * (1 - share)));
    return share > 0
      ? t("learn.minutes-left", "about {n} min left", { n: left })
      : t("learn.minutes-about", "about {n} min", { n: left });
  }

  // The label above a door's heading, naming the track; none for a language with one.
  function trackLabel(id, register) {
    var label = document.getElementById(id);
    if (!label) return;
    var name = register ? TRACKS[register] || "" : "";
    label.hidden = !name;
    label.textContent = name;
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

  // Every text the sheet has been given since the page settled on its language, newest
  // first: what the phone's cards lead with, since the sheet is not drawn there.
  var sheets = [];

  /* The rail says which of its cards is the one in the sheet (2026-09-18).
   *
   * By the reader rather than by the door: the rail draws one card per text and drops
   * the duplicates, so the card standing for what you are reading is often the one built
   * from `sheets`, which has no door id on it at all. The reader is the thing both halves
   * actually agree about.
   *
   * Called from `drawCarry` and nowhere else, because that is the one function that runs
   * every time the sheet changes — including the swaps a rail press makes, which redraw
   * no cards and would otherwise leave the mark behind on the card you came from. */
  function markRail(reader) {
    var list = document.getElementById("learn-cards");
    if (!list || !reader) return;
    var here = reader.entry || reader.id || "";
    Array.prototype.forEach.call(list.querySelectorAll(".learn-card"), function (one) {
      var mine = one.getAttribute("data-entry");
      if (here && mine === here) one.setAttribute("aria-current", "true");
      else one.removeAttribute("aria-current");
    });
  }

  function drawCarry(reader, door) {
    var sheet = document.getElementById("carry-sheet");
    var panel = document.getElementById("carry");
    if (!reader) {
      sheet.hidden = true;
      showing = null;
      markDoor("");
      return;
    }
    door = door || { state: "carry" };
    sheet.hidden = false;
    showing = reader;
    markRail(reader);
    var heading = document.getElementById("carry-heading");
    if (heading) heading.textContent = stateOf(door, reader);
    var hint = document.getElementById("carry-hint");
    if (hint) hint.textContent = HERE[mediumOf(reader)];
    markDoor(door.id || "");
    trackLabel("carry-track", door.register);
    panel.classList.toggle("primary", !!door.primary);
    panel.href = hrefOf(reader, door);
    sheets = sheets.filter(function (one) {
      return hrefOf(one.reader, one.door) !== panel.href;
    });
    sheets.unshift({ reader: reader, door: door });
    panel.setAttribute("data-entry", reader.entry || reader.id || "");

    var cover = document.getElementById("carry-cover");
    cover.textContent = "";
    var pictured = reader.entry || reader.id || reader.name;
    if (pictured) {
      cover.appendChild(
        window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(pictured)), {
          title: reader.title,
          language: reader.language,
          drawn: reader.drawn,
        })
      );
    }

    var title = document.getElementById("carry-title");
    title.textContent = reader.title;
    title.setAttribute("lang", reader.language);
    english("carry-english", reader.english);

    document.getElementById("carry-meta").textContent = door.meta !== undefined ? door.meta : facts(reader, door);

    var known = document.getElementById("carry-known");
    var said = share(reader);
    known.hidden = !said;
    known.textContent = said;
    // The line along the foot: how far through the text the reader is.
    var line = document.getElementById("carry-progress");
    if (line) {
      var share_ = door.state === "carry" && !door.src ? progress(reader) : 0;
      line.hidden = !share_;
      line.style.setProperty("--done", String(share_));
      line.setAttribute("aria-label", t("learn.read-share", "{share}% through", { share: Math.round(share_ * 100) }));
    }
    drawFrame(reader, door);
  }

  // The reader's own path under `/reader/`: the text's opening page, or the page the
  // conversation offered (`<name>/reader/<file>`), each segment encoded on its own.
  function readerPath(reader, door) {
    var path = door.path || reader.name + "/reader/index.html";
    return path.split("/").map(encodeURIComponent).join("/");
  }

  // The address the sheet would frame, kept while the window is too short to hold it.
  var framing = "";

  // The sheet's window (§13): the reader itself, framed and working, at the place it
  // was left — `preview=1` tells it it is on the front page, so it draws no bar, keeps
  // its own links in the frame and counts a visit at the first press. Only where the
  // door is the reader: a step up past the sequence is a library row, and a library
  // row is not a text to look at.
  function drawFrame(reader, door) {
    var window_ = document.getElementById("carry-window");
    var frame = document.getElementById("carry-frame");
    if (!window_ || !frame) return;
    if (!door.src && (door.href || !reader.name)) {
      framing = "";
      window_.hidden = true;
      return;
    }
    frame.title = reader.title || "";
    // A series' instalment names its reader's page itself (`door.src`): the weekly
    // portion's and a cycle's live under their own `/read/`, not under `/reader/`.
    var src = keyed(door.src || "/reader/" + readerPath(reader, door));
    src += (src.indexOf("?") < 0 ? "?" : "&") + "preview=1";
    framing = src;
    window_.hidden = false;
    fitWindow();
  }

  // A phone frames no reader (David, 2026-09-14: "the reading on mobile learn page had to
  // be a card, not an actual reader"). A phone gets the cards below instead, one for each
  // text the page can offer, and the frame is not loaded behind them. At a desk the
  // window is the reader, framed and working, as before.
  var phone = window.matchMedia ? window.matchMedia("(max-width: 40rem)") : null;
  function fitWindow() {
    var window_ = document.getElementById("carry-window");
    var frame = document.getElementById("carry-frame");
    var src = framing;
    if (!window_ || !frame || !src) return;
    if (phone && phone.matches) {
      window_.hidden = true;
      return;
    }
    window_.hidden = false;
    show(frame, src);
  }

  // Set only when it changes: a frame reloads on every write to its address.
  function show(frame, src) {
    if (frame.getAttribute("src") === src) return;
    frame.setAttribute("src", src);
  }
  window.addEventListener("resize", fitWindow);
  if (window.ResizeObserver) {
    var watching = new ResizeObserver(fitWindow);
    [".site-head", ".learn-head", ".page-head"].forEach(function (selector) {
      var above = document.querySelector(selector);
      if (above) watching.observe(above);
    });
  }

  /* --- the greeting, today, and the row of doors (2026-09-11) ---------------------
   * Decided with David: the page opens with a greeting and today, the count at the end
   * of the row, and under it one press for each text the page could show in the sheet
   * — what you were reading, what is next, the week's portion, a cycle you follow.
   */
  // The time of day and nothing else: no "Shabbat shalom" on a Saturday (David,
  // 2026-09-11: somebody on the internet on Shabbat does not get one).
  //
  // Said in the language the page is in, in Latin letters (David, 2026-09-14): "Boker tov"
  // rather than "Good morning" on Hebrew, so the first words on the page are ones the
  // reader can say before they can read the script. Morning, afternoon, evening. The
  // afternoon is Shalom on Hebrew and Shlama, peace, on Aramaic; French and Italian say
  // their day's greeting until the evening (David, 2026-09-14). The English is the title.
  var GREETINGS = {
    he: ["Boker tov", "Shalom", "Erev tov"],
    arc: ["Tzafra tava", "Shlama", "Ramsha tava"],
    yi: ["Gut morgn", "Gutn tog", "Gutn ovnt"],
    fr: ["Bonjour", "Bonjour", "Bonsoir"],
    ru: ["Dobroye utro", "Dobry den", "Dobry vecher"],
    it: ["Buongiorno", "Buongiorno", "Buonasera"],
  };
  var ENGLISH_GREETINGS = [
    t("learn.greeting.morning", "Good morning"),
    t("learn.greeting.afternoon", "Good afternoon"),
    t("learn.greeting.evening", "Good evening"),
  ];
  function partOfDay() {
    var hour = new Date().getHours();
    // The small hours belong to the evening before: half past midnight is not "Boker tov"
    // to somebody still up studying (found by QA, 2026-09-20).
    if (hour < 5) return 2;
    return hour < 12 ? 0 : hour < 18 ? 1 : 2;
  }
  function greeting(name, code) {
    var said = (GREETINGS[code] || ENGLISH_GREETINGS)[partOfDay()];
    return said + (name ? ", " + name : "") + ".";
  }
  var greetedName = "";
  function drawGreeting() {
    var hello = document.getElementById("greeting");
    if (!hello) return;
    var code = speaking();
    hello.textContent = greeting(greetedName, code);
    if (GREETINGS[code]) {
      hello.setAttribute("lang", code + "-Latn");
      hello.title = ENGLISH_GREETINGS[partOfDay()];
    } else {
      hello.removeAttribute("lang");
      hello.removeAttribute("title");
    }
  }

  // A number as Hebrew letters, the way a date is written: ט״ו and ט״ז rather than
  // the Name's letters, gershayim before the last letter, a geresh on one alone.
  var ONES = ["", "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט"];
  var TENS = ["", "י", "כ", "ל", "מ", "נ", "ס", "ע", "פ", "צ"];
  var HUNDREDS = ["", "ק", "ר", "ש", "ת"];
  function gematria(n) {
    var letters = "";
    n = Math.floor(n) % 1000;
    while (n >= 400) {
      letters += "ת";
      n -= 400;
    }
    letters += HUNDREDS[Math.floor(n / 100)];
    n %= 100;
    if (n === 15) letters += "טו";
    else if (n === 16) letters += "טז";
    else letters += TENS[Math.floor(n / 10)] + ONES[n % 10];
    if (!letters) return "";
    if (letters.length === 1) return letters + "׳";
    return letters.slice(0, -1) + "״" + letters.slice(-1);
  }

  // The Hebrew date, in Hebrew letters, where the browser can reckon the calendar.
  // Intl writes the calendar but not its letters (an algorithmic numbering system is
  // outside ECMA-402), so the day and the year are lettered here.
  function hebrewDate(now) {
    try {
      var parts = new Intl.DateTimeFormat("he-u-ca-hebrew", { day: "numeric", month: "long", year: "numeric" }).formatToParts(now);
      var day = 0;
      var year = 0;
      var month = "";
      parts.forEach(function (part) {
        if (part.type === "day") day = parseInt(part.value, 10);
        else if (part.type === "year") year = parseInt(part.value, 10);
        else if (part.type === "month") month = part.value;
      });
      if (!day || !year || !month) return "";
      return gematria(day) + " ב" + month + " " + gematria(year);
    } catch (e) {
      return "";
    }
  }

  /* --- a country's calendar, beside the date (2026-09-14) -----------------------------
   *
   * The Hebrew date is Hebrew's, and Aramaic's and Yiddish's: their texts keep that
   * calendar. A reader in French, Italian or Russian is not helped by it, so the date is
   * given the way that country gives it, in its own language, with the public holiday
   * when today is one. Fixed dates, and the ones that move with Easter: the Western
   * reckoning for France and Italy, the Orthodox one for Russia.
   */
  var COUNTRIES = {
    fr: {
      locale: "fr-FR",
      easter: "western",
      fixed: {
        "1-1": "Jour de l'an",
        "5-1": "Fête du Travail",
        "5-8": "Victoire 1945",
        "7-14": "Fête nationale",
        "8-15": "Assomption",
        "11-1": "Toussaint",
        "11-11": "Armistice 1918",
        "12-25": "Noël",
      },
      moving: { 1: "Lundi de Pâques", 39: "Ascension", 50: "Lundi de Pentecôte" },
    },
    it: {
      locale: "it-IT",
      easter: "western",
      fixed: {
        "1-1": "Capodanno",
        "1-6": "Epifania",
        "4-25": "Festa della Liberazione",
        "5-1": "Festa dei Lavoratori",
        "6-2": "Festa della Repubblica",
        "8-15": "Ferragosto",
        "11-1": "Ognissanti",
        "12-8": "Immacolata Concezione",
        "12-25": "Natale",
        "12-26": "Santo Stefano",
      },
      moving: { 0: "Pasqua", 1: "Lunedì dell'Angelo" },
    },
    ru: {
      locale: "ru-RU",
      easter: "orthodox",
      fixed: {
        "1-1": "Новый год",
        "1-7": "Рождество Христово",
        "2-23": "День защитника Отечества",
        "3-8": "Международный женский день",
        "5-1": "Праздник Весны и Труда",
        "5-9": "День Победы",
        "6-12": "День России",
        "11-4": "День народного единства",
      },
      moving: { 0: "Пасха" },
    },
  };

  // Easter Sunday as a local date. Western: the Gregorian computus. Orthodox: the Julian
  // computus, moved onto the Gregorian calendar (thirteen days, true from 1900 to 2099).
  function easter(year, reckoning) {
    if (reckoning === "orthodox") {
      var a = year % 4;
      var b = year % 7;
      var c = year % 19;
      var d = (19 * c + 15) % 30;
      var e = (2 * a + 4 * b - d + 34) % 7;
      var month = Math.floor((d + e + 114) / 31);
      var day = ((d + e + 114) % 31) + 1;
      return new Date(year, month - 1, day + 13);
    }
    var g = year % 19;
    var century = Math.floor(year / 100);
    var h = (century - Math.floor(century / 4) - Math.floor((8 * century + 13) / 25) + 19 * g + 15) % 30;
    var i = h - Math.floor(h / 28) * (1 - Math.floor(29 / (h + 1)) * Math.floor((21 - g) / 11));
    var j = (year + Math.floor(year / 4) + i + 2 - century + Math.floor(century / 4)) % 7;
    var l = i - j;
    var m = 3 + Math.floor((l + 40) / 44);
    var dayOf = l + 28 - 31 * Math.floor(m / 4);
    return new Date(year, m - 1, dayOf);
  }

  function holiday(now, country) {
    var named = country.fixed[now.getMonth() + 1 + "-" + now.getDate()];
    if (named) return named;
    var sunday = easter(now.getFullYear(), country.easter);
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var after = Math.round((today - sunday) / 86400000);
    return country.moving[after] || "";
  }

  function countryDate(now, code) {
    var country = COUNTRIES[code];
    if (!country) return "";
    try {
      var said = new Intl.DateTimeFormat(country.locale, {
        weekday: "long",
        day: "numeric",
        month: "long",
      }).format(now);
      var feast = holiday(now, country);
      return feast ? said + ", " + feast : said;
    } catch (e) {
      return "";
    }
  }

  // The calendars that are Hebrew's: its own texts, and the two languages written in
  // its letters.
  var HEBREW_CALENDAR = { he: true, arc: true, yi: true };

  var lastSeries = null;
  function todayLine(series) {
    lastSeries = series || lastSeries;
    var now = new Date();
    var day = now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
    var code = speaking();
    var hebrewCalendar = HEBREW_CALENDAR[code] === true;
    var beside = hebrewCalendar ? hebrewDate(now) : countryDate(now, code);
    var parts = [beside ? day + " (" + beside + ")" : day];
    // The week's portion is the Hebrew calendar's too.
    if (hebrewCalendar) {
      (lastSeries || []).forEach(function (one) {
        var inst = one.instalment;
        if (one.id === "parasha" && inst) {
          parts.push(t("learn.this-week", "This week: {portion}", { portion: inst.hebrew || inst.title }));
        }
      });
    }
    return parts.join(" · ");
  }
  // In the calendar of the language the switcher moves to.
  window.addEventListener("targum:language", function () {
    drawGreeting();
    var today = document.getElementById("today");
    if (today && lastSeries) today.textContent = todayLine(lastSeries);
  });

  function drawHello(name, series) {
    var today = document.getElementById("today");
    greetedName = name || "";
    drawGreeting();
    if (today) today.textContent = todayLine(series);
  }

  // The row (David, 2026-09-11): Continue reading, Suggested, Recently read, and your
  // subscriptions. The conversation is the pill at the foot of the page — a "let's
  // talk about it" here was one door too many — and whatever it offers opens in the
  // sheet (`offeredText`). One door is no choice, and no row is drawn for it. The
  // subscriptions are one door with a menu under it, however many there are ("I don't
  // feel this design can handle a user having many many subscriptions"): the door
  // says Subscriptions, or the name of the one in the sheet. Recently read is the
  // same shape (2026-09-11: the shelf that stood under the sheet, as a menu — the
  // last few, and All your targums at its foot); a text read through is marked in
  // either menu.
  var doors = [];
  var showing = null;
  var RECENTLY_READ = t("learn.recent", "Recently opened");
  var SUBSCRIPTIONS = t("learn.subscriptions", "Subscriptions");
  function kind(one) {
    return one.id.indexOf("series:") === 0 ? "series" : one.id.indexOf("recent:") === 0 ? "recent" : "pill";
  }
  function drawDoors() {
    var row = document.getElementById("doors");
    if (!row) return;
    row.textContent = "";
    var shown = doors.filter(function (one) {
      return one.reader;
    });
    var pills = shown.filter(function (one) {
      return kind(one) === "pill";
    });
    var recent = shown.filter(function (one) {
      return kind(one) === "recent";
    });
    var series = shown.filter(function (one) {
      return kind(one) === "series";
    });
    row.hidden = !showing || pills.length + (recent.length ? 1 : 0) + (series.length ? 1 : 0) < 2;
    pills.forEach(function (one) {
      row.appendChild(pill(one));
    });
    if (recent.length) {
      row.appendChild(
        menu({
          id: "recent",
          label: RECENTLY_READ,
          items: recent,
          foot: { label: t("learn.all-your-targums", "All your targums"), href: "/texts" },
        })
      );
    }
    if (series.length) row.appendChild(menu({ id: "subscriptions", label: SUBSCRIPTIONS, items: series }));
    /* And one door that is not a text (design.md §12, 2026-09-22): targum in Claude and
       ChatGPT. Styled exactly like the reading doors, because a door drawn as a lesser
       thing reads as an advertisement and this page does not carry those.

       It is appended rather than counted: the rule above still decides whether a row of
       doors is worth drawing at all, on the reading doors alone. A row holding nothing
       but this would be the first thing a new reader met, which is the push the panel
       below promises not to be. */
    if (!row.hidden && window.TARGUM_CONNECTOR) row.appendChild(connectDoor());
    drawCards();
    markDoor(current);
    // The cards are only now in the page, so the mark the sheet set before they existed
    // has nothing to sit on. Put it back.
    if (showing) markRail(showing);
  }

  /* --- on a phone, cards (2026-09-14) -------------------------------------------------
   * David, on a phone: the framed reader on Learn "had to be a card, not an actual
   * reader", and then "maybe we can have multiple cards on mobile, giving more choice".
   * So a phone draws no sheet and no row of doors: it draws a card for every text the
   * page can offer — what the sheet would hold, a new instalment, the suggestion, what
   * was read lately and what is followed — each a press to its reader. One text is one
   * card: the text carried on with is also the first recently read, and it is drawn once,
   * under the name that says why it leads. The stylesheet shows these under 40rem and
   * the sheet above it. */
  var LABELS = { recent: RECENTLY_READ };
  function drawCards() {
    var list = document.getElementById("learn-cards");
    if (!list) return;
    list.textContent = "";
    var seen = {};
    sheets
      .concat(
        doors.filter(function (one) {
          return one.reader;
        })
      )
      .forEach(function (one) {
        var door = one.door || { state: "carry" };
        var href = hrefOf(one.reader, door);
        if (seen[href]) return;
        seen[href] = true;
        /* The first card is the lead (design.md §12, 2026-09-19). On a phone there is no
           sheet, and a column of cards "each worth pressing equally" never said which
           one was next: the lead is across the column with the one filled press on the
           page, and its verb on it. At a desk the sheet is the lead and the stylesheet
           leaves this one looking like the rest. */
        list.appendChild(card(one.reader, door, one, !list.children.length));
      });
    list.hidden = !list.children.length;
    // The way to the whole list, which the Recently read menu carries at a desk.
    var all = document.getElementById("learn-cards-all");
    if (all) {
      all.href = keyed("/texts");
      all.hidden = !doors.some(function (one) {
        return one.reader && kind(one) === "recent";
      });
    }
  }

  function card(reader, door, one, lead) {
    var item = el("li", lead ? "learn-card-item is-lead" : "learn-card-item");
    var link = el("a", "learn-card");
    link.href = hrefOf(reader, door);
    link.setAttribute("data-entry", reader.entry || reader.id || "");
    /* Which door this card is, so the rail can say which one the sheet is showing
       (2026-09-18). A card drawn from `sheets` rather than from a door has none. */
    if (one && one.id) link.setAttribute("data-door", one.id);
    /* At a desk the rail took the row of doors' place, so a press has to do what a
       door did: swap the sheet. It stays an `<a href>` to the reader underneath — that
       is what it is on a phone, where there is no sheet to swap, and it is what a
       middle click, a long press and "open in new tab" should still get. So the swap
       is the click handler and the address is the fallback, which is the order that
       degrades the right way rather than the convenient way. */
    if (one && one.reader) {
      link.addEventListener("click", function (event) {
        var sheet = document.getElementById("carry-sheet");
        /* On a phone the stylesheet hides the sheet's column, not the sheet, so
           `hidden` is false there. Checking only `hidden` swapped a sheet nobody could
           see and every card on a phone went nowhere (2026-09-18). No boxes means it
           is not on screen, so the link opens the reader. */
        if (!sheet || sheet.hidden || !sheet.getClientRects().length) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button) return;
        if (event.preventDefault) event.preventDefault();
        drawCarry(one.reader, one.door);
        if (one.id) markDoor(one.id);
      });
    }
    /* At a desk the rail took the row of doors' place, so a press has to do what a
       door did: swap the sheet. It stays an `<a href>` to the reader underneath —
       that is what it is on a phone, where there is no sheet to swap, and it is what
       a middle click, a long press and "open in new tab" should still get. So the
       swap is the click handler and the address is the fallback, which is the order
       that degrades the right way rather than the convenient way. */
    var pictured = reader.entry || reader.id || reader.name;
    var cover = el("span", "card-cover");
    cover.setAttribute("aria-hidden", "true");
    cover.appendChild(
      window.TargumCovers.tile(pictured ? keyed("/thumb/" + encodeURIComponent(pictured)) : "", {
        title: reader.title,
        language: reader.language,
        drawn: pictured ? reader.drawn : false,
      })
    );
    link.appendChild(cover);

    var what = el("span", "learn-card-what");
    var kindOf = one && one.id ? kind(one) : "";
    what.appendChild(
      el("span", "learn-card-state", door.heading || LABELS[kindOf] || stateOf(door, reader))
    );
    var title = el("bdi", "learn-card-title", reader.title);
    title.setAttribute("lang", reader.language || "he");
    what.appendChild(title);
    if (reader.english) {
      var english_ = el("span", "learn-card-english", reader.english);
      english_.setAttribute("lang", "en");
      english_.setAttribute("dir", "ltr");
      what.appendChild(english_);
    }
    var meta = door.meta !== undefined ? door.meta : facts(reader, door);
    if (meta) what.appendChild(el("span", "learn-card-meta", meta));
    var said = share(reader);
    if (said) what.appendChild(el("span", "learn-card-known", said));
    if (lead) {
      what.appendChild(
        el(
          "span",
          "learn-card-go",
          door.state === "carry" ? t("learn.card.continue", "Continue") : BEGIN[mediumOf(reader)]
        )
      );
    }
    link.appendChild(what);

    var done = door.state === "carry" && !door.src ? progress(reader) : 0;
    if (done) {
      var line = el("span", "page-progress");
      line.setAttribute("role", "img");
      line.setAttribute("aria-label", t("learn.read-share", "{share}% through", { share: Math.round(done * 100) }));
      line.style.setProperty("--done", String(done));
      link.appendChild(line);
    }
    item.appendChild(link);
    return item;
  }

  /* The way in, as a door. A link and not a button: it goes somewhere, where the
     reading doors swap the sheet below, and a reader who wants it in another tab should
     be able to have it in another tab. */
  function connectDoor() {
    var way = el("a", "way", t("learn.door.claude-and-chatgpt", "Claude and ChatGPT"));
    way.href = "/connect";
    way.setAttribute("data-door", "connect");
    return way;
  }

  function pill(one) {
    var press = el("button", "way", one.label);
    press.type = "button";
    press.setAttribute("data-door", one.id);
    press.addEventListener("click", function () {
      drawCarry(one.reader, one.door);
    });
    return press;
  }

  // A door with a menu under it: one row per text, a dot on a followed series whose
  // newest instalment this browser has not seen yet, a leaf check on a text read
  // through (§4: green is progress), and at the foot, where the menu has one, the way
  // to the whole list.
  function menu(spec) {
    var host = el("div", "ways-menu-host");
    var press = el("button", "way way-menu", spec.label);
    press.type = "button";
    press.setAttribute("data-door", spec.id);
    press.setAttribute("aria-haspopup", "menu");
    press.setAttribute("aria-expanded", "false");
    var list = el("div", "ways-menu");
    list.setAttribute("role", "menu");
    list.hidden = true;
    spec.items.forEach(function (one) {
      var item = el("button", "ways-item");
      item.type = "button";
      item.setAttribute("role", "menuitem");
      item.setAttribute("data-door", one.id);
      if (one.lang) {
        var name = el("bdi", "ways-name", one.label);
        name.setAttribute("lang", one.lang);
        item.appendChild(name);
      } else {
        item.appendChild(el("span", "ways-name", one.label));
      }
      if (one.when) item.appendChild(el("span", "ways-when", one.when));
      if (one.done) item.appendChild(check());
      if (one.fresh) item.appendChild(el("span", "ways-fresh", ""));
      item.addEventListener("click", function () {
        fold();
        drawCarry(one.reader, one.door);
      });
      list.appendChild(item);
    });
    if (spec.foot) {
      var more = el("a", "ways-link", spec.foot.label);
      more.setAttribute("role", "menuitem");
      more.href = keyed(spec.foot.href);
      list.appendChild(more);
    }
    function fold() {
      list.hidden = true;
      press.setAttribute("aria-expanded", "false");
      if (document.removeEventListener) {
        document.removeEventListener("click", away, true);
        document.removeEventListener("keydown", escape);
      }
    }
    function away(event) {
      if (host.contains && !host.contains(event.target)) fold();
    }
    function escape(event) {
      if (event.key === "Escape") fold();
    }
    press.addEventListener("click", function () {
      if (!list.hidden) return fold();
      list.hidden = false;
      press.setAttribute("aria-expanded", "true");
      document.addEventListener("click", away, true);
      document.addEventListener("keydown", escape);
    });
    host.appendChild(press);
    host.appendChild(list);
    return host;
  }

  // The mark on a text read through: a check in leaf, which on the desk means progress
  // and nothing else (§4, §13). Drawn rather than typed, so it is a glyph and not a
  // character a font may swap for a picture (§7).
  function check() {
    var mark = el("span", "ways-done");
    mark.setAttribute("role", "img");
    mark.setAttribute("aria-label", t("learn.finished-mark", "Finished"));
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M3 8.5l3.2 3.2L13 5");
    svg.appendChild(path);
    mark.appendChild(svg);
    return mark;
  }

  // Read through, as this browser records it: every section of the document finished,
  // or the scene marked finished the way the sequence counts it.
  function isDone(reader) {
    if (!reader || !reader.document) return false;
    if (progress(reader) >= 1) return true;
    return !!(scenes && reader.entry && scenes.finished(reader, stored("targum:docs")));
  }

  // A followed series' current instalment, read through: the document its reader is
  // (the weekly is three, one a level, and any of them read counts), every section.
  function instalmentDone(inst) {
    if (!inst) return false;
    var parts = inst.levels && inst.levels.length ? inst.levels : [inst];
    return parts.some(function (part) {
      return !!part.document && progress({ document: part.document, sections: part.sections || 1 }) >= 1;
    });
  }

  // Recently read (2026-09-11): the reader's own texts opened lately, newest first, as
  // rows of a menu that put each in the sheet; the way to the whole list at its foot.
  function recentDoors(readers) {
    return readers
      .filter(function (reader) {
        return reader.opened > 0;
      })
      .slice(0, RECENT)
      .map(function (reader) {
        return {
          id: "recent:" + reader.name,
          label: reader.title,
          lang: reader.language || "",
          when: ago(reader.opened),
          done: isDone(reader),
          reader: reader,
          door: { id: "recent:" + reader.name, state: "carry", primary: true, register: reader.register },
        };
      });
  }

  var current = "";
  function markDoor(id) {
    current = id;
    var row = document.getElementById("doors");
    if (!row) return;
    var presses = Array.prototype.slice.call(row.querySelectorAll(".way"));
    presses = presses.concat(Array.prototype.slice.call(row.querySelectorAll(".ways-item")));
    presses.forEach(function (press) {
      var mine = press.getAttribute("data-door");
      var on =
        mine === id ||
        (mine === "subscriptions" && id.indexOf("series:") === 0) ||
        (mine === "recent" && id.indexOf("recent:") === 0);
      press.classList.toggle("on", on);
      press.setAttribute("aria-pressed", on ? "true" : "false");
      // The subscriptions door says which one is in the sheet.
      if (mine === "subscriptions") {
        var named = "";
        doors.forEach(function (one) {
          if (one.id === id) named = one.label;
        });
        press.textContent = on && named ? named : SUBSCRIPTIONS;
      }
    });
  }

  // Suggested (2026-09-11): one text that fits the reader's level and interests, from
  // `/suggest`, with no conversation. Framed where it is built already; otherwise the
  // sheet's head says what it is and why, and Open goes to its library row.
  function suggestedDoor(row) {
    if (!row || !row.id) return null;
    var reader = {
      id: row.id,
      entry: row.id,
      title: row.title,
      english: row.english,
      language: row.language || "he",
      minutes: row.minutes,
      register: row.register,
      known: typeof row.known_share === "number" ? row.known_share : undefined,
    };
    var why = row.because || "";
    var door = {
      id: "suggested",
      state: "up",
      heading: t("learn.suggested-for-you", "Suggested for you"),
      register: row.register === "biblical" ? "biblical" : row.register === "modern" ? "modern" : "",
      primary: true,
      meta: row.minutes ? why + " · " + t("learn.minutes", "{n} min", { n: row.minutes }) : why,
    };
    if (row.reader) {
      door.src = row.reader;
      door.href = row.reader;
    } else {
      // targum-internal#313: the door opens the text, not the library.
      door.href = "/open/" + encodeURIComponent(row.id);
    }
    return { id: "suggested", label: t("learn.suggested", "Suggested"), reader: reader, door: door };
  }

  // Your subscriptions as doors: each followed series with a current instalment.
  function seriesDoors(series) {
    var follow = window.TargumFollow;
    if (!follow) return [];
    var out = [];
    var unseen = {};
    follow.fresh(series).forEach(function (one) {
      unseen[one.id] = true;
    });
    series.forEach(function (one) {
      var inst = one.instalment;
      if (!inst || !follow.following(one.id)) return;
      var src = follow.readerOf(one);
      if (!src) return;
      out.push({
        id: "series:" + one.id,
        label: one.name,
        fresh: !!unseen[one.id],
        done: instalmentDone(inst),
        reader: { name: "", title: inst.hebrew || inst.title, english: inst.hebrew ? inst.title : "", language: "he" },
        door: {
          id: "series:" + one.id,
          state: "carry",
          heading: one.name,
          primary: true,
          src: src,
          // Open goes to the reader, never to the series' own page (David, 2026-09-11:
          // "it should open the reader, not their marketing landing pages").
          href: src,
          meta: follow.whenSaid(inst.when),
        },
      });
    });
    return out;
  }

  /* --- a text offered in the conversation ----------------------------------------
   * The conversation in the drawer cannot open a page of its own; it offers the text to
   * this page, which opens it in the sheet — "opened first in the reader on this page,
   * then they can ... go to the dedicated page" (2026-09-11).
   */
  var everything = [];
  function offeredText(path) {
    var name = "";
    try {
      name = decodeURIComponent(String(path).split("/")[0]);
    } catch (e) {
      name = String(path).split("/")[0];
    }
    if (!name) return;
    var found = null;
    everything.forEach(function (reader) {
      if (!found && reader.name === name) found = reader;
    });
    var reader = found || { name: name, title: name, language: "he" };
    // A phone has no sheet to open it in: the reader itself, as any other page does.
    if (phone && phone.matches) {
      window.location.href = keyed("/reader/" + readerPath(reader, { path: path }));
      return;
    }
    drawCarry(reader, {
      id: "offered",
      state: "carry",
      heading: t("learn.from-the-conversation", "From the conversation"),
      primary: true,
      path: path,
      meta: found ? undefined : "",
    });
    var sheet = document.getElementById("carry-sheet");
    if (sheet && typeof sheet.scrollIntoView === "function") {
      var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      sheet.scrollIntoView({ block: "start", behavior: still ? "auto" : "smooth" });
    }
  }
  // The drawer (`talk.js`) hands over what the conversation offers: a text to open in
  // the sheet, or a page of words marked known, after which the count above the sheet
  // is drawn again from the ledger it just changed.
  window.TargumLearn = { open: offeredText, changed: reload };

  /* --- what to read next ------------------------------------------------------
   *
   * The catalogue rides in the page, trimmed to an id, a title and two numbers. The
   * step up is worked out here rather than on the server for the same reason the word
   * counts are: what this reader has already read is in this browser, and the server
   * has no business being told about it to answer a question this size.
   *
   * "Level" is the difficulty of the hardest thing they have built — measured as the
   * share of running words a reader has to look up, so it is a fact about the text
   * rather than a guess about the person. The step up is the easiest thing in the
   * catalogue that is harder than that. It is drawn in the sheet only when there is
   * nothing of this reader's own to carry on with; the suggestion card that stood
   * beside the sheet left this page on 2026-09-11 with the rest of the lobby.
   */

  var catalogue = window.TARGUM_CATALOGUE || [];

  function stepUp(code, readers, register) {
    var built = {};
    readers.forEach(function (reader) {
      if (reader.entry) built[reader.entry] = true;
    });
    var open = catalogue
      .filter(function (entry) {
        // `difficulty >= 0` rather than a truth test. Zero is a measurement, not a
        // missing one: a twenty-word beginner scene has no uncommon word in it, and
        // reading it as "not measured" dropped the seven easiest texts in the library
        // out of the one list a beginner is shown.
        return (
          inLanguage(entry, code) &&
          !built[entry.id] &&
          entry.difficulty >= 0 &&
          (!register || entry.register === register)
        );
      })
      .sort(function (a, b) {
        return a.difficulty - b.difficulty;
      });
    if (!open.length) return null;
    var level = 0;
    readers.forEach(function (reader) {
      if (!inLanguage(reader, code)) return;
      if (register && reader.register !== register) return;
      if (reader.difficulty > level) level = reader.difficulty;
    });
    var pick = null;
    var why = "";
    if (!level) {
      pick = open[0];
      why = t("learn.why.start", "Where most people start");
    } else {
      open.forEach(function (entry) {
        if (!pick && entry.difficulty > level) pick = entry;
      });
      why = pick
        ? t("learn.why.step-up", "A step up from where you are")
        : t("learn.why.about-here", "About where you're reading");
      if (!pick) pick = open[open.length - 1];
    }
    return { pick: pick, why: why, level: level };
  }

  /* One track's door: which text, in which state, with the accent if this is the Hebrew
     the reader opened most recently. `readers` are their own, `shared` the seeded ones.
     The fixed sequence is the numbered scenes for modern Hebrew and the shared Biblical
     texts (Ruth) for the other; a box with no scenes seeded falls back to whatever
     shared modern text it has. */
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
     never shown back: nothing on any page says "you said gimel".

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
      bet: t("learn.level.bet", "Simple conversations"),
      "bet-plus": t("learn.level.bet-plus", "I follow slow Hebrew, with help"),
      gimel: t("learn.level.gimel", "I follow the news, with a dictionary"),
      dalet: t("learn.level.dalet", "I follow most things comfortably"),
      hey: t("learn.level.hey", "I follow almost anything"),
      vav: t("learn.level.vav", "Hebrew is a language I live in"),
    };
  }

  /* Which of the texts a subject can answer to open, given the rung. Sorted by the
     difficulty each row already carries, and the rung says how far along to land: aleph
     takes the easiest of them, vav the hardest, the rest in between. It is a coarse rule
     on purpose — it decides one text, once, and the reader's own marked words decide
     everything after it. No rung, and the order the shelf already has is the order. */
  function pickByRung(rows, rung) {
    if (!rows.length) return null;
    if (!rung) return rows[0];
    var sorted = rows.slice().sort(function (a, b) {
      return (a.difficulty || 0) - (b.difficulty || 0);
    });
    var at = Math.round(charts.seedFraction(rung) * (sorted.length - 1));
    return sorted[at] || sorted[0];
  }

  function interestLabels() {
    return {
      everyday: t("learn.arrival.everyday", "Everyday life in Israel"),
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

  function asksTongue() {
    if (offered().length < 2) return false;
    if (thisVisit()) return true;
    if (held(ASKED_READ) || readsInto()) return false;
    if (pageTongue() !== "en") return false;
    if (who && who.signedIn && who.readsSaid) return false;
    return true;
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

  function firstText(handed, code) {
    var store = charts.collect(charts.meaningLanguage(code))[code];
    var rung = charts.seed(store && store.words, code);
    for (var r = 0; r < arrived.length; r++) {
      var asked = interestOf(arrived[r]);
      if (!asked) continue;
      var theirs = inTheirs(
        handed.filter(function (reader) {
          return wanted(reader, asked);
        })
      );
      if (theirs.length) return pickByRung(voiced(theirs), rung);
    }
    for (var w = 0; w < arrived.length; w++) {
      var came = interestOf(arrived[w]);
      if (!came) continue;
      var rows = handed.filter(function (reader) {
        return wanted(reader, came);
      });
      if (rows.length) return pickByRung(voiced(rows), rung);
    }
    if (rung && !arrived.length) {
      return pickByRung(
        handed.filter(function (reader) {
          return reader.register === "modern";
        }),
        rung
      );
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
    var step = withTongue && thisVisit() ? 1 : 0;
    row.textContent = "";
    rungs.textContent = "";
    if (tongues) tongues.textContent = "";
    if (!withTongue) handOverTongue();

    /* One question a screen (David, 2026-09-19). The step is said in words, in the
       resting colour; Next belongs to the subjects alone, because on the second screen
       pressing a row *is* the answer and a second button would be a second question. */
    function settle() {
      var now = order[step];
      ["tongue", "subjects", "level"].forEach(function (name) {
        if (screenOf[name]) screenOf[name].hidden = name !== now;
      });
      if (where) {
        where.textContent = t("learn.arrival.step", "{n} of {of}")
          .replace("{n}", String(step + 1))
          .replace("{of}", String(order.length));
      }
      done.hidden = now !== "subjects";
      done.disabled = picked.length < WANTED;
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
        finish();
      });
      rungs.appendChild(rung);
    });

    done.onclick = function () {
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

  /* --- words you may already know, on the way in (targum-internal#297) ------- */

  /* The grid is #245's and its home is Your Words. This offers it at the one moment it
   * is worth most: after somebody has opened a text and watched a word land on their
   * list, so they know what a list of words is *for*. Offered before that it is a
   * vocabulary test handed to somebody who has not yet been told why.
   *
   * The reader it matters to is the one who already reads Hebrew. Their ledger starts
   * empty like everybody's, so the shelf is sorted for a beginner and every row reads as
   * out of reach; one page of this moves them to a four-figure count and the library
   * re-sorts under them. For a true beginner there is nothing to claim and the grid
   * reports itself empty, which hides it.
   *
   * Asked once. Answered or waved away, it does not come back — a page that keeps asking
   * a question somebody has declined is a page that is not listening.
   */
  var CLAIMED = "targum:claimed-here";

  function claimDone() {
    try {
      return !!localStorage.getItem(CLAIMED);
    } catch (e) {
      return false;
    }
  }

  function claimOver() {
    try {
      if (window.targumKeep) window.targumKeep(CLAIMED, "done");
      else localStorage.setItem(CLAIMED, "done");
    } catch (e) {
      /* it will be offered once more next visit, which is a smaller fault than never */
    }
  }

  //: Below this many known words the offer is worth making. Past it the reader has a
  //: ledger of their own and the commonest words are already on it.
  var CLAIM_FLOOR = 300;

  function offerClaim(opened, known) {
    var host = document.getElementById("claim-here");
    var body = document.getElementById("claim-here-body");
    var away = document.getElementById("claim-not-now");
    var claim = window.TargumClaim;
    if (!host || !body || !claim || !claim.mount) return;
    if (claimDone() || !opened || known > CLAIM_FLOOR || !claim.hebrew()) {
      host.hidden = true;
      return;
    }
    claim.mount(body, {
      panel: host,
      // One press and it is over: this is an offer on the way in, not the whole grid,
      // which is on Your Words for anybody who wants to keep going.
      once: true,
      onMarked: function () {
        claimOver();
      },
      onEmpty: function () {
        host.hidden = true;
      },
    });
    if (away) {
      away.onclick = function () {
        claimOver();
        host.hidden = true;
      };
    }
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

  /* --- what to work on (targum-internal#103, on Learn 2026-09-18) ---------------
   *
   * The same fold that stands on Your Words, drawn by the same `lists.js` rather than by
   * a second copy of it here: two answers to "what is worth going over" eventually
   * disagree, and the one on Your Words is the one with the tests.
   *
   * `lists.js` draws only what it finds. This page carries the fold's markup and none of
   * the table's, its search field's or its phrases' — so `mount` wires nothing else and
   * `draw` renders nothing else. That is the same arrangement `claim.js` already has
   * here, and the reason neither needed a page of its own.
   *
   * Five, and the way to the rest. The cap is why this can sit on the front door at all:
   * twenty rows of things to go over, above the shelf, is a chore list.
   */
  var WORK_ON_HERE = 5;
  var workList = null;
  //: This load of the page, so a line said once can stay up for the visit it is said on.
  var VISIT = String(Date.now());

  function drawWorkOn(code, store) {
    var panel = document.getElementById("work-on");
    var lists = window.TargumLists;
    if (!panel || !lists || !lists.mount) return;
    if (!workList) {
      lists.mount({ languages: window.TARGUM_LANGUAGES || {} });
      workList = lists;
    }
    lists.draw(code, store || { words: [], phrases: [] }, { workOn: WORK_ON_HERE });
    // The way to the rest is drawn by `lists.js`, since it follows the open tab.
    askSlips();
    sayWhatTheFoldIs(panel);
  }

  /* The third moment (targum-internal#335): "it remembers you". The first time the fold
     has anything in it, a line says what it is. Said on one visit and never again — the
     second time a reader sees their words waiting, they know whose they are. It counts
     nothing and asks for nothing (`test_the_queue_waits_and_never_chases`). */
  var TOLD_FOLD = "targum:taught-the-record";

  function sayWhatTheFoldIs(panel) {
    var line = document.getElementById("work-once");
    if (!line || panel.hidden) return;
    var told = "";
    try {
      told = localStorage.getItem(TOLD_FOLD) || "";
    } catch (e) {
      return;
    }
    // Shown for the whole of the visit it is first shown on, so a redraw does not take it
    // away mid-sentence; the stamp is this page's own, and any other means "already told".
    if (told && told !== VISIT) return;
    line.hidden = false;
    if (!told) keep(TOLD_FOLD, VISIT);
  }


  /* The lines the conversation corrected, for the fold's Phrases tab. Asked once a page
     and after the fold is drawn, so a slow answer never holds up the words; signed out
     there are none, and the refusal is swallowed like an empty list. */
  var slipsAsked = false;

  function askSlips() {
    var lists = window.TargumLists;
    if (slipsAsked || !lists || !lists.rewrote || !window.fetch) return;
    slipsAsked = true;
    fetch(keyed("/slips"), { headers: keyHeaders() })
      .then(function (response) {
        return response.ok ? response.json() : { slips: [] };
      })
      .then(function (data) {
        lists.rewrote((data && data.slips) || []);
      })
      .catch(function () {});
  }

  /* --- what you know --------------------------------------------------------- */

  //: How many known words the count line waits for before it counts (2026-09-11).
  var KNOWN_FLOOR = 10;

  function drawKnown(code, store) {
    var line = document.getElementById("known-line");
    var known = charts.known(store && store.words);
    // A count of a real thing, and nothing when there is nothing: "You know 0 words" is
    // a score of zero, which is the arcade the brand rules keep out.
    // Named, because a reader with Hebrew and Russian has two counts and this line is
    // only ever about the one the switcher is on.
    // A count under ten is true and deflating on the first line a new reader sees
    // (2026-09-11): until then the line says what to do, which is what makes the count.
    line.textContent = known >= KNOWN_FLOOR
      ? tn("learn.known-words", known, "You know {n} {language} words.", "You know {n} {language} words.", {
          language: named(code),
        })
      : t("learn.known-start", "Open something, tap the words you don't know and talk to targum about any line.");
    // The two facts the offer needs, both of them already here: whether they have opened
    // anything, and how few words they have. A reader who already reads Hebrew looks
    // exactly like a beginner at this line, and this is where they get to say otherwise.
    offerClaim(Object.keys(opened).length > 0, known);
  }

  /* --- putting it together --------------------------------------------------- */

  var opened = stored("targum:opened");

  /* Asked beside the shelf and waited for with it (2026-09-20): whether the arrival opens
     on the language depends on what the account has already said, and a question drawn
     and then taken away a moment later is a page moving under the hand. One request, as
     before — `hello` reads this answer rather than asking again. */
  var whoAsked = ask("/account/me").catch(function () {
    return null;
  });

  ask("/readers")
    .then(function (data) {
      return whoAsked.then(function (me) {
        who = me;
        return data;
      });
    })
    .then(function (data) {
      var readers = (data && data.readers) || [];
      var shared = (data && data.shared) || [];
      everything = readers.concat(shared);
      everything.forEach(function (reader) {
        reader.opened = opened[reader.document] || 0;
      });
      // What you had open last, then what was built most recently.
      readers.sort(function (a, b) {
        return b.opened - a.opened || b.built * 1000 - a.built * 1000;
      });

      // `kept()` is a list of {language}, not a map — reading it with Object.keys put a
      // language called "0" in the switcher.
      var vocabulary = kept();
      var codes = [lang.HOME];
      readers.concat(vocabulary).forEach(function (thing) {
        var code = base(thing.language);
        if (code && codes.indexOf(code) < 0) codes.push(code);
      });
      codes = lang.order(codes, names);

      // An empty shelf used to swap the whole page for three lines pointing at the
      // Library. The suggestion — the one thing on this page that says where to start
      // — lives inside the page, so the reader with nothing was the one reader who
      // never saw it. The page draws with its panels empty and the suggestion drawn.
      document.getElementById("nothing").hidden = true;
      document.getElementById("page").hidden = false;

      var chosen = lang.current(codes);

      function show(code) {
        chosen = code;
        sheets = [];
        // Remembered here rather than inside the switcher: the same control now draws
        // two different preferences, and only the caller knows which one it is drawing.
        lang.set(code);
        lang.switcher(document.getElementById("langs"), codes, names, code, show);
        var mine = readers.filter(function (reader) {
          return inLanguage(reader, code);
        });
        var handed = shared.filter(function (reader) {
          return inLanguage(reader, code);
        });
        if (code === lang.HOME) {
          // Hebrew: two tracks, one sheet. The track opened most recently takes it; on
          // a first sign-in modern did, and the Biblical track was on the Library —
          // which was the right default for somebody with no way to say otherwise and
          // the wrong one for the reader who came for the week's portion. Since
          // targum-internal#294 they can say, once, and the answer picks the track
          // until they have opened something of their own.
          var modern = trackDoor(code, "modern", readers, shared);
          var biblical = trackDoor(code, "biblical", readers, shared);
          var door = biblical.reader && biblical.opened > modern.opened ? biblical : modern;
          if (!modern.opened && !biblical.opened) {
            // What they said on arrival picks the door until they have opened something
            // of their own: see `firstText`.
            //
            // Not `wanted` as a variable: that is the predicate above, and a local of
            // the same name shadows it for the whole of `show`, which is how the video
            // door once came to call an object as a function and draw no sheet at all.
            var found = firstText(handed, code);
            if (found) {
              // The track is read off the text rather than off the subject: "judaism"
              // lands on a biblical row and "sport" on a modern one, and the row itself
              // is the only thing that knows which.
              door = { state: "start", reader: found, opened: 0, register: found.register };
            }
          }
          // A text of another register — revival, rabbinic, a novel — belongs to neither
          // track; opened more recently than either track's door, it is what the reader
          // came back for, and the sheet is theirs (2026-09-11).
          var latest = mine[0];
          if (latest && latest.opened > Math.max(modern.opened || 0, biblical.opened || 0)) {
            door = { state: "carry", reader: latest, opened: latest.opened, register: latest.register };
          }
          drawArrival(
            !arrived.length && !modern.opened && !biblical.opened && !arrivalOver,
            readers,
            shared,
            function () {
              arrivalOver = true;
              show(code);
            },
            function () {
              // Straight into the text the answers chose, or the track's own start
              // where they chose nothing the shelf can answer.
              var first = firstText(handed, code);
              var via = first ? { state: "start" } : modern.reader ? modern : biblical;
              var target = first || via.reader;
              if (!target) return false;
              /* Into the text, not onto its contents page. A book's own address is its
                 list of chapters, and a new reader who has just answered two questions
                 was landed on a page with a title, a button and four links — one more
                 press from a line of Hebrew (found by QA, 2026-09-20). The first chapter
                 that is ready is where "Start reading" on that page goes anyway. */
              var opening = (target.chapters || []).filter(function (chapter) {
                return chapter && chapter.ready && chapter.file;
              })[0];
              if (opening && !via.path && !via.href && !via.src) {
                via = { state: via.state, path: target.name + "/reader/" + opening.file };
              }
              window.location.href = hrefOf(target, via);
              return true;
            }
          );
          door.primary = true;
          door.id = "main";
          doors = [{ id: "main", label: stateOf(door, door.reader), reader: door.reader, door: door }].concat(
            recentDoors(mine)
          );
          // Modern first; past the whole modern catalogue, whatever is left in any
          // register, so a reader who has built every modern text is still offered one.
          fallbackPick = stepUp(code, readers.concat(shared), "modern") || stepUp(code, readers.concat(shared), "");
          if (door.reader) {
            drawCarry(door.reader, door);
          } else {
            // Past the scenes: the catalogue's next step, as a link to its library row;
            // and past the catalogue, the Biblical track's own start.
            var up = stepUp(code, readers.concat(shared), "modern");
            if (!up && biblical.reader) {
              biblical.primary = true;
              drawCarry(biblical.reader, biblical);
            } else if (up) {
              drawCarry(
                {
                  id: up.pick.id,
                  entry: up.pick.id,
                  title: up.pick.title,
                  english: up.pick.english,
                  language: up.pick.language,
                  minutes: up.pick.minutes,
                },
                {
                  state: up.level ? "up" : "start",
                  register: "modern",
                  primary: true,
                  href: "/open/" + encodeURIComponent(up.pick.id),
                  meta: up.pick.minutes ? up.why + " · " + t("learn.minutes", "{n} min", { n: up.pick.minutes }) : up.why,
                }
              );
            } else {
              drawCarry(null);
            }
          }
        } else {
          // One track: carry on with your own, or start on what was handed to you.
          var start = !mine.length && handed.length ? handed[0] : null;
          var carrying = mine[0] || start;
          doors = recentDoors(mine);
          drawCarry(carrying, { state: start ? "start" : "carry", primary: !!carrying });
        }
        drawDoors();
        // Meanings in the language this reader last read this one into, for the count.
        var store = charts.collect(charts.meaningLanguage(code))[code];
        drawKnown(code, store);
        drawWorkOn(code, store);
      }

      var waiting = document.getElementById("learn-waiting");
      if (waiting) waiting.hidden = true;
      show(chosen);
      hello();
      suggested();
      landed();
    })
    .catch(function () {
      // Signed out, or the server went away. The page says nothing rather than half of
      // something, and the nav is still there to leave by — and it says what happened,
      // rather than telling a reader with a shelf that they have nothing (2026-09-14).
      var waiting = document.getElementById("learn-waiting");
      if (waiting) waiting.hidden = true;
      var failed = document.getElementById("learn-failed");
      (failed || document.getElementById("nothing")).hidden = false;
    });

  /* --- a subscription that landed (2026-09-11) ------------------------------------
   * A followed series' newest instalment, the first time this browser sees it, takes
   * the sheet as what to read next and is said in the bell; seen once, the sheet goes
   * back to what the reader was reading. The Library is where following is done.
   */
  // Who is reading, and what today is: the account's name where it has one, the
  // date, and the week's portion where this box carries it.
  function hello() {
    var name = window.TargumSync && window.TargumSync.who ? window.TargumSync.who.name : "";
    drawHello(name || "", []);
    whoAsked
      .then(function (me) {
        if (me && me.signedIn && me.name) drawHello(me.name, []);
        // What they answered on arrival, from the account rather than this browser: the
        // question belongs to the person, so somebody who answered it on a phone is not
        // asked again on a laptop. Only ever adopted, never cleared from here — an
        // answer this browser has and the account has not is one that has not reached
        // the server yet (targum-internal#294).
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
        // And the rung, on the same terms: adopted, never cleared from here.
        var rung = (me && me.signedIn && me.declared) || "";
        var held = "";
        try {
          held = localStorage.getItem(charts.DECLARED) || "";
        } catch (e) {
          held = "";
        }
        if (rung && rung !== held) keep(charts.DECLARED, rung);
      })
      .catch(function () {});
  }

  // What this reader has finished, by catalogue id, so it is not suggested again: a
  // finished suggestion makes way for the next one (2026-09-11).
  function finished() {
    var docs = stored("targum:docs");
    var ids = [];
    everything.forEach(function (reader) {
      if (!reader.entry || !docs[reader.document]) return;
      var done = progress(reader) >= 1 || (scenes && scenes.finished(reader, docs));
      if (done && ids.indexOf(reader.entry) < 0) ids.push(reader.entry);
    });
    return ids;
  }

  // The catalogue's own next step, worked out here from what this browser knows, when
  // the server has no pick to give: the door is never simply missing.
  var fallbackPick = null;
  // The language Learn is in: the switcher's (2026-09-13).
  function speaking() {
    var lang = window.TargumLang;
    return lang && lang.learning ? lang.current(lang.learning()) : "he";
  }
  var suggestedIn = "";
  function suggested() {
    suggestedIn = speaking();
    var skip = [];
    try {
      skip = finished();
    } catch (e) {
      skip = [];
    }
    function place(door) {
      doors = doors.filter(function (one) {
        return one.id !== "suggested";
      });
      if (door) doors.splice(doors.length && doors[0].id === "main" ? 1 : 0, 0, door);
      drawDoors();
    }
    function fallback() {
      var up = fallbackPick;
      if (!up || skip.indexOf(up.pick.id) >= 0) return null;
      return suggestedDoor({
        id: up.pick.id,
        title: up.pick.title,
        english: up.pick.english,
        language: up.pick.language,
        minutes: up.pick.minutes,
        register: up.pick.register,
        because: up.why,
      });
    }
    ask(
      "/suggest?language=" +
        encodeURIComponent(suggestedIn) +
        (skip.length ? "&skip=" + encodeURIComponent(skip.join(",")) : "")
    )
      .then(function (got) {
        place(suggestedDoor(got && got.suggestion) || fallback());
      })
      .catch(function () {
        place(fallback());
      });
  }
  // The framed reader writes what it finishes into this browser's storage; the door
  // is asked again so a finished suggestion makes way for the next one.
  window.addEventListener("storage", function (event) {
    if (event && event.key === "targum:docs") suggested();
  });
  // And again in the language the switcher moves to, once the first has been asked.
  window.addEventListener("targum:language", function () {
    if (suggestedIn && speaking() !== suggestedIn) suggested();
  });

  function landed() {
    var follow = window.TargumFollow;
    if (!follow) return;
    follow.list().then(function (series) {
      var today = document.getElementById("today");
      if (today) today.textContent = todayLine(series);
      // The series are Hebrew's: under another language they are not this page's doors.
      if (speaking() !== "he") return;
      doors = doors.concat(seriesDoors(series));
      drawDoors();
      var fresh = follow.fresh(series);
      if (!fresh.length) return;
      fresh.forEach(function (one) {
        var line = one.name + ": " + (one.instalment.hebrew || one.instalment.title);
        if (window.TargumNotices && window.TargumNotices.note) {
          window.TargumNotices.note("series:" + one.id + ":" + one.instalment.id, line, {
            href: keyed(one.page || follow.readerOf(one)),
            label: t("learn.open", "Open"),
          });
        }
      });
      var newest = fresh[0];
      var src = follow.readerOf(newest);
      if (!src) return;
      var inst = newest.instalment;
      drawCarry(
        {
          name: "",
          title: inst.hebrew || inst.title,
          english: inst.hebrew ? inst.title : "",
          language: "he",
        },
        {
          id: "series:" + newest.id,
          state: "carry",
          heading: "New: " + newest.name,
          primary: true,
          src: src,
          href: src,
          // The date once: a title that already carries it ("… · 24 באוגוסט 2026") is not
          // followed by "Aug 24".
          meta: /\d/.test(inst.hebrew || inst.title || "") ? "" : follow.whenSaid(inst.when),
        }
      );
      follow.markSeen(newest.id, inst.id);
      // Seen now, in the sheet: the menu's dot on it goes.
      doors.forEach(function (one) {
        if (one.id === "series:" + newest.id) one.fresh = false;
      });
      drawDoors();
    });
  }

  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (changed) reload();
    });
    // An export comes from the account, so signed out there is nothing to offer and the
    // two buttons stay away rather than handing back a subset of one browser.
    window.TargumSync.start();
  }

})();
