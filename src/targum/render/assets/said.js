/* How the French is said (targum-internal#266; `annotate/french_said.py`).
 *
 * Carried only by a page written while `TARGUM_FRENCH_IPA` is on, so a page without it is
 * the page it was, byte for byte. The page's data holds, for each row, the places the
 * switch draws: a liaison every speaker makes (1, with the consonant heard), an elision's
 * apostrophe (2) and the final letters nobody says (3), as offsets into the row's text —
 * the same text the word offsets are measured in.
 *
 * Nothing is written into the text. Each place is a span around characters already there
 * — the space a liaison crosses, the apostrophe, the silent letters — and the stylesheet
 * draws the tie and greys the letters only while `body.said-on`. So a word's offsets, the
 * phrase a selection measures and the surface a saved word is read back from are the same
 * with the switch on or off: every one of them counts characters, and none are added.
 *
 * The spans go in after `reader.js` has marked a row, never before: it keeps a row's first
 * markup as the one it redraws from, and that must stay the bare text. A row is redrawn
 * from scratch whenever the reader marks it, so a MutationObserver puts them back.
 */
(function () {
  "use strict";

  var holder = document.getElementById("targum-data");
  if (!holder) return;
  var data;
  try {
    data = JSON.parse(holder.textContent);
  } catch (e) {
    return;
  }
  var marks = data.said;
  if (!marks) return;
  var words = data.saidWords || {};
  function t(key, english) {
    return typeof words[key] === "string" ? words[key] : english;
  }

  var KINDS = { 1: "said-tie", 2: "said-elide", 3: "said-mute" };
  var STORE = "targum:said";
  var SAID = [t("said.off", "As written."), t("said.on", "As said.")];

  var on = false;
  try {
    on = localStorage.getItem(STORE) === "1";
  } catch (e) {}

  // The row's text nodes, each with where it starts in the row.
  function pieces(cell) {
    var out = [];
    var offset = 0;
    var walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while ((node = walker.nextNode())) {
      out.push({ node: node, start: offset, end: offset + node.nodeValue.length });
      offset += node.nodeValue.length;
    }
    return out;
  }

  // Characters [start, end) of the row, wrapped in a span of this kind — one span per
  // text node the range crosses, since a word's own span may be cut by a kept phrase.
  function wrap(cell, start, end, kind, consonant) {
    pieces(cell).forEach(function (entry) {
      var from = Math.max(start, entry.start);
      var to = Math.min(end, entry.end);
      if (from >= to) return;
      var node = entry.node;
      if (from > entry.start) node = node.splitText(from - entry.start);
      if (to < entry.end) node.splitText(to - from);
      var span = document.createElement("span");
      span.className = KINDS[kind];
      span.setAttribute("data-said-mark", "");
      if (consonant) span.setAttribute("data-said", consonant);
      node.parentNode.replaceChild(span, node);
      span.appendChild(node);
    });
  }

  function draw(cell) {
    var pair = cell.closest ? cell.closest(".pair[data-id]") : null;
    if (!pair) return;
    var list = marks[pair.getAttribute("data-id")];
    if (!list || !list.length) return;
    // Only a row the reader has marked, and only once per marking.
    if (!cell.querySelector(".w") || cell.querySelector("[data-said-mark]")) return;
    list.forEach(function (mark) {
      wrap(cell, mark[0], mark[1], mark[2], mark[3] || "");
    });
  }

  function drawAll() {
    Array.prototype.forEach.call(document.querySelectorAll(".pair[data-id] .src"), draw);
  }

  // The card's reading is French, not Hebrew: `reader.js` names every reading's language
  // as the Hebrew one, and a screen reader would say it in a Hebrew voice.
  function nameReadings() {
    Array.prototype.forEach.call(
      document.querySelectorAll('.gloss-card .said bdi[lang="he-fonipa"]'),
      function (reading) {
        reading.setAttribute("lang", "fr-fonipa");
      }
    );
  }

  function apply() {
    document.body.classList.toggle("said-on", on);
    Array.prototype.forEach.call(document.querySelectorAll("[data-said-toggle]"), function (button) {
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function toggle() {
    on = !on;
    apply();
    try {
      if (window.targumKeep) window.targumKeep(STORE, on ? "1" : "0");
    } catch (e) {}
    var spoken = document.getElementById("spoken");
    if (spoken) {
      spoken.textContent = "";
      spoken.textContent = SAID[on ? 1 : 0];
    }
  }

  new MutationObserver(function (records) {
    var seen = [];
    var card = false;
    records.forEach(function (record) {
      var target = record.target.nodeType === 1 ? record.target : record.target.parentNode;
      if (!target || !target.closest) return;
      var cell = target.closest(".src");
      if (cell && seen.indexOf(cell) < 0) seen.push(cell);
      if (target.closest(".gloss-card")) card = true;
    });
    seen.forEach(draw);
    if (card) nameReadings();
  }).observe(document.body, { childList: true, subtree: true });

  Array.prototype.forEach.call(document.querySelectorAll("[data-said-toggle]"), function (button) {
    button.addEventListener("click", function (event) {
      event.stopPropagation();
      toggle();
    });
  });

  // `n`, as the vowels are on a Hebrew page. The reader's own keys go first: a key a card
  // has taken is not this one's.
  document.addEventListener("keydown", function (event) {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
    var target = event.target || {};
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName) || target.isContentEditable) return;
    var key = event.key;
    if (typeof key === "string" && key.length === 1) key = key.toLowerCase();
    if (!/^[a-z0-9?]$/.test(key) && /^Key[A-Z]$/.test(event.code || "")) {
      key = event.code.charAt(3).toLowerCase();
    }
    if (key !== "n") return;
    toggle();
  });

  apply();
  drawAll();
})();
