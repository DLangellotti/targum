/* A desk page sent whole fetches the desk's files once it is up, so the next page finds
 * them kept (design.md §12, "A first visit gets the page whole", 2026-10-19).
 *
 * Inline on such a page only, with its list on its own tag: `data-files`, the files this
 * page carried first and the desk's others after; `data-kept`, the address that gives the
 * browser the kept-files cookie once every one has arrived. It waits for `load` and a
 * moment more, and asks for a few at a time at low priority, so nothing the page itself
 * fetches waits behind it. If one fails it stops, and no cookie is asked for: the next
 * page is sent whole again and tries again. Off a disk it does nothing.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  if (!me || !/^https?:$/.test(location.protocol) || typeof window.fetch !== "function") return;
  var files;
  try {
    files = JSON.parse(me.getAttribute("data-files") || "[]");
  } catch (error) {
    return;
  }
  var kept = me.getAttribute("data-kept");
  var after = Number(me.getAttribute("data-after")) || 0;
  var lanes = Number(me.getAttribute("data-lanes")) || 1;
  if (!kept) return;

  function warm() {
    var next = 0;
    var busy = 0;
    var failed = false;
    function one() {
      if (failed) return;
      if (next >= files.length) {
        if (!busy) fetch(kept, { credentials: "same-origin" }).catch(function () {});
        return;
      }
      busy += 1;
      fetch(files[next++], { credentials: "same-origin", priority: "low" })
        .then(function (answer) {
          if (!answer.ok) throw new Error(String(answer.status));
          return answer.arrayBuffer();
        })
        .catch(function () {
          failed = true;
        })
        .then(function () {
          busy -= 1;
          one();
        });
    }
    for (var lane = 0; lane < lanes; lane += 1) one();
  }

  function soon() {
    setTimeout(warm, after);
  }
  if (document.readyState === "complete") soon();
  else window.addEventListener("load", soon);
})();
