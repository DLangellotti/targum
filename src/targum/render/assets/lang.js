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

  // Hebrew first, then the rest by name.
  function order(codes, names) {
    return codes.slice().sort(function (a, b) {
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
        tag.className = "beta";
        tag.textContent = "beta";
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

  // Said once, where the language is chosen, rather than on every card.
  function betaNote(code, names) {
    return (
      (names[code] || code.toUpperCase()) +
      " is in beta. targum is built for Hebrew first — vowel points, dictionary forms " +
      "and difficulty all work best there, and less well here."
    );
  }

  window.TargumLang = {
    HOME: HOME,
    beta: beta,
    set: set,
    current: current,
    order: order,
    switcher: switcher,
    betaNote: betaNote,
  };
})();
