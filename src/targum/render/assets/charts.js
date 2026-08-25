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

  var EARLIEST = Date.UTC(2024, 0, 1);

  var STATUS = {
    1: { name: "just met", slot: "--step-1" },
    2: { name: "getting there", slot: "--step-2" },
    3: { name: "nearly there", slot: "--step-3" },
    9: { name: "known", slot: "--step-4" },
    0: { name: "ignored", slot: "--off" },
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
    var dated = words.filter(function (word) {
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
        " kept between " +
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
          "</b> kept" +
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

  function drawTiles(host, entry) {
    host.textContent = "";
    var words = entry.words;
    var known = 0;
    var learning = 0;
    var recent = 0;
    var weekAgo = Date.now() - 7 * DAY;
    words.forEach(function (word) {
      if (word.status === KNOWN) known += 1;
      else if (word.status >= 1 && word.status <= 3) learning += 1;
      if (word.at > weekAgo && word.at > EARLIEST) recent += 1;
    });
    var scored = known + learning;

    function tile(value, label, extra) {
      var box = el("div", "tile");
      box.appendChild(el("b", null, String(value)));
      box.appendChild(el("span", null, label));
      if (extra) box.appendChild(el("span", "delta", extra));
      host.appendChild(box);
    }

    tile(words.length, "words kept", recent ? "+" + recent + " this week" : "");
    tile(known, "known", scored ? Math.round((known / scored) * 100) + "% of the way" : "");
    tile(learning, "still learning");
    tile(entry.phrases.length, entry.phrases.length === 1 ? "phrase" : "phrases");
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
      if (!byLanguage[code]) byLanguage[code] = { code: code, words: [], phrases: [] };
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

  window.TargumCharts = {
    el: el,
    svg: svg,
    plural: plural,
    shortDate: shortDate,
    dayOf: dayOf,
    tipFor: tipFor,
    growth: drawGrowth,
    tiles: drawTiles,
    collect: collect,
    read: read,
    EARLIEST: EARLIEST,
    STATUS: STATUS,
  };
})();
