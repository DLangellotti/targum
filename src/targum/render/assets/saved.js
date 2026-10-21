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
      dialogue: t("home.kind.dialogue", "Dialogue"),
      story: t("home.kind.story", "Story"),
      novel: t("home.kind.novel", "Book"),
      essay: t("home.kind.essay", "Essay"),
      prose: t("home.kind.prose", "Tanakh"),
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

  /* A row, as the board's tables draw it: the picture, the title over what was kept, its
     kind, its size, how it came to be saved, Keep (for one saved on its own) and Remove, a cross. */
  function row(item, mine) {
    var line = element("li", "saved-row");
    line.appendChild(tile(item));
    var what = element("span", "saved-what");
    var name = item.open && item.kind !== "playlist" ? element("a", "saved-name") : element("span", "saved-name");
    if (name.tagName === "A") name.href = item.open;
    var bdi = element("bdi", "", item.title || item.id);
    bdi.setAttribute("dir", "auto");
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
      offline.remove(item.id).then(draw, draw);
    });
    line.appendChild(gone);
    return line;
  }

  function fill(list, items, mine) {
    list.textContent = "";
    items.forEach(function (item) {
      list.appendChild(row(item, mine));
    });
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

  function drawRoom(items) {
    if (!navigator.storage || !navigator.storage.estimate) return;
    navigator.storage.estimate().then(function (room) {
      var used = Number(room.usage || 0);
      var quota = Number(room.quota || 0);
      if (!quota) return;
      /* The board's figure: what is used in the serif, and what the browser allows after
         it. The sentence is one string, so a language can put the two where it says them. */
      var said = t("saved.used", "{used} used of about {quota}", {
        used: "\u0000",
        quota: offline.size(quota),
      }).split("\u0000");
      var box = at("saved-used");
      box.textContent = "";
      if (said[0]) box.appendChild(element("span", "saved-used-rest", said[0]));
      box.appendChild(element("span", "saved-used-n", offline.size(used)));
      box.appendChild(element("span", "saved-used-rest", said.slice(1).join("")));
      at("saved-meter").parentNode.style.setProperty("--done", String(Math.min(1, Math.max(0.01, used / quota))));
      at("saved-room").hidden = false;
    }, function () {});
    if (!navigator.storage.persisted) return;
    navigator.storage.persisted().then(function (kept) {
      // Asked only where there is something to keep, and only where it is not yet so.
      at("saved-persist").hidden = !!kept || !items.length;
    }, function () {});
  }

  function draw() {
    return offline.list().then(function (items) {
      var held = {};
      items.forEach(function (item) {
        (item.members || []).forEach(function (member) {
          held[member] = true;
        });
      });
      var shown = items.filter(function (item) {
        return item.kind !== "page" && !(held[item.id] && item.how !== "you");
      });
      var auto = shown
        .filter(function (item) {
          return item.how !== "you";
        })
        .sort(function (a, b) {
          return Number(b.opened || b.at || 0) - Number(a.opened || a.at || 0);
        });
      var mine = shown
        .filter(function (item) {
          return item.how === "you";
        })
        .sort(function (a, b) {
          return Number(b.at || 0) - Number(a.at || 0);
        });
      fill(at("saved-auto-rows"), auto, false);
      fill(at("saved-mine-rows"), mine, true);
      at("saved-auto").hidden = !auto.length;
      at("saved-mine").hidden = !mine.length;
      at("saved-none").hidden = !!shown.length;
      at("saved-end").hidden = !shown.length;
      at("saved-choices").hidden = false;
      drawChoices();
      drawRoom(shown);
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
    offline.removeAll().then(function () {
      offline.keepPage(location.href);
      draw();
    });
  });

  // This page, kept, so the banner's way here works with no connection.
  offline.keepPage(location.href);
  offline.onChange(function () {
    draw();
  });
  draw();
})();
