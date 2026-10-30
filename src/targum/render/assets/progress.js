/* Your Progress, as a story in three parts (design.md §12, "Your Progress is a story in
 * three parts", 2026-10-09; its first part is Level since "Your level leads with what you
 * can read", 2026-10-28).
 *
 * Under the totals: Level — the hardest kind of text you can read on your own, the next
 * step, the ladder of the language's own kinds with how many of each you could read now,
 * and one foot line with the measured level — then what you knew of what you read; how
 * you got here — time and words, and the words taken up week by week; and what next — the
 * words you keep meeting and the texts at your level now.
 *
 * The totals and the weeks are read from the browser's own store, the same one the reader
 * writes; the ladder, the level, the words met and the texts at your level from
 * `/account/story`, and time and the reading line from the account's record. Nothing here
 * spends, and nothing in Level is a percentage.
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
    var parts = String(path).split("#");
    var bare = parts[0];
    bare = bare + (bare.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
    return bare + (parts.length > 1 ? "#" + parts.slice(1).join("#") : "");
  }

  var names = window.TARGUM_LANGUAGES || {};
  // The page's words in the reader's language, from `strings.js` (targum-internal#184).
  var words = window.TargumStrings;
  var t = words.t;
  var tn = words.tn;

  /* The rows, each with its name on the ladder and the sentences the card can say
     (design.md §12, "Your level leads with what you can read", 2026-10-28). The rows are
     the texts' own levels, not kinds of text: an easy video and a hard one sit in
     different rows. A sentence each rather than a name dropped into one, so Russian can
     take its case. Aramaic's rows are the Aramaic translations, the climb's own (§12,
     2026-10-25), and have no shelf of their own to open. */
  var RUNGS = {
    A1: {
      name: t("progress.rung.A1", "Beginner · A1"),
      can: t("progress.level.can.A1", "You can read beginner texts on your own."),
      next: t("progress.level.next.A1", "Your next step is beginner texts."),
      start: t("progress.level.start.A1", "Start with beginner texts."),
    },
    A2: {
      name: t("progress.rung.A2", "A2"),
      can: t("progress.level.can.A2", "You can read A2 texts on your own."),
      next: t("progress.level.next.A2", "Your next step is A2 texts."),
      start: t("progress.level.start.A2", "Start with A2 texts."),
    },
    B1: {
      name: t("progress.rung.B1", "B1"),
      can: t("progress.level.can.B1", "You can read B1 texts on your own."),
      next: t("progress.level.next.B1", "Your next step is B1 texts."),
      start: t("progress.level.start.B1", "Start with B1 texts."),
    },
    "B2+": {
      name: t("progress.rung.B2+", "B2 and up"),
      can: t("progress.level.can.B2+", "You can read texts at B2 and up on your own."),
      next: t("progress.level.next.B2+", "Your next step is texts at B2 and up."),
      start: t("progress.level.start.B2+", "Start with texts at B2 and up."),
    },
    /* Native split by the text ruler (design.md §12, "Your level, v3", 2026-10-29). Their
       sentences are B2 and up's, which stay true of each. */
    B2: { name: t("progress.rung.B2", "B2") },
    C1: { name: t("progress.rung.C1", "C1") },
    C2: { name: t("progress.rung.C2", "C2") },
    "past-C2": { name: t("progress.rung.past-C2", "Past C2") },
    "onkelos": {
      name: t("progress.rung.onkelos", "Onkelos"),
      can: t("progress.level.can.onkelos", "You can read Onkelos on your own."),
      next: t("progress.level.next.onkelos", "Your next step is Onkelos."),
      start: t("progress.level.start.onkelos", "Start with Onkelos."),
    },
    "former-prophets": {
      name: t("progress.rung.former-prophets", "Jonathan on Joshua to Kings"),
      can: t("progress.level.can.former-prophets", "You can read Jonathan on Joshua to Kings on your own."),
      next: t("progress.level.next.former-prophets", "Your next step is Jonathan on Joshua to Kings."),
      start: t("progress.level.start.former-prophets", "Start with Jonathan on Joshua to Kings."),
    },
    "jonathan-torah": {
      name: t("progress.rung.jonathan-torah", "Pseudo-Jonathan"),
      can: t("progress.level.can.jonathan-torah", "You can read Pseudo-Jonathan on your own."),
      next: t("progress.level.next.jonathan-torah", "Your next step is Pseudo-Jonathan."),
      start: t("progress.level.start.jonathan-torah", "Start with Pseudo-Jonathan."),
    },
    "latter-prophets": {
      name: t("progress.rung.latter-prophets", "Jonathan on the Prophets"),
      can: t("progress.level.can.latter-prophets", "You can read Jonathan on the Prophets on your own."),
      next: t("progress.level.next.latter-prophets", "Your next step is Jonathan on the Prophets."),
      start: t("progress.level.start.latter-prophets", "Start with Jonathan on the Prophets."),
    },
    "writings": {
      name: t("progress.rung.writings", "The Aramaic of the Writings"),
      can: t("progress.level.can.writings", "You can read the Aramaic of the Writings on your own."),
      next: t("progress.level.next.writings", "Your next step is the Aramaic of the Writings."),
      start: t("progress.level.start.writings", "Start with the Aramaic of the Writings."),
    },
  };

  //: Languages with nobody's voice in them have no listening to count (§12, 2026-10-08).
  var SILENT = { arc: true, yi: true };

  function named(code) {
    return names[code] || (code || "").toUpperCase();
  }

  function wireNav() {
    Array.prototype.forEach.call(document.querySelectorAll(".site-nav a"), function (link) {
      link.href = keyed(link.getAttribute("href"));
    });
  }
  wireNav();

  var charts = window.TargumCharts;
  var el = charts.el;
  var svg = charts.svg;
  var tipFor = charts.tipFor;
  var collect = charts.collect;

  // Anything still in the per-document lists is moved across first, or someone who
  // comes here before opening a text is told they have kept nothing.
  if (window.TargumVocab) window.TargumVocab.migrate();

  var data = collect();
  // Global rather than per-language: a day is not in a language.
  var readingDays = charts.days();
  // Hebrew first, then the rest by name — the same order as the library, so the two
  // pages never disagree about which language you are in.
  var codes = window.TargumLang.order(Object.keys(data), names);

  /* The account never answered, so the record is not known to be empty (errors QA,
     targum-internal#468): the panel home and Your Words draw, with Try again, and offline
     its own line, leaving the press to the bar's banner and asking again once back. */
  function couldNot() {
    var fault = document.getElementById("progress-fault");
    if (!fault) return;
    var offline = typeof navigator !== "undefined" && navigator.onLine === false;
    var retry = function () {
      location.reload();
    };
    if (offline) {
      document.getElementById("progress-fault-lede").textContent = t("progress.offline", "You're offline.");
      document.getElementById("progress-fault-says").textContent = t(
        "progress.offline.says",
        "Your progress opens when you're back online."
      );
      window.addEventListener("online", retry, { once: true });
    }
    var again = document.getElementById("progress-fault-again");
    again.hidden = offline;
    again.onclick = retry;
    document.getElementById("progress-fault-tell").hidden = offline;
    fault.hidden = false;
  }

  // Nothing in this browser yet: the page is drawn once the account has had its say.
  var waiting = !codes.length;
  if (waiting) {
    document.getElementById("library-link").href = keyed("/library");
    wireNav();
    // Signing in on a browser that has nothing is the whole point of signing in: this
    // is the new phone, and everything is about to arrive. So "nothing yet" waits for
    // the account's answer, and is said only if it brought nothing (2026-10-10): said
    // at once, it told somebody just signed in that their whole record was gone.
    //
    // What did arrive is drawn in place by the `onChange` below, which has run by the
    // time this resolves. It reloaded the page until 2026-10-22, so a new phone loaded
    // Progress twice: 2.67 s on the phone profile against §14's 1.5 s (#484).
    if (window.TargumSync && window.TargumSync.settled) {
      window.TargumSync.settled().then(function (changed) {
        if (changed && codes.length) return;
        if (window.TargumSync.reached === false) couldNot();
        else document.getElementById("nothing").hidden = false;
      });
    } else {
      document.getElementById("nothing").hidden = false;
    }
  } else {
    document.getElementById("page").hidden = false;
  }

  // Which language everything below is drawn for. The menu moves it.
  var currentCode = window.TargumLang.current(codes);

  // 1,000 rather than 1000. The counts are the point of the page and they get read.
  function grouped(count) {
    // In the page's language: 11 385 in Russian, 11,385 in English (polish 7, #471).
    var page = (document.documentElement && document.documentElement.lang) || "en";
    try {
      return Number(count).toLocaleString(page);
    } catch (e) {
      return String(count).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }
  }

  /* --- the totals ------------------------------------------------------------
   *
   * Real counts of real things, in the reading face with tabular figures — a ledger
   * rather than a score. Kept from the page before the story (§12, 2026-10-09), less the
   * longest run: the board has no figure about runs of days. Words read joins them where
   * the account keeps a record.
   */
  function drawLedger(host, entry, days, code) {
    host.textContent = "";
    var sums = charts.totals(entry);

    /* `hue` is the one thing this block is allowed that the rest of the page is not:
       §9 makes the inverted surface the only place the bright set is legal, and §4 says
       which is which — leaf for what has been reached, iris for phrases, sun for what
       targum taught. Everything without one stays paper-white. */
    function count(value, label, hue, title, name) {
      // A zero is not a peak moment: §6 keeps what has not happened quiet.
      var box = el("div", "count-" + name + (hue && value ? " lit " + hue : ""));
      box.appendChild(el("b", null, grouped(value)));
      box.appendChild(el("span", null, label));
      if (title) box.title = title;
      host.appendChild(box);
    }

    count(sums.saved, tn("progress.count.saved", sums.saved, "saved word", "saved words"), null, null, "saved");
    // The board's labels (§12, "The mockups win on Your Progress", 2026-10-09).
    count(sums.known, tn("progress.count.known", sums.known, "word known", "words known"), "leaf", null, "known");
    // What targum carried up to known, rather than what a reader arrived already having.
    // No title: a phone and a keyboard never show one, and the label says it (§14.3;
    // targum-internal#471, B1).
    count(
      sums.learned,
      tn("progress.count.learned", sums.learned, "learned on targum", "learned on targum"),
      "sun",
      null,
      "learned"
    );
    count(sums.phrases, tn("progress.count.phrases", sums.phrases, "phrase saved", "phrases saved"), "iris", null, "phrases");
    count(sums.finished, tn("progress.count.finished", sums.finished, "targum finished", "targums finished"), "leaf", null, "finished");
    count(days.length, tn("progress.count.days", days.length, "day on targum", "days on targum"), null, null, "days");
    var read = wordsRead(code);
    if (read !== null) count(read, tn("progress.count.read", read, "word read", "words read"), null, null, "read");
  }

  /* --- Level ----------------------------------------------------------------- */

  var story = {};
  var storyAsked = {};
  var signedIn = null;

  var TICK =
    '<svg class="touch-tick" viewBox="0 0 16 16" aria-hidden="true" focusable="false">' +
    '<path d="M3.5 8.5l3 3 6-7"/></svg>';
  var DOT =
    '<svg class="touch-dot" viewBox="0 0 16 16" aria-hidden="true" focusable="false">' +
    '<circle cx="8" cy="8" r="4.5"/></svg>';
  var RING =
    '<svg class="touch-ring" viewBox="0 0 16 16" aria-hidden="true" focusable="false">' +
    '<circle cx="8" cy="8" r="4.5"/></svg>';

  /* A row's shelf in the Library: the texts at that level you can read now where it
     counts any (`#see/now/level/<level>`, so the row's number is the shelf's), and every
     text at that level where it counts none. */
  function shelfHref(level, readable) {
    return keyed("/library#see/" + (readable ? "now/" : "") + "level/" + encodeURIComponent(level));
  }

  ["B2", "C1", "C2", "past-C2"].forEach(function (kind) {
    RUNGS[kind].can = RUNGS["B2+"].can;
    RUNGS[kind].next = RUNGS["B2+"].next;
    RUNGS[kind].start = RUNGS["B2+"].start;
  });

  function rungOf(rung) {
    return RUNGS[rung.name] || RUNGS[rung.kind] || { name: rung.kind, can: "", next: "", start: "" };
  }

  /* A sentence with one part set as an element: the known count in bold, a Hebrew level
     letter in its own direction. The rest of the sentence stays text. */
  function sentence(host, said, slot, node) {
    var at = said.indexOf(slot);
    if (at < 0) {
      host.appendChild(document.createTextNode(said));
      return;
    }
    if (at) host.appendChild(document.createTextNode(said.slice(0, at)));
    host.appendChild(node);
    var rest = said.slice(at + slot.length);
    if (rest) host.appendChild(document.createTextNode(rest));
  }

  //: A level letter as Hebrew writes it: the geresh after the letter, the plus after that,
  //: in a run of its own direction (ling-he, 2026-10-28).
  function letterRun(letter) {
    var bare = String(letter || "");
    var plus = bare.slice(-1) === "+";
    var run = el("bdi", "level-letter", bare.replace("+", "") + "׳" + (plus ? "+" : ""));
    run.setAttribute("lang", "he");
    run.setAttribute("dir", "rtl");
    return run;
  }

  function ulpanName(name) {
    var id = String(name || "").replace(/ /g, "-");
    return t("charts.ulpan." + id, String(name || ""));
  }

  /* A sentence with several parts set as elements, each standing at its own slot
     character in the translated line, so Russian can put them where it needs them. */
  function sentenceWith(host, said, nodes) {
    var rest = String(said);
    while (rest) {
      var at = -1;
      var slot = "";
      Object.keys(nodes).forEach(function (one) {
        var found = rest.indexOf(one);
        if (found >= 0 && (at < 0 || found < at)) {
          at = found;
          slot = one;
        }
      });
      if (at < 0) {
        host.appendChild(document.createTextNode(rest));
        return;
      }
      if (at) host.appendChild(document.createTextNode(rest.slice(0, at)));
      host.appendChild(nodes[slot]);
      rest = rest.slice(at + slot.length);
    }
  }

  /* The card (design.md §12, "Your level, v3", 2026-10-29): the level and nothing else.
     The ulpan letter leads, "About B2" beside it; a European level leads with itself. A
     bar toward the next rung, then the exact words to it ("637 words to ה׳"), from the
     server's one function, so the C1 row says the same number. At the top rung, no bar
     and no number. Before the first rung (`first`), the bar and the words to it. */
  function drawToward(scale, share, toGo, nextLetter, nextName) {
    var toward = document.getElementById("level-toward");
    var fill = document.getElementById("level-fill");
    var line = document.getElementById("level-togo");
    line.textContent = "";
    toward.hidden = true;
    if (typeof share !== "number" || typeof toGo !== "number" || !nextLetter) return;
    var ulpan = scale === "ulpan";
    var amount = Math.max(0, Math.min(1, share));
    // The bar is not spoken (§12, "See all keeps one level, and the bar is not spoken",
    // 2026-10-29): it is aria-hidden, and the words line under it is heard once, as text.
    fill.style.width = Math.round(amount * 100) + "%";
    var count = el("b", "level-count", grouped(toGo));
    var rung = ulpan ? letterRun(nextLetter) : document.createTextNode(nextName);
    sentenceWith(
      line,
      tn("progress.level.to-go", toGo, "{n} word to {next}", "{n} words to {next}", {
        n: "\u0001",
        next: "\u0000",
      }),
      { "\u0001": count, "\u0000": rung }
    );
    toward.hidden = false;
  }

  function drawMark(level) {
    var mark = document.getElementById("level-mark");
    var spoken = document.getElementById("level-spoken");
    var big = document.getElementById("level-big");
    var cefr = document.getElementById("level-cefr");
    mark.hidden = !level;
    if (!level) return;
    var ulpan = level.scale === "ulpan";
    // The letter alone with its geresh, in its own right-to-left run and hidden from a
    // screen reader, which hears its name instead; a European level is itself.
    big.textContent = ulpan ? letterRun(level.letter).textContent : level.name;
    if (ulpan) {
      big.setAttribute("lang", "he");
      big.setAttribute("dir", "rtl");
      big.setAttribute("aria-hidden", "true");
    } else {
      big.removeAttribute("lang");
      big.removeAttribute("dir");
      big.removeAttribute("aria-hidden");
    }
    spoken.textContent = ulpan
      ? t("progress.level.spoken", "Ulpan level {name},", { name: ulpanName(level.name) })
      : "";
    cefr.textContent = ulpan && level.cefr ? t("progress.level.about", "About {cefr}", { cefr: level.cefr }) : "";
    cefr.hidden = !cefr.textContent;
  }

  function drawWhere(code) {
    var grid = document.getElementById("level-grid");
    var head = document.getElementById("where-title");
    var step = document.getElementById("where-step");
    var knownLine = document.getElementById("where-known");
    var go = document.getElementById("where-go");
    var note = document.getElementById("where-note");
    var ladderCard = document.getElementById("ladder");
    var list = document.getElementById("touchstones");
    list.textContent = "";
    ladderCard.hidden = true;
    step.hidden = true;
    step.textContent = "";
    knownLine.hidden = true;
    knownLine.textContent = "";
    go.hidden = true;
    note.hidden = true;
    note.textContent = "";
    head.textContent = "";
    drawMark(null);
    drawToward(null);
    var said = story[code];

    if (signedIn === false) {
      grid.hidden = false;
      head.textContent = t("progress.level.signed-out", "Sign in to see which texts you can read on your own.");
      return;
    }
    if (!said) {
      grid.hidden = true;
      return;
    }
    grid.hidden = false;
    var ladder = said.ladder || [];
    var level = said.level || null;
    var first = said.first || null;
    // Aramaic's rungs are bodies of Targum, and the Library has no shelf for each, so they
    // are said without a link and without a count to check against a shelf; it has no
    // level of words, so its card says what it says today.
    var shelved = code !== "arc";

    if (level) {
      // The card is the level and nothing else (design.md §12, "Your level, v3").
      drawMark(level);
      if (level.next) drawToward(level.scale, level.toward, level.toGo, level.next.letter, level.next.name);
      go.textContent = t("progress.level.go-now", "Show texts you can read now");
      go.href = keyed("/library#see/now");
      go.hidden = false;
    }
    if (!ladder.length) {
      if (level) return;
      // Yiddish has no library, and a box without the lemma index (or a catalogue whose
      // Aramaic is not measured yet) has measured nothing: each says so, with the one
      // count it does have.
      var known = said.known || 0;
      head.textContent = tn("progress.where.known", known, "You know {n} word so far", "You know {n} words so far", {
        n: grouped(known),
      });
      note.textContent = !said.library
        ? t("progress.where.no-library", "The Library has nothing in this language yet, so we can't show which texts you can read.")
        : t("progress.where.unmeasured", "We'll show which texts you can read on your own once we've measured the Library.");
      note.hidden = false;
      return;
    }

    var here = typeof said.here === "number" ? ladder[said.here] : null;
    var next = typeof said.next === "number" ? ladder[said.next] : null;
    if (level) {
      // Drawn above.
    } else if (shelved && first) {
      // Week one: where to start, the bar and the words to aleph, and the one press,
      // which opens the first beginner conversation (David, 2026-10-29).
      var start = next || ladder[0];
      head.textContent = rungOf(start).start;
      drawToward(first.scale, first.toward, first.toGo, first.letter, first.name);
      if (said.conversations) {
        go.textContent = t("progress.level.start-learning", "Start learning");
        go.href = keyed("/library#see/kind/dialogue");
      } else {
        go.textContent = t("progress.level.go-first", "Show texts at this level");
        go.href = shelfHref(start.kind, 0);
      }
      go.hidden = false;
    } else if (here) {
      // A language with no level of words, Aramaic: the hardest level you can read on
      // your own, the next step, and the one press, as before.
      head.textContent = rungOf(here).can;
      step.textContent = next ? rungOf(next).next : t("progress.level.top", "That's the hardest level in the Library.");
      step.hidden = false;
      go.textContent = t("progress.level.go", "Show texts at your level");
      go.href = keyed("/library#see/now");
      go.hidden = false;
    } else {
      // Week one with no level of words: where to start, the words marked so far.
      var firstRow = next || ladder[0];
      head.textContent = rungOf(firstRow).start;
      if (!shelved) {
        step.textContent = t("progress.level.why-one", "It uses the most common words, so it's the easiest place to begin.");
        step.hidden = false;
      }
      var count = said.known || 0;
      var bold = el("b", "level-count", grouped(count));
      sentence(
        knownLine,
        tn("progress.level.marked", count, "You've marked {n} word as known so far.", "You've marked {n} words as known so far.", {
          n: "\u0000",
        }),
        "\u0000",
        bold
      );
      knownLine.hidden = false;
      if (!shelved) {
        go.textContent = t("progress.level.go-easiest", "Show the easiest texts");
        go.href = keyed("/library#see/now");
      } else if (said.conversations) {
        go.textContent = t("progress.level.start-learning", "Start learning");
        go.href = keyed("/library#see/kind/dialogue");
      } else {
        go.textContent = t("progress.level.go-first", "Show texts at this level");
        go.href = shelfHref(firstRow.kind, 0);
      }
      go.hidden = false;
    }

    ladder.forEach(function (rung) {
      list.appendChild(ladderRow(rung, shelved));
    });
    ladderCard.hidden = false;
  }

  /* One row of Texts by level (design.md §12, "Your level, v3", 2026-10-29). A row the
     reader's words cover says Easy for you or Next, by texts, and how many of its texts
     they can read now. A row above their words says the words to go, exact, and no count.
     Past C2 has no number. A row with no texts is plain text with no chevron. A language
     with no level of words (Aramaic) keeps its climb: Easy for you, Your next step, Not
     yet. */
  function ladderRow(rung, shelved) {
    var item = el("li", "touch");
    var worded = typeof rung.covered === "boolean";
    var state = rung.state;
    // Easy and Next are decided by texts, as before; any other row is ahead, and says the
    // words to go where the reader's words do not reach it.
    var look = state === "easy" || state === "next" ? state : "ahead";
    // A level the reader's words reach with no texts at it to decide by (C2 at the top
    // rung) is reached all the same: the tick, not a hollow ring (qa on #983).
    if (look === "ahead" && worded && rung.covered && !rung.texts) look = "easy";
    var linked = shelved && rung.texts > 0;
    var counted = look !== "ahead" || (worded && rung.covered);
    var readable = shelved && counted && rung.readable > 0 ? rung.readable : 0;
    var row = el(linked ? "a" : "span", "touch-row touch-" + look);
    if (linked) row.href = shelfHref(rung.kind, readable);
    var mark = el("span", "touch-mark");
    mark.innerHTML = look === "easy" ? TICK : look === "next" ? DOT : RING;
    row.appendChild(mark);
    var words = el("span", "touch-words");
    words.appendChild(el("span", "touch-name", rungOf(rung).name));
    var stateSaid = "";
    if (look === "easy") {
      stateSaid = t("progress.ladder.easy", "Easy for you");
    } else if (look === "next") {
      stateSaid = t("progress.ladder.next", "Next");
    } else if (!worded) {
      stateSaid = t("progress.ladder.ahead", "Not yet");
    } else if (!rung.covered && typeof rung.toGo === "number") {
      stateSaid = tn("progress.ladder.to-go", rung.toGo, "{n} word to go", "{n} words to go", {
        n: grouped(rung.toGo),
      });
    }
    words.appendChild(el("span", "touch-state", stateSaid));
    row.appendChild(words);
    row.appendChild(
      el(
        "span",
        "touch-count",
        readable
          ? tn("progress.ladder.readable", readable, "{n} you can read now", "{n} you can read now", {
              n: grouped(readable),
            })
          : ""
      )
    );
    var chevron = el("span", "touch-go", linked ? "›" : "");
    chevron.setAttribute("aria-hidden", "true");
    row.appendChild(chevron);
    if (look === "next") row.setAttribute("aria-current", "step");
    item.appendChild(row);
    return item;
  }

  // Whether the story for a language has answered, and whether its asking failed.
  var storyFailed = {};

  function storyState(code) {
    var wait = document.getElementById("where-wait");
    var failed = document.getElementById("where-failed");
    var answered = signedIn === false || !!story[code];
    if (wait) wait.hidden = answered || !!storyFailed[code];
    if (failed) failed.hidden = answered || !storyFailed[code];
  }

  function askStory(code) {
    if (!window.fetch || storyAsked[code]) return;
    storyAsked[code] = true;
    storyFailed[code] = false;
    storyState(code);
    fetch(keyed("/account/story?language=" + encodeURIComponent(code)), { credentials: "same-origin" })
      .then(function (answer) {
        if (answer.ok === false && answer.status !== 401) throw new Error(String(answer.status));
        return answer.json();
      })
      .then(function (said) {
        if (!said || said.signedIn === false) {
          signedIn = false;
        } else {
          signedIn = true;
          story[code] = said;
        }
        if (code === currentCode) {
          storyState(code);
          drawWhere(code);
          drawNext(code);
        }
      })
      .catch(function () {
        // Said, with Try again, rather than a card holding only its heading.
        storyFailed[code] = true;
        storyAsked[code] = false;
        if (code === currentCode) {
          storyState(code);
          drawNext(code);
        }
      });
  }

  /* --- 2 · how you got here ------------------------------------------------------
   *
   * design.md §12, "How you got here: two figures, the days active and the words of the
   * period" (2026-10-30). Words read and time listening are the account's reading of its
   * own log (targum-internal#339), a row a day, language and medium, so they add up
   * across devices; listening and watching are one figure, with the watched part said
   * under it. Each is set against the period of the same length before. Under them the
   * days active and the period's words — met, saved, become known — which the account
   * counts in the reader's own days. Week | Month | All time narrows all of it.
   */
  var spentRows = null;
  var wordDays = null;
  var spentPeriod = "30";

  function clock(seconds) {
    var minutes = Math.round(seconds / 60);
    if (!seconds) return t("progress.spent.minutes", "{m} min", { m: 0 });
    if (minutes < 1) return t("progress.spent.under-a-minute", "under a minute");
    var hours = Math.floor(minutes / 60);
    var rest = minutes % 60;
    if (!hours) return t("progress.spent.minutes", "{m} min", { m: rest });
    return rest
      ? t("progress.spent.hours-minutes", "{h} h {m} min", { h: hours, m: rest })
      : t("progress.spent.hours", "{h} h", { h: hours });
  }

  function localDay(date) {
    var two = function (n) {
      return (n < 10 ? "0" : "") + n;
    };
    return date.getFullYear() + "-" + two(date.getMonth() + 1) + "-" + two(date.getDate());
  }

  //: The first of the last `days` days, today the last of them, in this browser's days.
  function since(days) {
    var then = new Date();
    then.setDate(then.getDate() - (days - 1));
    return localDay(then);
  }

  //: Whether the account's record holds anything at all in this language.
  function recorded(code) {
    return Boolean(
      spentRows &&
        spentRows.some(function (row) {
          return !row.language || row.language === code;
        })
    );
  }

  //: Every word read in this language, ever, or null where the account keeps no record.
  function wordsRead(code) {
    if (!recorded(code)) return null;
    var sum = 0;
    spentRows.forEach(function (row) {
      if (!row.language || row.language === code) sum += row.words || 0;
    });
    return sum;
  }

  function drawHowTitle(code) {
    var head = document.getElementById("how-title");
    head.textContent =
      code === "arc"
        ? t("progress.how.reading", "Reading")
        : SILENT[code]
          ? t("progress.how.reading-watching", "Reading and watching")
          : t("progress.how.all", "Reading, listening and watching");
  }

  //: Words, seconds listened and seconds watched in this language from `from` up to,
  //: not including, `to`; either end left open by "".
  function spentBetween(code, from, to) {
    var sums = { listened: 0, watched: 0, words: 0 };
    (spentRows || []).forEach(function (row) {
      if (row.language && row.language !== code) return;
      if (from && row.day < from) return;
      if (to && row.day >= to) return;
      sums.listened += row.listened || 0;
      sums.watched += row.watched || 0;
      sums.words += row.words || 0;
    });
    return sums;
  }

  /* Never rounded into a lie, as `level.known_percent` keeps it: a change that is not
     nothing is never 0%, and one that is not exactly a hundred is never 100%. */
  function changePercent(now, before) {
    var exact = (Math.abs(now - before) / before) * 100;
    var whole = Math.round(exact);
    if (whole <= 0) return 1;
    if (whole === 100 && exact !== 100) return exact < 100 ? 99 : 101;
    return whole;
  }

  //: The line under a figure, against the period before; null on All time, or where the
  //: period before holds nothing — no "new" and no "∞".
  function comparison(now, before) {
    if (!spentPeriod || !before) return null;
    var week = spentPeriod === "7";
    var line = el("span", "spent-vs");
    if (now === before) {
      line.textContent = week
        ? t("progress.spent.same-week", "Same as last 7 days")
        : t("progress.spent.same-month", "Same as last 30 days");
      return line;
    }
    var up = now > before;
    line.className += up ? " up" : " down";
    line.appendChild(el("span", "spent-arrow", up ? "▲" : "▼")).setAttribute("aria-hidden", "true");
    line.appendChild(
      el("span", "visually-hidden", up ? t("progress.spent.up", "Up") : t("progress.spent.down", "Down"))
    );
    var n = changePercent(now, before);
    line.appendChild(
      document.createTextNode(
        " " +
          (week
            ? t("progress.spent.vs-week", "{n}% vs. last 7 days", { n: n })
            : t("progress.spent.vs-month", "{n}% vs. last 30 days", { n: n }))
      )
    );
    return line;
  }

  function drawSpent(code) {
    var panel = document.getElementById("spent");
    var figures = document.getElementById("spent-figures");
    if (!panel || !figures) return false;
    // Drawn whenever the record holds anything in this language, and absent where it
    // holds nothing: the board has no waiting state (§12, 2026-10-09).
    panel.hidden = !recorded(code);
    if (panel.hidden) return false;
    var days = Number(spentPeriod);
    var from = spentPeriod ? since(days) : "";
    var sums = spentBetween(code, from, "");
    var before = spentPeriod ? spentBetween(code, since(days * 2), from) : null;
    figures.textContent = "";
    function figure(amount, label, now, then, under) {
      var one = el("div", "spent-figure");
      one.appendChild(el("span", "spent-amount", amount));
      one.appendChild(el("span", "spent-label", label));
      var line = before ? comparison(now, then) : null;
      if (line) one.appendChild(line);
      if (under) one.appendChild(el("span", "spent-under", under));
      figures.appendChild(one);
    }
    // A nought is a figure of the period, not a gap in it.
    figure(
      grouped(sums.words),
      tn("progress.spent.words-read", sums.words, "Word read", "Words read"),
      sums.words,
      before ? before.words : 0
    );
    if (SILENT[code]) {
      // No recordings in this language: what it has is films, so the one figure stays.
      figure(clock(sums.watched), t("progress.spent.watched-label", "Watched"), sums.watched, before ? before.watched : 0);
    } else {
      var heard = sums.listened + sums.watched;
      figure(
        clock(heard),
        t("progress.spent.time-listening", "Time listening"),
        heard,
        before ? before.listened + before.watched : 0,
        sums.watched ? t("progress.spent.of-video", "Including {time} of video", { time: clock(sums.watched) }) : ""
      );
    }
    return true;
  }

  //: Whether this language's record has anything for one day: read, listened or watched.
  function activeDays(code) {
    var out = {};
    (spentRows || []).forEach(function (row) {
      if (row.language && row.language !== code) return;
      if ((row.listened || 0) + (row.watched || 0) + (row.words || 0) > 0) out[row.day] = true;
    });
    return out;
  }

  /* A square a day of the period, leaf where the reader read, listened or watched (David,
     2026-10-30: "active"). One count of days and nothing about runs of them. Not drawn
     on All time: the day strip was retired on 2026-10-09, and a field of ninety squares
     under "All time" would bring it back while describing ninety days, not all of them. */
  function drawDays(code) {
    var box = document.getElementById("how-days");
    if (!box) return false;
    box.hidden = !spentPeriod || !recorded(code);
    if (box.hidden) return false;
    var total = Number(spentPeriod);
    var active = activeDays(code);
    var grid = document.getElementById("days-grid");
    grid.textContent = "";
    var count = 0;
    var first = "";
    var last = "";
    for (var back = total - 1; back >= 0; back--) {
      var date = new Date();
      date.setDate(date.getDate() - back);
      var day = localDay(date);
      if (!first) first = day;
      last = day;
      var on = Boolean(active[day]);
      if (on) count += 1;
      grid.appendChild(el("span", on ? "day on" : "day"));
    }
    var title = document.getElementById("days-title");
    title.textContent = "";
    title.appendChild(document.createTextNode(t("progress.days.title", "Days active")));
    title.appendChild(el("span", "how-count", " " + t("progress.days.of", "· {n} of {all}", { n: count, all: total })));
    grid.setAttribute(
      "aria-label",
      t("progress.days.label", "You were active on {n} of the last {all} days.", { n: count, all: total })
    );
    document.getElementById("days-range").textContent = shortDay(dayOf(first)) + " → " + shortDay(dayOf(last));
    return true;
  }

  /* The period's words: met for the first time, saved, and become known, as exact counts,
     each bar the length of its count against the longest. Met and known are counted from
     the day the account began keeping them (`began`, 2026-10-30), and a period that
     starts before it says so; with no such day those two bars are left out, never drawn
     at nought. */
  function drawWords(code) {
    var box = document.getElementById("how-words");
    if (!box) return false;
    box.hidden = !wordDays;
    if (box.hidden) return false;
    var from = spentPeriod ? since(Number(spentPeriod)) : "";
    var sums = { met: 0, saved: 0, known: 0 };
    (wordDays.days || []).forEach(function (row) {
      if (row.language !== code) return;
      if (from && row.day < from) return;
      sums.met += row.met || 0;
      sums.saved += row.saved || 0;
      sums.known += row.known || 0;
    });
    var began = Number(wordDays.began) || 0;
    var rows = [];
    if (began) rows.push(["met", t("progress.words.met", "New words met"), sums.met, "--step-1"]);
    rows.push(["saved", t("progress.words.saved", "Saved"), sums.saved, "--step-2"]);
    if (began) rows.push(["known", t("progress.words.known", "Now known"), sums.known, "--step-4"]);
    document.getElementById("words-title").textContent =
      spentPeriod === "7"
        ? t("progress.words.week", "Words this week")
        : spentPeriod
          ? t("progress.words.month", "Words this month")
          : t("progress.words.ever", "Words all time");
    var most = rows.reduce(function (top, row) {
      return Math.max(top, row[2]);
    }, 0);
    var bars = document.getElementById("words-bars");
    bars.textContent = "";
    rows.forEach(function (row) {
      var line = el("div", "how-bar how-bar-" + row[0]);
      line.appendChild(el("span", "how-bar-label", row[1]));
      var track = el("span", "how-bar-track");
      track.setAttribute("aria-hidden", "true");
      var fill = el("span", "how-bar-fill");
      fill.style.width = (most ? Math.round((row[2] / most) * 1000) / 10 : 0) + "%";
      fill.style.background = "var(" + row[3] + ")";
      track.appendChild(fill);
      line.appendChild(track);
      line.appendChild(el("span", "how-bar-count", grouped(row[2])));
      bars.appendChild(line);
    });
    var note = document.getElementById("words-since");
    var beganDay = began ? localDay(new Date(began)) : "";
    note.hidden = !beganDay || Boolean(from && from >= beganDay);
    if (!note.hidden) {
      note.textContent = t("progress.words.since", "Words met and known are counted from {date}.", {
        date: shortDay(dayOf(beganDay)),
      });
    }
    return true;
  }

  function drawHow(code) {
    var spent = drawSpent(code);
    var days = drawDays(code);
    var wordsDrawn = drawWords(code);
    var off = document.getElementById("spent-off");
    var by = document.getElementById("how-by");
    if (by) by.hidden = !(spent || wordsDrawn);
    var lower = document.getElementById("how-lower");
    if (lower) {
      lower.hidden = !(days || wordsDrawn);
      lower.classList.toggle("ruled", spent);
    }
    // Nothing to say signed out, and no heading standing over nothing.
    var how = document.getElementById("how");
    if (how) how.hidden = !(spent || wordsDrawn || (off && !off.hidden));
  }

  function wireHowBy() {
    var by = document.getElementById("how-by");
    if (!by) return;
    Array.prototype.forEach.call(by.querySelectorAll("button"), function (button) {
      button.addEventListener("click", function () {
        spentPeriod = button.getAttribute("data-period") || "";
        Array.prototype.forEach.call(by.querySelectorAll("button"), function (other) {
          other.setAttribute("aria-pressed", other === button ? "true" : "false");
        });
        drawHow(currentCode);
      });
    });
  }
  wireHowBy();

  function askSpent() {
    if (!window.fetch) return;
    var zone = readingZone();
    fetch(keyed("/account/totals" + (zone ? "?tz=" + encodeURIComponent(zone) : "")), { credentials: "same-origin" })
      .then(function (answer) {
        return answer.json();
      })
      .then(function (said) {
        if (!said || !said.signedIn) return;
        // The words are the account's own, kept whether or not the record of use is on.
        wordDays = said.words || null;
        if (!said.on) {
          var off = document.getElementById("spent-off");
          if (off) off.hidden = false;
        } else {
          // Read wherever there is a record, kept or not kept any more (§12, 2026-10-09).
          spentRows = said.totals && said.totals.length ? said.totals : null;
        }
        drawHow(currentCode);
        if (spentRows) drawLedger(document.getElementById("counts"), data[currentCode], readingDays, currentCode);
      })
      .catch(function () {
        /* no record to read is no figures, which is how the page already stood */
      });
  }

  /* --- 3 · what next ------------------------------------------------------------ */

  // What next draws a word with its meaning, in the language the reader reads meanings
  // in: `collect()` with no target gathered none, and every row was a bare Hebrew word
  // (targum-internal#471, B3). Gathered once a language, again when the store changes.
  var meant = {};
  function meaningOf(code, lemma) {
    if (!meant[code]) meant[code] = collect(charts.meaningLanguage(code));
    var entry = meant[code][code] || data[code];
    if (!entry) return null;
    for (var n = 0; n < entry.words.length; n++) {
      if (entry.words[n].lemma === lemma) return entry.words[n];
    }
    return null;
  }

  function row(host, main, mainLang, aside, end, href, endLeaf) {
    var item = el("li", "next-row");
    var holder = href ? el("a", "next-link") : el("span", "next-link");
    if (href) holder.href = href;
    var term = el("bdi", "next-term", main);
    if (mainLang) term.setAttribute("lang", mainLang);
    holder.appendChild(term);
    if (aside) {
      var quiet = el("bdi", "next-aside", aside);
      quiet.setAttribute("dir", "auto");
      holder.appendChild(quiet);
    }
    item.appendChild(holder);
    if (end) item.appendChild(el("span", "next-end" + (endLeaf ? " leaf" : ""), end));
    host.appendChild(item);
    return item;
  }

  /* --- 3 · what next: your biggest grammar gap ---------------------------------------
   *
   * design.md §12, "What next leads with your biggest grammar gap" (2026-10-30, board
   * 4B). The account sends `grammar`: a row a binyan, a square a tense, each square the
   * share of the verb tokens met in finished sections whose word is known, or null under
   * the floor; and `gap`, the binyan with the lowest share among those with enough
   * forms, or null. Nothing is worked out here but what to say.
   */

  // Each binyan pointed, its transliteration and what it does, said once each.
  var BINYANIM = {
    paal: {
      he: "פָּעַל",
      name: t("progress.gap.binyan.paal", "pa'al"),
      does: t("progress.gap.does.paal", "Pa'al is the simple, basic pattern most verbs start from."),
    },
    nifal: {
      he: "נִפְעַל",
      name: t("progress.gap.binyan.nifal", "nif'al"),
      does: t("progress.gap.does.nifal", "Nif'al verbs are often passive, or say that something happened to someone."),
    },
    piel: {
      he: "פִּעֵל",
      name: t("progress.gap.binyan.piel", "pi'el"),
      does: t("progress.gap.does.piel", "Pi'el verbs are often active verbs made stronger, or made from a noun."),
    },
    pual: {
      he: "פֻּעַל",
      name: t("progress.gap.binyan.pual", "pu'al"),
      does: t("progress.gap.does.pual", "Pu'al is the passive of pi'el."),
    },
    hifil: {
      he: "הִפְעִיל",
      name: t("progress.gap.binyan.hifil", "hif'il"),
      does: t("progress.gap.does.hifil", "Hif'il verbs are often causative: making something happen."),
    },
    hufal: {
      he: "הֻפְעַל",
      name: t("progress.gap.binyan.hufal", "huf'al"),
      does: t("progress.gap.does.hufal", "Huf'al is the passive of hif'il."),
    },
    hitpael: {
      he: "הִתְפַּעֵל",
      name: t("progress.gap.binyan.hitpael", "hitpa'el"),
      does: t("progress.gap.does.hitpael", "Hitpa'el verbs are often reflexive or mutual."),
    },
  };
  var TENSES = ["past", "present", "future", "imperative", "infinitive"];
  var TENSE_NAMES = {
    past: t("progress.gap.past", "Past"),
    present: t("progress.gap.present", "Present"),
    future: t("progress.gap.future", "Future"),
    imperative: t("progress.gap.imperative", "Imperative"),
    infinitive: t("progress.gap.infinitive", "Infinitive"),
  };

  function hebrew(text, className) {
    var run = el("bdi", className || "", text);
    run.setAttribute("lang", "he");
    run.setAttribute("dir", "rtl");
    return run;
  }

  // A word the reader met, with its meaning where it is on their list: never invented.
  function example(code, lemma) {
    var holder = el("span", "gap-example");
    var word = meaningOf(code, lemma);
    holder.appendChild(hebrew((word && word.term) || lemma));
    var meaning = word ? word.note || word.meaning : "";
    if (meaning) holder.appendChild(document.createTextNode(" " + t("progress.gap.meaning", "“{meaning}”", { meaning: meaning })));
    return holder;
  }

  var openSquare = null;

  function shutWords() {
    var box = document.getElementById("grammar-words");
    if (box) box.hidden = true;
    if (openSquare) openSquare.setAttribute("aria-expanded", "false");
    openSquare = null;
  }

  function showWords(code, button, binyan, tense, cell) {
    if (openSquare === button) {
      shutWords();
      return;
    }
    shutWords();
    var box = document.getElementById("grammar-words");
    var title = document.getElementById("grammar-words-title");
    var list = document.getElementById("grammar-word-rows");
    title.textContent = t("progress.gap.words-title", "{pattern}, {tense}: the words you met", {
      pattern: BINYANIM[binyan].name,
      tense: TENSE_NAMES[tense],
    });
    list.textContent = "";
    (cell.words || []).forEach(function (one) {
      var word = meaningOf(code, one.lemma);
      row(
        list,
        (word && word.term) || one.lemma,
        code,
        word ? word.note || word.meaning : "",
        one.known
          ? t("progress.gap.word-known", "known")
          : tn("progress.gap.word-met", one.count, "met once", "met {n} times"),
        null,
        one.known
      );
    });
    box.hidden = false;
    button.setAttribute("aria-expanded", "true");
    openSquare = button;
  }

  function drawGap(code) {
    var said = story[code];
    var grammar = (said && said.grammar) || null;
    var box = document.getElementById("gap");
    var title = document.getElementById("next-title");
    var lead = document.getElementById("gap-said");
    var rows = document.getElementById("grammar-rows");
    var topics = document.getElementById("gap-topics");
    var halves = document.getElementById("gap-halves");
    if (!box || !title) return;
    shutWords();
    rows.textContent = "";
    lead.textContent = "";
    title.textContent = t("progress.next.title", "The words and texts that would help most");
    var gap = grammar && grammar.gap && BINYANIM[grammar.gap.binyan] ? grammar.gap : null;
    box.hidden = !grammar;
    lead.hidden = !gap;
    if (!grammar) return;

    if (gap) {
      var named = BINYANIM[gap.binyan];
      title.textContent = "";
      sentenceWith(title, t("progress.gap.title", "Your biggest gap: {pattern} verbs"), {
        "{pattern}": hebrew(named.he, "gap-pattern"),
      });
      lead.appendChild(
        document.createTextNode(
          t(
            "progress.gap.said",
            "You know {n}% of the {pattern} forms you meet, against {m}% for the other common patterns.",
            { n: gap.known, m: gap.others, pattern: named.name }
          ) +
            " " +
            named.does
        )
      );
      // Two words of the pattern the reader met, from their own reading; those on their
      // list first, since those can carry a meaning.
      var met = gap.examples || [];
      var mine = met.filter(function (lemma) {
        return !!meaningOf(code, lemma);
      });
      var two = mine.concat(met.filter(function (lemma) { return mine.indexOf(lemma) < 0; })).slice(0, 2);
      if (two.length === 2) {
        lead.appendChild(document.createTextNode(" "));
        sentenceWith(lead, t("progress.gap.examples", "You've met {first} and {second}."), {
          "{first}": example(code, two[0]),
          "{second}": example(code, two[1]),
        });
      } else if (two.length === 1) {
        lead.appendChild(document.createTextNode(" "));
        sentenceWith(lead, t("progress.gap.example", "You've met {first}."), { "{first}": example(code, two[0]) });
      }
    }

    document.getElementById("grammar-floor").textContent = t(
      "progress.gap.floor",
      "A dash means fewer than {n} forms met, too few to say.",
      { n: grammar.cellFloor }
    );

    (grammar.rows || []).forEach(function (line) {
      var named = BINYANIM[line.binyan];
      if (!named) return;
      var tr = el("tr", "grammar-row" + (gap && gap.binyan === line.binyan ? " weakest" : ""));
      var head = el("th", "grammar-binyan");
      head.setAttribute("scope", "row");
      head.appendChild(hebrew(named.he, "grammar-he"));
      head.appendChild(document.createTextNode(" "));
      head.appendChild(el("span", "grammar-name", named.name));
      tr.appendChild(head);
      TENSES.forEach(function (tense) {
        var cell = (line.cells || {})[tense];
        var td = el("td", "grammar-square");
        if (!cell) {
          td.className += " empty";
          td.appendChild(el("span", "", "—"));
          tr.appendChild(td);
          return;
        }
        var square = el("button", "grammar-cell", t("progress.gap.percent", "{n}%", { n: cell.known }));
        square.type = "button";
        square.setAttribute("aria-expanded", "false");
        square.setAttribute("aria-controls", "grammar-words");
        // The fill is leaf mixed into the card in proportion to the share (§12).
        square.style.setProperty("--share", String(cell.known));
        square.addEventListener("click", function () {
          showWords(code, square, line.binyan, tense, cell);
        });
        td.appendChild(square);
        tr.appendChild(td);
      });
      rows.appendChild(tr);
    });

    // Topics: hidden until topic tagging sends something (a card of its own).
    var topicRows = (said && said.topics) || [];
    topics.hidden = !topicRows.length;
    halves.classList.toggle("with-topics", !!topicRows.length);
  }

  function drawNext(code) {
    var said = story[code];
    drawGap(code);
    var met = document.getElementById("met-rows");
    var metEmpty = document.getElementById("met-empty");
    var level = document.getElementById("level-rows");
    var levelEmpty = document.getElementById("level-empty");
    var wordsTitle = document.getElementById("next-words-title");
    var textsTitle = document.getElementById("next-texts-title");
    var more = document.getElementById("more-texts");
    met.textContent = "";
    level.textContent = "";
    metEmpty.hidden = true;
    levelEmpty.hidden = true;
    var practise = document.getElementById("practise");
    practise.href = keyed("/words");

    wordsTitle.textContent =
      code === "arc"
        ? t("progress.next.words-arc", "Words you keep meeting, from your Aramaic list (kept apart from your Hebrew one)")
        : t("progress.next.words", "Words you keep meeting and don't know yet");

    // Nothing is said about what is missing until the account has answered: "None yet"
    // to a reader with six such words was false (targum-internal#471, B2).
    var answered = signedIn === false || !!said;
    var found = (said && said.words) || [];
    var nextWait = t("progress.next.loading", "We're finding the words and texts for you.");
    if (!answered && !storyFailed[code]) {
      metEmpty.textContent = nextWait;
      metEmpty.hidden = false;
    }
    // When the asking failed, each half says so under its heading rather than standing
    // empty; part 1 carries the Try again (targum-internal#522).
    if (!answered && storyFailed[code]) {
      var failedLine = t("progress.story.failed", "We couldn't load this part.");
      metEmpty.textContent = failedLine;
      metEmpty.hidden = false;
      levelEmpty.textContent = failedLine;
      levelEmpty.hidden = false;
    }
    found.forEach(function (one) {
      var word = meaningOf(code, one.lemma);
      row(
        met,
        (word && word.term) || one.lemma,
        code,
        word ? word.note || word.meaning : "",
        tn("progress.next.met", one.texts, "met in {n} text", "met in {n} texts")
      );
    });
    // With none, one quiet line rather than a paragraph (§12, 2026-10-09).
    if (!found.length && answered) {
      metEmpty.textContent =
        signedIn === false
          ? t("progress.next.words-signed-out", "Sign in and we'll find the words you keep meeting.")
          : t("progress.next.words-none", "None yet. They show up as you read.");
      metEmpty.hidden = false;
    }

    // Nothing to practise, no press to practise (polish 3; §12 2026-10-10 left Home's
    // Practise line out in the same case).
    practise.hidden = !found.length;

    // A language with no library offers what the reader brought (board ProgressYi).
    var library = !said || said.library !== false;
    textsTitle.textContent = library
      ? t("progress.next.texts", "Texts at your level now")
      : t("progress.next.texts-yours", "Upload something of your own.");
    more.textContent = library
      ? t("progress.next.library", "More in the Library") + " →"
      : t("progress.next.uploads", "All your uploads") + " →";
    more.href = keyed(library ? "/library" : "/?show=uploads");

    if (!library) {
      var upload = row(level, "+ " + t("progress.next.upload", "Upload something new"), "", t("progress.next.upload-how", "A link, a file, or a photo of a page"), "", keyed("/add"));
      // On a phone its aside goes under the term rather than being cut short (polish 9).
      upload.className += " next-stack";
      ((said && said.uploads) || []).forEach(function (one) {
        row(
          level,
          one.title,
          code,
          t("progress.next.uploaded", "Uploaded by you"),
          t("progress.next.known", "{n}% known", { n: one.known }),
          keyed("/reader/" + encodeURIComponent(one.name) + "/reader/index.html"),
          one.known >= 90
        );
      });
      return;
    }

    var texts = (said && said.texts) || [];
    // Aramaic has a ladder since targum#936, but its texts are placed only once the
    // catalogue's Aramaic rows are measured. Until then there is no ladder and nothing to
    // list, and this half says so, once, and offers the Library (polish 10).
    if (code === "arc" && !texts.length && !(said && said.ladder && said.ladder.length)) {
      if (answered) {
        levelEmpty.textContent = t(
          "progress.next.texts-arc",
          "We'll list Aramaic texts at your level once we've measured the library's Aramaic."
        );
        levelEmpty.hidden = false;
      }
      return;
    }
    // The title alone and how much of it is known, as the board has it.
    texts.forEach(function (one) {
      row(
        level,
        one.title,
        code,
        "",
        t("progress.next.known", "{n}% known", { n: one.known }),
        keyed("/library#" + encodeURIComponent(one.id)),
        true
      );
    });
    if (!texts.length && answered) {
      levelEmpty.textContent =
        signedIn === false
          ? t("progress.next.texts-signed-out", "Sign in and we'll find the texts at your level.")
          : t("progress.next.texts-none", "Nothing is quite at your level yet. The Library's “Hard for now” shelf has the closest.");
      levelEmpty.hidden = false;
    }
  }

  /* --- what you knew of what you read (targum-internal#291) -----------------------
   *
   * One line: of the running words in the sections finished, the share the reader had
   * marked known on the day they finished each one. Measured on the server when a
   * finished section arrives and kept as it was (`reading` rows), so a word marked today
   * does not reach back and lift August — which is what makes this a record and not a
   * second copy of the known count.
   *
   * By Day, Week or Month (design.md §12, "Your level, v3", 2026-10-29): the server sends
   * a bucket a day in the reader's own time zone, and weeks and months are summed here,
   * words and never shares, so a 40-word day does not count as much as a 4,000-word one
   * in its week. The sentence is an exact percentage of the last point and follows the
   * tab. It is the one figure on this page that can fall, and it is allowed to: on Week
   * and Month one sentence says why, harder text and not lost ground, and on Day nothing,
   * or it would be said most mornings. The card is absent until two days have points,
   * and signed out. One tab stop for the line: Left and Right move between points and a
   * polite live region says each one.
   */
  var readingSeries = null;
  var readingMeasurable = 20;
  var readingFailed = false;
  var BY_KEY = "targum.progress.reading-by";
  //: The days a Day view reaches back: thirty at a desk, fourteen on a phone, so the
  //: dots stay tappable (design P1-14).
  var DAYS_DESK = 30;
  var DAYS_PHONE = 14;
  var WEEKS = 12;

  /* Never rounded into a lie, as `level.known_percent` keeps it (targum-internal#560,
     qa on targum#993): a share above none is never 0%, and rounding down never says
     100% of a share under all of it. */
  function percentOf(point) {
    var share = point.known / Math.max(1, point.tokens);
    var percent = Math.max(0, Math.min(100, Math.floor(share * 100)));
    if (share > 0 && percent <= 0) percent = 1;
    return percent;
  }

  function pageLanguage() {
    return words.language || (document.documentElement && document.documentElement.lang) || "en";
  }

  function dayOf(text) {
    var parts = String(text).split("-");
    return new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2] || 15)));
  }

  function isoDay(date) {
    return date.toISOString().slice(0, 10);
  }

  function todayHere() {
    var now = new Date();
    return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  }

  //: The Monday a day's week starts on.
  function weekOf(date) {
    var back = (date.getUTCDay() + 6) % 7;
    return new Date(date.getTime() - back * 86400000);
  }

  function said(date, options) {
    options.timeZone = "UTC";
    try {
      return date.toLocaleDateString(pageLanguage(), options);
    } catch (e) {
      return isoDay(date);
    }
  }

  function monthName(month, withYear) {
    var options = { month: "long" };
    if (withYear) options.year = "numeric";
    return said(dayOf(month + "-15"), options);
  }

  function dayName(date) {
    return said(date, { day: "numeric", month: "long" });
  }

  function shortDay(date) {
    return said(date, { day: "numeric", month: "short" });
  }

  function summed(into, day) {
    into.tokens += Number(day.tokens) || 0;
    into.known += Number(day.known) || 0;
    into.sections += Number(day.sections) || 0;
    return into;
  }

  /* The points a view draws: each with its words, the known ones among them, the sections
     behind it and where it sits on the axis (0 to 1). A point under the measurable words
     is left off, as the server leaves a month off. */
  function viewOf(by, days) {
    var today = todayHere();
    var points = [];
    var labels = [];
    if (by === "month") {
      var months = {};
      days.forEach(function (day) {
        var month = String(day.day).slice(0, 7);
        months[month] = summed(months[month] || { month: month, tokens: 0, known: 0, sections: 0 }, day);
      });
      points = Object.keys(months)
        .sort()
        .map(function (month) {
          return months[month];
        })
        .filter(function (point) {
          return point.tokens >= readingMeasurable;
        });
      points.forEach(function (point, index) {
        point.at = points.length > 1 ? index / (points.length - 1) : 1;
        point.when = monthName(point.month, Number(point.month.slice(0, 4)) !== today.getUTCFullYear());
        point.whenFull = monthName(point.month, true);
      });
      return { points: points, labels: null };
    }
    var phone = window.matchMedia && window.matchMedia("(max-width: 40rem)").matches;
    var span = by === "week" ? WEEKS : phone ? DAYS_PHONE : DAYS_DESK;
    var step = by === "week" ? 7 * 86400000 : 86400000;
    var last = by === "week" ? weekOf(today) : today;
    var firstStart = new Date(last.getTime() - (span - 1) * step);
    var buckets = {};
    days.forEach(function (day) {
      var date = dayOf(day.day);
      var start = by === "week" ? weekOf(date) : date;
      if (start < firstStart || start > last) return;
      var key = isoDay(start);
      buckets[key] = summed(buckets[key] || { start: start, tokens: 0, known: 0, sections: 0 }, day);
    });
    points = Object.keys(buckets)
      .sort()
      .map(function (key) {
        return buckets[key];
      })
      .filter(function (point) {
        return point.tokens >= readingMeasurable;
      });
    points.forEach(function (point) {
      point.at = span > 1 ? Math.round((point.start - firstStart) / step) / (span - 1) : 1;
      point.when =
        by === "week"
          ? t("progress.reading.week-of", "Week of {day}", { day: dayName(point.start) })
          : dayName(point.start);
      point.whenFull = point.when;
      point.isNow = point.start.getTime() === last.getTime();
    });
    labels = [shortDay(firstStart), shortDay(last)];
    return { points: points, labels: labels };
  }

  function sentenceFor(by, point) {
    var share = { p: percentOf(point) };
    if (by === "day") {
      return point.isNow
        ? t("progress.reading.said-today", "Today you knew {p}% of the words you read.", share)
        : t("progress.reading.said-day", "On {day} you knew {p}% of the words you read.", {
            p: share.p,
            day: dayName(point.start),
          });
    }
    if (by === "week") {
      return point.isNow
        ? t("progress.reading.said-this-week", "This week you knew {p}% of the words you read.", share)
        : t("progress.reading.said-week", "In the week of {day} you knew {p}% of the words you read.", {
            p: share.p,
            day: dayName(point.start),
          });
    }
    var now = todayHere();
    var current = point.month === isoDay(now).slice(0, 7);
    return current
      ? t("progress.reading.said-so-far", "So far in {month} you knew {p}% of the words you read.", {
          p: share.p,
          // «С начала октября»: the month as a date says it, which in Russian is the
          // genitive and in English the month's own name.
          month: charts.monthInDate(Number(point.month.slice(5, 7)) - 1, pageLanguage()),
        })
      : t("progress.reading.said-month", "In {month} you knew {p}% of the words you read.", {
          p: share.p,
          month: point.when,
        });
  }

  function chosenBy(days) {
    var remembered = "";
    try {
      remembered = localStorage.getItem(BY_KEY) || "";
    } catch (e) {
      remembered = "";
    }
    if (remembered === "day" || remembered === "week" || remembered === "month") return remembered;
    // The coarsest view with two points (David, 2026-10-29).
    if (viewOf("month", days).points.length >= 2) return "month";
    if (viewOf("week", days).points.length >= 2) return "week";
    return "day";
  }

  var readingBy = "";

  function drawReading(code) {
    var panel = document.getElementById("reading");
    var host = document.getElementById("reading-line");
    var sayHost = document.getElementById("reading-said");
    var failed = document.getElementById("reading-failed");
    var switcher = document.getElementById("reading-by");
    if (!panel || !host || !sayHost) return;
    host.textContent = "";
    sayHost.textContent = "";
    if (failed) failed.hidden = !readingFailed;
    if (readingFailed) {
      // The chart's own fetch failed: said in its place, with Try again, as the part's.
      panel.hidden = signedIn === false;
      if (switcher) switcher.hidden = true;
      return;
    }
    if (!readingSeries) {
      panel.hidden = true;
      return;
    }
    if (switcher) switcher.hidden = false;
    var mine = readingSeries[code] || { days: [] };
    var days = (mine.days || []).filter(function (day) {
      return Number(day.tokens) > 0;
    });
    // Absent until two days have points: no card for a chart that isn't there.
    var measured = days.filter(function (day) {
      return Number(day.tokens) >= readingMeasurable;
    });
    panel.hidden = measured.length < 2;
    if (panel.hidden) return;

    if (!readingBy) readingBy = chosenBy(days);
    panel.setAttribute("data-by", readingBy);
    Array.prototype.forEach.call(switcher ? switcher.querySelectorAll("button") : [], function (button) {
      button.setAttribute("aria-pressed", button.getAttribute("data-by") === readingBy ? "true" : "false");
    });
    var view = viewOf(readingBy, days);
    var points = view.points;

    var W = Math.max(240, Math.round(host.clientWidth || (host.getBoundingClientRect ? host.getBoundingClientRect().width : 0) || 640));
    var H = 120;
    if (points.length < 2) {
      // An empty view is a state, not a disabled button: the 120px stays, and one quiet
      // line says what would draw it.
      var empty = el("div", "chart chart-empty");
      empty.appendChild(
        el(
          "p",
          "reading-empty",
          readingBy === "day"
            ? t("progress.reading.empty-day", "We'll draw this once you've finished sections on two different days.")
            : readingBy === "week"
              ? t("progress.reading.empty-week", "We'll draw this once you've finished sections in two different weeks.")
              : t("progress.reading.empty-month", "We'll draw this once you've finished sections in two different months.")
        )
      );
      host.appendChild(empty);
      return;
    }

    var last = points[points.length - 1];
    // One sentence, the last point's. A fall is drawn and not explained (David,
    // 2026-10-29: the "It fell because…" line is cut in every language).
    sayHost.appendChild(el("p", "reading-said", sentenceFor(readingBy, last)));

    var pad = { top: 12, right: 20, bottom: 22, left: 20 };
    var plotW = W - pad.left - pad.right;
    var plotH = H - pad.top - pad.bottom;
    function share(point) {
      return point.known / Math.max(1, point.tokens);
    }
    function px(point) {
      return pad.left + point.at * plotW;
    }
    function py(value) {
      return pad.top + plotH - value * plotH;
    }
    function spoken(point) {
      return (
        t("progress.reading.point", "{when}: {p}%", { when: point.whenFull, p: percentOf(point) }) +
        " · " +
        tn("progress.reading.sections", point.sections, "{n} section", "{n} sections")
      );
    }

    var wrap = el("div", "chart");
    var picture = svg("svg", {
      viewBox: "0 0 " + W + " " + H,
      width: W,
      height: H,
      role: "img",
      tabindex: "0",
      "aria-label": t("progress.reading.label", "Words you knew, {first} to {last}", {
        first: view.labels ? view.labels[0] : points[0].whenFull,
        last: view.labels ? view.labels[1] : last.whenFull,
      }),
    });
    picture.appendChild(svg("line", { class: "reading-base", x1: 0, y1: H - pad.bottom + 2, x2: W, y2: H - pad.bottom + 2 }));
    var line = points
      .map(function (point, index) {
        return (index ? "L" : "M") + px(point) + " " + py(share(point));
      })
      .join(" ");
    // Leaf, one hue, whichever way it goes: §4 gives progress to leaf, and a fall drawn in
    // clay would be the verdict the sentence under it refuses to give.
    picture.appendChild(svg("path", { class: "reading-path", d: line, fill: "none", stroke: "var(--leaf)", "stroke-width": 3 }));
    var dots = points.map(function (point, index) {
      var dot = svg("circle", {
        class: "reading-point",
        cx: px(point),
        cy: py(share(point)),
        r: index === points.length - 1 ? 5 : 4,
        fill: "var(--leaf)",
      });
      var title = svg("title", {});
      title.textContent = spoken(point);
      dot.appendChild(title);
      picture.appendChild(dot);
      return dot;
    });

    // Month: each name under its dot. Week and Day: the first and the last of the span.
    var axis = svg("g", { class: "axis" });
    function label(text, x, anchor) {
      var name = svg("text", { class: "reading-month", x: x, y: H - 4, "text-anchor": anchor });
      name.textContent = text;
      axis.appendChild(name);
    }
    if (view.labels) {
      label(view.labels[0], pad.left, "start");
      label(view.labels[1], W - pad.right, "end");
    } else {
      points.forEach(function (point, index) {
        label(point.when, px(point), index === 0 ? "start" : index === points.length - 1 ? "end" : "middle");
      });
    }
    picture.appendChild(axis);
    wrap.appendChild(picture);
    host.appendChild(wrap);
    var tip = tipFor(wrap);
    var live = document.getElementById("reading-live");

    var on = -1;
    function point(index, announce) {
      on = Math.max(0, Math.min(points.length - 1, index));
      dots.forEach(function (dot, at) {
        dot.classList.toggle("on", at === on && announce);
      });
      var hostBox = wrap.getBoundingClientRect();
      var words_ = spoken(points[on]);
      tip.show(words_.replace(" · ", "<br>"), (px(points[on]) / W) * hostBox.width, (py(share(points[on])) / H) * hostBox.height);
      if (announce && live) live.textContent = words_;
    }
    function nearest(event) {
      var box = picture.getBoundingClientRect();
      var atX = (event.clientX - box.left) * (W / box.width);
      var best = 0;
      points.forEach(function (one, index) {
        if (Math.abs(px(one) - atX) < Math.abs(px(points[best]) - atX)) best = index;
      });
      point(best, false);
    }
    // A mouse finds the nearest point; a thumb taps for it; a keyboard moves with the
    // arrows from the last point.
    picture.addEventListener("mousemove", nearest);
    picture.addEventListener("click", nearest);
    picture.addEventListener("mouseleave", function () {
      tip.hide();
    });
    picture.addEventListener("focus", function () {
      point(on < 0 ? points.length - 1 : on, true);
    });
    picture.addEventListener("blur", function () {
      tip.hide();
      dots.forEach(function (dot) {
        dot.classList.remove("on");
      });
    });
    picture.addEventListener("keydown", function (event) {
      var key = event.key;
      if (key === "ArrowLeft" || key === "ArrowRight" || key === "Home" || key === "End") {
        event.preventDefault();
        var to = key === "Home" ? 0 : key === "End" ? points.length - 1 : on + (key === "ArrowLeft" ? -1 : 1);
        point(to, true);
      }
    });
  }

  function wireReadingBy() {
    var switcher = document.getElementById("reading-by");
    if (!switcher) return;
    Array.prototype.forEach.call(switcher.querySelectorAll("button"), function (button) {
      button.addEventListener("click", function () {
        readingBy = button.getAttribute("data-by");
        try {
          localStorage.setItem(BY_KEY, readingBy);
        } catch (e) {
          /* remembered for this page only */
        }
        drawReading(currentCode);
      });
    });
    var again = document.getElementById("reading-again");
    if (again) {
      again.addEventListener("click", function () {
        readingFailed = false;
        askReading();
      });
    }
  }
  wireReadingBy();

  function readingZone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (e) {
      return "";
    }
  }

  function askReading() {
    if (!window.fetch) return;
    var zone = readingZone();
    fetch(keyed("/account/reading" + (zone ? "?tz=" + encodeURIComponent(zone) : "")), { credentials: "same-origin" })
      .then(function (answer) {
        if (answer.ok === false && answer.status !== 401) throw new Error(String(answer.status));
        return answer.json();
      })
      .then(function (said) {
        if (!said || !said.signedIn) return;
        readingFailed = false;
        readingSeries = said.reading || {};
        if (typeof said.measurable === "number") readingMeasurable = said.measurable;
        drawReading(currentCode);
      })
      .catch(function () {
        readingFailed = true;
        drawReading(currentCode);
      });
  }

  function show(code) {
    currentCode = code;
    // A language the reader learns and has kept nothing in yet is a page this can be:
    // chosen in the menu, it is drawn empty rather than thrown on.
    if (!data[code]) data[code] = { code: code, words: [], phrases: [], texts: 0, finished: 0 };
    window.TargumLang.set(code);
    window.TargumLang.switcher(document.getElementById("langs"), codes, names, code, show);
    var betaNote = document.getElementById("beta-note");
    if (betaNote) {
      betaNote.hidden = !window.TargumLang.beta(code);
      if (!betaNote.hidden) betaNote.textContent = window.TargumLang.betaNote(code, names);
    }
    drawLedger(document.getElementById("counts"), data[code], readingDays, code);
    drawWhere(code);
    drawReading(code);
    drawHowTitle(code);
    drawHow(code);
    drawNext(code);
    askStory(code);
  }

  var again = document.getElementById("story-again");
  if (again) {
    again.addEventListener("click", function () {
      askStory(currentCode);
    });
  }

  // The account's own figures, asked once the page has a language to draw them in.
  var askedAccount = false;
  function askAccount() {
    if (askedAccount) return;
    askedAccount = true;
    askSpent();
    askReading();
  }

  if (!waiting) {
    show(currentCode);
    askAccount();
  }

  // If the account turns out to hold words this browser had not seen — kept on a phone,
  // or kept here before signing in on another machine — everything is gathered again
  // and the page redrawn, and the story asked again: the ladder moves with the list.
  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (!changed) return;
      data = collect();
      meant = {};
      readingDays = charts.days();
      codes = window.TargumLang.order(Object.keys(data), names);
      document.getElementById("nothing").hidden = codes.length > 0;
      document.getElementById("page").hidden = codes.length === 0;
      if (!codes.length) return;
      if (codes.indexOf(currentCode) < 0) currentCode = window.TargumLang.current(codes);
      storyAsked = {};
      show(currentCode);
      askAccount();
    });
    if (window.TargumSync.settled) window.TargumSync.settled();
    else window.TargumSync.start();
  }

  // The reading line is drawn to a viewBox, but its tooltip is placed in page pixels.
  var redrawing = null;
  window.addEventListener("resize", function () {
    clearTimeout(redrawing);
    redrawing = setTimeout(function () {
      drawReading(currentCode);
    }, 150);
  });
})();
