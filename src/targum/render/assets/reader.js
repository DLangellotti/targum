/* targum reader.
   Everything here is progressive: the page reads with this file absent. It restores
   preferences, switches modes and translations, moves the selection with the keyboard,
   and keeps the list of words and phrases you decide to save. */

(function () {
  "use strict";

  var STORE = "targum:prefs";
  var root = document.documentElement;
  var body = document.body;
  var main = document.getElementById("reader");
  if (!main) return;

  var pairs = Array.prototype.slice.call(main.querySelectorAll(".pair"));
  var dataNode = document.getElementById("targum-data");
  var data = {};
  try {
    data = dataNode ? JSON.parse(dataNode.textContent) : {};
  } catch (e) {
    data = {};
  }

  var translationData = data.translations || {};
  var wordData = data.words || {};
  var lemmas = data.lemmas || [];
  var glosses = data.glosses || [];
  var levelNames = data.levelNames || {};
  var hasGloss = glosses.length > 0;
  var originalHTML = {};

  // list starts as null, meaning "decide from the width". Once you open or close it
  // yourself that choice is kept.
  var prefs = { mode: "parallel", size: 1.0625, leading: 1.75, translation: null, list: null };
  try {
    var stored = JSON.parse(localStorage.getItem(STORE) || "{}");
    for (var key in stored) if (key in prefs) prefs[key] = stored[key];
  } catch (e) {}

  function save() {
    try {
      localStorage.setItem(STORE, JSON.stringify(prefs));
    } catch (e) {}
  }

  /* --- what you have kept -------------------------------------------------- */

  // One list, two kinds of thing in it. Words are held by dictionary form so every
  // form of the same word is marked at once; phrases are held as offsets into the
  // segment they came from, so they survive a rerender.
  var language = root.getAttribute("lang") || "und";
  // Keyed by document rather than by language: what you kept while reading one
  // article belongs to that article, and its export should hold that and nothing else.
  var documentId = data.document || location.pathname;
  var documentTitle = data.title || document.title || "";
  var SAVED = "targum:saved:" + documentId;
  var PICKED = "targum:picked:" + documentId;
  var MASTER = "targum:master";

  // When you last had this text open, so the library can put what you are part way
  // through at the top.
  try {
    var opened = JSON.parse(localStorage.getItem("targum:opened") || "{}");
    opened[documentId] = Date.now();
    localStorage.setItem("targum:opened", JSON.stringify(opened));
  } catch (e) {}

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
  }

  var saved = read(SAVED, "{}");
  var picks = read(PICKED, "{}");
  var sequence = 0;

  function remember() {
    try {
      localStorage.setItem(SAVED, JSON.stringify(saved));
      localStorage.setItem(PICKED, JSON.stringify(picks));
      updateMaster();
    } catch (e) {}
  }

  // Everything kept across every text, gathered in one place as you go. Nothing reads
  // it yet; it is here so that what you collect while reading is not stranded inside
  // one article when there is something to do with it.
  function updateMaster() {
    var all = {};
    try {
      all = JSON.parse(localStorage.getItem(MASTER) || "{}");
    } catch (e) {
      all = {};
    }
    var rows = entries();
    if (rows.length) {
      all[documentId] = {
        title: documentTitle,
        language: language,
        updated: Date.now(),
        entries: rows.map(function (row) {
          return {
            text: row.term,
            lemma: row.lemma,
            level: row.level,
            kind: row.kind,
            meaning: row.meaning,
          };
        }),
      };
    } else {
      delete all[documentId];
    }
    try {
      localStorage.setItem(MASTER, JSON.stringify(all));
    } catch (e) {}
  }

  function nextOrder() {
    sequence += 1;
    return Date.now() + sequence;
  }

  // The segment's text without markup, for reading a token's surface back out of it.
  var plainText = {};

  function segmentText(segmentId) {
    if (plainText[segmentId] === undefined) {
      var holder = document.createElement("div");
      holder.innerHTML = originalHTML[segmentId] || "";
      plainText[segmentId] = holder.textContent;
    }
    return plainText[segmentId];
  }

  function toggleWord(index, surface, level) {
    var lemma = lemmas[index];
    if (!lemma) return false;
    if (saved[lemma]) {
      delete saved[lemma];
    } else {
      saved[lemma] = {
        surface: surface,
        lemma: lemma,
        level: level,
        meaning: glosses[index] || "",
        at: nextOrder(),
      };
      if (listBox && listBox.hidden) showList(true);
    }
    remember();
    return !!saved[lemma];
  }

  /* --- marking the page ---------------------------------------------------- */

  // Words are wrapped from character offsets rather than from a span per word emitted
  // up front: a book has hundreds of thousands of tokens, and that markup would not
  // open on a phone. Saved phrases are drawn in the same pass, because a phrase can
  // start mid-word and cover several, which the DOM will not nest.
  function markSegment(cell) {
    var segmentId = cell.parentNode.getAttribute("data-id");
    if (originalHTML[segmentId] === undefined) originalHTML[segmentId] = cell.innerHTML;
    cell.innerHTML = originalHTML[segmentId];

    var layers = [];
    (wordData[segmentId] || []).forEach(function (token) {
      var lemma = lemmas[token[4]];
      var classes = ["w"];
      if (token[3]) classes.push("split");
      if (saved[lemma]) classes.push("saved");
      layers.push({ start: token[0], end: token[1], classes: classes, lemma: token[4] });
    });
    (picks[segmentId] || []).forEach(function (pick, index) {
      layers.push({ start: pick.start, end: pick.end, classes: ["picked"], pick: index });
    });
    if (!layers.length) return;

    var offset = 0;
    var nodes = [];
    var walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while ((node = walker.nextNode())) {
      nodes.push({ node: node, start: offset, end: offset + node.nodeValue.length });
      offset += node.nodeValue.length;
    }

    nodes.forEach(function (entry) {
      // A layer can straddle a <bdi> boundary, so each piece is clipped to its node.
      var here = [];
      layers.forEach(function (layer) {
        var start = Math.max(layer.start, entry.start);
        var end = Math.min(layer.end, entry.end);
        if (start < end) {
          here.push({
            start: start,
            end: end,
            classes: layer.classes,
            lemma: layer.lemma,
            pick: layer.pick,
          });
        }
      });
      if (!here.length) return;

      // Every boundary any layer introduces, so the slices between them are atomic.
      var cuts = {};
      here.forEach(function (layer) {
        cuts[layer.start] = true;
        cuts[layer.end] = true;
      });
      var points = Object.keys(cuts)
        .map(Number)
        .sort(function (a, b) {
          return a - b;
        });

      var text = entry.node.nodeValue;
      var fragment = document.createDocumentFragment();
      var cursor = entry.start;
      for (var i = 0; i < points.length - 1; i++) {
        var from = points[i];
        var to = points[i + 1];
        var covering = here.filter(function (layer) {
          return layer.start <= from && layer.end >= to;
        });
        if (from > cursor) {
          fragment.appendChild(
            document.createTextNode(text.slice(cursor - entry.start, from - entry.start))
          );
        }
        var slice = text.slice(from - entry.start, to - entry.start);
        if (!covering.length) {
          fragment.appendChild(document.createTextNode(slice));
        } else {
          var span = document.createElement("span");
          var classes = {};
          var lemma = null;
          var pick = null;
          covering.forEach(function (layer) {
            layer.classes.forEach(function (name) {
              classes[name] = true;
            });
            if (layer.lemma !== undefined && layer.lemma !== null) lemma = layer.lemma;
            if (layer.pick !== undefined && layer.pick !== null) pick = layer.pick;
          });
          span.className = Object.keys(classes).join(" ");
          if (lemma !== null) span.setAttribute("data-lemma", lemma);
          if (pick !== null) span.setAttribute("data-pick", pick);
          if (classes.split) span.title = "read as a prefix plus a word";
          span.textContent = slice;
          fragment.appendChild(span);
        }
        cursor = to;
      }
      if (cursor - entry.start < text.length) {
        fragment.appendChild(document.createTextNode(text.slice(cursor - entry.start)));
      }
      entry.node.parentNode.replaceChild(fragment, entry.node);
    });
  }

  function redraw() {
    pairs.forEach(function (pair) {
      var cell = pair.querySelector(".src");
      if (cell) markSegment(cell);
    });
    renderList();
  }

  /* --- the list ------------------------------------------------------------ */

  var listBox = document.getElementById("list");
  var listItems = document.getElementById("list-items");
  var listEmpty = document.getElementById("list-empty");
  var listCount = document.getElementById("list-count");
  var listTab = document.getElementById("list-tab");
  var listTabCount = document.getElementById("list-tab-count");

  function translationFor(segmentId) {
    var entry = translationData[prefs.translation] || translationData.t0;
    return entry && entry.text ? entry.text[segmentId] || "" : "";
  }

  function entries() {
    var out = [];
    Object.keys(saved).forEach(function (lemma) {
      var item = saved[lemma];
      out.push({
        kind: "word",
        key: lemma,
        term: item.surface || lemma,
        lemma: lemma,
        level: item.level || "",
        meaning: item.meaning || "",
        at: item.at || 0,
      });
    });
    Object.keys(picks).forEach(function (segmentId) {
      picks[segmentId].forEach(function (pick, index) {
        out.push({
          kind: "phrase",
          key: segmentId + ":" + index,
          segmentId: segmentId,
          index: index,
          term: pick.text,
          lemma: "",
          level: "",
          meaning: pick.meaning || translationFor(segmentId),
          at: pick.at || 0,
        });
      });
    });
    return out.sort(function (a, b) {
      return a.at - b.at;
    });
  }

  var lastCount = null;

  function renderList() {
    if (!listBox) return;
    var rows = entries();

    if (listCount) listCount.textContent = String(rows.length);
    if (listTabCount) listTabCount.textContent = String(rows.length);
    if (lastCount !== null && rows.length > lastCount && listCount) {
      var holder = listCount.parentNode;
      holder.classList.remove("bumped");
      // Restarting a CSS animation needs a reflow between removing and adding.
      void holder.offsetWidth;
      holder.classList.add("bumped");
    }
    lastCount = rows.length;

    if (listEmpty) listEmpty.hidden = rows.length > 0;
    if (!listItems) return;
    listItems.textContent = "";

    rows.forEach(function (row) {
      var item = document.createElement("li");

      var term = document.createElement("span");
      term.className = "term";
      var word = document.createElement("bdi");
      word.setAttribute("lang", language);
      word.textContent = row.term;
      term.appendChild(word);
      if (row.lemma && row.lemma !== row.term) {
        var separator = document.createElement("span");
        separator.className = "sep";
        separator.textContent = "·";
        term.appendChild(separator);
        var dictionary = document.createElement("bdi");
        dictionary.setAttribute("lang", language);
        dictionary.className = "dict";
        dictionary.textContent = row.lemma;
        term.appendChild(dictionary);
      }
      item.appendChild(term);

      var kind = document.createElement("span");
      kind.className = "kind";
      kind.textContent = row.kind === "phrase" ? "phrase" : row.level;
      item.appendChild(kind);

      if (row.meaning) {
        var meaning = inTarget(document.createElement("span"));
        meaning.className = "meaning";
        meaning.textContent = row.meaning;
        item.appendChild(meaning);
      }

      var drop = document.createElement("button");
      drop.type = "button";
      drop.className = "drop";
      drop.textContent = "×";
      drop.title = "Take this off the list";
      drop.onclick = function () {
        if (row.kind === "word") {
          delete saved[row.key];
        } else {
          picks[row.segmentId].splice(row.index, 1);
          if (!picks[row.segmentId].length) delete picks[row.segmentId];
        }
        remember();
        redraw();
      };
      item.appendChild(drop);
      listItems.appendChild(item);
    });
  }

  function showList(open, remembered) {
    if (remembered !== false) prefs.list = open;
    if (listBox) listBox.hidden = !open;
    if (listTab) listTab.hidden = open;
    body.classList.toggle("list-open", open);
    if (remembered !== false) save();
  }

  var roomy = window.matchMedia("(min-width: 60rem)");

  /* --- what a word means --------------------------------------------------- */

  var card = document.getElementById("gloss-card");
  var lookedUp = null;

  function hideCard() {
    if (card) card.hidden = true;
    if (lookedUp) lookedUp.classList.remove("looked-up");
    lookedUp = null;
  }

  function levelOf(word) {
    var pair = word.closest(".pair");
    if (!pair) return "";
    var segmentId = pair.getAttribute("data-id");
    var index = parseInt(word.getAttribute("data-lemma"), 10);
    var match = (wordData[segmentId] || []).filter(function (token) {
      return token[4] === index;
    })[0];
    return match ? levelNames[match[2]] || "" : "";
  }

  function showCard(word) {
    if (!card) return;
    var index = parseInt(word.getAttribute("data-lemma"), 10);
    var lemma = lemmas[index];
    if (!lemma) return;

    hideCard();
    lookedUp = word;
    word.classList.add("looked-up");
    card.textContent = "";

    var head = document.createElement("bdi");
    head.className = "lemma";
    head.setAttribute("lang", language);
    head.textContent = lemma;
    card.appendChild(head);

    var level = levelOf(word);
    if (level) {
      var tag = document.createElement("span");
      tag.className = "pos";
      tag.textContent = level;
      card.appendChild(tag);
    }

    var meaning = inTarget(document.createElement("span"));
    meaning.className = "meaning";
    meaning.textContent = glosses[index] || (hasGloss ? "no meaning recorded" : "");
    card.appendChild(meaning);

    var keep = document.createElement("button");
    keep.type = "button";
    keep.className = "keep";
    keep.textContent = saved[lemma] ? "on your list ✓" : "add to my list";
    keep.onclick = function (event) {
      event.stopPropagation();
      var now = toggleWord(index, word.textContent, level);
      keep.textContent = now ? "on your list ✓" : "add to my list";
      redraw();
    };
    card.appendChild(keep);

    if (word.classList.contains("split")) {
      // Say so rather than presenting one reading of an ambiguous string as settled.
      var caveat = document.createElement("span");
      caveat.className = "caveat";
      caveat.textContent =
        "read as a prefix plus a word, so this dictionary form is one reading";
      card.appendChild(caveat);
    }
    card.hidden = false;
  }

  /* --- keeping a phrase ---------------------------------------------------- */

  var chip = document.getElementById("pick-chip");

  // The translation's own language and direction, read off the page. A card is chrome
  // and runs left to right, but the text inside it belongs to whichever language it
  // came from, or an English sentence on a Hebrew page loses its full stop to the
  // wrong end of the line.
  var trCell = main.querySelector(".tr");
  var targetLanguage = trCell ? trCell.getAttribute("lang") : "";
  var targetDirection = trCell ? trCell.getAttribute("dir") : "";

  function inTarget(element) {
    if (targetLanguage) element.setAttribute("lang", targetLanguage);
    if (targetDirection) element.setAttribute("dir", targetDirection);
    return element;
  }

  // Where a DOM position falls in the segment's own text. The reader rebuilds these
  // cells constantly, so offsets are the only stable way to record a selection.
  //
  // Measured by probing a range rather than by walking text nodes: a selection
  // boundary can sit on an element rather than inside a text node, where the offset
  // counts child nodes instead of characters. Selecting a whole paragraph, which is
  // what a triple click does, lands exactly there.
  function offsetWithin(cell, container, offset) {
    var probe = document.createRange();
    probe.selectNodeContents(cell);
    try {
      probe.setEnd(container, offset);
    } catch (e) {
      return null;
    }
    return probe.toString().length;
  }

  function currentSelection() {
    var selection = window.getSelection ? window.getSelection() : null;
    if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
    var range = selection.getRangeAt(0);
    var cell = range.startContainer;
    if (cell.nodeType !== 1) cell = cell.parentNode;
    while (cell && !(cell.classList && cell.classList.contains("src"))) cell = cell.parentNode;
    if (!cell || !cell.contains(range.endContainer)) return null;

    var start = offsetWithin(cell, range.startContainer, range.startOffset);
    var end = offsetWithin(cell, range.endContainer, range.endOffset);
    if (start === null || end === null || end <= start) return null;
    return {
      segmentId: cell.parentNode.getAttribute("data-id"),
      start: start,
      end: end,
      text: selection.toString().trim(),
      rect: range.getBoundingClientRect(),
    };
  }

  // A selection that touches exactly one word is that word. Saving it as a phrase
  // would throw away the dictionary form and the meaning, and leave two entries for
  // the same thing depending on whether you tapped it or dragged over it.
  function soleToken(picked) {
    var touching = (wordData[picked.segmentId] || []).filter(function (token) {
      return token[0] < picked.end && token[1] > picked.start;
    });
    return touching.length === 1 ? touching[0] : null;
  }

  function place(rect) {
    chip.hidden = false;
    chip.style.translate = "0 0";
    chip.style.transform = "none";
    chip.style.left = "0px";
    chip.style.top = "0px";

    var box = chip.getBoundingClientRect();

    // Centred on the selection but kept inside the window. A selection near the edge
    // of an RTL page is at the right, and a card centred on it would hang off it.
    var wanted = rect.left + rect.width / 2 - box.width / 2;
    var limit = window.innerWidth - box.width - 12;
    chip.style.left = Math.max(12, Math.min(wanted, limit)) + window.scrollX + "px";

    // Above the selection where there is room, below it where there is not. A card
    // for a phrase near the top of the page would otherwise be cut off by the window.
    var above = rect.top - box.height - 8;
    var top = above >= 8 ? above : rect.bottom + 8;
    chip.style.top = top + window.scrollY + "px";
  }

  // Whether the selection is the whole sentence, give or take the whitespace at its
  // edges. When it is, the translation on the page is the translation of it, exactly.
  function coversSegment(picked) {
    var text = segmentText(picked.segmentId);
    var first = text.search(/\S/);
    var last = text.replace(/\s+$/, "").length;
    return first > -1 && picked.start <= first && picked.end >= last;
  }

  // What a run of words means, composed from the glosses the reader already carries.
  // Only used for part of a sentence: alignment pairs whole sentences, so there is no
  // way to say which part of the translation answers to which part of the source, and
  // slicing it proportionally would be confidently wrong. Word by word is what can
  // honestly be offered, and it is labelled as that.
  function wordByWord(picked) {
    var parts = [];
    (wordData[picked.segmentId] || []).forEach(function (token) {
      if (token[0] < picked.end && token[1] > picked.start) {
        var meaning = glosses[token[4]];
        if (meaning) parts.push(meaning.split(";")[0].trim());
      }
    });
    return parts.join(" · ");
  }

  function pickCard(parts) {
    chip.textContent = "";
    var phrase = document.createElement("span");
    phrase.className = "phrase";
    var text = document.createElement("bdi");
    text.setAttribute("lang", language);
    text.textContent = parts.title;
    phrase.appendChild(text);
    chip.appendChild(phrase);

    if (parts.reading) {
      var reading = inTarget(document.createElement("span"));
      reading.className = "reading";
      reading.textContent = parts.reading;
      chip.appendChild(reading);
    }
    if (parts.note) {
      var note = document.createElement("span");
      note.className = "source-note";
      note.textContent = parts.note;
      chip.appendChild(note);
    }

    var action = document.createElement("button");
    action.type = "button";
    action.textContent = parts.action;
    action.onclick = parts.onclick;
    chip.appendChild(action);
  }

  // Pressing the mouse down on the card must not count as starting a new selection.
  // Without this the browser collapses the selection on mousedown, the mouseup below
  // sees nothing selected and hides the card, and the click never lands on the button
  // that was under the cursor. Which looks exactly like the button doing nothing.
  if (chip) {
    chip.addEventListener("mousedown", function (event) {
      event.preventDefault();
    });
  }

  document.addEventListener("mouseup", function (event) {
    if (!chip) return;
    if (chip.contains(event.target)) return;
    var picked = currentSelection();
    if (!picked || !picked.text) {
      chip.hidden = true;
      return;
    }

    var token = soleToken(picked);
    if (token) {
      var index = token[4];
      var lemma = lemmas[index];
      pickCard({
        title: lemma,
        reading: glosses[index] || "",
        note: levelNames[token[2]] || "",
        action: saved[lemma] ? "take off my list" : "add word to my list",
        onclick: function () {
          toggleWord(
            index,
            segmentText(picked.segmentId).slice(token[0], token[1]),
            levelNames[token[2]] || ""
          );
          if (window.getSelection) window.getSelection().removeAllRanges();
          chip.hidden = true;
          redraw();
        },
      });
      place(picked.rect);
      return;
    }

    // Dragging over a phrase you already kept offers to drop it again. Tapping cannot:
    // a tap means "what does this mean", and a phrase usually covers several words.
    var existing = -1;
    (picks[picked.segmentId] || []).forEach(function (item, index) {
      if (item.start < picked.end && item.end > picked.start) existing = index;
    });

    // The whole sentence has a translation already; a part of one does not.
    var whole = coversSegment(picked);
    var reading = whole ? translationFor(picked.segmentId) : wordByWord(picked);
    pickCard({
      title: picked.text,
      reading: reading,
      note: whole
        ? "from the translation"
        : reading
          ? "word by word, from the glossary"
          : "",
      action: existing > -1 ? "take off my list" : "add phrase to my list",
      onclick: function () {
        var list = picks[picked.segmentId] || (picks[picked.segmentId] = []);
        if (existing > -1) {
          list.splice(existing, 1);
          if (!list.length) delete picks[picked.segmentId];
        } else {
          list.push({
            start: picked.start,
            end: picked.end,
            text: picked.text,
            meaning: reading,
            at: nextOrder(),
          });
          if (listBox && listBox.hidden) showList(true);
        }
        remember();
        if (window.getSelection) window.getSelection().removeAllRanges();
        chip.hidden = true;
        redraw();
      },
    });
    place(picked.rect);
  });

  /* --- export -------------------------------------------------------------- */

  function csvCell(value) {
    var text = value === undefined || value === null ? "" : String(value);
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function exportCsv() {
    var header = ["text", "dictionary form", "difficulty", "kind", "meaning"];
    var rows = entries().map(function (row) {
      return [row.term, row.lemma, row.level, row.kind, row.meaning];
    });
    // A byte order mark, so a spreadsheet opens Hebrew and Russian as UTF-8.
    var csv =
      "\ufeff" +
      [header]
        .concat(rows)
        .map(function (row) {
          return row.map(csvCell).join(",");
        })
        .join("\n");

    var blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download =
      (document.title || "targum").replace(/[^\w\u0080-\uffff -]+/g, "").trim() + " list.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  /* --- type and mode ------------------------------------------------------- */

  function applyType() {
    prefs.size = Math.min(1.75, Math.max(0.875, prefs.size));
    root.style.setProperty("--size", prefs.size + "rem");
    root.style.setProperty("--leading", prefs.leading);
    // Hebrew and Arabic keep their extra room as the leading moves.
    root.style.setProperty("--leading-rtl", (prefs.leading + 0.2).toFixed(2));
  }

  function applyMode() {
    body.className = body.className.replace(/\bmode-\w+/g, "").trim();
    body.classList.add("mode-" + prefs.mode);
    Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (button) {
      button.classList.toggle("on", button.getAttribute("data-mode") === prefs.mode);
    });
    hideCard();
  }

  var picker = document.getElementById("translation");

  function applyTranslation(id) {
    var entry = translationData[id];
    if (!entry || !entry.text) return;
    var coarse = {};
    (entry.coarse || []).forEach(function (segmentId) {
      coarse[segmentId] = true;
    });
    pairs.forEach(function (pair) {
      var segmentId = pair.getAttribute("data-id");
      var cell = pair.querySelector(".tr");
      if (cell) cell.textContent = entry.text[segmentId] || "";
      // Each translation is aligned independently, so which regions are approximate
      // changes with the translation on show.
      pair.classList.toggle("coarse", !!coarse[segmentId]);
    });
    prefs.translation = id;
    save();
    renderList();
  }

  if (picker) {
    if (prefs.translation && translationData[prefs.translation]) {
      picker.value = prefs.translation;
      applyTranslation(prefs.translation);
    }
    picker.addEventListener("change", function () {
      applyTranslation(picker.value);
    });
  }

  /* --- clicks -------------------------------------------------------------- */

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("button") : null;
    if (button) {
      if (button.getAttribute("data-toggle") === "list") {
        showList(!!(listBox && listBox.hidden));
        return;
      }
      if (button.getAttribute("data-export") === "csv") {
        exportCsv();
        return;
      }
      var mode = button.getAttribute("data-mode");
      if (mode) {
        prefs.mode = mode;
        applyMode();
        save();
        return;
      }
      var action = button.getAttribute("data-type");
      if (action === "larger") prefs.size += 0.0625;
      if (action === "smaller") prefs.size -= 0.0625;
      if (action === "looser") prefs.leading = prefs.leading >= 2.1 ? 1.5 : prefs.leading + 0.15;
      if (action) {
        applyType();
        save();
      }
      return;
    }

    // A word answers the same way whichever mode you are reading in.
    var word = event.target.closest ? event.target.closest(".w") : null;
    if (word) {
      showCard(word);
      return;
    }
    hideCard();
  });

  /* --- keyboard ------------------------------------------------------------ */

  // Right-arrow means forward in Hebrew and backward in English. Read the direction
  // off the page rather than assuming either one.
  var rtl = (root.getAttribute("dir") || "ltr") === "rtl";

  function move(step) {
    var index = pairs.indexOf(document.activeElement);
    var next = pairs[Math.min(pairs.length - 1, Math.max(0, index + step))];
    if (next) {
      next.focus();
      if (next.scrollIntoView) next.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;

    switch (event.key) {
      case "ArrowDown":
      case "j":
        move(1);
        break;
      case "ArrowUp":
      case "k":
        move(-1);
        break;
      case "ArrowRight":
        move(rtl ? -1 : 1);
        break;
      case "ArrowLeft":
        move(rtl ? 1 : -1);
        break;
      case "p":
        prefs.mode = "parallel";
        applyMode();
        save();
        return;
      case "o":
        prefs.mode = "source";
        applyMode();
        save();
        return;
      case "s":
        if (listBox) showList(!!listBox.hidden);
        return;
      case "Escape":
        hideCard();
        return;
      default:
        return;
    }
    event.preventDefault();
  });

  // A way back, but only when there is somewhere to go back to. A reader opened
  // straight off the disk has no library page behind it, and the key it was served
  // with is the one it carries in its own address.
  var home = document.getElementById("home");
  if (home) {
    var served = /^https?:$/.test(location.protocol);
    var passKey = new URLSearchParams(location.search).get("k");
    if (served && passKey) {
      home.href = "/?k=" + encodeURIComponent(passKey);
      home.hidden = false;
      // Section-to-section links are relative and would drop the key, and with it
      // access: the next chapter would answer 403.
      var carried = document.querySelectorAll(".pager a, .bar-title .up");
      Array.prototype.forEach.call(carried, function (link) {
        var href = link.getAttribute("href");
        if (href && href.indexOf("?") === -1) {
          link.setAttribute("href", href + "?k=" + encodeURIComponent(passKey));
        }
      });
    }
  }

  applyType();
  applyMode();
  showList(prefs.list === null ? roomy.matches : prefs.list, prefs.list === null ? false : true);
  redraw();
})();
