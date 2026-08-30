/* Your targums: the shelf, its chapters, and the trash.
 *
 * Learn shows the first few of these and a new page shows all of them, so the drawing of
 * a row lives here rather than in either — two copies of a row is two rows that stop
 * matching, which the library and the shelf had already done once.
 *
 * Rows are drawn from `/readers`, which is the server's answer about what this person has
 * built. Everything a row can do — open a chapter, buy the next one, throw the whole
 * thing away — goes back to the same server.
 */

(function () {
  "use strict";

  var key = window.TARGUM_KEY;

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

  function named(code) {
    return names[code] || (code || "").toUpperCase();
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

  function ago(stamp) {
    var minutes = Math.round((Date.now() - stamp) / 60000);
    if (minutes < 2) return "just now";
    if (minutes < 60) return minutes + " minutes ago";
    var hours = Math.round(minutes / 60);
    if (hours < 24) return hours === 1 ? "an hour ago" : hours + " hours ago";
    var days = Math.round(hours / 24);
    return days === 1 ? "yesterday" : days + " days ago";
  }

  function base(code) {
    return (code || "").split("-")[0].toLowerCase();
  }

  /* --- your shelf ------------------------------------------------------------ */

  function drawShelf(code, readers, options) {
    var settings = options || {};
    var list = document.getElementById("library-list");
    var note = document.getElementById("shelf-note");
    var head = document.getElementById("shelf-head");
    var more = document.getElementById("shelf-more");
    list.textContent = "";
    if (head) head.hidden = true;
    if (more) more.hidden = true;

    var mine = readers.filter(function (reader) {
      return base(reader.language) === code;
    });
    if (!mine.length) {
      note.textContent = readers.length
        ? "Nothing in " + named(code) + " yet."
        : "Nothing here yet. Texts you open land here.";
      return;
    }
    note.textContent = settings.note || "";

    // A shelf of forty is a page of forty, and the point of this one is the top of it.
    // The rest are a page away rather than gone.
    var shown = settings.limit ? mine.slice(0, settings.limit) : mine;
    if (more && mine.length > shown.length) {
      more.hidden = false;
      more.textContent = "See all " + mine.length + " →";
    }

    shown.forEach(function (reader) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href = keyed("/reader/" + encodeURIComponent(reader.name) + "/reader/index.html");

      // A drawn cover where there is one, and the text's own first letter where there
      // is not — which is most of them. Covers are drawn for the library's own texts, so
      // a news article somebody pasted in this morning will never have one, and a shelf
      // of empty frames would be worse than a shelf of letters.
      link.appendChild(
        window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(reader.entry || reader.name)), {
          title: reader.title,
          language: reader.language,
          drawn: reader.drawn,
        })
      );

      // One cell for the title and, under it, its English where the catalogue has one.
      // The link lays its children out as the row's own grid cells, so the two share a
      // wrapper rather than taking a column each; an upload has no English and the
      // wrapper holds the Hebrew alone.
      var what = document.createElement("span");
      what.className = "book-what";
      var title = document.createElement("bdi");
      title.setAttribute("lang", reader.language || "und");
      title.className = "book-title";
      title.textContent = reader.title;
      what.appendChild(title);
      if (reader.english) {
        var english = document.createElement("span");
        english.className = "book-english";
        english.setAttribute("lang", "en");
        english.setAttribute("dir", "ltr");
        english.textContent = reader.english;
        what.appendChild(english);
      }
      link.appendChild(what);

      // A column each, rather than one line of facts separated by dots. "25 of 36" is
      // the whole of what paying by the chapter looks like from here, and it belongs
      // under a heading that says so.
      var bought = document.createElement("span");
      bought.className = "cell count";
      // "4 of 4" is a fraction with nothing left to say.
      bought.textContent = reader.chapters && reader.chapters.length
        ? reader.readyChapters === reader.chapters.length
          ? reader.chapters.length + (reader.chapters.length === 1 ? " chapter" : " chapters")
          : reader.readyChapters + " of " + reader.chapters.length + " translated"
        : reader.sections > 1
          ? reader.sections + " parts"
          : "—";
      link.appendChild(bought);

      var when = document.createElement("span");
      when.className = "cell when";
      when.textContent = reader.opened ? ago(reader.opened) : "not opened yet";
      link.appendChild(when);

      item.appendChild(link);

      var controls = document.createElement("span");
      controls.className = "row-controls";
      if (reader.chapters && reader.chapters.length) controls.appendChild(opener(reader, item));
      controls.appendChild(binButton(reader));
      item.appendChild(controls);
      list.appendChild(item);
    });
    if (head) head.hidden = false;
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
        keyed("/reader/" + encodeURIComponent(reader.name) + "/reader/" + encodeURIComponent(chapter.file));
      // A chapter that names something may have a cover of its own; the rest fall back
      // to the book's on the server, so every row carries the same one either way.
      var cover = window.TargumCovers.chapterName(reader.entry || reader.name, chapter.number);
      name.appendChild(
        window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(cover)), {
          title: chapter.title || reader.title,
          language: reader.language,
          className: "thumb tiny",
        })
      );
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

  window.TargumShelf = {
    draw: drawShelf,
    trash: drawTrash,
    ago: ago,
    base: base,
  };
})();
