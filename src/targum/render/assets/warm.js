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
  /* The faces, which such a page does not carry in place (#484): they wait in an inert
     `<template>` before this tag, and go on once the page is up, so their bytes never
     stand in front of what it draws first. At `load`, or, on a page that names an event
     in `TARGUM_FACES_AFTER` (the Library), when it fires, or at once when the page says
     it already has (`TARGUM_DRAWN`); never later than `FACES_LATEST` after `load`. */
  var FACES_LATEST = 3000;
  var faces = document.getElementById("late-faces");
  function dress() {
    if (!faces) return;
    var sheets = faces.content ? faces.content.cloneNode(true) : null;
    faces = null;
    if (sheets) document.head.appendChild(sheets);
  }
  if (faces) {
    var facesAfter = window.TARGUM_FACES_AFTER;
    if (facesAfter) window.addEventListener(facesAfter, dress);
    // The Library can have drawn before this tag at its foot runs: its shelf is asked
    // from the head, so the event may already have gone (qa-claude on #920).
    if (facesAfter && window.TARGUM_DRAWN) dress();
    var onLoad = function () {
      if (facesAfter) setTimeout(dress, FACES_LATEST);
      else dress();
    };
    if (document.readyState === "complete") onLoad();
    else window.addEventListener("load", onLoad);
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
