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

  /* Words said through the page's `TargumStrings`, looked up when a thing is said: this
     file runs before the page has handed its strings over. Where there are none, the
     English here (targum-internal#184). */
  function t(key, english, fill) {
    var said = window.TargumStrings;
    if (said) return said.t(key, english, fill);
    return english.replace(/\{(\w+)\}/g, function (all, name) {
      return fill && Object.prototype.hasOwnProperty.call(fill, name) ? String(fill[name]) : all;
    });
  }
  function tn(key, count, one, other, fill) {
    var said = window.TargumStrings;
    if (said) return said.tn(key, count, one, other, fill);
    var values = { n: count };
    for (var name in fill || {}) values[name] = fill[name];
    return t(key, count === 1 ? one : other, values);
  }

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
    if (minutes < 2) return t("shelf.ago.now", "just now");
    if (minutes < 60) return tn("shelf.ago.minutes", minutes, "{n} minute ago", "{n} minutes ago");
    var hours = Math.round(minutes / 60);
    if (hours < 24) return tn("shelf.ago.hours", hours, "an hour ago", "{n} hours ago");
    var days = Math.round(hours / 24);
    return tn("shelf.ago.days", days, "yesterday", "{n} days ago");
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
        ? t("shelf.empty.language", "Nothing in {language} yet.", { language: named(code) })
        : t("shelf.empty", "Nothing here yet. We'll keep the texts you open here.");
      return;
    }
    note.textContent = settings.note || "";

    // A shelf of forty is a page of forty, and the point of this one is the top of it.
    // The rest are a page away rather than gone.
    var shown = settings.limit ? mine.slice(0, settings.limit) : mine;
    if (more && mine.length > shown.length) {
      more.hidden = false;
      more.textContent = t("shelf.see-all", "See all {n} →", { n: mine.length });
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
          ? tn("shelf.chapters", reader.chapters.length, "{n} chapter", "{n} chapters")
          : t("shelf.chapters-translated", "{done} of {total} translated", {
              done: reader.readyChapters,
              total: reader.chapters.length,
            })
        : reader.sections > 1
          ? tn("shelf.parts", reader.sections, "{n} part", "{n} parts")
          : "—";
      link.appendChild(bought);

      var when = document.createElement("span");
      when.className = "cell when";
      when.textContent = reader.opened ? ago(reader.opened) : t("shelf.not-opened", "not opened yet");
      link.appendChild(when);

      item.appendChild(link);

      var controls = document.createElement("span");
      controls.className = "row-controls";
      if (reader.chapters && reader.chapters.length) controls.appendChild(opener(reader, item));
      controls.appendChild(listLink(reader));
      controls.appendChild(binButton(reader, item));
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
    press.title = t("shelf.chapters-menu", "Chapters");
    press.textContent = t("shelf.chapters-menu", "Chapters");

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
      get.textContent = t("shelf.translate", "Translate");
      get.onclick = function () {
        get.disabled = true;
        get.textContent = t("shelf.translating", "Translating…");
        // In the language the reader reads into, so a Russian reader's press never buys
        // the folder's English (targum-internal#287).
        var into = window.TargumLang && window.TargumLang.into ? window.TargumLang.into() : "";
        post("/chapter", { name: reader.name, number: chapter.number, to: into }).then(function (job) {
          follow(job.id, get);
        }, function () {
          get.disabled = false;
          get.textContent = t("shelf.translate", "Translate");
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
          button.textContent = job.error || job.blocked || t("shelf.translate-failed", "We couldn't translate it. Try again.");
        }
      });
    }, 1500);
  }

  /* Into a playlist (targum-internal#364). A link rather than a sheet of its own: the
   * sheet is `/playlists?add=`, the one a reader's ⋯ menu opens too, so there is one
   * place that chooses a playlist and it cannot drift into two. */
  function listLink(reader) {
    var link = document.createElement("a");
    link.className = "add-to-list";
    link.href = keyed(
      "/playlists?add=" + encodeURIComponent(reader.name) + "&title=" + encodeURIComponent(reader.title || reader.name)
    );
    link.textContent = t("shelf.add-to-playlist", "Add to playlist");
    return link;
  }

  /* Throwing one away and getting it back.
   *
   * No confirmation step: the trash is the confirmation, and a dialog asking "are you
   * sure" before something reversible is a question nobody can answer usefully. But the
   * way back has to be where the press was. The row used to vanish into a reload, with
   * Put back in a panel further down the page, which a reader who pressed Delete for
   * Chapters did not know to look for (targum-internal#278). So the row stays, says where
   * the text went, and holds Undo under the same finger; the next load files it in Trash
   * with the others. */
  function binButton(reader, item) {
    var press = document.createElement("button");
    press.type = "button";
    press.className = "bin";
    press.textContent = t("shelf.delete", "Delete");
    press.title = t("shelf.delete.title", "Move to trash");
    press.onclick = function () {
      press.disabled = true;
      post("/trash", { name: reader.name }).then(function () {
        binned(reader, item);
      }, function () {
        press.disabled = false;
      });
    };
    return press;
  }

  function binned(reader, item) {
    var tree = item.nextElementSibling;
    if (tree && tree.classList.contains("chapters")) tree.remove();
    item.textContent = "";
    item.classList.add("binned");

    var said = document.createElement("span");
    said.className = "binned-note";
    said.setAttribute("role", "status");
    var title = document.createElement("bdi");
    title.setAttribute("lang", reader.language || "und");
    title.className = "book-title";
    title.textContent = reader.title;
    // The title wherever the sentence puts it: `{title}` marks the place.
    var sentence = t("shelf.binned", "{title} is in Trash");
    var at = Math.max(0, sentence.indexOf("{title}"));
    said.appendChild(document.createTextNode(sentence.slice(0, at)));
    said.appendChild(title);
    said.appendChild(document.createTextNode(sentence.slice(at).replace("{title}", "")));
    item.appendChild(said);

    var undo = document.createElement("button");
    undo.type = "button";
    undo.className = "restore";
    undo.textContent = t("shelf.undo", "Undo");
    undo.onclick = function () {
      undo.disabled = true;
      post("/restore", { name: reader.name }).then(reload, function () {
        undo.disabled = false;
      });
    };
    item.appendChild(undo);
    undo.focus();
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
        reader.goesIn >= 1
          ? tn("shelf.goes-in", reader.goesIn, "goes for good tomorrow", "goes for good in {n} days")
          : t("shelf.goes-today", "goes for good today");

      var back = document.createElement("button");
      back.type = "button";
      back.className = "restore";
      back.textContent = t("shelf.put-back", "Put back");
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
