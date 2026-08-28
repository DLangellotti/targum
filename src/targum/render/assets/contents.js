/* The contents page, when it is being served rather than opened off the disk.
 *
 * Section links are relative, and a served reader run locally is behind a key held in
 * the address. Without carrying it, the first chapter anyone clicks answers 403 — which
 * is the whole of what a multi-section book does on its first click. Opened from a
 * file:// path there is no key and no library, and every link already works, so this
 * does nothing at all.
 *
 * Hosted there is no key either, and the session cookie carries the reader instead. So
 * the key is optional here and its absence is not a reason to stop: an earlier version
 * returned early without one, which off a hosted box left the whole contents page inert
 * — no chapter tree, no Translate, no Prepare all.
 */
(function () {
  "use strict";

  var served = location.protocol === "http:" || location.protocol === "https:";
  if (!served) return;

  var key = new URLSearchParams(location.search).get("k") || "";
  var suffix = key ? "?k=" + encodeURIComponent(key) : "";

  var links = document.querySelectorAll(".toc a");
  Array.prototype.forEach.call(links, function (link) {
    var href = link.getAttribute("href");
    if (href && href.indexOf("?") === -1) link.setAttribute("href", href + suffix);
  });

  // The link says Learn, so it goes there: somebody leaving a text wants their own
  // shelf and what they were part way through, not the catalogue. The same rule
  // reader.js follows for the section pages.
  var home = document.getElementById("home");
  var homePlain = document.getElementById("home-plain");
  if (home) {
    home.href = "/" + suffix;
    home.hidden = false;
    // Two drawings of the same mark, one a link and one not, so a book opened off the
    // disk shows the mark rather than a link to nowhere.
    if (homePlain) homePlain.hidden = true;
  }
})();

/* --- where to start ---------------------------------------------------------
 *
 * "Start reading" goes to the first chapter. Come back and it says "Continue" and goes
 * to the chapter last opened, which the reader writes down under the text's hash.
 */
(function () {
  "use strict";
  var start = document.getElementById("start");
  var toc = document.querySelector(".toc[data-document]");
  if (!start || !toc) return;
  var last = 0;
  try {
    last = Number(
      JSON.parse(localStorage.getItem("targum:chapter") || "{}")[toc.getAttribute("data-document")]
    );
  } catch (e) {}
  if (!last) return;
  var row = toc.querySelector('[data-chapter="' + last + '"] a');
  if (!row) return;
  start.href = row.getAttribute("href");
  start.textContent = "Continue";
})();

/* --- which chapters are ready -----------------------------------------------
 *
 * A book is bought a chapter at a time, so the contents page is where the state of
 * each one is shown and where a chapter that is waiting can be asked for. Off a
 * file:// path none of this runs: there is no server to ask and everything on disk is
 * already translated, or it would not be on disk.
 */
(function () {
  "use strict";
  if (location.protocol === "file:") return;

  // No key hosted, where the session cookie identifies the reader; a key locally, where
  // it is what proves the page came from the terminal that started the server. Only the
  // rows are worth stopping for.
  var key = new URLSearchParams(location.search).get("k") || "";
  var rows = document.querySelectorAll("[data-chapter]");
  if (!rows.length) return;

  // The folder name is the segment before /reader/ in the path.
  // The path is /reader/<folder>/reader/<file>: the route prefix and the folder inside
  // the build are both called "reader", so it is the *last* one the name sits before.
  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json();
    });
  }

  function mark(chapters) {
    Array.prototype.forEach.call(rows, function (row) {
      var number = Number(row.getAttribute("data-chapter"));
      var chapter = chapters.filter(function (c) {
        return c.number === number;
      })[0];
      if (!chapter) return;
      row.classList.toggle("waiting", !chapter.ready);
      if (chapter.ready || row.querySelector(".get")) return;

      var get = document.createElement("button");
      get.type = "button";
      get.className = "get";
      get.textContent = "Translate";
      get.onclick = function () {
        get.disabled = true;
        get.textContent = "Translating…";
        ask("/chapter", { name: name, number: number }).then(function (job) {
          watch(job.id, get);
        });
      };
      row.appendChild(get);
    });
  }

  function watch(id, button) {
    var timer = setInterval(function () {
      fetch(keyed("/job/" + id))
        .then(function (r) {
          return r.json();
        })
        .then(function (job) {
          if (job.stage === "done") {
            clearInterval(timer);
            location.reload();
          } else if (job.stage === "failed" || job.blocked) {
            clearInterval(timer);
            button.disabled = false;
            button.textContent = job.error || job.blocked || "That did not work.";
          }
        });
    }, 1500);
  }

  fetch(keyed("/readers"))
    .then(function (r) {
      return r.json();
    })
    .then(function (data) {
      var mine = (data.readers || []).filter(function (r) {
        return r.name === name;
      })[0];
      if (mine && mine.chapters && mine.chapters.length) mark(mine.chapters);
    })
    .catch(function () {});
})();

/* Prepare the whole book, for reading somewhere with no connection. */
(function () {
  "use strict";
  if (location.protocol === "file:") return;

  // No key hosted, a key locally — see above. Stopping on a missing key made this
  // button dead on the live site.
  var key = new URLSearchParams(location.search).get("k") || "";
  var press = document.getElementById("prepare");
  if (!press) return;

  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  // Its own, because this is its own scope. It was calling the one above and could not
  // reach it — the same way the reader called a `keyed` it never had.
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  function show() {
    var waiting = document.querySelectorAll("[data-chapter].waiting").length;
    var box = press.parentNode;
    box.hidden = waiting === 0;
  }

  press.onclick = function () {
    press.disabled = true;
    press.textContent = "Preparing…";
    fetch(keyed("/chapter"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name: name, all: true }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (job) {
        if (!job.id) return location.reload();
        var timer = setInterval(function () {
          fetch(keyed("/job/" + job.id))
            .then(function (r) {
              return r.json();
            })
            .then(function (state) {
              if (state.stage === "done") {
                clearInterval(timer);
                location.reload();
              } else if (state.stage === "failed" || state.blocked) {
                clearInterval(timer);
                press.disabled = false;
                press.textContent = state.error || state.blocked || "That did not work.";
              }
            });
        }, 1500);
      });
  };

  // The chapter states arrive a moment after load; watch for them rather than guess.
  new MutationObserver(show).observe(document.querySelector(".toc"), {
    subtree: true,
    attributes: true,
    attributeFilter: ["class"],
  });
  show();
})();
