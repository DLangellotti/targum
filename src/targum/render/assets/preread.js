/* The words to know before a chapter (targum-internal#97; `render/preread.py`).
 *
 * The page carries the chapter's hard words, the commonest first, and shows the first
 * forty. A page on the shared shelf is built once for everybody, so it cannot know which
 * of them this reader already has; the ledger in this browser can. A word they have
 * marked known, or put aside, comes off, and the next one comes up in its place. Where
 * nothing is left the list is not drawn at all.
 *
 * It reads the ledger the way the conversation and the claim do, from the same store the
 * reader writes (`targum:vocab:<language>`), and asks nothing of anybody: no request, no
 * address. When the account hands the page words this browser did not have, the list is
 * drawn again, as the reader's own marks are.
 *
 * Carried only by a page written with `TARGUM_PREREAD` on.
 */
(function () {
  "use strict";

  var box = document.getElementById("preread");
  if (!box) return;

  // The two ends of the ladder: a word finished with, and a word put aside.
  var KNOWN = 9;
  var IGNORED = 0;
  var SHOWN = Number(box.getAttribute("data-shown")) || 40;

  var root = document.documentElement;
  var language = (root.getAttribute("data-language") || root.getAttribute("lang") || "und")
    .split("-")[0]
    .toLowerCase();
  var LEDGER = "targum:vocab:" + language;
  var rows = Array.prototype.slice.call(box.querySelectorAll("li[data-lemma]"));
  var total = document.getElementById("preread-total");

  function ledger() {
    try {
      return JSON.parse(localStorage.getItem(LEDGER) || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  function settled(record) {
    return !!record && (record.status === KNOWN || record.status === IGNORED);
  }

  function draw() {
    var words = ledger();
    var shown = 0;
    rows.forEach(function (row) {
      var off = shown >= SHOWN || settled(words[row.getAttribute("data-lemma")]);
      row.hidden = off;
      if (!off) shown += 1;
    });
    if (total) total.textContent = String(shown);
    box.hidden = shown === 0;
    return shown;
  }

  draw();
  if (window.TargumSync && window.TargumSync.onChange) {
    window.TargumSync.onChange(function (changed) {
      if (changed) draw();
    });
  }
  // Marked in another tab of the same browser.
  window.addEventListener("storage", function (event) {
    if (!event.key || event.key === LEDGER) draw();
  });

  window.TargumPreread = { draw: draw };
})();
