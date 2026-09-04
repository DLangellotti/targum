/* The chart kit, the tiles and the growth line.
 *
 * Shared because two pages want them, and a second copy would drift: the words page shows
 * them as part of a working surface, Learn shows the same numbers as a glance. One
 * definition, drawn twice.
 *
 * Everything here reads the browser's own stores. Nothing is computed on the server and
 * nothing new is tracked to make it possible.
 */
(function () {
  "use strict";

  // Legacy records imported by the vocab migration carry `at: 0`; this keeps them out of
  // anything dated rather than putting the whole library on the first day of 2024.
  // A day, in milliseconds. It lived in words.js and was used from here: when the chart
  // kit moved out, the constant it draws with stayed behind, and `drawGrowth` threw
  // `DAY is not defined` on any page with words on it.
  var DAY = 86400000;

  // The status a word reaches when it is finished with. Its own, like every other IIFE
  // that needs it — reader.js and words.js each declare it too. It was being read from
  // words.js across a scope boundary, which threw the moment a tile was counted.
  var KNOWN = 9;
  var IGNORED = 0;

  // A name or a number, marked while reading. The reader records what it was as the
  // band, and nothing that counts vocabulary counts it: knowing that אחשורוש is a king
  // is not knowing a word of Hebrew.
  var NOT_VOCABULARY = { name: true, number: true };

  function vocabulary(words) {
    return (words || []).filter(function (word) {
      return !NOT_VOCABULARY[word.band];
    });
  }

  // Ignore means "this is not vocabulary" — a name, a numeral, a word from another
  // language. A word you ignored is not a word you kept, so nothing that counts what you
  // have counts it and nothing that draws it draws it. Dismissing something and then
  // being shown a tally of it is not dismissing it.
  //
  // A name the reader marked known rather than ignored is the same thing by a different
  // key, so it is not kept either. The rule was applied piecemeal — the milestones, the
  // ladder and Learn's headline each filtered for themselves, while the ledger, the
  // growth line, the day strip and the status bar drew from this and took the names —
  // so one page said 1,285 words known at the top and 1,439 in the block under it. One
  // filter, here, and every count on every page moves by it.
  function kept(words) {
    return vocabulary(words).filter(function (word) {
      return word.status !== IGNORED;
    });
  }

  var EARLIEST = Date.UTC(2024, 0, 1);

  var STATUS = {
    1: { name: "just met", slot: "--step-1" },
    2: { name: "getting there", slot: "--step-2" },
    3: { name: "nearly there", slot: "--step-3" },
    9: { name: "known", slot: "--step-4" },
  };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function svg(tag, attrs) {
    var node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (name) {
      node.setAttribute(name, attrs[name]);
    });
    return node;
  }

  function plural(count, one) {
    return count + " " + (count === 1 ? one : one + "s");
  }

  function shortDate(stamp) {
    var d = new Date(stamp);
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }

  function dayOf(stamp) {
    var d = new Date(stamp);
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  }

  /* How many words were marked on each local day, keyed by that day's midnight. The
     growth line walks it as a running total and the day strip colours one square per
     key; both want the same buckets and a second copy would drift the day boundary.
     Undated legacy records are dropped rather than piled onto the first day of 2024. */
  function buckets(words) {
    var out = {};
    kept(words || []).forEach(function (word) {
      if (!(word.at > EARLIEST)) return;
      var day = dayOf(word.at);
      out[day] = (out[day] || 0) + 1;
    });
    return out;
  }

  /* Which of five shades a day gets, the same arithmetic the about page's calendar
     runs in Python (`builder.level`). Zero stays zero rather than rounding up: a day
     nothing happened on is grey, and the faintest green has to mean something. */
  function shade(count, busiest) {
    if (!count || !busiest) return 0;
    return Math.min(4, 1 + Math.floor((3 * (count - 1)) / Math.max(1, busiest - 1)));
  }

  // Tooltips are positioned against the chart box, so every chart gets one of its own.
  function tipFor(host) {
    var tip = el("div", "tip");
    tip.hidden = true;
    host.appendChild(tip);
    return {
      show: function (html, x, y) {
        tip.innerHTML = html;
        tip.hidden = false;
        var box = host.getBoundingClientRect();
        var own = tip.getBoundingClientRect();
        var left = Math.max(0, Math.min(box.width - own.width, x - own.width / 2));
        tip.style.left = left + "px";
        tip.style.top = Math.max(0, y - own.height - 10) + "px";
      },
      hide: function () {
        tip.hidden = true;
      },
    };
  }

  function drawGrowth(host, words) {
    host.textContent = "";
    var dated = kept(words).filter(function (word) {
      return word.at > EARLIEST;
    });
    if (dated.length < 2) {
      host.appendChild(
        el("p", "empty", "A line appears after two days.")
      );
      return;
    }

    var perDay = buckets(dated);
    var days = Object.keys(perDay)
      .map(Number)
      .sort(function (a, b) {
        return a - b;
      });

    // Every day between the first and the last, so a gap reads as a gap rather than
    // being drawn as steady progress.
    //
    // Stepped with the calendar rather than by adding 86,400,000ms: the keys are local
    // midnights, and on the two days a year the clocks move, a fixed-size step lands an
    // hour off one and never matches it again. Every day after the first change was
    // being dropped, which showed as a chart that quietly stopped counting.
    var points = [];
    var running = 0;
    var cursor = new Date(days[0]);
    var last = days[days.length - 1];
    while (cursor.getTime() <= last) {
      var stamp = cursor.getTime();
      var added = perDay[stamp] || 0;
      running += added;
      points.push({ day: stamp, total: running, added: added });
      cursor.setDate(cursor.getDate() + 1);
    }
    if (points.length === 1) points.push({ day: points[0].day + DAY, total: running, added: 0 });

    var W = 320;
    var H = 150;
    var pad = { top: 10, right: 8, bottom: 22, left: 34 };
    var plotW = W - pad.left - pad.right;
    var plotH = H - pad.top - pad.bottom;
    var top = Math.max(1, running);

    function px(index) {
      return pad.left + (index / (points.length - 1)) * plotW;
    }
    function py(value) {
      return pad.top + plotH - (value / top) * plotH;
    }

    var wrap = el("div", "chart");
    var picture = svg("svg", {
      viewBox: "0 0 " + W + " " + H,
      role: "img",
      "aria-label":
        plural(running, "word") +
        " saved between " +
        shortDate(points[0].day) +
        " and " +
        shortDate(points[points.length - 1].day),
    });

    var grid = svg("g", { class: "grid" });
    var ticks = [0, Math.round(top / 2), top];
    ticks.forEach(function (value) {
      grid.appendChild(
        svg("line", { x1: pad.left, y1: py(value), x2: W - pad.right, y2: py(value) })
      );
      var text = svg("text", { x: pad.left - 6, y: py(value) + 3, "text-anchor": "end" });
      text.textContent = String(value);
      grid.appendChild(text);
    });
    picture.appendChild(grid);

    var line = points
      .map(function (point, index) {
        return (index ? "L" : "M") + px(index) + " " + py(point.total);
      })
      .join(" ");
    picture.appendChild(
      svg("path", {
        d: line + " L" + px(points.length - 1) + " " + py(0) + " L" + px(0) + " " + py(0) + " Z",
        // §4 gives progress to leaf, and charts are one of the places functional colour
        // belongs. One hue for this chart: the wash, the line and the end dot are all it.
        fill: "var(--leaf)",
        "fill-opacity": "0.16",
      })
    );
    picture.appendChild(
      svg("path", { d: line, fill: "none", stroke: "var(--leaf)", "stroke-width": 2 })
    );

    // The end of the line is the number the page is about, so it is the one labelled.
    picture.appendChild(
      svg("circle", {
        cx: px(points.length - 1),
        cy: py(running),
        r: 4,
        fill: "var(--leaf)",
        // The panel is flat now, so the dot's halo is the page rather than a raised card.
        stroke: "var(--paper)",
        "stroke-width": 2,
      })
    );

    var ends = svg("g", { class: "axis" });
    var first = svg("text", { x: pad.left, y: H - 6 });
    first.textContent = shortDate(points[0].day);
    var last = svg("text", { x: W - pad.right, y: H - 6, "text-anchor": "end" });
    last.textContent = shortDate(points[points.length - 1].day);
    ends.appendChild(first);
    ends.appendChild(last);
    picture.appendChild(ends);

    var hair = svg("line", {
      y1: pad.top,
      y2: pad.top + plotH,
      stroke: "var(--axis)",
      "stroke-width": 1,
      opacity: 0,
    });
    picture.appendChild(hair);

    wrap.appendChild(picture);
    host.appendChild(wrap);
    var tip = tipFor(wrap);

    picture.addEventListener("mousemove", function (event) {
      var box = picture.getBoundingClientRect();
      var scale = W / box.width;
      var atX = (event.clientX - box.left) * scale;
      var index = Math.round(((atX - pad.left) / plotW) * (points.length - 1));
      index = Math.max(0, Math.min(points.length - 1, index));
      var point = points[index];
      hair.setAttribute("x1", px(index));
      hair.setAttribute("x2", px(index));
      hair.setAttribute("opacity", 1);
      var hostBox = wrap.getBoundingClientRect();
      tip.show(
        shortDate(point.day) +
          "<br><b>" +
          point.total +
          "</b> saved" +
          (point.added ? " · " + point.added + " that day" : ""),
        (px(index) / W) * hostBox.width,
        (py(point.total) / H) * hostBox.height
      );
    });
    picture.addEventListener("mouseleave", function () {
      hair.setAttribute("opacity", 0);
      tip.hide();
    });
  }

  /* Every figure the ledger says about one language, counted once. This used to draw its
   * own row of tiles under the ledger, which meant the same words were counted twice on
   * one page in two different shapes — and said twice, since "phrases saved" was in both.
   */
  function totals(entry) {
    var words = kept(entry.words);
    var known = 0;
    var learning = 0;
    var learned = 0;
    var recent = 0;
    var weekAgo = Date.now() - 7 * DAY;
    words.forEach(function (word) {
      if (word.status === KNOWN) known += 1;
      else if (word.status >= 1 && word.status <= 3) learning += 1;
      // Saved at a level below known and now known: a word targum taught somebody, rather
      // than one they opened a text already having and ticked off. The flag is written
      // when the word crosses, because nothing in a finished record can say afterwards
      // which of the two it was.
      if (word.status === KNOWN && word.learned) learned += 1;
      if (word.at > weekAgo && word.at > EARLIEST) recent += 1;
    });
    return {
      saved: words.length,
      learned: learned,
      known: known,
      learning: learning,
      recent: recent,
      texts: entry.texts || 0,
      finished: entry.finished || 0,
      phrases: entry.phrases.length,
    };
  }

  /* --- what is in the browser ------------------------------------------------
   *
   * Shared for the same reason the charts are: two pages want the same vocabulary in the
   * same shape, and the second copy is the one that stops matching.
   */

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback) || JSON.parse(fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
  }

  /* What a word means, in whichever language the page is showing meanings in.
   *
   * A word belongs to a language and a meaning to a language pair, so these are two
   * different stores and the word carries no meaning of its own. `into` is the target
   * the page has been asked for; a word with nothing filed under that pair shows no
   * meaning at all, which is the honest answer and is never the wrong language.
   */
  function base(code) {
    return (code || "").split("-")[0].toLowerCase();
  }

  function meanings(source, into) {
    return into ? read("targum:meanings:" + source + ":" + into, "{}") : {};
  }

  /* Which languages this reader has meanings in, for one source language, most recently
   * written first. Derived rather than remembered: the records carry `seen`, so what she
   * last read in is a fact the store already holds and not a preference to keep in step.
   */
  /* Which languages this reader may be shown definitions in, or null where nobody has
   * ever signed in on this browser — which is not a restriction, it is an absence of one.
   * Written by `sync.js` from the account, and read here rather than asked for, because
   * a page that waited would draw the wrong thing first and correct it after.
   */
  function allowed() {
    var said = null;
    try {
      said = JSON.parse(localStorage.getItem("targum:reads") || "null");
    } catch (e) {}
    return said && said.length ? said : null;
  }

  function targets(source) {
    var mine = allowed();
    var found = [];
    for (var n = 0; n < localStorage.length; n++) {
      var name = localStorage.key(n) || "";
      var head = "targum:meanings:" + source + ":";
      if (name.indexOf(head) !== 0) continue;
      var records = read(name, "{}");
      var last = 0;
      var count = 0;
      Object.keys(records).forEach(function (term) {
        // Phrases are filed here too, under their own ids. The switcher is about
        // languages, so it counts everything that has a meaning in one.
        count += 1;
        last = Math.max(last, Number((records[term] || {}).seen || 0));
      });
      var code = name.slice(head.length);
      // A language the account does not read is not offered and not chosen. The meanings
      // stay where they are — nothing here deletes anything — they are simply not an
      // answer this reader can use.
      if (mine && mine.indexOf(code) < 0) continue;
      if (count) found.push({ code: code, count: count, last: last });
    }
    return found.sort(function (a, b) {
      return b.last - a.last;
    });
  }

  function collect(into) {
    var docs = read("targum:docs", "{}");
    // The index the reader writes now, and the one it wrote before. A phrase kept
    // before the change is only in the older one, and without this it has no language
    // and never reaches the page.
    var older = read("targum:master", "{}");
    function about(hash) {
      var now = docs[hash] || {};
      var was = older[hash] || {};
      return { language: now.language || was.language || "", title: now.title || was.title || "" };
    }
    var byLanguage = {};

    function slot(code) {
      if (!byLanguage[code]) {
        byLanguage[code] = { code: code, words: [], phrases: [], texts: 0, finished: 0 };
      }
      return byLanguage[code];
    }

    for (var i = 0; i < localStorage.length; i++) {
      var name = localStorage.key(i);
      if (!name) continue;

      if (name.indexOf("targum:vocab:") === 0) {
        var code = name.slice("targum:vocab:".length);
        var vocab = read(name, "{}");
        var said = meanings(code, into);
        Object.keys(vocab).forEach(function (lemma) {
          var item = vocab[lemma] || {};
          var meant = said[lemma] || {};
          slot(code).words.push({
            lemma: lemma,
            term: item.surface || lemma,
            meaning: meant.meaning || "",
            note: meant.note || "",
            // Which language the two above are written in, so the page can mark them up
            // as what they are rather than leaving Russian inside an English page.
            into: into || "",
            band: item.band || "",
            status: item.status,
            // Named here or dropped here. This is the third list of field names a word
            // passes through — the store, the sync, and this — and each one silently
            // loses whatever it does not mention.
            learned: item.learned ? 1 : 0,
            at: item.at || 0,
          });
        });
      }

      if (name.indexOf("targum:picked:") === 0) {
        var hash = name.slice("targum:picked:".length);
        var doc = about(hash);
        if (!doc.language) continue;
        var segments = read(name, "{}");
        var read_as = meanings(base(doc.language), into);
        Object.keys(segments).forEach(function (segmentId) {
          (segments[segmentId] || []).forEach(function (pick) {
            var meant = (pick.id && read_as["phrase:" + pick.id]) || {};
            slot(doc.language).phrases.push({
              store: name,
              segmentId: segmentId,
              index: (segments[segmentId] || []).indexOf(pick),
              // Its name in the meanings store, for a note written on the words page.
              id: pick.id || "",
              term: pick.text || "",
              meaning: meant.meaning || "",
              note: meant.note || "",
              into: into || "",
              status: pick.status === undefined ? null : pick.status,
              title: doc.title || "a text",
              at: pick.at || 0,
            });
          });
        });
      }
    }

    // How many texts in each language have been opened. Counted into the slots that
    // already exist rather than through `slot()`, on purpose: a language you opened
    // something in but never marked a word in has nothing to show, and minting a slot
    // for it would put an empty language in the switcher and empty charts under it.
    var opened = read("targum:opened", "{}");
    Object.keys(opened).forEach(function (hash) {
      var code = about(hash).language;
      if (code && byLanguage[code]) byLanguage[code].texts += 1;
    });
    /* And how many targums the reader said they had finished. A targum finishes at the
       end of a chapter rather than at the end of a book (targum-internal#173), so a
       document is worth the greater of its old whole-document record and the number of
       its sections finished since sections existed. Never their sum.

       The alternative was back-filling every chapter of an already-finished book, and it
       was rejected: with no floor that turns one finished Genesis into fifty overnight,
       and every reader's count leaps without them having read anything that morning.
       This page's credibility rests on every number being a real count of a real thing
       — see the note under the rungs below, "counting a point is inventing a currency"
       — and a number that jumps fifty overnight is the one that teaches a reader not to
       trust the rest. A section finished twice is finished once. */
    Object.keys(docs).forEach(function (hash) {
      var record = docs[hash] || {};
      var where = about(hash).language;
      if (!where || !byLanguage[where]) return;
      var parts = 0;
      var sections = record.sections;
      if (sections && typeof sections === "object") {
        Object.keys(sections).forEach(function (id) {
          if (sections[id]) parts += 1;
        });
      }
      byLanguage[where].finished += Math.max(record.done ? 1 : 0, parts);
    });

    Object.keys(byLanguage).forEach(function (code) {
      byLanguage[code].words.sort(function (a, b) {
        return a.at - b.at;
      });
      byLanguage[code].phrases.sort(function (a, b) {
        return a.at - b.at;
      });
    });
    return byLanguage;
  }

  // The days somebody read on, oldest first. Global rather than per-language, because a
  // day is not in a language: you can read Hebrew in the morning and Russian at night,
  // and that is one day either way.
  //
  // Read here and written only by the reader. This runs on pages whose test harness
  // gives it a localStorage with no `setItem` at all, so a write in this file throws
  // where a read does not.
  function days() {
    return Object.keys(read("targum:days", "{}")).sort();
  }

  /* How many of these are finished with. Learn says it at the top of the page and the
     ledger counts it too, and the two must never be able to disagree. */
  function known(words) {
    var count = 0;
    vocabulary(words).forEach(function (word) {
      if (word.status === KNOWN) count += 1;
    });
    return count;
  }

  /* Which language to show meanings in, for one source language.
   *
   * A choice the reader made wins, where they have meanings in it at all; failing that,
   * the language they last read in. Derived rather than stored, so a new device is right
   * the moment the account arrives rather than after the reader finds a setting.
   */
  function meaningLanguage(source) {
    var have = targets(base(source));
    if (!have.length) return "";
    var chosen = window.TargumLang && window.TargumLang.into();
    for (var n = 0; n < have.length; n++) if (have[n].code === chosen) return chosen;
    return have[0].code;
  }

  /* --- how far into Hebrew ---------------------------------------------------
   *
   * Ulpan levels are a real ladder with real names, which is why they are worth saying
   * at all — but what is behind them here is a reader's own marked words, not a
   * placement test, and the card says so. `annotate/base.py` refuses to call band 3 "B1"
   * for exactly this reason; this is the same caution, kept where a reader can see it.
   */

  // Rarer words count for more, because a word further out is evidence of the commoner
  // ones behind it. The bands are Zipf cuts and each step out covers several times more
  // of the language than the one before — these weights rise far more slowly than that,
  // deliberately. A reader who has marked a handful of rare words out of a hard text has
  // not thereby reached gimel, and a scale that said so would be flattering them.
  // Centred near one rather than rising from it, so the total stays readable as a
  // vocabulary size and can be compared with the rungs below. Weighted upward from one
  // instead, a mixed six thousand words scored near twelve and came out at hey, which is
  // most of the way to reading a newspaper unaided.
  var BAND_WEIGHT = {
    easy: 0.8,
    "fairly easy": 1,
    moderate: 1.3,
    hard: 1.7,
    "very hard": 2.2,
    "extremely hard": 2.8,
  };
  // A word from a language with no frequency data behind it. Counted at its face value,
  // not guessed at.
  var UNRATED_WEIGHT = 1;

  // The ladder, with the vocabulary each rung is usually reckoned to want. Estimates,
  // and round on purpose: the figures behind ulpan levels vary between ulpanim, and
  // false precision here would be a claim nobody can support.
  var ULPAN = [
    { at: 250, letter: "א", name: "aleph" },
    { at: 900, letter: "א+", name: "aleph plus" },
    { at: 1800, letter: "ב", name: "bet" },
    { at: 3000, letter: "ב+", name: "bet plus" },
    { at: 4500, letter: "ג", name: "gimel" },
    { at: 6500, letter: "ד", name: "dalet" },
    { at: 9000, letter: "ה", name: "hey" },
    { at: 12000, letter: "ו", name: "vav" },
  ];

  /** The known words, weighted by how common each is. */
  function reach(words) {
    var total = 0;
    var counted = 0;
    // Names and numbers are not on the ladder. Rare by corpus frequency, a known name
    // would otherwise weigh as much as three everyday words.
    vocabulary(words).forEach(function (word) {
      if (word.status !== KNOWN) return;
      counted += 1;
      total += Object.prototype.hasOwnProperty.call(BAND_WEIGHT, word.band)
        ? BAND_WEIGHT[word.band]
        : UNRATED_WEIGHT;
    });
    return { weighted: total, words: counted };
  }

  /** Which rung that reaches, and the one after it. */
  function standingIn(weighted) {
    var here = null;
    var next = null;
    ULPAN.forEach(function (rung) {
      if (weighted >= rung.at) here = rung;
      else if (next === null) next = rung;
    });
    return { here: here, next: next };
  }

  // Into the ledger's standing line rather than a panel of its own: this is what the
  // block at the top of the page is about, and it was being said twice otherwise.

  /* Which level of the weekly to hand this reader.
   *
   * The digest is written three times over, and Learn is the one surface that knows who
   * is reading — so it can open the issue at the reader's own rung instead of asking
   * them to guess. `levels` are the issue's editions, each with the vocabulary it is
   * written for; the answer is the largest one this reader has reached, and the smallest
   * where they have reached none.
   *
   * Here rather than in learn.js because it is the same ladder the progress page draws,
   * and two weightings would disagree about the same reader.
   */
  function levelFor(words, levels) {
    if (!levels || !levels.length) return null;
    var ordered = levels.slice().sort(function (a, b) {
      return a.written_for - b.written_for;
    });
    var got = reach(words).weighted;
    var best = ordered[0];
    ordered.forEach(function (level) {
      if (got >= level.written_for) best = level;
    });
    return best;
  }


  window.TargumCharts = {
    el: el,
    targets: targets,
    meaningLanguage: meaningLanguage,
    kept: kept,
    KNOWN: KNOWN,
    svg: svg,
    plural: plural,
    shortDate: shortDate,
    dayOf: dayOf,
    buckets: buckets,
    shade: shade,
    tipFor: tipFor,
    growth: drawGrowth,
    totals: totals,
    collect: collect,
    days: days,
    known: known,
    vocabulary: vocabulary,
    read: read,
    EARLIEST: EARLIEST,
    STATUS: STATUS,
    ULPAN: ULPAN,
    reach: reach,
    standingIn: standingIn,
    levelFor: levelFor,
  };
})();
