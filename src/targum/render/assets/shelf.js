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
    var going = building(settings.building).filter(function (job) {
      return base(job.language) === code;
    });
    going.forEach(function (job) {
      list.appendChild(buildingRow(job));
    });
    if (!mine.length && going.length) {
      note.textContent = settings.note || "";
      return;
    }
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

    var docs = stored("targum:docs");
    shown.forEach(function (reader) {
      list.appendChild(row(reader, docs));
    });
    if (head) head.hidden = false;
  }


  /* --- what is being built (design.md §12, "Yours and everyone's", 2026-09-25) --------
   *
   * A build is a row at the top of Your targums from the moment it starts. It was a card
   * under the Library's Your uploads, which made the Library the one place that could
   * say "everything of yours is here" while Your targums said the same thing and lacked
   * it; and the wait page sent a reader to Your targums to find it.
   *
   * Neither a link nor a button: there is nothing to open yet and nothing to buy again.
   * It says the title, how far the build has got, and Building, and it is replaced by
   * the ordinary row when the build is done. `/jobs` is what the bell polls, so the two
   * cannot disagree about what is happening. */
  function building(jobs) {
    return (jobs || []).filter(function (job) {
      return job.stage !== "done" && !job.error && job.title;
    });
  }

  /* The pipeline narrates itself in its own words; these three are the reader's, the
     same keys the Library's row uses for its own build. Anything else it says — "Fetching
     the recording…" — is already a sentence and is said as it came. */
  function plain(message) {
    var words = {
      "Finding each word's dictionary form…": t("library.build.words", "We're reading the words…"),
      "Adding vowel points…": t("library.build.points", "We're adding vowel points…"),
      "Building the reader…": t("library.build.page", "We're setting the page…"),
    };
    return words[message] || message;
  }

  function buildingRow(job) {
    var item = document.createElement("li");
    item.className = "is-building";
    // Said aloud when it changes, because a reader watching this is waiting on it.
    item.setAttribute("role", "status");
    var box = document.createElement("span");
    box.className = "building";
    box.appendChild(
      window.TargumCovers.tile("", { title: job.title, language: job.language, drawn: false })
    );

    var what = document.createElement("span");
    what.className = "book-what";
    var title = document.createElement("bdi");
    title.setAttribute("lang", job.language || "und");
    title.className = "book-title";
    title.textContent = job.title;
    what.appendChild(title);
    if (job.english) {
      var english = document.createElement("span");
      english.className = "book-english";
      english.setAttribute("lang", "en");
      english.setAttribute("dir", "ltr");
      english.textContent = job.english;
      what.appendChild(english);
    }
    var line = document.createElement("span");
    line.className = "book-facts";
    var said = [];
    if (job.behind) {
      said.push(
        tn("shelf.building.behind", job.behind, "Waiting behind {n} build", "Waiting behind {n} builds")
      );
    } else if (job.message) {
      said.push(plain(job.message));
    }
    if (job.total > 1) {
      said.push(t("shelf.building.share", "{n}% done", { n: Math.floor((job.done / job.total) * 100) }));
    }
    said.forEach(function (fact) {
      var bit = document.createElement("span");
      bit.className = "fact";
      bit.textContent = fact;
      line.appendChild(bit);
    });
    // The status again, for a phone, where the pill beside the row folds away.
    var folded = document.createElement("span");
    folded.className = "fact fact-status is-building";
    folded.textContent = t("shelf.status.building", "Building");
    line.appendChild(folded);
    what.appendChild(line);
    box.appendChild(what);

    var pill = document.createElement("span");
    pill.className = "row-status is-building";
    pill.textContent = t("shelf.status.building", "Building");
    box.appendChild(pill);
    item.appendChild(box);
    // The controls' column, empty: nothing on a build can be pressed.
    var controls = document.createElement("span");
    controls.className = "row-controls";
    item.appendChild(controls);
    return item;
  }

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  /* --- one row: what a text is at a glance (design.md §12, 2026-09-24) ----------------
   *
   * The picture; the title with its English under it; one line of facts (length, level,
   * how much of it the reader knows, when it came, the playlists it is in); its status;
   * and Add to playlist with a ⋯ for the rest. A phone keeps the picture and the title,
   * wraps the facts under them, folds the status into the facts and keeps two keys. */
  function row(reader, docs) {
    var item = document.createElement("li");
    var link = document.createElement("a");
    link.href = keyed("/reader/" + encodeURIComponent(reader.name) + "/reader/index.html");
    link.appendChild(
      window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(reader.entry || reader.name)), {
        title: reader.title,
        language: reader.language,
        drawn: reader.drawn,
      })
    );

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
    var state = status(reader, docs);
    what.appendChild(facts(reader, state));
    link.appendChild(what);

    var pill = document.createElement("span");
    pill.className = "row-status is-" + state.kind;
    if (state.kind === "finished") pill.appendChild(checkMark());
    pill.appendChild(document.createTextNode(state.said));
    link.appendChild(pill);
    item.appendChild(link);

    var controls = document.createElement("span");
    controls.className = "row-controls";
    if (!reader.shared) controls.appendChild(listLink(reader));
    controls.appendChild(more(reader, item));
    item.appendChild(controls);
    return item;
  }

  // A check in leaf, the mark Recently read already gives a text read through.
  function checkMark() {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M3.5 8.5l3 3 6-7");
    svg.appendChild(path);
    return svg;
  }

  function facts(reader, state) {
    var line = document.createElement("span");
    line.className = "book-facts";
    var said = [];
    var length = lengthOf(reader);
    if (length) said.push(length);
    var level = levelOf(reader.level);
    if (level) said.push(level);
    if (typeof reader.known === "number" && reader.words) {
      said.push(t("shelf.known", "You know {share}%", { share: Math.round(reader.known * 100) }));
    }
    if (reader.chapters && reader.chapters.length && reader.readyChapters < reader.chapters.length) {
      said.push(
        t("shelf.chapters-translated", "{done} of {total} translated", {
          done: reader.readyChapters,
          total: reader.chapters.length,
        })
      );
    }
    // When it came, for a text the reader brought; when they last had it open, for one
    // from the library, which came to everybody at once.
    if (!reader.entry && reader.built) {
      said.push(t("shelf.added", "Added {when}", { when: ago(reader.built * 1000) }));
    } else if (reader.opened) {
      said.push(t("shelf.opened", "Opened {when}", { when: ago(reader.opened) }));
    }
    if (reader.playlists && reader.playlists.length) {
      said.push(t("shelf.in-playlists", "In {names}", { names: reader.playlists.join(", ") }));
    }
    said.forEach(function (fact) {
      var bit = document.createElement("span");
      bit.className = "fact";
      bit.textContent = fact;
      line.appendChild(bit);

    });
    // The status again, for a phone, where the pill beside the row folds away.
    var folded = document.createElement("span");
    folded.className = "fact fact-status is-" + state.kind;
    folded.textContent = state.said;
    line.appendChild(folded);
    return line;
  }

  function lengthOf(reader) {
    if (reader.seconds > 0) {
      var minutes = Math.max(1, Math.round(reader.seconds / 60));
      return reader.video
        ? t("shelf.length.video", "{n} min video", { n: minutes })
        : t("shelf.length.audio", "{n} min audio", { n: minutes });
    }
    return reader.minutes ? t("shelf.length.read", "{n} min read", { n: reader.minutes }) : "";
  }

  var RUNGS = {
    aleph: "Aleph",
    "aleph plus": "Aleph+",
    bet: "Bet",
    "bet plus": "Bet+",
    gimel: "Gimel",
    dalet: "Dalet",
    hey: "Hey",
    vav: "Vav",
  };

  // The rung the text needs, never the reader's (design.md §12, 2026-09-24).
  function levelOf(level) {
    if (!level || !level.name) return "";
    var english = RUNGS[level.name];
    if (!english) return level.cefr || level.name;
    var name = t("shelf.rung." + level.name.replace(/ /g, "-"), english);
    return level.cefr ? name + " · " + level.cefr : name;
  }

  /* New, a part count while reading, or Finished: read off what the reader's own pages
   * recorded (`targum:docs`), the same record Learn's progress reads. */
  function status(reader, docs) {
    var record = (reader.document && docs[reader.document]) || null;
    var total = (reader.chapters && reader.chapters.length) || reader.sections || 1;
    var done = 0;
    if (record && record.sections && typeof record.sections === "object") {
      Object.keys(record.sections).forEach(function (part) {
        if (record.sections[part]) done += 1;
      });
    }
    if ((record && record.done) || done >= total) {
      return { kind: "finished", said: t("shelf.status.finished", "Finished") };
    }
    if (done > 0) {
      return {
        kind: "reading",
        said: t("shelf.status.parts", "{done} of {total}", { done: done, total: total }),
      };
    }
    if (reader.opened) return { kind: "reading", said: t("shelf.status.started", "Started") };
    return { kind: "new", said: t("shelf.status.new", "New") };
  }

  /* ⋯: the rest of what a row can do, in a small menu, so the row keeps one press of its
   * own. Chapters for a book, and Delete. */
  var openMenu = null;

  function more(reader, item) {
    var press = document.createElement("button");
    press.type = "button";
    press.className = "row-more";
    press.setAttribute("aria-haspopup", "menu");
    press.setAttribute("aria-expanded", "false");
    press.setAttribute("aria-label", t("shelf.more", "More for {title}", { title: reader.title }));
    press.textContent = "⋯";
    press.onclick = function (event) {
      event.stopPropagation();
      if (openMenu && openMenu.press === press) {
        closeMenu();
        return;
      }
      closeMenu();
      var menu = document.createElement("div");
      menu.className = "row-menu";
      menu.setAttribute("role", "menu");
      if (reader.chapters && reader.chapters.length) {
        var chapters = opener(reader, item);
        chapters.setAttribute("role", "menuitem");
        chapters.addEventListener("click", closeMenu);
        menu.appendChild(chapters);
      }
      if (!reader.shared) {
        var bin = binButton(reader, item);
        bin.setAttribute("role", "menuitem");
        bin.addEventListener("click", function () {
          setTimeout(closeMenu, 0);
        });
        menu.appendChild(bin);
      }
      if (!menu.childNodes.length) return;
      document.body.appendChild(menu);
      place(menu, press);
      press.setAttribute("aria-expanded", "true");
      openMenu = { press: press, menu: menu };
      document.addEventListener("click", outsideMenu, true);
      document.addEventListener("keydown", escapeMenu, true);
      window.addEventListener("scroll", closeMenu, true);
      window.addEventListener("resize", closeMenu);
      var first = menu.querySelector("button");
      if (first) first.focus();
    };
    return press;
  }

  function place(menu, press) {
    var at = press.getBoundingClientRect();
    var gutter = 8;
    var width = menu.offsetWidth;
    var rtl = getComputedStyle(press).direction === "rtl";
    var left = rtl ? at.left : at.right - width;
    left = Math.max(gutter, Math.min(left, window.innerWidth - width - gutter));
    var top = at.bottom + 6;
    if (top + menu.offsetHeight > window.innerHeight - gutter) top = Math.max(gutter, at.top - 6 - menu.offsetHeight);
    menu.style.left = left + "px";
    menu.style.top = top + "px";
  }

  function closeMenu() {
    if (!openMenu) return;
    var press = openMenu.press;
    openMenu.menu.remove();
    press.setAttribute("aria-expanded", "false");
    openMenu = null;
    document.removeEventListener("click", outsideMenu, true);
    document.removeEventListener("keydown", escapeMenu, true);
    window.removeEventListener("scroll", closeMenu, true);
    window.removeEventListener("resize", closeMenu);
    if (document.body.contains(press)) press.focus();
  }

  function outsideMenu(event) {
    if (openMenu && !openMenu.menu.contains(event.target) && event.target !== openMenu.press) closeMenu();
  }

  function escapeMenu(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
    }
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
    // The words at a desk; on a phone the + alone, with the words still there for a
    // screen reader.
    var glyph = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    glyph.setAttribute("class", "add-glyph");
    glyph.setAttribute("viewBox", "0 0 16 16");
    glyph.setAttribute("aria-hidden", "true");
    glyph.setAttribute("focusable", "false");
    var plus = document.createElementNS("http://www.w3.org/2000/svg", "path");
    plus.setAttribute("d", "M8 3.5v9M3.5 8h9");
    glyph.appendChild(plus);
    link.appendChild(glyph);
    var words = document.createElement("span");
    words.className = "add-word";
    words.textContent = t("shelf.add-to-playlist", "Add to playlist");
    link.appendChild(words);
    // A menu in place where the script is here (2026-09-24); the page where it is not.
    if (window.TargumPlaylistMenu) {
      window.TargumPlaylistMenu.attach(link, { name: reader.name, title: reader.title || reader.name }, key);
    }
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
    building: building,
    trash: drawTrash,
    ago: ago,
    base: base,
  };
})();
