/* Which language you are reading in, kept in one place.
 *
 * targum is a Hebrew app. Everything in it — the vowel points, the dictionary forms,
 * the difficulty bands — was built for Hebrew and works best there; the other
 * languages come along because the same machinery mostly holds, and they are marked
 * as what they are. So Hebrew is the default and comes first in every list, and a
 * reader who never touches another language never sees a switcher at all.
 *
 * The choice is one preference shared by every page: picking Russian on the library
 * page and then opening your words shows you your Russian words.
 */
(function () {
  "use strict";

  var HOME = "he";
  var NAME = "targum:language";
  // And which language you read them *into*. A different question with a different
  // answer: the first is the language you are learning, the second the one you already
  // have. Local, like the first, for the same reason — what you read into is a record of
  // what you read, and it changes with a single press.
  var INTO = "targum:into";

  function beta(code) {
    return (code || "").split("-")[0].toLowerCase() !== HOME;
  }

  function stored(name) {
    try {
      return localStorage.getItem(name) || "";
    } catch (e) {
      return "";
    }
  }

  function set(code) {
    try {
      localStorage.setItem(NAME, code);
    } catch (e) {}
  }

  function into(code) {
    if (code === undefined) return stored(INTO);
    try {
      localStorage.setItem(INTO, code);
    } catch (e) {}
    return code;
  }

  // The one to show, given what this page can actually show. A remembered choice
  // wins, then Hebrew, then whatever there is.
  function current(codes) {
    var was = stored(NAME);
    if (was && codes.indexOf(was) >= 0) return was;
    if (codes.indexOf(HOME) >= 0) return HOME;
    return codes[0] || HOME;
  }

  /* Which languages the reading pages will show at all: the ones the account says are
   * being learned.
   *
   * Everything those pages are made of is Hebrew: the difficulty bands, the word levels,
   * the ulpan rungs. A Yiddish view of them is the same page with most of it missing, and
   * it is offered only to somebody who ticked Yiddish on their profile and was told there
   * that it is experimental. `sync.js` mirrors that answer into `targum:learning`, and
   * this reads it rather than waiting for it. Absent — signed out, or before the account
   * has answered — means Hebrew alone. Nothing is deleted by any of this: the words are
   * still in the store and still sync; they are simply not offered.
   */
  var LEARNING = "targum:learning";
  var SHOWN = [HOME];

  function learning() {
    try {
      var said = JSON.parse(localStorage.getItem(LEARNING) || "null");
      return said && said.length ? said : SHOWN;
    } catch (e) {
      return SHOWN;
    }
  }

  function offered(codes) {
    var shown = learning();
    return codes.filter(function (code) {
      return shown.indexOf((code || "").split("-")[0].toLowerCase()) >= 0;
    });
  }

  // Hebrew first, then the rest by name.
  function order(codes, names) {
    return offered(codes).sort(function (a, b) {
      if (a === HOME) return -1;
      if (b === HOME) return 1;
      return (names[a] || a).localeCompare(names[b] || b);
    });
  }

  /* One switcher, built the same way on the library page and the words page.
   *
   * `onPick` is handed the code. Nothing is drawn for a single language: a switcher
   * with one thing in it only asks a question that has no other answer.
   */
  function switcher(host, codes, names, chosen, onPick, options) {
    if (!host) return;
    var settings = options || {};
    // Which codes wear "experimental", asked rather than assumed. `beta` means "not
    // Hebrew", which is the right question about a language being read and the wrong one
    // about a language being read into: it would put the tag on English.
    var tag = settings.tag || beta;
    host.textContent = "";
    host.hidden = codes.length < 2;
    // A title, where the control is not self-evident from what it sits beside. The
    // language switcher needs none — it is the page's own subject — and one that changes
    // which language a column of definitions is printed in needs to say so.
    if (settings.label) {
      var said = document.createElement("span");
      said.className = "langs-label";
      said.textContent = settings.label;
      host.appendChild(said);
    }
    codes.forEach(function (code) {
      var button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("data-code", code);
      button.appendChild(document.createTextNode(names[code] || code.toUpperCase()));
      if (tag(code)) {
        var mark = document.createElement("span");
        // The class is the old word and the text is the one a reader sees. "beta" said
        // one thing on this tab and "Experimental" said another on the upload picker,
        // about the same language on the same day.
        mark.className = "beta";
        mark.textContent = "experimental";
        button.appendChild(mark);
      }
      var on = code === chosen;
      button.classList.toggle("on", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
      // Drawn here, remembered by the caller: this control is used for two different
      // preferences now, and one of them is not the language you are reading.
      button.addEventListener("click", function () {
        onPick(code);
      });
      host.appendChild(button);
    });
  }

  // Said once, where the language is chosen, rather than on every card. The same
  // sentence the upload picker's own note uses, because it is the same claim.
  function betaNote(code, names) {
    return (
      (names[code] || code.toUpperCase()) +
      " is experimental. Everything works best in Hebrew."
    );
  }

  window.TargumLang = {
    HOME: HOME,
    beta: beta,
    offered: offered,
    set: set,
    into: into,
    current: current,
    order: order,
    switcher: switcher,
    betaNote: betaNote,
  };
})();
