/* The Tanakh map (targum-internal#144; design.md §12, 2026-09-28).
 *
 * The page arrives with every chapter already drawn as a square and linked to where it is
 * read; this shades them. `/tanakh-map.json` says, for whoever is signed in, the whole
 * percentage of each chapter's running words they have marked known, and which chapters
 * this week's portion covers. A chapter it says nothing about is not measured — Aramaic,
 * or not a chapter of Hebrew at all — and keeps its own look rather than reading as 0%.
 *
 * The ramp's turns are the page's `data-steps`, written from `coverage.MAP_STEPS`, so the
 * square, the legend and the server count one way.
 *
 * The card says what a square is on hover and on focus. On a phone a square is seven
 * pixels, a thing to point at rather than to press, so a tap there shows the card and
 * the card's Read is the press; with a mouse the square itself is the link.
 *
 * The squares are one stop for the keyboard, not 929: Tab lands on the map, and the
 * arrows walk it — across a chapter at a time, up and down a row of ten, which is how
 * each book's squares are laid out.
 */
(function () {
  "use strict";

  var map = document.getElementById("tanakh-map");
  var legend = document.getElementById("tanakh-legend");
  var card = document.getElementById("tanakh-card");
  if (!map || !legend || !card) return;

  var strings = window.TargumStrings;
  function t(key, english, fill) {
    return strings ? strings.t(key, english, fill) : english;
  }
  function tn(key, count, one, other, fill) {
    return strings ? strings.tn(key, count, one, other, fill) : (count === 1 ? one : other).replace("{n}", count);
  }

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    var hash = path.indexOf("#");
    var bare = hash < 0 ? path : path.slice(0, hash);
    var tail = hash < 0 ? "" : path.slice(hash);
    return bare + (bare.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key) + tail;
  }

  var turns = (legend.getAttribute("data-steps") || "")
    .split(" ")
    .filter(Boolean)
    .map(Number);
  function step(percent) {
    var on = 0;
    for (var i = 0; i < turns.length; i++) if (percent >= turns[i]) on = i + 1;
    return on;
  }

  // What the sentence over the map counts: a chapter read with a word to look up now
  // and then rather than one a line.
  var NINE_IN_TEN = 90;

  var cells = Array.prototype.slice.call(map.querySelectorAll(".cell"));
  var shares = {};
  var week = {};
  var signedIn = false;

  cells.forEach(function (cell, at) {
    if (cell.tagName === "A") cell.setAttribute("href", keyed(cell.getAttribute("href")));
    cell.setAttribute("tabindex", at === 0 ? "0" : "-1");
  });

  function shade() {
    var within = 0;
    var measured = 0;
    cells.forEach(function (cell) {
      var ref = cell.getAttribute("data-ref");
      var percent = shares[ref];
      var away = cell.classList.contains("away");
      if (typeof percent === "number" && !away) {
        cell.setAttribute("data-step", String(step(percent)));
        measured += 1;
        if (percent >= NINE_IN_TEN) within += 1;
      } else {
        cell.removeAttribute("data-step");
      }
      cell.classList.toggle("week", !!week[ref]);
    });
    var sum = document.getElementById("tanakh-sum");
    if (!sum) return;
    if (!signedIn) {
      sum.textContent = t("tanakh.sum.signed-out", "Sign in, and the squares show how much of each chapter you'd understand.");
      return;
    }
    sum.textContent = measured
      ? tn(
          "tanakh.sum.within",
          within,
          "{n} chapter where you know nine words in ten or more.",
          "{n} chapters where you know nine words in ten or more."
        )
      : "";
  }

  function tell(cell) {
    var ref = cell.getAttribute("data-ref") || "";
    var verses = Number(cell.getAttribute("data-verses") || 0);
    var portion = cell.getAttribute("data-portion") || "";
    var aramaic = cell.classList.contains("aramaic");
    var away = cell.classList.contains("away");
    var percent = shares[ref];

    document.getElementById("card-title").textContent = ref;
    var meta = [tn("tanakh.card.verses", verses, "{n} verse", "{n} verses")];
    if (portion) meta.push(portion);
    if (week[ref]) meta.push(t("tanakh.card.this-week", "This week's portion"));
    document.getElementById("card-meta").textContent = meta.join(" · ");

    var said = "";
    if (away) said = t("tanakh.card.away", "Not in the library yet.");
    else if (aramaic) said = t("tanakh.card.aramaic", "Aramaic. We don't measure it against your Hebrew words yet.");
    else if (typeof percent === "number")
      said = t("tanakh.card.share", "You know {share}% of its words.", { share: percent });
    document.getElementById("card-share").textContent = said;

    var read = document.getElementById("card-read");
    read.hidden = away || cell.tagName !== "A";
    if (!read.hidden) {
      read.setAttribute("href", cell.getAttribute("href"));
      read.setAttribute("aria-label", t("tanakh.card.read", "Read {ref}", { ref: ref }));
    }
    card.hidden = false;
  }

  function cellOf(target) {
    return target && target.classList && target.classList.contains("cell") && map.contains(target) ? target : null;
  }

  map.addEventListener("mouseover", function (event) {
    var cell = cellOf(event.target);
    if (cell) tell(cell);
  });
  map.addEventListener("focusin", function (event) {
    var cell = cellOf(event.target);
    if (cell) tell(cell);
  });

  var coarse = window.matchMedia && window.matchMedia("(hover: none) and (pointer: coarse)");
  map.addEventListener("click", function (event) {
    var cell = cellOf(event.target);
    if (!cell) return;
    if (cell.tagName !== "A" || (coarse && coarse.matches)) {
      event.preventDefault();
      tell(cell);
    }
  });

  map.addEventListener("keydown", function (event) {
    var cell = cellOf(event.target);
    if (!cell) return;
    var at = cells.indexOf(cell);
    var to = {
      ArrowRight: at + 1,
      ArrowLeft: at - 1,
      ArrowDown: at + 10,
      ArrowUp: at - 10,
      Home: 0,
      End: cells.length - 1,
    }[event.key];
    if (to === undefined) return;
    event.preventDefault();
    to = Math.max(0, Math.min(cells.length - 1, to));
    cell.setAttribute("tabindex", "-1");
    cells[to].setAttribute("tabindex", "0");
    cells[to].focus();
  });

  shade();
  if (typeof fetch !== "function") return;
  fetch(keyed("/tanakh-map.json"), { credentials: "same-origin" })
    .then(function (answer) {
      return answer.json();
    })
    .then(function (said) {
      if (!said) return;
      signedIn = !!said.signedIn;
      shares = said.chapters || {};
      week = {};
      (said.week || []).forEach(function (ref) {
        week[ref] = true;
      });
      shade();
    })
    .catch(function () {
      /* nothing to shade with is the map as drawn: every chapter, unshaded */
    });
})();
