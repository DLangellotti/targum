/* Where a text was opened from (targum-internal#546; design.md §12, "A named back beside
 * the mark, in the reader and Theatre", 2026-10-28).
 *
 * A beta reader got stuck inside a reader: the one way out was the mark, and it went to
 * Your targums whatever page they had come from. So the reader's bar carries a named back
 * beside the mark — "← Library", "← <playlist>", "← Words" — and this is how it knows
 * the name.
 *
 * Every desk page, as it is left, writes what it is in this tab's own store: its name,
 * as the page says it, and its address. A reader reads that as it opens. Nothing rides
 * in an address, so a link copied out of the bar is the same link it always was, and no
 * name, title or list ever reaches a server's log or a shared screen's history. The store
 * is the tab's: a second tab, or a link opened from another app, starts with nothing and
 * the back says "Your targums".
 *
 * A reader, as it is left, writes itself the same way, carrying its own back with it. So
 * the next section, the next scene or a playlist's next item inherits where the text was
 * opened from, and a reload finds what it had; and a desk page opened from a reader — ⋯ →
 * Words — knows which text, and where, to go back to (#547).
 *
 * Framed — the front page's picture of a reader, the drawer's conversation — a page is
 * not where anybody is, and writes and takes nothing. Off a disk there is no desk.
 */
(function () {
  "use strict";

  //: What the page just left was, in this tab.
  var FROM = "targum:from";
  //: Each text's back, by its folder, so the browser's own Back and Forward find it again.
  var BACKS = "targum:backs";

  function topmost() {
    try {
      return window.top === window;
    } catch (e) {
      return false;
    }
  }

  function read(name) {
    try {
      return JSON.parse(window.sessionStorage.getItem(name) || "null");
    } catch (e) {
      return null;
    }
  }

  function write(name, value) {
    try {
      window.sessionStorage.setItem(name, JSON.stringify(value));
    } catch (e) {}
  }

  function here() {
    return location.pathname + location.search;
  }

  function plain(text) {
    return String(text || "")
      .replace(/[⁦-⁩‎‏]/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  var live = topmost() && /^https?:$/.test(location.protocol);
  var script = document.currentScript;
  var handed = null;

  window.TargumCame = {
    /* What the page before this one was, as it said it, or null. */
    from: function () {
      return live ? read(FROM) : null;
    },
    /* What this page says it is when it is left, in place of its own name: the Words
       page's way back hands the text it came from straight on, so the reader opens with
       the back it had rather than "← Words". */
    hand: function (record) {
      handed = record || null;
    },
  };
  if (!live) return;

  var back = document.getElementById("bar-back");

  /* --- a desk page ---------------------------------------------------------------- */

  if (!back) {
    window.addEventListener("pagehide", function () {
      if (handed) return write(FROM, handed);
      var body = document.body;
      // A page whose name is drawn by its script — one playlist — says it on the body;
      // the rest are named where they are rendered.
      var label =
        (body && body.getAttribute("data-came-label")) ||
        (script && script.getAttribute("data-label")) ||
        (document.querySelector("h1") || {}).textContent ||
        document.title;
      write(FROM, { via: "desk", label: plain(label), href: here(), at: Date.now() });
    });
    return;
  }

  /* --- a reader ------------------------------------------------------------------- */

  var folder = location.pathname.replace(/[^/]*$/, "");
  var backs = read(BACKS) || {};
  var came = read(FROM);
  var how = "navigate";
  try {
    var entry = performance.getEntriesByType("navigation")[0];
    if (entry && entry.type) how = entry.type;
  } catch (e) {}

  var to = null;
  if (how === "back_forward" && backs[folder]) to = backs[folder];
  else if (came && came.via === "reader") to = came.back || null;
  else if (came && came.via === "desk" && came.href && came.label) to = { label: came.label, href: came.href };

  // Somewhere that is not the page itself, or the mark's own way home.
  if (to && to.href === here()) to = null;
  if (to) {
    backs[folder] = to;
    write(BACKS, backs);
  }

  var home = document.getElementById("home");
  var label = back.querySelector(".bar-back-to");
  var homeName = back.getAttribute("data-home-name") || "";
  var said = to ? to.label : homeName;
  // With nowhere named, where the mark goes. `reader.js` gives the mark the key and the
  // text's language once the durable store has answered, which may be after this runs,
  // so the back follows the mark's address rather than reading it once.
  function asTheMark() {
    if (!to && home) back.setAttribute("href", home.getAttribute("href") || "/");
  }
  back.setAttribute("href", to ? to.href : "/");
  asTheMark();
  if (!to && home && window.MutationObserver) {
    new MutationObserver(asTheMark).observe(home, { attributes: true, attributeFilter: ["href"] });
  }
  if (label) label.textContent = said;
  var aria = back.getAttribute("data-aria") || "";
  if (aria) back.setAttribute("aria-label", aria.replace("{place}", said));
  // Served, there is a desk to go back to: `reader.js` shows the mark's link on the same
  // test, and off a disk this file has already stopped.
  back.hidden = false;

  window.addEventListener("pagehide", function () {
    if (handed) return write(FROM, handed);
    write(FROM, {
      via: "reader",
      label: plain(back.getAttribute("data-text") || document.title),
      // Without the hash: the reader opened again at its plain address goes back to where
      // the reader stopped (`targum:place`), and a hash would hold it at the word it
      // was opened at instead (#547).
      href: here(),
      back: to,
      at: Date.now(),
    });
  });
})();
