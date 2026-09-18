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
  //: How many words the fold offers at once where the whole list is on the same page.
  //: A cap and never a target: nothing counts what is behind it, because "12 words due"
  //: is the sentence this card exists not to say. `limits.workOn` takes it lower where
  //: the fold is a guest — Learn shows five and says where the rest are (2026-09-18).
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
      .slice(0, limits.workOn || WORK_ON);
  }

  /* Phrases, the fold's second tab (2026-09-18). Two kinds of row answer the same
   * question, so they are one list: a phrase the reader kept from a text and has not
   * marked known, and a line they wrote in the conversation that came back changed.
   * Oldest first across both, for the reason the words are: the thing worth coming back
   * to is what has been sitting there longest.
   *
   * A kept phrase is on the same ladder as a word and moves on it the same way. A line
   * that came back changed has no ladder — it is a sentence the reader got wrong once —
   * so "I know this" takes it off the list on the account and "Still learning" only
   * moves it out of the sitting. The slip itself is never touched: it is the record,
   * and the record is not the queue.
   */
  function phraseKey(phrase) {
    return "phrase:" + phrase.store + ":" + phrase.segmentId + ":" + phrase.index;
  }

  function phrasesToWorkOn() {
    var rows = [];
    (entry.phrases || []).forEach(function (phrase) {
      if (passed[phraseKey(phrase)]) return;
      if (!(phrase.status >= 1 && phrase.status <= 3)) return;
      rows.push({ kind: "phrase", at: phrase.at || 0, phrase: phrase });
    });
    rewrote.forEach(function (slip) {
      if (passed["slip:" + slip.id]) return;
      // The queue from the server is every language's; the fold is one language's.
      if ((slip.language || code) !== code) return;
      rows.push({ kind: "slip", at: slip.at || 0, slip: slip });
    });
    return rows
      .sort(function (a, b) {
        return a.at - b.at;
      })
      .slice(0, limits.workOn || WORK_ON);
  }

  /* Which tab is open. In memory: a sitting's choice, and the next visit opens on
     whichever half has something in it, words first. */
  var workTab = null;

  function renderWorkOn() {
    var panel = at("work-on");
    var wordHost = at("work-rows");
    if (!panel || !wordHost) return;
    var phraseHost = at("work-phrase-rows");
    var words = workOn();
    var phrases = phraseHost ? phrasesToWorkOn() : [];
    // Nothing to work on is nothing on the page. Not an empty state and not an
    // invitation: a reader who has flagged nothing is not being told they are behind.
    panel.hidden = words.length === 0 && phrases.length === 0;

    // The open tab stays open while it has rows, and a tab that has just been worked
    // through hands over to the other rather than showing an empty list.
    if (workTab !== "phrases" || !phrases.length) workTab = words.length ? "words" : "phrases";
    if (workTab === "words" && !words.length) workTab = "phrases";

    /* The tabs only where both halves have something. A tab with nothing under it is an
       empty state with a label on it, and the fold does not have those: a reader with
       only words sees the words, as before. */
    var tabs = at("work-tabs");
    if (tabs) tabs.hidden = !(words.length && phrases.length);
    WORK_TABS.forEach(function (which) {
      var tab = at("work-tab-" + which);
      if (!tab) return;
      var on = which === workTab;
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.tabIndex = on ? 0 : -1;
    });
    wordHost.hidden = workTab !== "words";
    if (phraseHost) phraseHost.hidden = workTab !== "phrases";

    // The door and the way to the rest are about whichever half is open.
    var foot = at("work-foot");
    if (foot) foot.hidden = panel.hidden;
    var talk = at("work-talk");
    if (talk) {
      talk.textContent =
        workTab === "phrases"
          ? t("lists.work.talk-phrases", "Generate sentences with these phrases")
          : t("lists.work.talk-words", "Generate sentences with these words");
    }
    var all = at("work-all");
    if (all) {
      var path = workTab === "phrases" ? "/phrases" : "/words";
      var key = window.TARGUM_KEY || "";
      all.href = path + (key ? "?k=" + encodeURIComponent(key) : "");
      all.textContent =
        workTab === "phrases"
          ? t("learn.page.all-your-phrases", "All your phrases")
          : t("learn.page.all-your-words", "All your words");
    }

    drawWordRows(wordHost, words);
    if (phraseHost) drawPhraseRows(phraseHost, phrases);
  }

  var WORK_TABS = ["words", "phrases"];

  /** Switch the fold to one half. Arrow keys move between the tabs, as tabs do. */
  function mountWorkTabs() {
    WORK_TABS.forEach(function (which, n) {
      var tab = at("work-tab-" + which);
      if (!tab) return;
      tab.onclick = function () {
        workTab = which;
        renderWorkOn();
      };
      tab.onkeydown = function (event) {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        workTab = WORK_TABS[(n + 1) % WORK_TABS.length];
        renderWorkOn();
        at("work-tab-" + workTab).focus();
      };
    });
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
  function answers(onKnown, onStill) {
    var keys = el("span", "work-keys");
    var knew = el("button", "work-known", t("lists.work.known", "I know this"));
    knew.type = "button";
    knew.addEventListener("click", onKnown);
    var still = el("button", "work-still", t("lists.work.still", "Still learning"));
    still.type = "button";
    still.addEventListener("click", onStill);
    keys.appendChild(knew);
    keys.appendChild(still);
    return keys;
  }

  function drawWordRows(host, rows) {
    host.textContent = "";
    rows.forEach(function (word) {
      var item = el("li", "work-row");
      item.setAttribute("data-word", word.lemma || word.term);
      opens(item, wordCard(word));

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

      item.appendChild(
        answers(
          function () {
            updateWord(word, { status: KNOWN });
            renderWorkOn();
            renderWords();
            if (onChanged) onChanged();
          },
          function () {
            passed[word.lemma || word.term] = true;
            if (word.status > 1) {
              updateWord(word, { status: word.status - 1 });
              renderWords();
              if (onChanged) onChanged();
            }
            renderWorkOn();
          }
        )
      );
      host.appendChild(item);
    });
  }

  function drawPhraseRows(host, rows) {
    host.textContent = "";
    rows.forEach(function (row) {
      if (row.kind === "slip") {
        host.appendChild(slipRow(row.slip));
        return;
      }
      var phrase = row.phrase;
      var item = el("li", "work-row");
      item.setAttribute("data-phrase", phraseKey(phrase));
      opens(item, phraseCard(phrase));
      var said = el("span", "work-said");
      var term = el("bdi", "term", phrase.term);
      term.setAttribute("lang", code);
      said.appendChild(term);
      item.appendChild(said);
      var meaning = phrase.note || phrase.meaning;
      if (meaning) {
        item.appendChild(
          inTarget(el("span", "work-meaning" + (phrase.note ? " mine" : ""), meaning), phrase.into)
        );
      }
      // The same ladder as a word, written the way the reader and the list below write
      // a phrase's level: into the text's own store, so the text shows it too.
      item.appendChild(
        answers(
          function () {
            updatePhrase(phrase, { status: KNOWN });
            renderWorkOn();
            renderPhrases();
            if (onChanged) onChanged();
          },
          function () {
            passed[phraseKey(phrase)] = true;
            if (phrase.status > 1) {
              updatePhrase(phrase, { status: phrase.status - 1 });
              renderPhrases();
              if (onChanged) onChanged();
            }
            renderWorkOn();
          }
        )
      );
      host.appendChild(item);
    });
  }

  /* A line that came back changed, as a row to work on. "I know this" is said to the
     account, since that is where the slip lives; it leaves the list at once and comes
     back only if the account could not be told. */
  function slipRow(slip) {
    var item = el("li", "work-row work-slip");
    item.setAttribute("data-slip", String(slip.id));
    opens(item, slipCard(slip));
    item.appendChild(slipSaid(slip));
    item.appendChild(
      answers(
        function () {
          var was = rewrote.slice();
          rewrote = rewrote.filter(function (other) {
            return other.id !== slip.id;
          });
          renderWorkOn();
          knowSlip(slip.id).then(function (ok) {
            if (ok) return;
            rewrote = was;
            renderWorkOn();
          });
        },
        function () {
          passed["slip:" + slip.id] = true;
          renderWorkOn();
        }
      )
    );
    return item;
  }

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
   *
   * It carries whichever tab is open: the words, or the phrases.
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
  //: And how many phrases: fewer, because a phrase is several words and a corrected
  //: line is a whole sentence.
  var TAKEN_PHRASES = 3;

  function talkAbout() {
    var line;
    if (workTab === "phrases") {
      var phrases = phrasesToWorkOn()
        .slice(0, TAKEN_PHRASES)
        .map(function (row) {
          return row.kind === "slip" ? row.slip.recast : row.phrase.term;
        })
        .filter(Boolean);
      if (!phrases.length) return;
      line = t("lists.work.phrase-line", "Use these phrases in new sentences: ") + phrases.join("; ");
    } else {
      var words = workOn()
        .slice(0, TAKEN)
        .map(function (word) {
          return word.term;
        });
      if (!words.length) return;
      line = t("lists.work.line", "Use these in a sentence each: ") + words.join(", ");
    }
    try {
      localStorage.setItem(SAY, line);
    } catch (whatever) {
      // A browser refusing storage is a browser that gets a plain conversation. The
      // words come back through the ledger anyway; only the line is lost.
    }
    var key = window.TARGUM_KEY || "";
    window.location.href = "/chat" + (key ? "?k=" + encodeURIComponent(key) : "");
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

  /* The record on the phrases list: every line in this language, newest first. */
  function renderRecord() {
    var heading = at("rewrote-heading");
    var host = at("rewrote-rows");
    if (!host || !heading) return;
    var mine = corrected.filter(function (slip) {
      return (slip.language || code) === code;
    });
    heading.hidden = mine.length === 0;
    host.textContent = "";
    mine.forEach(function (slip) {
      var item = el("li", "work-row rewrote-row");
      opens(item, slipCard(slip));
      item.appendChild(slipSaid(slip));
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
    renderWorkOn();
    renderWords();
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
      // look at is not where anyone wants to correct a definition. The row opens the
      // word's card, as every list on these pages does (2026-09-18).
      opens(tr, wordCard(word));
      rowsBody.appendChild(tr);
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
    mountWorkTabs();
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
    /* A sitting ends when the page does, or when the reader changes language. It does
       not end because a word was marked: marking one calls back to the page, which
       redraws the whole list through here, and clearing the skips there took a word the
       reader had just passed over and put it back in front of them mid-sitting. Found on
       the running page. `passed` is module state, so a reload empties it by existing. */
    if (code !== was) {
      passed = {};
      // A card is about a word in one language; another language's lists close it.
      closeCard();
    }
    offerMeaningLanguages(which, meaningIn(), function (into) {
      lang.into(into);
      if (redrawing) redrawing(into);
    });
    renderWorkOn();
    renderRecord();
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
       (targum-internal#290): the queue, oldest first, without the lines already known.
       Here rather than fetched in this file, because each page asks on its own terms
       and one of them asks for more than this. */
    rewrote: function (rows) {
      rewrote = rows || [];
      renderWorkOn();
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
