/* One search, everywhere (design.md §12, "One search, everywhere", 2026-10-09).
 *
 * The overlay the bar's search opens, ⌘K and "/" open, and the Library's own box opens
 * already held to the Library. It was the command palette (2026-09-11), a flat list of
 * pages, texts and chats by title; it is the boards' search now (FindDesk, FindPhone):
 * a field, the language it searches in, a row of filters with counts, and what it found
 * grouped by where — Your targums, Playlists, Subscriptions, the Library and Words —
 * each row with its picture, what it is, its band and how much of it is known.
 *
 * The server does the finding (`/search.json`): it folds spelling and reads a
 * transliteration, so the page sends the line as typed. A word's sentences are a page of
 * their own here (`/search/word.json`). With nothing typed, the searches made on this
 * device and the texts opened last. Arrow keys move, Enter opens, Escape closes.
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

  var host = document.getElementById("palette");
  var field = document.getElementById("palette-find");
  var body = document.getElementById("palette-body");
  var filters = document.getElementById("palette-filters");
  var scope = document.getElementById("palette-lang");
  var scopeMenu = document.getElementById("palette-langs");
  var clearer = document.getElementById("palette-clear");
  var back = document.getElementById("palette-back");
  var opener = document.getElementById("palette-open");
  var scrim = document.getElementById("palette-scrim");
  if (!host || !field || !body) return;

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    var parts = path.split("#");
    var head = parts[0] + (parts[0].indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
    return head + (parts[1] !== undefined ? "#" + parts[1] : "");
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function glyph(path) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", "palette-glyph");
    var line = document.createElementNS("http://www.w3.org/2000/svg", "path");
    line.setAttribute("d", path);
    svg.appendChild(line);
    return svg;
  }

  // §7: sixteen pixels, a stroke at 1.4, round caps. A group's head says where.
  var GLYPHS = {
    yours: "M2.5 7.5 8 3l5.5 4.5M4 6.5v6.5h8V6.5",
    playlists: "M2.5 4h8M2.5 8h8M2.5 12h5M12 9.5v4l2-1",
    subscriptions: "M8 2.2a3.6 3.6 0 0 0-3.6 3.6v2.4L3.2 10.6h9.6l-1.2-2.4V5.8A3.6 3.6 0 0 0 8 2.2zM6.6 12.6a1.4 1.4 0 0 0 2.8 0",
    library: "M2.5 4h1M5.5 4h8M2.5 8h1M5.5 8h8M2.5 12h1M5.5 12h8",
    words: "M2.5 12.5 5.5 3.5l3 9M3.6 9.5h3.8M10 12.5V7.8M10 9.6c0-1.2.9-1.9 2-1.9s1.6.7 1.6 1.8v3",
    recent: "M8 2.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11zM8 5v3.2l2 1.3",
    globe: "M8 2.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11zM2.5 8h11M8 2.5c1.6 1.6 2.4 3.4 2.4 5.5S9.6 11.9 8 13.5M8 2.5C6.4 4.1 5.6 5.9 5.6 8s.8 3.9 2.4 5.5",
    upload: "M8 10.5V3M5 6l3-3 3 3M3 10.5v2.5h10v-2.5",
    chevron: "M6 3.5 10.5 8 6 12.5",
  };

  function groups() {
    return [
      ["yours", t("palette.group.yours", "Your targums")],
      ["playlists", t("palette.group.playlists", "Playlists")],
      ["subscriptions", t("palette.group.subscriptions", "Subscriptions")],
      ["library", t("palette.group.library", "Library")],
      ["words", t("palette.group.words", "Words")],
    ];
  }

  /* --- what is kept on this device ---------------------------------------- */

  var RECENT = "targum:searches";
  var MOST_RECENT = 8;

  function recents() {
    try {
      var kept = JSON.parse(localStorage.getItem(RECENT) || "[]");
      return Array.isArray(kept) ? kept.filter(Boolean).slice(0, MOST_RECENT) : [];
    } catch (e) {
      return [];
    }
  }
  function keepRecents(list) {
    try {
      localStorage.setItem(RECENT, JSON.stringify(list.slice(0, MOST_RECENT)));
    } catch (e) {}
  }
  function remember(line) {
    var said = String(line || "").trim();
    if (!said) return;
    keepRecents(
      [said].concat(
        recents().filter(function (was) {
          return was.toLowerCase() !== said.toLowerCase();
        })
      )
    );
  }

  /* --- the state ----------------------------------------------------------- */

  var state = {
    filter: "all",
    level: "",
    lang: "",
    word: null,
    was: "all",
    answer: null,
    opened: null,
    learning: [],
  };
  var asked = 0;
  var waiting = null;

  function language() {
    if (state.lang) return state.lang;
    var lang = window.TargumLang;
    if (lang && lang.current && lang.learning) return lang.current(lang.learning());
    return "he";
  }

  function ask(path) {
    if (typeof fetch !== "function") return Promise.resolve(null);
    var head = {};
    if (key) head["X-Targum-Key"] = key;
    return fetch(keyed(path), { headers: head })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .catch(function () {
        return null;
      });
  }

  function search() {
    var line = String(field.value || "").trim();
    var mine = ++asked;
    if (clearer) clearer.hidden = !line;
    if (waiting) clearTimeout(waiting);
    if (!line) {
      state.answer = null;
      draw();
      if (state.opened === null) {
        ask("/search.json?lang=" + encodeURIComponent(language())).then(function (got) {
          state.opened = (got && got.opened) || [];
          if (got && got.learning) state.learning = got.learning;
          if (mine === asked) draw();
        });
      }
      return;
    }
    waiting = setTimeout(function () {
      ask("/search.json?q=" + encodeURIComponent(line) + "&lang=" + encodeURIComponent(language())).then(
        function (got) {
          if (mine !== asked) return;
          state.answer = got || { q: line, groups: [], languages: [], failed: true };
          if (got && got.learning) state.learning = got.learning;
          draw();
        }
      );
    }, 160);
  }

  /* --- drawing ------------------------------------------------------------- */

  function langName(code) {
    if (code === "all") return t("palette.all-languages", "All languages");
    var names = window.TARGUM_LANGUAGES || {};
    var known = (state.learning || []).filter(function (one) {
      return one.code === code;
    })[0];
    if (state.answer && state.answer.language === code && state.answer.name) return state.answer.name;
    return (known && known.name) || names[code] || String(code || "").toUpperCase();
  }

  function drawScope() {
    if (!scope) return;
    scope.textContent = "";
    scope.appendChild(glyph(GLYPHS.globe));
    var code = language();
    scope.appendChild(
      el("span", "", code === "all" ? langName("all") : t("palette.in-language", "In {language}", { language: langName(code) }))
    );
    scope.appendChild(el("span", "palette-caret", "▾"));
  }

  function drawScopeMenu() {
    if (!scopeMenu) return;
    scopeMenu.textContent = "";
    var counts = {};
    ((state.answer && state.answer.languages) || []).forEach(function (one) {
      counts[one.code] = one.count;
    });
    var codes = (state.learning || []).map(function (one) {
      return one.code;
    });
    if (codes.indexOf(language()) < 0 && language() !== "all") codes.unshift(language());
    Object.keys(counts).forEach(function (code) {
      if (codes.indexOf(code) < 0) codes.push(code);
    });
    codes.concat(["all"]).forEach(function (code) {
      var item = el("button", "palette-lang-row");
      item.type = "button";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("aria-checked", code === language() ? "true" : "false");
      item.appendChild(el("span", "", langName(code)));
      var badge = code !== "all" && window.TargumLang && window.TargumLang.badge ? window.TargumLang.badge(code) : null;
      if (badge) item.appendChild(badge);
      if (state.answer && code !== "all") item.appendChild(el("span", "palette-lang-count", String(counts[code] || 0)));
      item.onclick = function () {
        state.lang = code;
        scopeMenu.hidden = true;
        scope.setAttribute("aria-expanded", "false");
        drawScope();
        search();
        field.focus();
      };
      scopeMenu.appendChild(item);
    });
  }

  function countOf(id) {
    var group = ((state.answer && state.answer.groups) || []).filter(function (one) {
      return one.id === id;
    })[0];
    return group ? group.count : 0;
  }

  function drawFilters() {
    if (!filters) return;
    filters.textContent = "";
    var answered = state.answer && !state.answer.failed;
    var total = 0;
    groups().forEach(function (pair) {
      total += countOf(pair[0]);
    });
    [["all", t("palette.group.all", "All")]].concat(groups()).forEach(function (pair) {
      var id = pair[0];
      var count = id === "all" ? total : countOf(id);
      var empty = answered && count === 0;
      var tab = el("button", empty ? "tab is-empty" : "tab");
      tab.type = "button";
      tab.setAttribute("role", "tab");
      tab.setAttribute("data-filter", id);
      tab.setAttribute("aria-selected", state.filter === id ? "true" : "false");
      tab.appendChild(el("span", "", pair[1]));
      if (answered) tab.appendChild(el("span", "tab-count", String(count)));
      if (empty && id !== "all") tab.disabled = true;
      tab.onclick = function () {
        state.filter = id;
        state.word = null;
        draw();
      };
      filters.appendChild(tab);
    });
    // The level, over what was found: the Library's three bands (design.md §12, "The
    // Library is shelved by how much you'd follow").
    if (answered && total) {
      var pick = el("label", "palette-level");
      pick.appendChild(el("span", "", t("palette.level", "Level:")));
      var select = el("select", "palette-level-pick");
      [
        ["", t("palette.level.any", "Any")],
        ["now", t("palette.band.now", "Read it now")],
        ["stretch", t("palette.band.stretch", "A stretch")],
        ["hard", t("palette.band.hard", "Hard for now")],
      ].forEach(function (option) {
        var one = el("option", "", option[1]);
        one.value = option[0];
        if (option[0] === state.level) one.selected = true;
        select.appendChild(one);
      });
      select.onchange = function () {
        state.level = select.value;
        draw();
      };
      pick.appendChild(select);
      filters.appendChild(pick);
    }
  }

  function picture(row) {
    var covers = window.TargumCovers;
    var name = row.entry || row.name || "";
    if (covers && covers.picture && name) {
      return covers.picture(
        { entry: row.entry, name: row.name, title: row.title, language: row.language, kind: row.type, register: row.register },
        { className: "thumb row-thumb", keyed: keyed }
      );
    }
    var tile = el("span", "thumb row-thumb is-letter tone-" + (row.kind === "subscription" || row.kind === "playlist" ? "set" : "book"));
    var letter = el("span", "glyph", String(row.title || "?").replace(/^[^\wא-תЀ-ӿ]+/, "").charAt(0));
    letter.setAttribute("aria-hidden", "true");
    tile.appendChild(letter);
    return tile;
  }

  function when(clock) {
    if (!clock) return "";
    var days = Math.floor((Date.now() - clock) / 86400000);
    if (days < 1) return t("palette.opened.today", "opened today");
    if (days < 2) return t("palette.opened.yesterday", "opened yesterday");
    if (days < 7) return tn("palette.opened.days", days, "opened {n} day ago", "opened {n} days ago");
    if (days < 14) return t("palette.opened.last-week", "opened last week");
    return tn("palette.opened.weeks", Math.floor(days / 7), "opened {n} week ago", "opened {n} weeks ago");
  }

  function known(row) {
    var end = el("span", "palette-end");
    if (row.band) {
      end.appendChild(el("span", "tag palette-band is-" + row.band, row.bandWord || ""));
    }
    if (typeof row.known === "number") {
      var share = el("span", "palette-known");
      share.appendChild(
        el("span", "palette-known-said", t("palette.known", "{percent}% known", { percent: Math.round(row.known * 100) }))
      );
      var meter = el("span", "meter");
      var fill = el("span");
      fill.style.setProperty("--done", String(row.known));
      meter.appendChild(fill);
      share.appendChild(meter);
      end.appendChild(share);
    }
    return end;
  }

  var hits = [];

  function hit(row, href, onPick) {
    var item = el("li", "row palette-row");
    var link = el("a", "palette-hit");
    link.href = href ? keyed(href) : "#";
    link.addEventListener("click", function (event) {
      remember(field.value);
      if (onPick) {
        event.preventDefault();
        onPick();
        return;
      }
      show(false);
    });
    item.appendChild(link);
    hits.push(link);
    return link;
  }

  function titled(main, row) {
    var title = el("bdi", "palette-title", row.title || "");
    if (row.language) title.setAttribute("lang", row.language);
    title.setAttribute("dir", "auto");
    main.appendChild(title);
    if (row.english && row.english !== row.title) {
      var english = el("span", "palette-english", row.english);
      english.setAttribute("dir", "auto");
      main.appendChild(english);
    }
  }

  function words(row) {
    return tn("palette.words", row.words, "{n} word", "{n} words", { n: Number(row.words).toLocaleString() });
  }

  // A row's facts, each isolated in its own direction: a Hebrew author between two
  // English facts reordered the line around itself when the line was one run.
  function factsLine(facts) {
    var line = el("span", "palette-facts");
    facts.forEach(function (fact, n) {
      if (n) line.appendChild(document.createTextNode(" · "));
      var one = el("bdi", "", fact);
      one.setAttribute("dir", "auto");
      line.appendChild(one);
    });
    return line;
  }

  function textRow(row, compact) {
    var link = hit(row, row.href);
    link.appendChild(picture(row));
    var main = el("span", "row-main");
    titled(main, row);
    var facts = [];
    if (row.what) facts.push(row.what);
    if (!compact && row.author) facts.push(row.author);
    if (row.words) facts.push(words(row));
    if (!compact && row.opened) facts.push(when(row.opened));
    var meta = el("span", "palette-meta");
    if (!compact && row.tag) {
      meta.appendChild(el("span", "tag", row.tag === "uploads" ? t("palette.tag.uploads", "Uploads") : t("palette.tag.recent", "Recent")));
    }
    meta.appendChild(factsLine(facts));
    main.appendChild(meta);
    link.appendChild(main);
    if (!compact) link.appendChild(known(row));
    return link.parentNode;
  }

  function playlistRow(row) {
    var link = hit(row, row.href);
    link.appendChild(picture({ name: row.name, title: row.title, kind: "playlist" }));
    var main = el("span", "row-main");
    titled(main, row);
    var facts = [t("palette.kind.playlist", "Playlist"), tn("palette.texts", row.count, "{n} text", "{n} texts")];
    if (row.by && row.by !== "targum") facts.push(t("palette.made-by-you", "made by you"));
    main.appendChild(factsLine(facts));
    link.appendChild(main);
    return link.parentNode;
  }

  function subscriptionRow(row) {
    var link = hit(row, row.href);
    link.appendChild(picture({ title: row.title, kind: "subscription", language: row.language }));
    var main = el("span", "row-main");
    titled(main, row);
    main.appendChild(el("span", "palette-facts", row.what || t("palette.kind.series", "Series")));
    link.appendChild(main);
    var end = el("span", "palette-end");
    if (row.state === "on") end.appendChild(el("span", "tag palette-band is-now", t("palette.subscribed", "Subscribed")));
    link.appendChild(end);
    return link.parentNode;
  }

  function stageWord(stage) {
    return (
      {
        1: t("palette.stage.1", "Just met"),
        2: t("palette.stage.2", "Getting there"),
        3: t("palette.stage.3", "Nearly there"),
        9: t("palette.stage.known", "Known"),
        0: t("palette.stage.ignore", "A name or a number"),
      }[stage] || ""
    );
  }

  function wordRow(row) {
    var open = function () {
      state.word = row;
      state.was = state.filter;
      state.filter = "words";
      draw();
    };
    var link = hit(row, "", open);
    var tile = el("span", "row-thumb palette-word-tile");
    tile.appendChild(glyph(GLYPHS.words));
    link.appendChild(tile);
    var main = el("span", "row-main");
    var top = el("span", "palette-word-head");
    var lemma = el("bdi", "palette-lemma", row.lemma);
    lemma.setAttribute("lang", row.language || "");
    lemma.setAttribute("dir", "auto");
    top.appendChild(lemma);
    if (row.meaning) top.appendChild(el("span", "palette-english", row.meaning));
    if (stageWord(row.stage)) top.appendChild(el("span", "tag", stageWord(row.stage)));
    main.appendChild(top);
    if (row.sentences) {
      main.appendChild(
        el(
          "span",
          "palette-facts",
          t("palette.word.in", "In {sentences} across {texts} you can open", {
            sentences: tn("palette.sentences", row.sentences, "{n} sentence", "{n} sentences"),
            texts: tn("palette.texts", row.texts, "{n} text", "{n} texts"),
          })
        )
      );
    }
    link.appendChild(main);
    var more = el("span", "btn text small palette-more", t("palette.word.texts", "Texts with this word"));
    more.appendChild(glyph(GLYPHS.chevron));
    link.appendChild(more);
    return link.parentNode;
  }

  function atLevel(row) {
    return !state.level || row.band === state.level || row.kind !== "text";
  }

  function head(id, name, count, all) {
    var top = el("div", "palette-group-head");
    var title = el("h3", "palette-group-name");
    title.appendChild(glyph(GLYPHS[id] || GLYPHS.library));
    title.appendChild(el("span", "", name));
    title.appendChild(el("span", "palette-group-count", String(count)));
    top.appendChild(title);
    if (all) {
      var more = el("button", "btn text small palette-see-all", t("palette.see-all", "See all {n}", { n: count }));
      more.type = "button";
      more.appendChild(glyph(GLYPHS.chevron));
      more.onclick = function () {
        state.filter = id;
        draw();
      };
      top.appendChild(more);
    }
    return top;
  }

  var SHOWN_IN_ALL = { yours: 3, playlists: 2, subscriptions: 2, library: 4, words: 2 };

  function drawResults(answer) {
    var names = {};
    groups().forEach(function (pair) {
      names[pair[0]] = pair[1];
    });
    var drew = 0;
    (answer.groups || []).forEach(function (group) {
      if (state.filter !== "all" && state.filter !== group.id) return;
      var rows = (group.rows || []).filter(atLevel);
      if (!rows.length) return;
      var cut = state.filter === "all" ? SHOWN_IN_ALL[group.id] || 3 : rows.length;
      var section = el("section", "palette-group");
      section.setAttribute("data-group", group.id);
      var count = state.level ? rows.length : group.count;
      section.appendChild(head(group.id, names[group.id] || group.id, count, state.filter === "all" && count > cut));
      var list = el("ul", "rows palette-rows");
      rows.slice(0, cut).forEach(function (row) {
        if (row.kind === "playlist") list.appendChild(playlistRow(row));
        else if (row.kind === "subscription") list.appendChild(subscriptionRow(row));
        else if (row.kind === "word") list.appendChild(wordRow(row));
        else list.appendChild(textRow(row));
      });
      section.appendChild(list);
      body.appendChild(section);
      drew += rows.length;
    });
    return drew;
  }

  function elsewhere(answer) {
    var other = answer.elsewhere;
    if (!other || !other.count) return null;
    var box = el("section", "card palette-elsewhere");
    var top = el("div", "palette-elsewhere-head");
    var said = el("p", "palette-elsewhere-said", t("palette.more-in", "{n} more in {language}", { n: other.count, language: other.name }));
    var badge = window.TargumLang && window.TargumLang.badge ? window.TargumLang.badge(other.language) : null;
    if (badge) said.appendChild(badge);
    top.appendChild(said);
    var all = el("button", "btn filled small palette-all-languages");
    all.type = "button";
    all.appendChild(glyph(GLYPHS.globe));
    all.appendChild(el("span", "", t("palette.search-all", "Search all languages")));
    all.onclick = function () {
      state.lang = "all";
      drawScope();
      search();
    };
    top.appendChild(all);
    box.appendChild(top);
    var list = el("ul", "rows palette-rows is-compact");
    (other.rows || []).forEach(function (row) {
      list.appendChild(textRow(row, true));
    });
    box.appendChild(list);
    return box;
  }

  function nothing(answer) {
    var box = el("section", "palette-nothing");
    var heading = el("p", "palette-nothing-head");
    heading.appendChild(document.createTextNode(t("palette.nothing", "Nothing on targum matches") + " "));
    var line = el("bdi", "", answer.q);
    line.setAttribute("dir", "auto");
    heading.appendChild(line);
    heading.appendChild(document.createTextNode("."));
    box.appendChild(heading);
    box.appendChild(
      el("p", "palette-nothing-note", t("palette.nothing.anywhere", "Not in your targums, playlists, subscriptions or the Library, in any language."))
    );
    var card = el("form", "card palette-bring");
    card.setAttribute("action", keyed("/add"));
    var label = el("label", "field");
    label.appendChild(el("span", "", t("palette.paste-a-link", "Paste a link")));
    var row = el("span", "palette-bring-row");
    var link = el("input", "well");
    link.type = "url";
    link.name = "source";
    link.placeholder = t("palette.paste-placeholder", "A page, a video or a podcast");
    row.appendChild(link);
    var go = el("button", "btn filled", t("palette.continue", "Continue"));
    go.type = "submit";
    row.appendChild(go);
    label.appendChild(row);
    card.appendChild(label);
    card.addEventListener("submit", function (event) {
      event.preventDefault();
      var wanted = String(link.value || "").trim();
      window.location.href = keyed("/add" + (wanted ? "?source=" + encodeURIComponent(wanted) : ""));
    });
    card.appendChild(el("p", "palette-or", t("palette.or", "or")));
    var upload = el("a", "btn outline palette-upload");
    upload.href = keyed("/add");
    upload.appendChild(glyph(GLYPHS.upload));
    upload.appendChild(el("span", "", t("palette.upload-file", "Upload it from a file")));
    card.appendChild(upload);
    box.appendChild(card);
    box.appendChild(
      el("p", "palette-nothing-foot", t("palette.uploads-yours", "Uploads are yours alone. The next step shows the credits before anything is made."))
    );
    return box;
  }

  function foot() {
    var line = el("p", "palette-foot");
    if (language() === "all") {
      line.textContent = t("palette.searched-all", "Searched in every language.");
      return line;
    }
    line.appendChild(document.createTextNode(t("palette.searched-in", "Searched in {language}.", { language: langName(language()) }) + " "));
    var all = el("button", "palette-foot-all", t("palette.search-all", "Search all languages"));
    all.type = "button";
    all.onclick = function () {
      state.lang = "all";
      drawScope();
      search();
    };
    line.appendChild(all);
    return line;
  }

  function drawEmpty() {
    var both = el("div", "palette-empty");
    var left = el("section", "palette-recent");
    var kept = recents();
    var top = el("div", "palette-group-head");
    top.appendChild(el("h3", "palette-group-name", t("palette.recent", "Recent searches")));
    if (kept.length) {
      var clear = el("button", "btn text small", t("palette.clear", "Clear"));
      clear.type = "button";
      clear.onclick = function () {
        keepRecents([]);
        draw();
      };
      top.appendChild(clear);
    }
    left.appendChild(top);
    if (!kept.length) left.appendChild(el("p", "palette-quiet", t("palette.recent.none", "What you search for is kept here, on this device.")));
    var list = el("ul", "rows palette-rows");
    kept.forEach(function (line) {
      var item = el("li", "row palette-recent-row");
      var again = el("button", "palette-hit palette-again");
      again.type = "button";
      again.appendChild(glyph(GLYPHS.recent));
      var said = el("bdi", "", line);
      said.setAttribute("dir", "auto");
      again.appendChild(said);
      again.onclick = function () {
        field.value = line;
        search();
        field.focus();
      };
      hits.push(again);
      item.appendChild(again);
      var drop = el("button", "palette-drop", "×");
      drop.type = "button";
      drop.setAttribute("aria-label", t("palette.forget", "Forget this search"));
      drop.onclick = function () {
        keepRecents(
          recents().filter(function (was) {
            return was !== line;
          })
        );
        draw();
      };
      item.appendChild(drop);
      list.appendChild(item);
    });
    left.appendChild(list);
    both.appendChild(left);
    var lately = state.opened || [];
    if (lately.length) {
      var right = el("section", "palette-lately");
      var named = el("div", "palette-group-head");
      named.appendChild(el("h3", "palette-group-name", t("palette.opened-lately", "Opened lately")));
      right.appendChild(named);
      var rows = el("ul", "rows palette-rows is-compact");
      lately.forEach(function (row) {
        rows.appendChild(textRow(row, true));
      });
      right.appendChild(rows);
      both.appendChild(right);
    }
    body.appendChild(both);
  }

  function marked(sentence, forms) {
    var line = el("span", "palette-sentence");
    line.setAttribute("dir", "auto");
    var found = (forms || []).filter(Boolean).sort(function (a, b) {
      return b.length - a.length;
    });
    if (!found.length) {
      line.textContent = sentence;
      return line;
    }
    var escaped = found.map(function (word) {
      return word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    });
    String(sentence)
      .split(new RegExp("(" + escaped.join("|") + ")"))
      .forEach(function (part) {
        if (!part) return;
        if (found.indexOf(part) >= 0) line.appendChild(el("mark", "", part));
        else line.appendChild(document.createTextNode(part));
      });
    return line;
  }

  function sentenceRow(one) {
    var item = el("li", "row palette-row palette-sentence-row");
    item.appendChild(picture({ entry: one.entry, name: one.name, title: one.title, language: one.language, type: one.type }));
    var main = el("span", "row-main");
    var said = marked(one.sentence, one.forms);
    said.setAttribute("lang", one.language || "");
    main.appendChild(said);
    var where = el("span", "palette-facts");
    var title = el("bdi", "", one.title);
    title.setAttribute("dir", "auto");
    where.appendChild(title);
    var rest = [one.what, one.author].filter(Boolean).join(" · ");
    if (rest) where.appendChild(document.createTextNode(" · " + rest));
    main.appendChild(where);
    item.appendChild(main);
    var end = el("span", "palette-at");
    if (typeof one.known === "number") end.appendChild(known({ known: one.known }));
    var open = el("a", "btn text small", t("palette.open-at", "Open at this sentence"));
    open.href = keyed(one.href);
    open.addEventListener("click", function () {
      remember(field.value);
    });
    hits.push(open);
    end.appendChild(open);
    item.appendChild(end);
    return item;
  }

  function drawWord() {
    var word = state.word;
    var page = el("div", "palette-word");
    var card = el("section", "card palette-word-card");
    var top = el("div", "palette-word-top");
    var name = el("div", "palette-word-name");
    var lemma = el("bdi", "palette-word-lemma", word.lemma);
    lemma.setAttribute("lang", word.language || "");
    lemma.setAttribute("dir", "auto");
    name.appendChild(lemma);
    if (word.meaning) name.appendChild(el("span", "palette-english", word.meaning));
    if (stageWord(word.stage)) name.appendChild(el("span", "tag", stageWord(word.stage)));
    top.appendChild(name);
    var tally = el("p", "palette-word-tally");
    top.appendChild(tally);
    card.appendChild(top);
    var forms = el("p", "palette-forms");
    card.appendChild(forms);
    page.appendChild(card);
    var parts = el("div", "palette-word-parts");
    parts.appendChild(el("p", "palette-quiet", t("palette.word.reading", "Looking through your texts…")));
    page.appendChild(parts);
    body.appendChild(page);
    var mine = asked;
    ask("/search/word.json?lemma=" + encodeURIComponent(word.lemma) + "&lang=" + encodeURIComponent(word.language || "")).then(function (got) {
      if (mine !== asked || state.word !== word) return;
      parts.textContent = "";
      if (!got) {
        parts.appendChild(el("p", "palette-quiet", t("palette.word.failed", "We couldn't look through your texts just now. Try again in a moment.")));
        return;
      }
      tally.textContent =
        tn("palette.sentences", got.sentences, "{n} sentence", "{n} sentences") + " · " + tn("palette.texts", got.texts, "{n} text", "{n} texts");
      if ((got.forms || []).length) {
        forms.appendChild(el("span", "palette-forms-label", t("palette.found-as", "Found as")));
        got.forms.forEach(function (form) {
          var chip = el("bdi", "tag palette-form", form);
          chip.setAttribute("lang", word.language || "");
          forms.appendChild(chip);
        });
      }
      [
        ["yours", t("palette.word.in-yours", "In your targums")],
        ["library", t("palette.word.in-library", "In the Library")],
      ].forEach(function (pair) {
        var part = got[pair[0]];
        if (!part || !part.count) return;
        var section = el("section", "palette-group");
        section.setAttribute("data-group", pair[0]);
        var top = el("div", "palette-group-head");
        var title = el("h3", "palette-group-name");
        title.appendChild(glyph(GLYPHS[pair[0]]));
        title.appendChild(el("span", "", pair[1]));
        title.appendChild(el("span", "palette-group-count", tn("palette.sentences", part.count, "{n} sentence", "{n} sentences")));
        top.appendChild(title);
        section.appendChild(top);
        var list = el("ul", "rows palette-rows");
        part.sentences.forEach(function (one) {
          list.appendChild(sentenceRow(one));
        });
        section.appendChild(list);
        parts.appendChild(section);
      });
      if (!got.sentences) parts.appendChild(el("p", "palette-quiet", t("palette.word.none", "No sentence on your shelf has this word yet.")));
    });
  }

  var chosen = -1;

  // Back from a word's sentences to what was found, under the filter it was opened from.
  function leaveWord() {
    state.word = null;
    state.filter = state.was || "all";
    draw();
  }

  function draw() {
    body.textContent = "";
    hits = [];
    chosen = -1;
    drawScope();
    drawFilters();
    host.classList.toggle("is-searching", !!state.answer);
    if (state.word) {
      drawWord();
      return;
    }
    var answer = state.answer;
    if (!answer) {
      drawEmpty();
      return;
    }
    if (answer.failed) {
      body.appendChild(el("p", "palette-quiet", t("palette.failed", "We couldn't search just now. Try again in a moment.")));
      return;
    }
    var drew = drawResults(answer);
    var other = elsewhere(answer);
    if (!drew && !other && !state.level) {
      body.appendChild(nothing(answer));
      return;
    }
    if (!drew && state.level) body.appendChild(el("p", "palette-quiet", t("palette.none-at-level", "Nothing found at that level.")));
    if (other && drew < 5) body.appendChild(other);
    body.appendChild(foot());
  }

  function choose(step) {
    if (!hits.length) return;
    chosen = Math.max(0, Math.min(hits.length - 1, chosen + step));
    hits.forEach(function (one, n) {
      one.classList.toggle("on", n === chosen);
    });
    if (hits[chosen].scrollIntoView) hits[chosen].scrollIntoView({ block: "nearest" });
  }

  /* --- opening and closing ------------------------------------------------- */

  function show(on, options) {
    var settings = options || {};
    host.hidden = !on;
    if (scrim) scrim.hidden = !on;
    if (opener) opener.setAttribute("aria-expanded", on ? "true" : "false");
    document.documentElement.classList.toggle("palette-up", !!on);
    if (!on) {
      if (scopeMenu) scopeMenu.hidden = true;
      // Focus leaves the field with it, or "/" would be typed into a field nobody sees.
      if (document.activeElement === field && field.blur) field.blur();
      return;
    }
    state.filter = settings.scope || "all";
    state.level = "";
    state.word = null;
    state.lang = "";
    state.opened = null;
    field.value = settings.q || "";
    search();
    field.focus();
  }

  field.addEventListener("input", function () {
    state.word = null;
    search();
  });
  field.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      choose(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      choose(-1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      remember(field.value);
      if (chosen < 0 && hits.length && state.answer) chosen = 0;
      if (hits[chosen]) hits[chosen].click();
    }
  });
  if (clearer) {
    clearer.addEventListener("click", function () {
      field.value = "";
      state.word = null;
      search();
      field.focus();
    });
  }
  if (back) {
    back.addEventListener("click", function () {
      if (state.word) {
        leaveWord();
        return;
      }
      show(false);
    });
  }
  if (scope && scopeMenu) {
    scope.addEventListener("click", function () {
      var open = scopeMenu.hidden;
      drawScopeMenu();
      scopeMenu.hidden = !open;
      scope.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  function typing(target) {
    if (!target) return false;
    var tag = String(target.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || !!target.isContentEditable;
  }

  document.addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && String(event.key).toLowerCase() === "k") {
      event.preventDefault();
      show(host.hidden);
    } else if (event.key === "/" && host.hidden && !event.metaKey && !event.ctrlKey && !event.altKey && !typing(event.target)) {
      event.preventDefault();
      show(true);
    } else if (event.key === "Escape" && !host.hidden) {
      if (scopeMenu && !scopeMenu.hidden) {
        scopeMenu.hidden = true;
        return;
      }
      if (state.word) {
        leaveWord();
        return;
      }
      show(false);
    }
  });
  if (opener) {
    opener.addEventListener("click", function () {
      show(host.hidden);
    });
  }
  // Search from the account's sheet on a phone (2026-09-14): the sheet goes as the search
  // comes, or it would stand open under it.
  Array.prototype.forEach.call(document.querySelectorAll("[data-palette-open]"), function (door) {
    door.addEventListener("click", function (event) {
      event.stopPropagation();
      var sheet = door.closest("[role=dialog]");
      if (sheet) sheet.hidden = true;
      var account = document.getElementById("account-open");
      if (account) {
        account.setAttribute("aria-expanded", "false");
        account.classList.remove("on");
      }
      show(true);
    });
  });
  if (scrim) {
    scrim.addEventListener("click", function () {
      show(false);
    });
  }

  window.TargumPalette = { show: show };
})();
