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
  var roots = data.roots || [];
  var binyanim = data.binyanim || [];
  // Absent in every reader with no Hebrew in it, and in one built before there was
  // anything to read the vowels with.
  var sounds = data.sounds || [];
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

  // Each sentence ships twice, bare and pointed, so both go through the server's bidi
  // isolation and neither has to be rebuilt here. Only one is ever on show.
  var plainCell = {};
  var pointedCell = {};
  // The pair a segment is drawn in. The word queue works in segment ids, because the
  // words themselves are data rather than page, and this is the one place it has to come
  // back to the page — to draw a pair's spans and to scroll to it.
  var pairBySegment = {};
  pairs.forEach(function (pair) {
    var segmentId = pair.getAttribute("data-id");
    plainCell[segmentId] = pair.querySelector(".src.plain");
    pointedCell[segmentId] = pair.querySelector(".src.pointed");
    pairBySegment[segmentId] = pair;
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
    localStorage.setItem("targum:opened", JSON.stringify(opened));

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
      localStorage.setItem("targum:days", JSON.stringify(days));
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

  // Shared with the words page, which has to be able to run it too.
  if (window.TargumVocab) window.TargumVocab.migrate(language, documentId);

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
      localStorage.setItem(store.name, JSON.stringify(store.records));
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
  // Words whose meaning the card has already asked the cache for, found or not.
  var peeked = {};
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
          onDone(true);
        } else {
          onDone(false);
        }
      })
      .catch(function () {
        onDone(false);
      });
  }

  function lookUp(index, sentence, onDone) {
    var lemma = lemmas[index];
    if (!lemma || !canAsk()) return;
    if (asked[lemma]) return;
    asked[lemma] = true;
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

  function undo() {
    var last = undoable.pop();
    if (!last) return false;
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

  function setStatus(index, surface, band, status) {
    var lemma = lemmas[index];
    if (!lemma) return false;
    recordUndo(index, lemma, surface);
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
    return now;
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
    var entry = translationData[showing] || translationData.t0;
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

  // Whether this chapter has had anything waiting while you were on it. One you open
  // already finished shows the ordinary count; one you finish yourself is told so.
  var wasWaiting = false;

  function renderStats() {
    var counts = coverage();
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
  }

  function showList(open, remembered) {
    // On a wide window the list takes a column of the width from the page rather than
    // covering it, so opening one re-wraps every line above the reader as well as below.
    var held = open === body.classList.contains("list-open") ? null : hold();
    if (remembered !== false) prefs.list = open;
    if (listBox) listBox.hidden = !open;
    if (listTab) listTab.hidden = open;
    body.classList.toggle("list-open", open);
    keep(held);
    relay();
    if (remembered !== false) save();
  }

  var roomy = window.matchMedia("(min-width: 60rem)");

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
    letGo();
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
          ? pair.querySelector('.w[data-lemma="' + index + '"]')
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
      // The field says what it is for, in the reader's words: the same line is its
      // accessible name, and "Enter text" was the one label on the card that was not.
      placeholder: "Your own meaning",
      onStatus: function (value) {
        setStatus(index, surface, band, value);
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

  // How the word you tapped is said, for this occurrence and not for its dictionary
  // form. בצל is batsˈal after "I ate" and btsˈel under a tree; the lemma is the same
  // word in both and the row drawn here is the only thing that knows which was meant.
  function readingOf(word) {
    if (!sounds.length) return "";
    var pair = word.closest ? word.closest(".pair") : null;
    var span = (word.getAttribute("data-bare") || "").split(",");
    if (!pair || span.length !== 2) return "";
    var rows = wordData[pair.getAttribute("data-id")] || [];
    var start = parseInt(span[0], 10);
    var end = parseInt(span[1], 10);
    for (var i = 0; i < rows.length; i++) {
      if (rows[i][0] === start && rows[i][1] === end) return sounds[rows[i][5]] || "";
    }
    return "";
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

    // Directly under the word, because it is about the word rather than about its
    // dictionary form, and because the stress is the half of it a learner cannot get
    // from the spelling and will not find in any dictionary entry either.
    var said = readingOf(word);
    if (said) {
      var say = document.createElement("span");
      say.className = "said";
      say.appendChild(document.createTextNode("said "));
      var heard = document.createElement("bdi");
      heard.setAttribute("dir", "ltr");
      heard.textContent = said;
      say.appendChild(heard);
      card.appendChild(say);
    }

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
    }

    card.appendChild(statusRow(index, surface, level));

    if (word.classList.contains("split")) {
      // Say so rather than presenting one reading of an ambiguous string as settled.
      var caveat = document.createElement("span");
      caveat.className = "caveat";
      caveat.textContent = "read as a prefix plus a word";
      card.appendChild(caveat);
    }

    // The card teaches its own keys. Shown whether or not you arrived by keyboard,
    // because a reader who taps is exactly the one who has not found out yet that there
    // is a faster way through a page — and the place they are already looking is here.
    // The arrow is the one that goes forward on this page: §7 wants the typed character
    // per reading direction.
    var legend = document.createElement("span");
    legend.className = "legend";
    var offering = !!card.querySelector(".look-up");
    legend.textContent =
      (rtl ? "←" : "→") +
      " next · k known · 1 2 3 · i ignore · " +
      (offering ? "Enter look up · " : "") +
      "u back · ? all keys";
    card.appendChild(legend);

    card.hidden = false;
    placeNear(card, word.getBoundingClientRect());
  }

  /* --- keeping a phrase ---------------------------------------------------- */

  var chip = document.getElementById("pick-chip");

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
    pickLevel = null;
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
        hideChip();
        redraw();
      },
    });
    placeChip(picked.rect);
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
  function ceiling() {
    return (bar ? bar.getBoundingClientRect().height : 0) + 16;
  }

  // The sentence in the middle of the reading area, which is where a reader's eye is
  // rather than where the text happens to begin. Held instead of the sentence at the top
  // of the window — which is the one they have just finished — a change of layout leaves
  // them looking at the words they were looking at, with as much of the page they have
  // read still above as there was before.
  function middle() {
    var top = ceiling();
    var eye = top + (window.innerHeight - top) / 2;
    for (var n = 0; n < pairs.length; n++) {
      if (pairs[n].getBoundingClientRect().bottom >= eye) return pairs[n];
    }
    // Nothing reaches the middle: the end of a chapter, where the last screenful is
    // mostly the space under it.
    return pairs[pairs.length - 1] || null;
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
    // The cell on show, which is the one `markPair` drew: the other keeps whatever spans
    // it had when it was last visible, and they are the wrong page's.
    var cell = (prefs.nikkud && pointedCell[segmentId]) || plainCell[segmentId];
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
      localStorage.setItem(PLACE, JSON.stringify(all));
    } catch (e) {}
  }

  // Two events, because neither one covers a reader on its own. `pagehide` is the one
  // that fires when a page is navigated away from or its tab is closed; a phone put down
  // mid-sentence may never see it, because a backgrounded tab can be discarded without
  // being given another frame, and `visibilitychange` is the last word that tab hears.
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
      word = pair.querySelector('.w[data-bare^="' + kept.word + ',"]');
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
      placeNear(card, lookedUp.getBoundingClientRect());
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

  function applyMode() {
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
    keysCard.hidden = !open;
    // The button discloses the panel, so it has to say whether the panel is open. Focus
    // stays on the word either way: looking up a key must not cost you your place.
    if (keysButton) keysButton.setAttribute("aria-expanded", open ? "true" : "false");
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
      if (button.hasAttribute("data-nikkud-toggle")) {
        prefs.nikkud = !prefs.nikkud;
        applyNikkud();
        save();
        return;
      }
      var action = button.getAttribute("data-type");
      if (action) {
        var held = hold();
        if (action === "larger") prefs.size += 0.0625;
        if (action === "smaller") prefs.size -= 0.0625;
        if (action === "looser") prefs.leading = nextLeading(prefs.leading);
        applyType();
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

    // A word answers the same way whichever mode you are in. Marking changes what the
    // page shows you, never what it lets you do — you have to be able to mark a word to
    // clear it, and the whole point of the mode is clearing them.
    var word = event.target.closest ? event.target.closest(".w") : null;
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
    var here = segmentIndex(from.segment);
    for (var n = 0; n < list.length; n++) {
      var entry = list[forward ? n : list.length - 1 - n];
      var there = segmentIndex(entry.segment);
      if (there === -1) continue;
      var after = there > here || (there === here && entry.start > from.start);
      var before = there < here || (there === here && entry.start < from.start);
      if (forward ? after : before) return entry;
    }
    return null;
  }

  // The next word, and round to the beginning when the end is reached with words still
  // waiting earlier in the chapter — which is what happens whenever you started in the
  // middle, and starting in the middle is the ordinary case. The header says how many are
  // left, so stopping dead against an invisible wall would be the page contradicting its
  // own counter. It cannot spin: every word it lands on is one the queue still holds, and
  // dealing with a word takes it out.
  function onward(from, forward) {
    return step(from, forward) || step(null, forward);
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
    return step(edge, forward) || step(null, forward);
  }

  // The sentence in front of the reader: the first one not yet scrolled past. Measured
  // from the top of the text rather than the top of the window, because the bar is
  // sticky and a sentence behind it is one you have already read.
  function onScreen() {
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
    // By offset as well as by lemma. A pair can hold two forms of one dictionary word,
    // and a saved phrase drawn across a word slices it into several spans — the first
    // piece is enough, because `bareSurface` reads the whole word back out of
    // `data-bare` whichever piece you hand it.
    var span = pair.querySelector(
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
    // Nothing that way. A card already open stays open: closing it out from under
    // somebody who pressed an arrow at the end of the chapter answers the wrong question.
    if (!entry) return !!place;
    // Stepping through words the page is not painting is a mode you can be lost in. `m`
    // puts it back.
    if (!prefs.marking) {
      prefs.marking = true;
      applyMarking();
      save();
    }
    // Already true where the card is open: a walk that reached the end of what it can
    // reach leaves you on the word you were on rather than on nothing.
    return goTo(entry, forward, asking()) || !!place;
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
        return;
      case "o":
        prefs.mode = "source";
        applyMode();
        settle();
        save();
        return;
      // `l` rather than `i`: `i` is ignore, on a word, and it cannot also be a mode.
      // The translation goes under each line, which is where the letter comes from.
      case "l":
        prefs.mode = "inter";
        applyMode();
        settle();
        save();
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
      case "Escape": {
        // One layer a press. Closing the keys and then dropping out of the queue in the
        // same keystroke costs a reader their place for looking a shortcut up.
        if (keysCard && !keysCard.hidden) {
          showKeys(false);
          return;
        }
        // The card next, and you stay where you are — the two are separate things, and
        // one key that did both would cost you your place to close a window.
        // A card that is already leaving is not a layer to be closed: Escape would
        // read as doing nothing, and the reader would have to press it twice to get
        // out of the queue.
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
  // leaving it set would hide every sentence on the page.
  if (!hasNikkud) {
    prefs.nikkud = false;
  } else {
    var chosen = prefs.nikkudBy ? prefs.nikkudBy[documentId] : undefined;
    prefs.nikkud = chosen === undefined ? !!data.sourcePointed : !!chosen;
  }
  applyNikkud();
  // The page is laid out from here on, so from here on a change to it can be measured.
  living = true;
  took("marks drawn on what is on screen");
  // After the layout every control has a say in, and before the reader can have touched
  // any of them: a scroll to where they left off has to be measured against the page
  // they left, in the mode and at the size they left it in.
  resume();
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
      return setStatus(index, lemmas[index], "", toggled(index, status));
    },
    undo: undo,
  };
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
  maybe();
})();
