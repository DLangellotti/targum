/* Talk to targum, from anywhere (2026-09-11).
 *
 * The conversation is not a page you go to: one pill, fixed at the foot of every page,
 * opens it as a drawer — from the edge on a laptop, up from the foot on a phone — holding
 * the conversation page framed without its bar (`/chat?embed=1`). Loaded the first time
 * it is opened and never before; closed by its own button, the scrim or Escape; left open
 * across pages once opened (`targum:talk`), since somebody mid-conversation who follows a
 * link has not finished talking.
 *
 * A text the conversation offers is opened by the page holding the drawer: Learn puts it
 * in its sheet (`TargumLearn.open`), any other page goes to the reader itself. Nothing is
 * taken from a message that did not come from the drawer's own frame on this origin.
 */
(function () {
  "use strict";

  var pill = document.getElementById("talk-open");
  var drawer = document.getElementById("talk-drawer");
  var frame = document.getElementById("talk-frame");
  var close = document.getElementById("talk-close");
  var scrim = document.getElementById("talk-scrim");
  if (!pill || !drawer || !frame) return;

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  var OPEN = "targum:talk";
  var loaded = false;

  function load() {
    if (loaded) return;
    loaded = true;
    frame.setAttribute("src", frame.getAttribute("data-src") || keyed("/chat?embed=1"));
  }

  function show(on) {
    if (on) load();
    drawer.hidden = !on;
    if (scrim) scrim.hidden = !on;
    pill.setAttribute("aria-expanded", on ? "true" : "false");
    document.body.classList.toggle("talking", on);
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
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !drawer.hidden) show(false);
  });

  // What the conversation offers: a text to open, a count that changed.
  window.addEventListener("message", function (event) {
    if (event.origin !== window.location.origin) return;
    if (!frame.contentWindow || event.source !== frame.contentWindow) return;
    var data = event.data || {};
    var learn = window.TargumLearn;
    if (data.type === "targum:open" && data.reader) {
      var path = String(data.reader);
      if (learn && learn.open) {
        learn.open(path);
        // On a phone the drawer covers the sheet the text just opened in.
        if (window.matchMedia && window.matchMedia("(max-width: 48rem)").matches) show(false);
        return;
      }
      window.location.href = keyed(
        "/reader/" + path.split("/").map(encodeURIComponent).join("/")
      );
    }
    if (data.type === "targum:changed" && learn && learn.changed) learn.changed();
  });

  var wasOpen = false;
  try {
    wasOpen = localStorage.getItem(OPEN) === "open";
  } catch (e) {
    wasOpen = false;
  }
  if (wasOpen) show(true);

  window.TargumTalk = { show: show };
})();
