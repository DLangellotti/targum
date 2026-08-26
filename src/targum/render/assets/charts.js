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

  // Ignore means "this is not vocabulary" — a name, a numeral, a word from another
  // language. A word you ignored is not a word you kept, so nothing that counts what you
  // have counts it and nothing that draws it draws it. Dismissing something and then
  // being shown a tally of it is not dismissing it.
  function kept(words) {
    return (words || []).filter(function (word) {
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

    var perDay = {};
    dated.forEach(function (word) {
      var day = dayOf(word.at);
      perDay[day] = (perDay[day] || 0) + 1;
    });
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
        fill: "var(--step-2)",
        "fill-opacity": "0.18",
      })
    );
    picture.appendChild(
      svg("path", { d: line, fill: "none", stroke: "var(--step-3)", "stroke-width": 2 })
    );

    // The end of the line is the number the page is about, so it is the one labelled.
    picture.appendChild(
      svg("circle", {
        cx: px(points.length - 1),
        cy: py(running),
        r: 4,
        fill: "var(--step-4)",
        stroke: "var(--paper-raised)",
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

  function collect() {
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
      if (!byLanguage[code]) byLanguage[code] = { code: code, words: [], phrases: [], texts: 0 };
      return byLanguage[code];
    }

    for (var i = 0; i < localStorage.length; i++) {
      var name = localStorage.key(i);
      if (!name) continue;

      if (name.indexOf("targum:vocab:") === 0) {
        var code = name.slice("targum:vocab:".length);
        var vocab = read(name, "{}");
        Object.keys(vocab).forEach(function (lemma) {
          var item = vocab[lemma] || {};
          slot(code).words.push({
            lemma: lemma,
            term: item.surface || lemma,
            meaning: item.meaning || "",
            note: item.note || "",
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
        Object.keys(segments).forEach(function (segmentId) {
          (segments[segmentId] || []).forEach(function (pick) {
            slot(doc.language).phrases.push({
              store: name,
              segmentId: segmentId,
              index: (segments[segmentId] || []).indexOf(pick),
              term: pick.text || "",
              meaning: pick.meaning || "",
              note: pick.note || "",
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
    (words || []).forEach(function (word) {
      if (word.status === KNOWN) count += 1;
    });
    return count;
  }

  window.TargumCharts = {
    el: el,
    kept: kept,
    KNOWN: KNOWN,
    svg: svg,
    plural: plural,
    shortDate: shortDate,
    dayOf: dayOf,
    tipFor: tipFor,
    growth: drawGrowth,
    totals: totals,
    collect: collect,
    days: days,
    known: known,
    read: read,
    EARLIEST: EARLIEST,
    STATUS: STATUS,
  };
})();
