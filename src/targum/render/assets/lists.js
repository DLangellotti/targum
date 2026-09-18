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

  //: How many words the fold at the top offers at once (targum-internal#103). Twenty is
  //: a sitting, not a syllabus: enough that arriving is worth it, few enough that the
  //: list is a thing somebody finishes rather than a backlog that grows while they look
  //: at it. It is a cap and never a target — nothing counts what is behind it.
  var WORK_ON = 20;

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
  // Which row is open for editing, keyed by the thing it is about. One at a time.
  var openKey = null;

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

  /* --- what to work on ------------------------------------------------------- */

  /* The fold at the top of Your Words: the words this reader flagged and never came back
   * to (targum-internal#103).
   *
   * Dmitry Z, 2026-09-16, on the one thing in an hour he called genuinely useful: "anki
   * requires bookkeeping and discipline that I lack", and "anki srs is kinda dumb in the
   * sense it doesnt really know what you get wrong beyond what you tell it". A per-session
   * answer is a commodity a chat window already gives him for free; what a chat window
   * structurally cannot do is remember him between sessions. The list that maintains
   * itself is the thing worth paying for.
   *
   * And the constraint, three minutes later in the same conversation: "if smth gonna ping
   * me or bother me like duolingo I'll fucking delete it". So it is pull and never push.
   * Nothing here is scheduled, nothing is due, nothing is counted, nothing is sent. It is
   * a view of rows that already exist, waiting when he arrives and silent when he does
   * not.
   *
   * The order is the plainest rule that is true of the data. `at` is when a word was
   * marked and there is nothing else: no record that a word was met again, no count of
   * times seen, no interval. So: still learning, oldest mark first — the ones that have
   * been sitting there longest. Any cleverer order would be a claim the ledger cannot
   * support.
   */
  /* Words the reader has said "still learning" to during this visit. In memory and
     nowhere else: it is not a snooze and not an interval, it is the difference between
     one sitting and the next. Cleared by `draw`, so coming back to the page brings them
     back — which is correct, because they are still words being learned. */
  var passed = {};

  function workOn() {
    return entry.words
      .filter(function (word) {
        if (passed[word.lemma || word.term]) return false;
        return word.status >= 1 && word.status <= 3;
      })
      .slice()
      .sort(function (a, b) {
        // Oldest mark first. A word with no stamp sorts as oldest, which is right: it was
        // marked before anything started stamping.
        return (a.at || 0) - (b.at || 0);
      })
      .slice(0, WORK_ON);
  }

  function renderWorkOn() {
    var panel = at("work-on");
    var host = at("work-rows");
    if (!panel || !host) return;
    var rows = workOn();
    // Nothing to work on is nothing on the page. Not an empty state and not an
    // invitation: a reader who has flagged no words is not being told they are behind.
    // Either half is enough to draw it: a reader with no flagged words may still have
    // lines that came back changed.
    panel.hidden = rows.length === 0 && rewrote.length === 0;
    host.textContent = "";
    // The door at the foot is about the words, so a reader whose fold holds only lines
    // that came back changed is not offered it: there would be nothing to carry.
    var foot = at("work-foot");
    if (foot) foot.hidden = rows.length === 0;
    if (!rows.length) return;

    rows.forEach(function (word) {
      var item = el("li", "work-row");
      item.setAttribute("data-word", word.lemma || word.term);

      var said = el("span", "work-said");
      var term = el("bdi", "term", word.term);
      term.setAttribute("lang", code);
      said.appendChild(term);
      // The dictionary form only where it differs, the way the table does it: repeating
      // a word under itself says the reader got something wrong.
      if (word.lemma && word.lemma !== word.term) {
        var form = el("bdi", "work-lemma", word.lemma);
        form.setAttribute("lang", code);
        said.appendChild(form);
      }
      item.appendChild(said);

      // What they kept, in the language they kept it in. Their own note wins over the
      // bought meaning, which is the rule everywhere else a meaning is shown.
      var meaning = word.note || word.meaning;
      if (meaning) {
        item.appendChild(inTarget(el("span", "work-meaning" + (word.note ? " mine" : ""), meaning), word.into));
      }

      /* The two questions, and nothing else.
       *
       * "I know this" takes it off the list through the ordinary path — the same
       * `updateWord` the table's editor calls — so the known count rises once, from one
       * store, and no second ledger exists to disagree with the first.
       *
       * "Still learning" steps it back down the ladder it is already on — nearly there
       * to getting there, getting there to just met — and moves it out of this sitting.
       * The step down is the honest opposite of the button beside it: both say what the
       * reader knows about this word, and both say it in the one place the product keeps
       * that. A press that changed nothing would have been a control with no job
       * (design.md §13), and this card frames the fold as a queue worked through.
       *
       * At "just met" there is nowhere lower, so the press only moves the word out of
       * the sitting and writes nothing. Saying "still learning" about a word marked met
       * once is agreement, and agreement is not news.
       *
       * It does not restamp `at`: that field is when a word was kept, it is what the
       * table's Kept column shows, and it is written once and preserved for life
       * (`vocab.js:161`) — so re-stamping it to reorder a queue would have quietly aged
       * every word in the product to today. The order of the fold is therefore
       * unchanged by a press, and a word stepped down today is where it was tomorrow.
       *
       * The sitting half is still in memory and nowhere else: a stored skip is an
       * interval wearing a different coat, and the whole of this card is that nothing is
       * scheduled. Come back tomorrow and the word is here again, one level lower, which
       * is true: it is still a word being learned.
       */
      var keys = el("span", "work-keys");
      var knew = el("button", "work-known", t("lists.work.known", "I know this"));
      knew.type = "button";
      knew.addEventListener("click", function () {
        updateWord(word, { status: KNOWN });
        renderWorkOn();
        renderWords();
        if (onChanged) onChanged();
      });
      var still = el("button", "work-still", t("lists.work.still", "Still learning"));
      still.type = "button";
      still.addEventListener("click", function () {
        passed[word.lemma || word.term] = true;
        if (word.status > 1) {
          updateWord(word, { status: word.status - 1 });
          renderWords();
          if (onChanged) onChanged();
        }
        renderWorkOn();
      });
      keys.appendChild(knew);
      keys.appendChild(still);
      item.appendChild(keys);
      host.appendChild(item);
    });
  }

  /* --- taking them into a conversation ---------------------------------------
   *
   * The fold's one door out (targum-internal#103). A list of words is a list of words;
   * the thing a reader stuck on six of them actually wants is to meet them in a
   * sentence, and the conversation is already the place this product does that.
   *
   * It writes the line and opens the chat with it in the box, unsent. That is the whole
   * of the mechanism, and the reason it is the whole of it: **nothing here spends.** A
   * control that started a turn would be a model's decision to bill somebody, which is
   * the one thing the rails exist to prevent. The reader reads the line, edits it or
   * does not, and presses Send with their own hand — the same press every other door in
   * the product waits for.
   *
   * The conversation needs no telling which words these are. `bring_back` already
   * carries the reader's whole ledger into every turn, and `recurring` already carries
   * what they keep getting wrong. What the line adds is *this sitting's* six, and a
   * sentence saying what the reader came for. Everything else was already there, which
   * is why the AI half of this feature is four lines of JavaScript.
   */

  /* The handoff is a stored line, not an address. A word belongs to the reader, and a
     reader's own vocabulary in a query string is their vocabulary in a server log, in
     their history, and in whatever sits between them and the site. Read once by the
     chat and deleted there, so a back button does not refill the box. */
  var SAY = "targum:say";

  //: How many words the line names. Six, because the line is a sentence a person reads
  //: before pressing Send, and twenty Hebrew words is not a sentence. The fold may hold
  //: twenty; this takes the ones nearest the top, which are the oldest marks.
  var TAKEN = 6;

  function talkAbout() {
    var words = workOn()
      .slice(0, TAKEN)
      .map(function (word) {
        return word.term;
      });
    if (!words.length) return;
    try {
      localStorage.setItem(
        SAY,
        t("lists.work.line", "Use these in a sentence each: ") + words.join(", ")
      );
    } catch (whatever) {
      // A browser refusing storage is a browser that gets a plain conversation. The
      // words come back through the ledger anyway; only the line is lost.
    }
    var key = window.TARGUM_KEY || "";
    window.location.href = "/chat" + (key ? "?k=" + encodeURIComponent(key) : "");
  }

  /* Lines that came back changed (targum-internal#290), in the same fold as the words.
   *
   * Their line above the recast, with the words that changed marked — which is the whole
   * of it. There is no control on a row: a sentence is not a word and there is nothing
   * here to mark known, and the record is the point rather than a thing to work through.
   *
   * "anki srs is kinda dumb in the sense it doesnt really know what you get wrong beyond
   * what you tell it." This is what it did not know.
   */
  var rewrote = [];

  function renderRewrote() {
    var heading = at("rewrote-heading");
    var host = at("rewrote-rows");
    if (!host || !heading) return;
    heading.hidden = rewrote.length === 0;
    host.textContent = "";
    if (!rewrote.length) return;

    rewrote.forEach(function (slip) {
      var item = el("li", "work-row rewrote-row");
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
      item.appendChild(said);
      host.appendChild(item);
    });
  }

  /* --- the word table ------------------------------------------------------- */

  function visibleWords() {
    var needle = (search.value || "").trim().toLowerCase();
    var want = filter.value;
    return entry.words
      .filter(function (word) {
        if (want === "learning") {
          if (!(word.status >= 1 && word.status <= 3)) return false;
        } else if (want !== "all" && String(word.status) !== want) {
          return false;
        }
        if (!needle) return true;
        return (
          word.term.toLowerCase().indexOf(needle) > -1 ||
          word.lemma.toLowerCase().indexOf(needle) > -1 ||
          word.meaning.toLowerCase().indexOf(needle) > -1
        );
      })
      .slice()
      .reverse();
  }

  function statusCell(status) {
    var pip = el("span", "pip");
    var dot = el("i");
    // Ignored is not a step on the ramp — a name is not a word you are a quarter of
    // the way through — so it has no slot, and asking for one threw and blanked the
    // whole table for anybody who had ever pressed `i`.
    var step = STATUS[status];
    dot.style.background = step ? "var(" + step.slot + ")" : "var(--rule)";
    pip.appendChild(dot);
    pip.appendChild(document.createTextNode(step ? step.name : status === 0 ? "ignored" : "—"));
    return pip;
  }

  function renderWords() {
    if (!rowsBody) return;
    var rows = visibleWords();
    var cap = limits.words || 0;
    var drawing = cap ? rows.slice(0, cap) : rows.slice(0, shown);
    rowsBody.textContent = "";
    drawing.forEach(function (word) {
      var tr = el("tr");

      var term = el("td");
      var bdi = el("bdi", "term", word.term);
      bdi.setAttribute("lang", code);
      term.appendChild(bdi);
      // In the word's own cell rather than a column of its own: a copy is about the
      // word, and the table already has six columns to hold on a phone.
      term.appendChild(window.TargumVocab.copyButton(word.term, {}));
      tr.appendChild(term);

      var lemma = el("td");
      if (word.lemma !== word.term) {
        var form = el("bdi", "term", word.lemma);
        form.setAttribute("lang", code);
        lemma.appendChild(form);
      }
      tr.appendChild(lemma);

      var meaning = inTarget(
        el("td", "meaning" + (word.note ? " mine" : ""), word.note || word.meaning),
        word.into
      );
      if (word.note && word.meaning) meaning.title = "targum: " + word.meaning;
      tr.appendChild(meaning);
      tr.appendChild(el("td", "band", word.band || "—"));

      var status = el("td");
      status.appendChild(statusCell(word.status));
      tr.appendChild(status);

      tr.appendChild(el("td", "when", word.at > EARLIEST ? shortDate(word.at) : "—"));

      // The same two questions the reader asks, asked here too: a list you can only
      // look at is not where anyone wants to correct a definition. Reachable by key
      // as well as pointer: the row is a stop, Enter or Space is the tap.
      tr.setAttribute("tabindex", "0");
      tr.setAttribute("aria-expanded", openKey === word.lemma ? "true" : "false");
      tr.addEventListener("click", function (event) {
        if (event.target.closest("button, input")) return;
        openKey = openKey === word.lemma ? null : word.lemma;
        renderWords();
      });
      tr.addEventListener("keydown", function (event) {
        if (event.key !== "Enter" && event.key !== " ") return;
        if (event.target !== tr) return;
        event.preventDefault();
        openKey = openKey === word.lemma ? null : word.lemma;
        renderWords();
      });
      if (openKey === word.lemma) tr.classList.add("open");
      rowsBody.appendChild(tr);

      if (openKey === word.lemma) {
        var holder = el("tr", "editor-row");
        var cell = document.createElement("td");
        cell.colSpan = 6;
        cell.appendChild(
          window.TargumVocab.editor({
            status: word.status,
            note: word.note,
            placeholder: t("vocab.own-meaning", "Your own meaning"),
            onStatus: function (value) {
              updateWord(word, { status: value === null ? word.status : value });
              renderWords();
              if (onChanged) onChanged();
            },
            onNote: function (text) {
              if (text === word.note) return;
              noteMeaning(code, word.into, word.lemma, text);
              word.note = text;
              // Patched rather than re-rendered. Committing on blur means the click
              // that caused the blur — usually a level button — has not landed yet,
              // and rebuilding the row here would take that button out from under it.
              meaning.textContent = text || word.meaning;
              meaning.className = "meaning" + (text ? " mine" : "");
            },
          })
        );
        holder.appendChild(cell);
        rowsBody.appendChild(holder);
      }
    });

    at("words-title").textContent =
      t("yours.page.your-words", "Your Words") + (rows.length ? " (" + rows.length + ")" : "");
    wordsEmpty.hidden = rows.length > 0;
    wordsEmpty.textContent = rows.length
      ? ""
      : search.value.trim()
        ? t("lists.no-match", "Nothing here matches that.")
        : entry.words.length
          ? t("lists.no-stage", "Nothing at that stage yet.")
          // Nothing at all, which is every new account: say what fills the list and
          // where, rather than naming a stage the reader has not met.
          : t("lists.no-words", "Nothing yet. Tap a word while you read and tell us how well you know it.");
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
        var key = phrase.store + ":" + phrase.segmentId + ":" + phrase.index;
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
        item.setAttribute("tabindex", "0");
        item.setAttribute("aria-expanded", openKey === key ? "true" : "false");
        item.addEventListener("click", function (event) {
          if (event.target.closest("button, input")) return;
          openKey = openKey === key ? null : key;
          renderPhrases();
        });
        item.addEventListener("keydown", function (event) {
          if (event.key !== "Enter" && event.key !== " ") return;
          if (event.target !== item) return;
          event.preventDefault();
          openKey = openKey === key ? null : key;
          renderPhrases();
        });
        if (openKey === key) {
          item.classList.add("open");
          item.appendChild(
            window.TargumVocab.editor({
              status: phrase.status,
              note: phrase.note,
              placeholder: t("vocab.own-meaning", "Your own meaning"),
              onStatus: function (value) {
                updatePhrase(phrase, { status: value === null ? phrase.status : value });
                renderPhrases();
              },
              onNote: function (text) {
                if (text === phrase.note) return;
                noteMeaning(code, phrase.into, phrase.id && "phrase:" + phrase.id, text);
                phrase.note = text;
                if (line) {
                  line.textContent = text || phrase.meaning;
                  line.className = "reading" + (text ? " mine" : "");
                }
              },
            })
          );
        }
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

  function mount(options) {
    languages = (options && options.languages) || {};
    onChanged = (options && options.onChanged) || null;

    // A page may carry one list rather than both — the whole point of the two pages this
    // also runs — so everything here is wired only if it is there.
    search = at("search");
    filter = at("status-filter");
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
    if (filter) {
      filter.onchange = function () {
        shown = PAGE;
        renderWords();
      };
    }
    if (at("export-words")) at("export-words").onclick = exportWords;
    if (at("work-talk")) at("work-talk").onclick = talkAbout;
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
    openKey = null;
    /* A sitting ends when the page does, or when the reader changes language. It does
       not end because a word was marked: marking one calls back to the page, which
       redraws the whole list through here, and clearing the skips there took a word the
       reader had just passed over and put it back in front of them mid-sitting. Found on
       the running page. `passed` is module state, so a reload empties it by existing. */
    if (code !== was) passed = {};
    offerMeaningLanguages(which, meaningIn(), function (into) {
      lang.into(into);
      if (redrawing) redrawing(into);
    });
    renderWorkOn();
    renderRewrote();
    renderWords();
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
       (targum-internal#290). Here rather than fetched in this file, because this file is
       drawn on two pages and only one of them asks. */
    rewrote: function (rows) {
      rewrote = rows || [];
      renderRewrote();
      renderWorkOn();
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
