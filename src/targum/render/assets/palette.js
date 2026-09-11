/* The command palette (2026-09-11): ⌘K, or the search in the bar.
 *
 * One field that finds a place, a text on your shelf or in the catalogue, a series, or
 * a conversation, and one press that goes there. The places are known on every page;
 * the shelf, the catalogue's rows and the conversations are asked for the first time
 * the palette opens and never before. A conversation opens in the drawer; a text opens
 * its reader; a place is a page. Arrow keys move, Enter goes, Escape closes.
 */
(function () {
  "use strict";

  var host = document.getElementById("palette");
  var field = document.getElementById("palette-find");
  var list = document.getElementById("palette-list");
  var opener = document.getElementById("palette-open");
  var scrim = document.getElementById("palette-scrim");
  if (!host || !field || !list) return;

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  var PLACES = [
    { kind: "place", title: "Learn", href: "/" },
    { kind: "place", title: "Library", href: "/library" },
    { kind: "place", title: "Your Progress", href: "/progress" },
    { kind: "place", title: "Your words and phrases", href: "/words" },
    { kind: "place", title: "Your subscriptions", href: "/you#subscriptions" },
    { kind: "place", title: "Your profile", href: "/you" },
    { kind: "place", title: "Add a text", href: "/add" },
    { kind: "talk", title: "Talk to targum" },
  ];

  var rows = null;
  var chosen = 0;

  function ask(path) {
    if (typeof fetch !== "function") return Promise.resolve({});
    return fetch(keyed(path), { headers: keyHeaders({}) })
      .then(function (response) {
        return response.ok ? response.json() : {};
      })
      .catch(function () {
        return {};
      });
  }

  // What can be found: gathered once per page, when first asked.
  function gather() {
    if (rows) return Promise.resolve(rows);
    var found = PLACES.slice();
    (window.TARGUM_CATALOGUE || []).forEach(function (entry) {
      found.push({
        kind: "catalogue",
        title: entry.title || entry.id,
        english: entry.english || "",
        href: "/library#" + encodeURIComponent(entry.id),
      });
    });
    return Promise.all([ask("/readers"), ask("/chat/list")]).then(function (got) {
      var readers = ((got[0] && got[0].readers) || []).concat((got[0] && got[0].shared) || []);
      readers.forEach(function (reader) {
        found.push({
          kind: "text",
          title: reader.title || reader.name,
          english: reader.english || "",
          href: "/reader/" + encodeURIComponent(reader.name) + "/reader/index.html",
        });
      });
      ((got[1] && got[1].chats) || []).forEach(function (chat) {
        found.push({ kind: "chat", title: chat.title || "Untitled", chat: chat.id });
      });
      rows = found;
      return rows;
    });
  }

  function matches(row, words) {
    var hay = (row.title + " " + (row.english || "")).toLowerCase();
    return words.every(function (word) {
      return hay.indexOf(word) >= 0;
    });
  }

  var KINDS = { place: "Page", catalogue: "Library", text: "Your shelf", chat: "Conversation", talk: "" };

  function draw(all) {
    var words = String(field.value || "")
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    var shown = all.filter(function (row) {
      return !words.length ? row.kind === "place" || row.kind === "talk" : matches(row, words);
    });
    shown = shown.slice(0, 12);
    list.textContent = "";
    if (chosen >= shown.length) chosen = 0;
    shown.forEach(function (row, n) {
      var li = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "palette-row" + (n === chosen ? " on" : "");
      button.setAttribute("aria-selected", n === chosen ? "true" : "false");
      var title = document.createElement("span");
      title.className = "palette-title";
      title.textContent = row.title;
      button.appendChild(title);
      if (row.english) {
        var english = document.createElement("span");
        english.className = "palette-english";
        english.textContent = row.english;
        button.appendChild(english);
      }
      if (KINDS[row.kind]) {
        var kind = document.createElement("span");
        kind.className = "palette-kind";
        kind.textContent = KINDS[row.kind];
        button.appendChild(kind);
      }
      button.onclick = function () {
        go(row);
      };
      li.appendChild(button);
      list.appendChild(li);
    });
    list.hidden = shown.length === 0;
    return shown;
  }

  var showing = [];

  function go(row) {
    if (!row) return;
    if (row.kind === "talk") {
      show(false);
      if (window.TargumTalk) window.TargumTalk.show(true);
      return;
    }
    if (row.kind === "chat") {
      show(false);
      if (window.TargumTalk && window.TargumTalk.open) window.TargumTalk.open(row.chat);
      return;
    }
    var parts = row.href.split("#");
    window.location.href = keyed(parts[0]) + (parts[1] ? "#" + parts[1] : "");
  }

  function show(on) {
    host.hidden = !on;
    if (scrim) scrim.hidden = !on;
    if (opener) opener.setAttribute("aria-expanded", on ? "true" : "false");
    if (!on) return;
    field.value = "";
    chosen = 0;
    gather().then(function (all) {
      showing = draw(all);
    });
    field.focus();
  }

  field.addEventListener("input", function () {
    chosen = 0;
    gather().then(function (all) {
      showing = draw(all);
    });
  });
  field.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      chosen = Math.min(chosen + 1, Math.max(0, showing.length - 1));
      showing = draw(rows || PLACES);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      chosen = Math.max(0, chosen - 1);
      showing = draw(rows || PLACES);
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(showing[chosen]);
    }
  });
  document.addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && String(event.key).toLowerCase() === "k") {
      event.preventDefault();
      show(host.hidden);
    } else if (event.key === "Escape" && !host.hidden) {
      show(false);
    }
  });
  if (opener) {
    opener.addEventListener("click", function () {
      show(host.hidden);
    });
  }
  if (scrim) {
    scrim.addEventListener("click", function () {
      show(false);
    });
  }

  window.TargumPalette = { show: show, gather: gather };
})();
