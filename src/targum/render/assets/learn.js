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
    return "You know " + Math.round(reader.known * 100) + "%";
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
  var TRACKS = { modern: "Modern Hebrew", biblical: "Biblical Hebrew" };
  var STATES = { start: "Start here", carry: "Continue reading", next: "Up next", up: "A step up" };

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
      out.push("Scene " + number + (door.total ? " of " + door.total : ""));
      if (door.state === "carry" && typeof reader.fresh === "number" && reader.fresh > 0) {
        out.push(reader.fresh + (reader.fresh === 1 ? " word left" : " words left"));
      } else if (reader.words) {
        out.push(reader.words + " words");
      }
    } else if (reader.chapters && reader.chapters.length > 1) {
      // "4 of 4" is a fraction with nothing left to say; "2 of 4 translated" says what
      // the fraction is a fraction of.
      out.push(
        reader.readyChapters === reader.chapters.length
          ? reader.chapters.length + " chapters"
          : reader.readyChapters + " of " + reader.chapters.length + " translated"
      );
    } else if (reader.sections > 1) {
      out.push(reader.sections + " parts");
    } else if (reader.minutes && door.state !== "carry") {
      out.push(reader.minutes + " min");
    }
    // One word, as on the library's rows: a video can be heard too, and saying both
    // says less than "video" does.
    if (reader.video) out.push("video");
    else if (reader.spoken) out.push("audio");
    if (door.state === "carry" && !number) {
      // How long is left, from what the reader records of the sections finished and
      // the text's own length (2026-09-11): "about 12 min left" says where you are
      // without a word more.
      var left = minutesLeft(reader);
      if (left) out.push(left);
      out.push(reader.opened ? "opened " + ago(reader.opened) : "not opened yet");
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
    if (share >= 1) return "finished";
    var left = Math.max(1, Math.round(reader.minutes * (1 - share)));
    return "about " + left + " min" + (share > 0 ? " left" : "");
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
    var heading = document.getElementById("carry-heading");
    if (heading) heading.textContent = door.heading || STATES[door.state] || "Continue reading";
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
      line.setAttribute("aria-label", Math.round(share_ * 100) + "% read");
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
  var ENGLISH_GREETINGS = ["Good morning", "Good afternoon", "Good evening"];
  function partOfDay() {
    var hour = new Date().getHours();
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
        if (one.id === "parasha" && inst) parts.push("This week: " + (inst.hebrew || inst.title));
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
        menu({ id: "recent", label: "Recently read", items: recent, foot: { label: "All your targums", href: "/texts" } })
      );
    }
    if (series.length) row.appendChild(menu({ id: "subscriptions", label: "Subscriptions", items: series }));
    markDoor(current);
    drawCards();
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
  var LABELS = { recent: "Recently read" };
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
        list.appendChild(card(one.reader, door, one));
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

  function card(reader, door, one) {
    var item = el("li", "learn-card-item");
    var link = el("a", "learn-card");
    link.href = hrefOf(reader, door);
    link.setAttribute("data-entry", reader.entry || reader.id || "");
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
      el("span", "learn-card-state", door.heading || LABELS[kindOf] || STATES[door.state] || "Continue reading")
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
    link.appendChild(what);

    var done = door.state === "carry" && !door.src ? progress(reader) : 0;
    if (done) {
      var line = el("span", "page-progress");
      line.setAttribute("role", "img");
      line.setAttribute("aria-label", Math.round(done * 100) + "% read");
      line.style.setProperty("--done", String(done));
      link.appendChild(line);
    }
    item.appendChild(link);
    return item;
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
    mark.setAttribute("aria-label", "Finished");
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
        press.textContent = on && named ? named : "Subscriptions";
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
      heading: "Suggested for you",
      register: row.register === "biblical" ? "biblical" : row.register === "modern" ? "modern" : "",
      primary: true,
      meta: row.minutes ? why + " · " + row.minutes + " min" : why,
    };
    if (row.reader) {
      door.src = row.reader;
      door.href = row.reader;
    } else {
      door.href = "/library#" + encodeURIComponent(row.id);
    }
    return { id: "suggested", label: "Suggested", reader: reader, door: door };
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
      heading: "From the conversation",
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
      why = "Where most people start";
    } else {
      open.forEach(function (entry) {
        if (!pick && entry.difficulty > level) pick = entry;
      });
      why = pick ? "A step up from what you've read" : "About where you're reading";
      if (!pick) pick = open[open.length - 1];
    }
    return { pick: pick, why: why, level: level };
  }

  /* One track's door: which text, in which state, with the accent if this is the Hebrew
     the reader opened most recently. `readers` are their own, `shared` the seeded ones.
     The fixed sequence is the numbered scenes for modern Hebrew and the shared Biblical
     texts (Ruth) for the other; a box with no scenes seeded falls back to whatever
     shared modern text it has. */
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
      ? "You know " + known + " " + named(code) + " words."
      : "Read, tap the words you don't know and talk to targum about any line.";
  }

  /* --- putting it together --------------------------------------------------- */

  var opened = stored("targum:opened");

  ask("/readers")
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
          // a first sign-in modern does, and the Biblical track is on the Library.
          var modern = trackDoor(code, "modern", readers, shared);
          var biblical = trackDoor(code, "biblical", readers, shared);
          var door = biblical.reader && biblical.opened > modern.opened ? biblical : modern;
          // A text of another register — revival, rabbinic, a novel — belongs to neither
          // track; opened more recently than either track's door, it is what the reader
          // came back for, and the sheet is theirs (2026-09-11).
          var latest = mine[0];
          if (latest && latest.opened > Math.max(modern.opened || 0, biblical.opened || 0)) {
            door = { state: "carry", reader: latest, opened: latest.opened, register: latest.register };
          }
          door.primary = true;
          door.id = "main";
          doors = [{ id: "main", label: STATES[door.state] || "Continue reading", reader: door.reader, door: door }].concat(
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
                  href: "/library#" + encodeURIComponent(up.pick.id),
                  meta: up.pick.minutes ? up.why + " · " + up.pick.minutes + " min" : up.why,
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
    ask("/account/me")
      .then(function (me) {
        if (me && me.signedIn && me.name) drawHello(me.name, []);
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
            label: "Open",
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
