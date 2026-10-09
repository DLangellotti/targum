/* The language the reader reads into, as the language menu keeps it, so a chapter bought
 * from here is bought in it rather than in whatever the folder holds most of
 * (targum-internal#287). */
function readInto() {
  try {
    return localStorage.getItem("targum:into") || "";
  } catch (e) {
    return "";
  }
}

/* What a waiting press spends, said beside it (copy audit, 2026-09-28): a translation
 * none. Only a book's chapters have a press here since 2026-10-07: a recording's parts
 * are made as the reader opens them (design.md §12, "One press gets the whole video, a
 * part at a time"), so its rows say how each part stands instead. */
function spends() {
  return window.TargumStrings.t("contents.uses-no-credits", "Uses none of your credits");
}

/* targum out of reach: the connection's banner under the top of the page (`fault.js`;
   design.md §12, 2026-10-09), whose Try again runs `retry`. */
function unreachable(retry) {
  if (window.TargumFault) window.TargumFault.unreachable(retry);
}

/* The parts of a recording a row holds, as the page writes them on `data-parts`. */
function partsOf(row) {
  return (row.getAttribute("data-parts") || "").split(" ").filter(Boolean);
}

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
    // A link out of the folder — a portion's own page, by route — needs no key. A link
    // to a verse carries its hash, and the key goes in front of that, not after it.
    if (!href || href.charAt(0) === "/" || href.indexOf("?") !== -1) return;
    var cut = href.indexOf("#");
    if (cut < 0) link.setAttribute("href", href + suffix);
    else link.setAttribute("href", href.slice(0, cut) + suffix + href.slice(cut));
  });

  // A portion's own page is a route, so it is offered only where there is a server to
  // answer it — the same rule the mark in the corner follows.
  Array.prototype.forEach.call(document.querySelectorAll(".toc .portion-page"), function (link) {
    link.hidden = false;
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
 * to the part the reader was last in — on this browser, or, signed in, on whichever
 * device they read on last (targum-internal#430). The reader writes the place down as
 * it is read (`TargumSync.place`); the account's copy is asked for here and wins when
 * it is newer, and is kept in this browser too, so the part it opens puts the reader
 * back on their sentence. Signed out, or off the disk, this browser's is the whole of it.
 */
(function () {
  "use strict";
  // Said in the page's language, from `strings.js` (targum-internal#184).
  var t = window.TargumStrings.t;
  var start = document.getElementById("start");
  var toc = document.querySelector(".toc[data-document]");
  if (!start || !toc) return;
  var documentId = toc.getAttribute("data-document");
  var PLACES = "targum:places";

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  // The text's place as this browser has it. `targum:chapter` is the one number a
  // browser kept before there were places, read for a text not opened since.
  function mine() {
    var place = stored(PLACES)[documentId];
    if (place && place.section) return place;
    var last = Number(stored("targum:chapter")[documentId]);
    return last ? { section: String(last), at: 0 } : null;
  }

  function point(place) {
    if (!place || !place.section) return;
    var row = toc.querySelector('[data-chapter="' + place.section + '"] a');
    if (!row) return;
    start.href = row.getAttribute("href");
    start.textContent = t("contents.continue", "Continue");
  }

  var here = mine();
  point(here);

  if (!/^https?:$/.test(location.protocol) || !window.fetch) return;
  var key = new URLSearchParams(location.search).get("k") || "";
  fetch(
    "/account/places?limit=1&document=" +
      encodeURIComponent(documentId) +
      (key ? "&k=" + encodeURIComponent(key) : ""),
    { credentials: "same-origin" }
  )
    .then(function (response) {
      return response.ok ? response.json() : null;
    })
    .then(function (answer) {
      var theirs = answer && answer.places && answer.places[0];
      if (!theirs || !theirs.section) return;
      if (Number(theirs.at || 0) <= Number((here && here.at) || 0)) return;
      var all = stored(PLACES);
      all[documentId] = {
        section: String(theirs.section),
        path: theirs.path || "",
        segment: theirs.segment || "",
        seconds: Number(theirs.seconds || 0),
        at: Number(theirs.at || 0),
      };
      try {
        targumKeep(PLACES, JSON.stringify(all));
      } catch (e) {}
      point(theirs);
    })
    .catch(function () {});
})();

/* --- a link to a verse ------------------------------------------------------
 *
 * `index.html#2:1` goes on to the file that holds chapter 2, hash and all, so a link to
 * Ruth 2:1 can be written without knowing which file chapter 2 landed in — and it is
 * not always the second: a range ingested from chapter 12 opens on chapter 12. Each row
 * says which chapters its file holds; the address is the one the verse rows answer to
 * (targum-internal#28). `replace`, so the contents page is not a step on the way back.
 *
 * A chapter is not always one file: a portion's files are aliyot, and Leviticus 16 runs
 * across three of them. So each row also says the first and last verse it holds, and a
 * link to a verse takes the row whose range has it (targum-internal#142). The chapter
 * match stays for a link with no verse, and for a verse no row holds — a number past
 * the end of its chapter opens on the chapter rather than on nothing.
 */
(function () {
  "use strict";
  var found = /^#(\d+)(?:[:.](\d+))?$/.exec(location.hash);
  if (!found) return;
  function place(text) {
    var parts = text.split(":");
    return [Number(parts[0]), Number(parts[1] || 0)];
  }
  function before(a, b) {
    return a[0] < b[0] || (a[0] === b[0] && a[1] <= b[1]);
  }
  var row = null;
  if (found[2]) {
    var want = place(found[1] + ":" + found[2]);
    var rows = document.querySelectorAll(".toc [data-from]");
    for (var i = 0; i < rows.length && !row; i++) {
      var from = place(rows[i].getAttribute("data-from"));
      var to = place(rows[i].getAttribute("data-to"));
      if (before(from, want) && before(want, to)) row = rows[i].querySelector("a");
    }
  }
  if (!row) row = document.querySelector('.toc [data-chapters~="' + found[1] + '"] a');
  if (!row) return;
  var hash = found[2] ? "#" + found[1] + ":" + found[2] : "";
  location.replace(row.href + hash);
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
  // Said in the page's language, from `strings.js` (targum-internal#184).
  var t = window.TargumStrings.t;
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
    var heard = [];
    Array.prototype.forEach.call(rows, function (row) {
      var number = Number(row.getAttribute("data-chapter"));
      var chapter = chapters.filter(function (c) {
        return c.number === number;
      })[0];
      if (!chapter) return;
      row.classList.toggle("waiting", !chapter.ready);
      if (chapter.ready) return;

      // A part of a recording has no press here (David, 2026-10-07; design.md §12, "One
      // press gets the whole video, a part at a time"): the press on its quote covered
      // every part, and opening the part's own page is what starts it. The row says
      // plainly how the part stands instead — waiting, or being made and how far — and
      // its link is the way in.
      if (row.hasAttribute("data-audio")) {
        if (!row.querySelector(".get-said")) {
          var line = document.createElement("span");
          line.className = "get-said";
          line.setAttribute("role", "status");
          // A sentence in the page's language inside a Hebrew list: isolated, or its
          // closing full stop is drawn at the start of the line.
          line.dir = "auto";
          row.appendChild(line);
        }
        heard.push(row);
        return;
      }
      if (row.querySelector(".get")) return;

      var get = document.createElement("button");
      get.type = "button";
      get.className = "get";
      get.textContent = t("contents.translate", "Translate");
      get.onclick = function () {
        get.disabled = true;
        get.textContent = t("contents.translating", "Translating…");
        ask("/chapter", { name: name, number: number, to: readInto() })
          .then(function (job) {
            if (job.ready) return location.reload();
            // A refusal carries an id too, and watching a job that was never kept
            // spun for ever (2026-09-14).
            if (job.blocked || job.stage === "blocked" || !job.id) {
              get.disabled = false;
              get.textContent = job.blocked || job.error || t("contents.could-not", "We couldn't start that. Try again.");
              return;
            }
            watch(job.id, get);
          })
          .catch(function () {
            // The connection's banner, not the button's label (design.md §12,
            // 2026-10-09): the button goes back to what it was, and Try again presses it.
            get.disabled = false;
            get.textContent = t("contents.translate", "Translate");
            unreachable(function () {
              get.click();
            });
          });
      };
      row.appendChild(get);
      var said = document.createElement("span");
      said.className = "get-cost";
      said.textContent = spends();
      row.appendChild(said);
    });
    if (heard.length) follow(heard);
  }

  /* How each waiting part of a recording stands, from the bell's own list of your builds
   * (`/jobs`, with the server's `said` about each), looked at again every three seconds
   * while any of them is being made, as the bell does, and not at all once none is. A
   * part made while the page was watching reloads it, so its row turns ready. Nothing
   * here asks for anything to be made. */
  function follow(heard) {
    var seen = {};
    var timer = null;
    function jobFor(row, jobs) {
      var mine = partsOf(row).map(Number);
      return jobs.filter(function (job) {
        if (job.folder !== name || job.stage === "done") return false;
        return (job.making || []).some(function (n) {
          return mine.indexOf(n) >= 0;
        });
      })[0];
    }
    function say(row, job) {
      var line = row.querySelector(".get-said");
      if (!job) {
        line.textContent = t("contents.part-waiting", "Waiting. We make it when you open it.");
      } else if (job.stage === "failed" || job.stage === "blocked") {
        line.textContent = job.said || job.blocked || job.error || t("contents.could-not", "We couldn't start that. Try again.");
      } else {
        var making = t("contents.part-making", "Being made.");
        line.textContent = job.said ? making + " " + job.said : making;
      }
    }
    function look() {
      fetch(keyed("/jobs"), { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : { jobs: [] };
        })
        .then(function (data) {
          var jobs = (data && data.jobs) || [];
          var going = false;
          var finished = false;
          heard.forEach(function (row) {
            var job = jobFor(row, jobs);
            say(row, job);
            var live = !!job && job.stage !== "failed" && job.stage !== "blocked";
            if (live) seen[job.id] = true;
            going = going || live;
          });
          // A job this page saw being made that is now done, or gone from the list.
          Object.keys(seen).forEach(function (id) {
            var now = jobs.filter(function (job) {
              return job.id === id;
            })[0];
            if (!now || now.stage === "done") finished = true;
          });
          if (finished) return location.reload();
          if (going && !timer) timer = setInterval(look, 3000);
          if (!going && timer) {
            clearInterval(timer);
            timer = null;
          }
        })
        .catch(function () {
          heard.forEach(function (row) {
            var line = row.querySelector(".get-said");
            if (!line.textContent) say(row, null);
          });
        });
    }
    look();
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
          } else if (job.stage === "failed" || job.blocked || (job.error && !job.stage)) {
            clearInterval(timer);
            button.disabled = false;
            button.textContent = job.error || job.blocked || t("contents.could-not", "We couldn't start that. Try again.");
          }
        })
        .catch(function () {
          clearInterval(timer);
          // Still building, as far as anybody knows: the banner says the connection
          // went, and Try again goes back to watching rather than starting it twice.
          unreachable(function () {
            watch(id, button);
          });
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

/* Prepare the whole book, for reading somewhere with no connection. A book's only: a
 * recording's contents page has no such press since 2026-10-07. */
(function () {
  "use strict";
  // Said in the page's language, from `strings.js` (targum-internal#184).
  var t = window.TargumStrings.t;
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
    // What preparing the rest spends, beside the press. Only a book's page has the
    // press since 2026-10-07, so it is a translation's none.
    var cost = document.getElementById("prepare-cost");
    if (!cost || !waiting) return;
    cost.textContent = spends();
    cost.hidden = !cost.textContent;
  }

  var pressLabel = press.textContent;

  press.onclick = function () {
    press.disabled = true;
    press.textContent = t("contents.preparing", "Preparing…");
    fetch(keyed("/chapter"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name: name, all: true, to: readInto() }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (job) {
        if (job.blocked || job.stage === "blocked") {
          press.disabled = false;
          press.textContent = job.blocked || job.error;
          return;
        }
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
              } else if (state.stage === "failed" || state.blocked || (state.error && !state.stage)) {
                clearInterval(timer);
                press.disabled = false;
                press.textContent = state.error || state.blocked || t("contents.could-not-prepare", "We couldn't prepare it. Try again.");
              }
            })
            .catch(function () {
              clearInterval(timer);
              press.disabled = false;
              press.textContent = pressLabel;
              unreachable(function () {
                press.click();
              });
            });
        }, 1500);
      })
      .catch(function () {
        press.disabled = false;
        press.textContent = pressLabel;
        unreachable(function () {
          press.click();
        });
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
