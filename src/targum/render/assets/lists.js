/* The two lists of what you are learning: words, and phrases.
 *
 * Both lived on the progress page, next to the charts, which put half of learning on the
 * page you go to for numbers. They belong on Learn, where everything you are working on
 * is. Their own file rather than more of learn.js: this is a working surface with a
 * filter, a search, paging and an editor in it, and learn.js is about a shelf.
 *
 * Reads the same stores the reader writes and writes back to them the same way, so a
 * definition corrected here is corrected in the reader on the next sync.
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

  var charts = window.TargumCharts;
  var lang = window.TargumLang;
  var el = charts.el;

  /* A meaning is written in one language, and the page it is shown on is written in
   * another. Without this, a Russian definition sat inside a page marked `lang="en"`:
   * read out in the wrong voice, hyphenated by the wrong rules, and — for a right-to-left
   * meaning — punctuated at the wrong end of the line. The reader's own words too: a note
   * belongs to the pair it was written under, the same as the meaning beside it.
   */
  function inTarget(node, code) {
    if (code) {
      node.setAttribute("lang", code);
      node.setAttribute("dir", DIRECTION[code] || "ltr");
    }
    return node;
  }

  // Right-to-left targets, of the languages targum translates into. Small enough to say
  // outright, and it is a fact about scripts rather than a setting.
  var DIRECTION = { he: "rtl", ar: "rtl", yi: "rtl", arc: "rtl" };
  var shortDate = charts.shortDate;
  var STATUS = charts.STATUS;
  var EARLIEST = charts.EARLIEST;
  var KNOWN = charts.KNOWN;

  //: How many rows are drawn before the More button. A vocabulary of four thousand words
  //: is a real thing, and four thousand rows is a page nobody can scroll.
  var PAGE = 200;

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
  }

  function save(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {}
    // Signed in, this reaches the account a moment later; signed out it is a no-op.
    if (window.TargumSync) window.TargumSync.touched();
  }

  /* --- state ---------------------------------------------------------------- */

  var code = null;
  var entry = { words: [], phrases: [] };
  var shown = PAGE;
  //: How many rows each list may draw here, if the page asked for a ceiling. Learn does;
  //: the pages that are only a list do not, and page through with More instead.
  var limits = {};

  //: Called after a word's status changes, so the page above can redraw what depends on
  //: it — the known count on Learn is the same number this list edits.
  var onChanged = null;

  var search = null;
  var filter = null;
  var rowsBody = null;
  var moreButton = null;
  var wordsEmpty = null;

  function at(id) {
    return document.getElementById(id);
  }

  /** The way to the rest of a list, when this page is only showing the top of it. */
  function seeAll(id, total) {
    var link = at(id);
    if (!link) return;
    link.hidden = !total;
    if (total) link.textContent = t("shelf.see-all", "See all {n} →", { n: total });
  }

  function named(names, which) {
    return (names || {})[which] || (which || "").toUpperCase();
  }

  /* --- writing back --------------------------------------------------------- */

  function updateWord(word, changes) {
    var name = "targum:vocab:" + code;
    var store = read(name, "{}");
    var item = store[word.lemma];
    if (!item) return;
    // A word carried up to known from a level below it was learned here, wherever it was
    // carried up. Asked before the change lands, because the answer is in the level it is
    // leaving — and the same rule lives in the reader, which is the other way up.
    if (
      changes.status === KNOWN &&
      item.status >= 1 &&
      item.status <= 3
    ) {
      item.learned = 1;
    }
    Object.keys(changes).forEach(function (key) {
      item[key] = changes[key];
    });
    item.seen = Date.now();
    save(name, store);
    Object.keys(changes).forEach(function (key) {
      word[key] = changes[key];
    });
  }

  /* Your own words for a word or a phrase, filed under the pair they were written in.
   *
   * The word record used to carry the note, and this page went on writing it there after
   * the reader moved it: into a slot nothing read back, that sync never sent, and that
   * the next pull wrote over — the cell patched itself and the note was gone by morning.
   * The same store the reader writes, the same shape, so a note made here is the note
   * the reader shows.
   */
  function noteMeaning(source, into, term, text) {
    if (!into || !term) return;
    var name = "targum:meanings:" + source + ":" + into;
    var store = read(name, "{}");
    var was = store[term] || {};
    var record = {
      meaning: was.meaning || "",
      note: text || "",
      at: was.at || Date.now(),
      seen: Date.now(),
    };
    if (!record.meaning && !record.note) delete store[term];
    else store[term] = record;
    save(name, store);
  }

  function updatePhrase(phrase, changes) {
    var store = read(phrase.store, "{}");
    var pick = (store[phrase.segmentId] || [])[phrase.index];
    if (!pick) return;
    Object.keys(changes).forEach(function (key) {
      pick[key] = changes[key];
    });
    // The same stamp the reader writes, and for the same reason: it is what tells the
    // account which browser's version of this phrase is the newer one.
    pick.seen = Date.now();
    save(phrase.store, store);
    Object.keys(changes).forEach(function (key) {
      phrase[key] = changes[key];
    });
  }

  /* --- what the server knows about the list ------------------------------------
   *
   * Your Words is one table and a practice card (design.md §12, "Your Words is one table
   * and a practice card", 2026-10-09; boards WordsDesk, WordsPhone and Words{Fr,Ru,Arc}).
   * Three things on it are not in this browser: in how many texts each word was met, a
   * line each word still being learned was met in, and what a row says beside a word's
   * meaning in some languages. `/account/words` answers all three, off builds and lists
   * already on the machine — nothing fetched, nothing spent — and the page hands the
   * answer in here. Signed out there is no answer, and the table is drawn without them.
   */
  var facts = { loaded: false, met: {}, often: 2, practise: [], notes: {} };

  function metIn(word) {
    return facts.met[word.lemma] || 0;
  }

  /* --- the practice card ---------------------------------------------------------
   *
   * "One word at a time, in a line you've read" (board WordsDesk). The words still being
   * learned that the reader met most, each in a sentence from a section they finished,
   * with the word marked, what it means, the line's translation and the five stages. It
   * replaces the fold that stood over the table, which listed the same words a second
   * time (What to work on, targum-internal#103), and keeps its rule: pull and never
   * push. Nothing is due, nothing is counted against the reader, nothing is sent; the
   * card is a view of rows that already exist, and "2 of 10" is where they are in it.
   *
   * The words are settled when the answer arrives and do not move under the hand: a word
   * marked known stays on the card, its stage said under the control, until Next.
   */
  var practising = { at: 0, shown: false };

  function wordFor(lemma) {
    for (var n = 0; n < entry.words.length; n++) {
      if (entry.words[n].lemma === lemma) return entry.words[n];
    }
    return null;
  }

  function practiseItems() {
    return (facts.practise || []).filter(function (item) {
      return !!wordFor(item.lemma);
    });
  }

  function renderPractise() {
    var host = at("practise");
    if (!host) return;
    var items = practiseItems();
    host.hidden = !items.length;
    if (!items.length) return;
    if (practising.at >= items.length) practising.at = 0;
    var item = items[practising.at];
    var word = wordFor(item.lemma);
    var language = item.language || code;

    var where = at("practise-at");
    if (where) {
      where.textContent = t("lists.practise.at", "{n} of {total}", {
        n: practising.at + 1,
        total: items.length,
      });
    }
    var body = at("practise-body");
    if (!body) return;
    body.textContent = "";
    body.classList.toggle("is-shown", practising.shown);

    var well = el("div", "practise-well");
    // Where the line is from: the text's picture, its title, and its part.
    var from = el("p", "practise-from");
    if (window.TargumCovers) {
      from.appendChild(
        window.TargumCovers.picture(
          { name: item.name, title: item.title, language: language },
          { className: "thumb practise-thumb", keyed: keyed }
        )
      );
    }
    var title = el("bdi", "practise-title", item.title || "");
    title.setAttribute("dir", "auto");
    var said = el("span", "practise-place");
    said.appendChild(document.createTextNode(t("lists.practise.from", "From") + " "));
    said.appendChild(title);
    if (item.chapter) {
      said.appendChild(
        document.createTextNode(" · " + t("lists.practise.chapter", "chapter {n}", { n: item.chapter }))
      );
    }
    from.appendChild(said);
    well.appendChild(from);

    // The line, with the word marked where it stands.
    var line = el("p", "practise-line");
    line.setAttribute("lang", language);
    line.setAttribute("dir", DIRECTION[language] || "ltr");
    var text = String(item.line || "");
    var start = Math.max(0, Math.min(text.length, item.start || 0));
    var end = Math.max(start, Math.min(text.length, item.end || 0));
    line.appendChild(document.createTextNode(text.slice(0, start)));
    line.appendChild(el("mark", "practise-word", text.slice(start, end)));
    line.appendChild(document.createTextNode(text.slice(end)));
    well.appendChild(line);

    // On a phone the meaning waits for a press (board WordsPhone): the line is read
    // first, which is the point of meeting a word in one.
    var ask = el("div", "practise-ask");
    ask.appendChild(el("p", "practise-question", t("lists.practise.question", "What does it mean here?")));
    var reveal = el("button", "btn practise-reveal", t("lists.practise.show", "Show the meaning"));
    reveal.type = "button";
    reveal.addEventListener("click", function () {
      practising.shown = true;
      renderPractise();
    });
    ask.appendChild(reveal);
    well.appendChild(ask);

    var meaning = el("div", "practise-meaning");
    var head = el("p", "practise-head");
    var term = el("bdi", "term", item.word || word.term);
    term.setAttribute("lang", language);
    head.appendChild(term);
    var sense = word.note || word.meaning;
    if (sense) head.appendChild(inTarget(el("span", "practise-sense", sense), word.into));
    meaning.appendChild(head);
    var note = noteLine(item);
    if (note) meaning.appendChild(note);
    if (item.translation) {
      meaning.appendChild(inTarget(el("p", "practise-translation", item.translation), word.into));
    }
    well.appendChild(meaning);
    body.appendChild(well);

    // The five stages, with the stage's name under them (design.md §12, "The five stages
    // are one control, on every card"), written into the one ledger as the table's are.
    var stage = el("div", "practise-stage");
    stage.appendChild(
      window.TargumVocab.editor({
        status: word.status,
        legend: true,
        onStatus: function (value) {
          if (value === null || value === word.status) return;
          updateWord(word, { status: value });
          renderWords();
          renderPractise();
          if (onChanged) onChanged();
        },
      })
    );
    body.appendChild(stage);

    var next = el("button", "practise-next", t("lists.practise.next", "Next word →"));
    next.type = "button";
    next.hidden = practising.at >= items.length - 1;
    next.addEventListener("click", function () {
      practising.at += 1;
      practising.shown = false;
      renderPractise();
    });
    body.appendChild(next);

    // The next three, each a press away.
    var coming = items.slice(practising.at + 1, practising.at + 4);
    if (coming.length) {
      var up = el("div", "practise-coming");
      up.appendChild(el("p", "practise-coming-head", t("lists.practise.coming", "Coming up")));
      var list = el("p", "practise-coming-words");
      coming.forEach(function (one, n) {
        var go = el("button", "practise-go", one.word || one.lemma);
        go.type = "button";
        go.setAttribute("lang", one.language || code);
        go.addEventListener("click", function () {
          practising.at += n + 1;
          practising.shown = false;
          renderPractise();
        });
        list.appendChild(go);
      });
      up.appendChild(list);
      body.appendChild(up);
    }
  }

  function keyed(path) {
    var key = window.TARGUM_KEY || "";
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  /* What a row or the card says beside a word's meaning, by language (boards WordsFr,
     WordsRu): a French word's false friend, a Russian word's case. The card says the
     case it came in on its own line ("Here: genitive"); a row says the case it mostly
     comes in. Nothing where the server had nothing. */
  function caseName(code) {
    var names = {
      Nom: t("lists.case.nominative", "nominative"),
      Gen: t("lists.case.genitive", "genitive"),
      Dat: t("lists.case.dative", "dative"),
      Acc: t("lists.case.accusative", "accusative"),
      Ins: t("lists.case.instrumental", "instrumental"),
      Loc: t("lists.case.prepositional", "prepositional"),
    };
    return Object.prototype.hasOwnProperty.call(names, code) ? names[code] : "";
  }

  function noteLine(item) {
    if (item && item.case && caseName(item.case)) {
      return el("p", "word-note", t("lists.note.here", "Here: {case}", { case: caseName(item.case) }));
    }
    return null;
  }

  function rowNotes(word, cell) {
    var note = facts.notes[word.lemma];
    if (!note) return;
    if (note.friend) {
      var friend = el("span", "word-note friend");
      friend.appendChild(el("span", "tag friend-tag", t("lists.note.false-friend", "False friend")));
      friend.appendChild(
        document.createTextNode(" " + t("lists.note.not", "not “{word}”", { word: note.friend.looks }))
      );
      cell.appendChild(friend);
    }
    if (note.case && caseName(note.case)) {
      var said = el("span", "word-note");
      said.appendChild(
        document.createTextNode(
          t("lists.note.often-in", "Often in the {case}:", { case: caseName(note.case) }) + " "
        )
      );
      var form = el("bdi", "", note.form || "");
      form.setAttribute("lang", code);
      said.appendChild(form);
      cell.appendChild(said);
    }
  }

  /* A corrected line the reader has not said they know yet carries the one answer it
     had in the fold (targum-internal#290): "I know this", said to the account, since
     that is where the slip lives. It leaves the queue at once, keeps its place in the
     record, and gets its press back if the account could not be told. */
  function knowSlip(id) {
    var key = window.TARGUM_KEY || "";
    var head = { "Content-Type": "application/json" };
    if (key) head["X-Targum-Key"] = key;
    if (typeof fetch !== "function") return Promise.resolve(false);
    return fetch("/slips/" + encodeURIComponent(String(id)) + (key ? "?k=" + encodeURIComponent(key) : ""), {
        method: "POST",
        headers: head,
        body: JSON.stringify({ known: true }),
      })
      .then(function (response) {
        return response.ok;
      })
      .catch(function () {
        return false;
      });
  }

  function slipAnswer(slip) {
    var knew = el("button", "work-known", t("lists.work.known", "I know this"));
    knew.type = "button";
    knew.addEventListener("click", function () {
      var was = rewrote.slice();
      rewrote = rewrote.filter(function (other) {
        return other.id !== slip.id;
      });
      renderRecord();
      knowSlip(slip.id).then(function (ok) {
        if (ok) return;
        rewrote = was;
        renderRecord();
      });
    });
    return knew;
  }

  /* Lines that came back changed (targum-internal#290).
   *
   * Their line above the recast, with the words that changed marked. In the fold they
   * are rows of the Phrases tab; on the phrases list they are the record, every one of
   * them, newest first, with no control on a row.
   *
   * "anki srs is kinda dumb in the sense it doesnt really know what you get wrong beyond
   * what you tell it." This is what it did not know.
   */
  var rewrote = [];
  var corrected = [];

  function slipSaid(slip) {
    var said = el("span", "rewrote-said");
    /* The whole group takes the text's own direction, so the three lines stack against
       the same edge. Without it the reason — English, left to right — sat at the far
       left of a wide row while the Hebrew it is about sat at the right, and a sentence
       about a sentence has to be next to it. The English still reads the way English
       reads; only where it begins moves. */
    said.setAttribute("dir", DIRECTION[slip.language || code] || "ltr");

    var mine = el("bdi", "rewrote-wrote", slip.wrote || "");
    mine.setAttribute("lang", slip.language || code);
    said.appendChild(mine);

    // The recast, with the words the reader did not write marked. Marked rather than
    // coloured alone: a colour is not a difference to somebody who cannot see it.
    var back = el("bdi", "rewrote-recast");
    back.setAttribute("lang", slip.language || code);
    var changed = {};
    (slip.changed || []).forEach(function (word) {
      changed[word] = true;
    });
    String(slip.recast || "")
      .split(" ")
      .forEach(function (word, index) {
        if (index) back.appendChild(document.createTextNode(" "));
        if (changed[word]) {
          var mark = el("mark", "rewrote-changed", word);
          back.appendChild(mark);
          return;
        }
        back.appendChild(document.createTextNode(word));
      });
    said.appendChild(back);

    /* The model's own one sentence, where it gave one. Never more than the one.
       A `bdi` with its own direction: the reason is English with Hebrew words in it,
       and inside a right-to-left block the punctuation at its edges migrates — "Past
       tense: הלכתי, not הלך." came out with the colon on the wrong side of the
       sentence. Isolated, it reads the way it was written, and only where it begins
       follows the block. */
    if (slip.why) {
      var reason = el("bdi", "rewrote-why", slip.why);
      reason.setAttribute("dir", "auto");
      said.appendChild(reason);
    }
    return said;
  }

  /* The record on the phrases list: every line in this language, newest first, the ones
     still to go over with their answer on them. */
  function renderRecord() {
    var heading = at("rewrote-heading");
    var host = at("rewrote-rows");
    if (!host || !heading) return;
    var mine = corrected.filter(function (slip) {
      return (slip.language || code) === code;
    });
    heading.hidden = mine.length === 0;
    host.textContent = "";
    var queued = {};
    rewrote.forEach(function (slip) {
      queued[slip.id] = true;
    });
    mine.forEach(function (slip) {
      var item = el("li", "work-row rewrote-row");
      item.setAttribute("data-slip", String(slip.id));
      opens(item, slipCard(slip));
      item.appendChild(slipSaid(slip));
      if (queued[slip.id]) item.appendChild(slipAnswer(slip));
      host.appendChild(item);
    });
  }

  /* --- a row's card (2026-09-18) ---------------------------------------------
   *
   * "When I click on a word or phrase on any list, I want to be able to open up its
   * card, and interact with it." One card for every list on these pages — the fold on
   * Learn and on Your Words, the word table, Your Phrases and the lines the
   * conversation corrected — so a word opened from a list is the same thing as a word
   * tapped in a text.
   *
   * The reader's card, as far as a list can honestly draw it. It wears the reader's
   * classes (`reader.css` is on every one of these pages) and its one control, the
   * level scale and the note from `TargumVocab.editor`, so the questions are asked the
   * same way in both places. What it cannot draw is what only a text has: the grammar,
   * the root, the sentence it sat in. A ledger row does not carry those, and a card that
   * invented them would be a card that lies.
   *
   * It replaces the editor row that opened under a table row: two ways of opening a
   * word, one of them on some lists and not on others, was the inconsistency this
   * removes.
   */
  var card = null;
  //: The row the card was opened from, so focus goes back to it on the way out.
  var cardFrom = null;

  function ensureCard() {
    if (card) return card;
    card = at("list-card");
    if (!card) {
      card = el("div");
      card.id = "list-card";
      document.body.appendChild(card);
    }
    card.className = "gloss-card list-card";
    card.setAttribute("role", "dialog");
    card.hidden = true;
    // Escape and a press anywhere else put it away, as they do in the reader.
    document.addEventListener("keydown", function (event) {
      if (event && event.key === "Escape" && !card.hidden) closeCard();
    });
    document.addEventListener("click", function (event) {
      if (card.hidden) return;
      var target = event && event.target;
      if (!target) return;
      if (card.contains && card.contains(target)) return;
      // The press that opened it reaches the document too, after the row has had it.
      if (cardFrom && cardFrom.contains && cardFrom.contains(target)) return;
      closeCard();
    });
    return card;
  }

  function closeCard() {
    if (!card || card.hidden) return;
    card.hidden = true;
    card.textContent = "";
    var back = cardFrom;
    cardFrom = null;
    if (back && back.focus && back.isConnected !== false) back.focus();
  }

  /* Beside the row on a desk; a sheet at the foot on a phone, where a panel beside a
     row has nowhere to stand. 40rem is Learn's own line between the two. */
  function place(row) {
    var narrow = window.matchMedia && window.matchMedia("(max-width: 40rem)").matches;
    card.classList.toggle("sheet", !!narrow);
    if (narrow || !row.getBoundingClientRect) {
      card.style.top = "";
      card.style.left = "";
      return;
    }
    var box = row.getBoundingClientRect();
    var gutter = 16;
    var width = card.offsetWidth || 0;
    var left = Math.max(
      gutter,
      Math.min(box.left, (window.innerWidth || 0) - width - gutter)
    );
    card.style.top = box.bottom + (window.scrollY || 0) + 6 + "px";
    card.style.left = left + (window.scrollX || 0) + "px";
  }

  function openCard(row, fill) {
    ensureCard();
    card.textContent = "";
    cardFrom = row;
    var shut = el("button", "list-card-close", "×");
    shut.type = "button";
    shut.setAttribute("aria-label", t("lists.card.close", "Close"));
    shut.addEventListener("click", function (event) {
      if (event && event.stopPropagation) event.stopPropagation();
      closeCard();
    });
    card.appendChild(shut);
    fill(card);
    card.hidden = false;
    place(row);
    shut.focus();
  }

  /** A row that opens a card: by a press anywhere on it but its own controls, or by
   *  Enter or Space when it is the stop the keyboard is on. */
  function opens(row, fill) {
    row.setAttribute("tabindex", "0");
    row.setAttribute("aria-haspopup", "dialog");
    row.classList.add("opens");
    row.addEventListener("click", function (event) {
      var target = event && event.target;
      if (target && target.closest && target.closest("button, input, a")) return;
      openCard(row, fill);
    });
    row.addEventListener("keydown", function (event) {
      if (!event || (event.key !== "Enter" && event.key !== " ")) return;
      if (event.target && event.target !== row) return;
      if (event.preventDefault) event.preventDefault();
      openCard(row, fill);
    });
  }

  /* The lines of a card. Each says one thing and carries its own copy, as the reader's
     do: "copy the word" means three different strings to three readers. */
  function headline(text, language) {
    var line = el("span", "copy-line");
    var head = el("bdi", "lemma", text);
    head.setAttribute("lang", language);
    line.appendChild(head);
    line.appendChild(window.TargumVocab.copyButton(text, {}));
    return line;
  }

  function meaningLine(own, bought, into) {
    return paintMeaning(inTarget(el("span"), into), own, bought);
  }

  /* Drawn into the node it is given, so a note typed on the card can repaint the line
     above it without the line being swapped out. */
  function paintMeaning(line, own, bought) {
    var sense = own || bought || "";
    line.textContent = "";
    line.className = "meaning" + (own ? " mine" : "");
    if (sense) {
      line.appendChild(document.createTextNode(sense));
      line.classList.add("copy-line");
      line.appendChild(window.TargumVocab.copyButton(sense, {}));
    } else {
      line.textContent = t("lists.card.no-meaning", "No meaning yet. Write your own below.");
    }
    return line;
  }

  /* After a level is said the card has done its job and goes, as the reader's does, and
     every list on the page is drawn again from the one store it was said into. */
  function said() {
    closeCard();
    renderWords();
    renderPractise();
    renderPhrases();
    if (onChanged) onChanged();
  }

  function wordCard(word) {
    return function (host) {
      host.appendChild(headline(word.term, code));
      if (word.lemma && word.lemma !== word.term) {
        var form = el("span", "form copy-line");
        form.appendChild(document.createTextNode(t("reader.card.from", "from ")));
        var lemma = el("bdi", "", word.lemma);
        lemma.setAttribute("lang", code);
        form.appendChild(lemma);
        form.appendChild(window.TargumVocab.copyButton(word.lemma, {}));
        host.appendChild(form);
      }
      var meaning = meaningLine(word.note, word.meaning, word.into);
      host.appendChild(meaning);
      host.appendChild(
        window.TargumVocab.editor({
          status: word.status,
          note: word.note,
          legend: true,
          placeholder: t("vocab.own-meaning", "Your own meaning"),
          onStatus: function (value) {
            updateWord(word, { status: value === null ? word.status : value });
            said();
          },
          onNote: function (text) {
            if (text === word.note) return;
            noteMeaning(code, word.into, word.lemma, text);
            word.note = text;
            // Patched rather than redrawn: the press that ended the typing — usually a
            // level — has not landed yet, and a redraw would take it out from under it.
            paintMeaning(meaning, text, word.meaning);
            renderWords();
          },
        })
      );
    };
  }

  function phraseCard(phrase) {
    return function (host) {
      host.appendChild(headline(phrase.term, code));
      var meaning = meaningLine(phrase.note, phrase.meaning, phrase.into);
      host.appendChild(meaning);
      host.appendChild(
        window.TargumVocab.editor({
          status: phrase.status,
          note: phrase.note,
          legend: true,
          placeholder: t("vocab.own-meaning", "Your own meaning"),
          onStatus: function (value) {
            updatePhrase(phrase, { status: value === null ? phrase.status : value });
            said();
          },
          onNote: function (text) {
            if (text === phrase.note) return;
            noteMeaning(code, phrase.into, phrase.id && "phrase:" + phrase.id, text);
            phrase.note = text;
            paintMeaning(meaning, text, phrase.meaning);
            renderPhrases();
          },
        })
      );
      // Phrases stay with their text, and the card says which.
      if (phrase.title) {
        host.appendChild(el("span", "form", t("lists.card.kept-from", "Kept from {title}", { title: phrase.title })));
      }
    };
  }

  /* A corrected line: what it should have been, first and largest, since that is the
     thing to learn; what the reader wrote under it, and the model's reason. No scale —
     a sentence has no level — and the row's own answers stay on the row. */
  function slipCard(slip) {
    return function (host) {
      var language = slip.language || code;
      host.appendChild(headline(slip.recast || "", language));
      var wrote = el("span", "form");
      wrote.appendChild(document.createTextNode(t("lists.card.you-wrote", "You wrote ")));
      var mine = el("bdi", "", slip.wrote || "");
      mine.setAttribute("lang", language);
      wrote.appendChild(mine);
      host.appendChild(wrote);
      if (slip.why) {
        var reason = el("bdi", "form", slip.why);
        reason.setAttribute("dir", "auto");
        host.appendChild(reason);
      }
    };
  }

  /* --- the word table ------------------------------------------------------- */

  /* One table (board WordsDesk): the word, what it means, in how many texts it was met,
     its stage by name, and the five stages to change it. Most met first where the
     server said how often, the newest kept first where it did not. */
  function visibleWords() {
    var needle = (search.value || "").trim().toLowerCase();
    var want = filter.value;
    var often = filter.often && facts.loaded;
    var rows = entry.words
      .filter(function (word) {
        if (want === "learning") {
          if (!(word.status >= 1 && word.status <= 3)) return false;
        } else if (want !== "all" && String(word.status) !== want) {
          return false;
        }
        if (often && metIn(word) < facts.often) return false;
        if (!needle) return true;
        return (
          word.term.toLowerCase().indexOf(needle) > -1 ||
          word.lemma.toLowerCase().indexOf(needle) > -1 ||
          word.meaning.toLowerCase().indexOf(needle) > -1
        );
      })
      .slice()
      .reverse();
    if (facts.loaded) {
      // Stable, so words met equally often keep the newest-kept order they came in.
      rows = rows
        .map(function (word, n) {
          return { word: word, n: n };
        })
        .sort(function (a, b) {
          return metIn(b.word) - metIn(a.word) || a.n - b.n;
        })
        .map(function (pair) {
          return pair.word;
        });
    }
    return rows;
  }

  function stageName(status) {
    if (status === KNOWN) return t("vocab.step.known.title", "Known");
    if (status === 0) return t("lists.stage.ignored", "Ignored");
    return t("vocab.step." + status, ["", "Just met", "Getting there", "Nearly there"][status] || "");
  }

  function renderWords() {
    if (!rowsBody) return;
    var rows = visibleWords();
    var cap = limits.words || 0;
    var drawing = cap ? rows.slice(0, cap) : rows.slice(0, shown);
    rowsBody.textContent = "";
    var table = at("word-table");
    if (table) {
      // The column only where something was met: an empty column is a question nobody
      // can answer yet.
      table.classList.toggle(
        "has-met",
        facts.loaded &&
          entry.words.some(function (word) {
            return metIn(word) > 0;
          })
      );
      table.classList.toggle("is-rtl", DIRECTION[code] === "rtl");
    }
    drawing.forEach(function (word) {
      var tr = el("tr");
      tr.setAttribute("data-word", word.lemma);

      var term = el("td", "word-cell");
      var bdi = el("bdi", "term", word.term);
      bdi.setAttribute("lang", code);
      term.appendChild(bdi);
      // In the word's own cell rather than a column of its own: a copy is about the
      // word, and the table has its columns to hold on a phone.
      term.appendChild(window.TargumVocab.copyButton(word.term, {}));
      // The dictionary form under the word it was met as, where the two differ: a column
      // of its own was mostly empty (board WordsDesk).
      if (word.lemma !== word.term) {
        var form = el("bdi", "term form", word.lemma);
        form.setAttribute("lang", code);
        term.appendChild(form);
      }
      // How a French word is said, under it (board WordsFr), where the server could say.
      var note = facts.notes[word.lemma];
      if (note && note.said) term.appendChild(el("span", "said", "/" + note.said + "/"));
      tr.appendChild(term);

      var meaning = inTarget(el("td", "meaning" + (word.note ? " mine" : "")), word.into);
      meaning.appendChild(el("span", "sense", word.note || word.meaning));
      if (word.note && word.meaning) meaning.title = "targum: " + word.meaning;
      rowNotes(word, meaning);
      tr.appendChild(meaning);

      // In how many texts it was met, inside sections the reader finished.
      var met = metIn(word);
      tr.appendChild(
        el("td", "met", met ? tn("lists.met.texts", met, "{n} text", "{n} texts") : "")
      );

      // Its stage by name, on the ramp's colour (board WordsDesk's Status column).
      var status = el("td", "status");
      status.appendChild(el("i", "dot dot-" + word.status));
      status.appendChild(el("span", "status-name", stageName(word.status)));
      if (met) {
        status.appendChild(
          el("span", "status-met", " · " + tn("lists.met.in", met, "met in {n} text", "met in {n} texts"))
        );
      }
      tr.appendChild(status);

      // The five stages on the row itself (vocab.js `steps()`): a press here moves the
      // word without opening its card.
      var stage = el("td", "stage");
      stage.appendChild(
        window.TargumVocab.editor({
          status: word.status,
          onStatus: function (value) {
            updateWord(word, { status: value === null ? word.status : value });
            said();
          },
        })
      );
      tr.appendChild(stage);

      // The row opens the word's card, as every list on these pages does (2026-09-18).
      opens(tr, wordCard(word));
      rowsBody.appendChild(tr);
    });

    var order = at("words-order");
    if (order) {
      order.textContent = !rows.length
        ? ""
        : facts.loaded
          ? t("lists.order.met", "Most met first")
          : t("lists.order.newest", "Newest first");
    }
    wordsEmpty.hidden = rows.length > 0;
    wordsEmpty.textContent = rows.length
      ? ""
      : search.value.trim()
        ? t("lists.no-match", "Nothing here matches that. Try another word or filter.")
        : entry.words.length
          ? t("lists.no-stage", "Nothing at that stage yet.")
          // Nothing at all, which is every new account: say what fills the list and
          // where, rather than naming a stage the reader has not met.
          : t("lists.no-words", "Nothing yet. Tap a word as you go and tell us how well you know it.");
    // Capped, there is no paging: the rest of the list is a page away, not a press away.
    moreButton.hidden = cap ? true : rows.length <= shown;
    moreButton.textContent = t("lists.show-more", "Show {n} more", { n: Math.min(PAGE, rows.length - shown) });
    seeAll("words-more", cap && rows.length > cap ? rows.length : 0);
  }

  /* --- phrases -------------------------------------------------------------- */

  function renderPhrases() {
    var host = at("phrase-list");
    var empty = at("phrases-empty");
    if (!host) return;
    host.textContent = "";
    var all = entry.phrases;
    var cap = limits.phrases || 0;
    var phrases = cap ? all.slice(0, cap) : all;
    at("phrases-title").textContent =
      t("yours.page.your-phrases", "Your Phrases") + (all.length ? " (" + all.length + ")" : "");
    seeAll("phrases-more", cap && all.length > cap ? all.length : 0);
    empty.hidden = all.length > 0;
    if (!phrases.length) return;

    // Grouped by the text they came from, which is the only place they mean anything.
    var byText = {};
    var order = [];
    // The same words kept twice in one text are one phrase to read (2026-09-14): a phrase
    // saved in three places listed "האנטישמיות שבימינו" three times over. The first stands
    // for the rest.
    var seenTerm = {};
    phrases.forEach(function (phrase) {
      if (!byText[phrase.title]) {
        byText[phrase.title] = [];
        order.push(phrase.title);
      }
      var said = phrase.title + "\u0000" + String(phrase.term || "").trim();
      if (seenTerm[said]) return;
      seenTerm[said] = true;
      byText[phrase.title].push(phrase);
    });

    order.forEach(function (title) {
      var group = el("div", "text-group");
      var heading = el("h3", null, title);
      heading.setAttribute("dir", "auto");
      if (/[\u0590-\u05FF]/.test(title)) heading.setAttribute("lang", "he");
      group.appendChild(heading);
      var list = el("ol");
      byText[title].forEach(function (phrase) {
        var item = el("li");
        var bdi = el("bdi", "term", phrase.term);
        bdi.setAttribute("lang", code);
        item.appendChild(bdi);
        item.appendChild(window.TargumVocab.copyButton(phrase.term, {}));
        var reading = phrase.note || phrase.meaning;
        var line = null;
        if (reading) {
          line = inTarget(
            el("span", "reading" + (phrase.note ? " mine" : ""), reading),
            phrase.into
          );
          if (phrase.note && phrase.meaning) line.title = "targum: " + phrase.meaning;
          item.appendChild(line);
        }
        opens(item, phraseCard(phrase));
        list.appendChild(item);
      });
      group.appendChild(list);
      host.appendChild(group);
    });
  }

  /* --- exports ---------------------------------------------------------------
   *
   * An export is the account's, not the browser's: it needs somewhere to have come
   * from, and a file assembled out of whatever happens to be in this browser is a
   * subset with no sign that anything is missing. Signed out the two buttons are not
   * there at all — an offer that cannot be met is worse than no offer.
   */

  /* A spreadsheet runs a cell that opens with =, +, - or @ as a formula, so an export
     is a way to hand somebody a file that does something when they open it. The leading
     apostrophe is what marks the rest as text; it is visible, which is the price of the
     file being inert. Everything else is left exactly as the reader wrote it. */
  function csvCell(value) {
    var text = value === undefined || value === null ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function saveFile(name, text, mime) {
    var blob = new Blob([text], { type: mime });
    var url = URL.createObjectURL(blob);
    var link = el("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  function download(name, header, rows) {
    // A byte order mark, so a spreadsheet opens Hebrew and Russian as UTF-8. Spelled
    // as an escape rather than typed: the character itself is invisible in the source,
    // and anything that strips it takes the Hebrew with it.
    var csv =
      "\ufeff" +
      [header]
        .concat(rows)
        .map(function (row) {
          return row.map(csvCell).join(",");
        })
        .join("\n");
    saveFile(name, csv, "text/csv;charset=utf-8");
  }

  /* --- anki --------------------------------------------------------------------
   *
   * A deck of the words on screen, in the tab-separated shape Anki imports natively
   * (targum-internal#103). Not an .apkg: that is a zipped SQLite database, it would be
   * the only binary this page has ever written, and it buys nothing a reader can see —
   * Anki reads this file with the deck already named and the notetype already chosen.
   *
   * Why offer it at all, when the card it sits on exists because "anki requires
   * bookkeeping and discipline that I lack". Because the objection is to *running* an
   * SRS, not to owning the rows. A reader who keeps their vocabulary here should be able
   * to walk out with it in the format the rest of the world uses, and a list you cannot
   * leave with is a list you are being held by. The fold above is the argument for
   * staying; this is the door, and the door being open is part of the argument.
   *
   * The header lines are Anki 2.1.55 and later. An older Anki shows them as a first card
   * to delete, which is a worse first run than it could be and better than a file it
   * refuses.
   */

  /* Tabs and newlines are the format, so a cell carrying either would silently become
     two cells or two notes. They are collapsed to spaces rather than escaped: a reader's
     own note is prose, and prose that lost a line break is still readable where a note
     split across two cards is not. A leading quote is the one thing Anki reads as
     structure, so a cell that starts with one is quoted properly.

     No `csvCell` guard here, deliberately: Anki runs no formulas, and an apostrophe
     glued to the front of a Hebrew word would sit on the face of the card for good. */
  function ankiCell(value) {
    var text = value === undefined || value === null ? "" : String(value);
    text = text.replace(/[\t\r\n]+/g, " ");
    return text.charAt(0) === '"' ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function exportAnki() {
    var deck = "targum " + named(languages, code);
    /* Three fields, and the third declared as tags so Anki's own Basic notetype takes
       the file without the reader configuring anything. `html:false` because every one
       of these strings is the reader's, and a meaning they wrote containing < should
       read as < on the card. */
    var lines = [
      "#separator:tab",
      "#html:false",
      "#notetype:Basic",
      "#deck:" + deck,
      "#tags column:3",
    ];
    visibleWords().forEach(function (word) {
      /* The back is the meaning, then what the reader wrote themselves, then the
         dictionary form when it is not already the face of the card. Their own note
         comes before the dictionary form because it is the part they will recognise. */
      var back = [word.meaning, word.note, word.lemma !== word.term ? word.lemma : ""]
        .filter(function (part) {
          return !!part;
        })
        .join(" \u00b7 ");
      /* Hierarchical, so the whole import is one collapsible branch in Anki's sidebar
         and a reader who exports twice can tell the halves apart. The level is the
         number, not its name: the names are translated and a tag that changes with the
         interface language would split one deck across five tags. */
      var tags = ["targum", "targum::" + code, "targum::level-" + word.status];
      lines.push([word.term, back, tags.join(" ")].map(ankiCell).join("\t"));
    });
    // No byte order mark: Anki reads UTF-8, and a BOM would land inside the first
    // field of the first note rather than being eaten as encoding.
    saveFile(deck + " words.txt", lines.join("\n") + "\n", "text/plain;charset=utf-8");
  }

  var languages = {};

  function exportWords() {
    // What the filter is showing, so what you exported is what you were looking at.
    download(
      "targum " + named(languages, code) + " words.csv",
      // The columns in the reader's language, like the page (targum-internal#287).
      [
        t("lists.csv.word", "word"),
        t("lists.csv.dictionary-form", "dictionary form"),
        t("lists.csv.how-common", "how common"),
        t("lists.csv.how-well", "how well"),
        t("lists.csv.meaning", "meaning"),
        t("lists.csv.your-meaning", "your meaning"),
        t("lists.csv.kept", "kept"),
      ],
      visibleWords().map(function (word) {
        return [
          word.term,
          word.lemma,
          word.band || "",
          (STATUS[word.status] || {}).name || "",
          word.meaning,
          word.note || "",
          word.at > EARLIEST ? new Date(word.at).toISOString().slice(0, 10) : "",
        ];
      })
    );
  }

  function exportPhrases() {
    download(
      "targum " + named(languages, code) + " phrases.csv",
      [
        t("lists.csv.phrase", "phrase"),
        t("lists.csv.reading", "reading"),
        t("lists.csv.your-reading", "your reading"),
        t("lists.csv.how-well", "how well"),
        t("lists.csv.from", "from"),
      ],
      entry.phrases.map(function (phrase) {
        return [
          phrase.term,
          phrase.meaning,
          phrase.note || "",
          (STATUS[phrase.status] || {}).name || "",
          phrase.title,
        ];
      })
    );
  }

  /** Show the export buttons, or do not. Called again whenever sync resolves. */
  function offerExports(signedIn) {
    ["export-words", "export-anki", "export-phrases"].forEach(function (id) {
      var button = at(id);
      if (button) button.hidden = !signedIn;
    });
  }

  /* --- what the page calls --------------------------------------------------- */

  /* Which stage the word table shows, as tabs (board WordsDesk; design.md §12, "Your
     Words is one table and a practice card", 2026-10-09). To work on is steps 1 to 3
     together and is where the page opens; each step, known, and everything follow, and
     then Met often, which keeps to the words met in two texts or more and is drawn only
     once the server has said how often. The step names are the control's own (`vocab.js`
     `steps()`), so a tab and a segment never call one stage two things. The choice is
     this browser's to remember. */
  var STAGE_CHOSEN = "targum:words-stage";

  function stages() {
    return [
      ["learning", t("lists.stage.work", "To work on")],
      ["1", t("vocab.step.1", "Just met")],
      ["2", t("vocab.step.2", "Getting there")],
      ["3", t("vocab.step.3", "Nearly there")],
      [String(KNOWN), t("vocab.step.known.title", "Known")],
      ["all", t("lists.stage.all", "All")],
    ];
  }

  var drawStageTabs = function () {};

  function mountStages(host) {
    var chosen = { value: "learning", often: false };
    if (!host) return chosen;
    try {
      var kept = localStorage.getItem(STAGE_CHOSEN);
      stages().forEach(function (pair) {
        if (pair[0] === kept) chosen.value = kept;
      });
    } catch (e) {}
    function tab(value, label, on, press) {
      var button = el("button", "tab", label);
      button.type = "button";
      button.setAttribute("data-stage", value);
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.addEventListener("click", press);
      host.appendChild(button);
      return button;
    }
    drawStageTabs = function () {
      host.textContent = "";
      stages().forEach(function (pair) {
        tab(pair[0], pair[1], chosen.value === pair[0], function () {
          chosen.value = pair[0];
          try {
            localStorage.setItem(STAGE_CHOSEN, pair[0]);
          } catch (e) {}
          shown = PAGE;
          drawStageTabs();
          renderWords();
        });
      });
      // Met often is a cut across the stages rather than a stage of its own, so it is
      // pressed on and off and stands apart from them.
      var met = entry.words.some(function (word) {
        return metIn(word) >= facts.often;
      });
      if (facts.loaded && met) {
        tab("often", t("lists.stage.often", "Met often"), chosen.often, function () {
          chosen.often = !chosen.often;
          shown = PAGE;
          drawStageTabs();
          renderWords();
        }).classList.add("tab-often");
      } else {
        chosen.often = false;
      }
    };
    drawStageTabs();
    return chosen;
  }

  /* What the list adds up to in this language, under the way back to Your Progress, and
     the count on each tab. Aramaic says its list is its own: its words are kept apart from
     Hebrew's even where the spelling is shared (2026-09-15). */
  function drawHead() {
    var summary = at("words-summary");
    var sums = charts.totals(entry);
    function grouped(n) {
      return { n: String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",") };
    }
    if (summary) {
      var parts = [
        code === "arc"
          ? tn(
              "lists.head.on-list-arc",
              sums.saved,
              "{n} on your Aramaic list, kept apart from your Hebrew one",
              "{n} on your Aramaic list, kept apart from your Hebrew one",
              grouped(sums.saved)
            )
          : tn("lists.head.on-list", sums.saved, "{n} on your list", "{n} on your list", grouped(sums.saved)),
        tn("lists.head.known", sums.known, "{n} known", "{n} known", grouped(sums.known)),
      ];
      if (sums.learned) {
        parts.push(
          tn("lists.head.learned", sums.learned, "{n} learned on targum", "{n} learned on targum", grouped(sums.learned))
        );
      }
      summary.textContent = parts.join(" · ");
    }
    if (at("count-words")) at("count-words").textContent = String(sums.saved);
    if (at("count-phrases")) at("count-phrases").textContent = String(sums.phrases);
  }

  function mount(options) {
    languages = (options && options.languages) || {};
    onChanged = (options && options.onChanged) || null;

    // A page may carry one list rather than both — the whole point of the two pages this
    // also runs — so everything here is wired only if it is there.
    search = at("search");
    filter = mountStages(at("stage-chips"));
    rowsBody = at("word-rows");
    moreButton = at("more");
    wordsEmpty = at("words-empty");

    if (moreButton) {
      moreButton.onclick = function () {
        shown += PAGE;
        renderWords();
      };
    }
    if (search) {
      search.oninput = function () {
        shown = PAGE;
        renderWords();
      };
    }
    if (at("export-words")) at("export-words").onclick = exportWords;
    if (at("export-anki")) at("export-anki").onclick = exportAnki;
    if (at("export-phrases")) at("export-phrases").onclick = exportPhrases;
    offerExports(false);
  }

  /** Draw both lists for one language. */
  /* Which language the meanings on this page are written in.
   *
   * Only ever drawn for somebody who has meanings in more than one — a reader who has
   * only ever read into English is not asked a question with one answer. Picking one
   * remembers it and redraws, and `TargumCharts.meaningLanguage` is what turns the
   * remembered choice back into the language the page shows.
   */
  function offerMeaningLanguages(source, chosen, onPick) {
    var host = document.getElementById("meaning-langs");
    if (!host) return;
    var have = charts.targets(source).map(function (one) {
      return one.code;
    });
    var names = window.TARGUM_LANGUAGES || {};
    lang.switcher(host, have, names, chosen, onPick, {
      label: t("yours.page.translations-in", "Translations in"),
      // Never "experimental": that is a claim about a language you are learning, and
      // these are the languages you already have.
      tag: function () {
        return false;
      },
    });
  }

  function draw(which, store, ceilings) {
    var was = code;
    code = which;
    entry = store || { words: [], phrases: [] };
    limits = ceilings || {};
    shown = PAGE;
    /* What the server said is about one language's list, and so is where the practice
       card stands: another language starts without either until its answer comes. A
       redraw in the same language — a word marked, which calls back to the page — keeps
       both, so the card does not jump under the hand. */
    if (code !== was) {
      facts = { loaded: false, met: {}, often: 2, practise: [], notes: {} };
      practising = { at: 0, shown: false };
      // A card is about a word in one language; another language's lists close it.
      closeCard();
    }
    offerMeaningLanguages(which, meaningIn(), function (into) {
      lang.into(into);
      if (redrawing) redrawing(into);
    });
    drawHead();
    drawStageTabs();
    renderRecord();
    renderWords();
    renderPractise();
    renderPhrases();
  }

  // What the rows on the page are in, taken from the rows themselves: `collect` stamps
  // each one, so this cannot disagree with what is drawn.
  function meaningIn() {
    var rows = (entry.words || []).concat(entry.phrases || []);
    for (var n = 0; n < rows.length; n++) if (rows[n].into) return rows[n].into;
    return "";
  }

  // What to call when the reader picks another language. The page owns redrawing, since
  // only it knows where its store comes from.
  var redrawing = null;

  window.TargumLists = {
    /* The lines that came back changed, handed in by the page that fetched them
       (targum-internal#290): the queue, oldest first, without the lines already known —
       the ones in the record on Your Phrases that still carry "I know this". */
    rewrote: function (rows) {
      rewrote = rows || [];
      renderRecord();
    },
    /* What `/account/words` said about this language's list (see `facts`). An answer
       for a language no longer shown is dropped. */
    facts: function (language, answer) {
      if (language !== code || !answer || !answer.signedIn) return;
      facts = {
        loaded: true,
        met: answer.met || {},
        often: answer.often || 2,
        practise: answer.practise || [],
        notes: answer.notes || {},
      };
      drawStageTabs();
      renderWords();
      renderPractise();
    },
    /* Every line, known ones too, for the record on the phrases list. */
    record: function (rows) {
      corrected = rows || [];
      renderRecord();
    },
    mount: mount,
    draw: draw,
    // The ledger changed under this list — a page of common words marked known
    // (`claim.js`, targum-internal#245) — so the count above and the rows here redraw.
    changed: function () {
      if (onChanged) onChanged();
      else draw(code, entry, limits);
    },
    onMeaningLanguage: function (fn) {
      redrawing = fn;
    },
    offerExports: offerExports,
  };
})();
