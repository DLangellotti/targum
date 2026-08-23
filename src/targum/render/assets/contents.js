/* The contents page, when it is being served rather than opened off the disk.
 *
 * Section links are relative, and a served reader is behind a key held in the address.
 * Without this the first chapter anyone clicks answers 403, which is the whole of what
 * a multi-section book does on its first click. Opened from a file:// path there is no
 * key and no library, and every link already works, so this does nothing at all.
 */
(function () {
  "use strict";

  var served = location.protocol === "http:" || location.protocol === "https:";
  if (!served) return;

  var key = new URLSearchParams(location.search).get("k");
  if (!key) return;

  var suffix = "?k=" + encodeURIComponent(key);

  var links = document.querySelectorAll(".toc a");
  Array.prototype.forEach.call(links, function (link) {
    var href = link.getAttribute("href");
    if (href && href.indexOf("?") === -1) link.setAttribute("href", href + suffix);
  });

  var home = document.getElementById("home");
  if (home) {
    home.href = "/" + suffix;
    home.hidden = false;
  }
})();
