/* Words you may already know (targum-internal#245).
 *
 * "We need a way for a user to indicate that their level is higher than their word
 * count." The level is a real count of known words, and §12 refuses a self-rated rung;
 * so the way up is to raise the count for real. The commonest words of modern Hebrew
 * that are not on the ledger, fifty at a time, each with the meaning the glossary already
 * holds and a checkbox (2026-09-11: "this should work with checkboxes, you can mark
 * words you checked as known, also option to check all"). One at the head checks the
 * page; "Mark checked as known" writes the checked ones as ordinary known words, marked
 * by the reader's own hand, and leaves the unchecked unmet and remembered as passed over,
 * since they were looked at and left; "None of these" passes the whole page. Nothing is
 * bought; a word the glossary does not hold is shown bare.
 *
 * Drawn wherever it is mounted (2026-09-11): on Your Words, and as the conversation's
 * first exchange on a first visit. `TargumClaim.mount(host, options)` builds the table
 * and the two presses inside `host`; `options.panel` is what to hide when there is
 * nothing to show, `options.once` stops after the first press, and `options.onMarked`
 * hears how many were marked.
 */
(function () {
  "use strict";

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  var LEDGER = "targum:vocab:he";
  var PASSED = "targum:claim-passed";
  var PAGE = 50;
  //: The fewest words a page shows while the list has them. A page of fifty set against
  //: a ledger that already holds most of it came down to one or two words at a time
  //: (2026-09-11); now the pages are gathered until there are at least this many.
  var FLOOR = 10;

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
  }
  function write(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {
      /* nothing to keep it in; the page still stands */
    }
  }

  // Whether there is anything to ask: Hebrew is the list's language and the ledger's,
  // and a reader with a page already marked or passed has answered once.
  function untouched() {
    var ledger = read(LEDGER, "{}");
    var passed = read(PASSED, "{}");
    return !Object.keys(ledger).length && !Object.keys(passed).length;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function mount(host, options) {
    options = options || {};
    var panel = options.panel || host;
    host.textContent = "";

    var wrap = el("div", "table-wrap");
    var table = el("table", "rows claim-table");
    var head = el("thead");
    var headRow = el("tr");
    var tick = el("th", "claim-tick");
    tick.setAttribute("scope", "col");
    var all = el("input", "claim-check claim-all");
    all.type = "checkbox";
    all.setAttribute("aria-label", "Check all");
    tick.appendChild(all);
    headRow.appendChild(tick);
    ["Word", "Meaning", "How common"].forEach(function (name) {
      var th = el("th", "", name);
      th.setAttribute("scope", "col");
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    table.appendChild(head);
    var rows = el("tbody", "claim-rows");
    table.appendChild(rows);
    wrap.appendChild(table);
    host.appendChild(wrap);

    var actions = el("div", "claim-actions");
    var yes = el("button", "claim-yes", "Mark checked as known");
    yes.type = "button";
    yes.disabled = true;
    var no = el("button", "claim-no", "None of these");
    no.type = "button";
    var said = el("span", "claim-said", "");
    actions.appendChild(yes);
    actions.appendChild(no);
    actions.appendChild(said);
    host.appendChild(actions);

    var shown = [];
    var boxes = [];
    var next = 0;
    var uid = "claim-" + Math.random().toString(36).slice(2, 7) + "-";

    // What is checked, and the controls that follow it: the press is only offered once
    // something is checked, and the head's box says whether all, some or none are.
    function checked() {
      return shown.filter(function (word, n) {
        return boxes[n] && boxes[n].checked;
      });
    }
    function settle() {
      var count = checked().length;
      yes.disabled = count === 0;
      all.checked = shown.length > 0 && count === shown.length;
      all.indeterminate = count > 0 && count < shown.length;
    }

    function draw(words) {
      rows.textContent = "";
      shown = words;
      boxes = [];
      words.forEach(function (word, n) {
        var tr = el("tr");
        var cell = el("td", "claim-tick");
        var box = el("input", "claim-check");
        box.type = "checkbox";
        box.id = uid + n;
        box.setAttribute("data-form", word.form);
        box.onchange = settle;
        cell.appendChild(box);
        tr.appendChild(cell);
        boxes.push(box);
        var form = el("td");
        var label = el("label");
        label.setAttribute("for", box.id);
        var he = el("bdi", "", word.form);
        he.setAttribute("lang", "he");
        he.setAttribute("dir", "rtl");
        label.appendChild(he);
        form.appendChild(label);
        tr.appendChild(form);
        tr.appendChild(el("td", "", word.meaning || ""));
        tr.appendChild(el("td", "", word.band || ""));
        rows.appendChild(tr);
      });
      panel.hidden = words.length === 0;
      no.disabled = false;
      settle();
    }

    all.onchange = function () {
      boxes.forEach(function (box) {
        box.checked = all.checked;
      });
      settle();
    };

    // The next words the ledger does not already hold and the reader has not passed
    // over. Asked for in pages of fifty and filtered here, because the ledger is the
    // browser's; pages are gathered until at least FLOOR words remain, or the list ends.
    function load(from, gathered) {
      gathered = gathered || [];
      var ledger = read(LEDGER, "{}");
      var passed = read(PASSED, "{}");
      return fetch(keyed("/words/common?offset=" + from + "&limit=" + PAGE), {
        headers: keyHeaders({}),
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (answer) {
          if (answer.error) return draw(gathered);
          var fresh = (answer.words || []).filter(function (word) {
            return !ledger[word.form] && !passed[word.form];
          });
          gathered = gathered.concat(fresh);
          next = answer.next;
          if (gathered.length < FLOOR && next !== null && next !== undefined) {
            return load(next, gathered);
          }
          draw(gathered);
        })
        .catch(function () {
          draw(gathered);
        });
    }

    // After a press: the next page, or — mounted once, as the first exchange — done.
    function onward() {
      if (options.once) {
        wrap.hidden = true;
        yes.hidden = true;
        no.hidden = true;
        if (options.onDone) options.onDone();
        return;
      }
      if (next === null || next === undefined) {
        draw([]);
        said.textContent = "That is the whole list.";
        return;
      }
      load(next);
    }

    // The checked words are known; the rest of the page was looked at and left, so it
    // is passed over with them rather than shown again.
    yes.onclick = function () {
      var known = checked();
      if (!known.length) return;
      yes.disabled = true;
      no.disabled = true;
      var ledger = read(LEDGER, "{}");
      var passed = read(PASSED, "{}");
      var now = Date.now();
      known.forEach(function (word, n) {
        if (ledger[word.form]) return;
        ledger[word.form] = {
          status: 9,
          surface: word.form,
          meaning: word.meaning || "",
          band: word.band || "",
          learned: 0,
          // One millisecond apart, so "kept" keeps the order they were shown in.
          at: now + n,
          seen: now + n,
        };
      });
      shown.forEach(function (word) {
        if (!ledger[word.form]) passed[word.form] = 1;
      });
      write(LEDGER, ledger);
      write(PASSED, passed);
      said.textContent = known.length + " marked known.";
      if (window.TargumSync && window.TargumSync.touched) window.TargumSync.touched();
      if (window.TargumLists && window.TargumLists.changed) window.TargumLists.changed();
      if (options.onMarked) options.onMarked(known.length);
      onward();
    };

    no.onclick = function () {
      if (!shown.length) return;
      var passed = read(PASSED, "{}");
      shown.forEach(function (word) {
        passed[word.form] = 1;
      });
      write(PASSED, passed);
      said.textContent = "";
      if (options.onMarked) options.onMarked(0);
      onward();
    };

    load(0);
    return { load: load };
  }

  // Hebrew only: the list is modern Hebrew's, and so is the ledger it is set against.
  function hebrew() {
    var lang = window.TargumLang;
    return (lang && lang.current ? lang.current(["he"]) : "he") === "he";
  }

  // The page that carries the panel mounts it by itself; the conversation mounts its own.
  var body = document.getElementById("claim-body");
  var panel = document.getElementById("claim-panel");
  if (body && panel) {
    if (hebrew()) mount(body, { panel: panel });
    else panel.hidden = true;
  }

  window.TargumClaim = { mount: mount, untouched: untouched, hebrew: hebrew, PAGE: PAGE, FLOOR: FLOOR };
})();
