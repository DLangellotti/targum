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

  /* What a text is, called what a reader would call it — which is not always what the
     catalogue calls it. "Prose" is the catalogue's word for the narrative books of the
     Tanakh, and beside "Novels" and "Stories", which are also prose, it says nothing to
     anybody. "News" is what an article is.

     Scenes first: the hundred numbered dialogues are where a reader with no words at all
     starts, and the chip that opens that path should be the first one met. After it,
     ordered by how much of the catalogue each one holds, so the next chips a reader
     meets are the ones with fifty texts behind them rather than the ones with two.
     Fixed rather than recomputed: a row of filters that rearranges itself as you use it
     is a row you have to read every time. "Bible narrative" rather than "Narrative":
     beside Novels and Stories the bare word said nothing, and what it names is the story
     books of the Bible. */
  var KINDS = [
    ["dialogue", "Scenes"],
    ["story", "Stories"],
    ["article", "News"],
    ["novel", "Novels"],
    ["essay", "Essays"],
    ["prose", "Bible narrative"],
    ["poetry", "Poetry"],
    ["document", "Documents"],
    ["play", "Plays"],
  ];

  var REGISTERS = [
    ["biblical", "Biblical"],
    ["modern", "Modern"],
  ];

  //: Only one direction is worth offering. "Without audio" is not a thing anybody looks
  //: for — the question is always whether there is something to listen to.
  var SPOKEN = [
    ["", "Any"],
    ["yes", "With audio"],
  ];

  var LENGTHS = [
    ["", "Any"],
    ["short", "Under 20 min"],
    ["hour", "20 min – 2 hr"],
    ["long", "Over 2 hr"],
  ];

  // The share of running words a reader would have to look up, in three steps. The
  // numbers behind them are measured off each text: see scripts/measure_difficulty.py.
  // Said in words as well as tiers, because the cutoffs were never stated anywhere:
  // "Beginners cannot understand library listings", said the first alpha reader.
  var LEVELS = [
    ["", "Any"],
    ["easy", "Easier — up to 1 word in 5 new"],
    ["mid", "Middling — about 1 in 4"],
    ["hard", "Harder — more than 1 in 4"],
  ];

  // The same number as a sentence: 17% is "about 1 word in 6 is hard". "Hard" because
  // it is the reader's own word — the band the count starts at is the one every tapped
  // word calls "hard", and the highlight menu offers "hard and up". Not "new to you":
  // the share is a fact about the text — how much of its vocabulary is rare — and a
  // reader who knows no words looks up all twenty-two of a text that says 0%.
  function inWords(share) {
    if (!share) return "";
    return "about 1 word in " + Math.max(2, Math.round(100 / share)) + " is hard";
  }

  /* One line under the controls that says what the active one means — for the reader
     who cannot yet read a title on the page, the most important sentence on it. Stated,
     never justified. At most two clauses; the first is the one that changes what the
     list is. "—" is explained only while one is on screen. */
  var NOTES = {
    base: "Tap a text to read it.",
    kind: {
      dialogue: "Scenes — numbered conversations with audio. Start at 1.",
      prose: "Bible narrative — the Bible's story books.",
      article: "News — the Israeli press, in the week it was written.",
      play: "Plays — a speaker, then a line.",
    },
    register: {
      biblical: "Biblical — the Hebrew of the Bible.",
      modern: "Modern — Hebrew as it is written today.",
    },
    spoken: "With audio — a recording, line by line.",
    sort: {
      difficulty: "New words — the share of a text's words that are hard.",
    },
    unmeasured: "— means not measured yet.",
  };

  function noteFor(showing) {
    var clauses = [];
    if (view.kind && NOTES.kind[view.kind]) clauses.push(NOTES.kind[view.kind]);
    if (view.register && NOTES.register[view.register]) clauses.push(NOTES.register[view.register]);
    if (view.spoken === "yes") clauses.push(NOTES.spoken);
    if (NOTES.sort[view.sort]) clauses.push(NOTES.sort[view.sort]);
    if (!clauses.length) clauses.push(NOTES.base);
    clauses = clauses.slice(0, 2);
    var dashed = showing.some(function (row) {
      return !measured(row);
    });
    if (dashed) clauses[Math.min(1, clauses.length)] = NOTES.unmeasured;
    return clauses.join(" · ");
  }

  /* Where the line is drawn. Under the controls, as `#picked-note`, every time but one:
     on the first visit of an account that knows no words, when the page has opened on
     the Scenes for them, it goes under the heading and above every control, because
     "Start at 1" has to be read before thirteen chips they do not yet understand. */
  var leading = false;
  function placeNote(text) {
    var note = document.getElementById("picked-note");
    var top = document.getElementById("picked-lead");
    var lead = leading && view.kind === "dialogue" && !!top;
    if (top) {
      top.hidden = !lead;
      top.textContent = lead ? text : "";
    }
    note.hidden = lead;
    note.textContent = lead ? "" : text;
  }

  /* The two halves of the page. The catalogue is everybody's; an upload is yours and
     nobody else can reach it. Tabs rather than a filter: they are not two settings of one
     list, they are two lists, and as a select called "Access" the second one was a thing
     nobody found. */
  var WHERE = [
    ["library", "Library"],
    ["mine", "Your Uploads"],
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

  /* Whether a row's share means anything. Zero is a measurement on a catalogue text — a
     twenty-word scene with no uncommon word in it — and "not measured" on an upload
     built without word-level annotation. The two are different claims, and only the
     second is drawn as a dash. */
  function measured(row) {
    return row.difficulty > 0 || !!row.entry;
  }

  function level(row) {
    if (!measured(row)) return "";
    var share = row.difficulty || 0;
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
  function rows(readers, shared) {
    var mine = {};
    var out = [];
    // The shared texts first, then the reader's own over them: a text on both is one
    // row, and it is theirs. A shared row opens like any built text and offers nothing
    // else — nothing on it can be bought, drawn or trashed, which `within()` on the
    // server already refuses. Before this the page read only the reader's own, so a
    // seeded scene showed as an unbuilt button and pressing it built a personal copy.
    (shared || []).forEach(function (reader) {
      if (reader.entry) mine[reader.entry] = reader;
    });
    readers.forEach(function (reader) {
      if (reader.entry) mine[reader.entry] = reader;
    });
    catalogue.forEach(function (entry) {
      var built = mine[entry.id];
      out.push({
        id: entry.id,
        entry: entry,
        title: entry.title,
        english: entry.english || "",
        author: entry.author,
        language: entry.language,
        kind: entry.kind,
        register: entry.register,
        difficulty: entry.difficulty,
        minutes: entry.minutes,
        spoken: !!entry.spoken,
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
        english: "",
        author: "",
        language: reader.language,
        kind: reader.kind,
        register: reader.register,
        difficulty: reader.difficulty,
        minutes: reader.minutes,
        spoken: !!reader.spoken,
        built: reader,
        opened: reader.opened || 0,
      });
    });
    return out;
  }

  /* --- drawing one ----------------------------------------------------------- */

  function gauge(row) {
    var box = el("span", "gauge");
    if (!measured(row)) {
      box.appendChild(el("span", "col count", "—"));
      return box;
    }
    var share = row.difficulty || 0;
    var track = el("span", "track");
    var fill = el("span", "fill");
    var reach = Math.max(6, Math.min(100, ((share - FLOOR) / (CEILING - FLOOR)) * 100));
    fill.style.inlineSize = reach + "%";
    track.appendChild(fill);
    box.appendChild(track);
    box.appendChild(el("span", "col count", share + "%"));
    var said = inWords(share);
    if (said) box.title = said;
    box.setAttribute("aria-label", share + "% new words" + (said ? ": " + said : ""));
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
      open.href = keyed("/reader/" + encodeURIComponent(row.built.name) + "/reader/index.html");
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
    // A scene says which it is, outside the Hebrew's own direction, before the title.
    var number = window.TargumScenes ? window.TargumScenes.numberOf(row.id) : 0;
    if (number) title.appendChild(el("span", "row-scene", "Scene " + number));
    var bdi = el("bdi", null, row.title);
    title.appendChild(bdi);
    // The one row to open next: the first scene not yet finished. "Start here" until
    // something has been, "Next" after. Ink, not accent — `.pointed` already spends the
    // page's accent on the row somebody was sent to — and a status, so what is read out
    // is what is seen.
    if (nextRow && row.id === nextRow.entry) {
      var chip = el("span", "row-next", anyFinished ? "Next" : "Start here");
      chip.setAttribute("role", "status");
      title.appendChild(chip);
    }
    what.appendChild(title);
    // The English under the Hebrew, in ink, with the byline after it: for a reader who
    // cannot yet read the line above, this is the title. Its own element, so the two
    // directions never share a string. An upload has no English and keeps its byline
    // line as it was.
    if (row.english) {
      var english = el("span", "row-english", row.english);
      english.setAttribute("lang", "en");
      english.setAttribute("dir", "ltr");
      if (row.author) english.appendChild(el("span", "row-by-after", " · " + row.author));
      what.appendChild(english);
    } else if (row.author) {
      what.appendChild(el("span", "row-by", row.author));
    }
    // Personal, where it can be: a text on the shelf is measured against the reader's
    // own words. Absent for one never built, for one built without word-level
    // annotation — "not measured" and "you know none of this" are different claims —
    // and at zero: "you know 0% of its words" is true and unkind, and the line starts
    // once there is something to say (as Learn's does).
    if (row.built && typeof row.built.known === "number" && row.built.known > 0) {
      what.appendChild(
        el("span", "row-fit", "you know " + Math.round(row.built.known * 100) + "% of its words")
      );
    }
    // The one thing on a row that is not a column: a text either can be listened to or
    // cannot, and a column of blanks down the page to say "no audio" would be noise.
    // No tooltip: what the word means is said in the line under the controls, where a
    // phone can read it.
    if (row.spoken) what.appendChild(el("span", "row-audio", "audio"));
    open.appendChild(what);

    open.appendChild(el("span", "col label drop", named(KINDS, row.kind)));
    open.appendChild(el("span", "col label drop", named(REGISTERS, row.register)));
    open.appendChild(el("span", "col count", said(row.minutes)));
    var hard = gauge(row);
    hard.className = "gauge drop";
    open.appendChild(hard);

    /* Where a build narrates itself — and, on a text this reader has finished, the one
       word that says so, in leaf: a real state, not a score, and the only leaf on the
       page. It used to say Public or Private, which the two
       tabs say once at the top now — but it is also what `build()` writes into, and a
       row with nothing to write into threw the moment anybody pressed one. Empty until
       there is something to say, and its column collapses to nothing while it is. */
    var state = el("span", "row-state");
    if (row.built && finishedDocs[row.built.document] && finishedDocs[row.built.document].done) {
      state.className = "row-state finished";
      state.textContent = "finished";
    }
    open.appendChild(state);

    item.appendChild(open);

    // Only where there is something to draw: a text on the shelf, from the library's own
    // catalogue — a cover is drawn from what the catalogue says a text is — and with no
    // cover yet. And only where this deployment has a key to draw with.
    if (canDraw && row.built && !row.built.shared && row.entry && !row.drawn) {
      var draw = el("button", "draw", "Draw cover");
      draw.type = "button";
      draw.setAttribute("data-draw", row.built.name);
      item.appendChild(draw);
    }
    return item;
  }

  /* --- sorting and sifting ---------------------------------------------------- */

  var SORTS = {
    // By the English where there is one: for the reader this page is sorted for, the
    // Hebrew titles are not yet in an order.
    title: function (row) {
      return row.english || row.title || "";
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
  };

  var COLUMNS = [
    ["", ""],
    ["title", "Text"],
    ["kind", "Kind"],
    ["register", "Hebrew"],
    ["minutes", "Length"],
    // What the number under it means, said the way somebody choosing a text would ask
    // it. "Looked up" is the measurement's name, not the reader's question.
    ["difficulty", "New words"],
    // Unlabelled: the column a build narrates itself in, empty the rest of the time.
    ["", ""],
  ];

  // Whether the server can draw at all, answered by the server. A deployment with no
  // image key offers nothing rather than offering and failing.
  var canDraw = false;
  // The reader's own finishes, by content hash, and the scene to open next — set once
  // the server has said what is shared.
  var finishedDocs = stored("targum:docs");
  var nextRow = null;
  var anyFinished = false;

  // Whether this browser has ever drawn the page. A remembered view means the reader has
  // made choices here before, and those win over anything the page would choose for
  // them; only a first visit is the page's to open somewhere.
  var firstVisit = false;
  try {
    firstVisit = localStorage.getItem("targum:library") === null;
  } catch (e) {
    firstVisit = false;
  }

  var view = stored("targum:library");
  // Easiest first. The default was by access, which sorted the catalogue into public and
  // private — a fact about who may read a text rather than about whether this reader
  // can. Somebody arriving at forty texts in a language they are learning is asking
  // which of them they can read now, and that is what the list answers.
  if (!view.sort) view.sort = "difficulty";
  if (!view.dir) view.dir = 1;
  if (!view.kind) view.kind = "";
  if (!view.register) view.register = "";
  if (!view.where) view.where = "library";

  /* Whether one row survives the filters. `using` lets a caller ask the question against
     a different set of them — see `present()`, which asks it with one filter lifted. */
  function matches(row, code, using) {
    var state = using || view;
    if (base(row.language) !== code) return false;
    if (state.kind && row.kind !== state.kind) return false;
    if (state.register && row.register !== state.register) return false;
    if (state.length && lengthOf(row.minutes) !== state.length) return false;
    if (state.spoken === "yes" && !row.spoken) return false;
    if (state.level && level(row) !== state.level) return false;
    if (state.where === "mine" && row.entry) return false;
    if (state.where !== "mine" && !row.entry) return false;
    if (state.find) {
      // The blurb and the name the text is filed under are in this on purpose. A reader
      // typing "herzl" into a library of Hebrew titles otherwise finds nothing: the
      // titles and the bylines are both in Hebrew, and the only Latin a text carries is
      // the sentence describing it and its own id.
      var hay = [row.title, row.english, row.author, row.entry ? row.entry.blurb : "", row.id]
        .join(" ")
        .toLowerCase();
      if (hay.indexOf(state.find.toLowerCase()) < 0) return false;
    }
    return true;
  }

  function sorted(list) {
    // A numbered sequence has one order. Under the Scenes chip the list is scene 1, 2,
    // 3… whatever column was last sorted on — their measured shares are noise at twenty
    // words — and the heading says so (see `heading()`).
    if (view.kind === "dialogue" && window.TargumScenes) return window.TargumScenes.ordered(list);
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

  /* Which values of one field the rest of the filters leave standing.
   *
   * Computed against everything except the field being drawn, so choosing a kind never
   * removes the other kinds from the row it lives in — that would be a filter that eats
   * itself. */
  function present(rows, field, code) {
    var seen = {};
    rows.forEach(function (row) {
      var pretend = {};
      for (var key in view) pretend[key] = view[key];
      pretend[field] = "";
      if (matches(row, code, pretend)) seen[row[field]] = true;
    });
    return seen;
  }

  function chips(host, options, field, redraw, shape, seen) {
    host.textContent = "";
    var offered = seen
      ? options.filter(function (pair) {
          return seen[pair[0]];
        })
      : options;
    // Nothing to choose between is not a choice: one kind left, or none, and the row of
    // chips is the word "All" on its own.
    if (seen && offered.length < 2) offered = [];
    var all = offered.length ? [["", "All"]].concat(offered) : [];
    all.forEach(function (pair) {
      var chip = el("button", shape || "chip", pair[1]);
      chip.type = "button";
      chip.setAttribute("aria-pressed", view[field] === pair[0] ? "true" : "false");
      chip.addEventListener("click", function () {
        view[field] = pair[0];
        redraw();
      });
      host.appendChild(chip);
    });
  }

  /* The one control that changes which list you are looking at rather than what it is
     narrowed to. Underlined rather than pilled: the page already has pills for the
     language above it and chips for the filters below, and a third row of the same shape
     would be a third thing to tell apart. */
  function tabs(host, options, field, redraw) {
    if (!host) return;
    host.textContent = "";
    options.forEach(function (pair) {
      var tab = el("button", "tab", pair[1]);
      tab.type = "button";
      tab.setAttribute("role", "tab");
      var on = (view[field] || options[0][0]) === pair[0];
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.addEventListener("click", function () {
        view[field] = pair[0];
        redraw();
      });
      host.appendChild(tab);
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
      // Under the Scenes chip the list is in scene order whatever this column says, so
      // the column says that instead, and cannot be pressed: a heading reading "New
      // words" over a list not in that order would be a lie.
      var scenes = pair[0] === "difficulty" && view.kind === "dialogue";
      button.appendChild(document.createTextNode(scenes ? "Scene number" : pair[1]));
      if (pair[0] === "difficulty") button.className = "drop";
      if (scenes) {
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
      } else if (view.sort === pair[0]) {
        button.setAttribute("aria-sort", view.dir > 0 ? "ascending" : "descending");
        button.appendChild(el("span", "arrow", view.dir > 0 ? " ↑" : " ↓"));
      }
      button.addEventListener("click", function () {
        if (scenes) return;
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
            window.location.href = keyed("/reader/" + job.reader.split("/").map(encodeURIComponent).join("/"));
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
      // The language this reader reads into, not English by assumption. They read in
      // two; a button that always bought one of them would be a button that reads their
      // mind wrong half the time. Clamped to what the account is offered, so a
      // remembered choice that no longer stands asks for English rather than a refusal.
      to: window.TargumSync ? window.TargumSync.into(lang.into()) : lang.into() || "en",
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
    var shared = data.shared || [];
    canDraw = !!data.covers;
    var opened = stored("targum:opened");
    readers.concat(shared).forEach(function (reader) {
      reader.opened = opened[reader.document] || 0;
    });
    if (window.TargumScenes) {
      nextRow = window.TargumScenes.next(shared, finishedDocs);
      anyFinished = shared.some(function (reader) {
        return window.TargumScenes.numberOf(reader.entry) > 0 && window.TargumScenes.finished(reader, finishedDocs);
      });
    }

    var everything = rows(readers, shared);
    var host = document.getElementById("catalogue");
    var empty = document.getElementById("picked-empty");
    var tally = document.getElementById("tally");
    var find = document.getElementById("find");
    var clear = document.getElementById("clear");
    var chosen;

    function redraw() {
      remember("targum:library", view);
      chips(document.getElementById("register-chips"), REGISTERS, "register", redraw, "segment");
      // Only the kinds that are actually in front of this reader. A row of seven chips
      // where three of them find nothing — and one of them is "Documents" — is seven
      // things to read and four dead ends.
      chips(
        document.getElementById("kind-chips"),
        KINDS,
        "kind",
        redraw,
        "chip",
        present(everything, "kind", chosen)
      );
      choices(document.getElementById("audio"), SPOKEN, "spoken", redraw);
      choices(document.getElementById("length"), LENGTHS, "length", redraw);
      choices(document.getElementById("difficulty"), LEVELS, "level", redraw);
      tabs(document.getElementById("where"), WHERE, "where", redraw);
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
      placeNote(noteFor(showing));
      pointAt();
      // Counted within the list being looked at, not across both: "2 of 116" under Your
      // Uploads would be counting somebody's two texts against everybody's catalogue.
      var here = everything.filter(function (row) {
        return base(row.language) === chosen && (view.where === "mine" ? !row.entry : row.entry);
      });
      empty.hidden = showing.length > 0;
      if (!showing.length) {
        // An empty tab and an empty filter are different things to be told.
        empty.textContent = here.length
          ? "Nothing here matches that."
          : view.where === "mine"
            ? "Nothing uploaded yet. Add your own from Upload."
            : "Nothing here yet.";
      }
      var total = here.length;
      tally.textContent =
        showing.length === total
          ? total + (total === 1 ? " text" : " texts")
          : showing.length + " of " + total;
      clear.hidden = !(view.find || view.kind || view.register || view.length || view.level);
    }

    /* Learn suggests something to read and links here with the id in the hash. Finding it
       is the reader's problem otherwise: this catalogue is forty rows and the thing they
       were sent for could be anywhere in it. Marked and scrolled to, never pressed —
       what pressing an unbuilt row does is start spending, and nothing arrives at a page
       with permission to do that. */
    var lifted = false;
    function pointAt() {
      var wanted = decodeURIComponent((location.hash || "").slice(1));
      if (!wanted) return;
      var row = host.querySelector('[data-row="' + wanted.replace(/"/g, "") + '"]');
      if (row) {
        row.classList.add("pointed");
        if (row.scrollIntoView) row.scrollIntoView({ block: "center" });
        return;
      }
      /* Not drawn. The filters, the tab and the language are all remembered between
         visits, so somebody sent here by Learn could arrive at a list that hides the one
         text they came for, land at the top of it, and have nothing to tell them why.
         Being sent is a stronger claim than a filter set on some earlier visit: lift them
         and draw again. Once — `lifted` is what stops an id that is genuinely not in this
         catalogue from doing it on every redraw. */
      if (lifted) return;
      var target = null;
      for (var i = 0; i < everything.length; i++) {
        if (everything[i].id === wanted) {
          target = everything[i];
          break;
        }
      }
      if (!target) return;
      lifted = true;
      view.find = view.kind = view.register = view.length = view.level = "";
      view.where = target.entry ? "library" : "mine";
      find.value = "";
      var code = base(target.language);
      // show() redraws, and redraw() comes back through here with the row in the list.
      if (code && code !== chosen) return show(code);
      redraw();
    }

    find.value = view.find || "";
    find.addEventListener("input", function () {
      view.find = find.value.trim();
      redraw();
    });
    clear.addEventListener("click", function () {
      // Not `where`: Clear empties the filters, and which of the two lists you are
      // looking at is not one of them.
      view.find = view.kind = view.register = view.length = view.level = "";
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
    var all = [lang.HOME];
    readers.concat(kept()).forEach(function (thing) {
      var code = base(thing.language);
      if (code && all.indexOf(code) < 0) all.push(code);
    });
    var codes = lang.order(all, names);
    chosen = lang.current(codes);
    var betaNote = document.getElementById("beta-note");

    /* Where the page opens for an account that knows nothing. A first visit, no word
       marked in Hebrew and nothing of their own in it: the list opens on the Scenes,
       in order, with the line that says to start at 1 above everything else. Once
       only — from then on the view is remembered and the reader's own choices win. The
       count is the same one Learn opens with, from the same store. */
    if (firstVisit && chosen === lang.HOME && !view.kind) {
      var charts = window.TargumCharts;
      var store = charts ? charts.collect(charts.meaningLanguage(chosen))[chosen] : null;
      var known = charts ? charts.known(store && store.words) : 0;
      var ownHebrew = readers.some(function (reader) {
        return base(reader.language) === chosen;
      });
      if (!known && !ownHebrew) {
        view.kind = "dialogue";
        leading = true;
      }
    }

    function show(code) {
      chosen = code;
      lang.set(code);
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
    //
    // And which languages the switcher offers is the account's answer too, which it
    // gave after the switcher was drawn: asked again here whether or not any words came
    // with it, or a reader who ticked Yiddish on another machine saw Hebrew alone here
    // until a reload.
    if (window.TargumSync) {
      window.TargumSync.onChange(function (changed) {
        var before = codes.join();
        codes = lang.order(all, names);
        var switched = codes.join() !== before;
        if (switched && codes.indexOf(chosen) < 0) chosen = lang.current(codes);
        if (changed) {
          var seen = stored("targum:opened");
          everything.forEach(function (row) {
            if (row.built) row.opened = seen[row.built.document] || 0;
          });
        }
        if (switched) show(chosen);
        else if (changed) redraw();
      });
      window.TargumSync.start();
    }
  })
    // Nothing to list, because nothing could be asked. The catalogue is still drawn from
    // what the page was built with; what fails here is only which of it you already have.
    .catch(function () {});
})();
