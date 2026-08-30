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
