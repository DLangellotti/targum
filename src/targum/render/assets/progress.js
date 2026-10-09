/* Your Progress, as a story in three parts (design.md §12, "Your Progress is a story in
 * three parts", 2026-10-09).
 *
 * Under the totals: where you are — a ladder of real kinds of text from the language's own
 * library, each a link to its shelf, and what you knew of what you read; how you got here —
 * time and words, and the words taken up week by week; and what next — the words you keep
 * meeting and the texts at your level now.
 *
 * The totals and the weeks are read from the browser's own store, the same one the reader
 * writes; the ladder, the words met and the texts at your level from `/account/story`, and
 * time and the reading line from the account's record. Nothing here spends.
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

  var KNOWN = 9;
  var STEPS = [
    { status: 1, name: t("progress.status.1", "just met"), slot: "--step-1" },
    { status: 2, name: t("progress.status.2", "getting there"), slot: "--step-2" },
    { status: 3, name: t("progress.status.3", "nearly there"), slot: "--step-3" },
    { status: KNOWN, name: t("progress.status.9", "known"), slot: "--step-4" },
  ];

  /* The rungs, each with what its chip says and the four sentences the headline can be.
     A sentence each rather than a name dropped into one: Russian declines the kind
     («почти всю новостную статью», «большую часть новостной статьи»), and a name in a
     slot would be wrong in two of the three. */
  var RUNGS = {
    dialogue: {
      chip: t("progress.touch.dialogue", "A conversation"),
      follow: t("progress.where.follow.dialogue", "You'd follow a conversation"),
      nearly: t("progress.where.nearly.dialogue", "You'd follow nearly all of a conversation"),
      most: t("progress.where.most.dialogue", "You'd follow most of a conversation"),
      start: t("progress.where.start.dialogue", "A conversation is the place to start"),
    },
    talk: {
      chip: t("progress.touch.talk", "A video"),
      follow: t("progress.where.follow.talk", "You'd follow a video"),
      nearly: t("progress.where.nearly.talk", "You'd follow nearly all of a video"),
      most: t("progress.where.most.talk", "You'd follow most of a video"),
      start: t("progress.where.start.talk", "A video is the place to start"),
    },
    article: {
      chip: t("progress.touch.article", "A news article"),
      follow: t("progress.where.follow.article", "You'd follow a news article"),
      nearly: t("progress.where.nearly.article", "You'd follow nearly all of a news article"),
      most: t("progress.where.most.article", "You'd follow most of a news article"),
      start: t("progress.where.start.article", "A news article is the place to start"),
    },
    story: {
      chip: t("progress.touch.story", "A short story"),
      follow: t("progress.where.follow.story", "You'd follow a short story"),
      nearly: t("progress.where.nearly.story", "You'd follow nearly all of a short story"),
      most: t("progress.where.most.story", "You'd follow most of a short story"),
      start: t("progress.where.start.story", "A short story is the place to start"),
    },
    "children-book": {
      chip: t("progress.touch.children-book", "A children's book"),
      follow: t("progress.where.follow.children-book", "You'd follow a children's book"),
      nearly: t("progress.where.nearly.children-book", "You'd follow nearly all of a children's book"),
      most: t("progress.where.most.children-book", "You'd follow most of a children's book"),
      start: t("progress.where.start.children-book", "A children's book is the place to start"),
    },
    novel: {
      chip: t("progress.touch.novel", "A novel"),
      follow: t("progress.where.follow.novel", "You'd follow a novel"),
      nearly: t("progress.where.nearly.novel", "You'd follow nearly all of a novel"),
      most: t("progress.where.most.novel", "You'd follow most of a novel"),
      start: t("progress.where.start.novel", "A novel is the place to start"),
    },
    poetry: {
      chip: t("progress.touch.poetry", "A poem"),
      follow: t("progress.where.follow.poetry", "You'd follow a poem"),
      nearly: t("progress.where.nearly.poetry", "You'd follow nearly all of a poem"),
      most: t("progress.where.most.poetry", "You'd follow most of a poem"),
      start: t("progress.where.start.poetry", "A poem is the place to start"),
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

  if (!codes.length) {
    document.getElementById("nothing").hidden = false;
    document.getElementById("library-link").href = keyed("/library");
    wireNav();
    // Signing in on a browser that has nothing is the whole point of signing in: this
    // is the new phone, and everything is about to arrive.
    if (window.TargumSync) {
      window.TargumSync.onChange(function (changed) {
        if (changed) location.reload();
      });
      window.TargumSync.start();
    }
    return;
  }

  document.getElementById("page").hidden = false;

  // Which language everything below is drawn for. The menu moves it.
  var currentCode = window.TargumLang.current(codes);

  // 1,000 rather than 1000. The counts are the point of the page and they get read.
  function grouped(count) {
    return String(count).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
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

    count(sums.saved, tn("progress.count.saved", sums.saved, "word on your list", "words on your list"), null, null, "saved");
    // The board's labels (§12, "The mockups win on Your Progress", 2026-10-09).
    count(sums.known, tn("progress.count.known", sums.known, "word known", "words known"), "leaf", null, "known");
    // What targum carried up to known, rather than what a reader arrived already having.
    count(
      sums.learned,
      tn("progress.count.learned", sums.learned, "learned on targum", "learned on targum"),
      "sun",
      t("progress.count.learned.title", "Saved as new and since marked known."),
      "learned"
    );
    count(sums.phrases, tn("progress.count.phrases", sums.phrases, "phrase saved", "phrases saved"), "iris", null, "phrases");
    count(sums.finished, tn("progress.count.finished", sums.finished, "targum finished", "targums finished"), "leaf", null, "finished");
    count(days.length, tn("progress.count.days", days.length, "day on targum", "days on targum"), null, null, "days");
    var read = wordsRead(code);
    if (read !== null) count(read, tn("progress.count.read", read, "word read", "words read"), null, null, "read");
  }

  /* --- 1 · where you are ------------------------------------------------------ */

  var story = {};
  var storyAsked = {};
  var signedIn = null;

  var TICK =
    '<svg class="touch-tick" viewBox="0 0 16 16" aria-hidden="true" focusable="false">' +
    '<path d="M3.5 8.5l3 3 6-7"/></svg>';

  function shelfHref(kind) {
    return keyed("/library#see/kind/" + encodeURIComponent(kind));
  }

  function drawWhere(code) {
    var head = document.getElementById("where-title");
    var list = document.getElementById("touchstones");
    var note = document.getElementById("where-note");
    list.textContent = "";
    list.hidden = true;
    note.hidden = true;
    note.textContent = "";
    var said = story[code];

    if (signedIn === false) {
      head.textContent = t("progress.where.signed-out", "Sign in and we'll say which texts you'd follow.");
      return;
    }
    if (!said) {
      head.textContent = "";
      return;
    }
    var ladder = said.ladder || [];
    if (!ladder.length) {
      // Aramaic has no ladder, Yiddish no library, and a box without the lemma index has
      // measured nothing: each says so, with the one count it does have.
      var known = said.known || 0;
      head.textContent = tn("progress.where.known", known, "You know {n} word so far", "You know {n} words so far", {
        n: grouped(known),
      });
      note.textContent =
        code === "arc"
          ? t(
              "progress.where.no-ladder-arc",
              "There's no ladder of texts for Aramaic: we have no list of how common its words are, so its texts can't be measured."
            )
          : !said.library
            ? t("progress.where.no-library", "The library has nothing in this language yet, so there's no ladder of texts to place you on.")
            : t("progress.where.unmeasured", "We'll show which kinds of text you'd follow once we've measured the library's texts.");
      note.hidden = false;
      return;
    }

    var here = typeof said.here === "number" ? ladder[said.here] : null;
    var wording = here ? RUNGS[here.name] || RUNGS[here.kind] : RUNGS[ladder[0].name] || RUNGS[ladder[0].kind];
    head.textContent = here && said.said ? wording[said.said] : wording ? wording.start : "";

    ladder.forEach(function (rung, index) {
      if (index) {
        var gap = el("li", "touch-gap");
        gap.setAttribute("aria-hidden", "true");
        gap.innerHTML =
          '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M6 3.5l4.5 4.5L6 12.5"/></svg>';
        list.appendChild(gap);
      }
      var item = el("li", "touch");
      var link = el("a", "touch-" + rung.state);
      link.href = shelfHref(rung.kind);
      var named_ = (RUNGS[rung.name] || RUNGS[rung.kind] || { chip: rung.kind }).chip;
      if (rung.state === "passed") link.innerHTML = TICK;
      link.appendChild(el("span", "touch-name", named_));
      var shown = (rung.state === "here" || rung.state === "next") && typeof rung.share === "number";
      if (shown) link.appendChild(el("span", "touch-share", t("progress.touch.share", "{n}%", { n: rung.share })));
      if (rung.state === "here") link.setAttribute("aria-current", "step");
      link.title =
        typeof rung.share === "number"
          ? t("progress.touch.title", "{kind}: you know {n}% of the words. Open this shelf in the Library", {
              kind: named_,
              n: rung.share,
            })
          : t("progress.touch.open", "Open this shelf in the Library");
      item.appendChild(link);
      list.appendChild(item);
    });
    list.hidden = false;
  }

  function askStory(code) {
    if (!window.fetch || storyAsked[code]) return;
    storyAsked[code] = true;
    fetch(keyed("/account/story?language=" + encodeURIComponent(code)), { credentials: "same-origin" })
      .then(function (answer) {
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
          drawWhere(code);
          drawNext(code);
        }
      })
      .catch(function () {
        /* nothing to say is a part that says nothing, which is how the page already stood */
      });
  }

  /* --- 2 · how you got here ------------------------------------------------------
   *
   * Time and words (targum-internal#339): the account's reading of its own log, a row a
   * day, language and medium, so they add up across devices. Filtered by period only
   * (§12, 2026-10-09): the three figures already say the medium. A figure that is nought
   * is not drawn, and the part is absent where there is no record at all.
   */
  var spentRows = null;
  var spentPeriod = "30";
  var PERIODS = [
    ["30", t("progress.spent.month", "Last 30 days")],
    ["7", t("progress.spent.week", "Last 7 days")],
    ["", t("progress.spent.ever", "All time")],
  ];

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

  function since(days) {
    var then = new Date();
    then.setDate(then.getDate() - (days - 1));
    var two = function (n) {
      return (n < 10 ? "0" : "") + n;
    };
    return then.getFullYear() + "-" + two(then.getMonth() + 1) + "-" + two(then.getDate());
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

  function drawSpent(code) {
    var panel = document.getElementById("spent");
    var figures = document.getElementById("spent-figures");
    var chips = document.getElementById("spent-period");
    if (!panel || !figures) return;
    // Drawn whenever the record holds anything in this language, and absent where it
    // holds nothing: the board has no waiting state (§12, 2026-10-09).
    panel.hidden = !recorded(code);
    if (panel.hidden) return;
    chips.textContent = "";
    PERIODS.forEach(function (pair) {
      var chip = el("button", "chip", pair[1]);
      chip.type = "button";
      chip.setAttribute("aria-pressed", spentPeriod === pair[0] ? "true" : "false");
      chip.addEventListener("click", function () {
        spentPeriod = pair[0];
        drawSpent(currentCode);
      });
      chips.appendChild(chip);
    });
    var from = spentPeriod ? since(Number(spentPeriod)) : "";
    var sums = { listened: 0, watched: 0, words: 0 };
    spentRows.forEach(function (row) {
      if (row.language && row.language !== code) return;
      if (from && row.day < from) return;
      sums.listened += row.listened || 0;
      sums.watched += row.watched || 0;
      sums.words += row.words || 0;
    });
    figures.textContent = "";
    function figure(amount, label) {
      var one = el("div", "spent-figure");
      one.appendChild(el("span", "spent-amount", amount));
      one.appendChild(el("span", "spent-label", label));
      figures.appendChild(one);
    }
    // The board's three, always: a nought is a figure of the period, not a gap in it.
    figure(grouped(sums.words), tn("progress.spent.words", sums.words, "word read", "words read"));
    if (!SILENT[code]) figure(clock(sums.listened), t("progress.spent.listened", "listened"));
    figure(clock(sums.watched), t("progress.spent.watched", "watched"));
  }

  function askSpent() {
    if (!window.fetch) return;
    fetch(keyed("/account/totals"), { credentials: "same-origin" })
      .then(function (answer) {
        return answer.json();
      })
      .then(function (said) {
        if (!said || !said.signedIn) return;
        if (!said.on) {
          var off = document.getElementById("spent-off");
          if (off) off.hidden = false;
          return;
        }
        // Read wherever there is a record, kept or not kept any more (§12, 2026-10-09).
        spentRows = said.totals && said.totals.length ? said.totals : null;
        if (!spentRows) return;
        drawSpent(currentCode);
        drawLedger(document.getElementById("counts"), data[currentCode], readingDays, currentCode);
      })
      .catch(function () {
        /* no record to read is no figures, which is how the page already stood */
      });
  }

  /* The words taken up, a column a week over the last twelve weeks, from the first week
     with anything in it. "Came to know" is what the board says; nothing records the day a
     word reached known, only the day it was saved, so the chart draws what was kept (§12,
     2026-10-09). Each column is one shade of the stage ramp chosen by its height — lighter
     for fewer, leaf for the most — and there is no legend, as the board draws it. */
  var WEEKS = 12;
  var DAY = 24 * 60 * 60 * 1000;

  function drawWeeks(host, list) {
    host.textContent = "";
    var today = new Date();
    today.setHours(0, 0, 0, 0);
    // Weeks end today, so the last column is the seven days up to now.
    var end = today.getTime() + DAY;
    var start = end - WEEKS * 7 * DAY;
    var columns = [];
    for (var w = 0; w < WEEKS; w++) columns.push({ 1: 0, 2: 0, 3: 0, 9: 0, all: 0 });
    charts.kept(list).forEach(function (word) {
      if (!word.at || word.at < start || word.at >= end) return;
      var at = Math.floor((word.at - start) / (7 * DAY));
      var step = word.status === KNOWN ? KNOWN : word.status;
      if (!columns[at] || columns[at][step] === undefined) return;
      columns[at][step] += 1;
      columns[at].all += 1;
    });
    var most = columns.reduce(function (top, column) {
      return Math.max(top, column.all);
    }, 0);
    if (!most) {
      host.appendChild(el("p", "empty", t("progress.weeks.none", "No words taken up in the last twelve weeks.")));
      return;
    }
    var bars = el("ol", "weeks");
    var total = 0;
    var first = 0;
    while (first < columns.length && !columns[first].all) first += 1;
    columns.forEach(function (column, index) {
      total += column.all;
      if (index < first) return;
      var bar = el("li", "week");
      var from = new Date(start + index * 7 * DAY);
      var label = tn("progress.weeks.week", column.all, "Week of {date}: {n} word", "Week of {date}: {n} words", {
        date: from.toLocaleDateString(words.language || "en", { day: "numeric", month: "short" }),
      });
      bar.title = label;
      bar.setAttribute("aria-label", label);
      var share = column.all / most;
      // A week with nothing in it keeps its place and draws nothing.
      if (!column.all) {
        bars.appendChild(bar);
        return;
      }
      var shade = el("span", "week-bar");
      shade.style.height = Math.round(share * 100) + "%";
      shade.style.background = "var(" + rampFor(share) + ")";
      bar.appendChild(shade);
      bars.appendChild(bar);
    });
    bars.setAttribute("role", "img");
    bars.setAttribute(
      "aria-label",
      tn("progress.weeks.label", total, "{n} word taken up in the last twelve weeks", "{n} words taken up in the last twelve weeks")
    );
    host.appendChild(bars);
  }

  //: The step of the ramp a column of this share of the tallest is drawn in.
  function rampFor(share) {
    if (share >= 0.9) return STEPS[3].slot;
    if (share >= 0.75) return STEPS[2].slot;
    if (share >= 0.6) return STEPS[1].slot;
    return STEPS[0].slot;
  }

  /* --- 3 · what next ------------------------------------------------------------ */

  function meaningOf(code, lemma) {
    var entry = data[code];
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
  }

  function drawNext(code) {
    var said = story[code];
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
    document.getElementById("practise").href = keyed("/words");

    wordsTitle.textContent =
      code === "arc"
        ? t("progress.next.words-arc", "Words you keep meeting, from your Aramaic list (kept apart from your Hebrew one)")
        : t("progress.next.words", "Words you keep meeting and haven't learned");

    var found = (said && said.words) || [];
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
    if (!found.length) {
      metEmpty.textContent =
        signedIn === false
          ? t("progress.next.words-signed-out", "Sign in and we'll find the words you keep meeting.")
          : t("progress.next.words-none", "None yet.");
      metEmpty.hidden = false;
    }

    // A language with no library offers what the reader brought (board ProgressYi).
    var library = !said || said.library !== false;
    textsTitle.textContent = library
      ? t("progress.next.texts", "Texts at your level now")
      : t("progress.next.texts-yours", "The library has nothing in this language yet, so what comes next is what you bring");
    more.textContent = library
      ? t("progress.next.library", "More in the Library") + " →"
      : t("progress.next.uploads", "All your uploads") + " →";
    more.href = keyed(library ? "/library" : "/?show=uploads");

    if (!library) {
      row(level, "+ " + t("progress.next.upload", "Upload something new"), "", t("progress.next.upload-how", "A link, a file, or a photo of a page"), "", keyed("/add"));
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
    if (!texts.length) {
      levelEmpty.textContent =
        signedIn === false
          ? t("progress.next.texts-signed-out", "Sign in and we'll find the texts at your level.")
          : t("progress.next.texts-none", "Nothing is quite at your level yet. The Library's Hard for now shelf has the nearest.");
      levelEmpty.hidden = false;
    }
  }

  /* --- what you knew of what you read (targum-internal#291) -----------------------
   *
   * One line: of the running words in the sections finished each month, the share the
   * reader had marked known on the day they finished each one. Measured on the server
   * when a finished section arrives and kept as it was (`reading` rows), so a word marked
   * today does not reach back and lift August — which is what makes this a record and
   * not a second copy of the known count.
   *
   * It is the one figure on this page that can fall, and it is allowed to: moving from a
   * graded dialogue to Agnon is a drop, and that is the truthful picture. When the latest
   * month is lower, one sentence says why — harder text, not lost ground — and nothing
   * else: no apology, no encouragement. Said as a count in ten, never as a percentage, a
   * level or a score (§6). Under two months there is no line and no part: nothing is
   * said about a chart that is not there. Absent signed out. Drawn as the board draws it
   * (§12, 2026-10-09): the panel's full width, a baseline, the line, a dot a month and
   * each month's name under its dot.
   */
  var readingSeries = null;

  function tenths(point) {
    return Math.max(0, Math.min(10, Math.round((point.known / Math.max(1, point.tokens)) * 10)));
  }

  function monthName(month, withYear) {
    var parts = String(month).split("-");
    var when = new Date(Date.UTC(Number(parts[0]), Number(parts[1]) - 1, 15));
    var options = { month: "long", timeZone: "UTC" };
    if (withYear) options.year = "numeric";
    try {
      return when.toLocaleDateString(words.language || "en", options);
    } catch (e) {
      return month;
    }
  }

  function inTen(point, month) {
    var n = tenths(point);
    if (n >= 10) {
      return t("progress.reading.said-all", "In {month} you knew nearly every word of what you read.", { month: month });
    }
    if (n <= 0) {
      return t("progress.reading.said-none", "In {month} you knew almost none of the words in what you read.", {
        month: month,
      });
    }
    return tn(
      "progress.reading.said",
      n,
      "In {month} you knew about {n} word in 10 of what you read.",
      "In {month} you knew about {n} words in 10 of what you read.",
      { month: month }
    );
  }

  function drawReading(code) {
    if (!readingSeries) return;
    var panel = document.getElementById("reading");
    var host = document.getElementById("reading-line");
    var said = document.getElementById("reading-said");
    if (!panel || !host || !said) return;
    host.textContent = "";
    said.textContent = "";
    var mine = readingSeries[code] || { line: [], months: 0, sections: 0 };
    var points = mine.line || [];
    // Under two months there is nothing to draw, and the part is not there at all
    // rather than a paragraph promising it (David, 2026-10-09: the board has no waiting
    // state, and §6 keeps what has not happened quiet).
    panel.hidden = points.length < 2;
    if (panel.hidden) return;

    var thisYear = new Date().getUTCFullYear();
    var last = points[points.length - 1];
    var before = points[points.length - 2];
    var lastYear = Number(String(last.month).slice(0, 4));
    said.appendChild(el("p", "reading-said", inTen(last, monthName(last.month, lastYear !== thisYear))));
    // Compared as the page says it, in tenths: a line that dipped inside the same count
    // is not a fall anybody was told about, and a sentence about it would be louder than
    // the change.
    if (tenths(last) < tenths(before)) {
      said.appendChild(
        el(
          "p",
          "reading-fell",
          t(
            "progress.reading.fell",
            "It fell because what you read in {month} had more words new to you, not because you lost any.",
            { month: monthName(last.month, lastYear !== thisYear) }
          )
        )
      );
    }

    // The panel's own width in pixels, so the dots stay round and the months stay their
    // size; redrawn on a resize (below).
    var W = Math.max(240, Math.round(host.clientWidth || (host.getBoundingClientRect ? host.getBoundingClientRect().width : 0) || 640));
    var H = 120;
    var pad = { top: 12, right: 20, bottom: 22, left: 20 };
    var plotW = W - pad.left - pad.right;
    var plotH = H - pad.top - pad.bottom;
    function share(point) {
      return point.known / Math.max(1, point.tokens);
    }
    function px(index) {
      return pad.left + (index / (points.length - 1)) * plotW;
    }
    function py(value) {
      return pad.top + plotH - value * plotH;
    }

    var wrap = el("div", "chart");
    var picture = svg("svg", {
      viewBox: "0 0 " + W + " " + H,
      width: W,
      height: H,
      role: "img",
      "aria-label": t("progress.reading.label", "What you knew of what you read, {first} to {last}", {
        first: monthName(points[0].month, true),
        last: monthName(last.month, true),
      }),
    });
    picture.appendChild(svg("line", { class: "reading-base", x1: 0, y1: H - pad.bottom + 2, x2: W, y2: H - pad.bottom + 2 }));

    var line = points
      .map(function (point, index) {
        return (index ? "L" : "M") + px(index) + " " + py(share(point));
      })
      .join(" ");
    // Leaf, one hue, whichever way it goes: §4 gives progress to leaf, and a fall drawn in
    // clay would be the verdict the sentence under it refuses to give.
    picture.appendChild(svg("path", { class: "reading-path", d: line, fill: "none", stroke: "var(--leaf)", "stroke-width": 3 }));

    // Every point carries its month, its count in ten and how many sections are behind
    // it — on the point itself, as a title a screen reader and a long press both reach.
    var dots = [];
    points.forEach(function (point, index) {
      var about = t("progress.reading.point", "{month}: about {n} in 10", {
        month: monthName(point.month, true),
        n: tenths(point),
      });
      var behind = tn("progress.reading.sections", point.sections, "{n} section", "{n} sections");
      var dot = svg("circle", {
        class: "reading-point",
        cx: px(index),
        cy: py(share(point)),
        r: index === points.length - 1 ? 5 : 4,
        fill: "var(--leaf)",
        tabindex: "0",
        "aria-label": about + " · " + behind,
      });
      var title = svg("title", {});
      title.textContent = about + " · " + behind;
      dot.appendChild(title);
      dots.push({ node: dot, about: about, behind: behind });
      picture.appendChild(dot);
    });

    // Each month's name under its dot, the year only where it is not this one.
    var months = svg("g", { class: "axis" });
    points.forEach(function (point, index) {
      var year = Number(String(point.month).slice(0, 4));
      var anchor = index === 0 ? "start" : index === points.length - 1 ? "end" : "middle";
      var name = svg("text", { class: "reading-month", x: px(index), y: H - 4, "text-anchor": anchor });
      name.textContent = monthName(point.month, year !== thisYear);
      months.appendChild(name);
    });
    picture.appendChild(months);

    wrap.appendChild(picture);
    host.appendChild(wrap);
    var tip = tipFor(wrap);

    function point(index) {
      var hostBox = wrap.getBoundingClientRect();
      tip.show(
        dots[index].about + "<br>" + dots[index].behind,
        (px(index) / W) * hostBox.width,
        (py(share(points[index])) / H) * hostBox.height
      );
    }
    function nearest(event) {
      var box = picture.getBoundingClientRect();
      var atX = (event.clientX - box.left) * (W / box.width);
      var index = Math.round(((atX - pad.left) / plotW) * (points.length - 1));
      point(Math.max(0, Math.min(points.length - 1, index)));
    }
    // A mouse finds the nearest month; a thumb taps for it; a keyboard focuses a point.
    picture.addEventListener("mousemove", nearest);
    picture.addEventListener("click", nearest);
    picture.addEventListener("mouseleave", function () {
      tip.hide();
    });
    dots.forEach(function (dot, index) {
      dot.node.addEventListener("focus", function () {
        point(index);
      });
      dot.node.addEventListener("blur", function () {
        tip.hide();
      });
    });
  }

  function askReading() {
    if (!window.fetch) return;
    fetch(keyed("/account/reading"), { credentials: "same-origin" })
      .then(function (answer) {
        return answer.json();
      })
      .then(function (said) {
        if (!said || !said.signedIn) return;
        readingSeries = said.reading || {};
        drawReading(currentCode);
      })
      .catch(function () {
        /* no account to read is no line, which is how the page already stood */
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
    drawSpent(code);
    drawWeeks(document.getElementById("weeks"), data[code].words);
    drawNext(code);
    askStory(code);
  }

  show(currentCode);
  askSpent();
  askReading();

  // If the account turns out to hold words this browser had not seen — kept on a phone,
  // or kept here before signing in on another machine — everything is gathered again
  // and the page redrawn, and the story asked again: the ladder moves with the list.
  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (!changed) return;
      data = collect();
      readingDays = charts.days();
      codes = window.TargumLang.order(Object.keys(data), names);
      document.getElementById("nothing").hidden = codes.length > 0;
      document.getElementById("page").hidden = codes.length === 0;
      if (!codes.length) return;
      if (codes.indexOf(currentCode) < 0) currentCode = window.TargumLang.current(codes);
      storyAsked = {};
      show(currentCode);
    });
    window.TargumSync.start();
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
