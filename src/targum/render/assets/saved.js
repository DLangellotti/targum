/* Saved on this device (design.md §12, "What is saved is a page of the account's",
 * 2026-10-09; boards OffSavedDesk and OffSavedPhone).
 *
 * Everything here is this browser's, read through `offline.js`: what is kept and how it
 * came to be, how much room it takes against what the browser allows, and what saves
 * itself. The server is asked nothing, so once the page has been opened with a connection
 * it opens without one: it keeps itself, the one page that does.
 *
 * Two groups, as the board draws them. **Saved automatically** — the recent texts and the
 * playlist the reader is in, each with Keep, which moves it to the other group. **Saved by
 * you** — what was saved with a press, each with Remove. A text a playlist holds is that
 * playlist's row, not one of its own.
 *
 * `persist()` is asked only from its button: a browser may answer it with a prompt, and a
 * prompt nobody pressed for is a prompt in the wrong place.
 */
(function () {
  "use strict";

  var offline = window.TargumOffline;
  var strings = window.TargumStrings || {};
  function t(key, english, fill) {
    return strings.t ? strings.t(key, english, fill) : english;
  }
  function tn(key, count, one, other, fill) {
    if (strings.tn) return strings.tn(key, count, one, other, fill);
    return (count === 1 ? one : other).replace("{n}", String(count));
  }

  function at(id) {
    return document.getElementById(id);
  }

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  if (new URLSearchParams(location.search).get("away")) at("saved-away").hidden = false;

  if (!offline || !offline.able) {
    at("saved-lede").hidden = true;
    at("saved-cannot").hidden = false;
    return;
  }

  // One word for what a text is, as home and the playlists say it.
  function kindWord(item) {
    if (item.kind === "playlist") return t("saved.kind.playlist", "Playlist");
    if (item.kind === "portion") return t("saved.kind.portion", "Torah portion");
    if (item.film) return t("home.kind.video", "Video");
    var kinds = {
      article: t("home.kind.article", "Article"),
      talk: t("home.kind.talk", "Video"),
      dialogue: t("home.kind.dialogue", "Conversation"),
      story: t("home.kind.story", "Story"),
      novel: t("home.kind.novel", "Book"),
      essay: t("home.kind.essay", "Essay"),
      tanakh: t("home.kind.tanakh", "Tanakh"),
      targum: t("home.kind.targum", "Aramaic translation"),
      mishnah: t("home.kind.mishnah", "Mishnah"),
      halakhah: t("home.kind.halakhah", "Halakhah"),
      prose: t("home.kind.prose", "Prose"),
      poetry: t("home.kind.poetry", "Poetry"),
      play: t("home.kind.play", "Play"),
      liturgy: t("home.kind.liturgy", "Prayer"),
      document: t("home.kind.document", "Document"),
    };
    return kinds[item.kind] || t("home.kind.text", "Text");
  }

  // What was kept of it, in the board's words: what it will do without a connection.
  function keptWord(item) {
    if (item.kind === "playlist") {
      return tn("saved.texts", (item.members || []).length, "{n} text", "{n} texts");
    }
    var media = item.withFilm
      ? t("saved.video-and-text", "video and text")
      : item.film
        ? t("saved.sound-and-text", "sound and text")
        : item.sound
          ? t("saved.text-and-recording", "text and recording")
          : t("saved.text", "text");
    var parts = Math.max(0, Number(item.pages || 0) - 1);
    if (parts > 1) {
      return tn("saved.parts", parts, "{n} part, {media}", "{n} parts, {media}", { media: media });
    }
    return media;
  }

  /* The text's picture, by the one tile path every desk page draws through
     (`TargumCovers.picture`; design.md §12, "The desk's controls are one layer"): its
     letter on the colour of its kind first, and its own picture only once that has
     loaded, so with no connection the tile is the letter and never a broken square. A
     playlist is its letter on the colour of a set. */
  function tile(item) {
    var covers = window.TargumCovers;
    var kind = item.kind === "playlist" ? "set" : item.film ? "video" : item.kind;
    var name = item.name || (/^\/reader\/([^/]+)\//.exec(String(item.id || "")) || [])[1] || "";
    if (!covers) return element("span", "thumb row-thumb is-letter");
    var box =
      item.kind === "playlist" || !name
        ? covers.tile("", { title: item.title, kind: kind, className: "thumb row-thumb" })
        : covers.picture({ entry: name, title: item.title, kind: kind }, { className: "thumb row-thumb" });
    box.setAttribute("aria-hidden", "true");
    return box;
  }

  // A small line drawing (§7): a pin for Keep, a cross for Remove.
  function glyph(d) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
    return svg;
  }
  var PIN = "M6 2.5h4M7 2.5v4L5 9h6L9 6.5v-4M8 9v4.5";
  var CROSS = "M4.5 4.5l7 7M11.5 4.5l-7 7";

  /* The language a title is written in, where it is in Hebrew letters: the index's own
     `language` for a text saved since it was kept, and otherwise the `-he` its folder's
     name ends in, else Hebrew. A title in Latin letters is the page's own language
     (targum-internal#720, P2 10: every Hebrew title stood inside `lang="en"`). */
  var HEBREW_LETTERS = /[\u0590-\u05FF\uFB1D-\uFB4F]/;
  function titleLanguage(item) {
    if (!HEBREW_LETTERS.test(String(item.title || ""))) return "";
    var said = String(item.language || "");
    if (/^(he|arc|yi)$/.test(said)) return said;
    var named = /-(he|arc|yi)$/.exec(String(item.name || ""));
    return named ? named[1] : "he";
  }

  /* A row, as the board's tables draw it: the picture, the title over what was kept, its
     kind, its size, how it came to be saved, Keep (for one saved on its own) and Remove, a cross. */
  function row(item, mine) {
    var line = element("li", "saved-row");
    line.setAttribute("data-id", item.id);
    line.appendChild(tile(item));
    var what = element("span", "saved-what");
    var name = item.open && item.kind !== "playlist" ? element("a", "saved-name") : element("span", "saved-name");
    if (name.tagName === "A") name.href = item.open;
    var bdi = element("bdi", "", item.title || item.id);
    bdi.setAttribute("dir", "auto");
    var spoken = titleLanguage(item);
    if (spoken) bdi.setAttribute("lang", spoken);
    name.appendChild(bdi);
    what.appendChild(name);
    what.appendChild(element("span", "saved-kept", keptWord(item)));
    // On a phone the kind joins what was kept, and the size goes under them.
    what.appendChild(element("span", "saved-kept-phone", kindWord(item) + " · " + keptWord(item)));
    what.appendChild(element("span", "saved-size-phone", offline.size(item.bytes)));
    line.appendChild(what);
    line.appendChild(element("span", "saved-kind", kindWord(item)));
    line.appendChild(element("span", "saved-size", offline.size(item.bytes)));
    line.appendChild(
      element("span", "saved-how tag" + (mine ? " is-mine" : ""), mine ? t("saved.by-you", "By you") : t("saved.on-its-own", "Automatically"))
    );
    if (!mine) {
      var keep = element("button", "btn ghost outline small saved-keep-it");
      keep.type = "button";
      keep.appendChild(glyph(PIN));
      keep.appendChild(element("span", "saved-keep-word", t("saved.keep", "Keep saved")));
      keep.setAttribute("aria-label", t("saved.keep-named", "Keep {title} saved", { title: item.title || "" }));
      keep.title = t("saved.keep", "Keep saved");
      keep.addEventListener("click", function () {
        keep.disabled = true;
        offline.keep(item.id).then(draw, draw);
      });
      line.appendChild(keep);
    } else {
      line.appendChild(element("span", "saved-keep-gap"));
    }
    var gone = element("button", "saved-x" + (mine ? " saved-remove" : " saved-let-go"));
    gone.type = "button";
    gone.appendChild(glyph(CROSS));
    gone.setAttribute("aria-label", t("saved.remove-named", "Remove {title}", { title: item.title || "" }));
    gone.title = t("saved.remove", "Remove");
    gone.addEventListener("click", function () {
      gone.disabled = true;
      var list = line.parentNode;
      var at = list ? Array.prototype.indexOf.call(list.children, line) : 0;
      settle();
      offline.take(item.id).then(function (hold) {
        holdFor({ hold: hold, item: item, mine: mine, at: at });
      }, draw);
    });
    line.appendChild(gone);
    return line;
  }

  function fill(list, items, mine) {
    list.textContent = "";
    items.forEach(function (item) {
      list.appendChild(row(item, mine));
    });
    if (holding && holding.item && holding.mine === mine) {
      list.insertBefore(heldRow(holding), list.children[Math.min(holding.at, list.children.length)] || null);
    }
  }

  /* --- Removed · Undo (design.md §12, "An offline copy follows its text when opened
     online, and Remove can be undone", 2026-11-14) ------------------------------------

     Remove and Remove all ask nothing first. The row (or, for all, the line under the
     choices) says "Removed · Undo" for a few seconds, and Undo puts back exactly what
     went: offline a copy can be the only one there is, so nothing has to be fetched to
     put it back (`offline.take`, `offline.takeAll`). When the line goes the files go.
     One at a time: a second removal finishes the first. */
  var UNDO_FOR = 8000;
  var holding = null;

  function holdFor(next) {
    holding = next;
    holding.timer = setTimeout(expire, UNDO_FOR);
    draw().then(function () {
      // Under the same finger, and the keyboard's next stop, as a binned text's Undo is.
      var undo = document.querySelector(".saved-undo");
      if (undo) undo.focus({ preventScroll: true });
    });
  }

  // The line goes, and what it held goes with it.
  function settle() {
    if (!holding) return Promise.resolve();
    var was = holding;
    holding = null;
    clearTimeout(was.timer);
    return was.hold.done();
  }

  function expire() {
    var undo = document.querySelector(".saved-undo");
    var focused = !!(undo && document.activeElement === undo);
    settle().then(draw).then(function () {
      // The keyboard had Undo; it is left at the page's heading, not on nothing.
      if (!focused) return;
      var heading = document.querySelector("main h1, h1");
      if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.focus({ preventScroll: true });
      }
    });
  }

  function undoHold() {
    if (!holding) return;
    var was = holding;
    holding = null;
    clearTimeout(was.timer);
    was.hold.undo().then(draw).then(function () {
      // Back where it was, with the keyboard on the press that took it.
      var back = was.item
        ? document.querySelector('.saved-row[data-id="' + String(was.item.id).replace(/"/g, '\\"') + '"] .saved-x')
        : at("saved-all");
      if (back) back.focus({ preventScroll: true });
    });
  }

  function undoPress(label) {
    var undo = element("button", "btn text small saved-undo", t("saved.undo", "Undo"));
    undo.type = "button";
    undo.setAttribute("aria-label", label);
    undo.addEventListener("click", undoHold);
    return undo;
  }

  // The row a removed text leaves behind while it can still be taken back.
  function heldRow(was) {
    var line = element("li", "saved-held");
    var said = element("span", "saved-held-note", t("saved.removed", "Removed"));
    said.setAttribute("role", "status");
    line.appendChild(said);
    line.appendChild(element("span", "saved-held-dot", "\u00b7"));
    line.lastChild.setAttribute("aria-hidden", "true");
    line.appendChild(
      undoPress(t("saved.undo-named", "Undo removing {title}", { title: was.item.title || "" }))
    );
    return line;
  }

  function drawHeldAll() {
    var line = at("saved-all-held");
    var all = !!(holding && !holding.item);
    at("saved-all").hidden = all;
    line.hidden = !all;
    line.textContent = "";
    if (!all) return;
    var said = element("span", "saved-held-note", t("saved.removed", "Removed"));
    said.setAttribute("role", "status");
    line.appendChild(said);
    line.appendChild(element("span", "saved-held-dot", "\u00b7"));
    line.lastChild.setAttribute("aria-hidden", "true");
    line.appendChild(undoPress(t("saved.undo-all", "Undo removing everything")));
  }

  function drawChoices() {
    var chosen = offline.choices();
    Array.prototype.forEach.call(document.querySelectorAll("[data-recent]"), function (button) {
      button.setAttribute("aria-checked", String(Number(button.getAttribute("data-recent")) === chosen.recent));
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-film]"), function (button) {
      button.setAttribute("aria-checked", String((button.getAttribute("data-film") === "1") === chosen.film));
    });
    at("saved-playlist").setAttribute("aria-checked", String(chosen.playlist));
    var says;
    if (!chosen.recent && !chosen.playlist) {
      says = t("saved.auto-none", "Nothing is saved automatically. Change that under Saving automatically.");
    } else if (!chosen.playlist) {
      says = tn(
        "saved.auto-texts",
        chosen.recent,
        "Your last text. A newer one takes its place.",
        "Your last {n} texts. Newer ones take their place."
      );
    } else if (!chosen.recent) {
      says = t("saved.auto-playlist", "The playlist you're in.");
    } else {
      says = tn(
        "saved.auto-both",
        chosen.recent,
        "Your last text and the playlist you're in. A newer one takes its place.",
        "Your last {n} texts and the playlist you're in. Newer ones take their place."
      );
    }
    at("saved-auto-says").textContent = says;
  }

  /* How full this device is, as the browser says it: { used, quota, nearly } or null where
     it does not say. Nearly full is 90% used (targum-internal#720, P1 3): a save that
     would not fit is refused by the browser with nothing said before it, so the page says
     it first, and where room is made. A browser with no estimate says nothing. */
  var NEARLY = 0.9;
  function room() {
    if (!navigator.storage || !navigator.storage.estimate) return Promise.resolve(null);
    var asked;
    try {
      asked = Promise.resolve(navigator.storage.estimate());
    } catch (e) {
      // A browser that throws where it should refuse still draws the page.
      return Promise.resolve(null);
    }
    return asked.then(
      function (said) {
        var used = Number((said && said.usage) || 0);
        var quota = Number((said && said.quota) || 0);
        if (!quota) return null;
        return { used: used, quota: quota, nearly: used / quota >= NEARLY };
      },
      function () {
        return null;
      }
    );
  }

  function drawRoom(items, space) {
    if (space) {
      /* The board's figure: what is used in the serif, and what the browser allows after
         it. The sentence is one string, so a language can put the two where it says them. */
      var said = t("saved.used", "{used} of about {quota} used", {
        used: "\u0000",
        quota: offline.size(space.quota),
      }).split("\u0000");
      var box = at("saved-used");
      box.textContent = "";
      if (said[0]) box.appendChild(element("span", "saved-used-rest", said[0]));
      box.appendChild(element("span", "saved-used-n", offline.size(space.used)));
      box.appendChild(element("span", "saved-used-rest", said.slice(1).join("")));
      var meter = at("saved-meter").parentNode;
      meter.style.setProperty("--done", String(Math.min(1, Math.max(0.01, space.used / space.quota))));
      // Clay from nearly full, as every meter that runs out is (`.meter.is-full`).
      meter.classList.toggle("is-full", space.nearly);
      meter.classList.toggle("is-building", !space.nearly);
      at("saved-nearly").hidden = !space.nearly;
      at("saved-room").hidden = false;
    }
    if (!navigator.storage || !navigator.storage.persisted) return;
    navigator.storage.persisted().then(function (kept) {
      // Asked only where there is something to keep, and only where it is not yet so.
      at("saved-persist").hidden = !!kept || !items.length;
    }, function () {});
  }

  /* The latest draw wins: a removal announces its change (`onChange`) a moment before
     it hands back the hold, so two draws are under way at once, and the earlier one
     landing last took the "Removed · Undo" row, and the keyboard on it, away again. */
  var drawing = 0;
  function draw() {
    var turn = ++drawing;
    return Promise.all([offline.list(), room()]).then(function (both) {
      if (turn !== drawing) return;
      var items = both[0];
      var space = both[1];
      var held = {};
      items.forEach(function (item) {
        (item.members || []).forEach(function (member) {
          held[member] = true;
        });
      });
      var shown = items.filter(function (item) {
        return item.kind !== "page" && !(held[item.id] && item.how !== "you");
      });
      /* By date, newest first; while the device is nearly full, largest first, so what
         makes the most room is at the top where the line points (#720, P1 3). */
      function largest(a, b) {
        return Number(b.bytes || 0) - Number(a.bytes || 0);
      }
      var auto = shown
        .filter(function (item) {
          return item.how !== "you";
        })
        .sort(
          space && space.nearly
            ? largest
            : function (a, b) {
                return Number(b.opened || b.at || 0) - Number(a.opened || a.at || 0);
              }
        );
      var mine = shown
        .filter(function (item) {
          return item.how === "you";
        })
        .sort(
          space && space.nearly
            ? largest
            : function (a, b) {
                return Number(b.at || 0) - Number(a.at || 0);
              }
        );
      fill(at("saved-auto-rows"), auto, false);
      fill(at("saved-mine-rows"), mine, true);
      var heldOne = holding && holding.item ? (holding.mine ? "mine" : "auto") : "";
      var heldAll = !!(holding && !holding.item);
      at("saved-auto").hidden = !auto.length && heldOne !== "auto";
      at("saved-mine").hidden = !mine.length && heldOne !== "mine";
      at("saved-none").hidden = !!shown.length || !!heldOne;
      // What these do without a connection is said over rows that do it, not over nothing
      // (#720, P2 6).
      at("saved-lede").hidden = !shown.length;
      at("saved-end").hidden = !shown.length && !heldAll;
      drawHeldAll();
      at("saved-choices").hidden = false;
      drawChoices();
      drawRoom(shown, space);
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll("[data-recent]"), function (button) {
    button.addEventListener("click", function () {
      offline.choose({ recent: Number(button.getAttribute("data-recent")) }).then(draw);
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll("[data-film]"), function (button) {
    button.addEventListener("click", function () {
      offline.choose({ film: button.getAttribute("data-film") === "1" }).then(draw);
    });
  });
  at("saved-playlist").addEventListener("click", function () {
    offline.choose({ playlist: !offline.choices().playlist }).then(draw);
  });
  at("saved-ask").addEventListener("click", function () {
    var ask = at("saved-ask");
    ask.disabled = true;
    navigator.storage.persist().then(
      function (granted) {
        at("saved-persist-says").textContent = granted
          ? t("saved.kept", "Your browser will keep them.")
          : t("saved.not-kept", "Your browser didn't agree. It still keeps them while it has room.");
        ask.hidden = true;
      },
      function () {
        ask.disabled = false;
      }
    );
  });
  at("saved-all").addEventListener("click", function () {
    settle().then(function () {
      return offline.takeAll();
    }).then(function (hold) {
      holdFor({ hold: hold, item: null, mine: false, at: 0 });
    }, draw);
  });

  // This page, kept, so the banner's way here works with no connection.
  offline.keepPage(location.href);
  offline.onChange(function () {
    draw();
  });
  draw();
})();
