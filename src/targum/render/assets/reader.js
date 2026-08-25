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

  /* --- where the time went, when asked ---------------------------------------
   *
   * Open a reader with `?debug=timing` and it says how long each part of starting up
   * took, in the browser that has the problem rather than in the one measuring it.
   * Silent otherwise. It exists because a page that felt slow measured fast everywhere
   * it could be measured, and guessing at that is how the wrong thing gets optimised.
   */
  // Matched against the raw address rather than parsed out of it. A reader is opened
  // with a key already in the query, so `?debug=timing` on the end makes a second `?`
  // and a parser reads the whole lot as the key — the switch then does nothing, silently,
  // which is the worst way for a diagnostic to fail.
  var timing = (location.search + location.hash).indexOf("debug=timing") >= 0;
  var began = performance.now();
  var timings = [];
  var readout = null;

  // Always recorded — it is four numbers and a string — and shown on request. Asking for
  // it through the address failed twice: a reader already carries a key in its query, so
  // `?debug=timing` on the end makes a second `?`, and a diagnostic whose address has to
  // be edited by hand is one that does not work when it is needed. Pressing `t` cannot
  // be got wrong.
  var lastTook = 0;

  // Two numbers, because one was ambiguous and cost a round trip to find out: when this
  // happened, counted from the first line of the reader, and how long since the line
  // before it. A timestamp alone cannot say whether five seconds went inside the step it
  // is printed against or in the wait before it.
  function took(what) {
    var at = performance.now() - began;
    timings.push(
      what + ": " + Math.round(at) + "ms (+" + Math.round(at - lastTook) + "ms)"
    );
    lastTook = at;
    if (timing) showTimings(true);
  }

  // Anything that throws goes in the readout too. A reader that half-starts looks like
  // a reader that is slow: the marks never appear, the preference never applies, and
  // the only sign is a line missing from a list nobody is reading.
  window.addEventListener("error", function (event) {
    took(
      "ERROR " +
        (event.message || "?") +
        " — " +
        String(event.filename || "").split("/").pop() +
        ":" +
        event.lineno
    );
  });

  function showTimings(open) {
    if (!readout) {
      readout = document.createElement("pre");
      readout.className = "timing";
      document.body.appendChild(readout);
    }
    readout.hidden = !open;
    readout.textContent = timings.join("\n") + "\n";
  }

  // Whether a server is behind this page, and the key it was handed. A reader opened
  // straight off the disk has neither, and everything that needs them is skipped.
  var served = /^https?:$/.test(location.protocol);
  var passKey = new URLSearchParams(location.search).get("k");

  /* Hosted there is no start-up key: the session cookie identifies the reader, and a key
     riding in every URL is a bearer token in browser history, on a shared screen, and in
     a Referer. Local it stays, because there it proves the page came from the terminal
     that started the process. Both cases are this one branch.

     These are the same two helpers every other page has. The reader called them and
     never had them: `home.href = keyed("/")` threw on the first served page load, and
     everything after it — the type size, the reading mode, the marking, the vowels, the
     word list, the sync — never ran. On a page opened off the disk it is unreachable, so
     it never showed up there. */
  function keyed(path) {
    if (!passKey) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(passKey);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (passKey) head["X-Targum-Key"] = passKey;
    return head;
  }

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
  var roots = data.roots || [];
  var binyanim = data.binyanim || [];
  var glosses = data.glosses || [];
  var levelNames = data.levelNames || {};
  var hasGloss = glosses.length > 0;
  // True while the meanings are still being looked up, so a word with no meaning yet
  // can say which of the two it is: not looked up yet, or looked up and not found.
  var meaningsPending = false;

  // Each sentence ships twice, bare and pointed, so both go through the server's bidi
  // isolation and neither has to be rebuilt here. Only one is ever on show.
  var plainCell = {};
  var pointedCell = {};
  pairs.forEach(function (pair) {
    var segmentId = pair.getAttribute("data-id");
    plainCell[segmentId] = pair.querySelector(".src.plain");
    pointedCell[segmentId] = pair.querySelector(".src.pointed");
  });
  var hasNikkud = Object.keys(pointedCell).some(function (id) {
    return !!pointedCell[id];
  });

  // Kept on the element rather than under the segment id, because a segment now has two
  // cells and one key for both would hand each the other's markup.
  function original(cell) {
    if (cell.__targumHTML === undefined) cell.__targumHTML = cell.innerHTML;
    return cell.__targumHTML;
  }

  // list starts as null, meaning "decide from the width". Once you open or close it
  // yourself that choice is kept.
  var prefs = {
    mode: "parallel",
    size: 1.0625,
    leading: 1.75,
    translation: null,
    list: null,
    nikkud: false,
    // Reading, or marking. Off is reading: no tints, and every word an ordinary word.
    //
    // On by default. It was off for a day, on the argument that a page covered in marks
    // is a worksheet — but a reader who has to find a key before the product does its one
    // distinctive thing has to know the key is there. The quiet page is one keystroke
    // away and the choice sticks, which is the right way round for a default.
    marking: true,
    listTab: "words",
    // Per document, because whose vowels these are is a fact about the text, not a
    // setting. A pointed poem opens pointed; a news article whose points were all
    // guessed opens bare. Only what you choose yourself is remembered here.
    nikkudBy: {},
    // Which generation of the defaults this browser has seen. See below.
    defaults: 0,
  };

  // A preference already in a browser beats a new default forever, so a default can only
  // be changed for somebody who has not got one — which, a day in, is nobody. When this
  // moves, the handful of settings named beside it are taken from the code once and the
  // reader's own choices after that are kept as they always were.
  // 2, not 1: the first pass turned marking on for browsers that had it off, and then
  // it got turned off again in one of them. Bumping this asks once more. It is blunt —
  // it overrides somebody who chose the quiet page on purpose — which is the price of
  // being able to change a default at all, and the reason to move it rarely.
  var DEFAULTS = 2;
  var RESET = { marking: true };

  try {
    var stored = JSON.parse(localStorage.getItem(STORE) || "{}");
    for (var key in stored) if (key in prefs) prefs[key] = stored[key];
  } catch (e) {}

  if ((prefs.defaults || 0) < DEFAULTS) {
    for (var changed in RESET) prefs[changed] = RESET[changed];
    prefs.defaults = DEFAULTS;
    save();
  }

  function save() {
    try {
      localStorage.setItem(STORE, JSON.stringify(prefs));
    } catch (e) {}
  }

  /* --- what you have kept -------------------------------------------------- */

  // One list, two kinds of thing in it. Words are held by dictionary form so every
  // form of the same word is marked at once; phrases are held as offsets into the
  // segment they came from, so they survive a rerender.
  var language = (root.getAttribute("lang") || "und").split("-")[0].toLowerCase();
  var documentId = data.document || location.pathname;
  var documentTitle = data.title || document.title || "";

  // Words are kept per language and shared by every text in it. Meeting a word again
  // in the next article, already marked, is the whole point of having kept it — which
  // is why this is no longer filed under the document it was first met in.
  //
  // Phrases stay per document: a phrase is a span of one sentence, and outside that
  // sentence it is not anything.
  var VOCAB = "targum:vocab:" + language;
  var PICKED = "targum:picked:" + documentId;
  var DOCS = "targum:docs";
  var MIGRATED = "targum:migrated";

  // What you have decided about a word. Learning runs 1 to 3, from just met to nearly
  // there; known and ignored are ends rather than steps. A word you have never marked
  // is not in the store at all, which is what makes "new" cost nothing to represent.
  var LEARNING = [1, 2, 3];
  var KNOWN = 9;
  var IGNORED = 0;

  function isLearning(status) {
    return status >= 1 && status <= 3;
  }

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

  var sequence = 0;

  function nextOrder() {
    sequence += 1;
    return Date.now() + sequence;
  }

  // Shared with the words page, which has to be able to run it too.
  if (window.TargumVocab) window.TargumVocab.migrate(language, documentId);

  var vocab = read(VOCAB, "{}");
  var picks = read(PICKED, "{}");

  function remember() {
    try {
      localStorage.setItem(VOCAB, JSON.stringify(vocab));
      localStorage.setItem(PICKED, JSON.stringify(picks));
      updateDocs();
    } catch (e) {}
    // Signed in, this goes up to the account a moment later; signed out it does
    // nothing at all, which is why nothing above it has to know which case it is in.
    if (window.TargumSync) window.TargumSync.touched();
  }

  // A record the reader has just changed. `seen` is the whole basis of the merge: it
  // is what tells the account that this browser's version of a word is the newer one.
  function stamp(record) {
    record.seen = Date.now();
    return record;
  }

  // Which texts you have read and in what language, so the library can total a
  // language's words without opening every reader to ask.
  function updateDocs() {
    var all = read(DOCS, "{}");
    all[documentId] = {
      title: documentTitle,
      language: language,
      updated: Date.now(),
    };
    try {
      localStorage.setItem(DOCS, JSON.stringify(all));
    } catch (e) {}
  }

  /* --- the two forms of a sentence ----------------------------------------- */

  // Hebrew combining marks. Deliberately not the whole 0591-05C7 block: the maqaf,
  // paseq, sof pasuq and nun hafukha live inside it and are characters of the text, not
  // marks above it. Mirrors MARKS in vocalize/base.py, and for the same reason.
  var MARK = /[\u0591-\u05BD\u05BF\u05C1-\u05C2\u05C4-\u05C5\u05C7]/;

  // Every stored offset — a token span, a phrase you kept — is measured against the
  // bare text, whichever form happens to be on show. That way turning the vowels on
  // cannot quietly move a saved phrase onto different characters. The pointed cell is
  // drawn by mapping those offsets across, and the map is derived from the text itself
  // rather than shipped with the page: it is one linear pass, and it costs nothing.
  var pointedIndex = {};

  function pointedMap(segmentId) {
    if (pointedIndex[segmentId] === undefined) {
      var text = cellText(pointedCell[segmentId]);
      var map = [];
      for (var i = 0; i < text.length; i++) if (!MARK.test(text[i])) map.push(i);
      map.push(text.length);
      pointedIndex[segmentId] = map;
    }
    return pointedIndex[segmentId];
  }

  // A position in the pointed text, back to the bare text it stands for.
  function toBare(segmentId, offset) {
    var text = cellText(pointedCell[segmentId]);
    var bare = 0;
    for (var i = 0; i < offset && i < text.length; i++) if (!MARK.test(text[i])) bare++;
    return bare;
  }

  // The segment's text without markup, for reading a token's surface back out of it.
  // Always the bare form: a word you keep should read the same whether you were looking
  // at the vowels or not, and one word must never become two entries in the list.
  var plainText = {};

  function cellText(cell) {
    if (!cell) return "";
    if (cell.__targumText === undefined) {
      var holder = document.createElement("div");
      holder.innerHTML = original(cell);
      cell.__targumText = holder.textContent;
    }
    return cell.__targumText;
  }

  function segmentText(segmentId) {
    if (plainText[segmentId] === undefined) {
      plainText[segmentId] = cellText(plainCell[segmentId]);
    }
    return plainText[segmentId];
  }

  // Looked up because you asked, not bought in advance. The answer is cached on the
  // machine, so the same word costs nothing the next time it turns up anywhere.
  var asked = {};
  // What came back for a word that had no meaning: "none" when it was looked up and
  // there was nothing to find, or the reason it could not be looked up. Kept so the
  // card can say which, instead of quietly offering the same button again.
  var lookup = {};

  function lookUp(index, onDone) {
    var lemma = lemmas[index];
    if (!lemma || !served || !passKey) return;
    if (asked[lemma]) return;
    asked[lemma] = true;
    fetch(keyed("/gloss"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ lemma: lemma, source: language, target: targetLanguage || "en" }),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (answer) {
        asked[lemma] = false;
        if (answer && answer.meaning) {
          glosses[index] = answer.meaning;
          hasGloss = true;
          delete lookup[lemma];
        } else {
          // A lemma the lemmatiser mangled is not a word, and the model is right to
          // decline rather than invent something for it.
          lookup[lemma] = answer && answer.error ? String(answer.error) : "none";
        }
        onDone(answer && answer.error ? String(answer.error) : "");
      })
      .catch(function () {
        asked[lemma] = false;
        onDone("Cannot reach targum.");
      });
  }

  function statusOf(lemma) {
    var item = vocab[lemma];
    return item ? item.status : undefined;
  }

  function noteOf(lemma) {
    var item = vocab[lemma];
    return item ? item.note || "" : "";
  }

  // Your own meaning for a word. Writing one against a word you have not marked yet
  // keeps it: putting down what something means is a way of saying you have met it.
  function setNote(index, surface, band, text) {
    var lemma = lemmas[index];
    if (!lemma) return;
    if (!vocab[lemma]) {
      if (!text) return;
      setStatus(index, surface, band, TargumVocab.LEARNING[0]);
    }
    if (!vocab[lemma]) return;
    vocab[lemma].note = text;
    vocab[lemma].seen = Date.now();
    remember();
  }

  // Setting a word to what it already is takes the mark off again, so the same tap
  // both grades a word and undoes a mistake.
  function setStatus(index, surface, band, status) {
    var lemma = lemmas[index];
    if (!lemma) return false;
    var current = statusOf(lemma);
    if (current === status) {
      delete vocab[lemma];
      if (window.TargumSync) window.TargumSync.forgetWord(language, lemma);
    } else {
      vocab[lemma] = {
        status: status,
        surface: vocab[lemma] ? vocab[lemma].surface || surface : surface,
        meaning: glosses[index] || (vocab[lemma] ? vocab[lemma].meaning : "") || "",
        // Whatever you wrote for it stays yours across a change of level.
        note: vocab[lemma] ? vocab[lemma].note || "" : "",
        band: band || (vocab[lemma] ? vocab[lemma].band : "") || "",
        at: vocab[lemma] ? vocab[lemma].at || nextOrder() : nextOrder(),
        seen: Date.now(),
      };
      if (isLearning(status) && listBox && listBox.hidden) showList(true);
    }
    remember();
    return statusOf(lemma);
  }

  function interlinear() {
    return prefs.mode === "inter";
  }

  /* --- marking the page ---------------------------------------------------- */

  // Words are wrapped from character offsets rather than from a span per word emitted
  // up front: a book has hundreds of thousands of tokens, and that markup would not
  // open on a phone. Saved phrases are drawn in the same pass, because a phrase can
  // start mid-word and cover several, which the DOM will not nest.
  function markSegment(cell) {
    var segmentId = cell.parentNode.getAttribute("data-id");
    cell.innerHTML = original(cell);

    // Offsets are held against the bare text. Drawing them on the pointed cell means
    // moving each span across, so that a word's marks travel inside its own span rather
    // than trailing outside it.
    var map = cell === pointedCell[segmentId] ? pointedMap(segmentId) : null;
    function at(offset) {
      if (!map) return offset;
      return offset < map.length ? map[offset] : map[map.length - 1];
    }

    var layers = [];
    (wordData[segmentId] || []).forEach(function (token) {
      var lemma = lemmas[token[4]];
      var classes = ["w"];
      if (token[3]) classes.push("split");
      var status = statusOf(lemma);
      if (status !== undefined) classes.push("marked");
      layers.push({
        start: at(token[0]),
        end: at(token[1]),
        classes: classes,
        status: status,
        lemma: token[4],
        // Where this word sits in the bare text. Saving reads its surface back out of
        // there, so the same word kept with the vowels showing and without is one entry.
        bare: token[0] + "," + token[1],
      });
    });
    (picks[segmentId] || []).forEach(function (pick, index) {
      layers.push({ start: at(pick.start), end: at(pick.end), classes: ["picked"], pick: index });
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
            status: layer.status,
            lemma: layer.lemma,
            bare: layer.bare,
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
          var bare = null;
          var pick = null;
          // Initialised, not merely declared: `var` is function-scoped, so a bare
          // declaration inside this loop keeps whatever the previous slice left in it
          // and one marked word smears its status across every word after it.
          var status = null;
          covering.forEach(function (layer) {
            layer.classes.forEach(function (name) {
              classes[name] = true;
            });
            if (layer.lemma !== undefined && layer.lemma !== null) lemma = layer.lemma;
            if (layer.status !== undefined && layer.status !== null) status = layer.status;
            if (layer.bare !== undefined && layer.bare !== null) bare = layer.bare;
            if (layer.pick !== undefined && layer.pick !== null) pick = layer.pick;
          });
          span.className = Object.keys(classes).join(" ");
          if (lemma !== null) span.setAttribute("data-lemma", lemma);
          if (status !== null) span.setAttribute("data-status", status);
          if (bare !== null) span.setAttribute("data-bare", bare);
          if (pick !== null) span.setAttribute("data-pick", pick);
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

  // Marking a pair turns a few text nodes into a few hundred inline spans, so doing it
  // to a whole chapter at once is several thousand elements before the browser paints
  // anything — and every one of them re-shapes a line of Hebrew. The work is the same
  // either way; what changes here is when it happens, so the marks on the part you are
  // looking at are not queued behind the marks on the part you are not.
  //
  // Nothing that counts anything reads the DOM — `lemmasHere`, `coverage` and
  // `wordEntries` all read the embedded word data — so every number on the page is the
  // same whichever pairs have been drawn.
  //
  // Two things were tried first and measured worse on a 400-pair chapter, both against
  // 106ms for simply marking the lot: reading every pair's rectangle up front to find
  // the visible ones cost 366ms, because asking for a rectangle before the browser has
  // laid the page out forces it to; and handing all 400 to an IntersectionObserver cost
  // 337ms, in `observe()` alone. Frames are cheaper than either.
  var AHEAD = 12; // pairs to mark before the first paint — about a screenful
  var pending = 0;
  // Whether the page has been through this once. The first pass is the only one that
  // runs before the browser has laid anything out, and so the only one that cannot
  // afford to ask where anything is.
  var drawn = false;

  // Drawn once per pass, whichever way the pair was reached — the background fill and a
  // scroll can both arrive at the same one, and marking rebuilds the cell from scratch.
  function markPair(pair) {
    if (pair.__targumDrawn === pending) return;
    pair.__targumDrawn = pending;
    var segmentId = pair.getAttribute("data-id");
    // Only the cell on show is worth marking; the other is redrawn when it appears.
    var cell = (prefs.nikkud && pointedCell[segmentId]) || plainCell[segmentId];
    if (cell) markSegment(cell);
  }

  // Everything in view, and a little either side. Cheap: the pairs are in document
  // order, so it stops at the first one past the bottom rather than walking the rest of
  // the chapter, and a pair already drawn this pass costs one property read.
  function markVisible() {
    var margin = window.innerHeight / 2;
    for (var n = 0; n < pairs.length; n++) {
      var box = pairs[n].getBoundingClientRect();
      if (box.bottom < -margin) continue;
      if (box.top > window.innerHeight + margin) break;
      markPair(pairs[n]);
    }
  }

  // Scrolling into a part of the chapter that has not been marked yet. Throttled to one
  // pass a frame, because a scroll fires far more often than that.
  var catching = false;

  function catchUp() {
    if (catching) return;
    catching = true;
    requestAnimationFrame(function () {
      catching = false;
      markVisible();
    });
  }

  function redraw() {
    pending += 1;
    var generation = pending;

    // Where to start. On the first pass the page is at the top and there is nothing laid
    // out to measure; afterwards the layout is current, reading it is cheap, and a mark
    // made by a keypress has to land in the frame the key was pressed in.
    var first = 0;
    if (drawn) {
      var margin = window.innerHeight;
      for (var n = 0; n < pairs.length; n++) {
        var box = pairs[n].getBoundingClientRect();
        if (box.bottom > -margin) {
          first = n;
          break;
        }
      }
    }
    drawn = true;

    var ordered = pairs.slice(first).concat(pairs.slice(0, first));

    // With no frames to schedule into, everything at once — the reader's standing rule
    // is that a missing API degrades rather than breaks.
    if (!window.requestAnimationFrame) {
      ordered.forEach(markPair);
      renderList();
      return;
    }

    // A screenful, and no more. The rest of the chapter is marked when it is scrolled
    // to, by `catchUp` — and never, for the part nobody reaches.
    //
    // It used to fill the whole page in the background, a slice per frame. That was
    // measured at 1,539ms on a real chapter in a real browser: work for text that was
    // mostly never looked at, competing with the scrolling of the text that was.
    ordered.slice(0, AHEAD).forEach(markPair);
    renderList();

    // Whatever else is on screen, once the browser has laid the page out — by then
    // asking where things are is free, and a screenful is not always twelve pairs.
    requestAnimationFrame(function () {
      if (generation !== pending) return;
      // Two lines: the wait for the browser's own first layout, and the marking done in
      // it. They were one number, and one number could not tell them apart.
      took("browser laid the page out and gave us a frame");
      markVisible();
      took("marks drawn on the rest of the screen");
    });
  }

  /* --- the list ------------------------------------------------------------ */

  var listBox = document.getElementById("list");
  var listItems = document.getElementById("list-items");
  var listCount = document.getElementById("list-count");
  var listTab = document.getElementById("list-tab");
  var listTabCount = document.getElementById("list-tab-count");
  var listTabPhrases = document.getElementById("list-tab-phrases");
  var phraseItems = document.getElementById("phrase-items");
  var phraseCount = document.getElementById("phrase-count");
  var wordsEmpty = document.getElementById("words-empty");
  var phrasesEmpty = document.getElementById("phrases-empty");
  var exportButton = document.getElementById("export-button");
  var tabs = document.querySelectorAll("[data-list]");
  var wordsLabel = document.getElementById("list-count-label");
  var phrasesLabel = document.getElementById("phrase-count-label");

  function label(element, count, one) {
    if (element) element.textContent = count === 1 ? one : one + "s";
  }

  function translationFor(segmentId) {
    var entry = translationData[prefs.translation] || translationData.t0;
    return entry && entry.text ? entry.text[segmentId] || "" : "";
  }

  // Every distinct dictionary form this section of the text uses. The list and the
  // count of what you know are both about the text in front of you, not about the
  // whole language: a vocabulary of four thousand words is not a reading aid.
  function lemmasHere() {
    var here = {};
    Object.keys(wordData).forEach(function (segmentId) {
      (wordData[segmentId] || []).forEach(function (token) {
        var lemma = lemmas[token[4]];
        if (lemma) here[lemma] = true;
      });
    });
    return Object.keys(here);
  }

  // Two lists, not one. A word is a fact about the language and travels with you; a
  // phrase is a piece of this text and stays with it. Counting them together said
  // neither number, and put a thing you keep for its wording next to a thing you keep
  // because you did not know it.
  function wordEntries() {
    var out = [];
    lemmasHere().forEach(function (lemma) {
      var item = vocab[lemma];
      // Known and ignored words are counted below but not listed: the list is what you
      // are still working on, and a finished word in it is in the way.
      if (!item || !isLearning(item.status)) return;
      out.push({
        kind: "word",
        key: lemma,
        term: item.surface || lemma,
        lemma: lemma,
        status: item.status,
        note: item.note || "",
        level: item.band || "",
        meaning: item.note || item.meaning || "",
        at: item.at || 0,
      });
    });
    return out.sort(byOrder);
  }

  function phraseEntries() {
    var out = [];
    Object.keys(picks).forEach(function (segmentId) {
      picks[segmentId].forEach(function (pick, index) {
        out.push({
          kind: "phrase",
          key: segmentId + ":" + index,
          segmentId: segmentId,
          index: index,
          term: pick.text,
          lemma: "",
          status: pick.status === undefined ? null : pick.status,
          note: pick.note || "",
          level: "",
          meaning: pick.note || pick.meaning || translationFor(segmentId),
          at: pick.at || 0,
        });
      });
    });
    return out.sort(byOrder);
  }

  function byOrder(a, b) {
    return a.at - b.at;
  }

  var listStats = document.getElementById("list-stats");
  var headerKnown = document.getElementById("known");

  // How much of what is in front of you you have already dealt with. The reason to
  // know it is choosing what to read next, so it counts this text and not the language.
  function coverage() {
    var here = lemmasHere();
    var counts = { total: here.length, learning: 0, known: 0, ignored: 0, fresh: 0 };
    here.forEach(function (lemma) {
      var status = statusOf(lemma);
      if (status === undefined) counts.fresh += 1;
      else if (status === KNOWN) counts.known += 1;
      else if (status === IGNORED) counts.ignored += 1;
      else counts.learning += 1;
    });
    return counts;
  }

  function renderStats() {
    var counts = coverage();
    // Ignored words are neither known nor waiting, so they come out of the total rather
    // than counting against you. Ignore means "this is not vocabulary" — a name, a
    // numeral, a word from another language — and counting it as known would make the
    // figure something you could raise without learning anything.
    var scored = counts.total - counts.ignored;

    // In the header, beside the title: how much of this text you can already read. The
    // words are counted here and the knowing is counted across the language, so a word
    // first met in another text already counts the moment you open this one.
    if (headerKnown) {
      headerKnown.hidden = !scored;
      if (scored) {
        // Built rather than written, so the two figures can carry the ledger treatment
        // the guidelines ask for and the words around them cannot.
        headerKnown.textContent = "";
        var whole = document.createElement("b");
        whole.textContent = String(counts.known);
        var all = document.createElement("b");
        all.textContent = String(scored);
        headerKnown.appendChild(whole);
        headerKnown.appendChild(document.createTextNode(" of "));
        headerKnown.appendChild(all);
        headerKnown.appendChild(document.createTextNode(" known"));
      }
    }

    if (!listStats) return;
    if (!counts.total) {
      listStats.textContent = "";
      return;
    }
    var share = scored ? Math.round((counts.known / scored) * 100) : 0;
    listStats.textContent =
      share + "% known here · " + counts.fresh + " you have not marked yet";
  }

  // Reading or marking. One class on the body, and nothing is redrawn: every word is
  // already wrapped in its span whichever mode you are in, so the difference is paint —
  // which is what keeps the lines from rebreaking as you switch, and what makes the text
  // you copy the same string either way.
  function applyMarking() {
    var on = !!prefs.marking;
    body.classList.toggle("marking", on);
    Array.prototype.forEach.call(document.querySelectorAll("[data-marking]"), function (button) {
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  var lastCounts = { words: null, phrases: null };

  function bump(element) {
    if (!element) return;
    var holder = element.parentNode;
    holder.classList.remove("bumped");
    // Restarting a CSS animation needs a reflow between removing and adding.
    void holder.offsetWidth;
    holder.classList.add("bumped");
  }

  function countInto(element, value, key) {
    if (element) element.textContent = String(value);
    if (lastCounts[key] !== null && value > lastCounts[key]) bump(element);
    lastCounts[key] = value;
  }

  function setPhrase(entry, changes) {
    var list = picks[entry.segmentId];
    var pick = list && list[entry.index];
    if (!pick) return;
    Object.keys(changes).forEach(function (name) {
      pick[name] = changes[name];
    });
    stamp(pick);
    remember();
    redraw();
  }

  function editorFor(entry) {
    if (entry.kind === "word") {
      var index = lemmas.indexOf(entry.lemma);
      if (index < 0) return null;
      return statusRow(index, entry.term, entry.level);
    }
    return TargumVocab.editor({
      status: entry.status,
      note: entry.note,
      placeholder: "Your own reading",
      onStatus: function (value) {
        setPhrase(entry, { status: value });
      },
      onNote: function (text) {
        if (text === entry.note) return;
        var list = picks[entry.segmentId];
        var pick = list && list[entry.index];
        if (!pick) return;
        pick.note = text;
        stamp(pick);
        remember();
      },
    });
  }

  // Which row is open for editing. One at a time: the panel is fifteen rems wide and
  // two scales stacked in it is not a list any more.
  var openRow = null;

  function row(entry) {
    var item = document.createElement("li");
    item.className = openRow === entry.key ? "open" : "";
    // Tapping the row says "I want to say something about this", which is the same
    // thing tapping the word in the text says.
    item.addEventListener("click", function (event) {
      if (event.target.closest("button, input")) return;
      openRow = openRow === entry.key ? null : entry.key;
      renderList();
    });

    var term = document.createElement("span");
    term.className = "term";
    var word = document.createElement("bdi");
    word.setAttribute("lang", language);
    word.textContent = entry.term;
    term.appendChild(word);
    if (entry.lemma && entry.lemma !== entry.term) {
      var separator = document.createElement("span");
      separator.className = "sep";
      separator.textContent = "·";
      term.appendChild(separator);
      var dictionary = document.createElement("bdi");
      dictionary.setAttribute("lang", language);
      dictionary.className = "dict";
      dictionary.textContent = entry.lemma;
      term.appendChild(dictionary);
    }
    item.appendChild(term);

    // A phrase is in its own list now, so it no longer has to announce that it is one.
    if (entry.kind === "word") {
      var kind = document.createElement("span");
      kind.className = "kind";
      kind.textContent = entry.level || "";
      if (!entry.level) kind.title = "not rated in this language";
      item.appendChild(kind);

      if (entry.status) {
        var mark = document.createElement("span");
        mark.className = "row-status status-" + entry.status;
        mark.textContent = String(entry.status);
        mark.title = "How well you know it";
        item.appendChild(mark);
      }
    }

    if (entry.meaning) {
      var meaning = inTarget(document.createElement("span"));
      meaning.className = "meaning";
      meaning.textContent = entry.meaning;
      item.appendChild(meaning);
    }

    var drop = document.createElement("button");
    drop.type = "button";
    drop.className = "drop";
    drop.textContent = "×";
    drop.title = "Take this off the list";
    drop.setAttribute("aria-label", "Take " + entry.term + " off the list");
    drop.onclick = function () {
      if (entry.kind === "word") {
        delete vocab[entry.key];
        if (window.TargumSync) window.TargumSync.forgetWord(language, entry.key);
      } else {
        var going = picks[entry.segmentId][entry.index];
        if (window.TargumSync && going) window.TargumSync.forgetPhrase(going.id);
        picks[entry.segmentId].splice(entry.index, 1);
        if (!picks[entry.segmentId].length) delete picks[entry.segmentId];
      }
      remember();
      redraw();
    };
    item.appendChild(drop);

    if (openRow === entry.key) {
      var editor = editorFor(entry);
      if (editor) {
        editor.classList.add("row-editor");
        item.appendChild(editor);
      }
    }
    return item;
  }

  function fill(list, rows) {
    if (!list) return;
    list.textContent = "";
    rows.forEach(function (entry) {
      list.appendChild(row(entry));
    });
  }

  // Which of the two lists is on show. Two counts, two lists and two exports, so the
  // panel holds one at a time rather than stacking them: a phrase section under a
  // hundred words is a section nobody scrolls to.
  function showTab(which) {
    prefs.listTab = which === "phrases" ? "phrases" : "words";
    var onPhrases = prefs.listTab === "phrases";
    Array.prototype.forEach.call(tabs, function (tab) {
      var selected = tab.getAttribute("data-list") === prefs.listTab;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.classList.toggle("on", selected);
    });
    if (listItems) listItems.hidden = onPhrases;
    if (phraseItems) phraseItems.hidden = !onPhrases;
    if (exportButton) {
      exportButton.textContent = onPhrases ? "Export these phrases" : "Export these words";
    }
    renderEmpty();
  }

  var lastWords = 0;
  var lastPhrases = 0;

  function renderEmpty() {
    var onPhrases = prefs.listTab === "phrases";
    if (wordsEmpty) wordsEmpty.hidden = onPhrases || lastWords > 0;
    if (phrasesEmpty) phrasesEmpty.hidden = !onPhrases || lastPhrases > 0;
    // Nothing to hand over is not worth offering.
    if (exportButton) exportButton.disabled = (onPhrases ? lastPhrases : lastWords) === 0;
  }

  function renderList() {
    renderStats();
    if (!listBox) return;
    var words = wordEntries();
    var phrases = phraseEntries();
    lastWords = words.length;
    lastPhrases = phrases.length;

    countInto(listCount, words.length, "words");
    countInto(listTabCount, words.length, "words");
    countInto(phraseCount, phrases.length, "phrases");
    label(wordsLabel, words.length, "word");
    label(document.getElementById("list-tab-label"), words.length, "word");
    label(phrasesLabel, phrases.length, "phrase");

    if (listTabPhrases) {
      listTabPhrases.hidden = phrases.length === 0;
      listTabPhrases.textContent = phrases.length
        ? " · " + phrases.length + (phrases.length === 1 ? " phrase" : " phrases")
        : "";
    }

    fill(listItems, words);
    fill(phraseItems, phrases);
    renderEmpty();
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

  // How well you know this word, and what you want it to say. The same control serves
  // the card, the list beside the text and the words page, so the three never drift.
  // Setting a level from the keyboard, on whichever word the card is open for. Does the
  // same as pressing the button: the card is rebuilt rather than patched, so every
  // control in it agrees about which level is now set.
  var KEYED_STATUS = { 1: 1, 2: 2, 3: 3, k: KNOWN, i: IGNORED };

  // How to set a level on the phrase card while it is open. A phrase is saved by its
  // offsets into one sentence and a word by its lemma, so the two cards cannot share a
  // path — they share the keys instead. Set by `showPick`, cleared when it closes.
  var pickLevel = null;

  function markLookedUp(key) {
    // Asked of the object's own keys: `KEYED_STATUS["constructor"]` is a function, and
    // every other key on the page would have gone through this branch holding one.
    if (!Object.prototype.hasOwnProperty.call(KEYED_STATUS, key)) return false;
    var status = KEYED_STATUS[key];

    // Whichever card is open. The word card wins if somehow both are.
    if (lookedUp && card && !card.hidden) {
      var index = parseInt(lookedUp.getAttribute("data-lemma"), 10);
      if (!lemmas[index]) return false;
      setStatus(index, bareSurface(lookedUp), levelOf(lookedUp), status);
      var word = lookedUp;
      redraw();
      // `redraw()` rebuilds the spans, so the element the card was opened for is gone.
      // Find its replacement by lemma in the same sentence rather than holding a
      // reference to a node that is no longer in the page.
      var pair = word.closest ? word.closest(".pair") : null;
      var again =
        pair && pair.parentNode
          ? pair.querySelector('.w[data-lemma="' + index + '"]')
          : null;
      if (again) showCard(again);
      else hideCard();
      return true;
    }

    if (pickLevel && chip && !chip.hidden) {
      pickLevel(status);
      return true;
    }
    return false;
  }

  function statusRow(index, surface, band) {
    var lemma = lemmas[index];
    return TargumVocab.editor({
      status: statusOf(lemma),
      note: noteOf(lemma),
      onStatus: function (value) {
        setStatus(index, surface, band, value === null ? statusOf(lemma) : value);
        redraw();
        // Rebuilt rather than patched, so every button in the row agrees about which
        // one is now set.
        if (lookedUp) showCard(lookedUp);
      },
      onNote: function (text) {
        if (text === noteOf(lemma)) return;
        // Not redrawn here: this commits on the way out of the field, and the click
        // that took focus away is usually a level button that has not fired yet.
        setNote(index, surface, band, text);
      },
    });
  }

  // The bare surface of the word that was tapped, whichever cell it was tapped in.
  function bareSurface(word) {
    var pair = word.closest ? word.closest(".pair") : null;
    var span = (word.getAttribute("data-bare") || "").split(",");
    if (!pair || span.length !== 2) return word.textContent;
    var text = segmentText(pair.getAttribute("data-id"));
    return text.slice(parseInt(span[0], 10), parseInt(span[1], 10)) || word.textContent;
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

    // Two different things. The card shows the word as it sits on the page, points and
    // all, because that is what was tapped; the list stores the bare form, so the same
    // word kept with the vowels showing and without is one entry rather than two.
    var shown = word.textContent;
    var surface = bareSurface(word);

    // The word you tapped, then its dictionary form, labelled. Leading with the
    // dictionary form alone meant tapping הציפור answered ציפור with no explanation of
    // why the answer was a different word.
    var head = document.createElement("bdi");
    head.className = "lemma";
    head.setAttribute("lang", language);
    head.textContent = shown;
    card.appendChild(head);

    if (lemma !== surface.toLowerCase() && lemma !== surface) {
      var form = document.createElement("span");
      form.className = "form";
      form.appendChild(document.createTextNode("dictionary form "));
      var bdi = document.createElement("bdi");
      bdi.setAttribute("lang", language);
      bdi.textContent = lemma;
      form.appendChild(bdi);
      card.appendChild(form);
    }

    // A Hebrew verb, taken apart. This is the half of the card that costs nothing and
    // never leaves the machine: the binyan is what the lemmatizer already worked out,
    // and the root follows from it. Where the root could not be had honestly the
    // binyan still shows on its own, and Pealim answers the rest.
    var root = roots[index];
    var binyan = binyanim[index];
    if (root || binyan) {
      var verb = document.createElement("span");
      verb.className = "verb";
      if (root) {
        verb.appendChild(document.createTextNode("root "));
        var shoresh = document.createElement("bdi");
        shoresh.className = "root";
        shoresh.setAttribute("lang", language);
        // Spaced out the way a root is written, so it reads as three letters rather
        // than as a word: כ־ת־ב, not כתב.
        shoresh.textContent = root.split("").join("\u05be");
        verb.appendChild(shoresh);
      }
      if (binyan) {
        if (root) verb.appendChild(document.createTextNode(" · "));
        var built = document.createElement("bdi");
        built.setAttribute("lang", language);
        built.textContent = binyan;
        verb.appendChild(built);
      }
      var pealim = document.createElement("a");
      pealim.className = "pealim";
      pealim.href = "https://www.pealim.com/search/?q=" + encodeURIComponent(lemma);
      pealim.target = "_blank";
      pealim.rel = "noopener noreferrer";
      pealim.textContent = "conjugations";
      verb.appendChild(pealim);
      card.appendChild(verb);
    }

    var level = levelOf(word);
    if (level) {
      var tag = document.createElement("span");
      tag.className = "pos";
      tag.textContent = level;
      card.appendChild(tag);
    }

    var meaning = inTarget(document.createElement("span"));
    meaning.className = "meaning";
    var own = noteOf(lemma);
    meaning.textContent = own || glosses[index] || "";
    if (own) meaning.classList.add("mine");
    card.appendChild(meaning);

    // Nothing has been looked up for this word, so nothing is claimed about it. The
    // translation is beside the line; write down what you make of it, or ask.
    if (!own && !glosses[index]) {
      var outcome = lookup[lemma];
      if (outcome === "none") {
        // Asked and answered: there is nothing to find. Offering the button again
        // would only buy the same silence twice.
        meaning.textContent = "nothing found — write your own";
      } else {
        var ask = document.createElement("button");
        ask.type = "button";
        ask.className = "look-up";
        ask.textContent = served && passKey ? "look it up" : "nothing saved";
        ask.disabled = !(served && passKey);
        ask.onclick = function (event) {
          event.stopPropagation();
          ask.disabled = true;
          ask.textContent = "looking…";
          lookUp(index, function () {
            if (lookedUp === word) showCard(word);
          });
        };
        card.appendChild(ask);
        if (outcome) {
          var trouble = document.createElement("span");
          trouble.className = "caveat";
          trouble.textContent = outcome;
          card.appendChild(trouble);
        }
      }
    }

    card.appendChild(statusRow(index, surface, level));

    if (word.classList.contains("split")) {
      // Say so rather than presenting one reading of an ambiguous string as settled.
      var caveat = document.createElement("span");
      caveat.className = "caveat";
      caveat.textContent = "read as a prefix plus a word";
      card.appendChild(caveat);
    }
    card.hidden = false;
    placeNear(card, word.getBoundingClientRect());
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

    // A phrase picked off the pointed cell is measured in pointed characters. It is
    // stored in bare ones, so that what you kept stays put when the vowels go away
    // again — and so the same phrase saved twice, once each way, is one entry.
    var segmentId = cell.parentNode.getAttribute("data-id");
    if (cell === pointedCell[segmentId]) {
      start = toBare(segmentId, start);
      end = toBare(segmentId, end);
      if (end <= start) return null;
    }
    // Read back out of the bare text rather than taken from the selection, so what the
    // card offers and what the list keeps are the same string, and so one phrase does
    // not become two entries depending on whether the vowels were on when you dragged.
    var text = segmentText(segmentId).slice(start, end).trim();
    return {
      segmentId: segmentId,
      start: start,
      end: end,
      text: text,
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

  // A card next to the thing it is about. The word card used to sit pinned to the
  // bottom of the window wherever you tapped, so marking a word in the first line meant
  // crossing the whole page to press a button about it, and again to come back.
  function placeNear(element, rect) {
    element.hidden = false;
    element.style.translate = "0 0";
    element.style.transform = "none";
    element.style.left = "0px";
    element.style.top = "0px";

    var box = element.getBoundingClientRect();

    // Centred on the word but kept inside the window. A word near the edge of an RTL
    // page is at the right, and a card centred on it would hang off it.
    var wanted = rect.left + rect.width / 2 - box.width / 2;
    var limit = window.innerWidth - box.width - 12;
    element.style.left = Math.max(12, Math.min(wanted, limit)) + window.scrollX + "px";

    // Below where there is room, above where there is not — and never over the word
    // itself, which is the one thing you are looking at while you decide.
    var below = rect.bottom + 8;
    var room = window.innerHeight - below - 12;
    var top = box.height <= room ? below : Math.max(8, rect.top - box.height - 8);
    element.style.top = top + window.scrollY + "px";
  }

  function place(rect) {
    placeNear(chip, rect);
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

    if (parts.editor) chip.appendChild(parts.editor);

    if (parts.action) {
      var action = document.createElement("button");
      action.type = "button";
      action.className = "drop-pick";
      action.textContent = parts.action;
      action.onclick = parts.onclick;
      chip.appendChild(action);
    }
  }

  // A phrase answers the same two questions a word does. Answering either one is what
  // keeps it, so there is no separate "save" to press first.
  function phraseEditor(picked, existing, reading) {
    var list = picks[picked.segmentId];
    var pick = existing > -1 && list ? list[existing] : null;

    function ensure() {
      if (pick) return pick;
      list = picks[picked.segmentId] || (picks[picked.segmentId] = []);
      pick = stamp({
        start: picked.start,
        end: picked.end,
        text: picked.text,
        meaning: reading,
        status: TargumVocab.LEARNING[0],
        note: "",
        at: nextOrder(),
      });
      list.push(pick);
      if (listBox && listBox.hidden) showList(true);
      return pick;
    }

    // The element and the doing, separately: the keys set a level on the open card, and
    // a phrase is saved by offsets into one sentence rather than by lemma, so they
    // cannot share the word's path.
    function apply(value) {
      var item = ensure();
      if (value !== null) item.status = value;
      stamp(item);
      remember();
      redraw();
    }

    return {
      element: TargumVocab.editor({
        status: pick ? pick.status : undefined,
        note: pick ? pick.note || "" : "",
        placeholder: "Your own reading",
        onStatus: apply,
        onNote: function (text) {
          var item = ensure();
          item.note = text;
          stamp(item);
          remember();
          redraw();
        },
      }),
      apply: apply,
    };
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
      pickLevel = null;
      return;
    }
    showPick(picked);
  });

  // Built as a function rather than inline in the handler, because setting a level from
  // the keyboard has to draw the card again to show which one is now set — the editor
  // reads its pressed state once, when it is made.
  function showPick(picked) {
    var token = soleToken(picked);
    if (token) {
      var index = token[4];
      var lemma = lemmas[index];
      // Dragging across one word is not a phrase, whatever the gesture was. It gets the
      // word's own card, with the same scale and the same field as tapping it.
      var surface = segmentText(picked.segmentId).slice(token[0], token[1]);
      var band = levelNames[token[2]] || "";
      pickCard({
        title: surface,
        reading: noteOf(lemma) || glosses[index] || "",
        note: lemma && lemma !== surface ? "dictionary form " + lemma : "",
        editor: statusRow(index, surface, band),
      });
      place(picked.rect);
      pickLevel = function (status) {
        setStatus(index, surface, band, status);
        redraw();
        showPick(picked);
      };
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
    var editing = phraseEditor(picked, existing, reading);
    pickCard({
      title: picked.text,
      reading: reading,
      note: whole
        ? "the whole sentence"
        : reading
          ? "word by word — the sentence is in parallel"
          : "",
      editor: editing.element,
      action: existing > -1 ? "take it off the list" : "",
      onclick: function () {
        var list = picks[picked.segmentId] || (picks[picked.segmentId] = []);
        if (existing > -1) {
          if (window.TargumSync) window.TargumSync.forgetPhrase(list[existing].id);
          list.splice(existing, 1);
          if (!list.length) delete picks[picked.segmentId];
        } else {
          list.push(stamp({
            start: picked.start,
            end: picked.end,
            text: picked.text,
            meaning: reading,
            // Kept at the first level, like a word dragged over rather than tapped.
            status: TargumVocab.LEARNING[0],
            note: "",
            at: nextOrder(),
          }));
          if (listBox && listBox.hidden) showList(true);
        }
        remember();
        if (window.getSelection) window.getSelection().removeAllRanges();
        chip.hidden = true;
        pickLevel = null;
        redraw();
      },
    });
    place(picked.rect);
    pickLevel = function (status) {
      editing.apply(status);
      showPick(picked);
    };
  }

  /* --- export -------------------------------------------------------------- */

  /* A spreadsheet runs a cell that opens with =, +, - or @ as a formula, so an export
     is a way to hand somebody a file that does something when they open it. The leading
     apostrophe is what marks the rest as text; it is visible, which is the price of the
     file being inert. Everything else is left exactly as the reader wrote it. */
  function csvCell(value) {
    var text = value === undefined || value === null ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  var STATUS_NAMES = { 1: "just met", 2: "getting there", 3: "nearly there" };
  STATUS_NAMES[KNOWN] = "known";
  STATUS_NAMES[IGNORED] = "ignored";

  function download(name, header, rows) {
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
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  function title() {
    return (documentTitle || document.title || "targum")
      .replace(/[^\w\u0080-\uffff -]+/g, "")
      .trim();
  }

  // Two lists, two files. Mixing them meant one column existed only to say which of
  // the two each row was, and neither could be opened as what it is.
  //
  // Both are this text's, matching what the panel shows. Your whole vocabulary in a
  // language is a different export and lives on the library page, where the library is.
  function exportWords() {
    download(
      title() + " — words.csv",
      ["word", "dictionary form", "difficulty", "how well", "meaning"],
      wordEntries().map(function (entry) {
        return [
          entry.term,
          entry.lemma,
          entry.level || "",
          STATUS_NAMES[entry.status] || "",
          entry.meaning || "",
        ];
      })
    );
  }

  function exportPhrases() {
    download(
      title() + " — phrases.csv",
      ["phrase", "reading"],
      phraseEntries().map(function (entry) {
        return [entry.term, entry.meaning || ""];
      })
    );
  }

  function exportCsv() {
    if (prefs.listTab === "phrases") exportPhrases();
    else exportWords();
  }

  /* --- type and mode ------------------------------------------------------- */

  function applyType() {
    prefs.size = Math.min(1.75, Math.max(0.875, prefs.size));
    root.style.setProperty("--size", prefs.size + "rem");
    root.style.setProperty("--leading", prefs.leading);
    // Hebrew and Arabic keep their extra room as the leading moves.
    root.style.setProperty("--leading-rtl", (prefs.leading + 0.2).toFixed(2));
  }

  // A cycle rather than a one-way increase, but one that includes the default and
  // returns to it. The old step landed on 1.5 and then climbed past the setting it
  // started from, so there was no way back to the spacing the page shipped with.
  var LEADINGS = [1.5, 1.75, 2.0, 2.25];

  function nextLeading(current) {
    for (var i = 0; i < LEADINGS.length; i++) {
      if (current < LEADINGS[i] - 0.01) return LEADINGS[i];
    }
    return LEADINGS[0];
  }

  var modes = document.getElementById("modes");
  var slide = modes ? modes.querySelector(".slide") : null;
  // What the page was last marked up for. Only a move into or out of interlinear
  // changes the words themselves; parallel and source only move columns.
  var drawnFor = null;

  function placeSlide() {
    if (!modes || !slide) return;
    var active = modes.querySelector("[data-mode].on");
    if (!active) return;
    var group = modes.getBoundingClientRect();
    var button = active.getBoundingClientRect();
    if (!button.width) return;
    slide.style.width = button.width + "px";
    slide.style.transform =
      "translateX(" + (button.left - group.left - modes.clientLeft) + "px)";
    if (!modes.classList.contains("ready")) {
      // Commit the first position with the transition still off, or the pill slides in
      // from the edge of the control the moment the page opens.
      void modes.offsetWidth;
      modes.classList.add("ready");
    }
  }

  function applyMode() {
    body.className = body.className.replace(/\bmode-\w+/g, "").trim();
    body.classList.add("mode-" + prefs.mode);
    Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (button) {
      button.classList.toggle("on", button.getAttribute("data-mode") === prefs.mode);
    });
    placeSlide();
    hideCard();
    if (interlinear() !== (drawnFor === "inter")) redraw();
    drawnFor = prefs.mode;
  }

  // The whole page moves when the mode changes. Settling it back in reads as one
  // movement instead of a jump, and costs nothing when it is not wanted.
  function settle() {
    if (!main) return;
    main.classList.remove("settled");
    void main.offsetWidth;
    main.classList.add("settled");
  }

  window.addEventListener("resize", placeSlide);
  window.addEventListener("scroll", catchUp, { passive: true });
  // A wider window shows pairs that were not on screen a moment ago.
  window.addEventListener("resize", catchUp);

  // Vowel points off by default, in every text. A pointed source is shown bare until
  // asked otherwise, which is the same offer made to an unpointed one.
  function applyNikkud() {
    if (prefs.nikkudBy && documentId) prefs.nikkudBy[documentId] = !!prefs.nikkud;
    body.classList.toggle("nikkud", !!prefs.nikkud);
    Array.prototype.forEach.call(document.querySelectorAll("[data-nikkud]"), function (button) {
      var on = button.getAttribute("data-nikkud") === "on";
      button.classList.toggle("on", on === !!prefs.nikkud);
    });
    hideCard();
    redraw();
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

  /* --- keyboard help ------------------------------------------------------- */

  // Eight single keys did things and nothing on the page said so, including the arrows,
  // which stop scrolling the moment this file loads.
  var keysCard = document.getElementById("keys");

  function showKeys(open) {
    if (!keysCard) return;
    keysCard.hidden = !open;
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
      var whichList = button.getAttribute("data-list");
      if (whichList) {
        showTab(whichList);
        save();
        return;
      }
      if (button.hasAttribute("data-keys")) {
        showKeys(keysCard ? keysCard.hidden : false);
        return;
      }
      if (button.hasAttribute("data-marking")) {
        prefs.marking = !prefs.marking;
        applyMarking();
        save();
        return;
      }
      var mode = button.getAttribute("data-mode");
      if (mode) {
        if (mode === prefs.mode) return;
        prefs.mode = mode;
        applyMode();
        settle();
        save();
        return;
      }
      var nikkud = button.getAttribute("data-nikkud");
      if (nikkud) {
        prefs.nikkud = nikkud === "on";
        applyNikkud();
        save();
        return;
      }
      var action = button.getAttribute("data-type");
      if (action === "larger") prefs.size += 0.0625;
      if (action === "smaller") prefs.size -= 0.0625;
      if (action === "looser") prefs.leading = nextLeading(prefs.leading);
      if (action) {
        applyType();
        placeSlide();
        save();
      }
      return;
    }

    // A word answers the same way whichever mode you are in. Marking changes what the
    // page shows you, never what it lets you do — you have to be able to mark a word to
    // clear it, and the whole point of the mode is clearing them.
    var word = event.target.closest ? event.target.closest(".w") : null;
    if (word) {
      showCard(word);
      return;
    }
    hideCard();
    showKeys(false);
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

    // While a word card is open the number and letter keys belong to it. `k` and `i`
    // already mean previous-sentence and interlinear, and they still do the moment the
    // card is closed — the card is the only thing that borrows them.
    if (markLookedUp(event.key)) {
      event.preventDefault();
      return;
    }

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
        settle();
        save();
        return;
      case "o":
        prefs.mode = "source";
        applyMode();
        settle();
        save();
        return;
      case "i":
        prefs.mode = "inter";
        applyMode();
        settle();
        save();
        return;
      case "t":
        // Not stored and not a preference: a question you ask once.
        showTimings(!readout || readout.hidden);
        return;
      case "m":
        prefs.marking = !prefs.marking;
        applyMarking();
        save();
        return;
      case "s":
        if (listBox) showList(!!listBox.hidden);
        return;
      case "n":
        if (!hasNikkud) return;
        prefs.nikkud = !prefs.nikkud;
        applyNikkud();
        save();
        return;
      case "?":
        showKeys(keysCard ? keysCard.hidden : false);
        return;
      case "Escape":
        hideCard();
        showKeys(false);
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
    if (served && passKey) {
      // The link says Library, so it goes to the library — not the start page.
      home.href = keyed("/");
      home.hidden = false;
      // Section-to-section links are relative and would drop the key, and with it
      // access: the next chapter would answer 403.
      var carried = document.querySelectorAll(".pager a, .bar-title .up");
      Array.prototype.forEach.call(carried, function (link) {
        var href = link.getAttribute("href");
        if (href && href.indexOf("?") === -1) {
          link.setAttribute("href", keyed(href));
        }
      });
    }
  }

  /* --- word meanings, once they arrive ------------------------------------- */

  // The reader opens as soon as there is something worth reading, which is before the
  // word meanings have been looked up: those are most of the calls a build makes and
  // none of what you need to start. They are fetched afterwards and filled in around
  // you, with no reload and nothing moving in the sentence you are on.
  var MEANINGS_FIRST_WAIT = 3000;
  var MEANINGS_MAX_WAIT = 10000;
  var MEANINGS_GIVE_UP = 10 * 60 * 1000;

  function buildFolder() {
    // A served reader lives at /reader/<folder>/reader/<page>.html, so its own address
    // says which build it belongs to and nothing has to be shipped in the payload.
    var parts = location.pathname.split("/");
    return parts.length > 2 && parts[1] === "reader" ? decodeURIComponent(parts[2]) : "";
  }

  function takeMeanings(entries) {
    var found = false;
    var complete = true;
    var filled = lemmas.map(function (lemma) {
      var meaning = entries[lemma] || "";
      if (meaning) found = true;
      else complete = false;
      return meaning;
    });
    if (!found) return false;
    glosses = filled;
    // Decides between an empty meaning and "no meaning recorded", so it has to move too.
    hasGloss = true;

    // A word kept before the meanings arrived holds an empty one: setStatus copies the
    // meaning in at the moment you save it, so those entries would stay blank for good.
    var changed = false;
    lemmas.forEach(function (lemma, index) {
      if (vocab[lemma] && !vocab[lemma].meaning && glosses[index]) {
        vocab[lemma].meaning = glosses[index];
        changed = true;
      }
    });
    if (changed) remember();

    renderList();
    // And the card, if one happens to be open on the word that just gained a meaning.
    if (lookedUp) showCard(lookedUp);
    // The file is written a batch at a time, so the first answer is usually a partial
    // one. Stopping there would leave most of the page's words permanently blank.
    return complete;
  }

  function waitForMeanings() {
    var folder = buildFolder();
    if (!served || !passKey || !folder) return;
    if (!lemmas.length || hasGloss) return;
    // Nothing was bought for this text, so nothing is coming. Words are looked up one
    // at a time from the card instead, and asking every few seconds for ten minutes
    // would be asking for a file that is never going to be written.
    if (!data.glossPending) return;

    var wait = MEANINGS_FIRST_WAIT;
    var giveUpAt = Date.now() + MEANINGS_GIVE_UP;
    meaningsPending = true;

    function stop() {
      meaningsPending = false;
      if (lookedUp) showCard(lookedUp);
    }

    function ask() {
      if (Date.now() > giveUpAt) return stop();
      fetch(keyed("/glossary/" + encodeURIComponent(folder)), {
        headers: keyHeaders(),
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (answer) {
          if (answer && answer.ready && answer.entries && takeMeanings(answer.entries)) {
            return stop();
          }
          wait = Math.min(wait * 1.5, MEANINGS_MAX_WAIT);
          setTimeout(ask, wait);
        })
        .catch(function () {
          // The server has stopped. There is nothing left to wait for, and the reader
          // keeps working exactly as it is.
          stop();
        });
    }
    setTimeout(ask, wait);
  }

  if (timing) {
    requestAnimationFrame(function () {
      took(
        "first frame — " +
          document.querySelectorAll(".w").length +
          " words drawn, " +
          document.querySelectorAll(".w[data-status]").length +
          " of them marked"
      );
    });
  }

  applyType();
  applyMode();
  applyMarking();
  showList(prefs.list === null ? roomy.matches : prefs.list, prefs.list === null ? false : true);
  // A remembered preference for vowels is worth nothing on a text that has none, and
  // leaving it set would hide every sentence on the page.
  if (!hasNikkud) {
    prefs.nikkud = false;
  } else {
    var chosen = prefs.nikkudBy ? prefs.nikkudBy[documentId] : undefined;
    prefs.nikkud = chosen === undefined ? !!data.sourcePointed : !!chosen;
  }
  applyNikkud();
  took("marks drawn on what is on screen");
  showTab(prefs.listTab);
  waitForMeanings();
  took("reader.js finished; the browser now lays the page out");

  /* --- the account, if there is one ----------------------------------------- */

  // The page has already drawn itself from the browser's own store by now, which is
  // what keeps it instant and what keeps it working with no account at all. If the
  // account then turns out to hold something this browser did not have, the store is
  // re-read and the marks are drawn again — a few milliseconds later, and only when
  // something actually arrived.
  if (served && window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      took("the account answered" + (changed ? "" : ", with nothing new"));
      if (!changed) return;
      vocab = read(VOCAB, "{}");
      picks = read(PICKED, "{}");
      redraw();
      took("marks redrawn from the account");
    });
    window.TargumSync.start();
  }
})();

/* --- the next chapter, bought before it is needed ---------------------------
 *
 * A book is paid for a chapter at a time. Waiting until somebody finishes one puts a
 * minute of dead time at every boundary — translating a chapter takes well under a
 * minute and reading one takes ten — so the next is started once they are most of the
 * way through this one. Nothing is bought from a reader who leaves early, and nobody
 * waits at the turn of a page.
 */
(function () {
  "use strict";
  if (location.protocol === "file:") return;

  var pager = document.querySelector(".pager[data-chapter]");
  var link = pager && pager.querySelector("[data-next]");
  // Its own, because this is its own scope: it read `passKey` and called `keyed` across
  // the boundary, and neither was ever in reach.
  var key = new URLSearchParams(location.search).get("k");
  if (!link || !key) return;

  function keyed(path) {
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    head["X-Targum-Key"] = key;
    return head;
  }

  // The path is /reader/<folder>/reader/<file>: the route prefix and the folder inside
  // the build are both called "reader", so it is the *last* one the name sits before.
  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  // Far enough in that they are reading it rather than glancing at it.
  var ENOUGH = 0.6;
  var asked = false;

  function through() {
    var height = document.documentElement.scrollHeight - window.innerHeight;
    return height > 0 ? window.scrollY / height : 1;
  }

  function maybe() {
    if (asked || through() < ENOUGH) return;
    asked = true;
    window.removeEventListener("scroll", maybe);
    fetch(keyed("/chapter"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name: name, number: Number(link.getAttribute("data-next")) }),
    }).catch(function () {});
  }

  window.addEventListener("scroll", maybe, { passive: true });
  maybe();
})();
