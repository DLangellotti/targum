/* Learn — the page you land on.
 *
 * What you came back for, then what you have, then what you know. In that order, because
 * most visits are somebody returning to a text rather than looking for a new one, and
 * because the reader is a reader rather than a player: the numbers sit under the thing
 * you came to do, not over it.
 *
 * Everything here is drawn from what already exists. `targum:opened` says which text you
 * had open last and already syncs; `/readers` says what is on your shelf and, since
 * today, how much of each one's vocabulary you have already marked known. Nothing new is
 * tracked to make this page possible.
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
  var charts = window.TargumCharts;
  var lang = window.TargumLang;
  var names = window.TARGUM_LANGUAGES || {};

  function el(tag, className, text) {
    return charts.el(tag, className, text);
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  function post(path, body) {
    return ask(path, body).then(function (answer) {
      if (answer && answer.error) throw new Error(answer.error);
      return answer;
    });
  }

  function reload() {
    location.reload();
  }

  Array.prototype.forEach.call(document.querySelectorAll(".site-nav a"), function (link) {
    link.href = keyed(link.getAttribute("href"));
  });
  // The two shelf links carry which room to open in, so "the Beit Midrash" lands there.
  Array.prototype.forEach.call(document.querySelectorAll("[data-shelf]"), function (link) {
    link.href = keyed("/library") + (keyed("/library").indexOf("?") < 0 ? "?" : "&") +
      "shelf=" + link.getAttribute("data-shelf");
  });

  function named(code) {
    return names[code] || (code || "").toUpperCase();
  }

  /* --- what you have already ------------------------------------------------ */

  function ago(stamp) {
    var minutes = Math.round((Date.now() - stamp) / 60000);
    if (minutes < 2) return "just now";
    if (minutes < 60) return minutes + " minutes ago";
    var hours = Math.round(minutes / 60);
    if (hours < 24) return hours === 1 ? "an hour ago" : hours + " hours ago";
    var days = Math.round(hours / 24);
    return days === 1 ? "yesterday" : days + " days ago";
  }

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  function base(code) {
    return (code || "").split("-")[0].toLowerCase();
  }

  /* --- your shelf ------------------------------------------------------------ */

  function drawShelf(code, readers) {
    var list = document.getElementById("library-list");
    var note = document.getElementById("shelf-note");
    list.textContent = "";

    var mine = readers.filter(function (reader) {
      return base(reader.language) === code;
    });
    if (!mine.length) {
      note.textContent = readers.length
        ? "Nothing in " + named(code) + " yet. Start one above."
        : "Nothing here yet. Pick something above.";
      return;
    }
    note.textContent = "Last read first.";

    mine.forEach(function (reader) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href = keyed("/reader/" + reader.name + "/reader/index.html");

      var title = document.createElement("bdi");
      title.setAttribute("lang", reader.language || "und");
      title.className = "book-title";
      title.textContent = reader.title;
      link.appendChild(title);

      var facts = [];
      // A book says how much of it is bought. "3 of 20 chapters" is the whole of what
      // paying by the chapter looks like from here.
      if (reader.chapters && reader.chapters.length) {
        facts.push(reader.readyChapters + " of " + reader.chapters.length + " chapters");
      } else if (reader.sections > 1) {
        facts.push(reader.sections + " parts");
      }
      facts.push(reader.opened ? "opened " + ago(reader.opened) : "not opened yet");
      var meta = document.createElement("span");
      meta.className = "book-meta";
      meta.textContent = facts.join(" · ");
      link.appendChild(meta);

      item.appendChild(link);
      if (reader.chapters && reader.chapters.length) item.appendChild(opener(reader, item));
      item.appendChild(binButton(reader));
      list.appendChild(item);
    });
  }

  /* A book is one row that opens, not twenty rows.
   *
   * The alternative — a row per chapter — is honest about what is being bought and makes
   * a novel look like homework. This keeps the book as one thing and puts its chapters
   * one press away. */
  function opener(reader, item) {
    var press = document.createElement("button");
    press.type = "button";
    press.className = "open-chapters";
    press.setAttribute("aria-expanded", "false");
    press.title = "Chapters";
    press.textContent = "Chapters";

    var tree = null;
    press.onclick = function () {
      if (tree) {
        tree.remove();
        tree = null;
        press.setAttribute("aria-expanded", "false");
        return;
      }
      tree = chapterTree(reader);
      item.after(tree);
      press.setAttribute("aria-expanded", "true");
    };
    return press;
  }

  function chapterTree(reader) {
    var list = document.createElement("ol");
    list.className = "chapters";

    reader.chapters.forEach(function (chapter) {
      var row = document.createElement("li");
      if (!chapter.ready) row.className = "waiting";

      var name = document.createElement("a");
      name.href =
        keyed("/reader/" + reader.name + "/reader/" + chapter.file);
      name.appendChild(document.createTextNode(chapter.number + ". "));
      var title = document.createElement("bdi");
      title.setAttribute("lang", reader.language || "und");
      title.textContent = chapter.title;
      name.appendChild(title);
      row.appendChild(name);

      if (chapter.ready) {
        list.appendChild(row);
        return;
      }
      var get = document.createElement("button");
      get.type = "button";
      get.className = "get";
      get.textContent = "Translate";
      get.onclick = function () {
        get.disabled = true;
        get.textContent = "Translating…";
        post("/chapter", { name: reader.name, number: chapter.number }).then(function (job) {
          follow(job.id, get);
        }, function () {
          get.disabled = false;
          get.textContent = "Translate";
        });
      };
      row.appendChild(get);
      list.appendChild(row);
    });
    return list;
  }

  function follow(id, button) {
    var timer = setInterval(function () {
      ask("/job/" + id).then(function (job) {
        if (job.stage === "done") {
          clearInterval(timer);
          reload();
        } else if (job.stage === "failed" || job.blocked) {
          clearInterval(timer);
          button.disabled = false;
          button.textContent = job.error || job.blocked || "That did not work.";
        }
      });
    }, 1500);
  }

  /* Throwing one away and getting it back.
   *
   * Both go through the same shape: press, ask the server, redraw. There is no
   * confirmation step — the trash is the confirmation, and a dialog asking "are you
   * sure" before something reversible is a question nobody can answer usefully. */
  function binButton(reader) {
    var press = document.createElement("button");
    press.type = "button";
    press.className = "bin";
    press.textContent = "Delete";
    press.title = "Move to trash";
    press.onclick = function () {
      press.disabled = true;
      post("/trash", { name: reader.name }).then(reload, function () {
        press.disabled = false;
      });
    };
    return press;
  }

  function drawTrash(code, trash) {
    var panel = document.getElementById("trash-panel");
    var list = document.getElementById("trash-list");
    if (!panel || !list) return;
    var mine = trash.filter(function (reader) {
      return base(reader.language) === code;
    });
    panel.hidden = !mine.length;
    list.textContent = "";

    mine.forEach(function (reader) {
      var item = document.createElement("li");
      var title = document.createElement("bdi");
      title.setAttribute("lang", reader.language || "und");
      title.className = "book-title";
      title.textContent = reader.title;

      var meta = document.createElement("span");
      meta.className = "book-meta";
      // Said in days rather than a date: what a reader wants to know is how long they
      // have, not when the clock started.
      meta.textContent =
        reader.goesIn > 1
          ? "goes for good in " + reader.goesIn + " days"
          : reader.goesIn === 1
            ? "goes for good tomorrow"
            : "goes for good today";

      var back = document.createElement("button");
      back.type = "button";
      back.className = "restore";
      back.textContent = "Put back";
      back.onclick = function () {
        back.disabled = true;
        post("/restore", { name: reader.name }).then(reload, function () {
          back.disabled = false;
        });
      };

      var wrap = document.createElement("span");
      wrap.className = "gone";
      wrap.appendChild(title);
      wrap.appendChild(meta);
      item.appendChild(wrap);
      item.appendChild(back);
      list.appendChild(item);
    });
  }

  /* Languages this reader has words in. Signed out with nothing kept, this is empty
     and the switcher does not appear, which is the intended resting state. */
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


  /* --- what you came back for ------------------------------------------------ */

  function share(reader) {
    // `known` is absent for a targum built without word-level annotation, which is a
    // normal state rather than a fault. Saying nothing beats saying "0% known", because
    // "not measured" and "you know none of this" are very different claims about a book.
    if (typeof reader.known !== "number") return "";
    return Math.round(reader.known * 100) + "% of its words are ones you know";
  }

  function drawCarry(reader) {
    var panel = document.getElementById("carry");
    if (!reader) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    var link = document.getElementById("carry-link");
    link.href = keyed("/reader/" + reader.name + "/reader/index.html");
    var title = document.getElementById("carry-title");
    title.textContent = reader.title;
    title.setAttribute("lang", reader.language);

    var facts = [];
    if (reader.chapters && reader.chapters.length > 1) {
      facts.push(reader.readyChapters + " of " + reader.chapters.length + " chapters");
    } else if (reader.sections > 1) {
      facts.push(reader.sections + " parts");
    }
    facts.push(reader.opened ? "opened " + ago(reader.opened) : "not opened yet");
    document.getElementById("carry-meta").textContent = facts.join(" · ");

    var known = document.getElementById("carry-known");
    var said = share(reader);
    known.hidden = !said;
    known.textContent = said;
  }

  /* --- what you know --------------------------------------------------------- */

  function drawWords(code) {
    var panel = document.getElementById("words-panel");
    var store = charts.collect()[code];
    if (!store || !store.words.length) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    charts.tiles(document.getElementById("tiles"), store);
    charts.growth(document.getElementById("growth"), store.words);
  }

  /* --- putting it together --------------------------------------------------- */

  var opened = stored("targum:opened");

  ask("/readers")
    .then(function (data) {
      var readers = (data && data.readers) || [];
      var trash = (data && data.trash) || [];
      readers.forEach(function (reader) {
        reader.opened = opened[reader.document] || 0;
      });
      // What you had open last, then what was built most recently.
      readers.sort(function (a, b) {
        return b.opened - a.opened || b.built * 1000 - a.built * 1000;
      });

      // `kept()` is a list of {language}, not a map — reading it with Object.keys put a
      // language called "0" in the switcher.
      var vocabulary = kept();
      var codes = [lang.HOME];
      readers.concat(vocabulary).forEach(function (thing) {
        var code = base(thing.language);
        if (code && codes.indexOf(code) < 0) codes.push(code);
      });
      codes = lang.order(codes, names);

      var nothing = !readers.length && !vocabulary.length;
      document.getElementById("nothing").hidden = !nothing;
      document.getElementById("page").hidden = nothing;
      if (nothing) return;

      var chosen = lang.current(codes);

      function show(code) {
        chosen = code;
        lang.switcher(document.getElementById("langs"), codes, names, code, show);
        var mine = readers.filter(function (reader) {
          return base(reader.language) === code;
        });
        drawCarry(mine[0]);
        // The rest of the shelf. Repeating the one above it would be a list whose first
        // row is the thing already filling the top of the page.
        drawShelf(code, readers.filter(function (reader) {
          return reader !== mine[0];
        }));
        drawTrash(code, trash);
        drawWords(code);
      }

      show(chosen);
    })
    .catch(function () {
      // Signed out, or the server went away. The page says nothing rather than half of
      // something, and the nav is still there to leave by.
      document.getElementById("nothing").hidden = false;
    });

  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (changed) reload();
    });
    window.TargumSync.start();
  }
})();
