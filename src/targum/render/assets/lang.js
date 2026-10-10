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

  /* Words said through the page's `TargumStrings` — `strings.js` on a desk page, and
     `reader.js`'s own in a reader, which arrives after this file — so it is looked up when
     a thing is said rather than when this loads. Where there is none, the English here
     (targum-internal#184). */
  function t(key, english, fill) {
    var said = window.TargumStrings;
    if (said) return said.t(key, english, fill);
    return english.replace(/\{(\w+)\}/g, function (all, name) {
      return fill && Object.prototype.hasOwnProperty.call(fill, name) ? String(fill[name]) : all;
    });
  }

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

  /* How far along each language is, as the menu badges it (David, 2026-10-08; design.md
     §12, "A language wears how far along it is"). A badge and nothing else: no note says
     what Beta means. A language not named here wears none. */
  var STATUS = {
    he: "beta",
    ru: "alpha",
    it: "alpha",
    fr: "alpha",
    arc: "experimental",
    yi: "experimental",
  };

  function status(code) {
    return STATUS[String(code || "").split("-")[0].toLowerCase()] || "";
  }

  function badge(code) {
    var which = status(code);
    if (!which) return null;
    var mark = document.createElement("span");
    mark.className = "lang-status is-" + which;
    mark.textContent =
      which === "beta"
        ? t("lang.status.beta", "Beta")
        : which === "alpha"
          ? t("lang.status.alpha", "Alpha")
          : t("lang.status.experimental", "Experimental");
    return mark;
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
      return window.TargumSync.language(code);
    }
    return null;
  }

  function into(code) {
    if (code === undefined) return stored(INTO);
    try {
      localStorage.setItem(INTO, code);
    } catch (e) {}
    return code;
  }

  // The one to show, given what this page has something in. A remembered choice wins,
  // then Hebrew, then whatever there is.
  //
  // A remembered choice wins where the reader learns it, too, and not only where this
  // page has something in it (2026-09-14). The menu lists every language learned, so a
  // language with nothing built or kept in it yet can be chosen — and a page asking only
  // of its own list then settled on Hebrew and wrote Hebrew back, so every change of page
  // put the reader back in Hebrew.
  //
  // And the language this page arrived carrying wins outright (2026-10-07): it was
  // pressed a page ago, and the account's list may not have heard of it yet.
  function current(codes) {
    var was = stored(NAME);
    if (carriedIn && was === carriedIn) return was;
    if (was && (codes.indexOf(was) >= 0 || learning().indexOf(was) >= 0)) return was;
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

  /* A text's language, carried in from the corner of its reader (design.md §12,
   * 2026-10-07).
   *
   * David left a Russian text he had imported over the connector by the mark in its
   * corner and landed on Learn in Hebrew: the mark went to `/` and said nothing, so the
   * page opened in whatever the menu last held. Now the reader's ways out carry
   * `?learning=<code>`, and this takes it as the menu takes a press — kept in this
   * browser here, and on the account by `sync.js` once it knows who is signed in, with
   * leave to turn the language on. Not `?lang=`, which is the language a public page
   * speaks: the front door would have answered a signed-out visitor in Russian chrome.
   *
   * Only a language targum has a desk for. The rest — a text in English, Spanish, Latin
   * — leaves the page in the language it was already in. The list is `READING` in
   * `translate/prompts.py`, which `test_lang_js.py` holds this to. The word comes off the
   * address either way, so a reload or a bookmark is the plain page and not a second
   * press. A reader built before this carries nothing, and goes home as it always did.
   */
  var CARRY = "learning";
  var LEARNABLE = ["he", "arc", "yi", "fr", "ru", "it"];
  var carriedIn = "";

  function arrived() {
    var code = "";
    try {
      var url = new URL(location.href);
      if (!url.searchParams.has(CARRY)) return "";
      code = String(url.searchParams.get(CARRY) || "").split("-")[0].toLowerCase();
      url.searchParams.delete(CARRY);
      history.replaceState(history.state, "", url.pathname + url.search + url.hash);
    } catch (e) {
      return "";
    }
    return LEARNABLE.indexOf(code) >= 0 ? code : "";
  }

  carriedIn = arrived();
  if (carriedIn) {
    set(carriedIn);
    // On the list in this browser as well, so the next page can be in it before the
    // account has answered — and at all, where nobody is signed in to answer.
    var listed = learning();
    if (listed.indexOf(carriedIn) < 0) {
      try {
        localStorage.setItem(LEARNING, JSON.stringify(listed.concat([carriedIn])));
      } catch (e) {}
    }
  }

  function carried() {
    return carriedIn;
  }

  /* The nav's host, which draws a menu rather than tabs. */
  var NAV = "langs";

  /* A small flag beside each language in the menu, drawn back on David's word
   * (2026-10-10: "bring back the flags here"; design.md §12). The flag of the country
   * whose language it is, in that flag's own colours, drawn rather than typed: an emoji
   * flag is an emoji, and §6 has none. Hebrew is Israel's. Yiddish and Aramaic have no
   * country, and wear the language flags David chose for them on 2026-09-14: Yiddish the
   * white flag with two black stripes and a menorah, Aramaic the Jewish Babylonian
   * Aramaic proposal, two blue stripes round the gate of the Vilna Talmud's title page.
   * A code with no flag keeps the width so the names still line up. */
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
    yi:
      '<rect width="18" height="12" fill="#fff"/>' +
      '<rect y="1.125" width="18" height="1.875" fill="#000"/>' +
      '<rect y="9" width="18" height="1.875" fill="#000"/>' +
      '<g fill="#000" transform="translate(0.75 0) scale(0.025)">' +
      '<path d="M230.694,172.92A99.306,99.306 0 1,0 429.306,172.92H419.851A89.851,89.851 0 1,1 240.149,172.92z"/>' +
      '<path d="M259.256,173.35A70.744,70.744 0 1,0 400.744,173.35H391.223A61.223,61.223 0 1,1 268.777,173.35z"/>' +
      '<path d="M288.157,172.92A41.843,41.843 0 1,0 371.843,172.92H362.388A32.388,32.388 0 1,1 297.612,172.92z"/>' +
      '<path d="M278.562,317.879V324.35H381.438V317.879L334.727,307.466V165.639H325.273V307.466z"/>' +
        '<path transform="translate(0 0)" d="M223.357,161.017H247.489L240.151,170.934H230.696z"/>' +
        '<path transform="translate(28.731 0)" d="M223.357,161.017H247.489L240.151,170.934H230.696z"/>' +
        '<path transform="translate(57.461 0)" d="M223.357,161.017H247.489L240.151,170.934H230.696z"/>' +
        '<path transform="translate(94.577 -7.261)" d="M223.357,161.017H247.489L240.151,170.934H230.696z"/>' +
        '<path transform="translate(131.693 0)" d="M223.357,161.017H247.489L240.151,170.934H230.696z"/>' +
        '<path transform="translate(160.424 0)" d="M223.357,161.017H247.489L240.151,170.934H230.696z"/>' +
        '<path transform="translate(189.154 0)" d="M223.357,161.017H247.489L240.151,170.934H230.696z"/>' +
      "</g>",
    arc:
      '<rect width="18" height="12" fill="#fff"/>' +
      '<rect y="1.25" width="18" height="1.45" fill="#0000f5"/>' +
      '<rect y="9.45" width="18" height="1.45" fill="#0000f5"/>' +
      '<g fill="#3a3a3a">' +
      '<path d="M6.9 4.25 8.8 3.4V3.9L7.5 4.25ZM11.1 4.25 9.2 3.4V3.9L10.5 4.25Z"/>' +
      '<rect x="6.8" y="4.25" width="4.4" height="0.5"/>' +
      '<rect x="7.05" y="4.75" width="0.5" height="3.6"/>' +
      '<rect x="7.8" y="4.75" width="0.4" height="3.6"/>' +
      '<rect x="9.8" y="4.75" width="0.4" height="3.6"/>' +
      '<rect x="10.45" y="4.75" width="0.5" height="3.6"/>' +
      '<rect x="6.8" y="8.35" width="4.4" height="0.65"/>' +
      "</g>" +
      '<path d="M8.2 7.75H9.8M8.2 5.1Q9 5.9 9.8 5.1" fill="none" stroke="#3a3a3a" stroke-width="0.3"/>',
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

  /* The greeting each language is met with in the menu, at the far side in the reading
   * serif and its own script, as board LangMenuDesk draws it (design.md §12, "The boards
   * are the desk", 2026-10-09), after the flag. */
  var GREETINGS = {
    he: ["שָׁלוֹם", "rtl"],
    arc: ["בְּקַדְמִין", "rtl"],
    yi: ["אַ גוטן טאָג", "rtl"],
    fr: ["Bonjour", "ltr"],
    it: ["Ciao", "ltr"],
    ru: ["Здравствуйте", "ltr"],
  };

  function greeting(code) {
    var key = String(code || "").split("-")[0].toLowerCase();
    var own = GREETINGS[key];
    if (!own) return null;
    var span = document.createElement("bdi");
    span.className = "lang-greeting";
    span.setAttribute("lang", key);
    span.setAttribute("dir", own[1]);
    span.textContent = own[0];
    return span;
  }

  /* Each language in its own name as well as English's (2026-09-14): a Russian reader
   * choosing what their translations are in was offered "Russian". The English name
   * leads, because the chrome is English; the language's own follows, in its own face. */
  var NATIVE = {
    he: ["עברית", "rtl"],
    arc: ["ארמית", "rtl"],
    yi: ["ייִדיש", "rtl"],
    fr: ["Français", "ltr"],
    it: ["Italiano", "ltr"],
    ru: ["Русский", "ltr"],
    en: ["English", "ltr"],
  };

  function native(code) {
    var key = String(code || "").split("-")[0].toLowerCase();
    var own = NATIVE[key];
    if (!own) return null;
    var span = document.createElement("bdi");
    span.className = "lang-native";
    span.setAttribute("lang", key);
    span.setAttribute("dir", own[1]);
    span.textContent = own[0];
    return span;
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
      // The desk's tab (chrome.css): a tinted pill, the chosen one filled.
      button.className = "tab";
      button.setAttribute("role", "tab");
      button.setAttribute("data-code", code);
      button.appendChild(document.createTextNode(names[code] || code.toUpperCase()));
      if (tag(code)) {
        var mark = document.createElement("span");
        // The class is the old word and the text is the one a reader sees. "beta" said
        // one thing on this tab and "Experimental" said another on the upload picker,
        // about the same language on the same day.
        mark.className = "beta";
        mark.textContent = t("lang.experimental", "experimental");
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
   * language the account has since stopped learning.
   *
   * Since 2026-10-09 (design.md §12, "The boards are the desk"; board LangMenuDesk) the
   * menu is drawn for a reader of one language too, with the language's badge on the
   * button and no flag anywhere. The panel is two groups: **Your languages**, the ones
   * learned, a tick on the one the page is in; and under a rule **Start another
   * language**, the rest targum teaches, each of which a press turns on and opens. Each
   * row carries its badge and, at the far side, the greeting it is met with.
   */
  function menu(host, codes, names, chosen, onPick, options) {
    var all = order(
      learning().concat(codes).filter(function (code, at, list) {
        return list.indexOf(code) === at;
      }),
      names
    );
    if (all.indexOf(chosen) < 0 && chosen) all.unshift(chosen);
    var others = LEARNABLE.filter(function (code) {
      return all.indexOf(code) < 0;
    });
    host.textContent = "";
    host.hidden = !all.length;
    host.classList.add("lang-menu");

    var open = document.createElement("button");
    open.type = "button";
    open.className = "lang-open";
    open.setAttribute("aria-haspopup", "menu");
    open.setAttribute("aria-expanded", "false");
    open.setAttribute("aria-label", t("lang.menu.label", "Language: {language}", { language: names[chosen] || chosen }));
    var label = document.createElement("span");
    label.className = "lang-name";
    label.textContent = names[chosen] || String(chosen || "").toUpperCase();
    open.appendChild(label);
    var worn = badge(chosen);
    if (worn) open.appendChild(worn);
    host.appendChild(open);

    var panel = document.createElement("div");
    panel.className = "lang-panel";
    panel.setAttribute("role", "menu");
    panel.setAttribute("aria-label", t("lang.menu.panel", "The language you're learning"));
    panel.hidden = true;

    function row(code, role) {
      var item = document.createElement("button");
      item.type = "button";
      item.setAttribute("role", role);
      item.setAttribute("data-code", code);
      if (role === "menuitemradio") item.setAttribute("aria-checked", code === chosen ? "true" : "false");
      else item.className = "lang-start";
      var named = document.createElement("span");
      named.className = "lang-item";
      var tick = document.createElement("span");
      tick.className = "lang-tick";
      tick.setAttribute("aria-hidden", "true");
      tick.textContent = code === chosen ? "\u2713" : "";
      named.appendChild(tick);
      named.appendChild(flag(code));
      named.appendChild(document.createTextNode(names[code] || code.toUpperCase()));
      var mark = badge(code);
      if (mark) named.appendChild(mark);
      item.appendChild(named);
      var said = greeting(code);
      if (said) item.appendChild(said);
      return item;
    }
    function heading(text) {
      var head = document.createElement("p");
      head.className = "lang-head";
      head.textContent = text;
      panel.appendChild(head);
    }

    heading(t("lang.menu.yours", "Your languages"));
    all.forEach(function (code) {
      var item = row(code, "menuitemradio");
      item.addEventListener("click", function () {
        close();
        if (code === chosen) return;
        onPick(code, remember(code));
      });
      panel.appendChild(item);
    });
    if (others.length) {
      var rule = document.createElement("hr");
      rule.className = "lang-rule";
      panel.appendChild(rule);
      heading(t("lang.menu.start", "Start another language"));
      others.forEach(function (code) {
        var item = row(code, "menuitem");
        // Turned on in this browser and on the account, then opened as any press is.
        item.addEventListener("click", function () {
          close();
          var listed = learning();
          if (listed.indexOf(code) < 0) {
            try {
              localStorage.setItem(LEARNING, JSON.stringify(listed.concat([code])));
            } catch (e) {}
          }
          set(code);
          var saved =
            window.TargumSync && typeof window.TargumSync.language === "function"
              ? window.TargumSync.language(code, true)
              : null;
          onPick(code, saved);
        });
        panel.appendChild(item);
      });
    }
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
        var was = button && button.querySelector && button.querySelector(".lang-status");
        var now = code ? badge(code) : null;
        if (button && was) button.removeChild(was);
        if (button && now) button.appendChild(now);
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
    // Reloaded once the account has the new language, not before: the page asks the
    // server for this language's conversations, and a reload that raced the save was
    // answered in the old one and drew an empty list (2026-09-14).
    switcher(host, codes, names, current(codes), function (code, saved) {
      var reload = function () {
        window.location.reload();
      };
      if (saved && typeof saved.then === "function") saved.then(reload, reload);
      else reload();
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
    return t("lang.beta-note", "{language} is new here, and still experimental.", {
      language: names[code] || code.toUpperCase(),
    });
  }

  window.TargumLang = {
    HOME: HOME,
    beta: beta,
    status: status,
    // The badge itself, for the arrival's first question, which wears the same ones.
    badge: badge,
    offered: offered,
    set: set,
    remember: remember,
    learning: learning,
    into: into,
    current: current,
    carried: carried,
    order: order,
    switcher: switcher,
    betaNote: betaNote,
    native: native,
  };
})();
