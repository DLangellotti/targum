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
    drawRoots(code);
  }

  /* "from N roots" under "words known" (design.md §12, '"from N roots" is a label on the
     known-words count', 2026-11-02): a second muted label on that count, never a figure
     of its own. The account's count, so it waits for the story; Hebrew only, and none
     without a root lexicon (`roots` is null) or with no root to say. */
  function drawRoots(code) {
    var tile = document.querySelector("#counts .count-known");
    if (!tile) return;
    var old = tile.querySelector(".count-roots");
    if (old) old.remove();
    var said = story[code];
    var roots = said && typeof said.roots === "number" ? said.roots : 0;
    if (roots < 1) return;
    tile.appendChild(
      el("span", "count-roots", tn("progress.count.roots", roots, "from {n} root", "from {n} roots", { n: grouped(roots) }))
    );
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
  /* French, Russian and Italian say their level once, on this card, as "About A2", and
     the words to the next rung as dictionary words (design.md §12, "Progress leads with
     what you can read", 2026-11-08). */
  var DICTIONARY = { fr: true, ru: true, it: true };

  function drawToward(scale, share, toGo, nextLetter, nextName, dictionary) {
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
    var fill = { n: "\u0001", next: "\u0000" };
    sentenceWith(
      line,
      dictionary
        ? tn(
            "progress.level.to-go-dictionary",
            toGo,
            "{n} more dictionary word to {next}",
            "{n} more dictionary words to {next}",
            fill
          )
        : tn("progress.level.to-go", toGo, "{n} word to {next}", "{n} words to {next}", fill),
      { "\u0001": count, "\u0000": rung }
    );
    toward.hidden = false;
  }

  function drawMark(level, dictionary) {
    var mark = document.getElementById("level-mark");
    var spoken = document.getElementById("level-spoken");
    var big = document.getElementById("level-big");
    var cefr = document.getElementById("level-cefr");
    var scale = document.getElementById("level-scale");
    var basis = document.getElementById("level-basis");
    mark.hidden = !level;
    if (basis) basis.hidden = !level;
    if (!level) return;
    var ulpan = level.scale === "ulpan";
    // Which scale the letter is on, where it can be seen, and under the card how that
    // scale runs (David, 2026-11-03; design.md §12, "The ulpan letter says what it is").
    if (scale) {
      scale.textContent = ulpan ? t("progress.level.ulpan", "Ulpan level") : "";
      scale.hidden = !ulpan;
    }
    if (basis) {
      basis.textContent = ulpan
        ? t("progress.basis.ulpan", "Ulpan classes in Israel run from aleph, for beginners, to vav. A guide, not a placement.")
        : t("progress.basis.cefr", "The European scale runs from A1, for beginners, to C2. A guide, not a placement.");
    }
    // The letter alone with its geresh, in its own right-to-left run and hidden from a
    // screen reader, which hears its name instead; a European level is itself.
    big.textContent = ulpan
      ? letterRun(level.letter).textContent
      : dictionary
        ? t("progress.level.about", "About {cefr}", { cefr: level.name })
        : level.name;
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
    var canRead = document.getElementById("can-read");
    if (canRead) canRead.hidden = true;
    step.hidden = true;
    step.textContent = "";
    step.className = "level-step";
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
    // French, Russian and Italian say what the reader can read in the library in the
    // ladder's place (design.md §12, "Progress leads with what you can read", 2026-11-08).
    var reads = drawCanRead(code, said);

    if (level) {
      // The card is the level and nothing else (design.md §12, "Your level, v3").
      drawMark(level, !!DICTIONARY[code]);
      if (level.next) {
        drawToward(level.scale, level.toward, level.toGo, level.next.letter, level.next.name, !!DICTIONARY[code]);
      }
      // A level the words check gave, until the reader's marks reach a rung, says where
      // it came from (design.md §12, "Your level comes from your words check until your
      // marks reach one", 2026-11-04).
      if (level.from === "check") {
        step.textContent = t("progress.level.from-check", "From your words check");
        step.className = "level-step level-from";
        step.hidden = false;
      }
      go.textContent = t("progress.level.go-now", "Show texts you can read now");
      go.href = keyed("/library#see/now");
      go.hidden = false;
    }
    if (!ladder.length) {
      if (level || reads) return;
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
      drawToward(first.scale, first.toward, first.toGo, first.letter, first.name, !!DICTIONARY[code]);
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

    if (reads) return;
    ladder.forEach(function (rung) {
      list.appendChild(ladderRow(rung, shelved));
    });
    ladderCard.hidden = false;
  }

  /* What you can read in our library (design.md §12, "Progress leads with what you can
     read", 2026-11-08), for French, Russian and Italian: what the level on the card beside
     it counts, then how many of the language's library texts are
     ready (98% of their running words known, the Library's own measure of a text), a
     stretch (95 to 98%) and not yet. The ready row opens Read it now, which holds every
     one of them. Hebrew, and a story the server sent no counts with, keep Texts by level.
     Returns whether it drew. */
  function drawCanRead(code, said) {
    var card = document.getElementById("can-read");
    var counts = said && said.coverage;
    if (!card || !counts || typeof counts !== "object") return false;
    var line = document.getElementById("can-read-line");
    var rows = document.getElementById("can-read-rows");
    rows.textContent = "";
    // The level itself is said once, on the Reading level card ("About A2"); here, what
    // it counts.
    line.textContent = t("progress.read.counted", "Counted in dictionary words, among {language}'s {n} most common.", {
      language: named(code),
      n: grouped(counts.among || 5000),
    });
    line.hidden = false;
    [
      ["ready", t("progress.read.ready", "Ready for you: you know 98% of their words")],
      ["stretch", t("progress.read.stretch", "A stretch: 95 to 98%")],
      ["notYet", t("progress.read.not-yet", "Not yet: under 95%")],
    ].forEach(function (band) {
      var n = Math.max(0, Number(counts[band[0]]) || 0);
      var ready = band[0] === "ready" && n > 0;
      var item = el("li", "touch can-read-" + band[0]);
      var row = el(ready ? "a" : "span", "touch-row " + (ready ? "touch-next" : "touch-ahead"));
      if (ready) row.href = keyed("/library#see/now");
      var mark = el("span", "touch-mark");
      mark.innerHTML = ready ? DOT : RING;
      row.appendChild(mark);
      var words = el("span", "touch-words");
      words.appendChild(el("span", "touch-name", tn("progress.read.texts", n, "{n} text", "{n} texts", { n: grouped(n) })));
      words.appendChild(el("span", "touch-state", band[1]));
      row.appendChild(words);
      var chevron = el("span", "touch-go", ready ? "\u203a" : "");
      chevron.setAttribute("aria-hidden", "true");
      row.appendChild(chevron);
      item.appendChild(row);
      rows.appendChild(item);
    });
    var find = document.getElementById("can-read-find");
    if (find) find.href = keyed("/#read-card");
    card.hidden = false;
    return true;
  }

  // How we measure opens and closes, closed at first, as Home's How we choose does.
  (function () {
    var press = document.getElementById("can-read-how-press");
    var how = document.getElementById("can-read-how");
    if (!press || !how) return;
    press.addEventListener("click", function () {
      var open = press.getAttribute("aria-expanded") !== "true";
      press.setAttribute("aria-expanded", open ? "true" : "false");
      how.hidden = !open;
    });
  })();

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
          drawRoots(code);
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
      // One full stop where a short month brings its own: «с 3 нояб.», never «нояб..»
      // (beta review 2026-11-03, R27).
      note.textContent = t("progress.words.since", "Words met and known are counted from {date}.", {
        date: shortDay(dayOf(beganDay)),
      }).replace(/\.\.$/, ".");
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
  // Each reviewed mishkal's transliteration, what it means (the word card's own line,
  // `reader.card.mishkal.*`, one meaning for both) and what What next says it does. The
  // pointed template comes with the row from the account (`annotate.mishkal`).
  var MISHKALIM = {
    qattal: {
      name: t("progress.gap.mishkal.qattal", "kattal"),
      means: t("reader.card.mishkal.qattal", "often someone whose trade it is"),
      does: t("progress.gap.does-mishkal.qattal", "Kattal words often name a person by their trade."),
    },
    qattelet: {
      name: t("progress.gap.mishkal.qattelet", "kattelet"),
      means: t("reader.card.mishkal.qattelet", "often an illness"),
      does: t("progress.gap.does-mishkal.qattelet", "Kattelet words are often an illness."),
    },
    miqtal: {
      name: t("progress.gap.mishkal.miqtal", "miktal"),
      means: t("reader.card.mishkal.miqtal", "often a place or a thing done"),
      does: t("progress.gap.does-mishkal.miqtal", "Miktal words are often a place or a thing done."),
    },
    miqtala: {
      name: t("progress.gap.mishkal.miqtala", "miktala"),
      means: t("reader.card.mishkal.miqtala", "often a place or an institution"),
      does: t("progress.gap.does-mishkal.miqtala", "Miktala words are often a place or an institution."),
    },
    maqtel: {
      name: t("progress.gap.mishkal.maqtel", "maktel"),
      means: t("reader.card.mishkal.maqtel", "often a tool or a device"),
      does: t("progress.gap.does-mishkal.maqtel", "Maktel words are often a tool or a device."),
    },
    maqtela: {
      name: t("progress.gap.mishkal.maqtela", "maktela"),
      means: t("reader.card.mishkal.maqtela", "often a device"),
      does: t("progress.gap.does-mishkal.maqtela", "Maktela words are often a device."),
    },
    miqtelet: {
      name: t("progress.gap.mishkal.miqtelet", "miktelet"),
      means: t("reader.card.mishkal.miqtelet", "often an object or a tool"),
      does: t("progress.gap.does-mishkal.miqtelet", "Miktelet words are often an object or a tool."),
    },
    maqtelet: {
      name: t("progress.gap.mishkal.maqtelet", "maktelet"),
      means: t("reader.card.mishkal.maqtelet", "often an object or a system"),
      does: t("progress.gap.does-mishkal.maqtelet", "Maktelet words are often an object or a system."),
    },
    qtila: {
      name: t("progress.gap.mishkal.qtila", "ktila"),
      means: t("reader.card.mishkal.qtila", "doing it (a pa'al verb's noun)"),
      does: t("progress.gap.does-mishkal.qtila", "Ktila words name the doing of a pa'al verb."),
    },
    qittul: {
      name: t("progress.gap.mishkal.qittul", "kittul"),
      means: t("reader.card.mishkal.qittul", "doing it (a pi'el verb's noun)"),
      does: t("progress.gap.does-mishkal.qittul", "Kittul words name the doing of a pi'el verb."),
    },
    haqtala: {
      name: t("progress.gap.mishkal.haqtala", "haktala"),
      means: t("reader.card.mishkal.haqtala", "doing it (a hif'il verb's noun)"),
      does: t("progress.gap.does-mishkal.haqtala", "Haktala words name the doing of a hif'il verb."),
    },
    hitqattlut: {
      name: t("progress.gap.mishkal.hitqattlut", "hitkattlut"),
      means: t("reader.card.mishkal.hitqattlut", "doing it (a hitpa'el verb's noun)"),
      does: t("progress.gap.does-mishkal.hitqattlut", "Hitkattlut words name the doing of a hitpa'el verb."),
    },
    hiqqatlut: {
      name: t("progress.gap.mishkal.hiqqatlut", "hikkatlut"),
      means: t("reader.card.mishkal.hiqqatlut", "doing it (a nif'al verb's noun)"),
      does: t("progress.gap.does-mishkal.hiqqatlut", "Hikkatlut words name the doing of a nif'al verb."),
    },
    qatul: {
      name: t("progress.gap.mishkal.qatul", "katul"),
      means: t("reader.card.mishkal.qatul", "had it done to it"),
      does: t("progress.gap.does-mishkal.qatul", "Katul words say something had it done to it, like written or closed."),
    },
    qatil: {
      name: t("progress.gap.mishkal.qatil", "katil"),
      means: t("reader.card.mishkal.qatil", "often -able, in newer words"),
      does: t("progress.gap.does-mishkal.qatil", "In newer words, katil often means -able, like edible or breakable."),
    },
    qatlan: {
      name: t("progress.gap.mishkal.qatlan", "katlan"),
      means: t("reader.card.mishkal.qatlan", "someone who does it a lot, or for a living"),
      does: t("progress.gap.does-mishkal.qatlan", "Katlan words name someone who does it a lot, or for a living."),
    },
    qotel: {
      name: t("progress.gap.mishkal.qotel", "kotel"),
      means: t("reader.card.mishkal.qotel", "the one who does it"),
      does: t("progress.gap.does-mishkal.qotel", "Kotel words name the one who does it."),
    },
    meqattel: {
      name: t("progress.gap.mishkal.meqattel", "mekattel"),
      means: t("reader.card.mishkal.meqattel", "who or what does it"),
      does: t("progress.gap.does-mishkal.meqattel", "Mekattel words name who or what does it."),
    },
    taqtil: {
      name: t("progress.gap.mishkal.taqtil", "taktil"),
      means: t("reader.card.mishkal.taqtil", "often a thing made or done"),
      does: t("progress.gap.does-mishkal.taqtil", "Taktil words are often a thing made or done."),
    },
    qatlut: {
      name: t("progress.gap.mishkal.qatlut", "-ut"),
      means: t("reader.card.mishkal.qatlut", "often a quality or a state"),
      does: t("progress.gap.does-mishkal.qatlut", "Words ending in -ut are often a quality or a state."),
    },
    "suffix-i": {
      name: t("progress.gap.mishkal.suffix-i", "-i"),
      means: t("reader.card.mishkal.suffix-i", "of or from, as an adjective"),
      does: t("progress.gap.does-mishkal.suffix-i", "Words ending in -i are adjectives meaning of or from something."),
    },
    "suffix-ai": {
      name: t("progress.gap.mishkal.suffix-ai", "-ai"),
      means: t("reader.card.mishkal.suffix-ai", "a person who works with it"),
      does: t("progress.gap.does-mishkal.suffix-ai", "Words ending in -ai are often a person who works with something."),
    },
    "suffix-iya": {
      name: t("progress.gap.mishkal.suffix-iya", "-iya"),
      means: t("reader.card.mishkal.suffix-iya", "often a place, or a set or group"),
      does: t("progress.gap.does-mishkal.suffix-iya", "Words ending in -iya are often a place, or a set or group."),
    },
    "suffix-it": {
      name: t("progress.gap.mishkal.suffix-it", "-it"),
      means: t("reader.card.mishkal.suffix-it", "often something smaller, a vehicle or a language"),
      does: t("progress.gap.does-mishkal.suffix-it", "Words ending in -it are often something smaller, a vehicle or a language."),
    },
    "suffix-on": {
      name: t("progress.gap.mishkal.suffix-on", "-on"),
      means: t("reader.card.mishkal.suffix-on", "something small, a periodical, or a place in order"),
      does: t("progress.gap.does-mishkal.suffix-on", "Words ending in -on are often something small, a periodical, or a place in order."),
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

  // One list of words open at a time, under its own table: a square of the Grammar grid
  // or of the Mishkal list. Pressing the open square again shuts it.
  var openSquare = null;
  var openBox = null;

  function shutWords() {
    if (openBox) openBox.hidden = true;
    if (openSquare) openSquare.setAttribute("aria-expanded", "false");
    openSquare = null;
    openBox = null;
  }

  function showWords(code, button, where, title, words) {
    if (openSquare === button) {
      shutWords();
      return;
    }
    shutWords();
    var box = document.getElementById(where + "-words");
    var list = document.getElementById(where + "-word-rows");
    document.getElementById(where + "-words-title").textContent = title;
    list.textContent = "";
    (words || []).forEach(function (one) {
      var word = meaningOf(code, one.lemma);
      // A topic's word to learn next was never counted as met: it says its meaning, the
      // reader's own where it is on their list, else the glossary's, and nothing after.
      row(
        list,
        (word && word.term) || one.lemma,
        code,
        word ? word.note || word.meaning : one.meaning || "",
        one.known
          ? t("progress.gap.word-known", "known")
          : typeof one.count === "number"
            ? tn("progress.gap.word-met", one.count, "met once", "met {n} times")
            : "",
        null,
        one.known
      );
    });
    box.hidden = false;
    button.setAttribute("aria-expanded", "true");
    openSquare = button;
    openBox = box;
  }

  // A square with a figure: a button that opens its words. The fill is leaf mixed into
  // the card in proportion to the share (§12).
  function squareFor(known, where, open) {
    var td = el("td", "grammar-square");
    if (known === null || known === undefined) {
      td.className += " empty";
      td.appendChild(el("span", "", "—"));
      return td;
    }
    var square = el("button", "grammar-cell", t("progress.gap.percent", "{n}%", { n: known }));
    square.type = "button";
    square.setAttribute("aria-expanded", "false");
    square.setAttribute("aria-controls", where + "-words");
    square.style.setProperty("--share", String(known));
    square.addEventListener("click", function () {
      open(square);
    });
    td.appendChild(square);
    return td;
  }

  // Two words of the pattern the reader met, from their own reading; those on their list
  // first, since those can carry a meaning.
  function addExamples(lead, code, met) {
    var mine = (met || []).filter(function (lemma) {
      return !!meaningOf(code, lemma);
    });
    var two = mine.concat((met || []).filter(function (lemma) { return mine.indexOf(lemma) < 0; })).slice(0, 2);
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

  // The Mishkal list (design.md §12, "The Mishkal list beside the Grammar grid",
  // 2026-11-02): a row a pattern, in the reviewed list's order, as the account sends it.
  // Split in two tables of rows from six rows up, so that wherever it has the room it
  // stands as two columns and not one long one; on a phone the two stack as one list.
  function drawMishkal(code, mishkal) {
    var cols = document.getElementById("mishkal-cols");
    cols.textContent = "";
    if (!mishkal) return;
    var rows = (mishkal.rows || []).filter(function (line) {
      return !!MISHKALIM[line.pattern];
    });
    var weakest = mishkal.gap ? mishkal.gap.pattern : null;
    var halves = rows.length >= 6 ? [rows.slice(0, Math.ceil(rows.length / 2)), rows.slice(Math.ceil(rows.length / 2))] : [rows];
    cols.classList.toggle("split", halves.length === 2);
    halves.forEach(function (part) {
      var table = el("table", "mishkal");
      table.setAttribute("aria-labelledby", "grammar-tab-mishkal");
      table.setAttribute("aria-describedby", "mishkal-note mishkal-floor");
      // The square's width is the column's: the spoken-only headers take no room.
      var widths = el("colgroup");
      widths.appendChild(el("col"));
      widths.appendChild(el("col", "mishkal-share"));
      table.appendChild(widths);
      var head = el("thead");
      var headRow = el("tr");
      [t("progress.gap.mishkal-head-pattern", "Pattern"), t("progress.gap.mishkal-head-known", "Known")].forEach(function (name) {
        var th = el("th", "", name);
        th.setAttribute("scope", "col");
        headRow.appendChild(th);
      });
      head.appendChild(headRow);
      table.appendChild(head);
      var body = el("tbody");
      part.forEach(function (line) {
        var named = MISHKALIM[line.pattern];
        var tr = el("tr", "mishkal-row" + (weakest === line.pattern ? " weakest" : ""));
        var th = el("th", "mishkal-pattern");
        th.setAttribute("scope", "row");
        var said = el("span", "mishkal-line");
        said.appendChild(hebrew(line.template, "mishkal-he"));
        said.appendChild(document.createTextNode(" "));
        said.appendChild(el("span", "mishkal-name", named.name));
        said.appendChild(document.createTextNode(" "));
        var means = el("span", "mishkal-means", named.means);
        // Where a wide row cuts the meaning short, the whole of it on hover.
        means.title = named.means;
        said.appendChild(means);
        th.appendChild(said);
        tr.appendChild(th);
        tr.appendChild(
          squareFor(line.known, "mishkal", function (square) {
            showWords(
              code,
              square,
              "mishkal",
              t("progress.gap.mishkal-words-title", "{pattern}: the words you met", { pattern: named.name }),
              line.words
            );
          })
        );
        body.appendChild(tr);
      });
      table.appendChild(body);
      cols.appendChild(table);
    });
    document.getElementById("mishkal-floor").textContent = t(
      "progress.gap.mishkal-floor",
      "A dash means you met these fewer than {n} times, too few to say.",
      { n: mishkal.cellFloor }
    );
  }

  // Under the headline: the gap's sentence, what the pattern does and two words of it the
  // reader met (David, 2026-11-03: they stay with the headline they explain).
  function saySaid(lead, code, sentence, does, examples) {
    lead.appendChild(document.createTextNode(sentence + " " + does));
    addExamples(lead, code, examples);
  }

  // Binyanim | Mishkalim: real tabs in the page's `.seg`. Changing tab shuts an open
  // list of words, since one list is open at a time across the two.
  function showTab(which, focus) {
    var tabs = document.querySelectorAll("#grammar-tabs [role=tab]");
    for (var n = 0; n < tabs.length; n++) {
      var on = tabs[n].getAttribute("data-tab") === which;
      tabs[n].setAttribute("aria-selected", on ? "true" : "false");
      tabs[n].classList.toggle("on", on);
      tabs[n].tabIndex = on ? 0 : -1;
      if (on && focus) tabs[n].focus();
    }
    var grammarPanel = document.getElementById("gap-grammar");
    var mishkalPanel = document.getElementById("gap-mishkal");
    if (grammarPanel) grammarPanel.hidden = which !== "binyan";
    if (mishkalPanel) mishkalPanel.hidden = which !== "mishkal";
  }

  (function wireTabs() {
    var strip = document.getElementById("grammar-tabs");
    if (!strip) return;
    strip.addEventListener("click", function (event) {
      var tab = event.target.closest("[role=tab]");
      if (!tab || tab.getAttribute("aria-selected") === "true") return;
      shutWords();
      showTab(tab.getAttribute("data-tab"), false);
    });
    strip.addEventListener("keydown", function (event) {
      var keys = { ArrowLeft: -1, ArrowRight: 1, Home: "first", End: "last" };
      if (!(event.key in keys)) return;
      var tabs = Array.prototype.slice.call(strip.querySelectorAll("[role=tab]"));
      var at = tabs.indexOf(document.activeElement);
      var step = keys[event.key];
      var rtl = getComputedStyle(strip).direction === "rtl";
      var next =
        step === "first" ? 0 : step === "last" ? tabs.length - 1 : (at + (rtl ? -step : step) + tabs.length) % tabs.length;
      event.preventDefault();
      shutWords();
      showTab(tabs[next].getAttribute("data-tab"), true);
    });
  })();

  function drawGap(code) {
    var said = story[code];
    var grammar = (said && said.grammar) || null;
    var mishkal = (said && said.mishkal) || null;
    var box = document.getElementById("gap");
    var title = document.getElementById("next-title");
    var lead = document.getElementById("gap-said");
    var rows = document.getElementById("grammar-rows");
    if (!box || !title) return;
    shutWords();
    rows.textContent = "";
    lead.textContent = "";
    title.textContent = t("progress.next.title", "The words and texts that would help most");
    // What next names one gap, the one further under the other common patterns of its
    // own kind (`gaps.lead`); an account from before the Mishkal list names the binyan.
    var leads = said && said.lead !== undefined ? said.lead : grammar && grammar.gap ? "binyan" : null;
    var gap = leads === "binyan" && grammar && grammar.gap && BINYANIM[grammar.gap.binyan] ? grammar.gap : null;
    var nouns = leads === "mishkal" && mishkal && mishkal.gap && MISHKALIM[mishkal.gap.pattern] ? mishkal.gap : null;
    // Topics stands on its own where there is no grid: a reader past the floor with no
    // binyan met often enough still sees which topics they know least.
    var topicsSaid = (said && said.topics) || null;
    box.hidden = !grammar && !mishkal && !topicsSaid;
    document.getElementById("grammar-head").hidden = !grammar && !mishkal;
    document.getElementById("gap-grammar").hidden = !grammar;
    document.getElementById("gap-mishkal").hidden = !mishkal;
    lead.hidden = !gap && !nouns;
    drawMishkal(code, mishkal);
    drawTopics(code, topicsSaid);
    if (!grammar && !mishkal) return;
    // One grid at a time, under "Grammar": the tab of the headline's gap open on every
    // load, never a remembered one, and with one kind only, no tabs (David, 2026-11-03).
    var both = !!grammar && !!mishkal;
    document.getElementById("grammar-tabs").hidden = !both;
    showTab(both ? (nouns ? "mishkal" : "binyan") : grammar ? "binyan" : "mishkal", false);

    if (gap) {
      var named = BINYANIM[gap.binyan];
      title.textContent = "";
      sentenceWith(title, t("progress.gap.title", "Your biggest gap: {pattern} verbs"), {
        "{pattern}": hebrew(named.he, "gap-pattern"),
      });
      saySaid(
        lead,
        code,
        t(
          "progress.gap.said",
          "You know {n}% of the {pattern} forms you meet, against {m}% for the other common patterns.",
          { n: gap.known, m: gap.others, pattern: named.name }
        ),
        named.does,
        gap.examples
      );
    } else if (nouns) {
      var pattern = MISHKALIM[nouns.pattern];
      title.textContent = "";
      sentenceWith(title, t("progress.gap.title-mishkal", "Your biggest gap: {pattern} words"), {
        "{pattern}": hebrew(nouns.template, "gap-pattern"),
      });
      saySaid(
        lead,
        code,
        t(
          "progress.gap.said-mishkal",
          "You know {n}% of the {pattern} words you meet, against {m}% for the other common patterns.",
          { n: nouns.known, m: nouns.others, pattern: pattern.name }
        ),
        pattern.does,
        nouns.examples
      );
    }

    if (grammar) {
      document.getElementById("grammar-floor").textContent = t(
        "progress.gap.floor",
        "A dash means fewer than {n} forms met, too few to say.",
        { n: grammar.cellFloor }
      );
      // Each list outlines its own weakest pattern, whichever of the two What next names.
      var weakest = grammar.gap ? grammar.gap.binyan : null;
      (grammar.rows || []).forEach(function (line) {
        var named = BINYANIM[line.binyan];
        if (!named) return;
        var tr = el("tr", "grammar-row" + (weakest === line.binyan ? " weakest" : ""));
        var head = el("th", "grammar-binyan");
        head.setAttribute("scope", "row");
        head.appendChild(hebrew(named.he, "grammar-he"));
        head.appendChild(document.createTextNode(" "));
        head.appendChild(el("span", "grammar-name", named.name));
        tr.appendChild(head);
        TENSES.forEach(function (tense) {
          var cell = (line.cells || {})[tense];
          tr.appendChild(
            squareFor(cell ? cell.known : null, "grammar", function (square) {
              showWords(
                code,
                square,
                "grammar",
                t("progress.gap.words-title", "{pattern}, {tense}: the words you met", {
                  pattern: named.name,
                  tense: TENSE_NAMES[tense],
                }),
                cell.words
              );
            })
          );
        });
        rows.appendChild(tr);
      });
    }
  }

  /* --- 3 · what next: Topics ------------------------------------------------------
   *
   * targum-internal#608, design.md §12, "Topics in What next are weighed by how common a
   * word is" (2026-11-11). The account sends `topics` (`topics.progress`): a row a shown
   * topic with enough words to say anything, its exact share known, the commoner words
   * counting for more, and the commonest it has not seen on the reader's list yet; or
   * no rows under the reader floor, and the page says what to do instead. Nothing at all
   * where the machine has no topic lexicon, and the slot stays hidden.
   */
  var TOPIC_NAMES = {
    everyday: t("find.topic.everyday", "Everyday life"),
    family: t("find.topic.family", "Family & home"),
    people: t("find.topic.people", "People & feelings"),
    food: t("find.topic.food", "Food & drink"),
    money: t("find.topic.money", "Money & shopping"),
    travel: t("find.topic.travel", "Travel & transport"),
    work: t("find.topic.work", "Work & business"),
    school: t("find.topic.school", "School & study"),
    health: t("find.topic.health", "Health & body"),
    culture: t("find.topic.culture", "Free time & culture"),
    nature: t("find.topic.nature", "Nature & weather"),
    politics: t("find.topic.politics", "Politics & government"),
    law: t("find.topic.law", "Law & crime"),
    security: t("find.topic.security", "Security & the army"),
    science: t("find.topic.science", "Science & technology"),
    religion: t("find.topic.religion", "Religion & tradition"),
  };

  function drawTopics(code, said) {
    var holder = document.getElementById("gap-topics");
    var rows = document.getElementById("topic-rows");
    var note = document.getElementById("topics-note");
    if (!holder || !rows) return;
    rows.textContent = "";
    var lines = ((said && said.rows) || []).filter(function (line) {
      return !!TOPIC_NAMES[line.topic];
    });
    holder.hidden = !said;
    if (!said) return;
    rows.hidden = !lines.length;
    if (!lines.length) {
      // Under the reader floor: what to do, never a row of bars at 0%.
      note.textContent = tn(
        "progress.topics.floor",
        said.floor,
        "Once you know {n} word, we'll show how much of each topic you know. Mark the words you know as you read.",
        "Once you know {n} words, we'll show how much of each topic you know. Mark the words you know as you read."
      );
      return;
    }
    note.textContent = t(
      "progress.topics.note",
      "Share of each topic's common words that you know. Commoner words count for more. Tap a topic to see words to learn next."
    );
    lines.forEach(function (line) {
      var name = TOPIC_NAMES[line.topic];
      // With one bar there is nothing to set it against, so no outline (the grid's rule).
      var item = el("li", "topic-row" + (lines.length > 1 && said.weakest === line.topic ? " weakest" : ""));
      var words = line.words || [];
      var bar = el(words.length ? "button" : "div", "topic-bar");
      bar.appendChild(el("span", "topic-name", name));
      var track = el("span", "topic-track");
      track.setAttribute("aria-hidden", "true");
      var fill = el("span", "topic-fill");
      fill.style.inlineSize = Math.max(0, Math.min(100, line.known)) + "%";
      track.appendChild(fill);
      bar.appendChild(track);
      bar.appendChild(el("span", "topic-percent", t("progress.gap.percent", "{n}%", { n: line.known })));
      if (words.length) {
        bar.type = "button";
        bar.setAttribute("aria-expanded", "false");
        bar.setAttribute("aria-controls", "topics-words");
        bar.addEventListener("click", function () {
          showWords(
            code,
            bar,
            "topics",
            t("progress.topics.words-title", "{topic}: words to learn next", { topic: name }),
            words
          );
        });
      }
      item.appendChild(bar);
      rows.appendChild(item);
    });
  }

  /* --- 3 · what next: Russian's Grammar -------------------------------------------
   *
   * design.md §12, "Russian grammar on Your Progress" (2026-11-09, targum-internal#639).
   * The account sends `russian` (`gaps_ru.progress`): the aspect × tense grid and the
   * case × number grid, each with its gap or null; aspect pairs and where and where to,
   * each its tab's companion; and More's three, verbs of motion, nouns in -ь and
   * participles and gerunds. Hebrew's floors, fill, outline and tap, and one list of
   * words open at a time across all of it, Hebrew's own `openSquare`. A row names
   * itself in the reader's language, and in English with the Russian term under it. A
   * square's words are the forms met, beside their dictionary form and meaning.
   */
  function russian(text, className) {
    var run = el("bdi", className || "", text);
    run.setAttribute("lang", "ru");
    return run;
  }

  // The Russian term beside a name, where the page is not already in Russian.
  function showTerms() {
    return pageLanguage().split("-")[0] === "ru" ? false : true;
  }

  // A name in the page's words, with the Russian term under it where the page is not
  // already saying it in Russian.
  function ruName(name, term, className) {
    var holder = el("span", "");
    holder.appendChild(el("span", "grammar-en", name));
    if (term && showTerms()) {
      holder.appendChild(document.createTextNode(" "));
      holder.appendChild(russian(term, className || "grammar-ru"));
    }
    return holder;
  }

  var RU_ASPECTS = [
    { key: "imperfective", name: t("progress.ru.aspect.imperfective", "Imperfective"), term: "несовершенный", short: t("progress.ru.aspect.imperfective-short", "Impf.") },
    { key: "perfective", name: t("progress.ru.aspect.perfective", "Perfective"), term: "совершенный", short: t("progress.ru.aspect.perfective-short", "Pf.") },
  ];
  var RU_CASES = [
    { key: "nom", name: t("progress.ru.case.nom", "Nominative"), term: "именительный" },
    { key: "gen", name: t("progress.ru.case.gen", "Genitive"), term: "родительный" },
    { key: "dat", name: t("progress.ru.case.dat", "Dative"), term: "дательный" },
    { key: "acc", name: t("progress.ru.case.acc", "Accusative, inanimate"), term: "винительный, неодушевлённые" },
    { key: "acca", name: t("progress.ru.case.acca", "Accusative, animate"), term: "винительный, одушевлённые" },
    { key: "ins", name: t("progress.ru.case.ins", "Instrumental"), term: "творительный" },
    { key: "loc", name: t("progress.ru.case.loc", "Prepositional"), term: "предложный" },
  ];
  // What What next says a case does when it is the gap, and its name in the headline.
  var RU_CASE_GAP = {
    nom: {
      name: t("progress.ru.gap-case.nom", "the nominative"),
      does: t("progress.ru.does-case.nom", "The nominative names who or what does the action, and it is the form in the dictionary."),
    },
    gen: {
      name: t("progress.ru.gap-case.gen", "the genitive"),
      does: t("progress.ru.does-case.gen", "The genitive says whose and of what, and follows numbers, {a} and many prepositions."),
      fill: ["нет"],
    },
    dat: {
      name: t("progress.ru.gap-case.dat", "the dative"),
      does: t("progress.ru.does-case.dat", "The dative names who something is given or said to."),
    },
    acc: {
      name: t("progress.ru.gap-case.acc", "the inanimate accusative"),
      does: t("progress.ru.does-case.acc", "The accusative names what the action is done to, and says where to after {a} and {b}."),
      fill: ["в", "на"],
    },
    acca: {
      name: t("progress.ru.gap-case.acca", "the animate accusative"),
      does: t("progress.ru.does-case.acca", "For a person or an animal the accusative takes the genitive’s ending, {f}."),
    },
    ins: {
      name: t("progress.ru.gap-case.ins", "the instrumental"),
      does: t("progress.ru.does-case.ins", "The instrumental says with what or with whom, and says where after {a} and {b}."),
      fill: ["за", "под"],
    },
    loc: {
      name: t("progress.ru.gap-case.loc", "the prepositional"),
      does: t("progress.ru.does-case.loc", "The prepositional says where after {a} and {b}, and what about after {c}."),
      fill: ["в", "на", "о"],
    },
  };
  var RU_NUMBERS = [
    { key: "sing", name: t("progress.ru.sing", "Singular"), short: t("progress.ru.sing-short", "Sing.") },
    { key: "plur", name: t("progress.ru.plur", "Plural"), short: t("progress.ru.plur-short", "Plur.") },
  ];
  var RU_TENSES = TENSES.map(function (tense) {
    return {
      key: tense,
      name: TENSE_NAMES[tense],
      short: t("progress.gap." + tense + "-short", { past: "Past", present: "Pres.", future: "Fut.", imperative: "Imp.", infinitive: "Inf." }[tense]),
    };
  });
  var RU_PREPOSITIONS = [
    { key: "v", term: "в", gloss: t("progress.ru.prep.v", "in") },
    { key: "na", term: "на", gloss: t("progress.ru.prep.na", "on, at") },
    { key: "za", term: "за", gloss: t("progress.ru.prep.za", "behind") },
    { key: "pod", term: "под", gloss: t("progress.ru.prep.pod", "under") },
  ];
  var RU_PLACES = [
    { key: "where", name: t("progress.ru.where", "Where"), term: "где?", short: t("progress.ru.where-short", "Where") },
    { key: "whereto", name: t("progress.ru.whereto", "Where to"), term: "куда?", short: t("progress.ru.whereto-short", "To") },
  ];
  var RU_WAYS = [
    { key: "one", name: t("progress.ru.one-way", "One way"), short: t("progress.ru.one-way-short", "One way") },
    { key: "back", name: t("progress.ru.there-and-back", "There and back"), short: t("progress.ru.there-and-back-short", "And back") },
  ];
  var RU_GENDERS = [
    { key: "fem", name: t("progress.ru.soft.fem", "Feminine") },
    { key: "masc", name: t("progress.ru.soft.masc", "Masculine") },
  ];
  var RU_FORMS = [
    { key: "partact", name: t("progress.ru.form.partact", "Participle, active"), term: "действительное причастие", example: "читающий, прочитавший" },
    { key: "partpass", name: t("progress.ru.form.partpass", "Participle, passive"), term: "страдательное причастие", example: "читаемый, прочитанный" },
    { key: "short", name: t("progress.ru.form.short", "Short participle"), term: "краткое причастие", example: "прочитан, сделано" },
    { key: "gerund", name: t("progress.ru.form.gerund", "Gerund"), term: "деепричастие", example: "читая, прочитав" },
  ];
  var RU_TITLES = {
    pairs: { name: t("progress.ru.pairs-title", "Aspect pairs"), term: "видовые пары" },
    place: { name: t("progress.ru.place-title", "Where and where to"), term: "где и куда" },
    motion: { name: t("progress.ru.motion-title", "Verbs of motion"), term: "глаголы движения" },
    soft: { name: t("progress.ru.soft-title", "Nouns in -ь"), term: "существительные на -ь" },
    forms: { name: t("progress.ru.forms-title", "Participles and gerunds"), term: "причастия и деепричастия" },
  };

  // A word's meaning: the reader's own where it is on their list, else the glossary's
  // the account sent; never invented.
  function ruMeaning(code, one) {
    var word = meaningOf(code, one.lemma);
    return (word && (word.note || word.meaning)) || one.meaning || "";
  }

  // The words under a square: each form met, its dictionary form where that differs,
  // and its meaning; "known" in leaf, or how often it was met.
  function showRuWords(code, button, where, title, words) {
    if (openSquare === button) {
      shutWords();
      return;
    }
    shutWords();
    var box = document.getElementById(where + "-words");
    var list = document.getElementById(where + "-word-rows");
    if (!box || !list) return;
    document.getElementById(where + "-words-title").textContent = title;
    list.textContent = "";
    (words || []).forEach(function (one) {
      var meaning = ruMeaning(code, one);
      var form = one.form || one.lemma;
      var same = form === one.lemma;
      var said = meaning ? t("progress.gap.meaning", "“{meaning}”", { meaning: meaning }) : "";
      var aside = same ? said : one.lemma + (said ? " " + said : "");
      row(
        list,
        form,
        "ru",
        aside,
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
    openBox = box;
  }

  function wordsBox(where) {
    var box = el("div", "grammar-words");
    box.id = where + "-words";
    box.hidden = true;
    var title = el("h4", "grammar-words-title");
    title.id = where + "-words-title";
    box.appendChild(title);
    var list = el("ul", "next-rows");
    list.id = where + "-word-rows";
    list.setAttribute("aria-labelledby", title.id);
    box.appendChild(list);
    return box;
  }

  function columnHead(column) {
    var th = el("th", "");
    th.setAttribute("scope", "col");
    var long = el("span", "tense-long");
    long.appendChild(document.createTextNode(column.name));
    if (column.term && showTerms()) {
      long.appendChild(document.createTextNode(" · "));
      long.appendChild(russian(column.term));
    }
    th.appendChild(long);
    var short = el("span", "tense-short", column.short || column.name);
    short.setAttribute("aria-hidden", "true");
    th.appendChild(short);
    return th;
  }

  // A grid: a real table, its headers scoped, a square a button that opens its words in
  // the box under its own table. `none` names the squares that are no such form.
  function ruGrid(code, where, kind, view, rows, columns, labelled, none) {
    var table = el("table", "grammar " + kind + (columns.length === 2 ? " two" : ""));
    table.id = where;
    table.setAttribute("aria-labelledby", labelled);
    var head = el("thead");
    var headRow = el("tr");
    headRow.appendChild(el("td"));
    columns.forEach(function (column) {
      headRow.appendChild(columnHead(column));
    });
    head.appendChild(headRow);
    table.appendChild(head);
    var body = el("tbody");
    var weakest = view.gap ? view.gap.row : null;
    rows.forEach(function (named) {
      var line = null;
      (view.rows || []).forEach(function (one) {
        if (one.row === named.key) line = one;
      });
      if (!line) return;
      var tr = el("tr", "grammar-row" + (weakest === named.key ? " weakest" : ""));
      var th = el("th", "grammar-binyan");
      th.setAttribute("scope", "row");
      th.appendChild(named.label ? named.label() : ruName(named.name, named.term));
      tr.appendChild(th);
      columns.forEach(function (column) {
        if (none && none(named.key, column.key)) {
          var blank = el("td", "grammar-square none");
          var hatch = el("span", "");
          hatch.appendChild(el("span", "sr", t("progress.ru.none", "No such form")));
          blank.appendChild(hatch);
          tr.appendChild(blank);
          return;
        }
        var cell = (line.cells || {})[column.key];
        tr.appendChild(
          squareFor(cell ? cell.known : null, where, function (square) {
            showRuWords(
              code,
              square,
              where,
              t("progress.gap.words-title", "{pattern}, {tense}: the words you met", {
                pattern: named.title || named.name,
                tense: String(column.name).toLowerCase(),
              }),
              cell.words
            );
          })
        );
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    return table;
  }

  function note(host, text, nodes) {
    var p = el("p", "gap-note");
    if (nodes) sentenceWith(p, text, nodes);
    else p.textContent = text;
    host.appendChild(p);
    return p;
  }

  function part(host, which, id) {
    var holder = el("div", "gap-part");
    holder.id = "ru-part-" + id;
    var title = el("h4", "gap-part-title");
    title.id = "ru-" + id + "-title";
    var named = RU_TITLES[which];
    title.appendChild(document.createTextNode(named.name));
    if (showTerms()) {
      title.appendChild(document.createTextNode(" "));
      title.appendChild(russian("· " + named.term, "grammar-name"));
    }
    holder.appendChild(title);
    host.appendChild(holder);
    return holder;
  }

  function floorLine(said) {
    return t("progress.gap.mishkal-floor", "A dash means you met these fewer than {n} times, too few to say.", { n: said.cellFloor });
  }

  // A pair of verbs as a row: "спрашивать · спросить", its meaning, and which are known.
  function pairRow(host, code, first, second, meaning, known, names) {
    var own = meaningOf(code, first) || meaningOf(code, second);
    var said = (own && (own.note || own.meaning)) || meaning || "";
    var end;
    if (known === "both") end = t("progress.ru.pairs-both", "both known");
    else if (known === "neither") end = t("progress.ru.not-yet", "not yet");
    else end = t("progress.ru.pairs-known", "{w} known", { w: known === names[0] ? first : second });
    var item = row(host, first + " · " + second, "ru", said ? t("progress.gap.meaning", "“{meaning}”", { meaning: said }) : "", end, null, known === "both");
    item.className += " next-stack";
    return item;
  }

  function drawAspect(code, said, panel) {
    var aspect = said.aspect;
    var label = el("span", "sr", t("progress.ru.tab-aspect", "Aspect"));
    label.id = "ru-aspect-title";
    panel.appendChild(label);
    panel.appendChild(
      ruGrid(code, "ru-aspect-grid", "aspect", aspect, RU_ASPECTS.map(function (one) {
        return { key: one.key, name: one.name, term: one.term };
      }), RU_TENSES, "ru-aspect-title", function (row, column) {
        // A perfective has no present: always drawn, whatever the counts.
        return row === "perfective" && column === "present";
      })
    );
    note(panel, t("progress.ru.aspect-note", "Share of the verb forms you met that you know. Participles and gerunds are under More. Tap a square to see its words."));
    var none = el("p", "gap-note");
    sentenceWith(none, t("progress.ru.aspect-none", "A perfective verb has no present: what looks like one is its future, {f} “I’ll read”."), { "{f}": russian("прочитаю") });
    none.appendChild(document.createTextNode(" " + t("progress.gap.floor", "A dash means fewer than {n} forms met, too few to say.", { n: said.cellFloor })));
    panel.appendChild(none);
    panel.appendChild(wordsBox("ru-aspect-grid"));

    var pairs = said.pairs;
    if (!pairs || !(pairs.rows || []).length) return;
    var holder = part(panel, "pairs", "pairs");
    var line = el("p", "gap-part-said", tn("progress.ru.pairs-said", pairs.met, "You know both verbs of {both} of the {n} pair you’ve met.", "You know both verbs of {both} of the {n} pairs you’ve met.", { both: pairs.both }));
    holder.appendChild(line);
    var list = el("ul", "next-rows next-stack");
    list.setAttribute("aria-labelledby", "ru-pairs-title");
    pairs.rows.forEach(function (one) {
      pairRow(list, code, one.imperfective, one.perfective, one.meaning, one.known, ["imperfective", "perfective"]);
    });
    holder.appendChild(list);
    note(holder, t("progress.ru.pairs-note", "Pairs where you know one verb come first, the most met at the top. Imperfective first, then perfective."));
  }

  function drawCases(code, said, panel) {
    var label = el("span", "sr", t("progress.ru.tab-cases", "Cases"));
    label.id = "ru-cases-title";
    panel.appendChild(label);
    panel.appendChild(ruGrid(code, "ru-cases-grid", "cases", said.cases, RU_CASES, RU_NUMBERS, "ru-cases-title"));
    note(panel, t("progress.ru.cases-note", "Share of the nouns and adjectives you met in each case that you know. Tap a square to see its words."));
    var animate = el("p", "gap-note");
    sentenceWith(animate, t("progress.ru.cases-animate", "For a person or an animal the accusative takes the genitive’s ending, {f}. The animate row counts nouns only."), { "{f}": russian("вижу брата") });
    animate.appendChild(document.createTextNode(" " + floorLine(said)));
    panel.appendChild(animate);
    panel.appendChild(wordsBox("ru-cases-grid"));

    var place = said.place;
    if (!place) return;
    var holder = part(panel, "place", "place");
    var rows = RU_PREPOSITIONS.map(function (one) {
      return {
        key: one.key,
        name: one.term,
        title: one.term,
        label: function () {
          var span = el("span", "");
          span.appendChild(russian(one.term, "grammar-prep"));
          // A gloss for a reader who does not read the page in Russian.
          var gloss = showTerms() ? one.gloss : "";
          if (gloss) {
            span.appendChild(document.createTextNode(" "));
            span.appendChild(el("span", "grammar-name", gloss));
          }
          return span;
        },
      };
    });
    holder.appendChild(ruGrid(code, "ru-place-grid", "place", place, rows, RU_PLACES, "ru-place-title"));
    note(holder, t("progress.ru.place-note", "Share of the words you met after each preposition that you know. {v} and {na} say where with the prepositional, {e1}; {za} and {pod} with the instrumental, {e2}. All four say where to with the accusative, {e3}."), {
      "{v}": russian("в"),
      "{na}": russian("на"),
      "{za}": russian("за"),
      "{pod}": russian("под"),
      "{e1}": russian("в школе"),
      "{e2}": russian("под столом"),
      "{e3}": russian("в школу"),
    });
    note(holder, floorLine(said));
    holder.appendChild(wordsBox("ru-place-grid"));
  }

  function drawMotion(code, said, host) {
    var motion = said.motion;
    var holder = part(host, "motion", "motion");
    var one = motion.cells.one;
    var back = motion.cells.back;
    if (one && back) {
      holder.appendChild(el("p", "gap-part-said", t("progress.ru.motion-said", "You know {n}% of the one-way forms you meet, and {m}% of the there-and-back ones.", { n: one.known, m: back.known })));
    }
    var allName = t("progress.ru.motion-all", "All the pairs you met");
    holder.appendChild(
      ruGrid(code, "ru-motion-grid", "motion", { rows: [{ row: "all", cells: motion.cells }] }, [{ key: "all", name: allName, title: t("progress.ru.motion-title", "Verbs of motion") }], RU_WAYS, "ru-motion-title")
    );
    holder.appendChild(wordsBox("ru-motion-grid"));
    var list = el("ul", "next-rows next-stack motion-pairs");
    list.setAttribute("aria-labelledby", "ru-motion-title");
    (motion.pairs || []).forEach(function (pair) {
      pairRow(list, code, pair.one, pair.back, pair.meaning, pair.known, ["one", "back"]);
    });
    holder.appendChild(list);
    note(holder, t("progress.ru.motion-note", "Both verbs of a pair are imperfective: {a} is one way, now; {b} is there and back, or often. A pair is one dictionary word each way, so the pairs are listed as known or not, never as a share."), {
      "{a}": russian("идти"),
      "{b}": russian("ходить"),
    });
  }

  function drawSoft(code, said, host) {
    var soft = said.soft;
    var holder = part(host, "soft", "soft");
    var wrap = el("div", "gap-mishkal soft");
    var table = el("table", "mishkal");
    table.id = "ru-soft-grid";
    table.setAttribute("aria-labelledby", "ru-soft-title");
    var widths = el("colgroup");
    widths.appendChild(el("col"));
    widths.appendChild(el("col", "mishkal-share"));
    table.appendChild(widths);
    var head = el("thead");
    var headRow = el("tr");
    [t("progress.ru.soft-head", "Nouns"), t("progress.gap.mishkal-head-known", "Known")].forEach(function (name) {
      var th = el("th", "", name);
      th.setAttribute("scope", "col");
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    table.appendChild(head);
    var body = el("tbody");
    RU_GENDERS.forEach(function (gender) {
      var line = null;
      (soft.rows || []).forEach(function (one) {
        if (one.row === gender.key) line = one;
      });
      if (!line) return;
      var tr = el("tr", "mishkal-row");
      var th = el("th", "mishkal-pattern");
      th.setAttribute("scope", "row");
      var said2 = el("span", "mishkal-line");
      said2.appendChild(el("span", "grammar-en", gender.name));
      if ((line.examples || []).length) said2.appendChild(russian(line.examples.join(", "), "mishkal-means"));
      th.appendChild(said2);
      tr.appendChild(th);
      var cell = line.cells.all;
      tr.appendChild(
        squareFor(cell ? cell.known : null, "ru-soft-grid", function (square) {
          showRuWords(
            code,
            square,
            "ru-soft-grid",
            t("progress.gap.mishkal-words-title", "{pattern}: the words you met", {
              pattern: gender.name + ", -ь",
            }),
            cell.words
          );
        })
      );
      body.appendChild(tr);
    });
    table.appendChild(body);
    wrap.appendChild(table);
    holder.appendChild(wrap);
    note(holder, t("progress.ru.soft-note", "A noun in -ь can be either, and the ending gives no clue. What agrees with it does: {a}, {b}."), {
      "{a}": russian("эта дверь"),
      "{b}": russian("этот день"),
    });
    holder.appendChild(wordsBox("ru-soft-grid"));
  }

  function drawForms(code, said, host) {
    var holder = part(host, "forms", "forms");
    var rows = RU_FORMS.map(function (one) {
      return {
        key: one.key,
        name: one.name,
        label: function () {
          var span = el("span", "");
          span.appendChild(el("span", "grammar-en", one.name));
          span.appendChild(document.createTextNode(" "));
          span.appendChild(russian(one.example, "grammar-ru"));
          return span;
        },
      };
    });
    var columns = RU_ASPECTS.map(function (one) {
      return { key: one.key, name: one.name, short: one.short };
    });
    holder.appendChild(ruGrid(code, "ru-forms-grid", "forms", said.forms, rows, columns, "ru-forms-title"));
    note(holder, t("progress.ru.forms-note", "Share of the participles and gerunds you met that you know. Courses usually teach them at B1, for reading. A participle we can’t sort as active or passive is left out."));
    note(holder, floorLine(said));
    holder.appendChild(wordsBox("ru-forms-grid"));
  }

  function showRuTab(which, focus) {
    var tabs = document.querySelectorAll("#ru-tabs [role=tab]");
    for (var n = 0; n < tabs.length; n++) {
      var on = tabs[n].getAttribute("data-tab") === which;
      tabs[n].setAttribute("aria-selected", on ? "true" : "false");
      tabs[n].classList.toggle("on", on);
      tabs[n].tabIndex = on ? 0 : -1;
      if (on && focus) tabs[n].focus();
    }
    document.getElementById("ru-aspect").hidden = which !== "aspect";
    document.getElementById("ru-cases").hidden = which !== "cases";
  }

  (function wireRuTabs() {
    var strip = document.getElementById("ru-tabs");
    if (!strip) return;
    strip.addEventListener("click", function (event) {
      var tab = event.target.closest("[role=tab]");
      if (!tab || tab.getAttribute("aria-selected") === "true") return;
      shutWords();
      showRuTab(tab.getAttribute("data-tab"), false);
    });
    strip.addEventListener("keydown", function (event) {
      var keys = { ArrowLeft: -1, ArrowRight: 1, Home: "first", End: "last" };
      if (!(event.key in keys)) return;
      var tabs = Array.prototype.slice.call(strip.querySelectorAll("[role=tab]"));
      var at = tabs.indexOf(document.activeElement);
      var step = keys[event.key];
      var next = step === "first" ? 0 : step === "last" ? tabs.length - 1 : (at + step + tabs.length) % tabs.length;
      event.preventDefault();
      shutWords();
      showRuTab(tabs[next].getAttribute("data-tab"), true);
    });
    var more = document.getElementById("ru-more");
    // Shutting More shuts a list open inside it.
    if (more) more.addEventListener("toggle", function () {
      if (!more.open && openBox && more.contains(openBox)) shutWords();
    });
  })();

  // A word met, as the headline's sentence names it: the form, and its meaning where
  // there is one.
  function ruExample(code, one) {
    var holder = el("span", "gap-example");
    holder.appendChild(russian(one.form || one.lemma));
    var meaning = ruMeaning(code, one);
    if (meaning) holder.appendChild(document.createTextNode(" " + t("progress.gap.meaning", "“{meaning}”", { meaning: meaning })));
    return holder;
  }

  function ruExamples(lead, code, met) {
    var mine = (met || []).filter(function (one) {
      return !!ruMeaning(code, one);
    });
    var two = mine.concat((met || []).filter(function (one) { return mine.indexOf(one) < 0; })).slice(0, 2);
    if (two.length === 2) {
      lead.appendChild(document.createTextNode(" "));
      sentenceWith(lead, t("progress.gap.examples", "You've met {first} and {second}."), {
        "{first}": ruExample(code, two[0]),
        "{second}": ruExample(code, two[1]),
      });
    } else if (two.length === 1) {
      lead.appendChild(document.createTextNode(" "));
      sentenceWith(lead, t("progress.gap.example", "You've met {first}."), { "{first}": ruExample(code, two[0]) });
    }
  }

  function drawRussian(code) {
    var box = document.getElementById("gap-ru");
    if (!box) return;
    var said = story[code];
    var ru = code === "ru" && said ? said.russian || null : null;
    var aspectPanel = document.getElementById("ru-aspect");
    var casesPanel = document.getElementById("ru-cases");
    var more = document.getElementById("ru-more");
    var parts = document.getElementById("ru-more-parts");
    aspectPanel.textContent = "";
    casesPanel.textContent = "";
    parts.textContent = "";
    more.open = false;
    box.hidden = !ru;
    if (!ru) return;
    shutWords();
    if (ru.aspect) drawAspect(code, ru, aspectPanel);
    if (ru.cases) drawCases(code, ru, casesPanel);
    var both = !!ru.aspect && !!ru.cases;
    document.getElementById("ru-tabs").hidden = !both;
    showRuTab(both ? (ru.lead === "cases" ? "cases" : "aspect") : ru.aspect ? "aspect" : "cases", false);

    // More: in a course's order, each part only where it has enough; shut on every load.
    var which = [];
    if (ru.motion) {
      drawMotion(code, ru, parts);
      which.push(RU_TITLES.motion.name);
    }
    if (ru.soft) {
      drawSoft(code, ru, parts);
      which.push(RU_TITLES.soft.name);
    }
    if (ru.forms) {
      drawForms(code, ru, parts);
      which.push(RU_TITLES.forms.name);
    }
    more.hidden = !which.length;
    document.getElementById("ru-more-which").textContent = which.join(" · ");

    // The headline: an aspect or a case, whichever sits further under its own kind.
    var title = document.getElementById("next-title");
    var lead = document.getElementById("gap-said");
    var gap = ru.lead === "aspect" && ru.aspect ? ru.aspect.gap : ru.lead === "cases" && ru.cases ? ru.cases.gap : null;
    if (!gap) return;
    lead.textContent = "";
    lead.hidden = false;
    if (ru.lead === "aspect") {
      var perfective = gap.row === "perfective";
      title.textContent = perfective
        ? t("progress.ru.title-perfective", "Your biggest gap: perfective verbs")
        : t("progress.ru.title-imperfective", "Your biggest gap: imperfective verbs");
      lead.appendChild(
        document.createTextNode(
          (perfective
            ? t("progress.ru.said-perfective", "You know {n}% of the perfective forms you meet, against {m}% for imperfective ones.", { n: gap.known, m: gap.others })
            : t("progress.ru.said-imperfective", "You know {n}% of the imperfective forms you meet, against {m}% for perfective ones.", { n: gap.known, m: gap.others })) +
            " " +
            (perfective
              ? t("progress.ru.does-perfective", "A perfective verb says a thing was done, or will be, once and to the end.")
              : t("progress.ru.does-imperfective", "An imperfective verb says a thing goes on, comes round, or is simply named."))
        )
      );
    } else {
      var named = RU_CASE_GAP[gap.row];
      if (!named) return;
      title.textContent = t("progress.ru.title-case", "Your biggest gap: {case}", { case: named.name });
      lead.appendChild(
        document.createTextNode(
          t("progress.ru.said-case", "You know {n}% of the forms you meet in this case, against {m}% in the other cases.", { n: gap.known, m: gap.others }) + " "
        )
      );
      var fills = { "{f}": russian("вижу брата") };
      (named.fill || []).forEach(function (word, n) {
        fills["{" + "abc".charAt(n) + "}"] = russian(word);
      });
      sentenceWith(lead, named.does, fills);
    }
    ruExamples(lead, code, gap.examples);
  }

  function drawNext(code) {
    var said = story[code];
    drawGap(code);
    drawRussian(code);
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
    // Our estimate where it is the text's figure, said as home's card says it, the label
    // quiet beside the number (design.md §12, "A text's figure is our estimate until your
    // marks settle it", 2026-11-04).
    texts.forEach(function (one) {
      var item = row(
        level,
        one.title,
        code,
        "",
        one.estimated
          ? t("known.estimate.about", "About {n}%", { n: one.known }) + " "
          : t("progress.next.known", "{n}% known", { n: one.known }),
        keyed("/library#" + encodeURIComponent(one.id)),
        true
      );
      if (one.estimated) {
        var end = item.querySelector(".next-end");
        if (end) {
          end.className += " is-estimate";
          end.appendChild(el("span", "estimate-ours", t("known.estimate.ours", "(our estimate)")));
        }
      }
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
    // Where the language has a yardstick, "How much Hebrew you understand" stands in
    // this card's place (targum-internal#575).
    if (!readingSeries || understands(code)) {
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
        understandSeries = said.understand || {};
        if (typeof said.measurable === "number") readingMeasurable = said.measurable;
        drawReading(currentCode);
        drawUnderstand(currentCode);
      })
      .catch(function () {
        readingFailed = true;
        drawReading(currentCode);
      });
  }

  /* --- how much Hebrew you understand (targum-internal#575) ------------------------
   *
   * design.md §12, "How much Hebrew you understand is measured on a fixed yardstick"
   * (2026-10-30). The share of a fixed word list's running words, weighted by frequency,
   * that the reader's known words cover, on one of four yardsticks: everyday
   * conversation, a news article, classic literature, the Bible. News opens for
   * everyone; a yardstick with no list yet is left out of the picker, never shown as 0%.
   * The choice changes this card and nothing else.
   *
   * The server sends, per yardstick, the exact percentage now, `base` (what the words
   * known before the word records began cover) and each day's `gain` since, all against
   * the current list (`level.coverage_days`). A point is `base` plus every gain up to the
   * end of its week or month, so the line moves only when the reader learns a word, and
   * never falls. Nothing before `began` is drawn: the record cannot say when those words
   * were learned, and the card says from when it counts.
   */
  var understandSeries = null;
  /* The four modern registers what readers bring is sorted into, and what learners bring
     that sorts into none, follow the first four (David, 2026-11-01): each is offered once
     it has a list, and the picker shows every one that has. */
  var UNDERSTAND_ORDER = ["conversation", "news", "literature", "bible", "social", "video", "podcasts", "everyday", "imports"];
  var UNDERSTAND_KEY = "targum.progress.understand";
  var UNDERSTAND_BY_KEY = "targum.progress.understand-by";
  var UNDERSTAND_SPAN = 12;
  var YARDSTICKS = {
    conversation: {
      option: t("progress.understand.option.conversation", "Everyday conversation"),
      chosen: t("progress.understand.chosen.conversation", "everyday conversation"),
      said: function (p) {
        return t("progress.understand.said.conversation", "You know {p}% of the words in everyday conversation.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.conversation", "You know {p}% of the words in everyday conversation, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
    news: {
      option: t("progress.understand.option.news", "A news article"),
      chosen: t("progress.understand.chosen.news", "a news article"),
      said: function (p) {
        return t("progress.understand.said.news", "You know {p}% of the words in a typical news article.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.news", "You know {p}% of the words in a typical news article, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
    literature: {
      option: t("progress.understand.option.literature", "Classic literature"),
      chosen: t("progress.understand.chosen.literature", "classic literature"),
      said: function (p) {
        return t("progress.understand.said.literature", "You know {p}% of the words in classic literature.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.literature", "You know {p}% of the words in classic literature, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
    bible: {
      option: t("progress.understand.option.bible", "The Bible"),
      chosen: t("progress.understand.chosen.bible", "the Bible"),
      said: function (p) {
        return t("progress.understand.said.bible", "You know {p}% of the words in the Bible.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.bible", "You know {p}% of the words in the Bible, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
    social: {
      option: t("progress.understand.option.social", "Social media"),
      chosen: t("progress.understand.chosen.social", "social media"),
      said: function (p) {
        return t("progress.understand.said.social", "You know {p}% of the words in social media posts.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.social", "You know {p}% of the words in social media posts, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
    video: {
      option: t("progress.understand.option.video", "Online video"),
      chosen: t("progress.understand.chosen.video", "online video"),
      said: function (p) {
        return t("progress.understand.said.video", "You know {p}% of the words in online video.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.video", "You know {p}% of the words in online video, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
    podcasts: {
      option: t("progress.understand.option.podcasts", "Podcasts and radio"),
      chosen: t("progress.understand.chosen.podcasts", "podcasts and radio"),
      said: function (p) {
        return t("progress.understand.said.podcasts", "You know {p}% of the words in podcasts and radio.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.podcasts", "You know {p}% of the words in podcasts and radio, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
    everyday: {
      option: t("progress.understand.option.everyday", "Everyday life"),
      chosen: t("progress.understand.chosen.everyday", "everyday life"),
      said: function (p) {
        return t("progress.understand.said.everyday", "You know {p}% of the words of everyday life.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.everyday", "You know {p}% of the words of everyday life, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
    imports: {
      option: t("progress.understand.option.imports", "What learners bring"),
      chosen: t("progress.understand.chosen.imports", "what learners bring"),
      said: function (p) {
        return t("progress.understand.said.imports", "You know {p}% of the words in the texts learners bring.", { p: p });
      },
      up: function (p, q, then) {
        return t("progress.understand.up.imports", "You know {p}% of the words in the texts learners bring, up from {q}% {then}.", { p: p, q: q, then: then });
      },
    },
  };

  /* The whole percentage a share is shown as, by `level.known_percent`'s rule (design.md
     §12, "How much of a text you know is an exact percentage", 2026-10-29): rounded, but
     under all of it never 100 and above none of it never 0. */
  function exactPercent(share) {
    var value = Number(share) || 0;
    var percent = Math.max(0, Math.min(100, Math.round(value * 100)));
    if (value < 1 && percent >= 100) return 99;
    if (value > 0 && percent <= 0) return 1;
    return percent;
  }

  function remembered(key, allowed) {
    try {
      var said = localStorage.getItem(key) || "";
      return allowed.indexOf(said) >= 0 ? said : "";
    } catch (e) {
      return "";
    }
  }

  function keep(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      /* remembered for this page only */
    }
  }

  function understandOf(code) {
    var mine = understandSeries && understandSeries[code];
    if (!mine || !mine.registers) return null;
    var present = UNDERSTAND_ORDER.filter(function (one) {
      return mine.registers[one];
    });
    return present.length ? { began: Number(mine.began) || 0, registers: mine.registers, present: present } : null;
  }

  //: Whether a language has a yardstick to show; "Words you knew" stands where it has none.
  function understands(code) {
    var mine = understandOf(code);
    if (!mine) return false;
    // Nothing known on any list yet: no card, as "Words you knew" had none before a point.
    return mine.present.some(function (one) {
      var entry = mine.registers[one];
      return Number(entry.base) > 0 || (entry.days || []).length > 0;
    });
  }

  var understandRegister = "";
  var understandBy = "";

  function chosenRegister(mine) {
    if (understandRegister && mine.present.indexOf(understandRegister) >= 0) return understandRegister;
    var kept = remembered(UNDERSTAND_KEY, mine.present);
    if (kept) return kept;
    // News for everyone (David, 2026-10-30); the next in the picker's order where news
    // has no list yet.
    return mine.present.indexOf("news") >= 0 ? "news" : mine.present[0];
  }

  /* The points of one yardstick by Week or Month: the share at the end of each period
     since the records began, the current one's being now and the server's own figure. */
  function understandPoints(by, mine, register) {
    var entry = mine.registers[register];
    var gains = (entry.days || []).slice().sort(function (a, b) {
      return a.day < b.day ? -1 : a.day > b.day ? 1 : 0;
    });
    function shareBy(day) {
      var share = Number(entry.base) || 0;
      gains.forEach(function (one) {
        if (one.day <= day) share += Number(one.gain) || 0;
      });
      return share;
    }
    var today = todayHere();
    var beganDay = mine.began ? dayOf(localDay(new Date(mine.began))) : null;
    var points = [];
    if (by === "month") {
      var first = beganDay || today;
      var y = first.getUTCFullYear();
      var m = first.getUTCMonth();
      while (y < today.getUTCFullYear() || (y === today.getUTCFullYear() && m <= today.getUTCMonth())) {
        var start = new Date(Date.UTC(y, m, 1));
        var end = new Date(Date.UTC(y, m + 1, 0));
        var current = end >= today;
        var month = isoDay(start).slice(0, 7);
        points.push({
          start: start,
          share: shareBy(isoDay(current ? today : end)),
          isNow: current,
          month: month,
          when: monthName(month, y !== today.getUTCFullYear()),
          whenFull: monthName(month, true),
          then: t("progress.understand.then-month", "in {month}", {
            month: charts.monthInDate(m, pageLanguage()),
          }),
        });
        m += 1;
        if (m > 11) {
          m = 0;
          y += 1;
        }
      }
    } else {
      var week = weekOf(beganDay || today);
      var last = weekOf(today);
      while (week <= last) {
        var weekEnd = new Date(week.getTime() + 6 * 86400000);
        var now = week.getTime() === last.getTime();
        var lastWeek = week.getTime() === last.getTime() - 7 * 86400000;
        points.push({
          start: week,
          share: shareBy(isoDay(now ? today : weekEnd)),
          isNow: now,
          when: now
            ? t("progress.understand.this-week", "This week")
            : lastWeek
              ? t("progress.understand.last-week", "Last week")
              : shortDay(week),
          whenFull: now
            ? t("progress.understand.this-week", "This week")
            : lastWeek
              ? t("progress.understand.last-week", "Last week")
              : t("progress.reading.week-of", "Week of {day}", { day: dayName(week) }),
          then: lastWeek
            ? t("progress.understand.then-last-week", "last week")
            : t("progress.understand.then-week", "in the week of {day}", { day: dayName(week) }),
        });
        week = new Date(week.getTime() + 7 * 86400000);
      }
    }
    points = points.slice(-UNDERSTAND_SPAN);
    points.forEach(function (point, index) {
      point.percent = point.isNow ? Number(entry.percent) : exactPercent(point.share);
      point.at = points.length > 1 ? index / (points.length - 1) : 1;
    });
    return points;
  }

  function chosenUnderstandBy(mine, register) {
    var kept = remembered(UNDERSTAND_BY_KEY, ["week", "month"]);
    if (kept) return kept;
    // The coarsest view with two points (David, 2026-10-29), Week before there are two.
    return understandPoints("month", mine, register).length >= 2 ? "month" : "week";
  }

  function closeUnderstandList(focusButton) {
    var list = document.getElementById("understand-list");
    var open = document.getElementById("understand-open");
    if (!list || list.hidden) return;
    list.hidden = true;
    if (open) {
      open.setAttribute("aria-expanded", "false");
      if (focusButton) open.focus();
    }
  }

  function drawUnderstandList(mine, register) {
    var list = document.getElementById("understand-list");
    var open = document.getElementById("understand-open");
    var chosen = document.getElementById("understand-chosen");
    if (!list || !open || !chosen) return;
    chosen.textContent = YARDSTICKS[register].chosen;
    open.setAttribute(
      "aria-label",
      t("progress.understand.open", "Compare with: {yardstick}", { yardstick: YARDSTICKS[register].chosen })
    );
    list.textContent = "";
    mine.present.forEach(function (one) {
      var option = el("li", "understand-option");
      option.id = "understand-" + one;
      option.setAttribute("role", "option");
      option.setAttribute("data-register", one);
      option.setAttribute("aria-selected", one === register ? "true" : "false");
      var tick = el("span", "understand-tick", one === register ? "\u2713" : "");
      tick.setAttribute("aria-hidden", "true");
      option.appendChild(tick);
      option.appendChild(el("span", "understand-name", YARDSTICKS[one].option));
      option.appendChild(el("span", "understand-figure", Number(mine.registers[one].percent) + "%"));
      option.addEventListener("click", function () {
        pickUnderstand(one);
      });
      list.appendChild(option);
    });
    list.setAttribute("aria-activedescendant", "understand-" + register);
  }

  function pickUnderstand(register) {
    understandRegister = register;
    keep(UNDERSTAND_KEY, register);
    closeUnderstandList(true);
    drawUnderstand(currentCode);
  }

  function drawUnderstand(code) {
    var panel = document.getElementById("understand");
    var host = document.getElementById("understand-line");
    var said = document.getElementById("understand-said");
    var read = document.getElementById("understand-read");
    var since_ = document.getElementById("understand-since");
    var switcher = document.getElementById("understand-by");
    if (!panel || !host || !said) return;
    var mine = understandOf(code);
    panel.hidden = !understands(code);
    if (panel.hidden) return;
    var register = chosenRegister(mine);
    if (!understandBy) understandBy = chosenUnderstandBy(mine, register);
    panel.setAttribute("data-by", understandBy);
    panel.setAttribute("data-register", register);
    Array.prototype.forEach.call(switcher ? switcher.querySelectorAll("button") : [], function (button) {
      button.setAttribute("aria-pressed", button.getAttribute("data-by") === understandBy ? "true" : "false");
    });
    drawUnderstandList(mine, register);

    var stick = YARDSTICKS[register];
    var points = understandPoints(understandBy, mine, register);
    var last = points[points.length - 1];
    var firstPoint = points[0];
    var up = points.length > 1 && last.percent > firstPoint.percent;
    said.textContent = "";
    var figure = el("b", "", last.percent + "%");
    sentenceWith(
      said,
      up ? stick.up("\u0001", firstPoint.percent, firstPoint.then) : stick.said("\u0001"),
      { "\u0001%": figure, "\u0001": figure }
    );

    // What they read, as one small line: the reading record's own share for the period.
    if (read) {
      var from = understandBy === "week" ? isoDay(weekOf(todayHere())) : isoDay(todayHere()).slice(0, 7) + "-01";
      var sum = { tokens: 0, known: 0 };
      ((readingSeries && readingSeries[code] && readingSeries[code].days) || []).forEach(function (day) {
        if (String(day.day) < from) return;
        sum.tokens += Number(day.tokens) || 0;
        sum.known += Number(day.known) || 0;
      });
      read.hidden = sum.tokens < readingMeasurable;
      if (!read.hidden) {
        var p = exactPercent(sum.known / Math.max(1, sum.tokens));
        read.textContent =
          understandBy === "week"
            ? t("progress.understand.read-week", "In what you read this week you knew {p}% of the words.", { p: p })
            : t("progress.understand.read-month", "In what you read this month you knew {p}% of the words.", { p: p });
      }
    }

    // From when it counts, where the view would reach back past it.
    if (since_) {
      var beganDay = mine.began ? localDay(new Date(mine.began)) : "";
      since_.hidden = !beganDay || points.length >= UNDERSTAND_SPAN;
      if (!since_.hidden) {
        since_.textContent = t("progress.understand.since", "Counted since {date}.", { date: shortDay(dayOf(beganDay)) });
      }
    }

    host.textContent = "";
    var W = Math.max(240, Math.round(host.clientWidth || (host.getBoundingClientRect ? host.getBoundingClientRect().width : 0) || 508));
    var H = 120;
    if (points.length < 2) {
      var empty = el("div", "chart chart-empty");
      empty.appendChild(
        el(
          "p",
          "reading-empty",
          understandBy === "week"
            ? t("progress.understand.empty-week", "We'll draw the line once there are two weeks to show.")
            : t("progress.understand.empty-month", "We'll draw the line once there are two months to show.")
        )
      );
      host.appendChild(empty);
      return;
    }

    // The scale reaches 100% at the top and starts at a round tenth under the lowest
    // point, so a line that climbs from 79% to 87% is not drawn flat.
    var lowest = Math.min.apply(null, points.map(function (one) { return one.share; }));
    var floor = lowest < 0.5 ? 0 : Math.max(0, Math.floor((lowest - 0.05) * 10) / 10);
    var pad = { top: 12, right: 20, bottom: 22, left: 20 };
    var plotW = W - pad.left - pad.right;
    var plotH = H - pad.top - pad.bottom;
    function px(point) {
      return pad.left + point.at * plotW;
    }
    function py(value) {
      return pad.top + plotH - ((value - floor) / (1 - floor)) * plotH;
    }
    function spoken(point) {
      return t("progress.reading.point", "{when}: {p}%", { when: point.whenFull, p: point.percent });
    }
    var wrap = el("div", "chart");
    var picture = svg("svg", {
      viewBox: "0 0 " + W + " " + H,
      width: W,
      height: H,
      role: "img",
      tabindex: "0",
      "aria-label": t("progress.understand.label", "Words you know in {yardstick}, {first} to {last}", {
        yardstick: stick.chosen,
        first: firstPoint.whenFull,
        last: last.whenFull,
      }),
    });
    picture.appendChild(svg("line", { class: "reading-base", x1: 0, y1: H - pad.bottom + 2, x2: W, y2: H - pad.bottom + 2 }));
    picture.appendChild(svg("line", { class: "understand-top", x1: 0, y1: pad.top, x2: W, y2: pad.top }));
    var full = svg("text", { class: "reading-month understand-full", x: 0, y: pad.top - 3 });
    full.textContent = "100%";
    picture.appendChild(full);
    var line = points
      .map(function (point, index) {
        return (index ? "L" : "M") + px(point) + " " + py(point.share);
      })
      .join(" ");
    var area = line + " L" + px(last) + " " + (H - pad.bottom + 2) + " L" + px(firstPoint) + " " + (H - pad.bottom + 2) + " Z";
    picture.appendChild(svg("path", { class: "understand-area", d: area }));
    picture.appendChild(svg("path", { class: "reading-path", d: line, fill: "none", stroke: "var(--leaf)", "stroke-width": 3 }));
    var labelled = points.length <= 6;
    var dots = points.map(function (point, index) {
      var dot = svg("circle", {
        class: "reading-point",
        cx: px(point),
        cy: py(point.share),
        r: index === points.length - 1 ? 5 : 4,
        fill: "var(--leaf)",
      });
      var title = svg("title", {});
      title.textContent = spoken(point);
      dot.appendChild(title);
      picture.appendChild(dot);
      if (labelled || index === 0 || index === points.length - 1) {
        var anchor = index === 0 ? "start" : index === points.length - 1 ? "end" : "middle";
        var figure_ = svg("text", {
          class: "understand-figure" + (index === points.length - 1 ? " now" : ""),
          x: px(point),
          y: py(point.share) - 10,
          "text-anchor": anchor,
        });
        figure_.textContent = point.percent + "%";
        picture.appendChild(figure_);
      }
      return dot;
    });
    var axis = svg("g", { class: "axis" });
    points.forEach(function (point, index) {
      if (!labelled && index !== 0 && index !== points.length - 1) return;
      var name = svg("text", {
        class: "reading-month",
        x: px(point),
        y: H - 4,
        "text-anchor": index === 0 ? "start" : index === points.length - 1 ? "end" : "middle",
      });
      name.textContent = point.when;
      axis.appendChild(name);
    });
    picture.appendChild(axis);
    wrap.appendChild(picture);
    host.appendChild(wrap);
    var tip = tipFor(wrap);
    var live = document.getElementById("understand-live");
    var on = -1;
    function point(index, announce) {
      on = Math.max(0, Math.min(points.length - 1, index));
      dots.forEach(function (dot, at) {
        dot.classList.toggle("on", at === on && announce);
      });
      var hostBox = wrap.getBoundingClientRect();
      tip.show(spoken(points[on]), (px(points[on]) / W) * hostBox.width, (py(points[on].share) / H) * hostBox.height);
      if (announce && live) live.textContent = spoken(points[on]);
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
      var key_ = event.key;
      if (key_ === "ArrowLeft" || key_ === "ArrowRight" || key_ === "Home" || key_ === "End") {
        event.preventDefault();
        var to = key_ === "Home" ? 0 : key_ === "End" ? points.length - 1 : on + (key_ === "ArrowLeft" ? -1 : 1);
        point(to, true);
      }
    });
  }

  function wireUnderstand() {
    var switcher = document.getElementById("understand-by");
    var open = document.getElementById("understand-open");
    var list = document.getElementById("understand-list");
    var pick = document.getElementById("understand-pick");
    if (switcher) {
      Array.prototype.forEach.call(switcher.querySelectorAll("button"), function (button) {
        button.addEventListener("click", function () {
          understandBy = button.getAttribute("data-by");
          keep(UNDERSTAND_BY_KEY, understandBy);
          drawUnderstand(currentCode);
        });
      });
    }
    if (!open || !list) return;
    function options() {
      return Array.prototype.slice.call(list.querySelectorAll(".understand-option"));
    }
    function active() {
      var id = list.getAttribute("aria-activedescendant");
      var all = options();
      for (var i = 0; i < all.length; i++) if (all[i].id === id) return i;
      return 0;
    }
    function activate(index) {
      var all = options();
      if (!all.length) return;
      var at = Math.max(0, Math.min(all.length - 1, index));
      all.forEach(function (one, i) {
        one.classList.toggle("active", i === at);
      });
      list.setAttribute("aria-activedescendant", all[at].id);
    }
    function show() {
      list.hidden = false;
      open.setAttribute("aria-expanded", "true");
      var all = options();
      var selected = 0;
      all.forEach(function (one, i) {
        if (one.getAttribute("aria-selected") === "true") selected = i;
      });
      activate(selected);
      list.focus();
    }
    open.addEventListener("click", function (event) {
      event.stopPropagation();
      if (list.hidden) show();
      else closeUnderstandList(true);
    });
    open.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        show();
      }
    });
    list.addEventListener("keydown", function (event) {
      var key_ = event.key;
      if (key_ === "ArrowDown" || key_ === "ArrowUp") {
        event.preventDefault();
        activate(active() + (key_ === "ArrowDown" ? 1 : -1));
      } else if (key_ === "Home" || key_ === "End") {
        event.preventDefault();
        activate(key_ === "Home" ? 0 : options().length - 1);
      } else if (key_ === "Enter" || key_ === " ") {
        event.preventDefault();
        var chosen = options()[active()];
        if (chosen) pickUnderstand(chosen.getAttribute("data-register"));
      } else if (key_ === "Escape") {
        event.preventDefault();
        closeUnderstandList(true);
      } else if (key_ === "Tab") {
        closeUnderstandList(false);
      }
    });
    document.addEventListener("click", function (event) {
      if (pick && !pick.contains(event.target)) closeUnderstandList(false);
    });
  }
  wireUnderstand();

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
    drawUnderstand(code);
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
      drawUnderstand(currentCode);
    }, 150);
  });
})();
