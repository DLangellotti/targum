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

  function beta(code) {
    return (code || "").split("-")[0].toLowerCase() !== HOME;
  }

  function stored() {
    try {
      return localStorage.getItem(NAME) || "";
    } catch (e) {
      return "";
    }
  }

  function set(code) {
    try {
      localStorage.setItem(NAME, code);
    } catch (e) {}
  }

  // The one to show, given what this page can actually show. A remembered choice
  // wins, then Hebrew, then whatever there is.
  function current(codes) {
    var was = stored();
    if (was && codes.indexOf(was) >= 0) return was;
    if (codes.indexOf(HOME) >= 0) return HOME;
    return codes[0] || HOME;
  }

  /* Which languages the reading pages will show at all. One, for now.
   *
   * Everything those pages are made of is Hebrew: the difficulty bands, the word levels,
   * the ulpan rungs. A Russian view of them was the same page with most of it missing and
   * a switcher inviting you into it. Nothing is deleted by this — the words are still in
   * the store and still sync — they are simply not offered until the rest catches up.
   *
   * To offer a language again, add its code here. Nothing else has to change: the
   * switcher draws itself for two and hides itself for one.
   */
  var SHOWN = [HOME];

  function offered(codes) {
    return codes.filter(function (code) {
      return SHOWN.indexOf((code || "").split("-")[0].toLowerCase()) >= 0;
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
  function switcher(host, codes, names, chosen, onPick) {
    if (!host) return;
    host.textContent = "";
    host.hidden = codes.length < 2;
    codes.forEach(function (code) {
      var button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("data-code", code);
      button.appendChild(document.createTextNode(names[code] || code.toUpperCase()));
      if (beta(code)) {
        var tag = document.createElement("span");
        // The class is the old word and the text is the one a reader sees. "beta" said
        // one thing on this tab and "Experimental" said another on the upload picker,
        // about the same language on the same day.
        tag.className = "beta";
        tag.textContent = "experimental";
        button.appendChild(tag);
      }
      var on = code === chosen;
      button.classList.toggle("on", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
      button.addEventListener("click", function () {
        set(code);
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
    current: current,
    order: order,
    switcher: switcher,
    betaNote: betaNote,
  };
})();
