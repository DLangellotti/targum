/* The end of an issue, said once.

   Everything the page needs works without this file: the subscribe form is a real form
   that posts, and the dialog's markup is the same form again. This adds one thing — the
   dialog opens when somebody actually reaches the foot of the issue, rather than after
   a timer or on arrival, because the ask is worth making only once the reading has
   happened.

   Shown once ever, and remembered in this browser. A card is a card the first time; the
   second time it is a nag, and the guidelines are explicit that the reader is a reader.
*/
(function () {
  "use strict";

  var SEEN = "targum:weekly:asked";
  var dialog = document.getElementById("finished");
  if (!dialog || typeof dialog.showModal !== "function") return;

  function remembered() {
    // A private window, cleared site data, or a browser refusing storage all throw or
    // answer empty. Any of those means "show it", which is the same as a first visit.
    try {
      return window.localStorage.getItem(SEEN) === "1";
    } catch (error) {
      return false;
    }
  }

  function remember() {
    try {
      window.localStorage.setItem(SEEN, "1");
    } catch (error) {
      /* Storage refused. The dialog will offer itself once more another day, which is
         a smaller wrong than never closing. */
    }
  }

  /* Full screen, asked for and never imposed.

     For a while the frame took the window on its own — when scrolling reached it, or
     at the first tap inside — and that felt like being pushed. Nothing here is
     automatic now: the page settles around the reader by scroll-snap in the stylesheet,
     a tap inside just reads, and the row above the reader is the one way to the whole
     screen. Through the browser's own full screen where there is one, which brings its
     own way out (the system's gesture, Escape); pinned by hand only where there is
     none, which is Safari on a phone, and given back from the same row or Escape. */
  var embed = document.getElementById("embed");
  var handle = document.getElementById("embed-handle");
  var framed = embed && embed.querySelector("iframe");

  /* The stage reaches the window's edges: measured, because `100vw` counts a scrollbar
     the page cannot draw on and a percentage margin resolves against a box with padding
     of its own. The variables are cleared, the slot's own edge is read, and the frame
     is moved out to the window's — again on resize, and never while it is pinned. */
  function placeStage() {
    if (!embed || embed.classList.contains("locked")) return;
    var root = document.documentElement.style;
    root.removeProperty("--stage-left");
    root.removeProperty("--stage-width");
    var left = embed.getBoundingClientRect().left;
    root.setProperty("--stage-left", -left + "px");
    root.setProperty("--stage-width", document.documentElement.clientWidth + "px");
  }
  placeStage();
  window.addEventListener("resize", placeStage);

  if (embed && handle && framed) {
    var native = !!(embed.requestFullscreen || embed.webkitRequestFullscreen);
    var pinned = false;
    var held = 0;

    function isFull() {
      return document.fullscreenElement === embed || document.webkitFullscreenElement === embed;
    }

    function say(open) {
      handle.textContent = open ? "Back to the page" : "Full screen";
      handle.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function pin() {
      if (pinned) return;
      pinned = true;
      held = window.scrollY;
      document.body.style.top = -held + "px";
      document.body.classList.add("locked");
      embed.classList.add("locked");
      say(true);
    }

    function unpin() {
      if (!pinned) return;
      pinned = false;
      embed.classList.remove("locked");
      document.body.classList.remove("locked");
      document.body.style.top = "";
      window.scrollTo(0, held);
      say(false);
      placeStage();
    }

    handle.addEventListener("click", function () {
      if (native) {
        if (isFull()) {
          (document.exitFullscreen || document.webkitExitFullscreen).call(document);
        } else {
          var ask = embed.requestFullscreen || embed.webkitRequestFullscreen;
          var asked = ask.call(embed);
          /* Refused — a browser that has the call but not the permission — falls back
             to pinning, so the row always does something. */
          if (asked && asked.catch) asked.catch(pin);
        }
        return;
      }
      if (pinned) unpin();
      else pin();
    });

    function changed() {
      var open = isFull();
      embed.classList.toggle("full", open);
      say(open);
    }
    document.addEventListener("fullscreenchange", changed);
    document.addEventListener("webkitfullscreenchange", changed);

    /* Escape gives the pinned page back — unless the reader has a card or a sheet up,
       which is what Escape closes first. The browser's own full screen handles its own. */
    function readerIsBusy() {
      try {
        var doc = framed.contentDocument;
        return !!(doc && doc.querySelector(
          ".gloss-card:not([hidden]), #list:not([hidden]), .bar-more.open, #keys:not([hidden])"
        ));
      } catch (error) {
        return false;
      }
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && pinned) unpin();
    });
    function listenInside() {
      var doc;
      try {
        doc = framed.contentDocument;
      } catch (error) {
        return;
      }
      if (!doc || doc.__targumListening) return;
      doc.__targumListening = true;
      doc.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && pinned && !readerIsBusy()) unpin();
      });
    }
    framed.addEventListener("load", listenInside);
    listenInside();
  }

  /* The sources, folded on a phone. Open in the markup, so that without this file
     they are simply there; closed here where twelve rows are a long tail. */
  var sources = document.getElementById("sources");
  if (sources && window.matchMedia("(max-width: 60rem)").matches) sources.open = false;

  /* The level on the page and the level in the frame, kept the same. The reader's own
     bar switches level by navigating the frame, and a page that only knew the level it
     was served at would then be marking the wrong one — which is the reason it had no
     switcher of its own for a while. Same origin, so the frame's address can be read
     on every load: the chip moves, the sentence under it changes, and the page's own
     address follows, so a link copied from the bar is a link to what is showing. */
  var frame = document.querySelector(".embed iframe");
  var ladder = document.querySelector(".ladder");
  var what = document.getElementById("ladder-what");
  if (frame && ladder) {
    frame.addEventListener("load", function () {
      var path;
      try {
        path = frame.contentWindow.location.pathname;
      } catch (error) {
        return;
      }
      var found = /\/weekly\/read\/weekly-(\d{4}-w\d{2})-([a-z]+)-[a-z]+\/reader\//.exec(path);
      if (!found) return;
      var chips = ladder.querySelectorAll("a[data-level]");
      Array.prototype.forEach.call(chips, function (chip) {
        var on = chip.getAttribute("data-level") === found[2];
        chip.classList.toggle("here", on);
        if (on) chip.setAttribute("aria-current", "page");
        else chip.removeAttribute("aria-current");
        if (on && what) what.textContent = chip.getAttribute("data-what") || "";
      });
      if (window.history && history.replaceState) {
        history.replaceState(null, "", "/weekly/" + found[1] + "/" + found[2]);
      }
    });
  }

  if (remembered()) return;

  var close = dialog.querySelector("[data-close]");
  if (close) {
    close.addEventListener("click", function () {
      dialog.close();
    });
  }
  dialog.addEventListener("close", remember);

  /* When somebody has come past the reading.
   *
   * This watched `.part` — the last section of the issue, back when the page rendered
   * the prose itself. The reader is framed now and there are no `.part` elements on
   * this page at all, so the observer had nothing to watch and the dialog never opened
   * once. It was dead from the moment the reader was embedded.
   *
   * The end of the issue is inside the frame now and this page cannot see it without
   * talking across the boundary, which is machinery for a smaller thing than it costs.
   * Coming past the reader to the sources is the honest proxy: somebody who has
   * scrolled below the product has read some of it, or decided not to. Either way they
   * are the person worth asking.
   */
  var below = document.querySelector(".sources") || document.querySelector(".subscribe");
  if (!below || typeof window.IntersectionObserver !== "function") return;

  var watcher = new window.IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting || remembered()) return;
      /* Not while the reader has the screen: holding the page still puts the sources
         under the frame, where the observer counts them as in view — and a card over
         somebody who has just started reading is the nag this was written not to be.
         The observer stays on; they will come past the reader on their way out. */
      if (document.body.classList.contains("locked")) return;
      watcher.disconnect();
      dialog.showModal();
    });
  }, { rootMargin: "0px 0px -25% 0px" });
  watcher.observe(below);
})();
