/* Started once the durable store has put back what this browser kept — see
   durable.js. On `file://` the copy `localStorage` holds can be one version behind,
   and everything below reads it: the place, the vocabulary, the preferences, the
   theme. The whole file waits rather than the first block of it, because the player
   and the rest are their own closures and read the same store.

   One local read, and it gives up after half a second — a store that will not answer
   costs a beat, not a reader. */
var targumReader = function () {
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

  // Whether the server will answer a question that costs something — a word looked
  // up, a glossary waited for. The start-up key says yes on a machine somebody runs
  // themselves. Hosted there is no key: the session cookie is what lets the request
  // through, and a page cannot read that cookie, so it asks the sync layer, which has
  // already asked the server who is signed in. Gated on the key alone, the live site
  // drew every look-up button disabled, and Enter looked nothing up.
  function canAsk() {
    return served && !!(passKey || (window.TargumSync && window.TargumSync.who));
  }

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
  // What this language knows about its dictionary forms beyond what every language
  // carries: tables parallel to the lemmas, named for the fact. Only the Hebrew ones are
  // drawn here; a table this reader does not know is left alone.
  var extensions = data.extensions || {};
  var roots = extensions.roots || [];
  var binyanim = extensions.binyanim || [];
  // Which Hebrew each dictionary form belongs to, where its two registers disagree, and
  // which one this text is written in. Codes, not sentences: the words are in
  // `registerLine`, so rewriting them costs nothing and re-annotating a library is not
  // part of it.
  var registers = data.registers || [];
  var sourceRegister = data.sourceRegister || "";
  // Absent in every reader with no Hebrew in it, and in one built before there was
  // anything to read the vowels with.
  var sounds = data.sounds || [];
  // How split words are put together and how each occurrence is conjugated or declined
  // — tables of distinct strings, like the sounds, with an index on each token. Absent
  // on annotations written before they existed, and the card then simply says less.
  var builts = data.built || [];
  var grammarTable = data.grammar || [];
  // A verb's citation form and a noun's lying plural, parallel to the lemmas. Facts
  // about the source word, so one table serves every target language — and grown at
  // runtime as words are looked up, since most texts were glossed before they existed.
  var citations = data.citations || [];
  var plurals = data.plurals || [];
  // What the words mean, per target language: `{ en: [...], ru: [...] }`, each table
  // parallel to `lemmas`. A meaning is written in one language and a text may carry a
  // translation into two, so there is no such thing as "the" meaning of a word here —
  // only the meaning in the language the reader is reading it in. `glosses` below is
  // whichever of these the translation on show calls for.
  var glossesBy = data.glosses || {};
  var levelNames = data.levelNames || {};
  // True while the meanings are still being looked up, so a word with no meaning yet
  // can say which of the two it is: not looked up yet, or looked up and not found.
  var meaningsPending = false;

  /* --- which language this is being read in --------------------------------
   *
   * The source language is on `<html lang>` and never changes. The target does: a
   * reader can hold an English translation and a Russian one and switch between them,
   * and everything that is a language pair rather than a language follows that switch —
   * the meanings on the cards, the meanings in the list, which glossary is polled for,
   * and which language a word is looked up in.
   *
   * These were read off the first `.tr` cell in the page, a thousand lines below the
   * first use, and they described `translations[0]` for ever after. `lookUp` read the
   * target 1,249 lines before it was assigned and worked only because `var` hoists.
   */
  var targetLanguage = "";
  var targetDirection = "";
  var glosses = [];
  // Which of the translations is on show. The page opens on the first one.
  var showing = "t0";

  function useTarget(id) {
    showing = id;
    var entry = translationData[id] || {};
    targetLanguage = entry.language || "";
    targetDirection = entry.direction || "";
    // A copy, because `lookUp` and `takeMeanings` write into it and the payload's own
    // table is the answer for this language rather than a scratch pad.
    glosses = (glossesBy[targetLanguage] || []).slice();
  }

  // Anything shown in the language being read into. A card is chrome and runs left to
  // right, but the text inside it belongs to whichever language it came from, or an
  // English sentence on a Hebrew page loses its full stop to the wrong end of the line.
  function inTarget(element) {
    if (targetLanguage) element.setAttribute("lang", targetLanguage);
    if (targetDirection) element.setAttribute("dir", targetDirection);
    return element;
  }

  // Each sentence ships bare and pointed — pointed meaning everything the edition wrote,
  // accents included — so both go through the server's bidi isolation and neither has to
  // be rebuilt here. Only one is ever on show.
  //
  // Scripture ships a third: the vowels without the chanting marks. It is not a middle
  // step in the vowel switch, which is what it was the first time and why it went; it is
  // its own two-position control, because the te'amim are what somebody preparing to
  // leyn came for and clutter for everybody else. Every other text has two cells and
  // never sees it. See `shownCell`.
  var FORMS = ["plain", "pointed", "unaccented"];
  var cells = { plain: {}, pointed: {}, unaccented: {} };
  // The pair a segment is drawn in. The word queue works in segment ids, because the
  // words themselves are data rather than page, and this is the one place it has to come
  // back to the page — to draw a pair's spans and to scroll to it.
  var pairBySegment = {};
  pairs.forEach(function (pair) {
    var segmentId = pair.getAttribute("data-id");
    for (var f = 0; f < FORMS.length; f++) {
      cells[FORMS[f]][segmentId] = pair.querySelector(".src." + FORMS[f]);
    }
    pairBySegment[segmentId] = pair;
  });
  function anyCell(form) {
    return Object.keys(cells[form]).some(function (id) {
      return !!cells[form][id];
    });
  }
  var hasNikkud = anyCell("pointed");
  var hasTaamim = anyCell("unaccented");

  // Which form a segment is actually showing. A pair the vocalizer never reached has no
  // pointed cell, and it keeps showing the bare one while the rest of the page is
  // pointed. The accents come off inside the pointed position rather than beside it: a
  // reader who has turned the vowels off has nothing to take the accents from.
  function shownCell(segmentId) {
    if (!prefs.nikkud) return cells.plain[segmentId];
    if (!prefs.taamim && cells.unaccented[segmentId]) return cells.unaccented[segmentId];
    return cells.pointed[segmentId] || cells.plain[segmentId];
  }

  // A word's span, looked for in the cell that is showing and nowhere else. A pair holds
  // up to three cells and `pair.querySelector` answers with the first in document order,
  // which is the bare one — hidden, and still holding the spans from the last time it
  // was up. The arrows then stood on a word nobody could see. The forms cycle through
  // bare as a matter of course now, so this is the ordinary case, not a corner.
  function wordIn(pair, selector) {
    var cell = shownCell(pair.getAttribute("data-id"));
    return cell ? cell.querySelector(selector) : null;
  }

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
    // Which translation you chose, per text. It was one id for every text, and an id is
    // a position: `t1` is a Russian machine translation in one book and a published
    // English one in the next, so one remembered choice put a reader in a language they
    // had picked somewhere else entirely. Per document, the way the vowels already are.
    translationBy: {},
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
    // The chanting marks, on scripture that carries them. On by default and everywhere:
    // they are in the text the edition wrote, and taking them out is the departure. Not
    // per document, unlike the vowels — whether you read te'amim is a fact about you.
    taamim: true,
    // Pages, or one long scroll. Pages: the first alpha reader asked twice — "I get
    // tired from reading and want logical places to stop" — and a page is a place to
    // stop. A preference, because a paragraph taller than a phone's window fits on
    // no page and that page has to scroll, which is more forgivable inside a mode
    // somebody can leave than as the reader everybody gets.
    paged: true,
    // Where you were, per chapter: the first sentence of the page you were on. A page
    // number would be wrong after the type grows or the window turns.
    pageBy: {},
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
  // 3: pages, for every browser that had a preference from before there were pages.
  // 4: pages again, on a phone. A phone that scrolls is one where somebody pressed the
  // button — and until the bar was one row it sat in a bar that wrapped to four, an
  // inch from the text, where it was pressed by readers who did not know it was a
  // button. Handed back once, under 60rem only: a choice made on a wide window was
  // made in a bar with room, and stands.
  var DEFAULTS = 4;
  var RESET = { marking: true, paged: true };

  try {
    var stored = JSON.parse(localStorage.getItem(STORE) || "{}");
    for (var key in stored) if (key in prefs) prefs[key] = stored[key];
  } catch (e) {}

  // A switch: on or off. For a day it was a step, 0 to 2, and a browser that opened a
  // text that day holds a number here. `!!` reads any of them the way they were meant —
  // 0 was off and 1 and 2 were both the pointed text — so nobody is reset and no
  // per-document choice is lost.
  prefs.nikkud = !!prefs.nikkud;
  for (var doc in prefs.nikkudBy) prefs.nikkudBy[doc] = !!prefs.nikkudBy[doc];
  // Absent in every browser that read a text before scripture had the switch, and the
  // accents are what the edition wrote, so absent means on.
  prefs.taamim = prefs.taamim === undefined ? true : !!prefs.taamim;

  if ((prefs.defaults || 0) < DEFAULTS) {
    // Generations 1 to 3 reset everybody; 4 is the phone's alone.
    if ((prefs.defaults || 0) < 3) for (var changed in RESET) prefs[changed] = RESET[changed];
    if (window.matchMedia && window.matchMedia("(max-width: 60rem)").matches) prefs.paged = true;
    prefs.defaults = DEFAULTS;
    save();
  }

  function save() {
    try {
      targumKeep(STORE, JSON.stringify(prefs));
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

  // What the card calls a level: 1, 2, 3, known, ignore.
  function stepLabel(status) {
    var steps = (window.TargumVocab && window.TargumVocab.STEPS) || [];
    for (var i = 0; i < steps.length; i++) {
      if (steps[i].value === status) return steps[i].label;
    }
    return status;
  }

  // When you last had this text open, so the library can put what you are part way
  // through at the top.
  //
  // And the day itself, which is the whole of "12 days reading" on the progress page.
  // `targum:opened` cannot answer that question — it holds one stamp per text and
  // overwrites it on every open, so yesterday is gone the moment you come back. This is
  // a set, and the only thing that writes to it is this line: a day is a day you opened
  // a text, not a day you marked a word, and dressing one up as the other would make the
  // number a claim nobody could check.
  //
  // The reader's own local midnight rather than UTC, because "did I read yesterday" is a
  // question about their evening. Built from the parts rather than sliced off an ISO
  // string, which is UTC and lands on the wrong day either side of midnight.
  try {
    var opened = JSON.parse(localStorage.getItem("targum:opened") || "{}");
    opened[documentId] = Date.now();
    targumKeep("targum:opened", JSON.stringify(opened));

    var now = new Date();
    var today =
      now.getFullYear() +
      "-" +
      String(now.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(now.getDate()).padStart(2, "0");
    var days = JSON.parse(localStorage.getItem("targum:days") || "{}");
    if (!days[today]) {
      days[today] = 1;
      targumKeep("targum:days", JSON.stringify(days));
      // Signed in, this reaches the account a moment later; signed out it is a no-op.
      if (window.TargumSync) window.TargumSync.touched();
    }
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

  // Shared with the words page, which has to be able to run it too. `data.moves` is this
  // text's own lemma renames, and only a text can carry them — the words page has no
  // annotation behind it and so passes none.
  if (window.TargumVocab) window.TargumVocab.migrate(language, documentId, data.moves);

  var vocab = read(VOCAB, "{}");
  var picks = read(PICKED, "{}");

  /* --- what words mean, in the language you read them in ---------------------
   *
   * A word belongs to a language; a meaning belongs to a language pair. Hebrew ספר is
   * one word whether it was met on an English page or a Russian one — one entry in the
   * vocabulary, one level, one line in every count — but "book" and "книга" are two
   * different facts, and handing a reader the wrong one is worse than handing them
   * nothing. So the status lives with the word and the meaning lives here, under the
   * pair it was written for.
   *
   * The answer is also bought once and then belongs to this browser. It used to live in
   * the page and no further, so every reload asked the server the same question about
   * the same word and the reader met the "look it up" button on a word they had already
   * looked up.
   *
   * Shared by every text in the pair: meeting a word again in the next article, already
   * answered, is the whole point of having asked. Kept apart from the vocabulary because
   * asking what a word means and deciding you know it are different acts — and because
   * one of them is about a pair of languages and the other is not.
   */
  var meaningStores = {};

  function meaningsFor(target) {
    var into = target || targetLanguage;
    if (!into) return null;
    if (!meaningStores[into]) {
      meaningStores[into] = { name: "targum:meanings:" + language + ":" + into, records: null };
    }
    var store = meaningStores[into];
    if (store.records === null) store.records = read(store.name, "{}");
    return store;
  }

  // A dictionary form, or `phrase:<id>` for the reading of a phrase. One store rather
  // than two: both are the same fact about the same pair, and `targum:gone` already
  // namespaces the two kinds this way.
  function meaningRecord(term, target) {
    var store = meaningsFor(target);
    return (store && store.records[term]) || null;
  }

  function meaningOf(term, target) {
    var record = meaningRecord(term, target);
    return (record && record.meaning) || "";
  }

  function noteOn(term, target) {
    var record = meaningRecord(term, target);
    return (record && record.note) || "";
  }

  // Written whole, the way a word record is, so the account's merge has one `seen` to
  // compare and cannot take half of an edit.
  function writeMeaning(term, changes, target) {
    var store = meaningsFor(target);
    if (!store) return;
    var was = store.records[term] || {};
    var now = {
      meaning: changes.meaning === undefined ? was.meaning || "" : changes.meaning,
      note: changes.note === undefined ? was.note || "" : changes.note,
      at: was.at || nextOrder(),
      seen: Date.now(),
    };
    if (!now.meaning && !now.note) delete store.records[term];
    else store.records[term] = now;
    try {
      targumKeep(store.name, JSON.stringify(store.records));
    } catch (e) {}
    if (window.TargumSync) window.TargumSync.touched();
  }

  function keepMeaning(term, meaning, target) {
    if (meaning && meaning !== meaningOf(term, target)) {
      writeMeaning(term, { meaning: meaning }, target);
    }
  }

  // A phrase's reading and your note on it go in the same store, under the phrase's own
  // id. The same fact about the same pair — the sentence it was cut from is the source's
  // and does not move, but what it says in English and what it says in Russian are two
  // answers — and one store to keep rather than two.
  //
  // The id is minted here rather than lazily by the sync, because a phrase that has a
  // meaning needs a name to file it under at that moment, not at the next sign-in.
  function phraseTerm(pick) {
    if (!pick.id) {
      pick.id = "p" + (pick.at || Date.now()) + "-" + Math.random().toString(36).slice(2, 8);
    }
    return "phrase:" + pick.id;
  }

  // Folded into the page's own table so nothing downstream has to know there are two
  // sources: `glosses` stays the one answer to what this page knows a word means,
  // whether the build shipped it or the reader asked for it a fortnight ago.
  function foldMeanings() {
    var store = meaningsFor();
    if (!store) return;
    lemmas.forEach(function (lemma, index) {
      if (!glosses[index] && store.records[lemma]) {
        glosses[index] = store.records[lemma].meaning || "";
      }
    });
  }

  function remember() {
    try {
      targumKeep(VOCAB, JSON.stringify(vocab));
      targumKeep(PICKED, JSON.stringify(picks));
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
    var was = all[documentId] || {};
    all[documentId] = {
      title: documentTitle,
      language: language,
      updated: Date.now(),
      // Kept across every rewrite of the record: finishing a text is the one thing
      // here the reader said outright.
      done: was.done || 0,
    };
    try {
      targumKeep(DOCS, JSON.stringify(all));
    } catch (e) {}
  }

  // Finished with this text, said once at the foot of its last part. Pressing again
  // takes it back, so a text is finished once however often the button is pressed —
  // and the count on the progress page can only ever move by one.
  var finishedBox = document.getElementById("finished");
  var finishedMark = document.getElementById("done-mark");
  var finishedSaid = document.getElementById("done-said");

  function finishedAt() {
    var record = read(DOCS, "{}")[documentId];
    return record ? Number(record.done || 0) : 0;
  }

  function setFinished(on) {
    var all = read(DOCS, "{}");
    var record = all[documentId] || {};
    // Said every time, not only on a fresh record. A record can be born nameless —
    // the sync sweeps opened texts before a word is kept, and a row made that way
    // has no language — and the progress page drops a finish it cannot place, so
    // the celebration said "your 1st" while the ledger said 0. This page knows who
    // it is; the record is told so whenever it is touched.
    record.title = documentTitle || record.title || "";
    record.language = language || record.language || "";
    record.done = on ? Date.now() : 0;
    record.updated = Date.now();
    all[documentId] = record;
    try {
      targumKeep(DOCS, JSON.stringify(all));
    } catch (e) {}
    if (window.TargumSync) window.TargumSync.touched();
    renderFinished();
    say(on ? "Finished. It counts on your progress page." : "Not finished.");
  }

  // How many texts this reader has finished, in every language: the number the
  // celebration brags with. One record per text, so one at most each.
  function finishedCount() {
    var all = read(DOCS, "{}");
    var count = 0;
    Object.keys(all).forEach(function (hash) {
      if (all[hash] && all[hash].done) count += 1;
    });
    return count;
  }

  function ordinal(n) {
    var rest = n % 100;
    if (rest >= 11 && rest <= 13) return n + "th";
    return n + (["th", "st", "nd", "rd"][n % 10] || "th");
  }

  // Finished: the strip inverts to ink — §9's wake-up move, spent on the one block
  // that earned it — and brags the brand's way: a real count, in serif tabular figures,
  // leaf-bright on ink. Type, not motion.
  function renderFinished() {
    if (!finishedBox || !finishedMark || !finishedSaid) return;
    var when = finishedAt();
    finishedSaid.textContent = "";
    if (when) {
      var day = new Date(when);
      var said = "";
      try {
        said = day.toLocaleDateString(undefined, { day: "numeric", month: "short" });
      } catch (e) {
        said = day.toDateString();
      }
      var count = finishedCount();
      var lead = document.createElement("b");
      lead.className = "cheer";
      lead.textContent = "You finished a targum.";
      finishedSaid.appendChild(lead);
      var tally = document.createElement("span");
      tally.className = "tally";
      var figure = document.createElement("b");
      figure.textContent = ordinal(count);
      tally.appendChild(document.createTextNode("Your "));
      tally.appendChild(figure);
      tally.appendChild(document.createTextNode(count === 1 ? " · " + said : " · " + said));
      finishedSaid.appendChild(tally);
      finishedSaid.hidden = false;
      finishedMark.textContent = "Undo";
      finishedMark.classList.add("undo");
    } else {
      finishedSaid.hidden = true;
      finishedMark.textContent = "Done";
      finishedMark.classList.remove("undo");
    }
    finishedBox.classList.toggle("is-done", !!when);
    // The inverted block is a ledger, and `.ledger` is what licenses the bright set.
    finishedBox.classList.toggle("ledger", !!when);
  }
  renderFinished();

  /* --- the forms of a sentence --------------------------------------------- */

  // Hebrew combining marks. Deliberately not the whole 0591-05C7 block: the maqaf,
  // paseq, sof pasuq and nun hafukha live inside it and are characters of the text, not
  // marks above it. Mirrors MARKS in vocalize/base.py, and for the same reason.
  //
  // One set, covering the accents as well as the points. Which of them is a ta'am and
  // which a vowel is a question only the builder ever has to answer, and it answers it
  // once, in Python, by deciding what goes in which cell. Here the only question is
  // "what is a mark", so the reader needs no second constant and cannot disagree with
  // the server about the first — which is what the mark-parity test checks, and why one
  // constant here keeps it sufficient.
  var MARK = /[\u0591-\u05BD\u05BF\u05C1-\u05C2\u05C4-\u05C5\u05C7]/;

  // Every stored offset — a token span, a phrase you kept — is measured against the
  // bare text, whichever form happens to be on show. That way turning the vowels on
  // cannot quietly move a saved phrase onto different characters. A pointed cell is
  // drawn by mapping those offsets across, and the map is derived from the text itself
  // rather than shipped with the page: it is one linear pass, and it costs nothing.
  //
  // Cached on the element, not under the segment id, because a segment now has up to
  // three cells and one key for all of them would hand each the others' positions — the
  // same reason `original` and `cellText` cache where they do. It works unchanged on the
  // accented form because MARK covers accents too: what comes back either way is where
  // the consonants are, and all three cells share those.
  function markMap(cell) {
    if (!cell) return null;
    if (cell.__targumMap === undefined) {
      var text = cellText(cell);
      var map = [];
      for (var i = 0; i < text.length; i++) if (!MARK.test(text[i])) map.push(i);
      map.push(text.length);
      cell.__targumMap = map;
    }
    return cell.__targumMap;
  }

  // A position in a pointed cell, back to the bare text it stands for.
  function toBare(cell, offset) {
    var text = cellText(cell);
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
      plainText[segmentId] = cellText(cells.plain[segmentId]);
    }
    return plainText[segmentId];
  }

  // Looked up because you asked, not bought in advance. The answer is cached on the
  // machine, so the same word costs nothing the next time it turns up anywhere.
  var asked = {};
  // Words whose meaning the card has already asked the cache for, found or not.
  var peeked = {};
  // Words whose meaning a sentence has chosen — the server's, or asked for from here
  // this session. A meaning the build shipped was bought for the whole text at once,
  // with no sentence per word, and עם came back "people" on a page where it was "with".
  // The first card that opens on such a word asks once more, with the sentence it is
  // in, and the answer stands for every reader after. Once a session per word: an
  // answer that is already grounded is a cache hit on the server, and asking again
  // buys nothing either way.
  var grounded = {};
  // What came back for a word that had no meaning: "none" when it was looked up and
  // there was nothing to find, or the reason it could not be looked up. Kept so the
  // card can say which, instead of quietly offering the same button again.
  var lookup = {};

  // The sentence a word was met in, sent with the lookup so the meaning that comes
  // back is the one the word has here. Bare rather than pointed: the plain cell is
  // always there, and the model reads either.
  function sentenceOf(word) {
    var pair = word && word.closest ? word.closest("[data-id]") : null;
    return pair ? segmentText(pair.getAttribute("data-id")) : "";
  }

  // Whether a meaning is already held for this word — never bought. A card opens with
  // what targum has before it offers to go and get what it does not.
  function peek(index, onDone) {
    var lemma = lemmas[index];
    if (!lemma || !canAsk() || typeof fetch !== "function") return;
    var into = targetLanguage || "en";
    fetch(keyed("/gloss"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ lemma: lemma, source: language, target: into, free: true }),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (answer) {
        if (answer && answer.meaning) {
          keepMeaning(lemma, answer.meaning, into);
          if (into === targetLanguage) glosses[index] = answer.meaning;
          if (answer.citation) citations[index] = String(answer.citation);
          if (answer.plural) plurals[index] = String(answer.plural);
          if (answer.grounded) grounded[lemma] = true;
          onDone(true);
        } else {
          onDone(false);
        }
      })
      .catch(function () {
        onDone(false);
      });
  }

  // A meaning already on the card, asked about once more with the sentence it is in.
  // Nothing is claimed while the answer is in the air — the old meaning stays up — and
  // the card is redrawn only where the answer moved it.
  function ground(index, word, onChanged) {
    var lemma = lemmas[index];
    if (!lemma || grounded[lemma] || !canAsk()) return;
    grounded[lemma] = true;
    var before = glosses[index];
    lookUp(index, sentenceOf(word), function () {
      if (glosses[index] !== before) onChanged();
    });
  }

  function lookUp(index, sentence, onDone) {
    var lemma = lemmas[index];
    if (!lemma || !canAsk()) return;
    if (asked[lemma]) return;
    asked[lemma] = true;
    // A lookup that carries its sentence is a grounding: whatever comes back, the
    // server has now had the sentence, and the card need not send it again.
    if (sentence) grounded[lemma] = true;
    // The language asked about, held for the length of the flight. A reader can change
    // translations while an answer is in the air, and an English meaning filed against
    // Russian is exactly the thing none of this is allowed to do.
    var into = targetLanguage || "en";
    fetch(keyed("/gloss"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        lemma: lemma,
        source: language,
        target: into,
        sentence: sentence || "",
      }),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (answer) {
        asked[lemma] = false;
        if (answer && answer.meaning) {
          keepMeaning(lemma, answer.meaning, into);
          if (into === targetLanguage) glosses[index] = answer.meaning;
          if (answer.citation) citations[index] = String(answer.citation);
          if (answer.plural) plurals[index] = String(answer.plural);
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

  // What a run of words means, asked with the sentence and its translation in hand so
  // the answer can be the piece of the parallel text that is that run. Held for the life
  // of the page under the selection's offsets; the server's cache is what remembers
  // across a reload. `null` while an answer is in the air, `false` when none came.
  var phraseAnswers = {};

  function phraseKey(picked, into) {
    return picked.segmentId + ":" + picked.start + ":" + picked.end + ":" + into;
  }

  function phraseHeld(picked) {
    var held = phraseAnswers[phraseKey(picked, targetLanguage || "en")];
    return held && held.meaning ? held : null;
  }

  // Whether an answer could still come: the page can ask, there is a translation to ask
  // against, and nothing has been asked yet or one is on its way.
  function phrasePending(picked) {
    if (!canAsk() || typeof fetch !== "function") return false;
    if (!translationFor(picked.segmentId)) return false;
    var held = phraseAnswers[phraseKey(picked, targetLanguage || "en")];
    return held === undefined || held === null;
  }

  function askPhrase(picked, onDone) {
    if (!canAsk() || typeof fetch !== "function") return;
    // The language asked about, held for the flight, for the reason `lookUp` holds it.
    var into = targetLanguage || "en";
    var key = phraseKey(picked, into);
    if (phraseAnswers[key] !== undefined) return;
    phraseAnswers[key] = null;
    fetch(keyed("/phrase"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        phrase: picked.text,
        sentence: segmentText(picked.segmentId),
        translation: translationFor(picked.segmentId),
        source: language,
        target: into,
      }),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (answer) {
        phraseAnswers[key] =
          answer && answer.meaning
            ? {
                meaning: String(answer.meaning),
                quoted: !!answer.quoted,
                kind: String(answer.kind || ""),
                citation: String(answer.citation || ""),
              }
            : false;
        onDone(phraseAnswers[key], into);
      })
      .catch(function () {
        phraseAnswers[key] = false;
        onDone(false, into);
      });
  }

  function statusOf(lemma) {
    var item = vocab[lemma];
    return item ? item.status : undefined;
  }

  // What you wrote down that a word means. Beside the meaning targum gave and under the
  // same pair, because a note is a meaning too: one written in Russian is no more use on
  // an English page than a Russian gloss would be.
  function noteOf(lemma) {
    return noteOn(lemma);
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
    writeMeaning(lemma, { note: text });
  }

  // Setting a word to what it already is takes the mark off again, so the same tap
  // both grades a word and undoes a mistake.
  // What a keystroke did, for anyone listening. The page's only answer to a level was a
  // ring moving and a count in the opposite corner, and a screen reader was told neither.
  var spoken = document.getElementById("spoken");

  // Its own words rather than the buttons'. A button says what pressing it will do and
  // this says what pressing it did, which is a different tense and sometimes a different
  // word: the ignore button reads "a name or a number", and hearing that back as the
  // answer to a keystroke tells you nothing about what happened.
  var SAID = {};
  SAID[1] = "just met it";
  SAID[2] = "getting there";
  SAID[3] = "nearly know it";
  SAID[KNOWN] = "known";
  SAID[IGNORED] = "ignored";

  function stepTitle(status) {
    // Asked of the object's own keys, for the same reason every other lookup here is.
    if (Object.prototype.hasOwnProperty.call(SAID, status)) return SAID[status];
    // Saying a level a word already has takes it off again, which is a real answer and
    // has to be said as one.
    return "not marked";
  }

  function say(words) {
    if (!spoken) return;
    // Rewritten rather than appended: the same sentence twice running is still news, and
    // a region that only ever grows is read from the top every time.
    spoken.textContent = "";
    spoken.textContent = words;
  }

  function saidLevel(surface, status) {
    var counts = coverage();
    var left = counts.fresh + counts.learning;
    say(surface + ", " + stepTitle(status) + ". " + left + " left.");
  }

  // A level is one keystroke wide and there are five of them, so the wrong one is a
  // matter of time. Every change keeps what it replaced and the word it was said about,
  // and `u` puts both back. Without it a mis-keyed `k` is unreachable: known takes the
  // word out of the queue the arrows walk, so there is no way back to it from the
  // keyboard at all.
  var undoable = [];
  var UNDO_DEPTH = 50;

  function recordUndo(index, lemma, surface) {
    undoable.push({
      lemma: lemma,
      surface: surface || lemma,
      // A copy. The record itself is rewritten in place by the next change to the word,
      // and a reference would undo to whatever it had become.
      before: vocab[lemma] ? JSON.parse(JSON.stringify(vocab[lemma])) : null,
      // Where you were standing when you said it, so undo hands the word back rather
      // than only the level. Null where the level came from a card a pointer opened.
      where: place ? { segment: place.segment, lemma: index, start: place.start } : null,
    });
    if (undoable.length > UNDO_DEPTH) undoable.shift();
  }

  // A word taken off the list, and its meanings with it, in every language they were
  // written in — from this page's own copies and from the store, which `sync.js` sweeps
  // and tombstones. Left behind, a meaning with no word under it kept a language in the
  // definitions switcher after the last word learned through it was gone.
  function forgetWord(lemma) {
    delete vocab[lemma];
    Object.keys(meaningStores).forEach(function (into) {
      var records = meaningStores[into].records;
      if (records && records[lemma]) delete records[lemma];
    });
    if (window.TargumSync) {
      window.TargumSync.forgetWord(language, lemma);
      window.TargumSync.forgetMeanings(language, lemma);
    }
  }

  // Every word on this page you never said anything about, marked known at once. What
  // is left after reading a part is, by and large, what you knew already; this is the
  // `k` you would have pressed on each. One record for the whole batch, so one `u`
  // takes the whole batch back — pushed one at a time, a long part would overflow the
  // undo list and most of it would be unreachable. Names and numbers go too — the
  // whole point is a clean page — and stay out of every count, because the record
  // keeps "name" as its band.
  var restSaid = 0;

  // What is still unmarked on this page, names included: what the offer counts.
  function unmarkedHere() {
    return lemmasHere(true).filter(function (lemma) {
      return statusOf(lemma) === undefined;
    });
  }

  function markRest() {
    var batch = [];
    unmarkedHere().forEach(function (lemma) {
      if (statusOf(lemma) !== undefined) return;
      var index = lemmas.indexOf(lemma);
      batch.push({ lemma: lemma, before: null });
      vocab[lemma] = {
        status: KNOWN,
        surface: lemma,
        band: bandOfLemma(index),
        // Ticked off, not carried up: a word never at a level below known is one you
        // already had.
        learned: 0,
        at: nextOrder(),
        seen: Date.now(),
      };
      keepMeaning(lemma, glosses[index]);
    });
    if (!batch.length) return 0;
    undoable.push({ bulk: batch, surface: "", where: null });
    if (undoable.length > UNDO_DEPTH) undoable.shift();
    restSaid = batch.length;
    remember();
    redraw();
    say(batch.length + " words marked known. Nothing left to mark here.");
    return batch.length;
  }

  function bandOfLemma(index) {
    var ids = Object.keys(wordData);
    for (var i = 0; i < ids.length; i++) {
      var rows = wordData[ids[i]] || [];
      for (var j = 0; j < rows.length; j++) {
        if (rows[j][4] === index) return bandOf(rows[j]);
      }
    }
    return "";
  }

  function undo() {
    var last = undoable.pop();
    if (!last) return false;
    if (last.bulk) {
      last.bulk.forEach(function (item) {
        if (item.before) vocab[item.lemma] = item.before;
        else forgetWord(item.lemma);
      });
      restSaid = 0;
      remember();
      redraw();
      say("Took back " + last.bulk.length + " words.");
      return true;
    }
    if (last.before) {
      vocab[last.lemma] = last.before;
    } else {
      forgetWord(last.lemma);
    }
    remember();
    saidLevel(last.surface, statusOf(last.lemma));
    var open = asking();
    redraw();
    // Back onto the word it was said about, so the answer can be given again rather than
    // hunted for. Undoing a level set with a pointer changes the level and nothing else.
    if (last.where && !focusQueued(last.where, open)) leaveQueue();
    return true;
  }

  // Pressing the level a word already has takes the mark off again, so the same button
  // both grades a word and undoes a mistake. For the pointer only: a key that lands on
  // a marked word and says its level again is confirming it. Asked here, before anything
  // else has written to the store, rather than worked out inside `setStatus` from what
  // it finds there.
  function toggled(index, status) {
    return statusOf(lemmas[index]) === status ? null : status;
  }

  // `status` is what the reader asked for, and `null` is "take the mark off". Nothing is
  // inferred from what is already stored, because `setNote` writes a record at level 1 on
  // its way past: a `setStatus` that re-read the store saw the level it had just written
  // itself and took a press of "1" for a second press. Typing a definition and then
  // saying "just met it" unmarked the word and threw the definition away with it.
  // Whether this change is a word arriving at known from somewhere below it. Asked
  // before the record is rewritten, because the answer is in the level it is leaving.
  function learnedNow(lemma, status) {
    if (vocab[lemma] && vocab[lemma].learned) return true;
    return status === KNOWN && isLearning(statusOf(lemma));
  }

  // Words finished with on this page, so the list can keep showing them — see
  // `wordEntries`. This session only: it is a receipt, not a state.
  var justSaid = {};

  function setStatus(index, surface, band, status) {
    var lemma = lemmas[index];
    if (!lemma) return false;
    recordUndo(index, lemma, surface);
    if (status === null || status === undefined || isLearning(status)) delete justSaid[lemma];
    else justSaid[lemma] = true;
    if (status === null || status === undefined) {
      forgetWord(lemma);
    } else {
      vocab[lemma] = {
        status: status,
        surface: vocab[lemma] ? vocab[lemma].surface || surface : surface,
        band: band || (vocab[lemma] ? vocab[lemma].band : "") || "",
        // A word you carried up from a level below known is one you learned here; a word
        // you opened a text and ticked off is one you already had. Sticky, because
        // having learned it is not undone by later changing your mind about the level.
        learned: learnedNow(lemma, status) ? 1 : 0,
        at: vocab[lemma] ? vocab[lemma].at || nextOrder() : nextOrder(),
        seen: Date.now(),
      };
      // What the page says it means, kept beside the word under the language it was
      // said in. The word record used to hold it, which made one slot for a fact that
      // has one answer per language: keeping a word while reading in Russian overwrote
      // the English meaning of every text that word appears in.
      keepMeaning(lemma, glosses[index]);
      // Where the word went, the first time you keep one — but never in the middle of a
      // walk. Opening a panel over the translation while somebody is stepping the
      // chapter a word at a time takes away the thing they are grading against, at the
      // one moment they are not looking for it. `s` opens it when it is wanted.
      if (isLearning(status) && !standing && listBox && listBox.hidden) showList(true);
    }
    remember();
    var now = statusOf(lemma);
    // Said here rather than at the keys, so every way of setting a level says the same
    // thing: the card's buttons, the list beside the text, and the five keys.
    saidLevel(surface || lemma, now);
    firstWordMarked();
    return now;
  }

  // The first time in a reader. A line under the bar says what to do; the first word
  // marked turns it into the three keys that are most of a session; and then it is
  // never seen again. Never for a reader with words in this language already — they
  // have done this — and `?` still has the whole list.
  var first = document.getElementById("first");
  var FIRST = "targum:first";
  var firstTime = false;
  try {
    firstTime = !!first && !localStorage.getItem(FIRST) && !Object.keys(vocab).length;
  } catch (e) {}
  if (firstTime) first.hidden = false;

  function firstWordMarked() {
    if (!firstTime) return;
    firstTime = false;
    // The arrow that actually goes forward on this page — §7, typed characters per
    // reading direction. The card's legend already knew this; the bar did not.
    var forward =
      (document.documentElement.getAttribute("dir") || "ltr") === "rtl" ? "←" : "→";
    first.textContent = "k known · 1 2 3 · " + forward + " next word · ? every key";
    try {
      targumKeep(FIRST, String(Date.now()));
    } catch (e) {}
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
    var map = cell === cells.plain[segmentId] ? null : markMap(cell);
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
    // Only the cell on show is worth marking; the others are redrawn when they appear.
    // And the others are put back to plain text: a hidden cell still carrying spans is
    // one `.w` query away from being stood on, and `wordIn` is only the sites found so
    // far.
    var cell = shownCell(segmentId);
    for (var f = 0; f < FORMS.length; f++) {
      var other = cells[FORMS[f]][segmentId];
      if (other && other !== cell && other.querySelector("span")) {
        other.innerHTML = original(other);
      }
    }
    if (cell) markSegment(cell);
  }

  // Everything in view, and a little either side. Cheap: the pairs are in document
  // order, so it stops at the first one past the bottom rather than walking the rest of
  // the chapter, and a pair already drawn this pass costs one property read.
  function markVisible() {
    // On a page, the page: a hidden pair has no rectangle, and asking would mark the
    // whole chapter for nothing.
    if (paged() && pages.length) {
      for (var p = pages[current][0]; p <= pages[current][1]; p++) markPair(pairs[p]);
      return;
    }
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
    if (paged() && pages.length) {
      first = pages[current][0];
    } else if (drawn) {
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
  var ankiButton = document.getElementById("anki-button");
  var tabs = document.querySelectorAll("[data-list]");

  // The other half of the tablist contract: arrows move between the two tabs, and the
  // move selects. Either arrow — there are two tabs, so "the other one" is unambiguous
  // and the pair works the same on an RTL page.
  Array.prototype.forEach.call(tabs, function (tab) {
    tab.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      event.stopPropagation();
      var other = tab.getAttribute("data-list") === "words" ? "phrases" : "words";
      showTab(other);
      var next = document.querySelector('[data-list="' + other + '"]');
      if (next) next.focus();
    });
  });
  var wordsLabel = document.getElementById("list-count-label");
  var phrasesLabel = document.getElementById("phrase-count-label");

  function label(element, count, one) {
    if (element) element.textContent = count === 1 ? one : one + "s";
  }

  function translationFor(segmentId) {
    var entry = translationData[showing] || translationData.t0;
    return entry && entry.text ? entry.text[segmentId] || "" : "";
  }

  // Every distinct dictionary form this section of the text uses. The list and the
  // count of what you know are both about the text in front of you, not about the
  // whole language: a vocabulary of four thousand words is not a reading aid.
  //
  // Names and numbers are left out unless `everything` is asked for: they are on the
  // page to be tapped and cleared, and they are on the list if you kept one, but they
  // are never in the count of what you know or have yet to.
  function lemmasHere(everything) {
    var here = {};
    Object.keys(wordData).forEach(function (segmentId) {
      (wordData[segmentId] || []).forEach(function (token) {
        if (!everything && isName(token)) return;
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
    lemmasHere(true).forEach(function (lemma) {
      var item = vocab[lemma];
      // Known and ignored words are counted below but not listed: the list is what you
      // are still working on, and a finished word in it is in the way. Except the one
      // you finished with just now, which stays until the page is left — a word that
      // vanished the moment you said you knew it read as a save that had failed.
      if (!item) return;
      var done = !isLearning(item.status);
      if (done && !justSaid[lemma]) return;
      out.push({
        kind: "word",
        key: lemma,
        term: item.surface || lemma,
        lemma: lemma,
        status: item.status,
        done: done,
        // Both in the language on show. A meaning kept from a Russian reading is not an
        // answer to a word met on the English page, and the list beside the text is the
        // one place a reader compares the two at a glance.
        note: noteOf(lemma),
        level: item.band || "",
        meaning: noteOf(lemma) || meaningOf(lemma),
        at: item.at || 0,
      });
    });
    return out.sort(byOrder);
  }

  function phraseEntries() {
    var out = [];
    Object.keys(picks).forEach(function (segmentId) {
      picks[segmentId].forEach(function (pick, index) {
        var term = phraseTerm(pick);
        var note = noteOn(term);
        out.push({
          kind: "phrase",
          key: segmentId + ":" + index,
          segmentId: segmentId,
          index: index,
          term: pick.text,
          lemma: "",
          status: pick.status === undefined ? null : pick.status,
          note: note,
          level: "",
          // The sentence's own translation is the last resort, and it is already the
          // one on show: `translationFor` follows the picker, so a phrase with nothing
          // written against it reads in the language being read.
          meaning: note || meaningOf(term) || translationFor(segmentId),
          at: pick.at || 0,
        });
      });
    });
    return out.sort(byOrder);
  }

  // Newest at the top. The word you just kept is the one you are looking for, and
  // at the foot of a list longer than the panel it was the one you could not see.
  function byOrder(a, b) {
    return b.at - a.at;
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

  // Whether this chapter has had anything waiting while you were on it. One you open
  // already finished shows the ordinary count; one you finish yourself is told so.
  var wasWaiting = false;
  //: Whether this visit has already marked the text finished on the reader's behalf. One
  //: at most: pressing Done afterwards to un-finish it is a decision, and repeating the
  //: automatic one on the next redraw would take it back.
  var finishedBySelf = false;

  var restBox = document.getElementById("rest");
  var restText = document.getElementById("rest-text");
  var restMark = document.getElementById("rest-mark");
  var restUndo = document.getElementById("rest-undo");

  function renderRest(counts) {
    if (!restBox || !restText || !restMark || !restUndo) return;
    if (restSaid) {
      restText.textContent = restSaid + (restSaid === 1 ? " word" : " words") + " marked known";
      restMark.hidden = true;
      restUndo.hidden = false;
      restBox.hidden = false;
    } else if (unmarkedHere().length) {
      // One button that says the whole thing, rather than a question and a number.
      // The number is the header's number: vocabulary only, because a count that
      // included names and numerals sat beside a header that did not, and the two
      // disagreeing on one screen read as a bug. Names and numerals are still
      // cleared by the press — the offer is a clean page — they are just not called
      // words to your face.
      var left = lemmasHere(false).filter(function (lemma) {
        return statusOf(lemma) === undefined;
      }).length;
      restText.textContent = "";
      restMark.textContent = left
        ? "Mark " + left + (left === 1 ? " word" : " words") + " as known"
        : "Clear names and numbers";
      restMark.setAttribute(
        "title",
        left ? "Names and numbers are cleared too, without being counted." : ""
      );
      restMark.hidden = false;
      restUndo.hidden = true;
      restBox.hidden = false;
    } else {
      restBox.hidden = true;
    }
  }

  function renderStats() {
    var counts = coverage();
    renderRest(counts);
    // What the arrows still have to walk: everything neither known nor ignored. The
    // queue is built from the same rule, so this is its length without building it.
    var left = counts.fresh + counts.learning;
    if (left) wasWaiting = true;
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
        var done = !left && wasWaiting;
        headerKnown.classList.toggle("done", done);
        // Clearing the last word is finishing the text. Asking for Done as well is asking
        // somebody to tell the page what it has just watched them do.
        //
        // Once a visit, and never over the reader: `finishedAt` already being set means
        // there is nothing to do, and somebody who presses Done again to un-finish it has
        // said something, so the flag stops this from saying it back.
        if (done && !finishedBySelf && !finishedAt()) {
          finishedBySelf = true;
          setFinished(true);
        }
        if (done) {
          // A milestone bragged the brand's way: what is true, in type, once. Not a
          // banner, and nothing moves.
          headerKnown.appendChild(document.createTextNode("nothing left to mark here"));
        } else {
          var whole = document.createElement("b");
          whole.textContent = String(counts.known);
          var all = document.createElement("b");
          all.textContent = String(scored);
          headerKnown.appendChild(whole);
          headerKnown.appendChild(document.createTextNode(" of "));
          headerKnown.appendChild(all);
          headerKnown.appendChild(document.createTextNode(" known"));
          if (left) {
            // Ink rather than leaf. Leaf is what you know; work still to do is not an
            // achievement, and colouring it as one would say the opposite of the number.
            var rest = document.createElement("b");
            rest.className = "left";
            rest.textContent = String(left);
            headerKnown.appendChild(document.createTextNode(" · "));
            headerKnown.appendChild(rest);
            headerKnown.appendChild(document.createTextNode(" left"));
          }
        }
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

  /* The count used to scale to 1.4x and flash the accent when it went up. §6 asks for
     celebration in type rather than motion, and an overshoot curve on a counter is the
     arcade register the brand exists to avoid: the number changing is the news. */
  function countInto(element, value) {
    if (element) element.textContent = String(value);
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
      placeholder: "Your own meaning",
      onStatus: function (value) {
        setPhrase(entry, { status: value });
      },
      onNote: function (text) {
        if (text === entry.note) return;
        var list = picks[entry.segmentId];
        var pick = list && list[entry.index];
        if (!pick) return;
        writeMeaning(phraseTerm(pick), { note: text });
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
    if (entry.done) item.classList.add("done");
    // Tapping the row says "I want to say something about this", which is the same
    // thing tapping the word in the text says. A keyboard can say it too: the row is
    // a stop, and Enter or Space is the tap — a clickable thing with no key was the
    // one pointer-only interaction left in the reader.
    item.setAttribute("tabindex", "0");
    item.setAttribute("role", "button");
    item.setAttribute("aria-expanded", openRow === entry.key ? "true" : "false");
    item.addEventListener("click", function (event) {
      if (event.target.closest("button, input")) return;
      openRow = openRow === entry.key ? null : entry.key;
      renderList();
    });
    item.addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target !== item) return;
      event.preventDefault();
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
    // Inside the term's cell, so the row keeps its four columns.
    term.appendChild(window.TargumVocab.copyButton(entry.term, { say: say }));
    item.appendChild(term);

    // A phrase is in its own list now, so it no longer has to announce that it is one.
    if (entry.kind === "word") {
      var kind = document.createElement("span");
      kind.className = "kind";
      kind.textContent = entry.level || "";
      if (!entry.level) kind.title = "not rated in this language";
      item.appendChild(kind);

      // `!== undefined`, not truthy: ignored is 0, and it is a level like the others.
      if (entry.status !== undefined && entry.status !== null) {
        var mark = document.createElement("span");
        mark.className = "row-status status-" + entry.status;
        mark.textContent = String(stepLabel(entry.status));
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
        forgetWord(entry.key);
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
      // Roving: `role="tablist"` promises one Tab stop and arrow keys between the two,
      // and for a while it delivered neither — the tabs were two ordinary stops.
      tab.setAttribute("tabindex", selected ? "0" : "-1");
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
    if (ankiButton) ankiButton.disabled = (onPhrases ? lastPhrases : lastWords) === 0;
  }

  function renderList() {
    renderStats();
    if (!listBox) return;
    var words = wordEntries();
    var phrases = phraseEntries();
    lastWords = words.length;
    lastPhrases = phrases.length;

    countInto(listCount, words.length);
    countInto(listTabCount, words.length);
    countInto(phraseCount, phrases.length);
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
    // A sheet grows when a word is kept, and the controls standing on it go up with it.
    if (seatFoot()) relayout();
  }

  function showList(open, remembered) {
    if (open) occupy("list");
    // On a wide window the list takes a column of the width from the page rather than
    // covering it, so opening one re-wraps every line above the reader as well as below.
    var held = open === body.classList.contains("list-open") ? null : hold();
    if (remembered !== false) prefs.list = open;
    if (listBox) listBox.hidden = !open;
    if (listTab) listTab.hidden = open;
    // The keys button says whether its panel is out (§ shortcuts, line below showKeys);
    // the list's own toggle said nothing. Same disclosure, same convention.
    if (listTab) listTab.setAttribute("aria-expanded", open ? "true" : "false");
    body.classList.toggle("list-open", open);
    keep(held);
    relay();
    // Before the pages are measured: the arrows and the player stand on the sheet, and
    // `room` reads where they stand.
    seatFoot();
    relayout();
    if (!open) vacate("list");
    if (remembered !== false) save();
  }

  var roomy = window.matchMedia("(min-width: 60rem)");

  /* --- the band at the foot of a narrow window --------------------------------

     Under 60rem there is no width for a column beside the text and no height for a
     pile on top of it. So everything that stands over the text — the words sheet, a
     word's card, a phrase's chip, the keys, the menu behind ⋯ — is an occupant of one
     band at the foot, and the band holds one of them at a time. Opening one puts the
     last away.

     Two kinds of occupant. The sheet is a mode: the reader opened it and means it to
     stay. A card is transient: it is about one word and leaves when that word is
     answered. So a card that takes the band from the sheet gives it back when it goes,
     and the sheet's own preference is not touched by either move. Nothing else is
     given back; a menu over a card is a reader who has moved on.

     On a wide window this arbitrates nothing — the list is a column, the card sits by
     its word, and there is room for all of them — but the bookkeeping runs anyway, so
     turning a tablet does not find the state half-kept. */
  var occupant = null;
  var sheetWas = false;
  var restoring = 0;

  function occupy(which) {
    if (restoring) {
      cancelAnimationFrame(restoring);
      restoring = 0;
    }
    if (occupant === which) return;
    var was = occupant;
    // Set before the last one is put away, so that its own `vacate` sees a band that
    // is already somebody else's and does nothing.
    occupant = which;
    if (roomy.matches) return;
    if (was === "list") {
      sheetWas = true;
      showList(false, false);
    } else if (was === "card") {
      hideCard();
    } else if (was === "chip") {
      hideChip();
    } else if (was === "keys") {
      showKeys(false);
    } else if (was === "more") {
      showMore(false);
    } else if (was === "video") {
      // Put away through its own closure, which holds the button state and the store.
      if (window.TargumVideo) window.TargumVideo.hide();
    }
    if (which === "list") sheetWas = false;
  }

  // The occupant has gone. A frame later rather than now: tapping a second word closes
  // the first card before it opens the next, and giving the sheet back in between
  // would open it for one frame and shut it again, laying the pages out twice.
  function vacate(which) {
    if (occupant !== which) return;
    occupant = null;
    if (which === "list") sheetWas = false;
    if (!sheetWas || roomy.matches) return;
    restoring = requestAnimationFrame(function () {
      restoring = 0;
      if (occupant !== null || !sheetWas) return;
      sheetWas = false;
      showList(true, false);
    });
  }

  // Where the band stands, told to the stylesheet. `--occupant` is the occupant's
  // measured height — measured, not its ceiling: a sheet of two words is nowhere near
  // the 42svh it may grow to, and lifting the player by the ceiling parked it in the
  // middle of the page with nothing under it. `--strip` is the player's height, `--tab`
  // the width the words tab takes at the strip's start, `--tab-lift` what centres the
  // tab on the strip, and `--foot` the whole band from its highest edge to the bottom
  // of the window — which is what the scrolling reader pads its body by, so the last
  // line can be scrolled clear of it. Each is set and then the next is measured,
  // because where the strip stands depends on the occupant and where the arrows stand
  // on both. Cleared on a wide window, where the stylesheet's own numbers apply.
  // Returns whether anything changed, so a caller knows the pages need measuring again.
  var footSaid = { "--occupant": null, "--strip": null, "--tab": null, "--tab-lift": null, "--foot": null };

  function seatFoot() {
    var root = document.documentElement.style;
    var said = { "--occupant": null, "--strip": null, "--tab": null, "--tab-lift": null, "--foot": null };
    function tell(name) {
      if (said[name]) root.setProperty(name, said[name]);
      else root.removeProperty(name);
    }
    function standing(thing) {
      return thing && !thing.hidden && thing.getBoundingClientRect().height > 0;
    }
    if (!roomy.matches) {
      var occ = 0;
      occupants().forEach(function (thing) {
        if (standing(thing)) occ = Math.max(occ, thing.getBoundingClientRect().height);
      });
      said["--occupant"] = occ ? Math.round(occ) + "px" : null;
      tell("--occupant");
      var strip = standing(scenePlayer) ? scenePlayer.getBoundingClientRect().height : 0;
      said["--strip"] = strip ? Math.round(strip) + "px" : null;
      if (standing(listTab)) {
        var tab = listTab.getBoundingClientRect();
        // Its own width, its inset from the edge, and the gap to the play button.
        said["--tab"] = Math.round(tab.width + 20) + "px";
        if (strip) said["--tab-lift"] = Math.round(Math.max(0, (strip - tab.height) / 2)) + "px";
      }
      tell("--strip");
      tell("--tab");
      tell("--tab-lift");
      var top = window.innerHeight;
      [turn, scenePlayer, listTab].forEach(function (thing) {
        if (standing(thing)) top = Math.min(top, settledTop(thing, false));
      });
      occupants().forEach(function (thing) {
        if (standing(thing)) top = Math.min(top, settledTop(thing, true));
      });
      var foot = window.innerHeight - top;
      said["--foot"] = foot > 0 ? Math.round(foot) + "px" : null;
    }
    var changed = false;
    Object.keys(said).forEach(function (name) {
      if (footSaid[name] === said[name]) return;
      footSaid[name] = said[name];
      changed = true;
      tell(name);
    });
    return changed;
  }

  // What can hold the band. Read at the moment of asking rather than held in a list:
  // most of these are found further down this file, and the list would be written
  // before they were. The video panel is the one resident found by id here: its own
  // wiring lives in the player's closure, which runs after this one.
  var videoPanel = document.getElementById("video");

  function occupants() {
    return [listBox, card, chip, keysCard, more, videoPanel];
  }

  // Where a thing at the foot will stand once it has stopped moving. The strip, the
  // tab and the arrows ride to their places over 200ms, and an occupant rises from the
  // foot; measured mid-flight, the band came out too small as a menu opened — four
  // verses laid out, then run under the arrows as they arrived — and too big as it
  // closed, two verses and a screen of paper. An occupant is anchored to the foot, so
  // its settled top is the foot less its height; a riding thing's is read off its own
  // transition, whose last keyframe is where it is going. Where nothing is moving, this
  // is the box.
  function settledTop(thing, anchored) {
    var box = thing.getBoundingClientRect();
    if (anchored) return window.innerHeight - box.height;
    if (!thing.getAnimations) return box.top;
    var runs = thing.getAnimations();
    for (var i = 0; i < runs.length; i++) {
      var run = runs[i];
      // The logical property, or its physical name: a browser reports a transition on
      // `inset-block-end` as one on `bottom`, keyframes included.
      var on = run.transitionProperty;
      if ((on !== "inset-block-end" && on !== "bottom") || !run.effect || !run.effect.getKeyframes) {
        continue;
      }
      var frames = run.effect.getKeyframes();
      var last = frames.length ? frames[frames.length - 1] : null;
      var to = last ? parseFloat(last.insetBlockEnd || last.bottom) : NaN;
      if (!isNaN(to)) return window.innerHeight - to - box.height;
    }
    return box.top;
  }

  // How much of the window the band takes, as the stylesheet was last told.
  function footHeight() {
    return parseFloat(footSaid["--foot"]) || 0;
  }

  // The band changes height without anyone here touching it — a word is kept and the
  // sheet grows, a card's meaning wraps, the browser's own chrome comes and goes and
  // moves `svh` — and everything standing on it must follow, and the page be laid out
  // again above it. One observer for every occupant, watched from the moment the file
  // has found them all. No loop: laying the pages out again hides pairs and pads the
  // body, neither of which sizes a fixed occupant.
  function watchFoot() {
    if (!window.ResizeObserver) return;
    var watcher = new ResizeObserver(function () {
      if (seatFoot()) relayout();
    });
    occupants().forEach(function (thing) {
      if (thing) watcher.observe(thing);
    });
  }

  /* --- what a word means --------------------------------------------------- */

  var card = document.getElementById("gloss-card");
  var lookedUp = null;

  // Where you are in the word queue, and the word itself. Kept apart from `lookedUp`,
  // because standing on a word and asking what it means are two different things: the
  // arrows move the first, Enter does the second, and walking a page fires no windows.
  //
  // `place` is also what tells `markLookedUp` which of two things to do when you say how
  // well you know a word: one you walked to hands you the next, one you tapped stays put.
  var place = null;
  var standing = null;

  function hideCard() {
    stopFade();
    if (card) card.hidden = true;
    vacate("card");
    // And the phrase chip with it. One popup at a time: mouseup drew the chip and the
    // click that followed drew the card over it, for the same word, and nothing that
    // closed one knew about the other.
    hideChip();
    letGo();
  }

  // Somewhere to take hold of, at the head of a card that is a sheet.
  //
  // The sheets have always closed on a swipe down — see `dismissible` — but nothing on
  // one said so. On a phone the card opens over the sentence it was asked about, and the
  // ways out were a gesture nobody had been told about and a tap on the text behind it,
  // which is the text the card is covering. So the bar is both the sign that it can be
  // pulled down and a target that closes it when tapped: whichever the reader tries,
  // that is the one that works.
  //
  // Narrow screens only — `.grab` is display:none above the breakpoint, where the card
  // is a small panel beside the word rather than a sheet across the foot of the window,
  // and where Escape and a click elsewhere are already the way out. Rebuilt with the
  // card because `showCard` empties it every time.
  function grabHandle(close) {
    var grab = document.createElement("button");
    grab.type = "button";
    grab.className = "grab";
    // The bar carries no text, so it says what it is here rather than in the page.
    grab.setAttribute("aria-label", "Close");
    grab.addEventListener("click", close);
    return grab;
  }

  // The card lets go of the word it was about. Its own function because a card that has
  // been answered lets go at once and leaves a moment later, so the two are no longer
  // one thing.
  function letGo() {
    if (lookedUp) {
      lookedUp.classList.remove("looked-up");
      lookedUp.removeAttribute("aria-describedby");
    }
    lookedUp = null;
  }

  // A card that has been answered. Saying a level answers the question the card was
  // opened to ask, so it goes rather than riding the arrows on to the next word — but
  // not in the frame the key was pressed in: a reader clearing a chapter a word at a
  // time would have a window blinking at them forty times. It holds still long enough
  // for the level it has just taken to be read, and then fades.
  //
  // The word is let go of straight away. What fades is chrome nobody is reading any
  // more, and a card that still claimed a word could be handed back to `showCard` after
  // the redraw had replaced the span it named.
  var LINGER = 700;
  // Matches `.gloss-card.going` in reader.css, which is where the fade itself lives.
  var FADE = 220;
  var fading = null;

  function spendCard() {
    if (!card || card.hidden) return;
    stopFade();
    letGo();
    fading = setTimeout(function () {
      card.classList.add("going");
      fading = setTimeout(hideCard, FADE);
    }, LINGER);
  }

  // Nothing on its way out. Said by every path that puts a card up or takes one down, so
  // a card that is leaving and a card that has just been asked for are never both up.
  function stopFade() {
    if (fading) clearTimeout(fading);
    fading = null;
    if (card) card.classList.remove("going");
  }

  // Out of the queue altogether. A word is not focusable in its own right — it is a span
  // the marking pass drew — so leaving it in the tab order once you have moved on would
  // be litter.
  function leaveQueue() {
    if (standing) {
      standing.classList.remove("queued");
      standing.removeAttribute("tabindex");
    }
    standing = null;
    place = null;
  }

  // What a token row says a word is: a name, a number, or a word with a difficulty.
  // Kept on the record as its band, so every count that reads the band — the ledger,
  // the milestones, the ulpan ladder — knows to leave a name out. Column 7; rows built
  // before it existed have none, and read as words.
  var KIND_NAMES = ["", "name", "number"];

  function bandOf(token) {
    return (token[6] && KIND_NAMES[token[6]]) || levelNames[token[2]] || "";
  }

  function isName(token) {
    return !!(token[6] && KIND_NAMES[token[6]]);
  }

  // One entry of the grammar string the annotator kept — "UPOS=VERB|Person=1|Tense=Past"
  // and nothing more. A missing key is "", never a guess.
  function feat(line, key) {
    var parts = (line || "").split("|");
    for (var i = 0; i < parts.length; i++) {
      var eq = parts[i].indexOf("=");
      if (eq > 0 && parts[i].slice(0, eq) === key) return parts[i].slice(eq + 1);
    }
    return "";
  }

  // Who a form is about, in plain words. "past · I" reads to a novice and is
  // unambiguous to a student; "1cs perfect" is neither, on either shelf.
  function personWord(line) {
    var person = feat(line, "Person");
    var gender = feat(line, "Gender");
    var plural = feat(line, "Number") === "Plur";
    if (person === "1") return plural ? "we" : "I";
    if (person === "2") {
      var marks = [];
      if (gender === "Masc") marks.push("m");
      if (gender === "Fem") marks.push("f");
      if (plural) marks.push("pl");
      return marks.length ? "you (" + marks.join(", ") + ")" : "you";
    }
    if (person === "3") {
      if (plural) return "they";
      if (gender === "Masc") return "he";
      if (gender === "Fem") return "she";
    }
    return "";
  }

  var TENSE_WORDS = { Past: "past", Pres: "present", Fut: "future" };
  var POS_WORDS = {
    NOUN: "noun",
    ADJ: "adjective",
    ADP: "preposition",
    PRON: "pronoun",
    PART: "particle",
    CCONJ: "conjunction",
    SCONJ: "conjunction",
  };

  // The part of speech's own line: for each kind of word, the one fact whose absence
  // is the usual reason a learner mis-reads it. A verb is parsed, a noun declares its
  // gender and number, an adjective its agreement — and an adverb needs nothing, so
  // it gets nothing.
  // Which Hebrew a word belongs to, said from where the reader is standing. The table
  // holds a code only where the two registers disagree, so every line here is news: a
  // word ordinary in scripture and gone from the street, or in use today and never in
  // the Tanakh. The same word is ordinary in a Tanakh and an import in a newspaper,
  // and the line says whichever the reader is looking at.
  function registerLine(code, source) {
    if (code === "biblical") {
      return source === "biblical" ? "biblical · rare today" : "biblical · an import here";
    }
    if (code === "modern") return "modern · not in the Tanakh";
    return "";
  }

  function useLine(line) {
    var pos = feat(line, "UPOS");
    if (pos === "VERB" || pos === "AUX") {
      var parts = [];
      var form = feat(line, "VerbForm");
      var tense = TENSE_WORDS[feat(line, "Tense")];
      if (form === "Inf") parts.push("infinitive");
      else if (tense) parts.push(tense);
      // The beinoni: tagged as a participle, met as the present tense.
      else if (form === "Part") parts.push("present");
      var who = personWord(line);
      if (who) parts.push(who);
      return parts.join(" · ");
    }
    if (pos === "NOUN") {
      var noun = ["noun"];
      var gender = feat(line, "Gender");
      if (gender === "Masc") noun.push("m");
      if (gender === "Fem") noun.push("f");
      if (feat(line, "Number") === "Plur") noun.push("pl.");
      if (feat(line, "Definite") === "Cons") noun.push("construct");
      return noun.length > 1 ? noun.join(" · ") : "";
    }
    if (pos === "ADJ") {
      var agree = ["adjective"];
      if (feat(line, "Gender") === "Fem") agree.push("f");
      if (feat(line, "Number") === "Plur") agree.push("pl.");
      return agree.join(" · ");
    }
    if (pos === "PRON") return personWord(line);
    return POS_WORDS[pos] || "";
  }

  // A line that mixes Hebrew pieces with English glue — "ו and + ל to + בית". The
  // Hebrew runs get their own bdi with the page's language, so they take the carried
  // face and hold their own direction inside the English sentence.
  function mixedLine(container, text) {
    var hebrew = /[֐-׿]+/g;
    var at = 0;
    var found;
    while ((found = hebrew.exec(text))) {
      if (found.index > at) {
        container.appendChild(document.createTextNode(text.slice(at, found.index)));
      }
      var piece = document.createElement("bdi");
      piece.setAttribute("lang", language);
      piece.textContent = found[0];
      container.appendChild(piece);
      at = found.index + found[0].length;
    }
    if (at < text.length) container.appendChild(document.createTextNode(text.slice(at)));
  }

  // The word's own sound, where the page's recording covers it. The audio lives in the
  // player's closure and `TargumSpeech` is its one window — never opened on a silent
  // page, so the card, like the phrase chip, offers only what the page can.
  var HEAR_GLYPH =
    '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">' +
    '<path d="M5 3.5 12.5 8 5 12.5Z"></path></svg>';

  function hearButton(segmentId, start, end, label) {
    if (!window.TargumSpeech) return null;
    var slice = window.TargumSpeech.clockFor(segmentId, start, end);
    if (!slice) return null;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "hear";
    button.title = "Hear";
    button.setAttribute("aria-label", label);
    button.innerHTML = HEAR_GLYPH;
    button.addEventListener("click", function (event) {
      event.stopPropagation();
      window.TargumSpeech.playSlice(slice);
    });
    return button;
  }

  function hearFor(word) {
    var pair = word.closest ? word.closest(".pair") : null;
    var span = (word.getAttribute("data-bare") || "").split(",");
    if (!pair || span.length !== 2) return null;
    return hearButton(
      pair.getAttribute("data-id"),
      parseInt(span[0], 10),
      parseInt(span[1], 10),
      "Hear this word"
    );
  }

  function levelOf(word) {
    var pair = word.closest(".pair");
    if (!pair) return "";
    var segmentId = pair.getAttribute("data-id");
    var index = parseInt(word.getAttribute("data-lemma"), 10);
    var match = (wordData[segmentId] || []).filter(function (token) {
      return token[4] === index;
    })[0];
    return match ? bandOf(match) : "";
  }

  // How well you know this word, and what you want it to say. The same control serves
  // the card, the list beside the text and the words page, so the three never drift.
  // Setting a level from the keyboard, on whichever word the card is open for. Does the
  // same as pressing the button: the card is rebuilt rather than patched, so every
  // control in it agrees about which level is now set.
  // `4` as well as `k`: known is the level above 3, and a hand already on the number
  // row should not have to leave it.
  var KEYED_STATUS = { 1: 1, 2: 2, 3: 3, 4: KNOWN, k: KNOWN, i: IGNORED };

  // How to set a level on the phrase card while it is open. A phrase is saved by its
  // offsets into one sentence and a word by its lemma, so the two cards cannot share a
  // path — they share the keys instead. Set by `showPick`, cleared when it closes.
  var pickLevel = null;

  // Hover is the browser's, and it does not let go until the pointer moves. Marking a
  // word from the keyboard while the pointer rests on it left the word highlighted as
  // though it were still being looked up — known, and still lit. Turn hover off for the
  // page when a key changes a word, and give it back at the first move.
  var hovering = true;

  function stopHover() {
    if (!hovering) return;
    hovering = false;
    body.classList.add("no-hover");
  }

  document.addEventListener("mousemove", function () {
    if (hovering) return;
    hovering = true;
    body.classList.remove("no-hover");
  });

  function markLookedUp(key) {
    // Asked of the object's own keys: `KEYED_STATUS["constructor"]` is a function, and
    // every other key on the page would have gone through this branch holding one.
    if (!Object.prototype.hasOwnProperty.call(KEYED_STATUS, key)) return false;
    var status = KEYED_STATUS[key];

    // The word the arrows are standing on, or failing that whichever card is open — the
    // word card winning if somehow both are. Saying how well you know a word does not
    // need the card open: the card is a question you asked, and this is an answer you
    // already had.
    var word = standing || (lookedUp && card && !card.hidden ? lookedUp : null);
    if (word) {
      var index = parseInt(word.getAttribute("data-lemma"), 10);
      if (!lemmas[index]) return false;
      var surface = bareSurface(word);
      // Said, not toggled. The back arrow lands on words already marked, and a level
      // pressed to confirm one took the mark off instead and walked on — silently. From
      // the keyboard a level means what it says; `u` is the way back.
      setStatus(index, surface, levelOf(word), status);
      stopHover();
      var from = place;
      var open = asking();
      // Read before the redraw. `markSegment` replaces the text nodes inside the cell,
      // so the span is detached afterwards and has no ancestors left to search — asking
      // a detached word for its sentence answers null, and the card shut itself on every
      // word marked with a pointer.
      var pair = word.closest ? word.closest(".pair") : null;
      redraw();
      // The card asked what the word means and the level is an answer, so it is spent:
      // it fades where it stands rather than being carried on to the next word. See
      // `spendCard` — the next word is walked to without one, and Enter asks again.
      if (open) spendCard();
      // Reached with the arrows: say the word and take the next one, so a page is
      // cleared at one key a word. Forward is always the way the text reads — the
      // arrows decide which key that is, the queue does not.
      //
      // All five keys move on, not only `k` and `i`. A level means "still learning", so
      // the word stays in the queue; asking for the first one past where you were
      // carries you over it without a case of its own.
      //
      // On pages `onward` stops at the foot of the page before turning it, and a level
      // said on the foot turns it. The level was announced by `setStatus` a moment ago
      // and "Page 2 of 9" now takes the live region over it — accepted: the turn is the
      // larger news, and the word was known to be known.
      if (from) {
        // Nothing further. Close up, and let the header say the chapter is clear.
        if (!goTo(onward(from, true), true, false)) {
          var last = pair;
          leaveQueue();
          // Unless it is already going, which is the last word of a chapter answered
          // from an open card: it gets the same beat as every word before it.
          if (!fading) hideCard();
          if (last && last.focus) last.focus();
        }
        return true;
      }
      // `redraw()` rebuilds the spans, so the element the card was opened for is gone.
      // Find its replacement by lemma in the same sentence rather than holding a
      // reference to a node that is no longer in the page.
      var again =
        pair && pair.parentNode
          ? wordIn(pair, '.w[data-lemma="' + index + '"]')
          : null;
      // Rebuilt before it is spent, so what the reader watches leave is the card with
      // the level they just said on it rather than the question it answered.
      if (again) {
        showCard(again);
        spendCard();
      } else hideCard();
      return true;
    }

    if (pickLevel && chip && !chip.hidden) {
      stopHover();
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
      // The scale says what the pressed step means. "1 2 3" alone had to be explained
      // — the first alpha reader asked — and the names were only ever in tooltips.
      legend: true,
      // The field says what it is for, in the reader's words: the same line is its
      // accessible name, and "Enter text" was the one label on the card that was not.
      placeholder: "Your own meaning",
      onStatus: function (value) {
        setStatus(index, surface, band, value);
        redraw();
        // Rebuilt rather than patched, so every button in the row agrees about which
        // one is now set.
        if (lookedUp) showCard(lookedUp);
        // And then spent, exactly as the same level said with a key is. A level answers
        // the question the card was opened to ask, whichever way it was said — but only
        // the keyboard path knew that, so a level tapped on a phone left the card
        // sitting over the sentence it came from, to be dismissed by a gesture nobody
        // had been told about. Rebuilt first and spent second, so what the reader
        // watches leave is the card with the level they just said on it.
        spendCard();
      },
      onNote: function (text) {
        if (text === noteOf(lemma)) return;
        // Not redrawn here: this commits on the way out of the field, and the click
        // that took focus away is usually a level button that has not fired yet.
        setNote(index, surface, band, text);
      },
      // Pressing Save is an explicit act, and the one moment a redraw is safe. The
      // card comes back with the meaning you wrote where the machine's was, marked as
      // yours — until now that only showed the next time the card was opened.
      onSaved: function () {
        redraw();
        if (lookedUp) showCard(lookedUp);
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

  // How the word you tapped is said, for this occurrence and not for its dictionary
  // form. בצל is batsˈal after "I ate" and btsˈel under a tree; the lemma is the same
  // word in both and the row drawn here is the only thing that knows which was meant.
  function readingOf(word) {
    if (!sounds.length) return "";
    var row = rowOf(word);
    return row ? sounds[row[5]] || "" : "";
  }

  // The token row under a tapped word — the one thing that knows this occurrence's
  // sound, build and grammar, which its dictionary form cannot.
  function rowOf(word) {
    var pair = word.closest ? word.closest(".pair") : null;
    var span = (word.getAttribute("data-bare") || "").split(",");
    if (!pair || span.length !== 2) return null;
    var rows = wordData[pair.getAttribute("data-id")] || [];
    var start = parseInt(span[0], 10);
    var end = parseInt(span[1], 10);
    for (var i = 0; i < rows.length; i++) {
      if (rows[i][0] === start && rows[i][1] === end) return rows[i];
    }
    return null;
  }

  function showCard(word) {
    if (!card) return;
    var index = parseInt(word.getAttribute("data-lemma"), 10);
    var lemma = lemmas[index];
    if (!lemma) return;

    // The old card first, then the band: `hideCard` vacates the band, and taking it
    // before that would hand it straight back to the sheet under the new card.
    hideCard();
    occupy("card");
    lookedUp = word;
    word.classList.add("looked-up");
    card.textContent = "";
    card.appendChild(grabHandle(hideCard));

    // Two different things. The card shows the word as it sits on the page, points and
    // all, because that is what was tapped; the list stores the bare form, so the same
    // word kept with the vowels showing and without is one entry rather than two.
    var shown = word.textContent;
    var surface = bareSurface(word);

    // The word you tapped, then its dictionary form, labelled. Leading with the
    // dictionary form alone meant tapping הציפור answered ציפור with no explanation of
    // why the answer was a different word.
    // Each line the card says carries its own copy: the word as it is here, its dictionary
    // form, its meaning. Three controls rather than one, because "copy the word" meant
    // three different strings to three readers, and the line beside the control says which.
    var headline = document.createElement("span");
    headline.className = "copy-line";
    var head = document.createElement("bdi");
    head.className = "lemma";
    head.setAttribute("lang", language);
    head.textContent = shown;
    headline.appendChild(head);
    headline.appendChild(window.TargumVocab.copyButton(shown, { say: say }));
    card.appendChild(headline);

    // The meaning first — it is the question the tap asked — and everything else
    // under it. The old card made the reader walk four lines of metadata to reach it.
    var meaning = inTarget(document.createElement("span"));
    meaning.className = "meaning";
    var own = noteOf(lemma);
    var sense = own || glosses[index] || "";
    meaning.textContent = sense;
    if (own) meaning.classList.add("mine");
    // Only where there is a meaning to copy: the placeholder below is not one.
    if (sense) {
      meaning.classList.add("copy-line");
      meaning.appendChild(window.TargumVocab.copyButton(sense, { say: say }));
    }
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
        if (!peeked[lemma]) {
          peeked[lemma] = true;
          peek(index, function (found) {
            if (found && lookedUp === word) showCard(word);
          });
        }
        var ask = document.createElement("button");
        ask.type = "button";
        ask.className = "look-up";
        ask.textContent = canAsk() ? "look it up" : "nothing saved";
        ask.disabled = !canAsk();
        ask.onclick = function (event) {
          event.stopPropagation();
          ask.disabled = true;
          ask.classList.add("looking");
          ask.textContent = "looking…";
          lookUp(index, sentenceOf(word), function () {
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
    } else if (!own) {
      // A meaning is up. If no sentence chose it, this one does — see `grounded`.
      ground(index, word, function () {
        if (lookedUp === word) showCard(word);
      });
    }

    // How it is said — the IPA bare, its stress mark being the half of the reading a
    // learner cannot get from the spelling — and, where the page's own recording
    // covers this word, the word itself, said by the voice that read the page.
    var said = readingOf(word);
    var hear = hearFor(word);
    if (said || hear) {
      var saying = document.createElement("span");
      saying.className = "copy-line";
      if (said) {
        // Not `say`: that is the reader's announcer, and the copy controls need it.
        var notation = document.createElement("span");
        notation.className = "said";
        var heard = document.createElement("bdi");
        heard.setAttribute("dir", "ltr");
        heard.textContent = said;
        notation.appendChild(heard);
        saying.appendChild(notation);
      }
      if (hear) saying.appendChild(hear);
      card.appendChild(saying);
    }

    // How the string is put together. A split token names its pieces — that is the
    // line that lets a learner find ולביתו in a dictionary at all — and a plain
    // inflected one names its dictionary form; a surface that is its own lemma says
    // nothing here.
    var row = rowOf(word);
    var built = row && row.length > 7 ? builts[row[7]] || "" : "";
    if (built) {
      var pieces = document.createElement("span");
      pieces.className = "form";
      pieces.appendChild(document.createTextNode("from "));
      mixedLine(pieces, built);
      card.appendChild(pieces);
    } else if (lemma !== surface.toLowerCase() && lemma !== surface) {
      var form = document.createElement("span");
      form.className = "form";
      form.appendChild(document.createTextNode("from "));
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
        // Not `built`: that name is the pieces line above, and `var` is one binding
        // per function — shadowing it here silenced the split caveat for every verb.
        var pattern = document.createElement("bdi");
        pattern.setAttribute("lang", language);
        pattern.textContent = binyan;
        verb.appendChild(pattern);
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

    // The part of speech's own line. A name and a number say which they are — that is
    // all a card can honestly say about either — and a word says the one grammatical
    // fact its kind usually hides from a learner.
    var kindWord = row && row.length > 6 ? KIND_NAMES[row[6]] || "" : "";
    var usage = kindWord || useLine(row && row.length > 8 ? grammarTable[row[8]] || "" : "");
    if (!kindWord) {
      // The paid half of the line, where a gloss has supplied it: the form a learner
      // keeps in front of a verb's parsing, the lying plural after a noun's gender.
      var cite = citations[index] || "";
      var lying = plurals[index] || "";
      if (cite) usage = usage ? cite + " · " + usage : cite;
      if (lying) {
        usage = usage.replace(" · pl.", "");
        usage = (usage ? usage + " · " : "") + "pl. " + lying;
      }
    }
    if (usage) {
      var use = document.createElement("span");
      use.className = "use";
      mixedLine(use, usage);
      card.appendChild(use);
    }

    // Which Hebrew the word belongs to, on the cards where that is worth a line at all:
    // the table is empty wherever the two registers agreed.
    var where = registerLine(registers[index] || "", sourceRegister);
    if (where) {
      var belongs = document.createElement("span");
      belongs.className = "register";
      belongs.textContent = where;
      card.appendChild(belongs);
    }

    // A name or a number takes no scale: neither is vocabulary, and the reader's key
    // for either is `i`. Everything else keeps the editor exactly as it was.
    var level = levelOf(word);
    if (!(row && isName(row))) card.appendChild(statusRow(index, surface, level));

    if (word.classList.contains("split") && !built) {
      // Say so rather than presenting one reading of an ambiguous string as settled —
      // but only on an annotation too old to name the pieces, which say it better.
      var caveat = document.createElement("span");
      caveat.className = "caveat";
      caveat.textContent = "read as a prefix plus a word";
      card.appendChild(caveat);
    }

    card.hidden = false;
    seatNear(card, word.getBoundingClientRect());
    keepOnPage(word);
    lift(word);
  }

  /* --- keeping a phrase ---------------------------------------------------- */

  var chip = document.getElementById("pick-chip");
  // The selection the chip is open on, so an answer that arrives late knows whether it
  // still has a card to restate.
  var picking = null;

  // The piece of the translation the chip is quoting, marked in the translation cell
  // itself while the chip is up, so "in the parallel text" points at something. One at
  // a time, and taken out again the moment the chip goes. §4: iris is the phrase hue,
  // and a highlight is a flat wash.
  var echo = null;

  function unecho() {
    if (echo && echo.parentNode) {
      var parent = echo.parentNode;
      parent.replaceChild(document.createTextNode(echo.textContent), echo);
      parent.normalize();
    }
    echo = null;
  }

  function echoIn(segmentId, piece) {
    unecho();
    var cell = document.querySelector('.pair[data-id="' + segmentId + '"] .tr');
    var words = piece.trim().split(/\s+/);
    if (!cell || !words[0]) return;
    // The words, with whatever whitespace the cell has between them: the answer had one
    // space where the cell may have a line break. Case is forgiven; the words are not.
    var pattern = new RegExp(
      words
        .map(function (word) {
          return word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        })
        .join("\\s+"),
      "i"
    );
    // Text nodes rather than the cell's text: the template wraps opposite-direction runs
    // in <bdi>, and a mark has to be put around characters, not across elements.
    var walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      var found = pattern.exec(node.nodeValue);
      if (!found) continue;
      var rest = node.splitText(found.index);
      rest.splitText(found[0].length);
      echo = document.createElement("mark");
      echo.className = "echo";
      rest.parentNode.replaceChild(echo, rest);
      echo.appendChild(rest);
      return;
    }
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
    if (cell !== cells.plain[segmentId]) {
      start = toBare(cell, start);
      end = toBare(cell, end);
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
  function touchedTokens(picked) {
    return (wordData[picked.segmentId] || []).filter(function (token) {
      return token[0] < picked.end && token[1] > picked.start;
    });
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
    // Cleared before measuring, or the cap a previous word needed is still on and the
    // card measures shorter than it is.
    element.style.maxHeight = "";

    var box = element.getBoundingClientRect();

    // Centred on the word but kept inside the window. A word near the edge of an RTL
    // page is at the right, and a card centred on it would hang off it.
    var wanted = rect.left + rect.width / 2 - box.width / 2;
    var limit = window.innerWidth - box.width - 12;
    element.style.left = Math.max(12, Math.min(wanted, limit)) + window.scrollX + "px";

    // Below where there is room, above where there is not — and never over the word
    // itself, which is the one thing you are looking at while you decide.
    //
    // A long card — a verb with a root, a note, a caveat — can be taller than either
    // side of a word in the middle of the window. Growing upwards from a floor of 8px
    // is what used to put it back over the word. It takes the roomier side instead and
    // scrolls inside whatever that side has.
    var under = window.innerHeight - rect.bottom - 8 - 12;
    var over = rect.top - 8 - 12;
    var below = box.height <= under || under >= over;
    var room = Math.max(below ? under : over, 0);
    if (box.height > room) element.style.maxHeight = room + "px";
    var height = Math.min(box.height, room);
    var top = below ? rect.bottom + 8 : rect.top - 8 - height;
    element.style.top = top + window.scrollY + "px";
  }

  // Named for what it places. It was `place`, which is also what the word queue calls
  // the position it is standing on — and `var place = null` and `function place` in one
  // scope are one binding, not two: the function is hoisted, the assignment runs over it,
  // and every later call throws. Which is what killed dragging a phrase outright, since
  // this is the only thing that takes the chip out of `hidden`.
  function placeChip(rect) {
    occupy("chip");
    seatNear(chip, rect);
  }

  // Beside the thing on a wide window; in the band on a narrow one, where the
  // stylesheet places it and anything `placeNear` last wrote has to be taken back.
  // Not `place` and not `bring`: both are names this scope already has, and a `var`
  // and a `function` with one name are one binding — see the note above `placeChip`.
  function seatNear(element, rect) {
    if (roomy.matches) {
      placeNear(element, rect);
      return;
    }
    element.style.translate = "";
    element.style.transform = "";
    element.style.left = "";
    element.style.top = "";
    element.style.maxHeight = "";
    element.hidden = false;
    // Measured here and laid out here. The observer on the occupant would do both a
    // frame later, but it sees no change by then — this measurement already took it —
    // and the page would stay laid out for a band that is no longer there.
    if (seatFoot()) relayout();
  }

  // The pair an occupant is about, kept on the page. Laying the pages out around a
  // band that has just grown by a card's height moves the page's end up, and the pair
  // the card is about can fall off it — a card about a word that is not on the screen.
  function keepOnPage(element) {
    if (!paged() || !pages.length || !element) return;
    var pair = element.closest ? element.closest(".pair") : null;
    var index = pair ? pairs.indexOf(pair) : -1;
    if (index > -1 && pair.hidden) showPage(pageFor(index, pages), true);
  }

  // The line a card is about, kept above the band the card is in. The scrolling reader
  // reserves nothing — text passes under the band by definition — so the one line that
  // must not is moved, the way the line being spoken is moved clear of the player.
  // Only when it has to be: scrolling a word that is already in front of the reader
  // moves the text under their eyes for no reason. The paged reader lays itself out
  // above the band instead, and has nothing to do here.
  function lift(element) {
    if (roomy.matches || paged() || !element) return;
    var box = element.getBoundingClientRect();
    var floor = window.innerHeight - footHeight() - 12;
    var ceiling = (bar ? bar.getBoundingClientRect().bottom : 0) + 12;
    if (box.bottom <= floor && box.top >= ceiling) return;
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    element.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
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
  // Alignment pairs whole sentences, so nothing on the page says which part of the
  // translation answers to which part of the source, and slicing it proportionally would
  // be confidently wrong. A served page asks (`askPhrase`) and shows this while it waits;
  // a page opened off the disk has only this, and it is labelled as that.
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
    // The phrase card is the same sheet in the same place, and was as hard to put away.
    chip.appendChild(grabHandle(hideChip));
    var phrase = document.createElement("span");
    phrase.className = "phrase";
    var text = document.createElement("bdi");
    text.setAttribute("lang", language);
    text.textContent = parts.title;
    phrase.appendChild(text);
    // The phrase and its reading each copy on their own, as the card's lines do — and
    // the run plays where the page's recording covers it.
    phrase.appendChild(window.TargumVocab.copyButton(parts.title, { say: say }));
    if (parts.hear) phrase.appendChild(parts.hear);
    chip.appendChild(phrase);

    if (parts.reading) {
      var reading = inTarget(document.createElement("span"));
      reading.className = "reading";
      reading.textContent = parts.reading;
      reading.appendChild(window.TargumVocab.copyButton(parts.reading, { say: say }));
      chip.appendChild(reading);
    }
    if (parts.note) {
      var note = document.createElement("span");
      note.className = "source-note";
      note.textContent = parts.note;
      chip.appendChild(note);
    }
    // What kind of unit this run is — an idiom, a construct chain — which is what
    // tells a learner what sort of thing to remember. Absent for a plain run of words.
    if (parts.kind) {
      var kind = document.createElement("span");
      kind.className = "kind";
      kind.textContent = parts.kind;
      chip.appendChild(kind);
    }
    // The form worth keeping, for a run built on a verb: the inflected run a reader
    // dragged is one conjugation of the thing, and unlearnable as such.
    if (parts.cite) {
      var cite = document.createElement("span");
      cite.className = "cite";
      cite.appendChild(document.createTextNode("to keep: "));
      var cited = document.createElement("bdi");
      cited.setAttribute("lang", language);
      cited.textContent = parts.cite;
      cite.appendChild(cited);
      chip.appendChild(cite);
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
        status: TargumVocab.LEARNING[0],
        at: nextOrder(),
      });
      list.push(pick);
      // The span is the phrase and belongs to the source sentence; what it says is a
      // fact about the pair and goes where the words' meanings go.
      keepMeaning(phraseTerm(pick), reading);
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
        note: pick ? noteOn(phraseTerm(pick)) : "",
        placeholder: "Your own meaning",
        onStatus: apply,
        onNote: function (text) {
          var item = ensure();
          writeMeaning(phraseTerm(item), { note: text });
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
      // Except on the field. Preventing the default on mousedown is exactly what stops
      // the browser moving focus, so the blanket that protected the selection also made
      // the note field impossible to click into: the caret never arrived and nothing you
      // typed went anywhere. The mouseup below already ignores everything inside the
      // chip, so the card does not close when the selection collapses under the caret.
      var to = event.target;
      if (to && /^(INPUT|SELECT|TEXTAREA)$/.test(to.tagName)) return;
      event.preventDefault();
    });
  }

  // The chip goes, and the keys go with it. A level pressed at a phrase nobody can see
  // any more would be saved against it all the same, so the two have to be one act
  // rather than two lines that have to be remembered together at four call sites.
  function hideChip() {
    if (chip) chip.hidden = true;
    vacate("chip");
    pickLevel = null;
    picking = null;
    unecho();
  }

  document.addEventListener("mouseup", function (event) {
    if (!chip) return;
    if (chip.contains(event.target)) return;
    var picked = currentSelection();
    if (!picked || !picked.text) {
      hideChip();
      return;
    }
    showPick(picked);
  });

  // Built as a function rather than inline in the handler, because setting a level from
  // the keyboard has to draw the card again to show which one is now set — the editor
  // reads its pressed state once, when it is made.
  function showPick(picked) {
    // Whatever the last card was quoting is not what this one is about.
    unecho();
    var touching = touchedTokens(picked);
    // One and zero are different answers. A drag that touches no word at all is
    // whitespace or punctuation, and it used to fall through to the phrase card — so
    // a click with a few pixels of drift made a phrase out of what the reader
    // experienced as a tap.
    if (!touching.length) {
      hideChip();
      return;
    }
    var token = touching.length === 1 ? touching[0] : null;
    if (token) {
      var index = token[4];
      var lemma = lemmas[index];
      // Dragging across one word is not a phrase, whatever the gesture was. It gets the
      // word's own card, with the same scale and the same field as tapping it.
      var surface = segmentText(picked.segmentId).slice(token[0], token[1]);
      var band = bandOf(token);
      pickCard({
        title: surface,
        reading: noteOf(lemma) || glosses[index] || "",
        note: lemma && lemma !== surface ? "from " + lemma : "",
        hear: hearButton(picked.segmentId, token[0], token[1], "Hear this word"),
        editor: statusRow(index, surface, band),
      });
      placeChip(picked.rect);
      pickLevel = function (status) {
        setStatus(index, surface, band, toggled(index, status));
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

    // The whole sentence has a translation already. A part of one is asked for, once,
    // where the page can ask; until the answer comes — or where it cannot — the words'
    // own glosses stand in, and the caption says which of the three this is.
    var whole = coversSegment(picked);
    var held = whole ? null : phraseHeld(picked);
    var asking = !whole && !held && phrasePending(picked);
    var reading = whole
      ? translationFor(picked.segmentId)
      : held
        ? held.meaning
        : wordByWord(picked);
    var editing = phraseEditor(picked, existing, reading);
    // The scale is for a phrase you have kept. Before that there is one button, Keep:
    // the scale used to keep the phrase the moment any part of it was touched, and an
    // accidental drag plus one press was a phrase on the list nobody had asked for.
    pickCard({
      title: picked.text,
      reading: reading,
      // Status only, never provenance. The captions that told the reader where an
      // answer came from said nothing anyone could act on; what remains says only
      // that an answer is still owed, or that this one is a stand-in built from the
      // words' own glosses.
      note: whole
        ? "the whole sentence"
        : held
          ? ""
          : asking
            ? reading
              ? "word by word — looking…"
              : "looking…"
            : reading
              ? "word by word — the sentence is in parallel"
              : "",
      hear: hearButton(picked.segmentId, picked.start, picked.end, "Hear this phrase"),
      kind: held ? held.kind : "",
      cite: held ? held.citation : "",
      editor: existing > -1 ? editing.element : null,
      action: existing > -1 ? "Remove" : "Keep",
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
        redraw();
        // Kept: the card comes back with the scale on it. Removed: it goes.
        if (existing > -1) hideChip();
        else showPick(picked);
      },
    });
    placeChip(picked.rect);
    picking = picked;
    if (held && held.quoted) echoIn(picked.segmentId, held.meaning);
    if (asking) {
      askPhrase(picked, function (answer, into) {
        // A phrase kept while the answer was in the air was kept with the glosses as its
        // meaning. It takes the real one; the reader's own note is never touched.
        if (answer) {
          var changed = false;
          (picks[picked.segmentId] || []).forEach(function (item) {
            if (item.start < picked.end && item.end > picked.start) {
              item.meaning = answer.meaning;
              keepMeaning(phraseTerm(item), answer.meaning, into);
              changed = true;
            }
          });
          if (changed) {
            remember();
            redraw();
          }
        }
        // And the card, if it is still the card for this selection, says so — or, when
        // nothing came, stops saying it is looking.
        if (picking === picked) showPick(picked);
      });
    }
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
  // The meaning column is in one language, so the header says which. A file that only
  // said "meaning" was a column of Russian under an English word for anyone who read in
  // both and opened it a month later.
  function meaningColumn() {
    var entry = translationData[showing] || {};
    var name = entry.languageName || targetLanguage;
    return name ? "meaning (" + name + ")" : "meaning";
  }

  function exportWords() {
    download(
      title() + " — words.csv",
      ["word", "dictionary form", "difficulty", "how well", meaningColumn()],
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
      ["phrase", meaningColumn().replace("meaning", "reading")],
      phraseEntries().map(function (entry) {
        return [entry.term, entry.meaning || ""];
      })
    );
  }

  function exportCsv() {
    if (prefs.listTab === "phrases") exportPhrases();
    else exportWords();
  }

  /* --- an Anki deck -------------------------------------------------------- */

  /* The two files above are for a spreadsheet. This one is for Anki, which is where
     most people learning Hebrew already keep the words they are drilling, and it carries
     what a card wants that a column does not: the word as it is pointed on the page, the
     sentence it was met in, and for a verb its root and binyan. Tab-separated with
     Anki's own header lines, so it imports as it is — no note type to make first and no
     columns to map — and HTML is on, which is what puts the sentence on a line of its
     own on the back.

     No formula guard here. This is not a spreadsheet's file, and the apostrophe that
     makes a cell inert would be the first character of a flashcard. */

  // The form a card is read in: the vowels without the chant. A Masoretic text ships
  // its accented form and its unaccented one, and the te'amim are for leyning, not
  // for learning a word; every other text has the pointed cell or only the bare one.
  function readingCell(segmentId) {
    return (
      cells.unaccented[segmentId] || cells.pointed[segmentId] || cells.plain[segmentId] || null
    );
  }

  // A run of the bare text, read back out of the reading form: the same offsets
  // carried across the marks, which is how the page draws a pointed span.
  function readingRun(segmentId, start, end) {
    var cell = readingCell(segmentId);
    if (!cell) return "";
    var map = cell === cells.plain[segmentId] ? null : markMap(cell);
    var text = cellText(cell);
    var from = map ? map[Math.min(start, map.length - 1)] : start;
    var to = map ? map[Math.min(end, map.length - 1)] : end;
    return text.slice(from, to);
  }

  // Where a word is first met in this text, which is the sentence its card quotes.
  function firstMeeting(lemma) {
    var ids = Object.keys(wordData);
    for (var i = 0; i < ids.length; i++) {
      var rows = wordData[ids[i]] || [];
      for (var j = 0; j < rows.length; j++) {
        if (lemmas[rows[j][4]] === lemma) return { segmentId: ids[i], token: rows[j] };
      }
    }
    return null;
  }

  // What goes on the cards: one per entry the list is showing, in the list's order.
  function ankiCards(kind) {
    if (kind === "phrases") {
      return phraseEntries().map(function (entry) {
        var pick = (picks[entry.segmentId] || [])[entry.index] || {};
        return {
          front: readingRun(entry.segmentId, pick.start || 0, pick.end || 0) || entry.term,
          meaning: entry.meaning || "",
          sentence: cellText(readingCell(entry.segmentId)),
          root: "",
          binyan: "",
        };
      });
    }
    return wordEntries().map(function (entry) {
      var met = firstMeeting(entry.lemma);
      var index = met ? met.token[4] : -1;
      return {
        front: met ? readingRun(met.segmentId, met.token[0], met.token[1]) : entry.term,
        // What the reader wrote or kept first; failing that, the meaning the page
        // shipped, which is what the card beside the word shows.
        meaning: entry.meaning || (index >= 0 && glosses[index]) || "",
        sentence: met ? cellText(readingCell(met.segmentId)) : "",
        root: (index >= 0 && roots[index]) || "",
        binyan: (index >= 0 && binyanim[index]) || "",
      };
    });
  }

  // A field of the file. HTML is on, so the text is escaped as HTML; a tab or a line
  // break inside a field would be read as the next field or the next card.
  function ankiField(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/\t/g, " ")
      .replace(/\r?\n/g, "<br>");
  }

  // The file itself, from a deck's name and its cards. Pure, so a test can hold it.
  //
  // Front: the word. Back: what it means, the sentence under it in the language it is
  // in, and a verb's root and binyan on a third line. Tags: targum, and the text, so a
  // deck merged into a bigger one can still be told apart. The deck is filed under
  // `targum::`, which is how Anki nests, so every text's deck sits under one parent.
  function ankiText(name, cards) {
    var lines = [
      "#separator:tab",
      "#html:true",
      "#notetype:Basic",
      "#deck:targum::" + name.replace(/::/g, ":"),
      "#columns:Front\tBack\tTags",
      "#tags column:3",
    ];
    var tag = "targum::" + name.replace(/\s+/g, "-");
    cards.forEach(function (card) {
      var back = [ankiField(card.meaning)];
      if (card.sentence) {
        back.push(
          '<span lang="' + language + '" dir="auto">' + ankiField(card.sentence) + "</span>"
        );
      }
      if (card.root || card.binyan) {
        var verb = [];
        if (card.root) verb.push("root " + ankiField(card.root.split("").join("\u05be")));
        if (card.binyan) verb.push(ankiField(card.binyan));
        back.push(verb.join(" \u00b7 "));
      }
      lines.push([ankiField(card.front), back.join("<br>"), "targum " + tag].join("\t"));
    });
    return lines.join("\n") + "\n";
  }

  function exportAnki() {
    var kind = prefs.listTab === "phrases" ? "phrases" : "words";
    var text = ankiText(title(), ankiCards(kind));
    var blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = title() + " \u2014 " + kind + ".anki.txt";
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

  /* --- keeping your place -------------------------------------------------- */

  // A scroll position is a pixel offset from the top of the document, and each of the
  // controls on the bar sets the same chapter at a different height: interlinear gives
  // every pair a line of translation and a blank line after it, source takes both away,
  // larger type takes more room per line, the list takes a column of the width. Keep the
  // offset across a change like that and you have kept a place in the document that has
  // nothing to do with the sentence you were reading — the taller layout carries you
  // backwards, the shorter one carries you on, and the further into a chapter you are the
  // further off it lands. What has to be held is the sentence; the offset is worked out
  // again from wherever the sentence has gone.
  //
  // Held before the change and given back after it, by every control that re-lays the
  // text out. `settle` fades the page over the difference, so what a reader sees is the
  // same words in a new shape rather than a jump to somewhere else in the chapter.

  // Nothing to hold before the opening pass: there is no layout yet, and asking where
  // anything is before there is forces the one the reader is waiting on.
  var living = false;

  // The top of the reading area. The bar is sticky, so the top of the window is not the
  // top of the text.
  var ceilingSaid = "";
  function ceiling() {
    var band = (bar ? bar.getBoundingClientRect().height : 0) + 16;
    // Written where the stylesheet can read it: `scroll-margin-block-start` used to say
    // 4rem while this measured the truth, and on a narrow window the bar wraps past
    // 4rem — so `scrollIntoView` landed the sentence behind it. One measurement, two
    // readers.
    var px = band + "px";
    if (px !== ceilingSaid) {
      ceilingSaid = px;
      document.documentElement.style.setProperty("--ceiling", px);
    }
    return band;
  }

  // The sentence in the middle of the reading area, which is where a reader's eye is
  // rather than where the text happens to begin. Held instead of the sentence at the top
  // of the window — which is the one they have just finished — a change of layout leaves
  // them looking at the words they were looking at, with as much of the page they have
  // read still above as there was before.
  function middle() {
    var top = ceiling();
    var eye = top + (window.innerHeight - top) / 2;
    // Shown pairs only. In page mode every pair off the current page is `hidden`, and a
    // hidden element measures zero at the origin — so a walk over all of them finds
    // nothing that reaches the eye and falls out of the bottom of the loop.
    var last = null;
    for (var n = 0; n < pairs.length; n++) {
      if (pairs[n].hidden) continue;
      last = pairs[n];
      if (pairs[n].getBoundingClientRect().bottom >= eye) return pairs[n];
    }
    // Nothing reaches the middle: the end of a chapter, where the last screenful is
    // mostly the space under it — or a short page, whose last line stops above the
    // halfway mark. The answer is the last line in front of the reader, and it has to be
    // the last *shown* one: reaching past the page to the end of the text told
    // `relayout` the reader was on the final page, and the font arriving turned every
    // dialogue to its last page a moment after it opened.
    return last;
  }

  // What the last change of layout was held by — the sentence, and the word in it where
  // there was one — kept until the reader moves away from it themselves.
  //
  // Every control on the bar can be pressed twice, and without this each press works the
  // place out afresh. Two things go wrong when it does. A sentence that loses its
  // translation line is half the height it was, so the middle of the window falls past
  // its end onto the one after it, and half a dozen presses walk the page down a
  // paragraph the reader never scrolled. And a change of layout puts away the card a tap
  // opened, so the word the reader is plainly looking at stops being a word the page
  // knows about after the first press. Held, one place answers for the whole run of them.
  //
  // The word by name rather than by node: a redraw replaces every span in the cell, and
  // `refind` is what turns the name back into whatever is on the page now.
  var resting = null;
  var restingAt = 0;
  // The element wearing the mark, so it can be taken off again without searching for it.
  var marked = null;

  // The place, said on the page. Being put back where you were is no use if you cannot
  // see where that is: the reader has just been carried across a change of layout, or
  // back into a text they left yesterday, and asking them to read for the line they were
  // on is asking them to do the work the page was supposed to have done.
  //
  // The word where the place is a word, in the ink of a selection — §8, and the one
  // treatment in the system loud enough to find in a paragraph at a glance. The sentence
  // where it is not, lifted exactly the way the pointer lifts the sentence under it: a
  // reader already knows that band means "this one", so it needs no explaining.
  function rest(pair, lemma, bare) {
    resting = { pair: pair, lemma: lemma, bare: bare };
    restingAt = window.scrollY;
    unmark();
    // By name rather than by node: a redraw is what draws interlinear, and it replaces
    // every span in the cell — including the one that was handed in here.
    marked = refind(resting) || pair;
    marked.classList.add("here");
    // A change of layout that moved nothing moves nothing to scroll, and a scroll is what
    // would otherwise have written this down.
    note();
  }

  function unmark() {
    if (marked) marked.classList.remove("here");
    marked = null;
  }

  // The reader has put themselves somewhere: scrolled off the place, tapped a word,
  // walked the arrows on. Whatever the page was holding for them, they are not in it any
  // more, and a band left sitting on a sentence nobody is reading is furniture.
  function forget() {
    resting = null;
    unmark();
  }

  // Where the reader is, written down as they go — the anchor, and the line of the window
  // it sits on. A resize is the one change of layout this file cannot measure first: the
  // browser reflows and then says so, and by the time it says so every line has rewrapped
  // and the offset that meant "this sentence" means somewhere else in the chapter. This
  // is the last thing that was true before that happened.
  //
  // Cheap where it has to be: a reader on a word is answered by the word, and only a
  // reader who is not pays for the walk down the pairs. Once a frame at most, beside the
  // marking pass that is already reading the same boxes.
  var seen = null;

  function note() {
    var here = anchor();
    if (!here) return;
    seen = {
      pair: here.pair,
      lemma: here.word ? here.word.getAttribute("data-lemma") : null,
      bare: here.word ? here.word.getAttribute("data-bare") : null,
      top: Math.round((here.word || here.pair).getBoundingClientRect().top),
    };
  }

  var noting = false;

  window.addEventListener(
    "scroll",
    function () {
      // `keep` scrolls the page itself, and that is the anchor being honoured rather than
      // the reader leaving it: its scroll lands on the offset recorded beside it, to the
      // pixel. Anything else is the reader, and the sentence they left is not their place
      // any more.
      if (Math.abs(window.scrollY - restingAt) > 1) forget();
      if (noting) return;
      noting = true;
      requestAnimationFrame(function () {
        noting = false;
        note();
      });
    },
    { passive: true }
  );

  // Where the reader is, in two answers of falling exactness: the word they are on, and
  // failing that the sentence in front of them.
  //
  // The word comes first whether the arrows put them on it or a tap did. Walking a
  // chapter and asking what a word means are different acts, which is why `standing` and
  // `lookedUp` are kept apart everywhere else in this file — but they are the same act as
  // far as a place is concerned. Both say the reader's attention is on one word, and a
  // word is exact where a sentence is a paragraph's worth of guess.
  function anchor() {
    var word = standing && standing.parentNode ? standing : null;
    if (!word && lookedUp && lookedUp.parentNode) word = lookedUp;
    var pair = word ? word.closest(".pair") : null;
    var top = ceiling();
    var box = pair ? pair.getBoundingClientRect() : null;
    // Unless they have scrolled away from it, in which case the word is somewhere they
    // have been and what is in front of them is the text.
    if (!box || box.bottom < top || box.top > window.innerHeight) {
      var rested = resting && resting.pair.parentNode ? resting : null;
      word = rested ? refind(rested) : null;
      pair = rested ? rested.pair : middle();
    }
    return pair ? { pair: pair, word: word } : null;
  }

  function hold() {
    if (!living) return null;
    var here = anchor();
    if (!here) return null;
    var word = here.word;
    return {
      pair: here.pair,
      top: here.pair.getBoundingClientRect().top,
      word: word,
      wordTop: word ? word.getBoundingClientRect().top : 0,
      // A redraw rebuilds every span in the cell, so the word is held as the two offsets
      // that name it as well: the node itself is about to be replaced.
      lemma: word ? word.getAttribute("data-lemma") : null,
      bare: word ? word.getAttribute("data-bare") : null,
    };
  }

  // The same sentence, back on the same line of the window. Not the middle of it: the eye
  // is already somewhere, and moving what it is reading to where the page would rather
  // have it is a second movement the reader did not ask for. What they asked for was the
  // translation off, or the type a step larger — the words in front of them are supposed
  // to stay in front of them. It is also what stops four presses of A+ from walking a
  // sentence up the window.
  //
  // Never smooth: the change of layout is already carried by `settle`, and a scroll
  // animated on top of it would be a second movement saying the same thing. Where the
  // page cannot move that far — the last screenful of a chapter that has just become
  // shorter — the browser stops at the end, which is the honest answer and the one it
  // gives a scrollbar.
  function keep(held) {
    if (!held || !held.pair.parentNode || !window.scrollTo) return;
    var word = held.word && held.word.parentNode ? held.word : null;
    // A word in a cell the change has hidden — the vowels swap one cell for the other —
    // measures as nothing at all, and its sentence is the honest fallback.
    var box = word ? word.getBoundingClientRect() : null;
    if (box && !box.width && !box.height) {
      word = null;
      box = null;
    }
    var moved = Math.round(
      (box ? box.top : held.pair.getBoundingClientRect().top) - (word ? held.wordTop : held.top)
    );
    if (moved) window.scrollTo(0, window.scrollY + moved);
    // What this change was held by, until the reader scrolls off it. The offset inside
    // `rest` is read back rather than worked out: at the end of a chapter the browser
    // stops where the page stops, which is a shorter move than the one that was asked for.
    rest(held.pair, held.lemma, held.bare);
  }

  // The held word again, after a redraw. `markSegment` rebuilds every span in the cell, so
  // the node held before the change is detached and the word survives only as the two
  // offsets that name it.
  function refind(held) {
    if (!held || !held.bare) return null;
    var segmentId = held.pair.getAttribute("data-id");
    // The cell on show, which is the one `markPair` drew: the others keep whatever spans
    // they had when they were last visible, and they are the wrong page's.
    var cell = shownCell(segmentId);
    if (!cell) return null;
    // Its spans may not have been drawn in this pass at all; only a screenful is marked.
    markPair(held.pair);
    return cell.querySelector(
      '.w[data-lemma="' + held.lemma + '"][data-bare="' + held.bare + '"]'
    );
  }

  // The ring, the tab stop and the focus, moved on to it. Without this the reader is
  // standing on nothing in the middle of a walk, in the mode they have just asked for —
  // the queue itself survives, because `place` is offsets rather than a node.
  function restand(word) {
    if (!word || !standing || word === standing) return;
    standing.classList.remove("queued");
    standing.removeAttribute("tabindex");
    standing = word;
    word.classList.add("queued");
    word.setAttribute("tabindex", "0");
    if (word.focus) word.focus({ preventScroll: true });
  }

  // The place put back a second time, against the page the redraw has left behind. Marks
  // are paint and move nothing, but interlinear is drawn by the same pass and a line with
  // a translation under it is taller than the line `keep` measured a moment earlier — so
  // the first `keep` is against a page that is about to change under it. Cheap: the
  // second one has nothing to do wherever the first was right, and scrolls by nothing.
  function putBack(held) {
    if (!held) return;
    var word = refind(held);
    restand(word);
    keep(
      word
        ? {
            pair: held.pair,
            top: held.top,
            word: word,
            wordTop: held.wordTop,
            lemma: held.lemma,
            bare: held.bare,
          }
        : held
    );
  }

  /* --- the place you left it in --------------------------------------------- */

  // `hold` and `keep` carry a place across a change of layout, in the same page and the
  // same second. This carries one across a closed tab: what you were reading when you
  // left is what is in front of you when you come back, rather than the first line of a
  // chapter you are forty verses into.
  //
  // Kept per page of a text rather than per text. A book's chapters share a document id,
  // and one place for all of them would hand somebody returning to chapter five the
  // sentence they left off in chapter one — which is not on the page to scroll to, so
  // what they would actually get is nothing at all. The first segment on the page names
  // the page, and it is the build's own id rather than a filename: the same text built
  // again under another name is still the same reading.
  var PLACE = "targum:place";
  var placeKey =
    documentId + "/" + (pairs.length ? pairs[0].getAttribute("data-id") : "");

  // A hundred pages. Left unbounded, a book of a hundred and fifty chapters read twice
  // would sit in the store for good; a reader coming back to a page they left half-read
  // comes back to it within a hundred pages of reading, or they are not coming back.
  var PLACES = 100;

  // On the way out. Written from the same anchor a change of layout holds, so leaving a
  // reader and switching it to source keep the same place by the same rule: the word if
  // there is one, the sentence in the middle of the window if there is not.
  function leavePlace() {
    var here = living ? anchor() : null;
    if (!here) return;
    var span = here.word ? here.word.getAttribute("data-bare") || "" : "";
    try {
      var all = read(PLACE, "{}");
      if (!here.word && window.scrollY <= 2) {
        // A text the reader never moved in has no place in it: they opened it and left it
        // where it opened, and where it opens is where it opens again. Kept as the
        // absence of a record rather than as a record of the top, so that a place from an
        // earlier reading is not left standing over a reading that went nowhere.
        delete all[placeKey];
      } else {
        all[placeKey] = {
          segment: here.pair.getAttribute("data-id"),
          // The word by where it starts in the sentence, not by the node: the page it was
          // drawn on is about to stop existing. One offset rather than the pair, because
          // a saved phrase slices a word into several spans and any piece of it will do.
          word: span.split(",")[0],
          // And how far down the window it sat. A place is a sentence and a height: put
          // back at the top of the text, or in the middle of it, the same sentence reads
          // as a page that has been scrolled since — the reader has to find their line
          // inside it again. Put back on the line it was on, there is nothing to find.
          top: Math.round(
            (here.word || here.pair).getBoundingClientRect().top
          ),
          at: Date.now(),
        };
      }
      Object.keys(all)
        .sort(function (a, b) {
          return (all[b].at || 0) - (all[a].at || 0);
        })
        .slice(PLACES)
        .forEach(function (stale) {
          delete all[stale];
        });
      targumKeep(PLACE, JSON.stringify(all));
    } catch (e) {}
  }

  // Three, and the third is the one that survives being carried.
  //
  // A place written on the way out is written at the one moment with no time left to
  // keep it. The durable store commits, but a commit is not instant, and a navigation
  // arriving in the same breath beats it — which is why the place was the key this
  // browser lost most often, and why it stayed the leftover after everything else was
  // safe (targum-internal#137). Measured through the reader's own write path: writes
  // made with time to settle came down from 2.20% lost to 0.40%, and what was left was
  // this pattern, write-then-leave, which is the place's alone.
  //
  // So it is also written while the reader is still reading, a second after they stop
  // moving. A second is long enough that a scroll does not write on every frame of
  // itself, and short enough that the place on disk is the place they are at. The two
  // events below stay: they are what catches a reader who moved and left inside the
  // second, and by then this has usually already saved them.
  var settling = null;

  function keepPlace() {
    if (settling) window.clearTimeout(settling);
    settling = window.setTimeout(function () {
      settling = null;
      leavePlace();
    }, 1000);
  }

  window.addEventListener("scroll", keepPlace, { passive: true });
  window.addEventListener("pagehide", leavePlace);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") leavePlace();
  });

  // The middle of the reading area, for something that is not on the screen at all.
  // `bring` is the same movement for the word queue and will not do here: it leaves a
  // word where it is when it is already in view, which is right when the arrows are
  // walking along a line and wrong on a page that has just opened, where nothing is
  // where the reader left it and the point is to put one thing back.
  function centre(word, pair) {
    if (!pair.getBoundingClientRect || !window.scrollTo) return;
    var top = ceiling();
    // The same middle `middle()` reads a place off, so a sentence put here is the
    // sentence the next change of layout finds.
    var eye = top + (window.innerHeight - top) / 2;
    var tall = pair.getBoundingClientRect().height > window.innerHeight - top - 16;
    // The rule `bring` walks by: the sentence moves and the word decides, unless the
    // sentence is taller than the window, when centring it would put the word itself off
    // the screen the scroll was meant to bring it on to.
    var target = tall && word ? word : pair;
    var box = target.getBoundingClientRect();
    // A sentence too tall to centre goes to the top of the text instead, which is where
    // it would sit if you had scrolled to it yourself.
    var wanted = tall && !word ? top : eye - box.height / 2;
    window.scrollTo(0, Math.max(0, Math.round(window.scrollY + box.top - wanted)));
  }

  // Back on the line of the window it was on. Where that line is no longer one this
  // window has — resized, or a phone turned, since it was written down — the middle
  // instead, which is a line every window has.
  //
  // What counts as gone differs for the two. A word has to end up whole and in the clear:
  // it is the thing the reader is being asked to find again, and half of it under the
  // sticky bar is not found. A sentence only has to have some of itself on the screen —
  // a paragraph taller than the window can never be wholly on it, and centring one every
  // time the window moved would throw a reader to its first line for no reason.
  function toLine(word, pair, top) {
    var box = (word || pair).getBoundingClientRect();
    var floor = ceiling();
    var fits =
      typeof top === "number" &&
      (word
        ? top >= floor && top + box.height <= window.innerHeight - 12
        : top < window.innerHeight - 12 && top + box.height > floor);
    if (!fits) return centre(word, pair);
    window.scrollTo(0, Math.max(0, Math.round(window.scrollY + box.top - top)));
  }

  // On the way back in: the same words on the same line of the window as when the tab was
  // closed, so that coming back reads as picking the page up rather than as arriving
  // somewhere near where you were. The mark is what says which line it is.
  function resume() {
    // Not over a position the browser has already chosen. A reload and the back button
    // both restore a scroll of their own, and both are the better answer: they are where
    // this reader was a moment ago rather than where they were last time.
    if (location.hash || window.scrollY > 2) return;
    var kept = read(PLACE, "{}")[placeKey] || {};
    var pair = kept.segment ? pairBySegment[kept.segment] : null;
    if (!pair) return;
    var word = null;
    if (/^\d+$/.test(String(kept.word || ""))) {
      // Its spans may never have been drawn: only a screenful is marked up front, and
      // that screenful is the top of the chapter, which is where the reader is not.
      markPair(pair);
      word = wordIn(pair, '.w[data-bare^="' + kept.word + ',"]');
    }
    toLine(word, pair, kept.top);
    // The sentence they came back to is the sentence the first press of a mode button
    // should hold, rather than whatever the middle of the window works out to.
    rest(
      pair,
      word ? word.getAttribute("data-lemma") : null,
      word ? word.getAttribute("data-bare") : null
    );
    // And the screenful that is now in front of them, which is not the one `redraw` drew.
    markVisible();
  }

  /* --- the window changing shape -------------------------------------------- */

  // A resize moves everything at once: the column changes width, every line rewraps, and
  // the sentence that was in front of the reader is somewhere else on the page. It is the
  // same failure `hold` and `keep` exist to prevent, arriving through the one door they
  // cannot stand at — so it is answered from `seen`, which was written down before the
  // reflow, rather than from a page that has already changed.
  //
  // A drag on a window corner fires this by the dozen. One pass a frame, the way the
  // marking keeps up with a scroll: the work is a scroll and two placements, and doing it
  // sixty times a second would fight the resize rather than follow it.
  var fitting = false;

  window.addEventListener("resize", function () {
    if (fitting) return;
    fitting = true;
    requestAnimationFrame(function () {
      fitting = false;
      refit();
    });
  });

  function refit() {
    seatFoot();
    relayout();
    if (living && seen && seen.pair.parentNode) {
      toLine(refind(seen), seen.pair, seen.top);
      // And say where that is. A reader who has just watched every line on the page move
      // has the least to go on of anybody, which is exactly when the mark earns its keep.
      rest(seen.pair, seen.lemma, seen.bare);
    }
    relay();
  }

  // The cards, back beside what they are about. Both are positioned in document
  // coordinates — absolute, so they scroll with the word rather than hanging off the
  // bottom of the window — which is right until the word moves without the page
  // scrolling, and a resize is exactly that. Left alone, a card ends up sitting over the
  // very word it was opened for, which `placeNear` is otherwise careful never to do.
  function relay() {
    if (card && !card.hidden && lookedUp && lookedUp.parentNode) {
      seatNear(card, lookedUp.getBoundingClientRect());
    }
    if (chip && !chip.hidden) {
      var picked = currentSelection();
      // A selection the reflow has collapsed is not a phrase any more, and a chip about
      // nothing is a chip in the way.
      if (picked && picked.text) placeChip(picked.rect);
      else hideChip();
    }
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

  // Under 46rem the columns are one, so parallel and interlinear are the same page and
  // only one of them is offered: a parallel choice brought here — from a wide window,
  // or by narrowing this one — is read as interlinear.
  var oneColumn = window.matchMedia("(max-width: 46rem)");

  function foldParallel() {
    if (prefs.mode !== "parallel" || !oneColumn.matches) return false;
    prefs.mode = "inter";
    return true;
  }

  if (oneColumn.addEventListener) {
    oneColumn.addEventListener("change", function () {
      if (foldParallel()) {
        applyMode();
        save();
      }
    });
  }

  function applyMode() {
    foldParallel();
    var held = hold();
    body.className = body.className.replace(/\bmode-\w+/g, "").trim();
    body.classList.add("mode-" + prefs.mode);
    Array.prototype.forEach.call(document.querySelectorAll("[data-mode]"), function (button) {
      button.classList.toggle("on", button.getAttribute("data-mode") === prefs.mode);
    });
    placeSlide();
    hideCard();
    // Before anything is drawn into the new layout: `redraw` marks the screenful it can
    // see, and a screenful measured before the scroll is a screenful of the part of the
    // chapter the reader has just been carried off.
    keep(held);
    if (interlinear() !== (drawnFor === "inter")) {
      redraw();
      putBack(held);
    }
    drawnFor = prefs.mode;
    relay();
    relayout();
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
  // What a screen reader hears when the switch is pressed. The button's own state is
  // `aria-pressed`; this says what changed.
  var FORM_SAID = ["Bare text.", "Vowel points."];

  function toggleVowels() {
    if (!hasNikkud) return;
    prefs.nikkud = !prefs.nikkud;
    applyNikkud();
    say(FORM_SAID[prefs.nikkud ? 1 : 0]);
    save();
  }

  // The chanting marks. Same shape as the vowels above, one position lower: it moves
  // between two pointed cells and does nothing at all with the vowels off.
  var TAAMIM_SAID = ["Vowels only.", "Chanting marks."];

  function toggleTaamim() {
    if (!hasTaamim) return;
    setTaamim(!prefs.taamim);
  }

  function setTaamim(on) {
    if (!hasTaamim) return;
    prefs.taamim = !!on;
    applyTaamim();
    say(TAAMIM_SAID[prefs.taamim ? 1 : 0]);
    save();
  }

  // `settled` false is the first call of the load, where the vowels are about to draw
  // the page anyway: this one only has to leave the state and the buttons right, and a
  // second full redraw before anybody has seen the first is a lap of the whole text.
  function applyTaamim(settled) {
    body.classList.toggle("taamim", !!prefs.taamim);
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-taamim-toggle]"),
      function (button) {
        button.classList.toggle("on", !!prefs.taamim);
        button.setAttribute("aria-pressed", prefs.taamim ? "true" : "false");
      }
    );
    if (settled === false) return;
    var held = hold();
    hideCard();
    // Two cells again, and the accented one is the taller: the same reason the vowels
    // hold the reader's place across the swap.
    keep(held);
    redraw();
    putBack(held);
    relay();
    relayout();
  }

  // For a page that frames this one. The parasha landing page carries the control a
  // reader arriving from outside sees, and it is the same origin, so it calls in here
  // rather than reaching into the markup and clicking a button that may not be drawn.
  window.targumReader = window.targumReader || {};
  window.targumReader.setTaamim = setTaamim;
  window.targumReader.hasTaamim = function () {
    return hasTaamim;
  };
  window.targumReader.taamim = function () {
    return !!prefs.taamim;
  };

  function applyNikkud() {
    var held = hold();
    if (prefs.nikkudBy && documentId) prefs.nikkudBy[documentId] = !!prefs.nikkud;
    body.classList.toggle("nikkud", !!prefs.nikkud);
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-nikkud-toggle]"),
      function (button) {
        button.classList.toggle("on", !!prefs.nikkud);
        button.setAttribute("aria-pressed", prefs.nikkud ? "true" : "false");
      }
    );
    hideCard();
    // Pointed and bare are two cells, not one cell restyled, and a pointed line is the
    // taller of the two — so putting the vowels on moves everything above you as well.
    keep(held);
    redraw();
    putBack(held);
    relay();
    relayout();
  }

  /* --- pages, not a scroll --------------------------------------------------
   *
   * A page is a contiguous run of pairs, and turning one is deciding which run to show:
   * the pairs outside it are hidden. Nothing reflows inside a pair, so the two-column
   * parallel grid paginates as rows, and print un-hides them in one rule. Not fixed at
   * build time — how many pairs fit depends on the window, the type size, the leading,
   * the mode and the vowels, and a reader off a disk cannot be rewritten. Measured
   * once per layout with everything shown, which is what the scrolling page has always
   * cost, and never again until something moves.
   *
   * Nothing here is fixed-height or overflow-hidden. The run fits the room by
   * construction; a single pair taller than the room gets a page of its own and that
   * page scrolls, which is the honest answer, and the last page scrolls to reach the
   * pager and the offer at the foot.
   */
  var turn = document.getElementById("turn");
  // The player floats at the foot too, so a page has to be measured around it the same
  // way it is measured around the arrows. Read here rather than passed in: it is put
  // away and brought back while the page is open, and `room` asks it each time.
  var scenePlayer = document.getElementById("player");
  var pageOf = document.getElementById("page-of");
  var pager = document.querySelector(".pager[data-chapter]");
  var pageKey = documentId + "#" + (pager ? pager.getAttribute("data-chapter") : "1");
  var pages = [];
  var current = 0;
  var paging = false;

  function paged() {
    return !!prefs.paged && pairs.length > 0;
  }

  // Which pairs share a page, from where each one starts and how tall it is. Pure: the
  // arithmetic is decided here so it can be tested without a browser to lay anything
  // out. A pair too tall for the room is a page on its own rather than a page nobody
  // can turn to.
  function boundariesFrom(tops, heights, room, opens, glue) {
    var out = [];
    if (!tops.length) return out;
    var start = 0;
    var base = tops[0];
    for (var n = 0; n < tops.length; n++) {
      var bottom = tops[n] + heights[n] - base;
      // A section starts a page. Without this the weekly's section links turned to the
      // page a section is *in*, which can begin halfway through the one before it — so
      // the reader arrived somewhere near sport and had to go looking for it. A section
      // beginning a page is what a paper does anyway, and it is the only arrangement in
      // which "take me to sport" and what the eye lands on are the same thing.
      var forced = opens && opens[n];
      if ((forced || bottom > room) && n > start) {
        // A heading closes nothing. On a short window the budget shrinks until a
        // chapter's plate was a page of its own — "1 of 15", and the first of the
        // fifteen said only the title. The cut walks back so a plate opens the page
        // its text is on; if that leaves nothing at all, the page overflows instead,
        // the same way a pair too tall for the room already does.
        var cut = n;
        while (glue && cut > start && glue[cut - 1]) cut--;
        if (cut === start) continue;
        out.push([start, cut - 1]);
        start = cut;
        base = tops[cut];
      }
    }
    out.push([start, tops.length - 1]);
    return out;
  }

  function pageFor(index, list) {
    for (var n = 0; n < list.length; n++) {
      if (index >= list[n][0] && index <= list[n][1]) return n;
    }
    return 0;
  }

  // What is left of the window under the bar and above whatever floats at its foot.
  // Under the bar, and above the arrows, the player, the words tab and the sheet — the
  // whole band they stand in, from the top edge of the highest of them to the foot of
  // the window, not their own heights: a page is laid out so that no line of it can end
  // up under any of them.
  //
  // This is why the player can float without covering anything. A control fixed over a
  // page of text either takes its room out of the layout or takes it out of the reading,
  // and the second is not a trade a reader agreed to.
  //
  // The sheet only where it is one. On a wide window the list is a column from the bar
  // to the foot, and measuring that would leave the page its 160px floor and nothing
  // more. And the sheet is measured first: the arrows and the player are lifted by its
  // height, so where they stand is only right once the stylesheet has been told it.
  function room() {
    seatFoot();
    var top = bar ? bar.getBoundingClientRect().bottom : 0;
    var foot = 0;
    // On a wide window the occupants are not in the band: the list is a column from
    // the bar to the foot, and measuring that would leave the page its 160px floor and
    // nothing more; a card sits beside its word.
    [turn, scenePlayer, listTab].forEach(function (thing) {
      if (!thing || thing.hidden) return;
      var box = thing.getBoundingClientRect();
      if (box.height) foot = Math.max(foot, window.innerHeight - settledTop(thing, false) + 12);
    });
    if (!roomy.matches) {
      occupants().forEach(function (thing) {
        if (!thing || thing.hidden) return;
        var box = thing.getBoundingClientRect();
        if (box.height) foot = Math.max(foot, window.innerHeight - settledTop(thing, true) + 12);
      });
    }
    return Math.max(160, window.innerHeight - top - foot - 24);
  }

  function paginate() {
    if (!paged()) return;
    pairs.forEach(function (pair) {
      pair.hidden = false;
    });
    var tops = [];
    var heights = [];
    // Which pairs open a section: a heading of the top level, and never the first pair,
    // which would only make an empty page before it. Only the weekly has more than one
    // in a file — a book's chapters are already separate files — so this changes where
    // pages fall there and nowhere else.
    var opens = [];
    pairs.forEach(function (pair, index) {
      var box = pair.getBoundingClientRect();
      tops.push(box.top + window.scrollY);
      heights.push(box.height);
      opens.push(index > 0 && !!pair.querySelector("h1"));
    });
    // Everything above the first pair — a chapter's plate, the margin under the bar — is
    // on every page and not only the first: `showPage` hides pairs and nothing else. Left
    // out of the budget, every page runs past the foot by the height of the plate, which
    // is what put the last verse of a chapter under the turning arrows and, once there
    // was one, under the player.
    var over = bar ? bar.getBoundingClientRect().bottom + window.scrollY : window.scrollY;
    var lead = tops.length ? Math.max(0, tops[0] - over) : 0;
    // Which pairs are plates rather than text — the built page marks them `head`.
    var glue = pairs.map(function (pair) {
      return pair.classList.contains("head");
    });
    pages = boundariesFrom(tops, heights, Math.max(160, room() - lead), opens, glue);
    if (!pages.length) pages = [[0, pairs.length - 1]];
  }

  function showPage(n, quiet) {
    if (!paged() || !pages.length) return;
    current = Math.max(0, Math.min(pages.length - 1, n));
    var range = pages[current];
    for (var i = 0; i < pairs.length; i++) pairs[i].hidden = i < range[0] || i > range[1];
    body.classList.toggle("last-page", current === pages.length - 1);
    // The back arrow does nothing on the first page, and a button that does nothing
    // should say so — dimmed by the stylesheet, named inert for a screen reader. The
    // forward arrow stays live on the last page: it goes on to the next chapter.
    body.classList.toggle("first-page", current === 0);
    var back = document.querySelector('.turn button[data-turn="-1"]');
    if (back) back.setAttribute("aria-disabled", current === 0 ? "true" : "false");
    if (pageOf) pageOf.textContent = current + 1 + " of " + pages.length;
    for (i = range[0]; i <= range[1]; i++) markPair(pairs[i]);
    if (!quiet && window.scrollTo) window.scrollTo(0, 0);
    // A turned page replaces everything on the screen; the live region is how anyone
    // not looking at it finds out. Quiet turns are restores, not news.
    if (!quiet) say("Page " + (current + 1) + " of " + pages.length);
    if (prefs.pageBy) {
      prefs.pageBy[pageKey] = pairs[range[0]].getAttribute("data-id") || "";
      save();
    }
    // For the chapter prefetch, which lives in its own scope and reads the scroll.
    if (typeof CustomEvent === "function") {
      document.dispatchEvent(new CustomEvent("targum:page"));
    }
  }

  function turnTo(pair) {
    if (!paged() || !pages.length) return;
    var index = pairs.indexOf(pair);
    if (index < 0) return;
    var n = pageFor(index, pages);
    if (n !== current) showPage(n, true);
  }

  function turnBy(delta) {
    if (!paged() || !pages.length) return false;
    var n = current + delta;
    if (n < 0 || n >= pages.length) return false;
    showPage(n);
    turned(delta);
    return true;
  }

  // A turned page comes in from the side it lived on — from the left on a Hebrew text
  // going forward, from the right going back, and the other way round in English — so
  // the movement is the one thing on screen that says which way the pages run.
  // Nothing under `prefers-reduced-motion`, where the stylesheet leaves it still.
  function turned(delta) {
    if (!main) return;
    var rtl = (document.documentElement.getAttribute("dir") || "ltr") === "rtl";
    var fromLeft = delta > 0 ? rtl : !rtl;
    main.classList.remove("settled", "turned-from-left", "turned-from-right");
    void main.offsetWidth;
    main.classList.add(fromLeft ? "turned-from-left" : "turned-from-right");
  }

  /* --- a swipe turns the page -------------------------------------------------
     On touch, a horizontal swipe across the text turns the page in the reading
     direction: the next page lives at the inline end, and a finger draws it in by
     moving toward the inline start — leftwards in English, rightwards in Hebrew.
     Nothing follows the finger; the page turns on release, with the movement above,
     which is what says which way the pages run. Not from a control, not over a
     selection, not a slow drag, and never one that is more up-and-down than across
     — that is scrolling, and the browser has it. Off the last page, on to the next
     chapter, as the forward arrow goes. */
  var SWIPE = 48;
  (function () {
    if (!main) return;
    var startX = null;
    var startY = 0;
    var startAt = 0;
    main.addEventListener(
      "touchstart",
      function (event) {
        startX = null;
        if (!paged() || event.touches.length !== 1) return;
        var at = event.target;
        if (at && at.closest && at.closest("button, a, input, select, textarea")) return;
        startX = event.touches[0].clientX;
        startY = event.touches[0].clientY;
        startAt = Date.now();
      },
      { passive: true }
    );
    main.addEventListener(
      "touchend",
      function (event) {
        if (startX === null || !event.changedTouches.length) return;
        var touch = event.changedTouches[0];
        var dx = touch.clientX - startX;
        var dy = touch.clientY - startY;
        startX = null;
        if (Date.now() - startAt > 600) return;
        if (Math.abs(dx) < SWIPE || Math.abs(dx) < Math.abs(dy) * 2) return;
        var picked = window.getSelection && window.getSelection();
        if (picked && String(picked).trim()) return;
        var rtl = (document.documentElement.getAttribute("dir") || "ltr") === "rtl";
        var forward = rtl ? dx > 0 : dx < 0;
        if (!turnBy(forward ? 1 : -1) && forward) nextChapter();
      },
      { passive: true }
    );
  })();

  // On to the next chapter's file, where there is one: what PageDown, the forward arrow
  // of the page control and the walk all do off the last page. False on the last
  // chapter, where the foot of the text carries Done instead.
  function nextChapter() {
    var link = pager && pager.querySelector("[data-next]");
    if (!link) return false;
    location.href = link.getAttribute("href");
    return true;
  }

  /* --- straight to a section -------------------------------------------------
   *
   * The weekly is one long targum rather than six chapters, which is right for reading
   * it through and wrong for somebody who does not want the politics. The bar carries a
   * link per section; this is what those links do.
   *
   * A plain `#id` cannot do it. In page mode every pair outside the current page is
   * `hidden`, so the browser has nothing to scroll to — the section is not off-screen,
   * it is not rendered. So: turn to its page first, then bring it to the top.
   */
  function jumpTo(id) {
    return jumpToPair(pairBySegment[id]);
  }

  function jumpToPair(pair) {
    if (!pair) return false;
    if (paged()) turnTo(pair);
    if (pair.scrollIntoView) pair.scrollIntoView({ block: "start", behavior: behaviour() });
    return true;
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("[data-to]");
    if (!link) return;
    if (jumpTo(link.getAttribute("data-to"))) event.preventDefault();
  });

  /* --- straight to a verse ---------------------------------------------------
   *
   * A verse's row is `#2:1` — chapter and verse, which is how every learner of a
   * Biblical text locates a line — so a link to Ruth 2:1 opens on Ruth 2:1
   * (targum-internal#28). The scrolling reader needs nothing from here: the browser
   * lands on an id by itself, `resume` stands aside when there is a hash, and the row's
   * `scroll-margin` keeps it out from under the bar. The pages are the case above all
   * over again — a verse on another page is not rendered, so its page is turned first.
   * Sefaria writes the same address `Ruth.2.1`, so a dot between the numbers is read too.
   */
  function verseInHash() {
    var found = /^#(\d+)[:.](\d+)$/.exec(location.hash);
    var pair = found ? document.getElementById(found[1] + ":" + found[2]) : null;
    return pair && pair.classList.contains("pair") ? pair : null;
  }

  function arrive() {
    var pair = verseInHash();
    if (pair) jumpToPair(pair);
  }

  window.addEventListener("hashchange", arrive);

  // The same page after the layout has changed under it — the type a step larger, the
  // vowels on, the list open. Held by the pair the reader is on, not by a number.
  function relayout() {
    if (!paging || !paged()) return;
    var held = pages.length ? pairs[pages[current][0]] : null;
    var here = anchor();
    // A word the reader stood on, and nothing weaker. `anchor` otherwise falls back to
    // whatever line the middle of the window lands on, which in page mode is a line they
    // have not chosen — and holding that turns the page under them.
    //
    // It is the font arriving that makes this bite. The first layout is measured in the
    // fallback's metrics, three lines fit; the real face lands, they grow, and the third
    // line is now on page two — so a reader who had opened the text and touched nothing
    // was moved to page two a moment later. In page mode the page is the place, and only
    // a word the reader marked is a better answer than it.
    if (here && here.word && here.pair && !here.pair.hidden) held = here.pair;
    // And the verse a link named, while it is still on the page. The link turned to
    // its page in the fallback's metrics; the real face lands, the page is one line
    // shorter, and holding the page's first line hands the reader the page *before*
    // the verse they asked for. Once they have turned away from it, the page is the
    // place again.
    var linked = verseInHash();
    if (linked && !linked.hidden) held = linked;
    paginate();
    showPage(held ? pageFor(pairs.indexOf(held), pages) : current, true);
  }

  function applyPaged() {
    body.classList.toggle("paged", !!prefs.paged);
    Array.prototype.forEach.call(document.querySelectorAll("[data-paged]"), function (button) {
      button.classList.toggle("on", !!prefs.paged);
      button.setAttribute("aria-pressed", prefs.paged ? "true" : "false");
    });
    if (turn) turn.hidden = !prefs.paged;
    paging = true;
    if (!paged()) {
      pairs.forEach(function (pair) {
        pair.hidden = false;
      });
      body.classList.remove("last-page");
      pages = [];
      redraw();
      return;
    }
    paginate();
    var was = prefs.pageBy ? prefs.pageBy[pageKey] : "";
    var at = was && pairBySegment[was] ? pairs.indexOf(pairBySegment[was]) : 0;
    showPage(at > 0 ? pageFor(at, pages) : 0, true);
  }

  // How far through the chapter, as the prefetch asks it: null when not paged, so it
  // falls back to reading the scroll.
  function through() {
    if (!paged() || !pages.length) return null;
    return pages.length > 1 ? current / (pages.length - 1) : 1;
  }

  var picker = document.getElementById("translation");

  // Changing translation can be changing language, and everything that is about a pair
  // of languages rather than about a word has to follow it: which meanings the cards and
  // the list show, which language a word is looked up in, which glossary is waited for,
  // and which language the cells themselves claim to be written in.
  //
  // Not the marks, though. They are painted from the word's level, which is a fact about
  // the word and not about the language it is being read in — redrawing them here would
  // be a full re-mark of the screen to arrive at the page that is already on it.
  function applyTranslation(id, first) {
    var entry = translationData[id];
    if (!entry || !entry.text) return;
    var was = targetLanguage;
    useTarget(id);
    foldMeanings();
    var coarse = {};
    (entry.coarse || []).forEach(function (segmentId) {
      coarse[segmentId] = true;
    });
    pairs.forEach(function (pair) {
      var segmentId = pair.getAttribute("data-id");
      var cell = pair.querySelector(".tr");
      if (!cell) return;
      cell.textContent = entry.text[segmentId] || "";
      // The template stamps these from the first translation, so every other one wore
      // the first one's language — a Russian sentence marked English, punctuated at the
      // wrong end of the line and read out in the wrong voice.
      if (targetLanguage) cell.setAttribute("lang", targetLanguage);
      if (targetDirection) cell.setAttribute("dir", targetDirection);
      // Each translation is aligned independently, so which regions are approximate
      // changes with the translation on show.
      pair.classList.toggle("coarse", !!coarse[segmentId]);
    });
    if (prefs.translationBy && documentId) prefs.translationBy[documentId] = id;
    save();
    if (!first && targetLanguage !== was) {
      // What was asked and answered in the language being left says nothing about the
      // one being entered: a word with no English meaning may well have a Russian one,
      // and offering "nothing found" for it would be a lie.
      asked = {};
      lookup = {};
      hideCard();
      hideChip();
      waitForMeanings();
    }
    renderList();
  }

  // Which translation to open on. The page is already rendered with the first one, so
  // opening on that costs nothing: the target is taken and the meanings folded in
  // without a single cell being touched. Only a remembered choice of another one
  // rewrites the text, and only a reader who made that choice pays for it.
  var opening = "t0";
  var kept = prefs.translationBy ? prefs.translationBy[documentId] : "";
  if (kept && translationData[kept]) opening = kept;

  if (opening !== "t0") {
    applyTranslation(opening, true);
  } else {
    useTarget("t0");
    foldMeanings();
  }

  if (picker) {
    picker.value = opening;
    picker.addEventListener("change", function () {
      applyTranslation(picker.value);
    });
  }

  /* --- keyboard help ------------------------------------------------------- */

  // Eight single keys did things and nothing on the page said so, including the arrows,
  // which stop scrolling the moment this file loads.
  var keysCard = document.getElementById("keys");

  var keysButton = document.querySelector("[data-keys]");

  function showKeys(open) {
    if (!keysCard) return;
    if (open) occupy("keys");
    keysCard.hidden = !open;
    // The button discloses the panel, so it has to say whether the panel is open. Focus
    // stays on the word either way: looking up a key must not cost you your place.
    if (keysButton) keysButton.setAttribute("aria-expanded", open ? "true" : "false");
    if (!open) vacate("keys");
    if (seatFoot()) relayout();
  }

  // Whether there is a keyboard here at all. The stylesheet hides the keys button on a
  // phone by a media query, and the query lies: a phone's in-app browser reported a
  // pointer that could hover, the button showed, and the card of shortcuts opened over
  // a screen with nothing to press them on. So under 60rem the button waits for proof
  // — the first key pressed. Not a key typed into a field: a phone's own keyboard
  // sends those, and typing a meaning is not evidence of arrow keys.
  document.addEventListener(
    "keydown",
    function (event) {
      if (!event.key || event.key === "Unidentified") return;
      var into = event.target && event.target.tagName;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(into || "")) return;
      body.classList.add("has-keyboard");
    },
    true
  );

  // The menu behind ⋯: on a narrow window, everything the bar has no row for. Under
  // 60rem it opens in the band like the sheet and the card; on a wide window it is
  // not a menu at all — its groups lie in the bar — and this is never called.
  var more = document.getElementById("more");
  var moreButtons = Array.prototype.slice.call(document.querySelectorAll("[data-more]"));

  function showMore(open) {
    if (!more) return;
    if (open) occupy("more");
    more.classList.toggle("open", !!open);
    moreButtons.forEach(function (button) {
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    if (!open) vacate("more");
    if (seatFoot()) relayout();
  }

  watchFoot();

  /* --- the reader alone on the glass ----------------------------------------
     The browser's own full screen, offered only where the browser has one: Safari on a
     phone has none for a page, and a button that does nothing is worse than no button.
     The browser handles the way out — Escape, the system's gesture — and says so
     itself; this only keeps the button honest about which state it is in. */
  var fullscreenGroup = document.getElementById("fullscreen-group");
  var fullscreenButton = document.querySelector("[data-fullscreen]");
  var fullscreenable =
    !!(root.requestFullscreen || root.webkitRequestFullscreen) &&
    document.fullscreenEnabled !== false;
  if (fullscreenGroup && fullscreenable) fullscreenGroup.hidden = false;

  function inFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement);
  }

  function toggleFullscreen() {
    if (!fullscreenable) return;
    if (inFullscreen()) {
      (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    } else {
      var ask = root.requestFullscreen || root.webkitRequestFullscreen;
      var asked = ask.call(root);
      if (asked && asked.catch) asked.catch(function () {});
    }
  }

  function fullscreenChanged() {
    var on = inFullscreen();
    if (fullscreenButton) {
      fullscreenButton.classList.toggle("on", on);
      fullscreenButton.setAttribute("aria-pressed", on ? "true" : "false");
      fullscreenButton.setAttribute("aria-label", on ? "Leave full screen" : "Full screen");
    }
    say(on ? "Full screen." : "Out of full screen.");
    // The window is another size: the pages are laid out for it.
    relayout();
  }
  document.addEventListener("fullscreenchange", fullscreenChanged);
  document.addEventListener("webkitfullscreenchange", fullscreenChanged);
  if (fullscreenButton) fullscreenButton.addEventListener("click", toggleFullscreen);

  // Pulled down, and away. On a phone an occupant of the band is closed the way every
  // sheet on a phone is closed: a finger on it, drawn down, and let go. The occupant
  // follows the finger — that is what the gesture looks like, not an animation, so it
  // is not subject to `prefers-reduced-motion` — and past a thumb's length it goes.
  // Not from inside a scrolled list: a finger drawn down over words that have been
  // scrolled is scrolling them back up, and `overscroll-behavior: contain` keeps the
  // page itself from following. Nor from a field, where a finger is placing a caret.
  var PULLED = 64;

  function scrolledInside(from, element) {
    for (var node = from; node && node !== element; node = node.parentNode) {
      if (node.scrollTop > 0) return true;
    }
    return element.scrollTop > 0;
  }

  function dismissible(element, close) {
    if (!element) return;
    var startY = null;
    var pulled = 0;
    element.addEventListener(
      "touchstart",
      function (event) {
        startY = null;
        pulled = 0;
        if (roomy.matches || event.touches.length !== 1) return;
        var at = event.target;
        if (at && /^(INPUT|TEXTAREA|SELECT)$/.test(at.tagName || "")) return;
        if (scrolledInside(at, element)) return;
        startY = event.touches[0].clientY;
        element.classList.add("pulling");
      },
      { passive: true }
    );
    element.addEventListener(
      "touchmove",
      function (event) {
        if (startY === null) return;
        pulled = event.touches[0].clientY - startY;
        element.style.transform = pulled > 0 ? "translateY(" + pulled + "px)" : "";
      },
      { passive: true }
    );
    function letGoOf() {
      if (startY === null) return;
      var far = pulled > PULLED;
      startY = null;
      pulled = 0;
      element.classList.remove("pulling");
      if (!far) {
        element.style.transform = "";
        return;
      }
      // On down, off the foot of the window, and then gone — unless the reader asked
      // for stillness, in which case gone.
      var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (still) {
        element.style.transform = "";
        close();
        return;
      }
      element.style.transform = "translateY(100%)";
      setTimeout(function () {
        element.style.transform = "";
        close();
      }, 200);
    }
    element.addEventListener("touchend", letGoOf);
    element.addEventListener("touchcancel", letGoOf);
  }

  dismissible(listBox, function () { showList(false); });
  dismissible(card, hideCard);
  dismissible(chip, hideChip);
  dismissible(keysCard, function () { showKeys(false); });
  dismissible(more, function () { showMore(false); });
  // The video panel closes through its own closure, which runs after this one and
  // holds the button state and the store — hence the window indirection, the same
  // door occupy() uses to put it away. The video carries no controls of its own
  // (the strip is the transport), so the pull conflicts with nothing.
  if (videoPanel) {
    dismissible(videoPanel, function () {
      if (window.TargumVideo) window.TargumVideo.hide();
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
      if (button.id === "rest-mark") {
        markRest();
        return;
      }
      if (button.id === "rest-undo") {
        undo();
        return;
      }
      if (button.id === "done-mark") {
        setFinished(!finishedAt());
        return;
      }
      if (button.getAttribute("data-export") === "csv") {
        exportCsv();
        return;
      }
      if (button.getAttribute("data-export") === "anki") {
        exportAnki();
        return;
      }
      var whichList = button.getAttribute("data-list");
      if (whichList) {
        showTab(whichList);
        save();
        return;
      }
      if (button.hasAttribute("data-more")) {
        showMore(!(more && more.classList.contains("open")));
        return;
      }
      if (button.hasAttribute("data-keys")) {
        showKeys(keysCard ? keysCard.hidden : false);
        // Closed from the × on the card itself: the button just pressed is gone with
        // the card, so focus goes back to the one in the bar that opened it.
        if (keysCard && keysCard.hidden && keysCard.contains(button) && keysButton) {
          keysButton.focus();
        }
        return;
      }
      if (button.hasAttribute("data-marking")) {
        prefs.marking = !prefs.marking;
        applyMarking();
        save();
        // Said aloud: the pressed state on a 24px icon is the whole visual change, and
        // a mode that alters what reading does deserves more than that.
        say(prefs.marking ? "Marking words as you read." : "Not marking.");
        return;
      }
      if (button.hasAttribute("data-paged")) {
        prefs.paged = !prefs.paged;
        applyPaged();
        save();
        say(prefs.paged ? "Pages." : "One long scroll.");
        return;
      }
      if (button.hasAttribute("data-turn")) {
        var went = turnBy(Number(button.getAttribute("data-turn")));
        if (!went && Number(button.getAttribute("data-turn")) > 0) nextChapter();
        return;
      }
      var mode = button.getAttribute("data-mode");
      if (mode) {
        if (mode === prefs.mode) return;
        prefs.mode = mode;
        applyMode();
        settle();
        save();
        say(button.getAttribute("aria-label") || mode);
        return;
      }
      if (button.hasAttribute("data-nikkud-toggle")) {
        toggleVowels();
        return;
      }
      if (button.hasAttribute("data-taamim-toggle")) {
        toggleTaamim();
        return;
      }
      var action = button.getAttribute("data-type");
      if (action) {
        var held = hold();
        if (action === "larger") prefs.size += 0.0625;
        if (action === "smaller") prefs.size -= 0.0625;
        if (action === "looser") prefs.leading = nextLeading(prefs.leading);
        applyType();
        relayout();
        placeSlide();
        // The type grows around the line you are reading rather than sliding it off the
        // top of the window, which is what four presses of A+ used to do.
        keep(held);
        // A card stays open across a step of type size — it is the same word and the same
        // answer — and the word it belongs to has just moved out from under it.
        relay();
        save();
      }
      return;
    }

    // A row of the menu is one control with its name beside it, and on a phone the
    // name is most of the row. A tap on the name presses the control. Not a row of
    // several — the type sizes, the levels — where the name says nothing about which.
    var row = event.target.closest ? event.target.closest(".bar-more.open .group") : null;
    if (row && !button) {
      var controls = row.querySelectorAll("button, a");
      if (controls.length === 1 && !row.querySelector("select")) {
        controls[0].click();
        return;
      }
    }

    // A word answers the same way whichever mode you are in. Marking changes what the
    // page shows you, never what it lets you do — you have to be able to mark a word to
    // clear it, and the whole point of the mode is clearing them.
    var word = event.target.closest ? event.target.closest(".w") : null;
    // With the chip up, this click is the tail of the drag that drew it: mouseup fires
    // first, and drew a card there already. A second card over the first was the "pop up
    // card is a mess".
    //
    // Whatever the click landed on, and that is the point. A click fires on the nearest
    // common ancestor of where the pointer went down and where it came up, so a drag
    // across two words reports the cell rather than a word — and requiring a word here
    // meant every phrase closed the card it had just drawn, which looked from the outside
    // like selecting a phrase doing nothing at all. A tap cannot reach this: mousedown
    // puts the chip away, and a tap draws no new one.
    if (chip && !chip.hidden) return;
    // Either way the pointer has taken over from the arrows, and the ring goes with them.
    leaveQueue();
    // And from the page: wherever it was holding a place for them, they have just said
    // where they are. The tap is the new one, and the card is its mark.
    forget();
    if (word) {
      showCard(word);
      // Tapping a word does not scroll, so nothing else here would write it down — and
      // this is the word a resize has to be able to hand back.
      note();
      return;
    }
    hideCard();
    showKeys(false);
    // And the menu, unless this is a press inside it: its own buttons — the theme, the
    // player's — fall through to here.
    if (!(more && more.contains(event.target))) showMore(false);
  });

  /* --- the word queue ------------------------------------------------------ */

  // The words of this chapter you have not finished with, in reading order, each one
  // once. Built from the embedded data rather than from the page, for the reason every
  // other count here is built from it: most of the chapter's spans do not exist yet —
  // `markSegment` draws a screenful and leaves the rest until it is scrolled to — and
  // the ones that do are thrown away by the next `redraw`.
  //
  // A word is in the queue when it is neither known nor ignored, which is `fresh` plus
  // `learning` in `coverage()`. The figure in the header and the length of this list are
  // the same number arrived at twice, so they cannot drift.
  function buildQueue() {
    var seen = {};
    var out = [];
    Object.keys(wordData).forEach(function (segmentId) {
      (wordData[segmentId] || []).forEach(function (token) {
        var lemma = lemmas[token[4]];
        // Asked of the object's own keys: a text using the word "constructor" would
        // otherwise find a function sitting in `seen` and skip every one of them.
        if (!lemma || Object.prototype.hasOwnProperty.call(seen, lemma)) return;
        // Claimed at the first appearance whether or not it is queued, so a word you
        // already know cannot let a later occurrence of itself back in.
        seen[lemma] = true;
        var status = statusOf(lemma);
        if (status === KNOWN || status === IGNORED) return;
        out.push({ segment: segmentId, lemma: token[4], start: token[0] });
      });
    });
    return out;
  }

  // Every word of the chapter in reading order, which is what the back key walks.
  //
  // No status filter and no deduplication by lemma, both deliberately. A word you have
  // just marked is precisely the one you are stepping back to look at, so filtering by
  // status would hide it; and the word before this one is the word before this one
  // whether or not its dictionary form turned up earlier in the chapter.
  function buildAll() {
    var out = [];
    Object.keys(wordData).forEach(function (segmentId) {
      (wordData[segmentId] || []).forEach(function (token) {
        if (!lemmas[token[4]]) return;
        out.push({ segment: segmentId, lemma: token[4], start: token[0] });
      });
    });
    return out;
  }

  // Forward is the worklist; back is the text. The two are not the same list and were
  // never symmetrical.
  //
  // Forward means "the next word I have not finished with", which is the whole point of
  // the queue. Back cannot mean that, because dealing with a word takes it out of the
  // queue: built on the queue, the back key skipped every word the reader had just
  // marked and landed somewhere earlier in the chapter, walking back *past* their own
  // work instead of retracing it. The way back to a word you just answered is `u`, which
  // takes the level off; the way back to the word before this one is this.
  function queueFor(forward) {
    return forward ? buildQueue() : buildAll();
  }

  // Rebuilt on every move rather than kept and patched. A chapter is a few thousand
  // tokens and the walk does not reach the page at all, which is cheaper than every way
  // of being wrong about when a saved list went stale.
  //
  // Segment ids are opaque, so the order they read in is the order they arrive in.
  // `builder.py` writes them in document order and a render test pins that.
  var segmentAt = null;

  function segmentIndex(segmentId) {
    if (!segmentAt) {
      segmentAt = {};
      Object.keys(wordData).forEach(function (id, index) {
        segmentAt[id] = index;
      });
    }
    return Object.prototype.hasOwnProperty.call(segmentAt, segmentId)
      ? segmentAt[segmentId]
      : -1;
  }

  // Where you are is a position rather than an index into the list, because the list is
  // rebuilt underneath you: saying "known" takes the word out of the queue and saying
  // "2" leaves it in. Asking for the first word past this position answers both.
  function step(from, forward) {
    var list = queueFor(forward);
    if (!list.length) return null;
    if (!from) return forward ? list[0] : list[list.length - 1];
    for (var n = 0; n < list.length; n++) {
      var entry = list[forward ? n : list.length - 1 - n];
      if (segmentIndex(entry.segment) === -1) continue;
      if (forward ? later(entry, from) : later(from, entry)) return entry;
    }
    return null;
  }

  // Whether `a` comes after `b` in the reading: a later sentence, or the same one
  // further along.
  function later(a, b) {
    var x = segmentIndex(a.segment);
    var y = segmentIndex(b.segment);
    return x > y || (x === y && a.start > b.start);
  }

  // The last word on a page, whatever was said about it. Decided by the same test of
  // what counts as a word as `buildAll`, so the foot the forward arrow stops at and the
  // word the back arrow returns to are the same one. Null for a page with no words.
  function footOf(n) {
    var range = pages[n];
    if (!range) return null;
    for (var i = range[1]; i >= range[0]; i--) {
      var id = pairs[i].getAttribute("data-id");
      var tokens = wordData[id] || [];
      for (var t = tokens.length - 1; t >= 0; t--) {
        if (!lemmas[tokens[t][4]]) continue;
        return { segment: id, lemma: tokens[t][4], start: tokens[t][0] };
      }
    }
    return null;
  }

  // Which page a queued word is on; -1 for a word the page drew no pair for.
  function pageAt(entry) {
    var pair = entry ? pairBySegment[entry.segment] : null;
    var index = pair ? pairs.indexOf(pair) : -1;
    return index < 0 ? -1 : pageFor(index, pages);
  }

  // The next word, and nothing past the last one. It used to round to the beginning when
  // the end was reached with words still waiting earlier — right by the counter, which
  // would otherwise say five left while the arrow refused, and wrong by the reading: a
  // reader who walks to the end of a text is at the end of it, and being thrown back to
  // page one is the page taking the text away at the moment they finished it.
  //
  // The words earlier are still reachable — the other arrow walks back through the text
  // as written, and a tap reaches any word at all — so what is lost is a shortcut, and
  // what is gained is an end that behaves like one.
  //
  // On pages, forward is a page at a time. The next word owed can be on a later page,
  // and turning straight to it turned the page under the lines beneath the word the
  // reader was on — the last word they had not finished with is seldom the last word on
  // the page — so the end of every page went unread and had to be paged back to. And a
  // page with nothing left to mark had no way through it from the keyboard at all. So
  // the foot of the page comes first: the arrow stops on its last word, whatever was
  // said about it, and from there turns one page — loudly, like PageDown, because a turn
  // is news — and stands on the first word owed on the new page, or its foot when it has
  // none. A page already clear costs one key, the same as a word.
  //
  // Back is untouched: it walks the text as written and lands on the previous page's
  // foot by itself. Off the last page, nothing further, as before.
  function onward(from, forward) {
    var entry = step(from, forward);
    if (!forward || !paged() || !pages.length) return entry;
    if (entry && pageAt(entry) === current) return entry;
    var foot = footOf(current);
    if (foot && (!from || later(foot, from))) return foot;
    if (!turnBy(1)) return entry;
    if (entry && pageAt(entry) === current) return entry;
    return footOf(current);
  }

  // Entering the queue from where you are reading, not from the top of the chapter. On a
  // chapter you had scrolled halfway into, starting at the first word would read as the
  // page having lost your place.
  function enterFrom(forward) {
    var here = document.activeElement;
    var pair = here && here.closest ? here.closest(".pair") : null;
    if (!pair) pair = onScreen();
    if (!pair) return step(null, forward);
    // Outside this sentence on the side you came from, so its own words are all still
    // ahead of you: going forward that is before its first offset, going back its last.
    var edge = { segment: pair.getAttribute("data-id"), start: forward ? -1 : Infinity };
    // Through `onward`, so the first press on a page already clear goes to its foot and
    // not to a word some pages on.
    return onward(edge, forward) || step(null, forward);
  }

  // The sentence in front of the reader: the first one not yet scrolled past. Measured
  // from the top of the text rather than the top of the window, because the bar is
  // sticky and a sentence behind it is one you have already read.
  function onScreen() {
    if (paged() && pages.length) return pairs[pages[current][0]] || null;
    var top = ceiling();
    for (var n = 0; n < pairs.length; n++) {
      if (pairs[n].getBoundingClientRect().bottom > top) return pairs[n];
    }
    return pairs[0] || null;
  }

  var still = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;
  var bar = document.querySelector(".bar");

  function behaviour() {
    // §8: everything honours prefers-reduced-motion, and a page that slides under
    // somebody who asked it not to is the least forgivable way to break that.
    return still && still.matches ? "auto" : "smooth";
  }

  // Scrolling is for a word that is not in front of you. Stepping along a line already on
  // the screen must not move the page — that is the difference between a queue that feels
  // like reading and one that feels like a slideshow.
  //
  // The word decides and the sentence moves. Asking the sentence whether it is on screen
  // scrolled the page whenever a long verse happened to run past the fold, with the word
  // you were standing on in plain sight the whole time; centring the word alone puts the
  // line it belongs to at the very edge of the window, so you would have to scroll again
  // to read it.
  function bring(word, pair) {
    if (!word.getBoundingClientRect || !pair.scrollIntoView) return;
    var box = word.getBoundingClientRect();
    var top = ceiling();
    if (box.top >= top && box.bottom <= window.innerHeight - 16) return;
    // Unless the sentence is taller than the window, in which case centring it would put
    // the word off the screen the scroll was meant to bring it on to.
    var room = window.innerHeight - top - 16;
    var tall = pair.getBoundingClientRect().height > room;
    (tall ? word : pair).scrollIntoView({ block: "center", behavior: behaviour() });
  }

  // What a word means, on the word the arrows are on. Asked for rather than offered: a
  // card that opened at every step would put a window between a reader and the page they
  // are walking, forty times in a row.
  function openCard() {
    if (!standing || !card) return;
    var word = standing;
    // `showCard` puts away whatever was open, which takes the ring off this very word.
    showCard(word);
    word.classList.add("queued");
    word.setAttribute("tabindex", "0");
    // So a screen reader says the word and what it means together, rather than reading
    // out a word from the middle of a sentence with no account of why.
    if (card.id) word.setAttribute("aria-describedby", card.id);
    if (word.focus) word.focus({ preventScroll: true });
  }

  // "Look it up", from the keyboard: Enter, on a card that is offering it. It was the
  // only action on the card without a key, which put the thing a reader most often
  // wants — what does this word mean — behind the one input they had otherwise put
  // down. It had a letter of its own once, `g` for the gloss, which is what this file
  // calls the thing and nothing a reader ever sees; the key that opened the card is
  // the key that asks.
  //
  // The button is pressed rather than reimplemented. Every condition for offering it is
  // already decided in `showCard` — something to ask with, nothing known about the word
  // already, and not a word that has been asked about and not found — and a second copy
  // of that reasoning here is a second copy to get wrong. Pressing it also buys the
  // feedback for free: the same "looking…" on the same disabled button.
  //
  // Answers true while there is a question on the card: offered, or already asked and
  // still waiting. False means there is nothing to ask, and Enter closes the card
  // instead. A button disabled because nothing can be asked at all — off the disk, or
  // signed out — is the second case, not the first.
  function askMeaning() {
    var button = card && !card.hidden ? card.querySelector(".look-up") : null;
    if (!button) return false;
    if (button.disabled) return button.classList.contains("looking");
    button.click();
    return true;
  }

  // Stand on a queued word: the ring, the keyboard, and nothing else. `open` carries a
  // card that was already up on to the next word — you asked the question once, and
  // walking on does not withdraw it.
  function focusQueued(entry, open) {
    var pair = entry ? pairBySegment[entry.segment] : null;
    if (!pair) return false;
    // Its spans may never have been drawn: only a screenful is marked up front.
    markPair(pair);
    // And it may be on another page.
    turnTo(pair);
    // By offset as well as by lemma. A pair can hold two forms of one dictionary word,
    // and a saved phrase drawn across a word slices it into several spans — the first
    // piece is enough, because `bareSurface` reads the whole word back out of
    // `data-bare` whichever piece you hand it.
    var span = wordIn(
      pair,
      '.w[data-lemma="' + entry.lemma + '"][data-bare^="' + entry.start + ',"]'
    );
    if (!span) return false;
    leaveQueue();
    // The same for the arrows as for a tap: the walk says where the reader is, and the
    // ring on the word is what says it.
    forget();
    // A card on its way out is left to go at its own pace: the reader answered it and
    // stepped on, and the point of the beat is that they see it happen.
    if (!open && !fading) hideCard();
    standing = span;
    place = { segment: entry.segment, start: entry.start };
    // The page's one tab stop, so Tab and Shift+Tab from the bar come back to the word
    // rather than to the far end of the chapter.
    span.classList.add("queued");
    span.setAttribute("tabindex", "0");
    if (span.focus) span.focus({ preventScroll: true });
    bring(span, pair);
    // `bring` leaves a word already on the screen where it is, so the walk can move from
    // word to word without a scroll to write either of them down.
    note();
    if (open) openCard();
    return true;
  }

  // On to the next one where a word cannot be reached — a segment the page drew no pair
  // for, or a cell with no span for it. Skipping a word is a small wrong; falling back
  // to moving a sentence, which is what happens if this gives up, is a confusing one.
  // Bounded all the same: the worst thing here would be a loop that never gives the page
  // back.
  function goTo(entry, forward, open) {
    for (var tries = 0; entry && tries < 200; tries += 1) {
      if (focusQueued(entry, open)) return true;
      entry = step(entry, forward);
    }
    return false;
  }

  // Whether the card is up on the word being stood on, rather than on one a pointer
  // opened somewhere else.
  function asking() {
    return !!(standing && card && !card.hidden && lookedUp === standing);
  }

  // An arrow. Answers false where there is no queue to walk at all — a text with no
  // annotation carries no words to mark, and the arrows go on meaning sentences there
  // rather than doing nothing.
  function walk(forward) {
    if (!card) return false;
    var entry = place ? onward(place, forward) : enterFrom(forward);
    var had = !!place;
    // Nothing that way. A card already open stays open: closing it out from under
    // somebody who pressed an arrow at the end of the chapter answers the wrong question.
    //
    // Walking off the end of a text puts the keyboard on Done, which is the only thing
    // left to do with it. Rather than giving Enter a second meaning — the thing this file
    // refuses to do with a key — the button is focused and Enter presses it because that
    // is what Enter does to a focused button. The focus ring is also the answer to "it
    // stopped, now what".
    //
    // On pages, nothing further from the foot of the last page means the next chapter,
    // as it does for PageDown — the foot rule has already stood the reader on the last
    // word of the last page, so nothing is skipped. Done and the next chapter never
    // meet: Done is only on the last part, and a part with a next has no Done.
    if (!entry) {
      if (forward && place && finishedMark && !finishedAt() && finishedMark.focus) {
        finishedMark.focus();
      } else if (forward && place && paged() && current === pages.length - 1 && nextChapter()) {
        return true;
      }
      offPage();
      return had;
    }
    // Stepping through words the page is not painting is a mode you can be lost in. `m`
    // puts it back.
    if (!prefs.marking) {
      prefs.marking = true;
      applyMarking();
      save();
    }
    if (goTo(entry, forward, asking())) return true;
    // Already true where the card is open: a walk that reached the end of what it can
    // reach leaves you on the word you were on rather than on nothing.
    offPage();
    return had;
  }

  // `onward` may have turned the page and then found nothing to stand on — a page with
  // no words, or a foot whose span was not drawn. Left as it was, the ring would be on
  // a word the page is no longer showing, and the next level key would mark it out of
  // sight. Not `goTo`'s retry: that walks the queue past the page rule.
  function offPage() {
    if (!paged() || !standing) return;
    var pair = standing.closest ? standing.closest(".pair") : null;
    if (!pair || pair.hidden) leaveQueue();
  }

  /* --- keyboard ------------------------------------------------------------ */

  // Whichever arrow points the way the text reads is the one that goes forward, so on a
  // Hebrew page that is the left one. Read the direction off the page rather than
  // assuming either.
  var rtl = (root.getAttribute("dir") || "ltr") === "rtl";

  // The ring must not outlive the focus that drew it. The word is the page's one tab
  // stop, so a Tab takes you off it and onto a link or a control somewhere else — and
  // the ring, the card and `standing` all stayed behind on the word you left. The next
  // `k` then marked that word, silently, on a word no longer in front of you.
  //
  // Anything inside the card is still the word's own business: its level buttons and its
  // note field are reached by Tab from the word, and that is not leaving. Nor is the
  // bar: it is sticky, the word is still in front of you while you change the type
  // size, and Shift+Tab brings you straight back to it.
  document.addEventListener("focusin", function (event) {
    if (!standing || event.target === standing) return;
    if (card && card.contains && card.contains(event.target)) return;
    if (bar && bar.contains(event.target)) return;
    leaveQueue();
    hideCard();
  });

  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;

    // A key is the letter on it, whatever the shift and caps lock happened to be. Read
    // literally, `event.key` is "K" with caps lock down and every letter the reader
    // answers to is dead — the whole interface, on a state nothing on the page shows.
    var key = event.key;
    if (typeof key === "string" && key.length === 1) key = key.toLowerCase();
    // And the letter printed on the key, whatever layout delivered it. Under the Hebrew
    // layout the P key arrives as "פ", and every letter here was dead for the reader
    // this page is for. A Latin letter is taken as typed, so a Dvorak keyboard keeps
    // its mnemonics; anything else falls back to the key it sits on.
    if (!/^[a-z0-9?]$/.test(key) && /^Key[A-Z]$/.test(event.code || "")) {
      key = event.code.charAt(3).toLowerCase();
    }

    // While a word card is open the number and letter keys belong to it. `k` and `i`
    // already mean previous-sentence and interlinear, and they still do the moment the
    // card is closed — the card is the only thing that borrows them.
    if (markLookedUp(key)) {
      event.preventDefault();
      return;
    }

    // Turning the page. PageDown forward, PageUp back — the keys a scroll already answers
    // to, which is the point: nothing to relearn. On the last page, forward is the next
    // chapter. Not paged, they scroll as they always did.
    //
    // Space is not among them. It turns the page in every reader on earth, and it is
    // still the wrong key here: it plays the recording, on every text that has one, and a
    // key that means two things means neither. Half the library has no recording, and
    // leaving Space to page there is the version of this bug that is hardest to see —
    // the key works until the text happens to have audio, and then it does something
    // else. The arrows either side of the page count turn it, and so do these two.
    if (key === "PageDown" || key === "PageUp") {
      if (!paged()) return;
      event.preventDefault();
      var back = key === "PageUp";
      if (!turnBy(back ? -1 : 1) && !back) nextChapter();
      return;
    }

    switch (key) {
      // The whole of the navigation. This page is walked a word at a time and nothing
      // else — stepping sentences was a second way through the text that shared `k` and
      // `i` with the levels, and a key that means two things means neither.
      //
      // `walk` hands the key back on a text that carries no words to mark. Handing it
      // back matters: unhandled, the arrows scroll the page, which is what a reader with
      // nothing to mark wants them to do and what this file used to take away.
      case "ArrowRight":
        if (!walk(!rtl)) return;
        break;
      case "ArrowLeft":
        if (!walk(rtl)) return;
        break;
      case "p":
        prefs.mode = "parallel";
        applyMode();
        settle();
        save();
        say("Parallel.");
        return;
      case "o":
        prefs.mode = "source";
        applyMode();
        settle();
        save();
        say("Source only.");
        return;
      // `l` rather than `i`: `i` is ignore, on a word, and it cannot also be a mode.
      // The translation goes under each line, which is where the letter comes from.
      case "l":
        prefs.mode = "inter";
        applyMode();
        settle();
        save();
        say("Interlinear.");
        return;
      // The card is asked for, never offered. Walking the page fires no windows; this is
      // the second action that opens one. Open already, the same key asks the question
      // the card is offering, and once there is nothing left to ask it puts the card
      // away.
      case "Enter":
        if (!standing) return;
        if (!asking()) openCard();
        else if (!askMeaning()) hideCard();
        break;
      // The way back from the wrong key. Takes the level off again and puts you back on
      // the word, as many times as you have said something.
      case "u":
        if (!undo()) return;
        break;
      case "t":
        // Not stored and not a preference: a question you ask once.
        showTimings(!readout || readout.hidden);
        return;
      case "m":
        prefs.marking = !prefs.marking;
        applyMarking();
        save();
        say(prefs.marking ? "Marking words as you read." : "Not marking.");
        return;
      case "b":
        prefs.paged = !prefs.paged;
        applyPaged();
        save();
        say(prefs.paged ? "Pages." : "One long scroll.");
        return;
      case "f":
        toggleFullscreen();
        return;
      case "s":
        if (listBox) showList(!!listBox.hidden);
        return;
      case "n":
        toggleVowels();
        return;
      case "a":
        toggleTaamim();
        return;
      case "?":
        showKeys(keysCard ? keysCard.hidden : false);
        return;
      case "Escape": {
        // One layer a press. Closing the keys and then dropping out of the queue in the
        // same keystroke costs a reader their place for looking a shortcut up.
        if (more && more.classList.contains("open")) {
          showMore(false);
          return;
        }
        if (keysCard && !keysCard.hidden) {
          showKeys(false);
          return;
        }
        // The card next, and you stay where you are — the two are separate things, and
        // one key that did both would cost you your place to close a window.
        // A card that is already leaving is not a layer to be closed: Escape would
        // read as doing nothing, and the reader would have to press it twice to get
        // out of the queue.
        if (chip && !chip.hidden) {
          hideChip();
          if (window.getSelection) window.getSelection().removeAllRanges();
          return;
        }
        if (card && !card.hidden && !fading) {
          hideCard();
          if (standing && standing.focus) standing.focus({ preventScroll: true });
          return;
        }
        // Then the panel, which covers the translation you are grading against. It is a
        // thing on top of the text, and Escape takes those off before it takes your
        // place away.
        if (listBox && !listBox.hidden) {
          showList(false);
          if (standing && standing.focus) standing.focus({ preventScroll: true });
          return;
        }
        // Then out of the queue, back onto the sentence the word was in, so the arrows
        // still know where they are.
        var back = standing && standing.closest ? standing.closest(".pair") : null;
        leaveQueue();
        if (back && back.focus) back.focus();
        return;
      }
      default:
        return;
    }
    event.preventDefault();
  });

  // A way back, but only when there is somewhere to go back to. A reader opened
  // straight off the disk has no library page behind it, and the key it was served
  // with is the one it carries in its own address.
  var home = document.getElementById("home");
  var homePlain = document.getElementById("home-plain");
  if (home && served) {
    home.href = keyed("/");
    home.hidden = false;
    // Two drawings of the same mark, one a link and one not, so a reader opened off the
    // disk shows the mark rather than a link to nowhere.
    if (homePlain) homePlain.hidden = true;
    // Section-to-section links are relative and would drop the key, and with it access:
    // the next chapter would answer 403. No key hosted, where `keyed` is the identity.
    var carried = document.querySelectorAll(".pager a, .bar-title .up");
    Array.prototype.forEach.call(carried, function (link) {
      var href = link.getAttribute("href");
      if (href && href.indexOf("?") === -1) {
        link.setAttribute("href", keyed(href));
      }
    });
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

  // A batch of meanings, for the language it was written in. `target` is the language
  // the answer is about, which is not always the one on show: a reply can land after the
  // reader has switched translations, and one written in English is not a fact about
  // Russian. Filed either way, applied only when it is the language being read.
  function takeMeanings(entries, target) {
    var found = false;
    var complete = true;
    var have = glossesBy[target] || [];
    var filled = lemmas.map(function (lemma, index) {
      var meaning = entries[lemma] || "";
      if (meaning) found = true;
      // Whether the file is finished is a question about the file, so it is asked of
      // what came back and not of what this browser happens to know.
      else complete = false;
      // A word the reader looked up themselves while the glossary was still being
      // written. The batch has never heard of it and must not take it away again.
      return meaning || have[index] || "";
    });
    if (!found) return false;
    glossesBy[target] = filled;
    if (target !== targetLanguage) return complete;
    glosses = filled.slice();

    // A word kept before the meanings arrived holds an empty one: the meaning is copied
    // in at the moment you save it, so those entries would stay blank for good.
    lemmas.forEach(function (lemma, index) {
      if (vocab[lemma] && !meaningOf(lemma) && glosses[index]) {
        keepMeaning(lemma, glosses[index]);
      }
    });

    renderList();
    // And the card, if one happens to be open on the word that just gained a meaning.
    if (lookedUp) showCard(lookedUp);
    // The file is written a batch at a time, so the first answer is usually a partial
    // one. Stopping there would leave most of the page's words permanently blank.
    return complete;
  }

  // One wait per target, and only for the target whose meanings somebody actually
  // bought. A reader holding two translations must not sit asking for ten minutes about
  // a language nobody ordered a glossary in.
  var waiting = {};

  function waitForMeanings() {
    var folder = buildFolder();
    if (!canAsk() || !folder) return;
    if (!lemmas.length) return;
    var target = data.glossPending || "";
    // Nothing was bought for this text, so nothing is coming. Words are looked up one
    // at a time from the card instead, and asking every few seconds for ten minutes
    // would be asking for a file that is never going to be written.
    if (!target || target !== targetLanguage) return;
    if (waiting[target] || (glossesBy[target] || []).length) return;
    waiting[target] = true;

    var wait = MEANINGS_FIRST_WAIT;
    var giveUpAt = Date.now() + MEANINGS_GIVE_UP;
    meaningsPending = true;

    function stop() {
      waiting[target] = false;
      meaningsPending = false;
      if (lookedUp) showCard(lookedUp);
    }

    function ask() {
      if (Date.now() > giveUpAt) return stop();
      fetch(keyed("/glossary/" + encodeURIComponent(folder) + "?to=" + encodeURIComponent(target)), {
        headers: keyHeaders(),
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (answer) {
          // The server says which language it answered about; the reader asked about
          // one language and must not file the reply under another.
          var said = (answer && answer.target) || target;
          if (answer && answer.ready && answer.entries && takeMeanings(answer.entries, said)) {
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
  // leaving it set would hide every sentence on the page. `sourceMarked` means "the
  // source carries its own phonetic layer, so open in the form this text was published
  // in" — which for a Tanakh is the whole of it, accents and all — and a per-document
  // choice still wins over it.
  if (!hasNikkud) {
    prefs.nikkud = false;
  } else {
    var chosen = prefs.nikkudBy ? prefs.nikkudBy[documentId] : undefined;
    prefs.nikkud = chosen === undefined ? !!data.sourceMarked : !!chosen;
  }
  applyTaamim(false);
  applyNikkud();
  applyPaged();
  // The Hebrew face rides inside the page, but the browser still resolves it a beat
  // after the first layout — and a page measured in the fallback's metrics is a page
  // whose last verse falls outside the window. So measure once more when the real face
  // is in. `relayout` keeps the reader where they were, which is the whole reason it
  // exists; a browser too old for `document.fonts` simply never asks.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(function () {
      relayout();
    });
  }
  // The page is laid out from here on, so from here on a change to it can be measured.
  living = true;
  took("marks drawn on what is on screen");
  // After the layout every control has a say in, and before the reader can have touched
  // any of them: a scroll to where they left off has to be measured against the page
  // they left, in the mode and at the size they left it in.
  resume();
  // Or where a link said. After the layout, like `resume`, and for the same reason: a
  // verse's page is only known once the pages have been cut.
  arrive();
  took("back where the reader left off");
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

  /* --- what a test can reach ------------------------------------------------ */

  /* Every other script here already hangs its module off `window` — TargumLang,
     TargumCovers, TargumCharts — so this is the same shape rather than a hatch cut for
     tests. Two things in this file are worth checking without a browser, and both have
     shipped a bug: where a card lands beside a word, which is arithmetic, and whether a
     hover survives the keypress that marked the word under it, which is a two-state
     machine. The rest of the reader rebuilds spans through innerHTML and a TreeWalker
     and belongs to a real browser. See tests/js/reader.js.

     The word queue is here for the same reason: which words are in it and which one
     comes next are decided entirely in the embedded data, without asking the page
     anything. Reaching the word once it is chosen is the half that needs a browser. */
  window.TargumReader = {
    placeNear: placeNear,
    stopHover: stopHover,
    hovering: function () {
      return hovering;
    },
    queue: buildQueue,
    step: step,
    // Saying a level and taking it back. The queue is the assertion: known takes a word
    // out of it, and `u` has to put the same word back in the same place.
    level: function (index, status) {
      // Followed by the redraw every caller in the page does after it, so the counts
      // and the offer at the foot are as a reader would see them.
      var now = setStatus(index, lemmas[index], "", toggled(index, status));
      redraw();
      return now;
    },
    undo: undo,
    // The list beside the text, as it would be drawn: newest first, and with the word
    // you have just finished with still on it.
    entries: wordEntries,
    // The Anki file, from cards a test hands it: the headers, the columns, the back.
    ankiText: ankiText,
    // Everything never marked, marked known at once; one undo takes it all back.
    markRest: markRest,
    // Finished with the text, and taken back.
    finish: setFinished,
    finishedAt: finishedAt,
    // The card's grammar line, for tests with no card to open: the plain words a
    // grammar string comes out as, and who a form is about.
    useLine: useLine,
    personWord: personWord,
    // And the register line: which Hebrew a word belongs to, from where the reader is.
    registerLine: registerLine,
    // The arithmetic of a page, for tests with no browser to lay anything out.
    boundariesFrom: boundariesFrom,
    pageFor: pageFor,
    through: through,
    // Putting the player away gives a page its room back, and bringing it out takes the
    // room again. Both are a change of layout like any other, and this is how the rest
    // of the page says so.
    relayout: relayout,
    // The page's one live region, offered to the player's closure so a refused
    // recording is announced the way everything else is.
    say: say,
    // The band's one-at-a-time rule, offered to the video panel's closure the same
    // way: it is an occupant like the sheet and the cards, and arbitrating from two
    // places is how two things end up standing in one band.
    occupy: occupy,
    vacate: vacate,
    // The sentence in front of the reader, for the link home: the line a deep link
    // should open on when nothing is being spoken.
    inFront: onScreen,
  };
})();

/* Where to go next, shown only where there is somewhere to go.
 *
 * The address is the library's, so it means nothing to a reader opened from a disk —
 * which is a real way to read one of these and the reason nothing here is fetched. The
 * suggestion is written into the page either way and revealed only when the page arrived
 * over a connection, rather than offering a link that leads nowhere.
 */
(function () {
  "use strict";
  if (location.protocol === "file:") return;
  var next = document.getElementById("next-up");
  if (next) next.hidden = false;
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
  if (!link) return;
  // Its own, because this is its own scope: it read `passKey` and called `keyed` across
  // the boundary, and neither was ever in reach. No key hosted, where the session cookie
  // identifies the reader; a key locally. This used to stop when there was no key — so
  // on the live site the next chapter was never bought, and the first alpha reader
  // followed the arrow into a page of blank translations.
  var key = new URLSearchParams(location.search).get("k") || "";

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
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
    // Paged, the page says; otherwise the scroll does. Its own scope, so it asks the
    // reader above it through the one seam that scope leaves open.
    var reader = window.TargumReader;
    if (reader && reader.through) {
      var far = reader.through();
      if (far !== null && far !== undefined) return far;
    }
    var height = document.documentElement.scrollHeight - window.innerHeight;
    return height > 0 ? window.scrollY / height : 1;
  }

  function maybe() {
    if (asked || through() < ENOUGH) return;
    asked = true;
    window.removeEventListener("scroll", maybe);
    // In the language this page is being read in. Its own scope, so it asks the page
    // rather than the reader above it — and the page is kept honest by the picker, which
    // restamps every cell it swaps. Without this the next chapter of a Russian book was
    // bought in English, because the server's fallback was English and nothing said
    // otherwise.
    var reading = document.querySelector(".pair .tr");
    var into = reading ? reading.getAttribute("lang") || "" : "";
    fetch(keyed("/chapter"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        name: name,
        number: Number(link.getAttribute("data-next")),
        to: into,
      }),
    }).catch(function () {});
  }

  window.addEventListener("scroll", maybe, { passive: true });
  document.addEventListener("targum:page", maybe);
  maybe();
})();

/* --- a chapter nobody has paid for yet ----------------------------------------
 *
 * The page says so above the text, and this is the button on it. Its own scope, like
 * the prefetch above: it needs the key helpers and the folder name and nothing else.
 * Off a disk there is no server to ask, and the button stays hidden; the line above
 * it still says what the page is.
 */
(function () {
  "use strict";
  var note = document.getElementById("waiting-note");
  var press = document.getElementById("translate-chapter");
  if (!note || !press || location.protocol === "file:") return;

  var key = new URLSearchParams(location.search).get("k") || "";
  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  press.hidden = false;
  press.onclick = function () {
    press.disabled = true;
    // The page set the button's word to the work owed — a translation, or for an
    // imported recording a transcript — and the working form keeps that promise.
    press.textContent = press.textContent === "Transcribe" ? "Transcribing…" : "Translating…";
    fetch(keyed("/chapter"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name: name, number: Number(note.getAttribute("data-chapter")) }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (job) {
        if (job.ready) return location.reload();
        if (!job.id) throw new Error(job.error || job.blocked || "That did not work.");
        var timer = setInterval(function () {
          fetch(keyed("/job/" + job.id))
            .then(function (r) {
              return r.json();
            })
            .then(function (state) {
              if (state.stage === "done") {
                clearInterval(timer);
                location.reload();
              } else if (state.stage === "failed" || state.blocked) {
                clearInterval(timer);
                press.disabled = false;
                press.textContent = state.error || state.blocked || "That did not work.";
              }
            });
        }, 1500);
      })
      .catch(function (problem) {
        press.disabled = false;
        press.textContent = String(problem.message || problem);
      });
  };
})();

/* Which chapter this was, written down for the contents page, so "Start reading" can
 * become "Continue" and point here. One number per text, browser-local: it is a
 * convenience, not a record of how far anybody has read. */
(function () {
  "use strict";
  var pager = document.querySelector(".pager[data-chapter][data-document]");
  if (!pager) return;
  try {
    var opened = JSON.parse(localStorage.getItem("targum:chapter") || "{}");
    opened[pager.getAttribute("data-document")] = Number(pager.getAttribute("data-chapter"));
    targumKeep("targum:chapter", JSON.stringify(opened));
  } catch (e) {}
})();

/* Playing a dialogue: one line, or the whole scene with the text following along.
 *
 * The scene is one audio file and each turn is a span of it, so a line is played by
 * seeking and then stopping at its end — never by loading a clip per line, because a
 * reader is one file and fifty small files is not a shape it has.
 *
 * A single line stops on a timer rather than a `timeupdate` handler: that event fires
 * about four times a second, which overshoots the end of a short turn by a syllable and
 * reads as the next speaker starting. A timer set from the span's own length lands where
 * the seam is. Following the whole scene is the opposite case — nothing is being stopped,
 * only marked — so there the coarse event is exactly right and costs nothing.
 */
(function () {
  "use strict";
  var node = document.getElementById("targum-data");
  if (!node) return;
  var speech;
  var spokenOf = "";
  try {
    var loaded = JSON.parse(node.textContent) || {};
    speech = loaded.speech;
    spokenOf = loaded.document || location.pathname;
  } catch (e) {
    return;
  }
  if (!speech || !speech.audio) return;

  /* One media element, not two clocks. Where the import kept its pictures the page
     carries a <video> pointed at the sidecar beside this file, and that element is the
     player's whole instrument — same HTMLMediaElement, so every span, timer and rate
     below works on it unchanged. Showing and hiding the panel never touches playback:
     a hidden video keeps sounding, which is exactly the audio reader. The inlined
     audio stays in the page for the download button, and as the instrument the player
     falls back to if the sidecar did not travel with the file. */
  var videoBox = document.getElementById("video");
  var videoEl = videoBox ? videoBox.querySelector(".video-el") : null;
  if (videoEl) {
    /* The page's own address carries the serve key in its query, and the sidecar
       request must carry the same or be turned away as a stranger. Off a disk the
       search is empty and the relative address stands alone. */
    videoEl.src = videoEl.getAttribute("data-src") + (location.search || "");
  }
  var videoDead = false;
  var audio = videoEl || new Audio(speech.audio);
  var spans = speech.spans || {};
  /* Each written word's clock, where the build could pair one: rows of
     [charStart, charEnd, start, end] per segment, in the bare text's own offsets. */
  var wordClocks = speech.words || {};
  /* In reading order, because the object came from the page in that order and following
     along means walking it. */
  var order = Object.keys(spans).map(function (id) {
    return { id: id, start: spans[id][0], end: spans[id][1] };
  });
  // No spans is a shape, not a failure: prose is recorded as one reading and played
  // straight through. Everything below works without them — what goes is the highlight
  // that would otherwise crawl down a sentence at a time, which is a thing to do to a
  // dialogue and not to an article.

  /* However many controls ask for it — the bar's button and the player's — there is one
     scene and one state, so they are held together rather than each keeping its own. */
  var scenes = Array.prototype.slice.call(document.querySelectorAll("[data-play-scene]"));
  var player = document.getElementById("player");
  var fill = player && player.querySelector(".player-fill");
  var clock = player && player.querySelector(".player-clock");
  var said = player && player.querySelector(".player-said");
  var scene = scenes[0] || null;
  var stopAt = null;
  var playing = null;      /* the one-line button, when a single line is playing */
  var playingEnd = 0;      /* where that line ends, for re-arming its timer at a new speed */
  var following = false;   /* whether the whole scene is running */
  var marked = null;

  /* The same question the rest of the page asks, asked the same way. Read at the moment
     of scrolling rather than once at load, because a reader can change the setting while
     a scene is playing and the page should already be honouring it. */
  var quiet = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  function behaviour() {
    return quiet && quiet.matches ? "auto" : "smooth";
  }

  function mark(id) {
    if (marked && marked.getAttribute("data-id") === id) return;
    if (marked) marked.classList.remove("now");
    marked = id ? document.querySelector('.pair.voiced[data-id="' + CSS.escape(id) + '"]') : null;
    if (!marked) return;
    marked.classList.add("now");
    /* Only when it has gone off the page. Scrolling a line that is already in front of
       the reader moves the text under their eyes for no reason. */
    var box = marked.getBoundingClientRect();
    /* The scrolling reader reserves nothing — text passes under a fixed control there by
       definition — so the floor is the player's own top edge while it is out. The line
       being spoken is the one line that must not be behind it. */
    var floor = window.innerHeight - 24;
    if (player && !player.hidden) {
      var seat = player.getBoundingClientRect();
      if (seat.height) floor = Math.min(floor, seat.top - 12);
    }
    /* On a narrow window the player is a strip standing on whatever holds the band —
       the sheet, a card — and the reader's own stylesheet knows how tall the lot is. */
    var band = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--foot"));
    if (band > 0) floor = Math.min(floor, window.innerHeight - band - 12);
    if (box.top < 64 || box.bottom > floor) {
      marked.scrollIntoView({ block: "center", behavior: behaviour() });
    }
  }

  function pressed(on) {
    scenes.forEach(function (button) {
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (player) player.classList.toggle("playing", !!on);
  }

  function clocked(seconds) {
    var whole = Math.max(0, Math.floor(seconds));
    return Math.floor(whole / 60) + ":" + ("0" + (whole % 60)).slice(-2);
  }

  function halt() {
    if (stopAt) { clearTimeout(stopAt); stopAt = null; }
    audio.pause();
    if (playing) { playing.classList.remove("saying"); playing = null; }
    if (following) {
      following = false;
      pressed(false);
    }
    if (marked) { marked.classList.remove("now"); marked = null; }
    pressed(false);
  }

  function play(from) {
    try {
      audio.currentTime = from;
    } catch (why) {
      return refused("This recording will not play in this browser.", why);
    }
    var done = audio.play();
    if (done && done.catch) {
      done.catch(function (why) {
        // Chrome rejects here when the tab is not allowed to make a sound — a site muted
        // in the address bar, or a policy about autoplay — and the promise is the only
        // place it says so. Silently stopping made that indistinguishable from a broken
        // file: the control flipped back and the page had nothing to say for itself.
        refused(
          why && why.name === "NotAllowedError"
            ? "This tab is not allowed to play sound. Check the address bar."
            : "This recording would not play.",
          why
        );
      });
    }
  }

  /* Playback failed, and the reader is told which. A control that reverts and explains
     nothing is the worst of both: it looks broken and gives nobody anything to act on. */
  function refused(message, why) {
    halt();
    if (player) {
      player.classList.add("refused");
      if (said) said.textContent = message;
    }
    // The label is written where sighted eyes are; the live region is where everyone
    // else's are. A play button that reverts silently looks broken and says nothing.
    var reader = window.TargumReader;
    if (reader && reader.say) reader.say(message);
    try {
      var trouble = audio.error ? " (media error " + audio.error.code + ")" : "";
      console.error("targum: " + message + trouble, why || "");
    } catch (e) {}
  }

  /* How fast. Steps either side of the recording's own pace, and a pair of buttons rather
     than one that cycles: a cycle from 2× comes round to 0.5×, which is the one step
     nobody pressing "faster" means.

     Held per browser rather than per text — the opposite of the closed player below,
     and for the opposite reason. Which texts you would rather read in silence is a fact
     about each text; how fast you can follow a voice is a fact about you, like the type
     size, and a reader who wanted the last scene slower wants this one slower too.

     The pitch is kept. A slowed voice should drop in speed and not turn into somebody
     else; browsers default to keeping it, but the default is not what the file relies
     on. */
  var RATES = [0.5, 0.75, 1, 1.25, 1.5, 2];
  var RATE_STORE = "targum:player-rate";
  var slower = player && player.querySelector(".player-slower");
  var faster = player && player.querySelector(".player-faster");
  var rateNow = player && player.querySelector(".player-rate-now");

  /* Whatever was stored, the nearest step — a number from a version of this table that
     no longer exists is snapped rather than obeyed, and anything else is the pace it was
     read at. */
  function nearestRate(value) {
    var n = parseFloat(value);
    if (isNaN(n)) return 1;
    var best = 1;
    RATES.forEach(function (rate) {
      if (Math.abs(rate - n) < Math.abs(best - n)) best = rate;
    });
    return best;
  }

  function setRate(value, chosen) {
    var rate = nearestRate(value);
    audio.playbackRate = rate;
    try {
      audio.preservesPitch = true;
      audio.webkitPreservesPitch = true;   // Safari answered to this one for years
    } catch (e) {}
    var i = RATES.indexOf(rate);
    if (rateNow) rateNow.textContent = rate + "×";
    // aria-disabled rather than disabled: a disabled button drops the keyboard focus that
    // was on it, and the reader who just pressed it is still standing there.
    if (slower) slower.setAttribute("aria-disabled", i === 0 ? "true" : "false");
    if (faster) faster.setAttribute("aria-disabled", i === RATES.length - 1 ? "true" : "false");
    /* A single line stops on a timer set from its length at the old speed. Re-armed from
       what is left of it at the new one, or the line runs into the next speaker. */
    if (playing && stopAt) {
      clearTimeout(stopAt);
      stopAt = setTimeout(halt, Math.max(0, ((playingEnd - audio.currentTime) * 1000) / rate));
    }
    if (chosen) {
      try {
        targumKeep(RATE_STORE, String(rate));
      } catch (e) {}
      var reader = window.TargumReader;
      if (reader && reader.say) reader.say(rate + "×");
    }
  }

  function stepRate(by) {
    var i = RATES.indexOf(nearestRate(audio.playbackRate)) + by;
    if (i < 0 || i >= RATES.length) return;
    setRate(RATES[i], true);
  }

  var keptRate = 1;
  try {
    keptRate = localStorage.getItem(RATE_STORE) || 1;
  } catch (e) {}
  setRate(keptRate, false);
  if (slower) slower.addEventListener("click", function () { stepRate(-1); });
  if (faster) faster.addEventListener("click", function () { stepRate(1); });
  /* The figure itself steps on, and round: on a phone it is the only speed control there
     is room for, and one button that cycles is a control, where two arrows for a scale
     of six were a column. */
  if (rateNow) {
    rateNow.addEventListener("click", function () {
      var i = RATES.indexOf(nearestRate(audio.playbackRate));
      setRate(RATES[(i + 1) % RATES.length], true);
    });
  }

  /* One line. */
  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest(".say") : null;
    if (!button) return;
    var span = spans[button.getAttribute("data-id")];
    if (!span) return;
    var again = playing === button;
    halt();
    if (again) return;
    playing = button;
    playingEnd = span[1];
    button.classList.add("saying");
    play(span[0]);
    // Wall-clock, so the span's length is divided by the speed it is played at.
    stopAt = setTimeout(halt, Math.max(0, ((span[1] - span[0]) * 1000) / audio.playbackRate));
  });

  /* One word, or one run of them, for the cards. The audio and its timers live in this
     closure, so this window is the whole bridge — and it only exists on a page with a
     recording, which is how a card on a silent page finds no ear to offer. */
  window.TargumSpeech = {
    /* Where a tapped span's sound sits: the clocks of every written word it overlaps,
       breathing a little either side — the chapter cutter's move — but never into the
       neighbouring word. Null where the recording never said it. */
    clockFor: function (segmentId, start, end) {
      var rows = wordClocks[segmentId];
      if (!rows || !rows.length) return null;
      var from = null;
      var until = null;
      var before = 0;
      var after = Infinity;
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        if (row[0] < end && row[1] > start) {
          if (from === null || row[2] < from) from = row[2];
          if (until === null || row[3] > until) until = row[3];
        } else if (row[1] <= start) {
          if (row[3] > before) before = row[3];
        } else if (row[0] >= end && row[2] < after) {
          after = row[2];
        }
      }
      if (from === null || until <= from) return null;
      var PAD = 0.15;
      /* Rounded like the build side's clocks, so a slice is a tidy number and not
         float dust the tests would have to forgive. */
      var opens = Math.max(before, from - PAD, 0);
      var closes = Math.min(after, until + PAD);
      return [Math.round(opens * 1000) / 1000, Math.round(closes * 1000) / 1000];
    },
    playSlice: function (slice) {
      halt();
      play(slice[0]);
      stopAt = setTimeout(halt, Math.max(0, ((slice[1] - slice[0]) * 1000) / audio.playbackRate));
    },
  };

  /* The whole scene: play, and pause where it stands rather than starting over. A
     control that only restarts is a control nobody presses twice. */
  function at(seconds) {
    for (var i = 0; i < order.length; i++) {
      if (seconds >= order[i].start && seconds < order[i].end) return order[i].id;
    }
    return order[0].id;
  }

  function toggleScene() {
    if (playing) {                      /* a single line was running; that ends here */
      if (stopAt) { clearTimeout(stopAt); stopAt = null; }
      playing.classList.remove("saying");
      playing = null;
      audio.pause();
    }
    if (following && !audio.paused) {   /* pause: keep the place and the mark */
      audio.pause();
      pressed(false);
      return;
    }
    following = true;
    pressed(true);
    var opening = order.length ? order[0].start : 0;
    var from = audio.ended || audio.currentTime <= 0 ? opening : audio.currentTime;
    play(from);
    mark(at(from));
  }

  scenes.forEach(function (button) {
    button.addEventListener("click", toggleScene);
  });

  function onTime() {
    if (fill && audio.duration) {
      fill.style.inlineSize = (audio.currentTime / audio.duration) * 100 + "%";
    }
    if (clock && audio.duration) {
      clock.textContent = clocked(audio.currentTime) + " / " + clocked(audio.duration);
    }
    if (!following) return;
    var at = audio.currentTime;
    for (var i = 0; i < order.length; i++) {
      if (at >= order[i].start && at < order[i].end) { mark(order[i].id); return; }
    }
  }

  /* Attached through a function because the instrument can be swapped once: a page
     whose sidecar video is gone falls back to the inlined audio, and the new element
     needs the same ears. The handlers read `audio` at call time, so nothing else
     changes hands. */
  function wire(element) {
    element.addEventListener("timeupdate", onTime);
    element.addEventListener("ended", halt);
  }
  wire(audio);

  /* Space plays and pauses — on a dialogue, and only on a dialogue.
   *
   * Space is already spoken for here: in paged mode it turns the page. Two meanings for
   * one key is the thing this file says elsewhere means neither, so the split is by text:
   * where a text can be listened to, Space plays it, and nowhere else.
   *
   * This was narrower for a day — dialogues only, on the reasoning that a book is fifty
   * chapters and the pager should keep its key. That was overruled, and it is the right
   * call: a reader who has pressed Space on one recorded text has learned what Space
   * does, and having it mean something else on the next one is the confusion the rule
   * against two meanings exists to prevent. The arrows and the pager still turn pages,
   * and the help card says which it is.
   *
   * Captured, because the pager listens on the way back up and would turn the page as
   * well — one keystroke doing two things is exactly what this is avoiding.
   *
   * `<` and `>` step the speed, the keys every video player has taught. Read off the
   * physical key as well as the character: under a Hebrew layout Shift on the comma
   * arrives as something else entirely, the way the letters do further up. */
  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    var key = event.key;
    if (event.shiftKey && event.code === "Comma") key = "<";
    if (event.shiftKey && event.code === "Period") key = ">";
    if (!/^[ <>]$/.test(key)) return;
    var on = document.activeElement;
    // SELECT is in this list and not in the argument below: Space is how a keyboard
    // opens one, and taking it away leaves the translations menu unopenable.
    if (
      on &&
      (on.tagName === "INPUT" || on.tagName === "SELECT" || on.tagName === "TEXTAREA" || on.isContentEditable)
    )
      return;
    /* Not even for a focused button, which would otherwise answer Space itself. On a page
       that can be listened to Space plays and does nothing else, so a button under the
       keyboard must not quietly take it — walking to the end of a text puts the keyboard
       on Done, and Space there would finish the text instead of playing it. Enter is what
       presses a button. */
    event.preventDefault();
    event.stopPropagation();
    if (key === " ") toggleScene();
    else stepRate(key === "<" ? -1 : 1);
  }, true);

  /* Saving the audio. The file is already in the page, so this asks the network for
     nothing — the same reason the fonts and the icons ride inside it. */
  if (player) {
    var get = player.querySelector(".player-get");
    if (get) {
      var named = (document.title || "dialogue").replace(/[\\/:*?"<>|]/g, "").trim();
      /* Named for what it actually is. The build inlines whatever the scene was voiced
         as, so a suffix written into the page rather than read off it hands the reader a
         file their machine opens with the wrong thing. */
      var ENDS = {
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/flac": "flac",
      };
      var kind = speech.audio.slice(5).split(";")[0].split(",")[0];
      get.setAttribute("href", speech.audio);
      get.setAttribute("download", (named || "dialogue") + "." + (ENDS[kind] || "mp3"));
    }

    /* Put away, and stays away. A reader who has met the player once does not need to be
       shown it every time they open a scene; the bar keeps its button for coming back. */
    // Per text, not per browser. It was one key for everything, on the reasoning that a
    // reader who has met the player once need not meet it again — and the cost of that
    // was closing it on one scene and finding every other scene silent, with a control
    // that was simply not on the page and no way to know why. Put away means put away
    // here.
    // The page needs to know a player is out: the blocks at the foot of a text sit after
    // the pairs, and the pairs are the only thing `room` budgets for — so the Done line
    // and the suggestion land inside the band the player is fixed in.
    function standing(out) {
      document.body.classList.toggle("has-player", !!out);
    }

    var STORE = "targum:player-closed:" + spokenOf;

    /* The pages were laid out before this ran, with room kept for a player that may be
       put away — so whenever that changes, they are laid out again. */
    function remeasure() {
      var reader = window.TargumReader;
      if (reader && reader.relayout) reader.relayout();
    }

    try {
      if (localStorage.getItem(STORE) === "1") {
        player.hidden = true;
        remeasure();
      }
    } catch (e) {}
    standing(!player.hidden);

    var shut = player.querySelector(".player-close");
    if (shut) {
      shut.addEventListener("click", function () {
        halt();
        player.hidden = true;
        try { targumKeep(STORE, "1"); } catch (e) {}
        standing(false);
        remeasure();
      });
    }

    /* Coming back through the bar's button unhides it, so the two are never out of step. */
    if (scenes.length > 1) {
      scenes[0].addEventListener("click", function () {
        if (!player.hidden) return;
        player.hidden = false;
        try { targumForget(STORE); } catch (e) {}
        standing(true);
        remeasure();
      });
    }
  }

  /* The picture, brought out and put away. Off by default — the reader is a reader,
     not a player, and the transport stays the strip — so the toggle only decides
     whether the picture is on the page, never whether anything sounds. Kept per text,
     like the closed player and for the same reason. On a narrow window the panel is an
     occupant of the band, one at a time with the sheet and the cards. */
  if (videoBox && videoEl) {
    var flips = Array.prototype.slice.call(document.querySelectorAll("[data-video]"));
    var VIDEO_STORE = "targum:video-open:" + spokenOf;

    var revideo = function () {
      var reader = window.TargumReader;
      if (reader && reader.relayout) reader.relayout();
    };

    var showVideo = function (out, chosen) {
      if (videoDead) out = false;
      videoBox.hidden = !out;
      flips.forEach(function (button) {
        button.setAttribute("aria-pressed", out ? "true" : "false");
      });
      var reader = window.TargumReader;
      if (out && reader && reader.occupy) reader.occupy("video");
      if (!out && reader && reader.vacate) reader.vacate("video");
      if (chosen) {
        try {
          if (out) targumKeep(VIDEO_STORE, "1");
          else targumForget(VIDEO_STORE);
        } catch (e) {}
      }
      revideo();
    };

    /* How the band puts the picture away when something else takes its place. */
    window.TargumVideo = {
      hide: function () { showVideo(false, false); },
    };

    flips.forEach(function (button) {
      button.addEventListener("click", function () {
        showVideo(videoBox.hidden, true);
      });
    });
    var shutVideo = videoBox.querySelector(".video-close");
    if (shutVideo) {
      shutVideo.addEventListener("click", function () { showVideo(false, true); });
    }

    /* The sidecar did not travel — a reader folder copied without its video/, or a
       page opened somewhere the file is not. The player swaps to the inlined audio
       and the page becomes exactly the audio reader, toggle and all. */
    videoEl.addEventListener("error", function () {
      if (videoDead) return;
      videoDead = true;
      var rate = nearestRate(audio.playbackRate);
      halt();
      showVideo(false, false);
      flips.forEach(function (button) {
        var group = button.closest(".group");
        if (group) group.hidden = true;
        else button.hidden = true;
      });
      audio = new Audio(speech.audio);
      wire(audio);
      setRate(rate, false);
    });

    try {
      if (localStorage.getItem(VIDEO_STORE) === "1") showVideo(true, false);
    } catch (e) {}
  }

  /* The video's home, opened at the line in front of the reader. The sidecar stays
     the instrument — it plays on a plane and this does not — and the link is a credit
     that happens to be useful: YouTube's own page, at the second this sentence starts.
     The address is fixed in the markup and only the time is decided, at the click
     rather than on every tick, because an address that changes forty times a minute
     is one nobody can copy. The spans are into this part's own cut, which begins
     `offset` seconds into the whole video; the two are added here. */
  var home = document.querySelector("[data-home]");
  if (home) {
    var homeBase = home.getAttribute("href");
    var homeOffset = Number(speech.offset) || 0;
    var homeAt = function () {
      // The line being spoken, then the one line playing, then the sentence in front
      // of the reader — and failing all three, the whole video from its start.
      var pair = marked || (playing && playing.closest(".pair"));
      if (!pair) {
        var reader = window.TargumReader;
        pair = reader && reader.inFront ? reader.inFront() : null;
      }
      var id = pair ? pair.getAttribute("data-id") : "";
      if (id && spans[id]) return homeOffset + spans[id][0];
      return audio.currentTime ? homeOffset + audio.currentTime : 0;
    };
    home.addEventListener("click", function () {
      var seconds = Math.max(0, Math.floor(homeAt()));
      home.href = homeBase + (seconds ? "&t=" + seconds + "s" : "");
    });
  }

  /* Leaving the page mid-sentence should not leave a voice talking into an empty room. */
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) halt();
  });
})();

};

if (window.TargumStore) window.TargumStore.ready(targumReader);
else targumReader();
