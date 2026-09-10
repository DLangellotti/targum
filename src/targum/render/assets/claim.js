/* Words you may already know (targum-internal#245).
 *
 * "We need a way for a user to indicate that their level is higher than their word
 * count." The level is a real count of known words, and §12 refuses a self-rated rung;
 * so the way up is to raise the count for real. The commonest words of modern Hebrew
 * that are not on the ledger, fifty at a time, each with the meaning the glossary already
 * holds: "I know all of these" marks the page known — ordinary known words, marked by the
 * reader's own press — and "Not these" leaves them unmet and remembered as passed over.
 * Nothing is bought; a word the glossary does not hold is shown bare.
 */
(function () {
  "use strict";

  var panel = document.getElementById("claim-panel");
  var rows = document.getElementById("claim-rows");
  var yes = document.getElementById("claim-yes");
  var no = document.getElementById("claim-no");
  var said = document.getElementById("claim-said");
  if (!panel || !rows || !yes || !no) return;

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

  var shown = [];
  var offset = 0;
  var next = 0;

  function draw(words) {
    rows.textContent = "";
    shown = words;
    words.forEach(function (word) {
      var tr = document.createElement("tr");
      var form = document.createElement("td");
      var he = document.createElement("bdi");
      he.setAttribute("lang", "he");
      he.setAttribute("dir", "rtl");
      he.textContent = word.form;
      form.appendChild(he);
      tr.appendChild(form);
      var meaning = document.createElement("td");
      meaning.textContent = word.meaning || "";
      tr.appendChild(meaning);
      var band = document.createElement("td");
      band.textContent = word.band || "";
      tr.appendChild(band);
      rows.appendChild(tr);
    });
    panel.hidden = words.length === 0;
    yes.disabled = false;
    no.disabled = false;
  }

  // The next page the ledger does not already hold and the reader has not passed over.
  // Asked for in pages of fifty and filtered here, because the ledger is the browser's;
  // pages that filter down to nothing are skipped until one has rows in it.
  function load(from) {
    var ledger = read(LEDGER, "{}");
    var passed = read(PASSED, "{}");
    return fetch(keyed("/words/common?offset=" + from + "&limit=" + PAGE), {
      headers: keyHeaders({}),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (answer) {
        if (answer.error) return draw([]);
        var fresh = (answer.words || []).filter(function (word) {
          return !ledger[word.form] && !passed[word.form];
        });
        offset = from;
        next = answer.next;
        if (!fresh.length && answer.next !== null && answer.next !== undefined) {
          return load(answer.next);
        }
        draw(fresh);
      })
      .catch(function () {
        draw([]);
      });
  }

  function onward() {
    if (next === null || next === undefined) {
      draw([]);
      if (said) said.textContent = "That is the whole list.";
      return;
    }
    load(next);
  }

  yes.onclick = function () {
    if (!shown.length) return;
    yes.disabled = true;
    no.disabled = true;
    var ledger = read(LEDGER, "{}");
    var now = Date.now();
    shown.forEach(function (word, n) {
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
    write(LEDGER, ledger);
    if (said) said.textContent = shown.length + " marked known.";
    if (window.TargumSync && window.TargumSync.touched) window.TargumSync.touched();
    if (window.TargumLists && window.TargumLists.changed) window.TargumLists.changed();
    onward();
  };

  no.onclick = function () {
    if (!shown.length) return;
    var passed = read(PASSED, "{}");
    shown.forEach(function (word) {
      passed[word.form] = 1;
    });
    write(PASSED, passed);
    if (said) said.textContent = "";
    onward();
  };

  // Hebrew only: the list is modern Hebrew's, and so is the ledger it is set against.
  var lang = window.TargumLang;
  var hebrew = lang && lang.current ? lang.current(["he"]) : "he";
  if (hebrew === "he") load(0);
  else panel.hidden = true;

  window.TargumClaim = { load: load, PAGE: PAGE };
})();
