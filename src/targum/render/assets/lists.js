/* The two lists of what you are learning: words, and phrases.
 *
 * Both lived on the progress page, next to the charts, which put half of learning on the
 * page you go to for numbers. They belong on Learn, where everything you are working on
 * is. Their own file rather than more of learn.js: this is a working surface with a
 * filter, a search, paging and an editor in it, and learn.js is about a shelf.
 *
 * Reads the same stores the reader writes and writes back to them the same way, so a
 * definition corrected here is corrected in the reader on the next sync.
 */

(function () {
  "use strict";

  var charts = window.TargumCharts;
  var el = charts.el;
  var shortDate = charts.shortDate;
  var STATUS = charts.STATUS;
  var EARLIEST = charts.EARLIEST;
  var KNOWN = charts.KNOWN;

  //: How many rows are drawn before the More button. A vocabulary of four thousand words
  //: is a real thing, and four thousand rows is a page nobody can scroll.
  var PAGE = 200;

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
  }

  function save(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {}
    // Signed in, this reaches the account a moment later; signed out it is a no-op.
    if (window.TargumSync) window.TargumSync.touched();
  }

  /* --- state ---------------------------------------------------------------- */

  var code = null;
  var entry = { words: [], phrases: [] };
  var shown = PAGE;
  //: How many rows each list may draw here, if the page asked for a ceiling. Learn does;
  //: the pages that are only a list do not, and page through with More instead.
  var limits = {};
  // Which row is open for editing, keyed by the thing it is about. One at a time.
  var openKey = null;

  //: Called after a word's status changes, so the page above can redraw what depends on
  //: it — the known count on Learn is the same number this list edits.
  var onChanged = null;

  var search = null;
  var filter = null;
  var rowsBody = null;
  var moreButton = null;
  var wordsEmpty = null;

  function at(id) {
    return document.getElementById(id);
  }

  /** The way to the rest of a list, when this page is only showing the top of it. */
  function seeAll(id, total) {
    var link = at(id);
    if (!link) return;
    link.hidden = !total;
    if (total) link.textContent = "See all " + total + " →";
  }

  function named(names, which) {
    return (names || {})[which] || (which || "").toUpperCase();
  }

  /* --- writing back --------------------------------------------------------- */

  function updateWord(word, changes) {
    var name = "targum:vocab:" + code;
    var store = read(name, "{}");
    var item = store[word.lemma];
    if (!item) return;
    // A word carried up to known from a level below it was learned here, wherever it was
    // carried up. Asked before the change lands, because the answer is in the level it is
    // leaving — and the same rule lives in the reader, which is the other way up.
    if (
      changes.status === KNOWN &&
      item.status >= 1 &&
      item.status <= 3
    ) {
      item.learned = 1;
    }
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

  /* --- the word table ------------------------------------------------------- */

  function visibleWords() {
    var needle = (search.value || "").trim().toLowerCase();
    var want = filter.value;
    return entry.words
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
    if (!rowsBody) return;
    var rows = visibleWords();
    var cap = limits.words || 0;
    var drawing = cap ? rows.slice(0, cap) : rows.slice(0, shown);
    rowsBody.textContent = "";
    drawing.forEach(function (word) {
      var tr = el("tr");

      var term = el("td");
      var bdi = el("bdi", "term", word.term);
      bdi.setAttribute("lang", code);
      term.appendChild(bdi);
      tr.appendChild(term);

      var lemma = el("td");
      if (word.lemma !== word.term) {
        var form = el("bdi", "term", word.lemma);
        form.setAttribute("lang", code);
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
          window.TargumVocab.editor({
            status: word.status,
            note: word.note,
            onStatus: function (value) {
              updateWord(word, { status: value === null ? word.status : value });
              renderWords();
              if (onChanged) onChanged();
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

    at("words-title").textContent =
      "Your Words" + (rows.length ? " (" + rows.length + ")" : "");
    wordsEmpty.hidden = rows.length > 0;
    wordsEmpty.textContent = rows.length
      ? ""
      : search.value.trim()
        ? "Nothing here matches that."
        : "Nothing at that stage yet.";
    // Capped, there is no paging: the rest of the list is a page away, not a press away.
    moreButton.hidden = cap ? true : rows.length <= shown;
    moreButton.textContent = "Show " + Math.min(PAGE, rows.length - shown) + " more";
    seeAll("words-more", cap && rows.length > cap ? rows.length : 0);
  }

  /* --- phrases -------------------------------------------------------------- */

  function renderPhrases() {
    var host = at("phrase-list");
    var empty = at("phrases-empty");
    if (!host) return;
    host.textContent = "";
    var all = entry.phrases;
    var cap = limits.phrases || 0;
    var phrases = cap ? all.slice(0, cap) : all;
    at("phrases-title").textContent =
      "Your Phrases" + (all.length ? " (" + all.length + ")" : "");
    seeAll("phrases-more", cap && all.length > cap ? all.length : 0);
    empty.hidden = all.length > 0;
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
        bdi.setAttribute("lang", code);
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
            window.TargumVocab.editor({
              status: phrase.status,
              note: phrase.note,
              placeholder: "Enter text",
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

  /* --- exports ---------------------------------------------------------------
   *
   * An export is the account's, not the browser's: it needs somewhere to have come
   * from, and a file assembled out of whatever happens to be in this browser is a
   * subset with no sign that anything is missing. Signed out the two buttons are not
   * there at all — an offer that cannot be met is worse than no offer.
   */

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
    // A byte order mark, so a spreadsheet opens Hebrew and Russian as UTF-8. Spelled
    // as an escape rather than typed: the character itself is invisible in the source,
    // and anything that strips it takes the Hebrew with it.
    var csv =
      "\ufeff" +
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

  var languages = {};

  function exportWords() {
    // What the filter is showing, so what you exported is what you were looking at.
    download(
      "targum " + named(languages, code) + " words.csv",
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
  }

  function exportPhrases() {
    download(
      "targum " + named(languages, code) + " phrases.csv",
      ["phrase", "reading", "your reading", "how well", "from"],
      entry.phrases.map(function (phrase) {
        return [
          phrase.term,
          phrase.meaning,
          phrase.note || "",
          (STATUS[phrase.status] || {}).name || "",
          phrase.title,
        ];
      })
    );
  }

  /** Show the two export buttons, or do not. Called again whenever sync resolves. */
  function offerExports(signedIn) {
    ["export-words", "export-phrases"].forEach(function (id) {
      var button = at(id);
      if (button) button.hidden = !signedIn;
    });
  }

  /* --- what the page calls --------------------------------------------------- */

  function mount(options) {
    languages = (options && options.languages) || {};
    onChanged = (options && options.onChanged) || null;

    // A page may carry one list rather than both — the whole point of the two pages this
    // also runs — so everything here is wired only if it is there.
    search = at("search");
    filter = at("status-filter");
    rowsBody = at("word-rows");
    moreButton = at("more");
    wordsEmpty = at("words-empty");

    if (moreButton) {
      moreButton.onclick = function () {
        shown += PAGE;
        renderWords();
      };
    }
    if (search) {
      search.oninput = function () {
        shown = PAGE;
        renderWords();
      };
    }
    if (filter) {
      filter.onchange = function () {
        shown = PAGE;
        renderWords();
      };
    }
    if (at("export-words")) at("export-words").onclick = exportWords;
    if (at("export-phrases")) at("export-phrases").onclick = exportPhrases;
    offerExports(false);
  }

  /** Draw both lists for one language. */
  function draw(which, store, ceilings) {
    code = which;
    entry = store || { words: [], phrases: [] };
    limits = ceilings || {};
    shown = PAGE;
    openKey = null;
    renderWords();
    renderPhrases();
  }

  window.TargumLists = {
    mount: mount,
    draw: draw,
    offerExports: offerExports,
  };
})();
