/* The rest of the reader: what a first tap does not need (targum-internal#503).
 *
 * A word answers a tap once `reader.js` has run, and a page runs its scripts in order as
 * they arrive, so everything in `reader.js` was bytes a word waited for. What it needs
 * is there: the words, the card and the lookups, the page cut into pages and the place
 * kept. What it does not is here, after the faces: the lenses and the case lens, export
 * and the Anki deck, shnayim mikra, the bar's panels and the keys card, full screen and
 * the pull that closes a sheet, the keyboard, and dragging over words to keep a phrase.
 *
 * This file only defines `targumReaderRest`; `reader.js` runs it at its foot, and hands
 * it `R`, the names of its own that the code here reads. A name whose value changes
 * while the page is open is read through `R` where it is used (`R.showing`), so it is
 * always the current one; every other is taken once, below. `reader.js` answers for what
 * lives here with a line that passes the call on (`passOn`), which does nothing until this
 * file has arrived: a press of the bar in the moment before then is a press on a page
 * still arriving. Like `player.js`, it runs itself on arrival when the reader got there
 * first (the foot of this file), and is run by the reader when it did not.
 */
window.targumReaderRest = function (R) {
  "use strict";

  // The reader's names this file reads and nothing changes once the page is set up.
  var CASE_LENS = R.CASE_LENS, IGNORED = R.IGNORED, KNOWN = R.KNOWN, LIST_FULL = R.LIST_FULL,
    already = R.already, applyMarking = R.applyMarking, applyMode = R.applyMode,
    applyPaged = R.applyPaged, applyTranslation = R.applyTranslation, askMeaning = R.askMeaning,
    askPhrase = R.askPhrase, asking = R.asking, bandOf = R.bandOf, bar = R.bar,
    besideId = R.besideId, besideTables = R.besideTables, binyanim = R.binyanim, body = R.body,
    card = R.card, caseWord = R.caseWord, cellText = R.cellText, cells = R.cells, chip = R.chip,
    companionKeys = R.companionKeys, documentId = R.documentId, feat = R.feat,
    finishedAt = R.finishedAt, firstMeeting = R.firstMeeting, grabHandle = R.grabHandle,
    grammarTable = R.grammarTable, gt = R.gt, hearButton = R.hearButton, hideCard = R.hideCard,
    inTarget = R.inTarget, keepMeaning = R.keepMeaning, keysButton = R.keysButton,
    keysCard = R.keysCard, language = R.language, leaveQueue = R.leaveQueue, lemmas = R.lemmas,
    listBox = R.listBox, markLookedUp = R.markLookedUp, markMap = R.markMap,
    markSegment = R.markSegment, more = R.more, namedTerm = R.namedTerm,
    nextChapter = R.nextChapter, nextOrder = R.nextOrder, noteOf = R.noteOf, noteOn = R.noteOn,
    occupy = R.occupy, openCard = R.openCard, openedBefore = R.openedBefore, paged = R.paged,
    paintSize = R.paintSize, pairs = R.pairs, phraseEntries = R.phraseEntries,
    phraseHeld = R.phraseHeld, phrasePending = R.phrasePending, phraseTerm = R.phraseTerm,
    pops = R.pops, practiceKeys = R.practiceKeys, practising = R.practising, prefs = R.prefs,
    read = R.read, redraw = R.redraw, relayout = R.relayout, remember = R.remember,
    roomy = R.roomy, root = R.root, roots = R.roots, rtl = R.rtl, save = R.save, say = R.say,
    seatFoot = R.seatFoot, seatNear = R.seatNear, sectionId = R.sectionId,
    segmentText = R.segmentText, setStatus = R.setStatus, settle = R.settle,
    showList = R.showList, showPage = R.showPage, showTimings = R.showTimings, stamp = R.stamp,
    statusRow = R.statusRow, t = R.t, title = R.title, toBare = R.toBare,
    toggleTaamim = R.toggleTaamim, toggleVowels = R.toggleVowels,
    translationData = R.translationData, translationFor = R.translationFor, turnBy = R.turnBy,
    turnTo = R.turnTo, undo = R.undo, vacate = R.vacate, walk = R.walk, wordData = R.wordData,
    wordEntries = R.wordEntries, writeMeaning = R.writeMeaning;

  /* --- one case at a time --------------------------------------------------
   *
   * A Russian page can light every word in one case: the wash kept words wear, and a
   * dotted underline so the mark never rests on colour alone (design.md §4). One case,
   * never six colours; chosen, never on by default; forgotten when the page is left
   * (targum-internal#261). The count of each case on this page rides in its option, so
   * "genitive · 12" is both the label and the answer to how many.
   */
  var caseLens = document.querySelector("[data-case-lens]");
  var caseCounts = {};
  CASE_LENS.forEach(function (name) {
    caseCounts[name] = 0;
  });
  Object.keys(wordData).forEach(function (segmentId) {
    (wordData[segmentId] || []).forEach(function (token) {
      var inCase = token.length > 8 ? feat(grammarTable[token[8]] || "", "Case") : "";
      if (caseCounts[inCase] !== undefined) caseCounts[inCase]++;
    });
  });
  if (caseLens) {
    Array.prototype.forEach.call(caseLens.options, function (option) {
      if (!option.value) return;
      var count = caseCounts[option.value] || 0;
      option.textContent = caseWord(option.value) + " · " + count;
      option.disabled = !count;
    });
    caseLens.addEventListener("change", function () {
      showCase(caseLens.value);
    });
  }

  function showCase(name) {
    var chosen = CASE_LENS.indexOf(name) >= 0 ? name : "";
    if (chosen) {
      body.setAttribute("data-case", chosen);
      showGoverned(false, true);
      showOrder(false, true);
      showVav(false, true);
      showSuffix(false, true);
    } else body.removeAttribute("data-case");
    if (caseLens) caseLens.value = chosen;
    say(
      chosen
        ? cueOnce("case", t("reader.case.cue", "Every word lit is in the {case}.", { case: caseWord(chosen) })) ||
            t("reader.case.said", "{case}, {n} here.", { case: caseWord(chosen), n: caseCounts[chosen] })
        : t("reader.case.none", "No case shown.")
    );
  }

  /* --- lenses wait for a second read -------------------------------------------
   *
   * design.md §12, "Lenses wait for a second read" (2026-10-13), from the research in
   * targum-internal#439: lighting a feature buys a little form at a cost to
   * comprehension, and only with a line saying what to look at. So no lens is offered on
   * a first read: its row appears once this part is finished, or when the text is
   * opened again. One lens is on at a time, the first time one is turned on it says
   * what it shows, and none is remembered past the page.
   */
  var lensRows = document.querySelectorAll(".lens-row");
  var cued = {};

  function cueOnce(name, line) {
    if (cued[name]) return "";
    cued[name] = true;
    return line;
  }

  function offerLenses() {
    Array.prototype.forEach.call(lensRows, function (row) {
      row.hidden = false;
    });
  }

  var governedLens = document.querySelector("[data-governed-lens]");
  // Counted off the page's data rather than the drawn words, which may not be drawn yet.
  function governedCount() {
    var count = 0;
    Object.keys(wordData).forEach(function (segmentId) {
      (wordData[segmentId] || []).forEach(function (token) {
        if (token.length > 8 && feat(grammarTable[token[8]] || "", "Takes")) count++;
      });
    });
    return count;
  }

  // One lens at a time: turning one on turns the case and the other switch off, and every
  // switch says whether it is the one on.
  function lensOn(name) {
    if (name) {
      body.setAttribute("data-lens", name);
      if (body.getAttribute("data-case")) {
        body.removeAttribute("data-case");
        if (caseLens) caseLens.value = "";
      }
    } else body.removeAttribute("data-lens");
    if (governedLens) governedLens.setAttribute("aria-pressed", name === "governed" ? "true" : "false");
    if (orderLens) orderLens.setAttribute("aria-pressed", name === "order" ? "true" : "false");
    if (vavLens) vavLens.setAttribute("aria-pressed", name === "vav" ? "true" : "false");
    if (suffixLens) suffixLens.setAttribute("aria-pressed", name === "suffix" ? "true" : "false");
  }

  function showGoverned(on, quietly) {
    if (!governedLens) return false;
    if (on) lensOn("governed");
    else if (body.getAttribute("data-lens") === "governed") lensOn("");
    if (quietly) return true;
    say(
      on
        ? cueOnce(
            "governed",
            t("reader.lens.governed-cue", "Each verb lit takes the preposition lit beside it, in this line.")
          ) || t("reader.lens.governed-said", "Prepositions verbs take, {n} here.", { n: governedCount() })
        : t("reader.lens.none", "No lens shown.")
    );
    return true;
  }

  /* The word-order lens: a Russian subject that comes after its verb, lit (design.md §12,
   * "Subjects after their verb, on a lens", 2026-10-13). Russian says who did it with the
   * ending, so "Книгу написал Толстой" is Tolstoy writing the book, and a reader who takes
   * the first noun for the subject reads it backwards. */
  var orderLens = document.querySelector("[data-order-lens]");
  function orderCount() {
    var count = 0;
    Object.keys(wordData).forEach(function (segmentId) {
      (wordData[segmentId] || []).forEach(function (token) {
        if (token.length > 8 && feat(grammarTable[token[8]] || "", "Order") === "VS") count++;
      });
    });
    return count;
  }

  function showOrder(on, quietly) {
    if (!orderLens) return false;
    if (on) lensOn("order");
    else if (body.getAttribute("data-lens") === "order") lensOn("");
    if (quietly) return true;
    say(
      on
        ? cueOnce("order", t("reader.lens.order-cue", "Each word lit is the subject of a verb before it.")) ||
            t("reader.lens.order-said", "Subjects after their verb, {n} here.", { n: orderCount() })
        : t("reader.lens.none", "No lens shown.")
    );
    return true;
  }

  if (orderLens) {
    orderLens.addEventListener("click", function () {
      showOrder(body.getAttribute("data-lens") !== "order");
    });
  }

  // `w` turns the word-order lens on and off, where the page has it and it is offered.
  function toggleOrder() {
    if (!orderLens || orderLens.hidden) return false;
    return showOrder(body.getAttribute("data-lens") !== "order");
  }

  /* The vav lens: every vav-consecutive on a Biblical page, lit (targum-internal#449,
   * 2026-10-21). ויאמר is spelled as the future, "he will say", and read as the past, "he
   * said"; the narrative runs on it, and a reader who takes the spelling at its word reads
   * the whole story as yet to happen. */
  var vavLens = document.querySelector("[data-vav-lens]");
  function vavCount() {
    var count = 0;
    Object.keys(wordData).forEach(function (segmentId) {
      (wordData[segmentId] || []).forEach(function (token) {
        if (token.length > 8 && feat(grammarTable[token[8]] || "", "Vav") === "Cons") count++;
      });
    });
    return count;
  }

  function showVav(on, quietly) {
    if (!vavLens) return false;
    if (on) lensOn("vav");
    else if (body.getAttribute("data-lens") === "vav") lensOn("");
    if (quietly) return true;
    say(
      on
        ? cueOnce("vav", t("reader.lens.vav-cue", "Each word lit is a future form the vav turns into the past.")) ||
            t("reader.lens.vav-said", "The narrative past, {n} here.", { n: vavCount() })
        : t("reader.lens.none", "No lens shown.")
    );
    return true;
  }

  if (vavLens) {
    vavLens.addEventListener("click", function () {
      showVav(body.getAttribute("data-lens") !== "vav");
    });
  }

  // `y` turns the vav lens on and off, where the page has it and it is offered.
  function toggleVav() {
    if (!vavLens || vavLens.hidden) return false;
    return showVav(body.getAttribute("data-lens") !== "vav");
  }

  /* The suffix lens: every word with a pronoun on the end, lit (targum-internal#450,
   * 2026-10-21). שלו, אותך, לפניהם: the pronoun is fused onto the word, so a reader who
   * looks the word up finds the preposition or the noun and loses whose it is. */
  var suffixLens = document.querySelector("[data-suffix-lens]");
  function suffixCount() {
    var count = 0;
    Object.keys(wordData).forEach(function (segmentId) {
      (wordData[segmentId] || []).forEach(function (token) {
        if (token.length > 8 && feat(grammarTable[token[8]] || "", "Pron")) count++;
      });
    });
    return count;
  }

  function showSuffix(on, quietly) {
    if (!suffixLens) return false;
    if (on) lensOn("suffix");
    else if (body.getAttribute("data-lens") === "suffix") lensOn("");
    if (quietly) return true;
    say(
      on
        ? cueOnce("suffix", t("reader.lens.suffix-cue", "Each word lit has a pronoun on the end.")) ||
            t("reader.lens.suffix-said", "Pronoun endings, {n} here.", { n: suffixCount() })
        : t("reader.lens.none", "No lens shown.")
    );
    return true;
  }

  if (suffixLens) {
    suffixLens.addEventListener("click", function () {
      showSuffix(body.getAttribute("data-lens") !== "suffix");
    });
  }

  // `e` turns the suffix lens on and off, where the page has it and it is offered.
  function toggleSuffix() {
    if (!suffixLens || suffixLens.hidden) return false;
    return showSuffix(body.getAttribute("data-lens") !== "suffix");
  }

  if (openedBefore || finishedAt()) offerLenses();

  if (governedLens) {
    governedLens.addEventListener("click", function () {
      showGoverned(body.getAttribute("data-lens") !== "governed");
    });
  }

  // `r` turns the prepositions lens on and off, where the page has it and it is offered.
  function toggleGoverned() {
    if (!governedLens || governedLens.hidden) return false;
    return showGoverned(body.getAttribute("data-lens") !== "governed");
  }

  // `c` steps through the cases this page has, and past the last one back to none.
  function nextCase() {
    if (!caseLens || caseLens.closest(".lens-row").hidden) return false;
    var present = CASE_LENS.filter(function (name) {
      return caseCounts[name] > 0;
    });
    var at = present.indexOf(body.getAttribute("data-case") || "");
    showCase(at + 1 < present.length ? present[at + 1] : "");
    return true;
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

  function statusName(status) {
    if (status === 1) return gt("reader.grammar.status-1", "new to you");
    if (status === 2) return gt("reader.grammar.status-2", "still learning");
    if (status === 3) return gt("reader.grammar.status-3", "almost known");
    if (status === KNOWN) return gt("reader.grammar.status-known", "known");
    if (status === IGNORED) return gt("reader.grammar.status-ignored", "ignored");
    return "";
  }

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


  // Two lists, two files. Mixing them meant one column existed only to say which of
  // the two each row was, and neither could be opened as what it is.
  //
  // Both are this text's, matching what the panel shows. Your whole vocabulary in a
  // language is a different export and lives on the library page, where the library is.
  // The meaning column is in one language, so the header says which. A file that only
  // said "meaning" was a column of Russian under an English word for anyone who read in
  // both and opened it a month later.
  function meaningColumn() {
    var entry = translationData[R.showing] || {};
    var name = entry.languageName || R.targetLanguage;
    return name
      ? t("reader.export.meaning-in", "meaning ({language})", { language: name })
      : t("reader.export.meaning", "meaning");
  }

  function exportWords() {
    download(
      title() + " — words.csv",
      [
        t("reader.export.word", "word"),
        t("reader.export.dictionary-form", "dictionary form"),
        t("reader.export.difficulty", "difficulty"),
        t("reader.export.how-well", "how well"),
        meaningColumn(),
      ],
      wordEntries().map(function (entry) {
        return [
          namedTerm(entry) || entry.term,
          entry.lemma,
          entry.level || "",
          statusName(entry.status),
          entry.meaning || "",
        ];
      })
    );
  }

  function exportPhrases() {
    download(
      title() + " — phrases.csv",
      [
        t("reader.export.phrase", "phrase"),
        (function () {
          var entry = translationData[R.showing] || {};
          var name = entry.languageName || R.targetLanguage;
          return name
            ? t("reader.export.reading-in", "reading ({language})", { language: name })
            : t("reader.export.reading", "reading");
        })(),
      ],
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


  // What goes on the cards: one per entry the list is showing, in the list's order.
  function ankiCards(kind) {
    if (kind === "phrases") {
      return phraseEntries().map(function (entry) {
        var pick = (R.picks[entry.segmentId] || [])[entry.index] || {};
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
      var line = met && met.token.length > 8 ? grammarTable[met.token[8]] || "" : "";
      var named = namedTerm(entry);
      return {
        front: named || (met ? readingRun(met.segmentId, met.token[0], met.token[1]) : entry.term),
        // What the reader wrote or kept first; failing that, the meaning the page
        // shipped, which is what the card beside the word shows.
        meaning: entry.meaning || (index >= 0 && R.glosses[index]) || "",
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
        if (card.root) verb.push(t("reader.card.root", "root ") + ankiField(card.root.split("").join("\u05be")));
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

  /* --- shnayim mikra --------------------------------------------------------------
   *
   * The weekly practice, on a text that carries Onkelos beside the Hebrew: each verse
   * read twice in Hebrew and once in Onkelos (targum-internal#202). People keep it two
   * ways and both are here — verse by verse, or the whole aliyah twice and then its
   * Onkelos — because serving one custom would turn away the other.
   *
   * The structure is the progress. Nothing here counts anything: a verse read is quieter
   * than one still to read, the foot says which reading of the aliyah this is, and the
   * section's own Done is where it finishes, as every section does (#173). Nor does it
   * rule on anything — how many readings, what counts — it lays the text out in the
   * order the practice reads it and says nothing more.
   *
   * Where a reader is in it is kept per section and per way of keeping it, so leaving
   * the practice, switching between the two, or closing the page loses no place — and
   * the words, which live in their own stores, are never touched by any of it.
   */
  var PRACTICE = "targum:practice";
  var practiceStore = read(PRACTICE, "{}");
  var practiceAt = documentId + "#" + sectionId;
  // Every verse of the section, in order. A heading is the section's name, not a verse.
  var practiceVerses = pairs.filter(function (pair) {
    return /(^|\s)verse(\s|$)/.test(pair.className || "") || pair.classList.contains("verse");
  });
  // The verse walk has run off the end of the section.
  var PRACTICE_DONE = "done";
  var practiceLine = null;
  // Onkelos is put in the column for the third reading of an aliyah and taken out
  // again afterwards, back to whatever the reader had there.
  var borrowedFrom = "";
  var practiceStep = document.getElementById("practice-step");
  var practiceSaid = document.getElementById("practice-said");
  var practiceNext = document.getElementById("practice-next");

  function practiceKind() {
    if (!practising) return "";
    return prefs.practice === "verse" || prefs.practice === "section" ? prefs.practice : "";
  }

  function practiceRecord() {
    var mine = practiceStore[practiceAt];
    if (!mine || typeof mine !== "object") mine = practiceStore[practiceAt] = {};
    if (!(mine.pass >= 1 && mine.pass <= 3)) mine.pass = 1;
    if (!(mine.step >= 0 && mine.step <= 2)) mine.step = 0;
    if (typeof mine.verse !== "string") mine.verse = "";
    return mine;
  }

  function keepPractice() {
    try {
      targumKeep(PRACTICE, JSON.stringify(practiceStore));
    } catch (e) {}
  }

  // Which verse the walk stands on: the one kept, the first where none is or where the
  // one kept is no longer in the section, and -1 once the walk has run off the end.
  function practiceIndex(record) {
    if (record.verse === PRACTICE_DONE) return -1;
    for (var i = 0; i < practiceVerses.length; i++) {
      if (practiceVerses[i].getAttribute("data-id") === record.verse) return i;
    }
    return practiceVerses.length ? 0 : -1;
  }

  function practiceButton(label, onPress) {
    var button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", onPress);
    return button;
  }

  function drawVerseWalk(record) {
    if (practiceLine && practiceLine.parentNode) practiceLine.parentNode.removeChild(practiceLine);
    practiceLine = null;
    practiceVerses.forEach(function (pair) {
      pair.classList.remove("practised");
      pair.classList.remove("practising");
    });
    if (!record) return;
    var at = practiceIndex(record);
    var upTo = at < 0 ? practiceVerses.length : at;
    for (var i = 0; i < upTo; i++) practiceVerses[i].classList.add("practised");
    if (at < 0) return;
    var pair = practiceVerses[at];
    var id = pair.getAttribute("data-id");
    pair.classList.add("practising");
    var line = document.createElement("div");
    line.className = "practice-line";
    if (record.step === 2) {
      var entry = translationData[besideId] || {};
      var onkelos = document.createElement("p");
      onkelos.className = "practice-targum";
      if (entry.language) onkelos.setAttribute("lang", entry.language);
      if (entry.direction) onkelos.setAttribute("dir", entry.direction);
      onkelos.textContent = (entry.text && entry.text[id]) || "";
      line.appendChild(onkelos);
    }
    var row = document.createElement("div");
    row.className = "practice-row";
    row.setAttribute("dir", "ltr");
    var said = document.createElement("span");
    said.textContent = [
      t("reader.practice.in-hebrew", "In Hebrew"),
      t("reader.practice.again-hebrew", "Again, in Hebrew"),
      t("reader.practice.in-onkelos", "In Onkelos"),
    ][record.step];
    row.appendChild(said);
    var last = at === practiceVerses.length - 1;
    row.appendChild(
      practiceButton(
        record.step === 0
          ? t("reader.practice.again", "Again")
          : record.step === 1
            ? t("reader.practice.onkelos", "Onkelos")
            : last
              ? t("reader.practice.finish", "Finish")
              : t("reader.practice.next-verse", "Next verse"),
        advancePractice
      )
    );
    line.appendChild(row);
    pair.appendChild(line);
    practiceLine = line;
    // Onkelos under the verse is words, like Onkelos in the column (targum-internal#202).
    var targum = line.querySelector ? line.querySelector(".practice-targum") : null;
    if (targum && R.targumTable && besideTables[R.targumTable].rows[id]) markSegment(targum);
  }

  function drawPracticeFoot(kind, record) {
    if (!practiceStep) return;
    var words = "";
    var press = "";
    var again = false;
    if (kind === "section") {
      words = [
        t("reader.practice.first-reading", "First reading, in Hebrew"),
        t("reader.practice.second-reading", "Second reading, in Hebrew"),
        t("reader.practice.once-onkelos", "Once in Onkelos"),
      ][record.pass - 1];
      press = [
        t("reader.practice.read-again", "Read it again"),
        t("reader.practice.now-onkelos", "Now Onkelos"),
        t("reader.practice.start-again", "Start again"),
      ][record.pass - 1];
      again = record.pass === 3;
    } else if (kind === "verse" && record.verse === PRACTICE_DONE) {
      words = t("reader.practice.every-verse", "Every verse, twice in Hebrew and once in Onkelos");
      press = t("reader.practice.start-again", "Start again");
      again = true;
    }
    practiceStep.hidden = !words;
    if (practiceSaid) practiceSaid.textContent = words;
    if (practiceNext) {
      practiceNext.textContent = press;
      // From the step, not the words, which are the reader's language.
      practiceNext.classList.toggle("again", again);
    }
  }

  function applyPractice(first) {
    var kind = practiceKind();
    var record = practiceRecord();
    practiceKeys.forEach(function (key) {
      var on = (key.getAttribute("data-practice") || "") === kind;
      key.classList.toggle("on", on);
      key.setAttribute("aria-pressed", on ? "true" : "false");
    });
    var ended =
      (kind === "section" && record.pass === 3) ||
      (kind === "verse" && record.verse === PRACTICE_DONE);
    body.classList.toggle("practice-verse", kind === "verse");
    body.classList.toggle("practice-section", kind === "section");
    // The Hebrew alone, for every reading but the aliyah's third.
    body.classList.toggle("practice-hebrew", kind === "verse" || (kind === "section" && !ended));
    body.classList.toggle("practice-ended", ended);

    var wantOnkelos = kind === "section" && record.pass === 3;
    if (wantOnkelos && R.showing !== besideId) {
      borrowedFrom = R.showing;
      applyTranslation(besideId, false, false);
    } else if (!wantOnkelos && borrowedFrom && R.showing === besideId) {
      var back = borrowedFrom;
      borrowedFrom = "";
      applyTranslation(back, false, false);
    } else if (!wantOnkelos) {
      borrowedFrom = "";
    }

    drawVerseWalk(kind === "verse" ? record : null);
    drawPracticeFoot(kind, record);
    paintPracticeSwitch(kind);
    if (!first) relayout();
  }

  /* Shnayim mikra is a switch, not a layout (David, 2026-10-05, targum-internal#421).
     On, it offers the two ways of keeping it, and the columns beside the verse stand
     aside: their switches go grey and say "Shown in Read", because a switch that looks
     pressed and does nothing is a switch that lies. */
  var practiceSwitch = document.getElementById("practice-on");
  var practiceHow = document.getElementById("practice-how");
  var columnsHeld = document.getElementById("columns-held");
  //: The way the practice was last kept, for the switch to turn it back on with.
  var practiceWay = "verse";

  function paintPracticeSwitch(kind) {
    if (kind) practiceWay = kind;
    if (practiceSwitch) {
      practiceSwitch.classList.toggle("on", !!kind);
      practiceSwitch.setAttribute("aria-pressed", kind ? "true" : "false");
    }
    if (practiceHow) practiceHow.hidden = !kind;
    if (columnsHeld) columnsHeld.hidden = !kind;
    companionKeys.forEach(function (key) {
      key.classList.toggle("held", !!kind);
      if (kind) key.setAttribute("aria-describedby", "columns-held");
      else key.removeAttribute("aria-describedby");
    });
  }

  if (practiceSwitch) {
    practiceSwitch.addEventListener("click", function () {
      choosePractice(practiceKind() ? "" : practiceWay);
    });
  }

  function showPracticeVerse() {
    var at = practiceIndex(practiceRecord());
    var pair = at < 0 ? practiceVerses[practiceVerses.length - 1] : practiceVerses[at];
    if (!pair) return;
    if (paged()) turnTo(pair);
    else if (typeof pair.scrollIntoView === "function") {
      pair.scrollIntoView({ block: "nearest" });
    }
  }

  function advancePractice() {
    var kind = practiceKind();
    var record = practiceRecord();
    if (kind === "verse") {
      var at = practiceIndex(record);
      if (at < 0) {
        record.verse = practiceVerses.length ? practiceVerses[0].getAttribute("data-id") : "";
        record.step = 0;
      } else if (record.step < 2) {
        record.verse = practiceVerses[at].getAttribute("data-id");
        record.step += 1;
      } else if (at + 1 < practiceVerses.length) {
        record.verse = practiceVerses[at + 1].getAttribute("data-id");
        record.step = 0;
      } else {
        record.verse = PRACTICE_DONE;
        record.step = 0;
      }
    } else if (kind === "section") {
      record.pass = record.pass >= 3 ? 1 : record.pass + 1;
    } else {
      return;
    }
    keepPractice();
    applyPractice();
    if (kind === "verse") {
      showPracticeVerse();
      var done = document.getElementById("done-go");
      if (record.verse === PRACTICE_DONE && done && typeof done.focus === "function") {
        done.focus();
      } else if (practiceLine) {
        var next = practiceLine.querySelector("button");
        if (next && typeof next.focus === "function") next.focus();
      }
    } else if (paged() && pairs.length) {
      // A new reading of the aliyah starts at its first verse.
      showPage(0, true);
    } else if (typeof window.scrollTo === "function") {
      window.scrollTo(0, 0);
    }
  }

  function choosePractice(kind) {
    if (!practising) return;
    prefs.practice = kind === "verse" || kind === "section" ? kind : "";
    save();
    applyPractice();
    if (prefs.practice === "verse") showPracticeVerse();
  }

  practiceKeys.forEach(function (key) {
    key.addEventListener("click", function () {
      choosePractice(key.getAttribute("data-practice") || "");
    });
  });
  if (practiceNext) practiceNext.addEventListener("click", advancePractice);
  // Starting anywhere: in the verse walk, a verse's number is where the walk goes.
  practiceVerses.forEach(function (pair) {
    var number = pair.querySelector(".verse-number");
    if (!number) return;
    number.addEventListener("click", function () {
      if (practiceKind() !== "verse") return;
      var record = practiceRecord();
      record.verse = pair.getAttribute("data-id");
      record.step = 0;
      keepPractice();
      applyPractice();
    });
  });
  // A practice in progress is laid out as this file arrives, which is after the page has
  // been laid out once in Read: `applyPractice` lays it out again, in place, keeping the
  // reader where they were, as the faces arriving do.
  if (practising) applyPractice();

  // What the test hook says about the practice (`TargumReader.practice`).
  function practiceSays(kind) {
    if (kind !== undefined) choosePractice(kind);
    var record = practiceRecord();
    return {
      kind: practiceKind(),
      offered: practising,
      pass: record.pass,
      verse: record.verse,
      step: record.step,
      practised: practiceVerses
        .filter(function (pair) {
          return pair.classList.contains("practised");
        })
        .map(function (pair) {
          return pair.getAttribute("data-id");
        }),
      onkelos: practiceLine
        ? (practiceLine.querySelector(".practice-targum") || {}).textContent || ""
        : "",
      hebrewOnly: body.classList.contains("practice-hebrew"),
      showing: R.showing,
      foot: practiceStep && !practiceStep.hidden ? practiceSaid.textContent : "",
    };
  }

  /* --- keyboard help ------------------------------------------------------- */

  // Eight single keys did things and nothing on the page said so, including the arrows,
  // which stop scrolling the moment this file loads. The card and its press are found in
  // `reader.js`, because the band counts the card among its residents.
  function showKeys(open) {
    if (!keysCard) return;
    // Pressed from ⋯ (#421): the menu has done its job, and the card takes its place.
    if (open && more && more.classList.contains("open")) showMore(false);
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

  /* The bar's four panels (targum-internal#421): Aa, print, the recording choice and ⋯.
     One at a time. Under its press on a wide window; from the foot on a phone, where each
     is an overlay of the band like the card — drawn over the page, laying nothing out
     (§12, 2026-09-14). Focus goes to the first control inside as one opens, and back to
     the press that opened it as it closes from the keyboard; Escape closes it, and so
     does a press anywhere outside it. `aria-expanded` on every press that names it. */
  // ⋯ itself is found in `reader.js`, which counts it among the band's overlays.
  var moreButtons = Array.prototype.slice.call(document.querySelectorAll("[data-more]"));
  // `pops`, the bar's panels by name, is gathered with the band's bookkeeping above.
  var popPresses = Array.prototype.slice.call(document.querySelectorAll("[data-pop]"));
  //: Which panel is out, by name ("more" for ⋯), and the press that opened it.
  var popOpen = null;
  var popFrom = null;

  function pressOf(name) {
    if (name === "more") return document.querySelector(".bar-tools [data-more]");
    // The speed has two presses, the bar's and the one under the picture, and only one
    // of them is on the screen at a time: that one.
    var presses = document.querySelectorAll('[data-pop="' + name + '"]');
    for (var i = 0; i < presses.length; i++) {
      if (presses[i].getClientRects().length) return presses[i];
    }
    return presses[0] || null;
  }

  // The panel under its own press, on a wide window: its far edge at the press's. One
  // that is not in the bar's row — the video's speed, under the picture (#422) — is
  // placed against the window instead, under its press and lined up with its start.
  function placePop(panel, press) {
    if (panel.hasAttribute("data-near")) {
      if (!roomy.matches || !press) return;
      var at = press.getBoundingClientRect();
      panel.style.setProperty("--near-top", Math.round(at.bottom + 6) + "px");
      panel.style.setProperty("--near-left", Math.round(Math.max(12, at.left - 8)) + "px");
      return;
    }
    if (!roomy.matches || !press || !bar) {
      panel.style.removeProperty("inset-inline-end");
      return;
    }
    var edge = bar.getBoundingClientRect().right - press.getBoundingClientRect().right;
    panel.style.setProperty("inset-inline-end", Math.max(12, Math.round(edge - 6)) + "px");
  }

  function firstControl(panel) {
    var all = panel.querySelectorAll("button:not([disabled]), a[href], select, [tabindex='0']");
    for (var i = 0; i < all.length; i++) {
      // Not the sheet's own ×, which is the last thing a reader opening Aa came for.
      if (all[i].hasAttribute("data-pop-close") || all[i].closest(".more-head")) continue;
      if (all[i].getClientRects().length) return all[i];
    }
    return null;
  }

  function popped(name, open) {
    body.classList.toggle("pop-open", !!open);
    if (open) {
      popOpen = name;
      if (typeof CustomEvent === "function") {
        document.dispatchEvent(new CustomEvent("targum:pop", { detail: name }));
      }
    } else if (popOpen === name) {
      popOpen = null;
      document.dispatchEvent(new CustomEvent("targum:pop", { detail: "" }));
    }
  }

  function showMore(open, focusIn) {
    if (!more) return;
    var was = more.classList.contains("open");
    if (open) closePops();
    if (open) occupy("more");
    if (open) {
      popFrom = pressOf("more");
      placePop(more, popFrom);
    }
    more.classList.toggle("open", !!open);
    moreButtons.forEach(function (button) {
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    if (open !== was) popped("more", !!open);
    if (open && focusIn) {
      var first = firstControl(more);
      if (first) first.focus({ preventScroll: true });
    }
    if (!open) vacate("more");
    if (seatFoot()) relayout();
  }

  function showPop(name, open, focusIn) {
    var panel = pops[name];
    if (!panel) return;
    var was = panel.classList.contains("open");
    if (open) {
      closePops(name);
      if (more && more.classList.contains("open")) showMore(false);
      occupy(name);
      popFrom = pressOf(name);
      placePop(panel, popFrom);
    }
    panel.classList.toggle("open", !!open);
    popPresses.forEach(function (press) {
      if (press.getAttribute("data-pop") !== name) return;
      press.setAttribute("aria-expanded", open ? "true" : "false");
    });
    if (open !== was) popped(name, !!open);
    if (open) {
      if (name === "aa") paintSize();
      if (focusIn) {
        var first = firstControl(panel);
        if (first) first.focus({ preventScroll: true });
      }
    } else {
      vacate(name);
    }
  }

  // Every panel but one shut, ⋯ aside, which has its own door.
  function closePops(except) {
    Object.keys(pops).forEach(function (name) {
      if (name !== except && pops[name].classList.contains("open")) showPop(name, false);
    });
  }

  // Put away whatever is out, and hand focus back to its press when the keyboard did it.
  function closeAnyPop(refocus) {
    var name = popOpen;
    if (!name) return false;
    var back = popFrom;
    if (name === "more") showMore(false);
    else showPop(name, false);
    if (refocus && back && back.getClientRects().length) back.focus({ preventScroll: true });
    return true;
  }

  popPresses.forEach(function (press) {
    press.addEventListener("click", function () {
      var name = press.getAttribute("data-pop");
      var panel = pops[name];
      if (!panel) return;
      // `detail` is 0 for a press from the keyboard, which is when focus goes inside.
      showPop(name, !panel.classList.contains("open"), fromKeys());
    });
  });
  Array.prototype.slice.call(document.querySelectorAll("[data-pop-close]")).forEach(function (shut) {
    shut.addEventListener("click", function () {
      var name = shut.getAttribute("data-pop-close");
      showPop(name, false);
      var press = pressOf(name);
      if (press && press.getClientRects().length) press.focus({ preventScroll: true });
    });
  });

  // ⋯ pressed, from the reader's click handler.
  function pressMore() {
    var opening = !(more && more.classList.contains("open"));
    var from = popFrom;
    showMore(opening, opening && fromKeys());
    // Shut from the keyboard, by the panel's own × or the press again: focus goes
    // back to the ⋯ rather than to a control that has just gone.
    if (!opening && fromKeys() && from && from.getClientRects().length) from.focus({ preventScroll: true });
  }

  // The keys pressed, from the reader's click handler: the bar's press or the card's ×.
  function pressKeys(button) {
    showKeys(keysCard ? keysCard.hidden : false);
    // Closed from the × on the card itself: the button just pressed is gone with
    // the card, so focus goes back to the one in the bar that opened it.
    if (keysCard && keysCard.hidden && keysCard.contains(button) && keysButton) {
      // Behind ⋯ since #421, where the press is out of sight: then the ⋯ itself.
      var keysBack = keysButton.getClientRects().length ? keysButton : pressOf("more");
      if (keysBack) keysBack.focus();
    }
  }

  // Whether the last press came from the keyboard, read off the click that is being
  // handled: a pointer's click carries the count of presses, a key's carries none.
  var lastClickDetail = 1;
  document.addEventListener(
    "click",
    function (event) {
      lastClickDetail = event.detail;
    },
    true
  );
  function fromKeys() {
    return lastClickDetail === 0;
  }

  // A row of ⋯ that takes the reader somewhere else — full screen, the talk, the word
  // list, the picture, the original — has done the menu's job, and the menu goes.
  if (more) {
    more.addEventListener("click", function (event) {
      var at = event.target;
      if (!at || !at.closest) return;
      if (!at.closest('[data-fullscreen], #talk-open, [data-toggle="list"], .home, [data-video]')) return;
      setTimeout(function () {
        showMore(false);
      }, 0);
    });
  }

  // A press anywhere outside the panel that is out puts it away — the same as a tap on
  // the page has always put ⋯ away. Not a press on its own press, which toggles it.
  document.addEventListener("click", function (event) {
    if (!popOpen || popOpen === "more") return;
    var panel = pops[popOpen];
    var at = event.target;
    if (!panel || !at || !at.closest) return;
    if (panel.contains(at)) return;
    if (at.closest('[data-pop="' + popOpen + '"]')) return;
    showPop(popOpen, false);
  });

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
      fullscreenButton.setAttribute(
        "aria-label",
        on ? t("reader.screen.leave-full", "Leave full screen") : t("reader.screen.full", "Full screen")
      );
    }
    say(on ? t("reader.screen.full-said", "Full screen.") : t("reader.screen.out-said", "Out of full screen."));
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

  /* Where the sheet is drawn at this instant, animation and all. Read off the computed
     transform rather than off the inline style, because while `rise` is running the
     inline style is not what anybody can see: the animation is a higher cascade origin
     than an inline declaration, and it wins. */
  function drawnAt(element) {
    var shown = getComputedStyle(element).transform;
    if (!shown || shown === "none") return 0;
    var inside = shown.slice(shown.indexOf("(") + 1, -1).split(",");
    // `matrix(a, b, c, d, tx, ty)`, or `matrix3d` with sixteen where ty is the
    // fourteenth. Anything else is a shape this does not need to understand.
    var down = Number(inside.length === 16 ? inside[13] : inside[5]);
    return isFinite(down) ? down : 0;
  }

  function dismissible(element, close) {
    if (!element) return;
    var startY = null;
    /* Where the sheet already was when the finger landed. Nought for a sheet standing
       still, and part way down for one still on its way up — a sheet can be caught. */
    var base = 0;
    var moved = 0;
    var pulled = 0;
    element.addEventListener(
      "touchstart",
      function (event) {
        startY = null;
        base = 0;
        moved = 0;
        pulled = 0;
        if (roomy.matches || event.touches.length !== 1) return;
        var at = event.target;
        if (at && /^(INPUT|TEXTAREA|SELECT)$/.test(at.tagName || "")) return;
        if (scrolledInside(at, element)) return;
        startY = event.touches[0].clientY;
        /* Take the sheet off its animation and pin it where the finger found it.
           `rise` outranks the inline transform this drag writes, so a sheet grabbed on
           its way up ignored the finger for the whole 220ms and then jumped to catch up
           — measured at 31.7px, which is a third of a thumb. Cancelled, the inline
           transform is what is drawn, and the sheet is the finger's from the first
           frame. Catching a rising sheet and throwing it back down is what every sheet
           on a phone does. */
        base = drawnAt(element);
        if (element.getAnimations) {
          element.getAnimations().forEach(function (running) {
            try {
              running.cancel();
            } catch (e) {}
          });
        }
        element.classList.add("pulling");
        if (base) element.style.transform = "translateY(" + base + "px)";
      },
      { passive: true }
    );
    element.addEventListener(
      "touchmove",
      function (event) {
        if (startY === null) return;
        moved = event.touches[0].clientY - startY;
        pulled = Math.max(0, base + moved);
        element.style.transform = pulled ? "translateY(" + pulled + "px)" : "";
      },
      { passive: true }
    );
    function letGoOf() {
      if (startY === null) return;
      /* How far the finger drew, not how far down the sheet ended up. A sheet caught
         low on its way up is a sheet the reader wants: they reached for it. Letting go
         of it should settle it open, and it did not when this asked where the sheet
         was rather than what the hand did. */
      var far = moved > PULLED;
      startY = null;
      base = 0;
      moved = 0;
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
        // Shut first, then the transform: cleared first, the sheet is back at the foot
        // of the window for however long the closing takes, which is a flash of a thing
        // the reader has just thrown away.
        close();
        element.style.transform = "";
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

  /* --- keyboard ------------------------------------------------------------ */

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
    if (!R.standing || event.target === R.standing) return;
    if (card && card.contains && card.contains(event.target)) return;
    if (bar && bar.contains(event.target)) return;
    leaveQueue();
    hideCard();
  });

  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    // Escape shuts a panel of the bar even from the choice inside it (#421).
    if (event.key === "Escape" && /^(SELECT)$/.test(event.target.tagName) && closeAnyPop(true)) {
      return;
    }
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
        say(t("reader.mode.parallel", "Parallel."));
        return;
      case "o":
        prefs.mode = "source";
        applyMode();
        settle();
        save();
        say(t("reader.mode.source-only", "Source only."));
        return;
      // `l` rather than `i`: `i` is ignore, on a word, and it cannot also be a mode.
      // The translation goes under each line, which is where the letter comes from.
      case "l":
        prefs.mode = "inter";
        applyMode();
        settle();
        save();
        say(t("reader.mode.interlinear", "Interlinear."));
        return;
      // The card is asked for, never offered. Walking the page fires no windows; this is
      // the second action that opens one. Open already, the same key asks the question
      // the card is offering, and once there is nothing left to ask it puts the card
      // away.
      case "Enter":
        if (!R.standing) return;
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
        showTimings(!R.readout || R.readout.hidden);
        return;
      case "m":
        prefs.marking = !prefs.marking;
        applyMarking();
        save();
        say(
          prefs.marking
            ? t("reader.mode.marking", "Highlighting the words you haven't learned.")
            : t("reader.mode.not-marking", "Not highlighting.")
        );
        return;
      case "b":
        prefs.paged = !prefs.paged;
        applyPaged();
        save();
        say(prefs.paged ? t("reader.mode.pages", "Pages.") : t("reader.mode.scroll", "One long scroll."));
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
      case "r":
        if (!toggleGoverned()) return;
        break;
      case "w":
        if (!toggleOrder()) return;
        break;
      case "y":
        if (!toggleVav()) return;
        break;
      case "e":
        if (!toggleSuffix()) return;
        break;
      case "c":
        if (!nextCase()) return;
        break;
      case "a":
        toggleTaamim();
        return;
      // Beside or Theatre (targum-internal#422), on a text whose picture is up and
      // nowhere else. Handed back where there is none, so the key falls through to
      // whatever the page would otherwise do with it rather than doing nothing loudly.
      case "v": {
        var pictures = window.TargumVideo;
        if (!pictures || !pictures.turn || !pictures.turn()) return;
        break;
      }
      case "?":
        showKeys(keysCard ? keysCard.hidden : false);
        return;
      case "Escape": {
        // One layer a press. Closing the keys and then dropping out of the queue in the
        // same keystroke costs a reader their place for looking a shortcut up. A panel
        // of the bar first, with focus back on the press that opened it (#421).
        if (closeAnyPop(true)) return;
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
        if (card && !card.hidden && !R.fading) {
          hideCard();
          if (R.standing && R.standing.focus) R.standing.focus({ preventScroll: true });
          return;
        }
        // A case on show is a layer over the text too.
        if (body.hasAttribute("data-case")) {
          showCase("");
          return;
        }
        // Then the panel, which covers the translation you are grading against. It is a
        // thing on top of the text, and Escape takes those off before it takes your
        // place away.
        if (listBox && !listBox.hidden) {
          showList(false);
          if (R.standing && R.standing.focus) R.standing.focus({ preventScroll: true });
          return;
        }
        // Then out of the queue, back onto the sentence the word was in, so the arrows
        // still know where they are.
        var back = R.standing && R.standing.closest ? R.standing.closest(".pair") : null;
        leaveQueue();
        if (back && back.focus) back.focus();
        return;
      }
      default:
        return;
    }
    event.preventDefault();
  });

  /* --- keeping a phrase ----------------------------------------------------
   *
   * Dragging over words, and the chip that answers it. The chip itself is found in
   * `reader.js`, which counts it among the band's overlays, and so is everything that
   * places a card beside its word, which the word's own card uses too.
   */
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

  // Named for what it places. It was `place`, which is also what the word queue calls
  // the position it is standing on — and `var place = null` and `function place` in one
  // scope are one binding, not two: the function is hoisted, the assignment runs over it,
  // and every later call throws. Which is what killed dragging a phrase outright, since
  // this is the only thing that takes the chip out of `hidden`.
  function placeChip(rect) {
    occupy("chip");
    seatNear(chip, rect);
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
        var meaning = R.glosses[token[4]];
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
      cite.appendChild(document.createTextNode(t("reader.pick.to-keep", "to keep: ")));
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
    var list = R.picks[picked.segmentId];
    var pick = existing > -1 && list ? list[existing] : null;

    function ensure() {
      if (pick) return pick;
      list = R.picks[picked.segmentId] || (R.picks[picked.segmentId] = []);
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

    function note(text) {
      var item = ensure();
      writeMeaning(phraseTerm(item), { note: text });
      stamp(item);
      remember();
      redraw();
    }

    return {
      element: TargumVocab.editor({
        status: pick ? pick.status : undefined,
        note: pick ? noteOn(phraseTerm(pick)) : "",
        // The stage's name under the control, on every card (§12, 2026-10-09).
        legend: true,
        placeholder: t("reader.card.own-meaning", "Your own meaning"),
        onStatus: apply,
        onNote: note,
      }),
      // The field without the scale, on a phrase not kept yet (2026-09-15: "I want to be
      // able to write my own meanings for phrases", and the field only came after Keep).
      // Writing a meaning is as deliberate as pressing Keep, so it keeps the phrase; the
      // scale still waits, because one stray press on it is not.
      field: function (onSaved) {
        return TargumVocab.editor({
          levels: false,
          note: "",
          placeholder: t("reader.card.own-meaning", "Your own meaning"),
          onNote: note,
          onSaved: onSaved,
        });
      },
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
    R.pickLevel = null;
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

  // A phone never sends that mouseup for a selection: a long press selects natively and
  // the handles are dragged by the browser, so the card never came and the phrase could
  // not be kept (2026-09-15). The selection is watched instead, once it has settled,
  // and only after a touch — with a mouse the handler above already has it, and a
  // selection changing under a drag would draw the card at every word crossed. It only
  // ever draws: the field on the card moves the selection too, and must not close it.
  var pickedByTouch = false;
  var pickSettling = null;
  document.addEventListener(
    "pointerdown",
    function (event) {
      pickedByTouch = event.pointerType === "touch" || event.pointerType === "pen";
    },
    true
  );
  document.addEventListener("selectionchange", function () {
    if (!chip || !pickedByTouch) return;
    if (pickSettling) window.clearTimeout(pickSettling);
    pickSettling = window.setTimeout(function () {
      pickSettling = null;
      var picked = currentSelection();
      if (!picked || !picked.text) return;
      var same =
        picking &&
        picking.segmentId === picked.segmentId &&
        picking.start === picked.start &&
        picking.end === picked.end;
      if (!same) showPick(picked);
    }, 400);
  });

  // The kept phrase this selection overlaps, by its index in the sentence's list, or -1.
  function keptOver(picked) {
    var found = -1;
    (R.picks[picked.segmentId] || []).forEach(function (item, index) {
      if (item.start < picked.end && item.end > picked.start) found = index;
    });
    return found;
  }

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
        reading: noteOf(lemma) || R.glosses[index] || "",
        note: lemma && lemma !== surface ? t("reader.card.from", "from ") + lemma : "",
        hear: hearButton(picked.segmentId, token[0], token[1], t("reader.card.hear-word", "Hear this word")),
        editor: statusRow(index, surface, band),
      });
      placeChip(picked.rect);
      R.pickLevel = function (status) {
        if (already(index, status)) return;
        if (setStatus(index, surface, band, status) === LIST_FULL) return;
        redraw();
        showPick(picked);
      };
      return;
    }

    // Dragging over a phrase you already kept offers to drop it again. Tapping cannot:
    // a tap means "what does this mean", and a phrase usually covers several words.
    var existing = keptOver(picked);

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
        ? t("reader.pick.whole-sentence", "the whole sentence")
        : held
          ? ""
          : asking
            ? reading
              ? t("reader.pick.looking-word-by-word", "word by word — looking…")
              : t("reader.card.looking", "looking…")
            : reading
              ? t("reader.pick.in-parallel", "word by word — the line's translation has the whole sentence")
              : "",
      hear: hearButton(picked.segmentId, picked.start, picked.end, t("reader.pick.hear-phrase", "Hear this phrase")),
      kind: held ? held.kind : "",
      cite: held ? held.citation : "",
      editor:
        existing > -1
          ? editing.element
          : editing.field(function () {
              showPick(picked);
            }),
      action: existing > -1 ? t("reader.pick.remove", "Remove") : t("reader.pick.keep", "Keep"),
      onclick: function () {
        var list = R.picks[picked.segmentId] || (R.picks[picked.segmentId] = []);
        // A meaning typed into the field has kept the phrase already, under a card still
        // saying Keep. Pressing it then is keeping what is kept: the card comes back with
        // the scale, rather than a second copy going on the list.
        if (existing === -1 && keptOver(picked) > -1) {
          showPick(picked);
          return;
        }
        if (existing > -1) {
          if (window.TargumSync) window.TargumSync.forgetPhrase(list[existing].id);
          list.splice(existing, 1);
          if (!list.length) delete R.picks[picked.segmentId];
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
          (R.picks[picked.segmentId] || []).forEach(function (item) {
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
    R.pickLevel = function (status) {
      editing.apply(status);
      showPick(picked);
    };
  }

  // What `reader.js` passes on to (`passOn`).
  return {
    advancePractice: advancePractice,
    ankiText: ankiText,
    choosePractice: choosePractice,
    currentSelection: currentSelection,
    exportAnki: exportAnki,
    exportCsv: exportCsv,
    hideChip: hideChip,
    offerLenses: offerLenses,
    placeChip: placeChip,
    practiceKind: practiceKind,
    practiceSays: practiceSays,
    pressKeys: pressKeys,
    pressMore: pressMore,
    showKeys: showKeys,
    showMore: showMore,
    showPop: showPop,
  };
};

/* Where the reader has already run, it left word to be handed this on arrival. Where it
   runs later (it waits on the store), it finds `targumReaderRest` and runs it itself.
   Once, either way. */
if (window.targumReaderRestWanted) {
  var targumRestJoin = window.targumReaderRestWanted;
  window.targumReaderRestWanted = null;
  targumRestJoin(window.targumReaderRest);
}
