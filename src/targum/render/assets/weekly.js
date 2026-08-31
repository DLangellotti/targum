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

  /* The frame takes the screen.

     A reader inside a page that scrolls is the worst of both: the page takes the
     scroll the reader wanted, and the reader is cramped inside a slot. So the moment
     somebody starts reading in it — a tap or a click inside the frame, which the page
     can hear because the frame is the same origin — the frame is given the whole
     window, and the page under it is held still. On a phone, scrolling the frame to
     the top of the window is starting to read too.

     Given back from the row above the reader, or on Escape — unless the reader has a
     card or a sheet up, which is what Escape closes first. And once somebody has let
     themselves out, scrolling does not pull them back in; only touching the reader
     again does. */
  var embed = document.getElementById("embed");
  var handle = document.getElementById("embed-handle");
  var framed = embed && embed.querySelector("iframe");
  if (embed && handle && framed) {
    var locked = false;
    var left = false;
    var held = 0;
    var narrow = window.matchMedia("(max-width: 60rem)");

    /* From the slot to the window and back as one movement, not a cut. The frame is
       laid out where it is going first; then a transform puts it back where it was and
       is let go of on the mode pill's curve, so the box is seen to grow from the slot
       (and to shrink back into it). The reader inside lays itself out for the new size
       at the start, under the transform — a small shift at the slot's size, then the
       rise. Nothing, where stillness was asked for. */
    var still = window.matchMedia("(prefers-reduced-motion: reduce)");
    var flying = 0;

    function fly(from) {
      if (still.matches) return;
      var to = embed.getBoundingClientRect();
      if (!to.width || !to.height) return;
      var sx = from.width / to.width;
      var sy = from.height / to.height;
      var dx = from.left - to.left;
      var dy = from.top - to.top;
      embed.style.transformOrigin = "0 0";
      embed.style.transition = "none";
      embed.style.transform = "translate(" + dx + "px, " + dy + "px) scale(" + sx + ", " + sy + ")";
      void embed.offsetWidth;
      embed.style.transition = "transform 260ms cubic-bezier(0.32, 0.72, 0, 1)";
      embed.style.transform = "";
      embed.classList.add("flying");
      clearTimeout(flying);
      flying = setTimeout(function () {
        embed.style.transition = "";
        embed.style.transformOrigin = "";
        embed.classList.remove("flying");
      }, 300);
    }

    function lock() {
      if (locked) return;
      locked = true;
      left = false;
      var from = embed.getBoundingClientRect();
      held = window.scrollY;
      document.body.style.top = -held + "px";
      document.body.classList.add("locked");
      embed.classList.add("locked");
      handle.textContent = "Back to the page";
      handle.setAttribute("aria-expanded", "true");
      fly(from);
    }

    function unlock() {
      if (!locked) return;
      locked = false;
      left = true;
      var from = embed.getBoundingClientRect();
      embed.classList.remove("locked");
      document.body.classList.remove("locked");
      document.body.style.top = "";
      window.scrollTo(0, held);
      handle.textContent = "Full screen";
      handle.setAttribute("aria-expanded", "false");
      fly(from);
    }

    /* Whether the reader has something of its own up that Escape should close first. */
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

    handle.addEventListener("click", function () {
      if (locked) unlock();
      else lock();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && locked) unlock();
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
      doc.addEventListener("pointerdown", function () { lock(); }, true);
      doc.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && locked && !readerIsBusy()) unlock();
      });
    }
    framed.addEventListener("load", listenInside);
    listenInside();

    window.addEventListener(
      "scroll",
      function () {
        if (locked || left || !narrow.matches) return;
        var top = embed.getBoundingClientRect().top;
        if (top <= 12 && top > -embed.offsetHeight / 2) lock();
      },
      { passive: true }
    );
  }

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
