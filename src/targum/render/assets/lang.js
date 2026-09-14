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
 *
 * Since 2026-09-13 it is chosen in one place, a menu at the end of the nav on every desk
 * page, and kept on the account so another device opens in it too (design.md §13). The
 * pages that switched with a row of tabs still call `switcher` with the same arguments;
 * pointed at the nav's host it draws the menu, and pointed anywhere else — the
 * definition-language control on Your Words — it still draws tabs.
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
    // The nav's menu says which language it is in; a page that changed the language by
    // some other control (the Add page's picker) is heard here.
    try {
      window.dispatchEvent(new CustomEvent("targum:language", { detail: code }));
    } catch (e) {}
  }

  /* A choice the reader made, as opposed to a page settling on one as it loads: kept on
   * the account as well. Only the menu calls this, so opening a page never writes. */
  function remember(code) {
    set(code);
    if (window.TargumSync && typeof window.TargumSync.language === "function") {
      window.TargumSync.language(code);
    }
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

  /* The nav's host, which draws a menu rather than tabs. */
  var NAV = "langs";

  /* A small flag beside each language in the menu (2026-09-14, design.md §12 — which
   * reverses "no flags" for this one place). The flag of the country whose language it
   * is, in that flag's own colours, drawn rather than typed: an emoji flag is an emoji,
   * and §6 has none. Hebrew is Israel's. Yiddish and Aramaic have no country, so they
   * have no flag, and keep the flag's width so the names still line up. */
  var FLAGS = {
    he:
      '<rect width="18" height="12" fill="#fff"/>' +
      '<rect y="1.3" width="18" height="1.5" fill="#0038b8"/>' +
      '<rect y="9.2" width="18" height="1.5" fill="#0038b8"/>' +
      '<path d="M9 3.4 11.6 7.9H6.4ZM9 8.6 6.4 4.1H11.6Z" fill="none" stroke="#0038b8" stroke-width="0.7"/>',
    fr:
      '<rect width="6" height="12" fill="#0055a4"/>' +
      '<rect x="6" width="6" height="12" fill="#fff"/>' +
      '<rect x="12" width="6" height="12" fill="#ef4135"/>',
    it:
      '<rect width="6" height="12" fill="#009246"/>' +
      '<rect x="6" width="6" height="12" fill="#fff"/>' +
      '<rect x="12" width="6" height="12" fill="#ce2b37"/>',
    ru:
      '<rect width="18" height="4" fill="#fff"/>' +
      '<rect y="4" width="18" height="4" fill="#0039a6"/>' +
      '<rect y="8" width="18" height="4" fill="#d52b1e"/>',
  };

  function flag(code) {
    var box = document.createElement("span");
    box.className = "lang-flag";
    box.setAttribute("aria-hidden", "true");
    var drawn = FLAGS[String(code || "").split("-")[0].toLowerCase()];
    if (drawn) {
      box.innerHTML = '<svg viewBox="0 0 18 12" focusable="false">' + drawn + "</svg>";
    } else {
      box.className += " none";
    }
    return box;
  }

  /* One switcher, built the same way on the library page and the words page.
   *
   * `onPick` is handed the code. Nothing is drawn for a single language: a switcher
   * with one thing in it only asks a question that has no other answer.
   */
  function switcher(host, codes, names, chosen, onPick, options) {
    if (!host) return;
    if (host.id === NAV) return menu(host, codes, names, chosen, onPick, options);
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

  /* The menu at the end of the nav (2026-09-13): the language this page is in, and a
   * list of the reader's languages under it.
   *
   * Every language the account learns is listed, whatever the page had to show in it: a
   * switcher that left out a language with nothing on the shelf yet could never be used
   * to go and add the first thing. The page's own languages come too, for a text in a
   * language the account has since stopped learning. The last item goes to where the
   * list itself is chosen.
   */
  function menu(host, codes, names, chosen, onPick, options) {
    var settings = options || {};
    var tag = settings.tag || beta;
    var all = order(
      learning().concat(codes).filter(function (code, at, list) {
        return list.indexOf(code) === at;
      }),
      names
    );
    if (all.indexOf(chosen) < 0 && chosen) all.unshift(chosen);
    host.textContent = "";
    host.hidden = all.length < 2;
    host.classList.add("lang-menu");

    var open = document.createElement("button");
    open.type = "button";
    open.className = "lang-open";
    open.setAttribute("aria-haspopup", "menu");
    open.setAttribute("aria-expanded", "false");
    open.setAttribute("aria-label", "Language: " + (names[chosen] || chosen));
    var label = document.createElement("span");
    label.className = "lang-name";
    label.textContent = names[chosen] || String(chosen || "").toUpperCase();
    open.appendChild(flag(chosen));
    open.appendChild(label);
    host.appendChild(open);

    var panel = document.createElement("div");
    panel.className = "lang-panel";
    panel.setAttribute("role", "menu");
    panel.hidden = true;
    all.forEach(function (code) {
      var item = document.createElement("button");
      item.type = "button";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("data-code", code);
      item.setAttribute("aria-checked", code === chosen ? "true" : "false");
      var named = document.createElement("span");
      named.className = "lang-item";
      named.appendChild(flag(code));
      named.appendChild(document.createTextNode(names[code] || code.toUpperCase()));
      item.appendChild(named);
      if (tag(code)) {
        var mark = document.createElement("span");
        mark.className = "beta";
        mark.textContent = "experimental";
        item.appendChild(mark);
      }
      item.addEventListener("click", function () {
        close();
        if (code === chosen) return;
        remember(code);
        onPick(code);
      });
      panel.appendChild(item);
    });
    var more = document.createElement("a");
    more.className = "lang-more";
    more.href = "/you#languages";
    more.setAttribute("role", "menuitem");
    more.textContent = "Your languages";
    panel.appendChild(more);
    host.appendChild(panel);

    function close() {
      panel.hidden = true;
      open.setAttribute("aria-expanded", "false");
      open.classList.remove("on");
    }
    open.addEventListener("click", function (event) {
      event.stopPropagation();
      var opening = panel.hidden;
      panel.hidden = !opening;
      open.setAttribute("aria-expanded", opening ? "true" : "false");
      open.classList.toggle("on", opening);
    });
    if (!host.getAttribute("data-menu-bound")) {
      host.setAttribute("data-menu-bound", "1");
      document.addEventListener("click", function (event) {
        var inside = host.contains && host.contains(event.target);
        if (!inside) {
          var shown = host.querySelector && host.querySelector(".lang-panel");
          var button = host.querySelector && host.querySelector(".lang-open");
          if (shown) shown.hidden = true;
          if (button) button.setAttribute("aria-expanded", "false");
        }
      });
      document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        var shown = host.querySelector && host.querySelector(".lang-panel");
        if (shown && !shown.hidden) {
          shown.hidden = true;
          var button = host.querySelector(".lang-open");
          if (button) {
            button.setAttribute("aria-expanded", "false");
            button.focus();
          }
        }
      });
      // A language set by another control on the page: the label follows it.
      window.addEventListener("targum:language", function (event) {
        var code = event && event.detail;
        var name = host.querySelector && host.querySelector(".lang-name");
        if (name && code) name.textContent = names[code] || String(code).toUpperCase();
        var button = host.querySelector && host.querySelector(".lang-open");
        var shown = button && button.querySelector && button.querySelector(".lang-flag");
        if (button && shown && code) button.replaceChild(flag(code), shown);
      });
    }
  }

  /* A page that never draws its own switcher — the conversation — still has the menu:
   * the reader's languages, and a press that opens the page again in the one chosen,
   * which for the conversation is that language's own conversation. Drawn once the page
   * has had its turn, so a page that does draw one is not drawn over. */
  function mountDefault() {
    var host = document.getElementById(NAV);
    if (!host || host.children.length) return;
    var codes = learning();
    var names = window.TARGUM_LANGUAGES || {};
    switcher(host, codes, names, current(codes), function () {
      window.location.reload();
    });
  }
  if (typeof document !== "undefined" && document.addEventListener) {
    var later = function () {
      setTimeout(mountDefault, 0);
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", later);
    else later();
  }

  // Said once, where the language is chosen, rather than on every card. The same
  // sentence the upload picker's own note uses, because it is the same claim.
  function betaNote(code, names) {
    return (
      (names[code] || code.toUpperCase()) +
      " is new here, and still experimental."
    );
  }

  window.TargumLang = {
    HOME: HOME,
    beta: beta,
    offered: offered,
    set: set,
    remember: remember,
    learning: learning,
    into: into,
    current: current,
    order: order,
    switcher: switcher,
    betaNote: betaNote,
  };
})();
