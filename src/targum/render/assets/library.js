/* The library: everything there is to read, in one list you can sort and sift.
 *
 * It used to be a grid of cards holding the catalogue, with the reader's own texts on
 * another page entirely. Two shapes for one question — what shall I read — and neither
 * of them answerable in a hurry: a card cannot be sorted, and twenty-six of them are a
 * wall. This is one row per text, and the controls above the list act on all of them as
 * you type.
 *
 * A picked text arrives with a translation somebody published, so opening one is only a
 * matter of fetching two texts and matching them up. Nothing about that is the reader's
 * business, and none of it belongs in what the page says.
 *
 * One language at a time. Someone reading Hebrew should not have to look past a Russian
 * novel to find their own shelf, and the language they pick here is the one their words
 * page opens on.
 */

(function () {
  "use strict";

  var key = window.TARGUM_KEY;
  /* Hosted there is no start-up key: the session cookie identifies the reader, and a key
     riding in every URL is a bearer token in browser history, on a shared screen, and in
     a Referer. Local it stays, because there it proves the page came from the terminal
     that started the process. Both cases are this one branch. */
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  var names = window.TARGUM_LANGUAGES || {};
  var catalogue = window.TARGUM_CATALOGUE || [];
  var lang = window.TargumLang;

  // What a text is. Six words a reader would actually filter by, and the seventh —
  // an article — is what their own shelf is mostly made of.
  var KINDS = [
    ["prose", "Prose"],
    ["poetry", "Poetry"],
    ["novel", "Novels"],
    ["story", "Stories"],
    ["essay", "Essays"],
    ["document", "Documents"],
    ["article", "Articles"],
  ];

  var REGISTERS = [
    ["biblical", "Biblical"],
    ["modern", "Modern"],
  ];

  var LENGTHS = [
    ["", "Any"],
    ["short", "Under 20 min"],
    ["hour", "20 min – 2 hr"],
    ["long", "Over 2 hr"],
  ];

  // The share of running words a reader would have to look up, in three steps. The
  // numbers behind them are measured off each text: see scripts/measure_difficulty.py.
  var LEVELS = [
    ["", "Any"],
    ["easy", "Easier"],
    ["mid", "Middling"],
    ["hard", "Harder"],
  ];

  var WHERE = [
    ["", "Everything"],
    ["mine", "On my shelf"],
    ["new", "Not built yet"],
  ];

  // Where the gauge starts and stops. Nothing in Hebrew comes in under a tenth or over
  // two fifths, so a bar drawn from zero would be four identical bars.
  var FLOOR = 12;
  var CEILING = 40;

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function base(code) {
    return (code || "").split("-")[0].toLowerCase();
  }

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  function remember(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {}
  }

  Array.prototype.forEach.call(document.querySelectorAll(".site-nav a"), function (link) {
    link.href = keyed(link.getAttribute("href"));
  });

  /* --- what the list holds --------------------------------------------------- */

  function level(share) {
    if (!share) return "";
    if (share <= 20) return "easy";
    return share <= 28 ? "mid" : "hard";
  }

  function lengthOf(minutes) {
    if (minutes < 20) return "short";
    return minutes <= 120 ? "hour" : "long";
  }

  function said(minutes) {
    if (minutes < 60) return minutes + " min";
    var hours = Math.round(minutes / 60);
    return hours + " hr";
  }

  // One row per text, from two places. A catalogue entry the reader has already built
  // is one row and not two: the catalogue is where it came from, the shelf is where it
  // is now, and the row says both.
  function rows(readers) {
    var mine = {};
    var out = [];
    readers.forEach(function (reader) {
      if (reader.entry) mine[reader.entry] = reader;
    });
    catalogue.forEach(function (entry) {
      var built = mine[entry.id];
      out.push({
        id: entry.id,
        entry: entry,
        title: entry.title,
        author: entry.author,
        language: entry.language,
        kind: entry.kind,
        register: entry.register,
        difficulty: entry.difficulty,
        minutes: entry.minutes,
        built: built || null,
        drawn: !!(built && built.drawn),
        opened: built ? built.opened || 0 : 0,
      });
    });
    readers.forEach(function (reader) {
      if (reader.entry && mine[reader.entry]) return;
      out.push({
        id: reader.name,
        entry: null,
        title: reader.title,
        author: "",
        language: reader.language,
        kind: reader.kind,
        register: reader.register,
        difficulty: reader.difficulty,
        minutes: reader.minutes,
        built: reader,
        opened: reader.opened || 0,
      });
    });
    return out;
  }

  /* --- drawing one ----------------------------------------------------------- */

  function gauge(share) {
    var box = el("span", "gauge");
    if (!share) {
      box.appendChild(el("span", "col count", "—"));
      return box;
    }
    var track = el("span", "track");
    var fill = el("span", "fill");
    var reach = Math.max(6, Math.min(100, ((share - FLOOR) / (CEILING - FLOOR)) * 100));
    fill.style.inlineSize = reach + "%";
    track.appendChild(fill);
    box.appendChild(track);
    box.appendChild(el("span", "col count", share + "%"));
    return box;
  }

  function named(list, value) {
    for (var i = 0; i < list.length; i++) if (list[i][0] === value) return list[i][1];
    return "";
  }

  function draw(row) {
    var item = el("li");
    item.setAttribute("data-row", row.id);

    var open = el(row.built ? "a" : "button", "row-open");
    if (row.built) {
      open.href = keyed("/reader/" + row.built.name + "/reader/index.html");
    } else {
      open.type = "button";
      open.setAttribute("data-build", row.id);
    }

    open.appendChild(
      window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(row.id)), {
        title: row.title,
        language: row.language,
      })
    );

    var what = el("span", "what");
    var title = el("span", "row-title");
    title.setAttribute("lang", row.language);
    var bdi = el("bdi", null, row.title);
    title.appendChild(bdi);
    what.appendChild(title);
    if (row.author) what.appendChild(el("span", "row-by", row.author));
    open.appendChild(what);

    open.appendChild(el("span", "col label drop", named(KINDS, row.kind)));
    open.appendChild(el("span", "col label drop", named(REGISTERS, row.register)));
    open.appendChild(el("span", "col count", said(row.minutes)));
    var hard = gauge(row.difficulty);
    hard.className = "gauge drop";
    open.appendChild(hard);

    var state = el("span", "row-state", row.built ? "On your shelf" : "Build it");
    if (row.built) state.className = "row-state mine";
    open.appendChild(state);

    item.appendChild(open);

    // Only where there is something to draw: a text on the shelf, from the library's own
    // catalogue — a cover is drawn from what the catalogue says a text is — and with no
    // cover yet. And only where this deployment has a key to draw with.
    if (canDraw && row.built && row.entry && !row.drawn) {
      var draw = el("button", "draw", "Draw cover");
      draw.type = "button";
      draw.setAttribute("data-draw", row.built.name);
      item.appendChild(draw);
    }
    return item;
  }

  /* --- sorting and sifting ---------------------------------------------------- */

  var SORTS = {
    title: function (row) {
      return row.title || "";
    },
    kind: function (row) {
      return named(KINDS, row.kind);
    },
    register: function (row) {
      return named(REGISTERS, row.register);
    },
    minutes: function (row) {
      return row.minutes || 0;
    },
    difficulty: function (row) {
      return row.difficulty || 0;
    },
    state: function (row) {
      return row.built ? 0 : 1;
    },
  };

  var COLUMNS = [
    ["", ""],
    ["title", "Text"],
    ["kind", "Kind"],
    ["register", "Hebrew"],
    ["minutes", "Length"],
    ["difficulty", "Looked up"],
    ["state", "Where"],
  ];

  // Whether the server can draw at all, answered by the server. A deployment with no
  // image key offers nothing rather than offering and failing.
  var canDraw = false;

  var view = stored("targum:library");
  if (!view.sort) view.sort = "state";
  if (!view.dir) view.dir = 1;
  if (!view.kind) view.kind = "";
  if (!view.register) view.register = "";

  function matches(row, code) {
    if (base(row.language) !== code) return false;
    if (view.kind && row.kind !== view.kind) return false;
    if (view.register && row.register !== view.register) return false;
    if (view.length && lengthOf(row.minutes) !== view.length) return false;
    if (view.level && level(row.difficulty) !== view.level) return false;
    if (view.where === "mine" && !row.built) return false;
    if (view.where === "new" && row.built) return false;
    if (view.find) {
      // The blurb and the name the text is filed under are in this on purpose. A reader
      // typing "herzl" into a library of Hebrew titles otherwise finds nothing: the
      // titles and the bylines are both in Hebrew, and the only Latin a text carries is
      // the sentence describing it and its own id.
      var hay = [row.title, row.author, row.entry ? row.entry.blurb : "", row.id]
        .join(" ")
        .toLowerCase();
      if (hay.indexOf(view.find.toLowerCase()) < 0) return false;
    }
    return true;
  }

  function sorted(list) {
    var pick = SORTS[view.sort] || SORTS.title;
    return list.slice().sort(function (a, b) {
      var left = pick(a);
      var right = pick(b);
      var order;
      if (typeof left === "number") order = left - right;
      else order = String(left).localeCompare(String(right));
      // A tie falls back to the title, so the list never shuffles under a reader who
      // sorted by something half of it shares.
      if (!order) order = String(a.title).localeCompare(String(b.title));
      return order * view.dir;
    });
  }

  /* --- the controls ----------------------------------------------------------- */

  function chips(host, options, field, redraw) {
    host.textContent = "";
    var all = [["", "All"]].concat(options);
    all.forEach(function (pair) {
      var chip = el("button", "chip", pair[1]);
      chip.type = "button";
      chip.setAttribute("aria-pressed", view[field] === pair[0] ? "true" : "false");
      chip.addEventListener("click", function () {
        view[field] = pair[0];
        redraw();
      });
      host.appendChild(chip);
    });
  }

  function choices(select, options, field, redraw) {
    select.textContent = "";
    options.forEach(function (pair) {
      var option = el("option", null, pair[1]);
      option.value = pair[0];
      if ((view[field] || "") === pair[0]) option.selected = true;
      select.appendChild(option);
    });
    select.onchange = function () {
      view[field] = select.value;
      redraw();
    };
  }

  function heading(redraw) {
    var host = document.getElementById("rows-head");
    host.textContent = "";
    COLUMNS.forEach(function (pair) {
      if (!pair[0]) {
        host.appendChild(el("span"));
        return;
      }
      var button = el("button", pair[0] === "kind" || pair[0] === "register" ? "drop" : null);
      button.type = "button";
      button.appendChild(document.createTextNode(pair[1]));
      if (pair[0] === "difficulty") button.className = "drop";
      if (view.sort === pair[0]) {
        button.setAttribute("aria-sort", view.dir > 0 ? "ascending" : "descending");
        button.appendChild(el("span", "arrow", view.dir > 0 ? " ↑" : " ↓"));
      }
      button.addEventListener("click", function () {
        if (view.sort === pair[0]) view.dir = -view.dir;
        else {
          view.sort = pair[0];
          view.dir = 1;
        }
        redraw();
      });
      host.appendChild(button);
    });
  }

  /* --- building one ----------------------------------------------------------- */

  // The pipeline narrates itself in its own words. This is the reader's.
  var PLAIN = {
    "Finding each word's dictionary form…": "Reading the words…",
    "Adding vowel points…": "Adding vowel points…",
    "Building the reader…": "Setting the page…",
  };

  function say(message) {
    if (!message) return "";
    if (PLAIN[message]) return PLAIN[message];
    if (message.indexOf("Matching") === 0) return "Lining up…";
    if (message.indexOf("Looking up") === 0) return "Looking words up…";
    return "Almost there…";
  }

  function watch(id, state) {
    return new Promise(function (resolve) {
      var timer = setInterval(function () {
        ask("/job/" + id).then(function (job) {
          if (job.error) {
            clearInterval(timer);
            state.textContent = job.error;
            resolve();
            return;
          }
          state.textContent = say(job.message) || "Almost there…";
          if (job.stage === "done") {
            clearInterval(timer);
            window.location.href = keyed("/reader/" + job.reader);
            resolve();
          }
        });
      }, 700);
    });
  }

  function build(open, entry) {
    var state = open.querySelector(".row-state");
    open.disabled = true;
    state.textContent = "Getting ready…";
    ask("/prepare", {
      source: entry.source,
      to: "en",
      from: entry.language,
      words: true,
      gloss: false,
      // Every published translation this text has. The reader switches between them.
      translations: entry.translations.map(function (t) {
        return t.source;
      }),
    })
      .then(function (job) {
        if (job.error) throw new Error(job.error);
        if (job.blocked) throw new Error(job.blocked);
        state.textContent = "Lining up…";
        return ask("/build", { id: job.id }).then(function () {
          return watch(job.id, state);
        });
      })
      .catch(function (problem) {
        state.textContent = String(problem.message || problem);
        open.disabled = false;
      });
  }

  function drawCovers(button, name) {
    button.disabled = true;
    button.textContent = "Drawing…";
    ask("/cover", { name: name, chapters: true })
      .then(function (job) {
        if (job.error) throw new Error(job.error);
        if (!job.id) {
          button.textContent = "Drawn";
          return;
        }
        return new Promise(function (resolve) {
          var timer = setInterval(function () {
            ask("/job/" + job.id).then(function (state) {
              if (state.error) {
                clearInterval(timer);
                button.textContent = state.error;
                resolve();
                return;
              }
              // Counted rather than guessed at: a book with thirty-five chapters worth
              // drawing takes minutes, and a button that only says "Drawing…" for that
              // long is indistinguishable from one that has died.
              if (state.total > 1) button.textContent = state.done + " of " + state.total;
              if (state.stage === "done") {
                clearInterval(timer);
                resolve();
              }
            });
          }, 900);
        });
      })
      .then(function () {
        // Drawn now, so the row shows it. The tiles ask for the image again from
        // scratch, which is the only way past a browser that has cached the 404.
        location.reload();
      })
      .catch(function (problem) {
        button.textContent = String(problem.message || problem);
        button.disabled = false;
      });
  }

  /* --- putting it together ----------------------------------------------------- */

  function kept() {
    var found = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var name = localStorage.key(i) || "";
        if (name.indexOf("targum:vocab:") === 0) {
          found.push({ language: name.slice("targum:vocab:".length) });
        }
      }
    } catch (e) {}
    return found;
  }

  ask("/readers").then(function (data) {
    var readers = data.readers || [];
    canDraw = !!data.covers;
    var opened = stored("targum:opened");
    readers.forEach(function (reader) {
      reader.opened = opened[reader.document] || 0;
    });

    var everything = rows(readers);
    var host = document.getElementById("catalogue");
    var empty = document.getElementById("picked-empty");
    var tally = document.getElementById("tally");
    var find = document.getElementById("find");
    var clear = document.getElementById("clear");
    var chosen;

    function redraw() {
      remember("targum:library", view);
      chips(document.getElementById("register-chips"), REGISTERS, "register", redraw);
      chips(document.getElementById("kind-chips"), KINDS, "kind", redraw);
      choices(document.getElementById("length"), LENGTHS, "length", redraw);
      choices(document.getElementById("difficulty"), LEVELS, "level", redraw);
      choices(document.getElementById("where"), WHERE, "where", redraw);
      heading(redraw);

      var showing = sorted(
        everything.filter(function (row) {
          return matches(row, chosen);
        })
      );
      host.textContent = "";
      showing.forEach(function (row) {
        host.appendChild(draw(row));
      });
      empty.hidden = showing.length > 0;
      if (!showing.length) empty.textContent = "Nothing here matches that.";
      var total = everything.filter(function (row) {
        return base(row.language) === chosen;
      }).length;
      tally.textContent =
        showing.length === total
          ? total + (total === 1 ? " text" : " texts")
          : showing.length + " of " + total;
      clear.hidden = !(
        view.find ||
        view.kind ||
        view.register ||
        view.length ||
        view.level ||
        view.where
      );
    }

    find.value = view.find || "";
    find.addEventListener("input", function () {
      view.find = find.value.trim();
      redraw();
    });
    clear.addEventListener("click", function () {
      view.find = view.kind = view.register = view.length = view.level = view.where = "";
      find.value = "";
      redraw();
    });

    host.addEventListener("click", function (event) {
      var drawing = event.target.closest ? event.target.closest("[data-draw]") : null;
      if (drawing) return drawCovers(drawing, drawing.getAttribute("data-draw"));
      var button = event.target.closest ? event.target.closest("[data-build]") : null;
      if (!button) return;
      for (var i = 0; i < everything.length; i++) {
        if (everything[i].id === button.getAttribute("data-build") && everything[i].entry) {
          build(button, everything[i].entry);
          return;
        }
      }
    });

    // Hebrew is always on offer, whether or not anything is on the shelf in it.
    //
    // The languages after it are the reader's own: what they have built, and what they
    // have kept words in. The catalogue deliberately does not add to this list. It
    // holds one Russian novel, and letting it in put Russian in front of every visitor
    // who had never touched it — which is the opposite of what this switcher is for.
    var codes = [lang.HOME];
    readers.concat(kept()).forEach(function (thing) {
      var code = base(thing.language);
      if (code && codes.indexOf(code) < 0) codes.push(code);
    });
    codes = lang.order(codes, names);
    chosen = lang.current(codes);
    var betaNote = document.getElementById("beta-note");

    function show(code) {
      chosen = code;
      lang.switcher(document.getElementById("langs"), codes, names, code, show);
      if (betaNote) {
        betaNote.hidden = !lang.beta(code);
        if (lang.beta(code)) betaNote.textContent = lang.betaNote(code, names);
      }
      redraw();
    }

    show(chosen);

    // The shelf is ordered by when each text was last opened, and that is one of the
    // things the account keeps. Signing in on a second machine should therefore reorder
    // the list to match where the reader actually is in their reading.
    if (window.TargumSync) {
      window.TargumSync.onChange(function (changed) {
        if (!changed) return;
        var seen = stored("targum:opened");
        everything.forEach(function (row) {
          if (row.built) row.opened = seen[row.built.document] || 0;
        });
        redraw();
      });
      window.TargumSync.start();
    }
  });
})();
