/* The first visit's one question (targum-internal#243).
 *
 * A stranger's browser says which language it speaks, and nothing else about them is
 * known. When it names a language the conversation can gloss in — the languages the
 * account may read into — and it is not English, the box asks once, in that language,
 * whether the lines under the Hebrew should be in it. Never a silent guess: what is
 * stored changes only on the press. Signed in, the answer goes to the account the way
 * the profile page's boxes do; signed out, it is kept in this browser as the language
 * to read into, which the account takes up on sign-in. Asked once per browser.
 */
(function () {
  "use strict";

  var host = document.getElementById("chat-first-lang");
  var ask = document.getElementById("chat-first-ask");
  var yes = document.getElementById("chat-first-yes");
  var no = document.getElementById("chat-first-no");
  if (!host || !ask || !yes || !no) return;

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  var ASKED = "targum:asked-read";
  var codes = window.TARGUM_INTO || [];
  var names = window.TARGUM_LANGUAGES || {};
  var lang = window.TargumLang;
  var sync = window.TargumSync;

  //: The question and its two answers, in the language it asks about. A language with
  //: no line of its own here is asked in English, by its name.
  var COPY = {
    ru: { ask: "Отвечать по-русски?", yes: "Да, по-русски", no: "English" },
  };

  function remembered(name) {
    try {
      return localStorage.getItem(name) || "";
    } catch (e) {
      return "";
    }
  }
  function remember(name, value) {
    try {
      if (window.targumKeep) window.targumKeep(name, value);
      else localStorage.setItem(name, value);
    } catch (e) {
      /* nothing to remember it in; the question stands until the next visit */
    }
  }

  // The language the browser speaks, if the conversation can gloss in it and it is not
  // the one it already glosses in.
  function guess() {
    var raw = (typeof navigator !== "undefined" && navigator.language) || "";
    var code = String(raw).split("-")[0].toLowerCase();
    if (!code || code === "en" || codes.indexOf(code) < 0) return "";
    return code;
  }

  function reads() {
    return (sync && sync.reads && sync.reads()) || null;
  }

  function decide() {
    var code = guess();
    var applies = !!code && !remembered(ASKED) && !(lang && lang.into());
    var already = reads();
    if (already && already.indexOf(code) >= 0) applies = false;
    if (!applies) {
      host.hidden = true;
      return;
    }
    var copy = COPY[code] || {
      ask: "Answers in " + (names[code] || code) + "?",
      yes: names[code] || code,
      no: "English",
    };
    ask.textContent = copy.ask;
    yes.textContent = copy.yes;
    no.textContent = copy.no;
    yes.onclick = function () {
      answer(code);
    };
    no.onclick = function () {
      answer("en");
    };
    host.hidden = false;
  }

  function answer(code) {
    remember(ASKED, "1");
    if (lang && lang.into) lang.into(code);
    host.hidden = true;
    var who = sync && sync.who;
    if (!who || !who.signedIn) return;
    fetch(keyed("/account/languages"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Targum-Key": key },
      body: JSON.stringify({ learning: who.learning || ["he"], reads: [code] }),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function () {
        if (sync && sync.start) sync.start();
      })
      .catch(function () {
        /* the browser keeps the answer; the account hears it next time */
      });
  }

  decide();
  if (sync && sync.onChange) sync.onChange(decide);

  window.TargumFirst = { decide: decide, guess: guess };
})();
