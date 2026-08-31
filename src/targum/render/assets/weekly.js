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
      watcher.disconnect();
      dialog.showModal();
    });
  }, { rootMargin: "0px 0px -25% 0px" });
  watcher.observe(below);
})();
