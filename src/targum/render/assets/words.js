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

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }
  var names = window.TARGUM_LANGUAGES || {};

  var KNOWN = 9;
  var IGNORED = 0;
  var STATUS = {
    1: { name: "just met", slot: "--step-1" },
    2: { name: "getting there", slot: "--step-2" },
    3: { name: "nearly there", slot: "--step-3" },
    9: { name: "known", slot: "--step-4" },
    0: { name: "ignored", slot: "--off" },
  };
  var BANDS = [
    "not rated",
    "easy",
    "fairly easy",
    "moderate",
    "hard",
    "very hard",
    "extremely hard",
  ];
  var DAY = 86400000;
  // targum did not exist before this, so a date earlier than it is a number that was
  // never a date. Treated as undated rather than drawn: one bad value would otherwise
  // stretch the chart back to 1970 and build twenty thousand days of nothing.
  var EARLIEST = Date.UTC(2024, 0, 1);

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
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

  // Words are filed per language; phrases per text, with the text index saying which
  // language each belongs to. Gathered here into one shape per language.
  var collect = charts.collect;

  // Anything still in the per-document lists is moved across first, or someone who
  // comes here before opening a text is told they have kept nothing.
  if (window.TargumVocab) window.TargumVocab.migrate();

  var data = collect();
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

  /* --- writing back ---------------------------------------------------------- */

  function save(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {}
    // Signed in, this reaches the account a moment later; signed out it is a no-op.
    if (window.TargumSync) window.TargumSync.touched();
  }

  function updateWord(word, changes) {
    var name = "targum:vocab:" + currentCode;
    var store = read(name, "{}");
    var item = store[word.lemma];
    if (!item) return;
    Object.keys(changes).forEach(function (key) {
      item[key] = changes[key];
    });
    item.seen = Date.now();
    save(name, store);
    Object.keys(changes).forEach(function (key) {
      word[key] = changes[key];
    });
  }

  function updatePhrase(phrase, changes) {
    var store = read(phrase.store, "{}");
    var pick = (store[phrase.segmentId] || [])[phrase.index];
    if (!pick) return;
    Object.keys(changes).forEach(function (key) {
      pick[key] = changes[key];
    });
    // The same stamp the reader writes, and for the same reason: it is what tells the
    // account which browser's version of this phrase is the newer one.
    pick.seen = Date.now();
    save(phrase.store, store);
    Object.keys(changes).forEach(function (key) {
      phrase[key] = changes[key];
    });
  }

  /* --- small helpers -------------------------------------------------------- */

  // The chart kit, the growth line and the tiles live in charts.js — Learn draws the same
  // numbers, and two copies of a chart drift.
  var charts = window.TargumCharts;
  var el = charts.el;
  var svg = charts.svg;
  var plural = charts.plural;
  var shortDate = charts.shortDate;
  var dayOf = charts.dayOf;
  var tipFor = charts.tipFor;
  var drawGrowth = charts.growth;
  var drawTiles = charts.tiles;

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

    var ignored = counts[IGNORED] || 0;
    note.textContent = ignored
      ? plural(ignored, "word") + " ignored are left out."
      : "";

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
    words.forEach(function (word) {
      var index = BANDS.indexOf(word.band || "not rated");
      counts[index < 0 ? 0 : index] += 1;
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
        fill: "var(--step-3)",
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



  /* --- the word table ------------------------------------------------------- */

  var PAGE = 200;
  var shown = PAGE;
  // Which row is open for editing, keyed by the thing it is about. One at a time.
  var openKey = null;
  var currentCode = window.TargumLang.current(codes);

  var search = document.getElementById("search");
  var filter = document.getElementById("status-filter");
  var rowsBody = document.getElementById("word-rows");
  var moreButton = document.getElementById("more");
  var wordsEmpty = document.getElementById("words-empty");

  function visibleWords() {
    var needle = (search.value || "").trim().toLowerCase();
    var want = filter.value;
    return data[currentCode].words
      .filter(function (word) {
        if (want === "learning") {
          if (!(word.status >= 1 && word.status <= 3)) return false;
        } else if (want !== "all" && String(word.status) !== want) {
          return false;
        }
        if (!needle) return true;
        return (
          word.term.toLowerCase().indexOf(needle) > -1 ||
          word.lemma.toLowerCase().indexOf(needle) > -1 ||
          word.meaning.toLowerCase().indexOf(needle) > -1
        );
      })
      .slice()
      .reverse();
  }

  function statusCell(status) {
    var pip = el("span", "pip");
    var dot = el("i");
    dot.style.background = "var(" + (STATUS[status] || STATUS[0]).slot + ")";
    pip.appendChild(dot);
    pip.appendChild(document.createTextNode((STATUS[status] || {}).name || "—"));
    return pip;
  }

  function renderWords() {
    var rows = visibleWords();
    rowsBody.textContent = "";
    rows.slice(0, shown).forEach(function (word) {
      var tr = el("tr");

      var term = el("td");
      var bdi = el("bdi", "term", word.term);
      bdi.setAttribute("lang", currentCode);
      term.appendChild(bdi);
      tr.appendChild(term);

      var lemma = el("td");
      if (word.lemma !== word.term) {
        var form = el("bdi", "term", word.lemma);
        form.setAttribute("lang", currentCode);
        lemma.appendChild(form);
      }
      tr.appendChild(lemma);

      var meaning = el("td", "meaning" + (word.note ? " mine" : ""), word.note || word.meaning);
      if (word.note && word.meaning) meaning.title = "targum: " + word.meaning;
      tr.appendChild(meaning);
      tr.appendChild(el("td", "band", word.band || "—"));

      var status = el("td");
      status.appendChild(statusCell(word.status));
      tr.appendChild(status);

      tr.appendChild(el("td", "when", word.at > EARLIEST ? shortDate(word.at) : "—"));

      // The same two questions the reader asks, asked here too: a list you can only
      // look at is not where anyone wants to correct a definition.
      tr.addEventListener("click", function (event) {
        if (event.target.closest("button, input")) return;
        openKey = openKey === word.lemma ? null : word.lemma;
        renderWords();
      });
      if (openKey === word.lemma) tr.classList.add("open");
      rowsBody.appendChild(tr);

      if (openKey === word.lemma) {
        var holder = el("tr", "editor-row");
        var cell = document.createElement("td");
        cell.colSpan = 6;
        cell.appendChild(
          TargumVocab.editor({
            status: word.status,
            note: word.note,
            onStatus: function (value) {
              updateWord(word, { status: value === null ? word.status : value });
              show(currentCode);
            },
            onNote: function (text) {
              if (text === word.note) return;
              updateWord(word, { note: text });
              // Patched rather than re-rendered. Committing on blur means the click
              // that caused the blur — usually a level button — has not landed yet,
              // and rebuilding the row here would take that button out from under it.
              meaning.textContent = text || word.meaning;
              meaning.className = "meaning" + (text ? " mine" : "");
            },
          })
        );
        holder.appendChild(cell);
        rowsBody.appendChild(holder);
      }
    });

    document.getElementById("words-title").textContent =
      "Words" + (rows.length ? " (" + rows.length + ")" : "");
    wordsEmpty.hidden = rows.length > 0;
    wordsEmpty.textContent = rows.length
      ? ""
      : search.value.trim()
        ? "Nothing here matches that."
        : "Nothing at that stage yet.";
    moreButton.hidden = rows.length <= shown;
    moreButton.textContent = "Show " + Math.min(PAGE, rows.length - shown) + " more";
  }

  moreButton.onclick = function () {
    shown += PAGE;
    renderWords();
  };
  search.oninput = function () {
    shown = PAGE;
    renderWords();
  };
  filter.onchange = function () {
    shown = PAGE;
    renderWords();
  };

  /* --- phrases -------------------------------------------------------------- */

  function renderPhrases() {
    var host = document.getElementById("phrase-list");
    var empty = document.getElementById("phrases-empty");
    host.textContent = "";
    var phrases = data[currentCode].phrases;
    document.getElementById("phrases-title").textContent =
      "Phrases" + (phrases.length ? " (" + phrases.length + ")" : "");
    empty.hidden = phrases.length > 0;
    if (!phrases.length) return;

    // Grouped by the text they came from, which is the only place they mean anything.
    var byText = {};
    var order = [];
    phrases.forEach(function (phrase) {
      if (!byText[phrase.title]) {
        byText[phrase.title] = [];
        order.push(phrase.title);
      }
      byText[phrase.title].push(phrase);
    });

    order.forEach(function (title) {
      var group = el("div", "text-group");
      group.appendChild(el("h3", null, title));
      var list = el("ol");
      byText[title].forEach(function (phrase) {
        var item = el("li");
        var key = phrase.store + ":" + phrase.segmentId + ":" + phrase.index;
        var bdi = el("bdi", "term", phrase.term);
        bdi.setAttribute("lang", currentCode);
        item.appendChild(bdi);
        var reading = phrase.note || phrase.meaning;
        var line = null;
        if (reading) {
          line = el("span", "reading" + (phrase.note ? " mine" : ""), reading);
          if (phrase.note && phrase.meaning) line.title = "targum: " + phrase.meaning;
          item.appendChild(line);
        }
        item.addEventListener("click", function (event) {
          if (event.target.closest("button, input")) return;
          openKey = openKey === key ? null : key;
          renderPhrases();
        });
        if (openKey === key) {
          item.classList.add("open");
          item.appendChild(
            TargumVocab.editor({
              status: phrase.status,
              note: phrase.note,
              placeholder: "Your own reading",
              onStatus: function (value) {
                updatePhrase(phrase, { status: value === null ? phrase.status : value });
                renderPhrases();
              },
              onNote: function (text) {
                if (text === phrase.note) return;
                updatePhrase(phrase, { note: text });
                if (line) {
                  line.textContent = text || phrase.meaning;
                  line.className = "reading" + (text ? " mine" : "");
                }
              },
            })
          );
        }
        list.appendChild(item);
      });
      group.appendChild(list);
      host.appendChild(group);
    });
  }

  /* --- exports -------------------------------------------------------------- */

  /* A spreadsheet runs a cell that opens with =, +, - or @ as a formula, so an export
     is a way to hand somebody a file that does something when they open it. The leading
     apostrophe is what marks the rest as text; it is visible, which is the price of the
     file being inert. Everything else is left exactly as the reader wrote it. */
  function csvCell(value) {
    var text = value === undefined || value === null ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function download(name, header, rows) {
    var csv =
      "﻿" +
      [header]
        .concat(rows)
        .map(function (row) {
          return row.map(csvCell).join(",");
        })
        .join("\n");
    var blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var link = el("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  document.getElementById("export-words").onclick = function () {
    // What the filter is showing, so what you exported is what you were looking at.
    download(
      "targum " + named(currentCode) + " words.csv",
      ["word", "dictionary form", "how common", "how well", "meaning", "your meaning", "kept"],
      visibleWords().map(function (word) {
        return [
          word.term,
          word.lemma,
          word.band || "",
          (STATUS[word.status] || {}).name || "",
          word.meaning,
          word.note || "",
          word.at > EARLIEST ? new Date(word.at).toISOString().slice(0, 10) : "",
        ];
      })
    );
  };

  document.getElementById("export-phrases").onclick = function () {
    download(
      "targum " + named(currentCode) + " phrases.csv",
      ["phrase", "reading", "your reading", "how well", "from"],
      data[currentCode].phrases.map(function (phrase) {
        return [
          phrase.term,
          phrase.meaning,
          phrase.note || "",
          (STATUS[phrase.status] || {}).name || "",
          phrase.title,
        ];
      })
    );
  };

  /* --- taking it all away ----------------------------------------------------
   *
   * The two Export buttons above hand back what you are looking at: one language, and
   * whatever the status filter is showing. That is right for a spreadsheet and quietly
   * wrong for leaving — a reader with Hebrew and Russian, or with "learning" selected,
   * would get a subset and no sign that anything was missing.
   *
   * This one is everything, from the account rather than from this browser, so it holds
   * what other devices contributed too. Signed out there is no account to ask, and what
   * is in this browser is all there is.
   */
  function takeEverything() {
    var signedIn = window.TargumSync && window.TargumSync.who;
    if (signedIn) {
      window.location.href = keyed("/account/export");
      return;
    }
    var stores = {};
    for (var i = 0; i < localStorage.length; i++) {
      var name = localStorage.key(i);
      if (name && name.indexOf("targum:") === 0) {
        try {
          stores[name] = JSON.parse(localStorage.getItem(name));
        } catch (e) {
          stores[name] = localStorage.getItem(name);
        }
      }
    }
    var blob = new Blob([JSON.stringify({ browser: stores }, null, 1)], {
      type: "application/json;charset=utf-8",
    });
    var url = URL.createObjectURL(blob);
    var link = el("a");
    link.href = url;
    link.download = "targum.json";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  var takeAll = document.getElementById("export-all");
  if (takeAll) takeAll.onclick = takeEverything;

  function offerEverything(anything) {
    var panel = document.getElementById("take");
    // Nothing to take is not worth offering, and an empty download is a worse answer
    // than no button.
    if (panel) panel.hidden = !anything;
  }

  /* --- putting it together --------------------------------------------------- */

  function show(code) {
    offerEverything(true);
    currentCode = code;
    shown = PAGE;
    window.TargumLang.switcher(document.getElementById("langs"), codes, names, code, show);
    var betaNote = document.getElementById("beta-note");
    betaNote.hidden = !window.TargumLang.beta(code);
    if (!betaNote.hidden) betaNote.textContent = window.TargumLang.betaNote(code, names);
    drawTiles(document.getElementById("tiles"), data[code]);
    drawProgress(
      document.getElementById("progress"),
      document.getElementById("progress-note"),
      data[code].words
    );
    drawGrowth(document.getElementById("growth"), data[code].words);
    drawBands(document.getElementById("bands"), data[code].words);
    renderWords();
    renderPhrases();
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
      codes = window.TargumLang.order(Object.keys(data), names);
      // Down to nothing is a state this page has to be able to reach, not just start
      // in: taking the last word off the list on another device has to empty this one
      // too, rather than leave the table it drew a moment ago standing.
      document.getElementById("nothing").hidden = codes.length > 0;
      document.getElementById("page").hidden = codes.length === 0;
      offerEverything(codes.length > 0);
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
