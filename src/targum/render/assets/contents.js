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

  // The link says Library, so it goes to the library — not the start page. The same
  // rule reader.js follows for the section pages.
  var home = document.getElementById("home");
  if (home) {
    home.href = "/library" + suffix;
    home.hidden = false;
  }
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

  var key = new URLSearchParams(location.search).get("k");
  var rows = document.querySelectorAll("[data-chapter]");
  if (!key || !rows.length) return;

  // The folder name is the segment before /reader/ in the path.
  // The path is /reader/<folder>/reader/<file>: the route prefix and the folder inside
  // the build are both called "reader", so it is the *last* one the name sits before.
  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  function ask(path, body) {
    return fetch(path + "?k=" + encodeURIComponent(key), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Targum-Key": key },
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
      fetch("/job/" + id + "?k=" + encodeURIComponent(key))
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

  fetch("/readers?k=" + encodeURIComponent(key))
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

  var key = new URLSearchParams(location.search).get("k");
  var press = document.getElementById("prepare");
  if (!key || !press) return;

  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  function show() {
    var waiting = document.querySelectorAll("[data-chapter].waiting").length;
    var box = press.parentNode;
    box.hidden = waiting === 0;
  }

  press.onclick = function () {
    press.disabled = true;
    press.textContent = "Preparing…";
    fetch("/chapter?k=" + encodeURIComponent(key), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Targum-Key": key },
      body: JSON.stringify({ name: name, all: true }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (job) {
        if (!job.id) return location.reload();
        var timer = setInterval(function () {
          fetch("/job/" + job.id + "?k=" + encodeURIComponent(key))
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
