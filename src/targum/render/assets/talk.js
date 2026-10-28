/* Talk to targum, from anywhere (2026-09-11).
 *
 * The conversation is not a page you go to: one pill, fixed at the foot of every page,
 * opens it as a drawer — from the edge on a laptop, up from the foot on a phone — holding
 * the conversation page framed without its bar (`/chat?embed=1`). Loaded the first time
 * it is opened and never before; closed by its own button, the scrim or Escape; left open
 * across pages once opened (`targum:talk`), since somebody mid-conversation who follows a
 * link has not finished talking. Only a press dims the page under it: a drawer a page
 * brings back because it was left open comes back beside the page, undimmed. Not on a
 * phone, where it would come back as a sheet over the page: there leaving a page closes
 * it (QA 2026-10-11, D7).
 *
 * A text the conversation offers opens the reader itself, from whatever page holds the
 * drawer (Learn's sheet, which held it in place, went with Learn on 2026-10-08). Nothing
 * is taken from a message that did not come from the drawer's own frame on this origin.
 */
(function () {
  "use strict";

  var pill = document.getElementById("talk-open");
  var drawer = document.getElementById("talk-drawer");
  var frame = document.getElementById("talk-frame");
  var close = document.getElementById("talk-close");
  var scrim = document.getElementById("talk-scrim");
  if (!pill || !drawer || !frame) return;

  // How far in from the window's end edge the pill reaches, in `--talk-room`, so a page
  // can keep its controls out from under it (targum-internal#379: at 1024–1280px the
  // shelf's right-hand cards scrolled their + and ⋯ beneath it). Measured rather than
  // guessed: the pill is as wide as its words, and Russian's are longer. While the
  // drawer is open the pill is put away, and the room is kept rather than let the page
  // jump under the drawer.
  function measureRoom() {
    var box = pill.getBoundingClientRect();
    if (!box.width) return;
    var rtl = getComputedStyle(pill).direction === "rtl";
    var reach = rtl ? box.right : document.documentElement.clientWidth - box.left;
    document.documentElement.style.setProperty("--talk-room", Math.max(0, Math.ceil(reach)) + "px");
  }
  measureRoom();
  window.addEventListener("resize", measureRoom);
  if (window.ResizeObserver) new ResizeObserver(measureRoom).observe(pill);

  // The reader is a built page with no key baked in: it carries the one it was served
  // with in its own address, as `reader.js` does. Off a disk there is nothing to talk
  // to, and the pill stays hidden.
  var key = window.TARGUM_KEY || "";
  if (!key) {
    try {
      key = new URLSearchParams(window.location.search).get("k") || "";
    } catch (e) {
      key = "";
    }
  }
  if (!/^https?:$/.test(window.location.protocol)) return;
  pill.hidden = false;
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  var OPEN = "targum:talk";
  var loaded = false;

  // Where the reader is, in a reader (2026-09-11): the text, the section, the sentence.
  // Said to the frame whenever it changes and once more when the frame arrives, so the
  // conversation can answer about what is in front of them.
  var reading = null;
  function tellReading() {
    if (!reading || !loaded || !frame.contentWindow) return;
    try {
      frame.contentWindow.postMessage({ type: "targum:reading", about: reading }, window.location.origin);
    } catch (e) {
      /* the frame is not ours yet; the next word will reach it */
    }
  }
  document.addEventListener("targum:where", function (event) {
    reading = event.detail || null;
    tellReading();
  });
  frame.addEventListener("load", function () {
    if (!reading && window.TargumReader && window.TargumReader.where) reading = window.TargumReader.where();
    tellReading();
  });

  // Which language the page holding the drawer is in, and so which conversation the
  // drawer shows (2026-09-14). The frame loads once and stays up, and the pages switch
  // language in place, so the conversation read the language for itself as it loaded and
  // was then one switch behind the page for as long as the page was open: Italian under
  // a Hebrew header, and "Write in Hebrew" under an Italian one. Every page says its
  // language with `targum:language` as it settles and when the menu changes it; the
  // drawer is told the same, as it loads and after.
  var language = "";
  function holding() {
    if (language) return language;
    var lang = window.TargumLang;
    return lang && lang.learning ? lang.current(lang.learning()) : "";
  }
  function tellLanguage() {
    var code = holding();
    if (!code || !loaded || !frame.contentWindow) return;
    try {
      frame.contentWindow.postMessage({ type: "targum:language", code: code }, window.location.origin);
    } catch (e) {
      /* the frame is not ours yet; its load will be told */
    }
  }
  window.addEventListener("targum:language", function (event) {
    var code = event && event.detail;
    if (typeof code !== "string" || !code || code === language) return;
    language = code;
    tellLanguage();
  });
  frame.addEventListener("load", tellLanguage);

  /* Signed out — the session gone while the page stayed open — the frame would land on
     sign-in, which refuses to be framed, and the drawer would be a blank sheet. Instead
     it says so, with Sign in that comes back to this page (#472 B4). */
  var out = document.getElementById("talk-out");
  var outDoor = document.getElementById("talk-sign-in");
  function signedOut(on) {
    if (!out) return false;
    out.hidden = !on;
    frame.hidden = on;
    if (on && outDoor) {
      outDoor.href = "/account/signin?next=" + encodeURIComponent(window.location.pathname + window.location.search);
    }
    return on;
  }
  function knownSignedOut() {
    var sync = window.TargumSync;
    return !!(sync && sync.signedOut);
  }

  function load() {
    if (loaded) return;
    if (knownSignedOut() && signedOut(true)) return;
    signedOut(false);
    loaded = true;
    var src = frame.getAttribute("data-src") || keyed("/chat?embed=1");
    var code = holding();
    if (code) src += (src.indexOf("?") < 0 ? "?" : "&") + "language=" + encodeURIComponent(code);
    frame.setAttribute("src", src);
  }

  // Until the conversation has loaded, the frame holds an empty document that says it is
  // complete, so readiness is the frame's own load event and not its readyState.
  var wantsFocus = false;
  var frameReady = false;
  function focusBox() {
    if (out && !out.hidden && outDoor) {
      outDoor.focus();
      return;
    }
    if (!frameReady) {
      wantsFocus = true;
      return;
    }
    frame.focus();
    // Under a thumb the box is left alone: focusing it would put the keyboard up over a
    // sheet the reader may only want to read.
    if (window.matchMedia && window.matchMedia("(hover: none) and (pointer: coarse)").matches) return;
    frame.contentWindow.postMessage({ type: "targum:focus" }, window.location.origin);
  }
  frame.addEventListener("load", function () {
    if (!frame.getAttribute("src")) return;
    // The conversation, or something that would not be framed (sign-in, an error page):
    // a frame we cannot read, or one that is not the conversation, is a door back in.
    var ours = false;
    try {
      ours = !!frame.contentDocument && /^\/chat\/?$/.test(frame.contentWindow.location.pathname);
    } catch (e) {
      ours = false;
    }
    if (!ours && out) {
      loaded = false;
      frameReady = false;
      signedOut(true);
      if (wantsFocus && !drawer.hidden && outDoor) outDoor.focus();
      wantsFocus = false;
      return;
    }
    frameReady = true;
    if (!wantsFocus || drawer.hidden) return;
    wantsFocus = false;
    focusBox();
  });

  /* Pressed open, the drawer is modal: the page behind the scrim is dimmed and cannot be
     clicked, so it cannot be tabbed either (§14.3, targum-internal#472 B3). Everything
     beside the drawer's own line of ancestors is made `inert` while it is open, and given
     back as it closes. A drawer brought back undimmed stays non-modal. */
  function holdFocus(on) {
    if (on) drawer.setAttribute("aria-modal", "true");
    else drawer.removeAttribute("aria-modal");
    if (!on) {
      Array.prototype.forEach.call(document.querySelectorAll("[data-talk-inert]"), function (node) {
        node.removeAttribute("data-talk-inert");
        node.inert = false;
        node.removeAttribute("inert");
      });
      return;
    }
    for (var at = drawer; at && at.parentElement && at !== document.body; at = at.parentElement) {
      Array.prototype.forEach.call(at.parentElement.children, function (node) {
        if (node === at || node === scrim || node.tagName === "SCRIPT" || node.inert) return;
        node.setAttribute("data-talk-inert", "1");
        node.inert = true;
        node.setAttribute("inert", "");
      });
    }
  }

  var leaving = null;
  /* `restored` is the drawer brought back by a page because it was left open on the one
     before, rather than pressed open on this one. It comes back as a panel beside the
     page and does not dim it: the scrim says "this is what you are doing now", and a
     reader who followed a link out of a conversation is reading the page they came to
     (audit 2, 2026-10-09; design.md §12, "A drawer left open comes back undimmed"). */
  function show(on, restored, byHistory) {
    if (on && !restored && !byHistory) stepIn();
    if (!on && !byHistory) stepOut();
    if (on) {
      if (!reading && window.TargumReader && window.TargumReader.where) reading = window.TargumReader.where();
      load();
      tellReading();
    }
    clearTimeout(leaving);
    drawer.classList.remove("leaving");
    if (on) drawer.hidden = false;
    else if (!drawer.hidden) {
      // Out the way it came: the class plays the leaving animation, and the drawer is
      // hidden once it has played. Under reduced motion the animation is none and the
      // wait is only the wait.
      drawer.classList.add("leaving");
      leaving = setTimeout(function () {
        drawer.classList.remove("leaving");
        drawer.hidden = true;
      }, 160);
    }
    if (scrim) scrim.hidden = !on || !!restored;
    holdFocus(on && !restored);
    drawer.classList.toggle("talk-aside", on && !!restored);
    if (on && restored) {
      // Beside the page, under its bar, so the bar's own buttons stay pressable.
      var head = document.querySelector(".site-head, body > .bar");
      var foot = head ? Math.max(0, Math.round(head.getBoundingClientRect().bottom)) : 0;
      drawer.style.setProperty("--talk-top", foot + "px");
    }
    pill.setAttribute("aria-expanded", on ? "true" : "false");
    document.body.classList.toggle("talking", on);
    // Focus goes in with a press and comes back to the pill with a close, so a keyboard
    // is never left on the page's body (QA 2026-10-11). A drawer a page brought back by
    // itself takes nothing: the reader came to the page.
    if (on && !restored) focusBox();
    if (!on && (drawer.contains(document.activeElement) || document.activeElement === frame ||
        document.activeElement === document.body || !document.activeElement)) {
      pill.focus();
    }
    try {
      if (on) localStorage.setItem(OPEN, "open");
      else localStorage.removeItem(OPEN);
    } catch (e) {
      /* nothing to keep it in; the drawer still opens */
    }
  }

  pill.addEventListener("click", function () {
    show(drawer.hidden);
  });
  if (close) {
    close.addEventListener("click", function () {
      show(false);
    });
  }
  if (scrim) {
    scrim.addEventListener("click", function () {
      show(false);
    });
  }
  // The sheet's handle on a phone closes it, as a tap on the dimmed page does.
  Array.prototype.forEach.call(drawer.querySelectorAll("[data-talk-close]"), function (grab) {
    grab.addEventListener("click", function () {
      show(false);
    });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !drawer.hidden) show(false);
  });

  // What the conversation offers: a text to open, a count that changed.
  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin) return;
    if (!frame.contentWindow || event.source !== frame.contentWindow) return;
    var data = event.data || {};
    if (data.type === "targum:close" && !drawer.hidden) {
      show(false);
      return;
    }
    if (data.type === "targum:open" && data.reader) {
      var path = String(data.reader);
      leave(keyed("/reader/" + path.split("/").map(encodeURIComponent).join("/")));
    }
  });

  // On a phone the drawer is a sheet over the whole page, so one brought back would cover
  // the page the reader just chose — "Open your targums" pressed inside it opened Your
  // targums under a sheet. There, leaving a page closes it: the next page forgets it was
  // open, and the conversation, which is the box's, is there again behind the pill (QA
  // 2026-10-11, decision D7; design.md §12, "On a phone, the drawer closes when you leave
  // the page"). "A phone" is where the CSS draws the sheet: 48rem on the chrome's pages
  // (chrome.css), 60rem on the reader's (reader.css). At a desk it still comes back
  // beside the page.
  function sheet() {
    var at = document.body.classList.contains("reader") ? "60rem" : "48rem";
    return !!(window.matchMedia && window.matchMedia("(max-width: " + at + ")").matches);
  }
  var wasOpen = false;
  try {
    wasOpen = localStorage.getItem(OPEN) === "open";
    if (wasOpen && sheet()) {
      wasOpen = false;
      localStorage.removeItem(OPEN);
    }
  } catch (e) {
    wasOpen = false;
  }
  if (wasOpen) show(true, true);

  /* On a phone, Back closes the sheet before it leaves the page (design.md §12,
     2026-10-28; targum-internal#548). The sheet covers the page, and a phone's Back — the
     button, or the swipe from the edge — is how a reader puts away what covers the page:
     it left the page instead, and the conversation with it. So opening the sheet adds one
     step to the history, at the same address, and Back takes that step and closes it; the
     next Back leaves. The only step a panel adds. Closing it any other way — ×, the
     dimmed page, the handle, Escape — takes the step back too, so the history never holds
     a step that does nothing. At a desk the drawer stands beside the page and adds none. */
  var STEP = "targumTalk";
  var stepped = false;
  function onStep() {
    var state = window.history.state;
    return !!(state && typeof state === "object" && state[STEP]);
  }
  function stepIn() {
    if (stepped || !sheet() || !window.history.pushState) return;
    var state = {};
    state[STEP] = true;
    try {
      window.history.pushState(state, "", window.location.href);
      stepped = true;
    } catch (e) {
      /* no history to add to; the sheet still opens */
    }
  }
  function stepOut() {
    if (!stepped) return;
    stepped = false;
    if (onStep()) window.history.back();
  }
  window.addEventListener("popstate", function () {
    var open = pill.getAttribute("aria-expanded") === "true";
    if (onStep()) {
      // Forward, onto the sheet's step: the sheet it stands for.
      if (!open && sheet()) {
        stepped = true;
        show(true, false, true);
      }
      return;
    }
    if (stepped && open) {
      stepped = false;
      show(false, false, true);
    }
  });
  // A page opened from the sheet takes the sheet's step's place, so Back from it comes
  // back to this page rather than to a step that would only close a sheet already shut.
  function leave(href) {
    if (stepped && onStep()) window.location.replace(href);
    else window.location.href = href;
  }
  // A page loaded onto the sheet's step — a reload, or the same address opened again —
  // opens with the sheet shut, as every page on a phone does (D7, above), so the step is
  // only an address now: its mark is taken off, and Back is never asked to close a sheet
  // that is not there.
  if (onStep()) {
    try {
      window.history.replaceState(null, "", window.location.href);
    } catch (e) {
      /* nothing to clear */
    }
  }

  // A conversation by id, from the palette: open the drawer and name it in the frame's
  // address, which the conversation's own script answers. Replaced, not set: a hash set
  // in a frame is a step in this page's history, and Back walked the conversations
  // opened from the palette before it left the page (targum-internal#548).
  function open(id) {
    show(true);
    var name = function () {
      try {
        var at = frame.contentWindow.location;
        at.replace(at.href.split("#")[0] + "#" + encodeURIComponent(id));
      } catch (e) {
        /* not this origin yet; the drawer still opens */
      }
    };
    if (frame.contentWindow && frame.contentWindow.location && frame.contentWindow.location.href !== "about:blank") name();
    else frame.addEventListener("load", name, { once: true });
  }

  // A line said in the conversation from the page holding the drawer, by the reader's
  // own press: Add's Ask targum, for a description of what they want to read
  // (2026-09-13, targum-internal#249). The frame says it once it has loaded its list.
  function say(text) {
    var line = String(text || "").trim();
    if (!line) return;
    show(true);
    var send = function () {
      try {
        frame.contentWindow.postMessage({ type: "targum:say", text: line }, window.location.origin);
      } catch (e) {
        /* not this origin yet; nothing is said */
      }
    };
    if (frame.contentWindow && frame.contentWindow.location && frame.contentWindow.location.href !== "about:blank") send();
    else frame.addEventListener("load", send, { once: true });
  }

  window.TargumTalk = { show: show, open: open, say: say };
})();
