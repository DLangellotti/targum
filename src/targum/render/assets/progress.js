/* Everything you have kept, and what it adds up to.
 *
 * Reads the same stores the reader writes — words per language, phrases per text —
 * so this page is a view of them rather than a second copy. Nothing is computed on
 * the server; the server only handed over the page.
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

  var names = window.TARGUM_LANGUAGES || {};
  // The page's words in the reader's language, from `strings.js` (targum-internal#184).
  var words = window.TargumStrings;
  var t = words.t;
  var tn = words.tn;

  var KNOWN = 9;
  var STATUS = {
    1: { name: t("progress.status.1", "just met"), slot: "--step-1" },
    2: { name: t("progress.status.2", "getting there"), slot: "--step-2" },
    3: { name: t("progress.status.3", "nearly there"), slot: "--step-3" },
    9: { name: t("progress.status.9", "known"), slot: "--step-4" },
  };
  // The six real ones. "not rated" was a seventh row that read as a category a word could
  // belong to, and it is not: it is the absence of frequency data for a language, which
  // is a fact about targum rather than about the word or the reader. A word that has one
  // is counted; a word that has none is not placed on a scale it has no reading for.
  var BANDS = ["easy", "fairly easy", "moderate", "hard", "very hard", "extremely hard"];
  // What each is called on the page; the names above are the words' own data.
  var BAND_NAMES = [
    t("progress.band.easy", "easy"),
    t("progress.band.fairly-easy", "fairly easy"),
    t("progress.band.moderate", "moderate"),
    t("progress.band.hard", "hard"),
    t("progress.band.very-hard", "very hard"),
    t("progress.band.extremely-hard", "extremely hard"),
  ];

  /* One bar per band, and each its own colour. A scale rather than six unrelated hues:
     it runs leaf → iris → clay, which is the order §4 already gives them — what you can
     read, what is new to you, what it costs you. Mixed from the three working cuts, so
     nothing here is a colour the palette does not have. Green to purple to red, deliberately: green to red alone mixes to brown in
     the middle, which is the thing this page was getting too much of. */
  var COMMONNESS = [
    "var(--leaf)",
    "color-mix(in srgb, var(--iris) 28%, var(--leaf))",
    "var(--iris)",
    "color-mix(in srgb, var(--clay) 40%, var(--iris))",
    "color-mix(in srgb, var(--clay) 70%, var(--iris))",
    "var(--clay)",
  ];
  /* A sentence with one figure in bold: `{bold}` in the text is where it goes, so a
     language can put it wherever its grammar wants it. */
  function boldIn(host, text, bold) {
    var at = text.indexOf("{bold}");
    if (at < 0) {
      host.textContent = text;
      return;
    }
    host.appendChild(document.createTextNode(text.slice(0, at)));
    host.appendChild(el("b", null, bold));
    host.appendChild(document.createTextNode(text.slice(at + "{bold}".length)));
  }

  function named(code) {
    return names[code] || (code || "").toUpperCase();
  }

  function wireNav() {
    Array.prototype.forEach.call(document.querySelectorAll(".site-nav a"), function (link) {
      link.href = keyed(link.getAttribute("href"));
    });
  }
  wireNav();

  function withKey(href) {
    return href + (href.indexOf("?") === -1 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  /* --- what is in the browser ---------------------------------------------- */

  // The chart kit, the growth line, the tiles and the collector live in charts.js —
  // Learn draws the same numbers, and two copies of a chart drift.
  //
  // Bound here rather than beside the charts further down, because `collect` is called
  // during start-up: `var` hoists the name but not the value, so reading it from a
  // declaration below meant `charts` was undefined and the page threw on load.
  var charts = window.TargumCharts;
  var el = charts.el;
  var svg = charts.svg;
  var tipFor = charts.tipFor;
  var drawGrowth = charts.growth;

  // Words are filed per language; phrases per text, with the text index saying which
  // language each belongs to. Gathered here into one shape per language.
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
    document.getElementById("library-link").href = withKey("/library");
    wireNav();
    // Signing in on a browser that has nothing is the whole point of signing in: this
    // is the new phone, and everything is about to arrive. The page has drawn its empty
    // state and built none of the rest, so it is started again rather than patched up.
    if (window.TargumSync) {
      window.TargumSync.onChange(function (changed) {
        if (changed) location.reload();
      });
      window.TargumSync.start();
    }
    return;
  }

  document.getElementById("page").hidden = false;

  // Which language everything below is drawn for. The switcher moves it.
  var currentCode = window.TargumLang.current(codes);

  /* --- small helpers -------------------------------------------------------- */


  /* --- the charts ----------------------------------------------------------- */

  // Part-to-whole across an ordered scale: one bar, one hue, light to dark, with every
  // segment labelled. Four classes, so direct labels are not optional.
  function drawProgress(host, note, words) {
    host.textContent = "";
    var counts = {};
    charts.kept(words).forEach(function (word) {
      counts[word.status] = (counts[word.status] || 0) + 1;
    });
    var order = [1, 2, 3, KNOWN];
    var segments = order
      .map(function (status) {
        return { status: status, count: counts[status] || 0 };
      })
      .filter(function (segment) {
        return segment.count > 0;
      });
    var total = segments.reduce(function (sum, segment) {
      return sum + segment.count;
    }, 0);

    // Ignored words are not mentioned. Ignore means "this is not vocabulary" — a name, a
    // numeral, a word from another language — and a page that keeps a tally of what you
    // dismissed has not dismissed it.
    note.textContent = "";

    if (!total) {
      host.appendChild(el("p", "empty", t("progress.empty", "Nothing marked yet.")));
      return;
    }

    var wrap = el("div", "chart");
    var height = 34;
    var picture = svg("svg", {
      viewBox: "0 0 100 " + height,
      preserveAspectRatio: "none",
      role: "img",
      height: height,
      "aria-label": t("progress.chart.status", "Your {language} words: {counts}", {
        language: named(currentCode),
        counts: segments
          .map(function (segment) {
            return segment.count + " " + STATUS[segment.status].name;
          })
          .join(", "),
      }),
    });
    picture.style.height = height + "px";

    var tip = null;
    var x = 0;
    segments.forEach(function (segment) {
      var width = (segment.count / total) * 100;
      var rect = svg("rect", {
        x: x,
        y: 0,
        width: width,
        height: height,
        rx: 1,
        fill: "var(" + STATUS[segment.status].slot + ")",
      });
      rect.addEventListener("mousemove", function (event) {
        var box = wrap.getBoundingClientRect();
        tip.show(
          "<b>" +
            segment.count +
            "</b> " +
            STATUS[segment.status].name +
            " · " +
            Math.round((segment.count / total) * 100) +
            "%",
          event.clientX - box.left,
          event.clientY - box.top
        );
      });
      rect.addEventListener("mouseleave", function () {
        tip.hide();
      });
      picture.appendChild(rect);
      x += width;
    });

    wrap.appendChild(picture);
    host.appendChild(wrap);
    tip = tipFor(wrap);

    var legend = el("div", "legend");
    segments.forEach(function (segment) {
      var item = el("span");
      var swatch = el("i");
      swatch.style.background = "var(" + STATUS[segment.status].slot + ")";
      item.appendChild(swatch);
      item.appendChild(el("b", null, grouped(segment.count)));
      item.appendChild(document.createTextNode(" " + STATUS[segment.status].name));
      legend.appendChild(item);
    });
    host.appendChild(legend);
  }

  // One series over time, so an area with no legend: the heading names it.


  // Magnitude across ordered classes: bars, one hue, length carries the number.
  function drawBands(host, words) {
    host.textContent = "";
    var counts = BANDS.map(function () {
      return 0;
    });
    var any = false;
    var kept = charts.kept(words);
    kept.forEach(function (word) {
      var index = BANDS.indexOf(word.band);
      if (index < 0) return;
      counts[index] += 1;
      any = true;
    });
    if (!any) {
      /* Words marked and none of them banded is a language with no frequency list —
         Yiddish, Aramaic — and "Nothing marked yet" told a reader with hundreds marked
         that they had marked nothing (copy audit, 2026-09-28). */
      host.appendChild(
        el(
          "p",
          "empty",
          kept.length
            ? t(
                "progress.bands.no-list",
                "We have no word list for this language, so we can't say how common its words are."
              )
            : t("progress.empty", "Nothing marked yet.")
        )
      );
      return;
    }

    var top = Math.max.apply(null, counts) || 1;
    var rowHeight = 22;
    var W = 320;
    var labelW = 92;
    var H = BANDS.length * rowHeight + 6;

    var wrap = el("div", "chart");
    var picture = svg("svg", {
      viewBox: "0 0 " + W + " " + H,
      role: "img",
      "aria-label": t("progress.chart.bands", "By how common: {counts}", {
        counts: BAND_NAMES.map(function (band, index) {
          return counts[index] + " " + band;
        }).join(", "),
      }),
    });

    var tip = null;
    BANDS.forEach(function (band, index) {
      var y = index * rowHeight + 3;
      // Room for the count after the longest bar: 26 units was two digits' worth, and a
      // four-digit count ran past the card's edge (2026-09-14).
      var width = (counts[index] / top) * (W - labelW - 48);

      var label = svg("text", { x: labelW - 8, y: y + 13, "text-anchor": "end" });
      label.textContent = BAND_NAMES[index];
      picture.appendChild(label);

      var bar = svg("rect", {
        x: labelW,
        y: y + 3,
        width: Math.max(counts[index] ? 2 : 0, width),
        height: rowHeight - 9,
        rx: 3,
        fill: COMMONNESS[index] || "var(--iris)",
      });
      if (counts[index]) {
        bar.addEventListener("mousemove", function (event) {
          var box = wrap.getBoundingClientRect();
          tip.show(
            "<b>" + counts[index] + "</b> " + BAND_NAMES[index],
            event.clientX - box.left,
            event.clientY - box.top
          );
        });
        bar.addEventListener("mouseleave", function () {
          tip.hide();
        });
      }
      picture.appendChild(bar);

      var value = svg("text", {
        x: labelW + Math.max(counts[index] ? 2 : 0, width) + 6,
        y: y + 13,
        class: "value",
      });
      value.textContent = grouped(counts[index]);
      picture.appendChild(value);
    });

    wrap.appendChild(picture);
    host.appendChild(wrap);
    tip = tipFor(wrap);
  }

  /* --- the tiles ------------------------------------------------------------ */



  /* --- what you have built ----------------------------------------------------
   *
   * The ledger, the milestones and the days. Real counts of real things, in the reading
   * face with tabular figures — a ledger rather than a score. Nothing here is invented:
   * every number is something the reader did, and there is no currency to inflate.
   */

  // Words known, and the thresholds worth saying so about. Known only — the learning
  // ladder is deliberately out, because a word somebody is halfway through is a word the
  // page still costs them.
  var MARKS = [10, 50, 100, 250, 500, 1000, 2500, 5000];

  // 1,000 rather than 1000. The counts are the point of the page and they get read.
  function grouped(count) {
    return String(count).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  // Everything the page counts, in one block. They were a row of tiles under this one,
  // which meant a reader read the same words twice on the way down the page in two
  // different shapes — and read "phrases saved" twice, in both.
  function drawLedger(counts, standing, entry, days, code) {
    counts.textContent = "";
    standing.textContent = "";
    var sums = charts.totals(entry);

    /* `hue` is the one thing this block is allowed that the rest of the page is not:
       §9 makes the inverted surface the only place the bright set is legal, and §4 says
       which is which — leaf for what has been reached, iris for phrases, sun for turning
       up. Everything without one stays paper-white. */
    function count(value, label, hue, title) {
      // A zero is not a peak moment. The bright set is for what happened, and spending
      // --sun on "0 words learned" paints the loudest colour in the system on the one
      // line that has nothing to report; §6 keeps what has not happened quiet.
      var box = el("div", hue && value ? "lit " + hue : null);
      box.appendChild(el("b", null, grouped(value)));
      // Singular where there is one of it. These sit at display size beside the figure
      // they belong to, which is where "1 words learned" is impossible not to read.
      box.appendChild(el("span", null, label));
      if (title) box.title = title;
      counts.appendChild(box);
    }

    /* Four, and each one a thing a reader would say out loud about their own reading.
       Seven included every number this page could work out — words saved beside words
       known beside words learned, and a count of texts opened, which is a fact about
       browsing rather than about Hebrew. */
    // A figure and its name, and nothing under either. "80% of the way" was a share of
    // known against still-learning — a fraction whose denominator is however many words
    // happen to be part-way up the ladder, so it fell when a reader saved a new word and
    // rose when they gave up on one. A number that moves the wrong way is worse company
    // than no number.
    // Everything kept, and then the half of it that has been finished with. "Known" on
    // its own read as a claim about the reader; "marked known" is what actually happened,
    // which is that they pressed a key while reading.
    count(sums.saved, tn("progress.count.saved", sums.saved, "word on your list", "words on your list"));
    count(
      sums.known,
      tn("progress.count.known", sums.known, "word marked known", "words marked known"),
      "leaf"
    );
    // What targum carried up to known, rather than what a reader arrived already having.
    // "Learned" alone read as contradicting the known count beside it (2026-09-14): it
    // is the part of that count that started lower on the ladder and was read up to known.
    count(
      sums.learned,
      tn("progress.count.learned", sums.learned, "word learned on targum", "words learned on targum"),
      "sun",
      t("progress.count.learned.title", "Saved as new and since marked known.")
    );
    count(sums.phrases, tn("progress.count.phrases", sums.phrases, "phrase saved", "phrases saved"), "iris");
    // Said finished, at the foot of the text, by the reader. A real count of a real
    // thing, and the one on this page that is a whole text rather than a word.
    count(sums.finished, tn("progress.count.finished", sums.finished, "targum finished", "targums finished"), "leaf");
    count(days.length, tn("progress.count.days", days.length, "day on targum", "days on targum"));
    // The longest run of days there has ever been, and never the current one. Decided
    // 2026-09-03 (targum-internal#175) and recorded in design.md §12: a current streak
    // is a count that can be destroyed, and that is what makes people quit in the week
    // they break a long one; the longest can be tied or beaten and never lost, which is
    // the property every other figure in this block has. Sun is the streak's hue (§4),
    // legal here because this block is the inverted surface. It rises on /progress
    // quietly; the day it rises, the foot of the section that did it says so.
    var longest = charts.longest(days);
    count(
      longest,
      tn("progress.count.longest", longest, "day in your longest run", "days in your longest run"),
      "sun"
    );

    drawStanding(standing, entry, code, sums.known);
  }

  // What the block is about: the rung reached and the distance to the next. One hue in
  // here, and it is leaf — §4 gives achievement to leaf, and a rung reached is one.
  //
  // Hebrew gets ulpan levels, which is a ladder with real names outside targum. Every
  // other language keeps the count of words known, because there is no such ladder to
  // put a Russian reader on and inventing one would be a score with a letter on it.
  function drawStanding(standing, entry, code, known) {
    var basis = document.getElementById("basis");
    var rung = document.getElementById("rung");
    var inside = document.getElementById("rung-standing");
    standing.textContent = "";
    inside.textContent = "";

    // A language with a ladder has a block of its own under the milestones: the ulpan
    // for Hebrew, the CEFR for French, Russian and Italian (2026-09-13). A language with
    // none — Yiddish, Aramaic — keeps the milestones as its standing, and says why.
    var ladder = charts.ladderFor(code);
    var title = document.getElementById("rung-title");
    rung.hidden = !ladder;
    basis.hidden = !ladder;
    if (ladder) {
      if (title) title.textContent = ladder.title;
      // What the ladder is, then its limit (David, 2026-09-28, COPY_QUESTIONS 29): a
      // newcomer meets "ב+" or "A2" here with nothing to say which end is the start.
      basis.textContent =
        code === "he"
          ? t("progress.basis.ulpan", "Ulpan classes in Israel run from aleph, for beginners, to vav. A guide, not a placement.")
          : t("progress.basis.cefr", "The European scale runs from A1, for beginners, to C2. A guide, not a placement.");
      drawLevel(inside, entry.words, ladder);
      return;
    }

    var passed = null;
    var next = null;
    MARKS.forEach(function (mark) {
      if (known >= mark) passed = mark;
      else if (next === null) next = mark;
    });

    if (passed) {
      standing.appendChild(
        el(
          "span",
          "reached",
          tn("progress.milestone.reached", passed, "{n} word known", "{n} words known", { n: grouped(passed) })
        )
      );
    }
    // Said once, beside the milestones that stand in for a level.
    standing.appendChild(
      el(
        "p",
        "why",
        t(
          "progress.milestone.why",
          "There's no level for this language yet: we have no word list to measure it against."
        )
      )
    );

    var line = el("p", "next");
    if (next === null) {
      line.textContent = t("progress.milestone.past", "You're past every milestone we keep.");
    } else if (known === 0) {
      line.textContent = t("progress.milestone.start", "Mark a word as known and your count starts here.");
    } else {
      boldIn(
        line,
        tn("progress.milestone.next", next - known, "Another {bold} known word to reach {next}.", "Another {bold} known words to reach {next}.", {
          next: grouped(next),
        }),
        grouped(next - known)
      );
    }
    standing.appendChild(line);
  }

  /* --- how far into Hebrew ---------------------------------------------------
   *
   * The ladder itself — the rungs, the band weighting, and what a reader's marked words
   * add up to — moved into the chart kit, because Learn needs it too: it opens the
   * weekly at the reader's own rung, and a second copy of a weighting is two pages
   * disagreeing about the same person. `charts.ULPAN`, `charts.reach`,
   * `charts.standingIn`.
   */

  function drawLevel(host, words, ladder) {
    ladder = ladder || charts.ladderFor("he");
    var got = charts.reach(words);
    var weighted = ladder.measure === "weighted";
    var value = weighted ? got.weighted : charts.common(words);
    var found = charts.standingIn(value, ladder.rungs);

    // The rung takes the celebration chip §9 allows one of per screen. Hebrew and Latin
    // at the same size inside it, because §3 does not let Hebrew be the small half.
    if (found.here) {
      var chip = el("span", "reached");
      if (weighted) {
        var letter = el("bdi", "letter", found.here.letter);
        // Said outright rather than left to the first strong character. Left to right,
        // because the name it stands beside is English and the pair reads as one label —
        // under rtl the plus went to the far side and "א+" came out as "+א".
        letter.setAttribute("dir", "ltr");
        letter.setAttribute("lang", "he");
        chip.appendChild(letter);
        chip.appendChild(el("span", "name", found.here.name));
        // The CEFR equivalent beside the ulpan name, so one scale reads across languages.
        if (found.here.cefr) {
          chip.appendChild(
            el("span", "cefr", " · " + t("progress.level.about", "about {level}", { level: found.here.cefr }))
          );
        }
      } else {
        chip.appendChild(el("span", "name", found.here.name));
      }
      host.appendChild(chip);
    }

    var line = el("p", "next");
    if (!got.words) {
      line.textContent = t("progress.level.start", "Mark a word as known and your level starts here.");
    } else if (!found.next) {
      line.textContent = weighted
        ? t("progress.level.past-ulpan", "You're past every rung an ulpan keeps.")
        : t("progress.level.past-cefr", "You're past every CEFR level.");
    } else {
      // In words either way, because words are what the reader has. The ulpan's total is
      // weighted, so it is turned back into words at the weight of the ones this reader
      // knows; counting a point is inventing a currency. The CEFR counts words already.
      var more = weighted
        ? Math.max(1, Math.round((found.next.at - got.weighted) / (got.weighted / got.words)))
        : Math.max(1, found.next.at - value);
      boldIn(
        line,
        weighted
          ? tn("progress.level.next-ulpan", more, "Another {bold} word to {letter} ({name}).", "Another {bold} words to {letter} ({name}).", {
              letter: found.next.letter,
              name: found.next.name,
            })
          : tn("progress.level.next-cefr", more, "Another {bold} common word to {name}.", "Another {bold} common words to {name}.", {
              name: found.next.name,
            }),
        grouped(more)
      );
    }
    host.appendChild(line);
  }

  function drawMarks(host, words) {
    host.textContent = "";
    var known = charts.known(words);
    var marks = el("div", "marks");
    MARKS.forEach(function (mark) {
      var chip = el("span", "mark" + (known >= mark ? " on" : ""), grouped(mark));
      chip.setAttribute("title", known >= mark ? t("progress.mark.reached", "Reached") : t("progress.mark.not-yet", "Not yet"));
      marks.appendChild(chip);
    });
    host.appendChild(marks);
  }

  // Twelve weeks, a column a week, ending today. Squares rather than a line because the
  // question is which days rather than how many at once, and a day nobody read is the
  // resting colour: §6 asks for missed days quiet, never red.
  var WEEKS = 12;

  function dayName(when) {
    return (
      when.getFullYear() +
      "-" +
      String(when.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(when.getDate()).padStart(2, "0")
    );
  }

  /* The strip is twelve weeks of squares, one a day, and the colour says how much
     vocabulary was marked that day — the about page's calendar arithmetic, run on the
     browser's own words rather than on commits (`charts.shade`, `builder.level`).
     Before this it was a two-state strip: read or not. A day you opened a text and
     marked nothing still counts as read and gets the faintest green, because the
     square is about showing up and the shade is about how much. */
  function drawDays(host, days, words) {
    host.textContent = "";
    var had = {};
    days.forEach(function (day) {
      had[day] = true;
    });
    var marked = charts.buckets(words);

    var strip = el("ul", "strip");
    var cursor = new Date();
    cursor.setHours(0, 0, 0, 0);
    // Stepped with the calendar rather than by adding milliseconds: on the two days a
    // year the clocks move, a fixed-size step lands an hour off and never matches a
    // local midnight again — the same bug the growth line already had once.
    cursor.setDate(cursor.getDate() - (WEEKS * 7 - 1));
    /* The busiest day inside the window, not of all time: a strip scaled to a
       first-week binge would read as twelve flat weeks forever after. */
    var window_ = [];
    var scan = new Date(cursor.getTime());
    for (var w = 0; w < WEEKS * 7; w++) {
      window_.push(marked[charts.dayOf(scan.getTime())] || 0);
      scan.setDate(scan.getDate() + 1);
    }
    var busiest = window_.reduce(function (most, n) {
      return n > most ? n : most;
    }, 0);

    var counted = 0;
    for (var i = 0; i < WEEKS * 7; i++) {
      var name = dayName(cursor);
      var count = window_[i];
      // A day with words but no opening still counts as read: marking a word is
      // reading, and a green square with no `read` behind it would be a day the
      // legend cannot explain.
      var read = had[name] || count > 0;
      var box = el("li", read ? "read level-" + Math.max(1, charts.shade(count, busiest)) : "");
      box.setAttribute(
        "title",
        count ? name + " — " + tn("progress.days.words", count, "{n} word", "{n} words") : name
      );
      if (read) counted += 1;
      strip.appendChild(box);
      cursor.setDate(cursor.getDate() + 1);
    }
    strip.setAttribute("role", "img");
    strip.setAttribute(
      "aria-label",
      counted
        ? tn(
            "progress.days.reading",
            counted,
            "{n} day on targum in the last twelve weeks",
            "{n} days on targum in the last twelve weeks"
          )
        : t("progress.days.none", "No days on targum in the last twelve weeks")
    );
    host.appendChild(strip);

    var said = el("p", "legend-days");
    if (!days.length) said.textContent = t("progress.days.first", "Open something and today is your first.");
    else {
      said.textContent = tn(
        "progress.days.counted",
        counted,
        "{n} day in the last twelve weeks.",
        "{n} days in the last twelve weeks."
      );
    }
    host.appendChild(said);
  }

  /* --- putting it together --------------------------------------------------- */

  /* --- time and words (targum-internal#339) ---------------------------------------
   *
   * "Track hours and minutes listened and watched, and words read; displayed and
   * filterable on Progress." These are the account's reading of its own log
   * (`/account/totals`, targum-internal#127), a row a day, language and medium — so they
   * add up across devices, which a tally kept in this browser never could.
   *
   * Filtered by what the reader was doing and by when; the language is the page's own.
   * A figure that is nought is not drawn ("a zero is worth suppressing rather than
   * colouring"), and the panel is absent where there is no record at all.
   */
  var spentRows = null;
  var spentView = { medium: "", period: "" };
  var MEDIA = [
    ["", t("progress.spent.all", "Everything")],
    ["read", t("progress.spent.reading", "Reading")],
    ["listen", t("progress.spent.listening", "Listening")],
    ["watch", t("progress.spent.watching", "Watching")],
  ];
  var PERIODS = [
    ["", t("progress.spent.ever", "All time")],
    ["30", t("progress.spent.month", "Last 30 days")],
    ["7", t("progress.spent.week", "Last 7 days")],
  ];

  function clock(seconds) {
    var minutes = Math.round(seconds / 60);
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

  function spentChips(host, options, field) {
    if (!host) return;
    host.textContent = "";
    options.forEach(function (pair) {
      var chip = el("button", "chip", pair[1]);
      chip.type = "button";
      chip.setAttribute("aria-pressed", spentView[field] === pair[0] ? "true" : "false");
      chip.addEventListener("click", function () {
        spentView[field] = pair[0];
        drawSpent(currentCode);
      });
      host.appendChild(chip);
    });
  }

  function drawSpent(code) {
    var panel = document.getElementById("spent");
    var figures = document.getElementById("spent-figures");
    if (!panel || !figures || !spentRows) return;
    panel.hidden = false;
    spentChips(document.getElementById("spent-medium"), MEDIA, "medium");
    spentChips(document.getElementById("spent-period"), PERIODS, "period");
    var from = spentView.period ? since(Number(spentView.period)) : "";
    var sums = { listened: 0, watched: 0, words: 0 };
    spentRows.forEach(function (row) {
      if (row.language && row.language !== code) return;
      if (spentView.medium && row.medium !== spentView.medium) return;
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
    if (sums.listened) figure(clock(sums.listened), t("progress.spent.listened", "listened"));
    if (sums.watched) figure(clock(sums.watched), t("progress.spent.watched", "watched"));
    if (sums.words) {
      figure(
        sums.words.toLocaleString(),
        tn("progress.spent.words", sums.words, "word read", "words read")
      );
    }
    if (!figures.children.length) {
      figures.appendChild(el("p", "note", t("progress.spent.nothing", "Nothing recorded for this choice yet.")));
    }
  }

  function askSpent() {
    if (!window.fetch) return;
    fetch(keyed("/account/totals"), { credentials: "same-origin" })
      .then(function (answer) {
        return answer.json();
      })
      .then(function (said) {
        if (!said || !said.signedIn || !said.kept) return;
        if (!said.on) {
          var off = document.getElementById("spent-off");
          if (off) off.hidden = false;
          return;
        }
        spentRows = said.totals || [];
        drawSpent(currentCode);
      })
      .catch(function () {
        /* no record to read is no panel, which is how the page already stood */
      });
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
   * else: no apology, no encouragement. Said as a count in ten, the way the quote says
   * it, never as a percentage, a level or a score (§6). Under three months there is no
   * line, and the page says what would draw one. Absent signed out, like Time and words.
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
    panel.hidden = false;
    host.textContent = "";
    said.textContent = "";
    var mine = readingSeries[code] || { line: [], months: 0, sections: 0 };
    var points = mine.line || [];
    if (points.length < 3) {
      said.appendChild(
        el(
          "p",
          "reading-waiting",
          mine.months
            ? t(
                "progress.reading.so-far",
                "We'll draw this once you've finished sections in three different months. Months so far: {n}.",
                { n: mine.months }
              )
            : t("progress.reading.waiting", "We'll draw this once you've finished sections in three different months.")
        )
      );
      return;
    }

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

    var W = 320;
    var H = 150;
    var pad = { top: 10, right: 10, bottom: 22, left: 44 };
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
      role: "img",
      "aria-label": t("progress.reading.label", "What you knew of what you read, {first} to {last}", {
        first: monthName(points[0].month, true),
        last: monthName(last.month, true),
      }),
    });
    var grid = svg("g", { class: "grid" });
    [0, 5, 10].forEach(function (n) {
      grid.appendChild(svg("line", { x1: pad.left, y1: py(n / 10), x2: W - pad.right, y2: py(n / 10) }));
      var tick = svg("text", { x: pad.left - 6, y: py(n / 10) + 3, "text-anchor": "end" });
      tick.textContent = t("progress.reading.tick", "{n} in 10", { n: n });
      grid.appendChild(tick);
    });
    picture.appendChild(grid);

    var line = points
      .map(function (point, index) {
        return (index ? "L" : "M") + px(index) + " " + py(share(point));
      })
      .join(" ");
    // Leaf, one hue, whichever way it goes: §4 gives progress to leaf, and a fall drawn in
    // clay would be the verdict the sentence under it refuses to give.
    picture.appendChild(svg("path", { class: "reading-path", d: line, fill: "none", stroke: "var(--leaf)", "stroke-width": 2 }));

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
        r: 4,
        fill: "var(--leaf)",
        stroke: "var(--paper)",
        "stroke-width": 2,
        tabindex: "0",
        "aria-label": about + " · " + behind,
      });
      var title = svg("title", {});
      title.textContent = about + " · " + behind;
      dot.appendChild(title);
      dots.push({ node: dot, about: about, behind: behind });
      picture.appendChild(dot);
    });

    var ends = svg("g", { class: "axis" });
    var first = svg("text", { x: pad.left, y: H - 6 });
    first.textContent = monthName(points[0].month, true);
    var end = svg("text", { x: W - pad.right, y: H - 6, "text-anchor": "end" });
    end.textContent = monthName(last.month, true);
    ends.appendChild(first);
    ends.appendChild(end);
    picture.appendChild(ends);

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
        /* no account to read is no panel, which is how the page already stood */
      });
  }

  function show(code) {
    currentCode = code;
    // A language the reader learns and has kept nothing in yet is a page this can be:
    // chosen in the menu, it is drawn empty rather than thrown on.
    if (!data[code]) data[code] = { code: code, words: [], phrases: [], texts: 0, finished: 0 };
    window.TargumLang.set(code);
    window.TargumLang.switcher(document.getElementById("langs"), codes, names, code, show);
    // The Tanakh map is Hebrew's, and hides under any other language (§13).
    var tanakhDoor = document.getElementById("tanakh-door");
    if (tanakhDoor) tanakhDoor.hidden = code !== "he";
    var betaNote = document.getElementById("beta-note");
    betaNote.hidden = !window.TargumLang.beta(code);
    if (!betaNote.hidden) betaNote.textContent = window.TargumLang.betaNote(code, names);
    drawLedger(
      document.getElementById("counts"),
      document.getElementById("standing"),
      data[code],
      readingDays,
      code
    );
    drawMarks(document.getElementById("milestones"), data[code].words);
    drawDays(document.getElementById("days"), readingDays, data[code].words);
    drawProgress(
      document.getElementById("progress"),
      document.getElementById("progress-note"),
      data[code].words
    );
    drawGrowth(document.getElementById("growth"), data[code].words);
    drawBands(document.getElementById("bands"), data[code].words);
    drawSpent(code);
    drawReading(code);
  }

  show(currentCode);
  askSpent();
  askReading();

  // If the account turns out to hold words this browser had not seen — kept on a phone,
  // or kept here before signing in on another machine — everything is gathered again
  // and the page redrawn. Cheaper than it looks: `collect()` reads localStorage, and it
  // only runs when something actually arrived.
  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (!changed) return;
      data = collect();
      readingDays = charts.days();
      codes = window.TargumLang.order(Object.keys(data), names);
      // Down to nothing is a state this page has to be able to reach, not just start
      // in: taking the last word off the list on another device has to empty this one
      // too, rather than leave the table it drew a moment ago standing.
      document.getElementById("nothing").hidden = codes.length > 0;
      document.getElementById("page").hidden = codes.length === 0;
      if (!codes.length) return;
      if (codes.indexOf(currentCode) < 0) currentCode = window.TargumLang.current(codes);
      show(currentCode);
    });
    window.TargumSync.start();
  }

  // The charts are drawn to a viewBox, but the tooltip is placed in page pixels.
  var redrawing = null;
  window.addEventListener("resize", function () {
    clearTimeout(redrawing);
    redrawing = setTimeout(function () {
      show(currentCode);
    }, 150);
  });
})();
