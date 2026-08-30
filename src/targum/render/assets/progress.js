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

  var KNOWN = 9;
  var STATUS = {
    1: { name: "just met", slot: "--step-1" },
    2: { name: "getting there", slot: "--step-2" },
    3: { name: "nearly there", slot: "--step-3" },
    9: { name: "known", slot: "--step-4" },
  };
  // The six real ones. "not rated" was a seventh row that read as a category a word could
  // belong to, and it is not: it is the absence of frequency data for a language, which
  // is a fact about targum rather than about the word or the reader. A word that has one
  // is counted; a word that has none is not placed on a scale it has no reading for.
  var BANDS = ["easy", "fairly easy", "moderate", "hard", "very hard", "extremely hard"];

  /* One bar per band, and each its own colour. A scale rather than six unrelated hues:
     it runs leaf → iris → clay, which is the order §4 already gives them — what you can
     read, what is new to you, what it costs you. Mixed from the three working cuts, so
     nothing here is a colour the palette does not have and every step flips with the
     theme. Green to purple to red, deliberately: green to red alone mixes to brown in
     the middle, which is the thing this page was getting too much of. */
  var COMMONNESS = [
    "var(--leaf)",
    "color-mix(in srgb, var(--iris) 28%, var(--leaf))",
    "var(--iris)",
    "color-mix(in srgb, var(--clay) 40%, var(--iris))",
    "color-mix(in srgb, var(--clay) 70%, var(--iris))",
    "var(--clay)",
  ];
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
  var plural = charts.plural;
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
    words.forEach(function (word) {
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
      host.appendChild(el("p", "empty", "Nothing marked yet."));
      return;
    }

    var wrap = el("div", "chart");
    var height = 34;
    var picture = svg("svg", {
      viewBox: "0 0 100 " + height,
      preserveAspectRatio: "none",
      role: "img",
      height: height,
      "aria-label":
        "Your " +
        named(currentCode) +
        " words: " +
        segments
          .map(function (segment) {
            return segment.count + " " + STATUS[segment.status].name;
          })
          .join(", "),
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
      item.appendChild(el("b", null, String(segment.count)));
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
    charts.kept(words).forEach(function (word) {
      var index = BANDS.indexOf(word.band);
      if (index < 0) return;
      counts[index] += 1;
      any = true;
    });
    if (!any) {
      host.appendChild(el("p", "empty", "Nothing marked yet."));
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
      "aria-label":
        "By how common: " +
        BANDS.map(function (band, index) {
          return counts[index] + " " + band;
        }).join(", "),
    });

    var tip = null;
    BANDS.forEach(function (band, index) {
      var y = index * rowHeight + 3;
      var width = (counts[index] / top) * (W - labelW - 26);

      var label = svg("text", { x: labelW - 8, y: y + 13, "text-anchor": "end" });
      label.textContent = band;
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
            "<b>" + counts[index] + "</b> " + band,
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
      value.textContent = String(counts[index]);
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
    function count(value, label, hue) {
      // A zero is not a peak moment. The bright set is for what happened, and spending
      // --sun on "0 words learned" paints the loudest colour in the system on the one
      // line that has nothing to report; §6 keeps what has not happened quiet.
      var box = el("div", hue && value ? "lit " + hue : null);
      box.appendChild(el("b", null, grouped(value)));
      // Singular where there is one of it. These sit at display size beside the figure
      // they belong to, which is where "1 words learned" is impossible not to read.
      box.appendChild(el("span", null, label));
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
    count(sums.saved, sums.saved === 1 ? "word saved" : "words saved");
    count(
      sums.known,
      sums.known === 1 ? "word marked known" : "words marked known",
      "leaf"
    );
    // What targum carried up to known, rather than what a reader arrived already having.
    count(sums.learned, sums.learned === 1 ? "word learned" : "words learned", "sun");
    count(sums.phrases, sums.phrases === 1 ? "phrase saved" : "phrases saved", "iris");
    // Said finished, at the foot of the text, by the reader. A real count of a real
    // thing, and the one on this page that is a whole text rather than a word.
    count(sums.finished, sums.finished === 1 ? "targum finished" : "targums finished", "leaf");
    count(days.length, days.length === 1 ? "day reading" : "days reading");

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

    // Hebrew's ladder is a block of its own, under the milestones. Every other language
    // has no such ladder, so the milestones themselves are the standing and the line
    // goes under the chips it belongs to.
    rung.hidden = code !== "he";
    basis.hidden = code !== "he";
    if (code === "he") {
      // The limit is all that is said (§6, and the 2026-08-24 amendment in §12).
      basis.textContent = "A guide, not a placement.";
      drawLevel(inside, entry.words);
      return;
    }

    var passed = null;
    var next = null;
    MARKS.forEach(function (mark) {
      if (known >= mark) passed = mark;
      else if (next === null) next = mark;
    });

    if (passed) standing.appendChild(el("span", "reached", grouped(passed) + " words known"));

    var line = el("p", "next");
    if (next === null) {
      line.textContent = "Past every milestone targum keeps.";
    } else if (known === 0) {
      line.textContent = "Mark a word while reading and it starts here.";
    } else {
      line.appendChild(document.createTextNode("Another "));
      line.appendChild(el("b", null, grouped(next - known)));
      line.appendChild(document.createTextNode(" to " + grouped(next) + "."));
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

  function drawLevel(host, words) {
    var got = charts.reach(words);
    var found = charts.standingIn(got.weighted);

    // The rung takes the celebration chip §9 allows one of per screen. Hebrew and Latin
    // at the same size inside it, because §3 does not let Hebrew be the small half.
    if (found.here) {
      var chip = el("span", "reached");
      var letter = el("bdi", "letter", found.here.letter);
      // Said outright rather than left to the first strong character. Left to right,
      // because the name it stands beside is English and the pair reads as one label —
      // under rtl the plus went to the far side and "א+" came out as "+א".
      letter.setAttribute("dir", "ltr");
      letter.setAttribute("lang", "he");
      chip.appendChild(letter);
      chip.appendChild(el("span", "name", found.here.name));
      host.appendChild(chip);
    }

    var line = el("p", "next");
    if (!got.words) {
      line.textContent = "Mark a word as known and this starts.";
    } else if (!found.next) {
      line.textContent = "Past every rung an ulpan keeps.";
    } else {
      // Turned back into words at the weight of the ones this reader actually knows, so
      // the figure is words rather than a score. Counting a point is inventing a
      // currency; counting words is counting what is there.
      var each = got.weighted / got.words;
      var more = Math.max(1, Math.round((found.next.at - got.weighted) / each));
      line.appendChild(document.createTextNode("Another "));
      line.appendChild(el("b", null, grouped(more)));
      line.appendChild(
        document.createTextNode(
          " words to " + found.next.letter + " (" + found.next.name + ")."
        )
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
      chip.setAttribute("title", known >= mark ? "Reached" : "Not yet");
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

  function drawDays(host, days) {
    host.textContent = "";
    var had = {};
    days.forEach(function (day) {
      had[day] = true;
    });

    var strip = el("ul", "strip");
    var cursor = new Date();
    cursor.setHours(0, 0, 0, 0);
    // Stepped with the calendar rather than by adding milliseconds: on the two days a
    // year the clocks move, a fixed-size step lands an hour off and never matches a
    // local midnight again — the same bug the growth line already had once.
    cursor.setDate(cursor.getDate() - (WEEKS * 7 - 1));
    var counted = 0;
    for (var i = 0; i < WEEKS * 7; i++) {
      var name = dayName(cursor);
      var box = el("li", had[name] ? "read" : "");
      box.setAttribute("title", name);
      if (had[name]) counted += 1;
      strip.appendChild(box);
      cursor.setDate(cursor.getDate() + 1);
    }
    strip.setAttribute("role", "img");
    strip.setAttribute(
      "aria-label",
      counted
        ? plural(counted, "day") + " reading in the last twelve weeks"
        : "No reading days in the last twelve weeks yet"
    );
    host.appendChild(strip);

    var said = el("p", "legend-days");
    if (!days.length) said.textContent = "Today is the first.";
    else said.textContent = plural(counted, "day") + " in the last twelve weeks.";
    host.appendChild(said);
  }

  /* --- putting it together --------------------------------------------------- */

  function show(code) {
    currentCode = code;
    window.TargumLang.set(code);
    window.TargumLang.switcher(document.getElementById("langs"), codes, names, code, show);
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
    drawDays(document.getElementById("days"), readingDays);
    drawProgress(
      document.getElementById("progress"),
      document.getElementById("progress-note"),
      data[code].words
    );
    drawGrowth(document.getElementById("growth"), data[code].words);
    drawBands(document.getElementById("bands"), data[code].words);
  }

  show(currentCode);

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
