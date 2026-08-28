/* Learn — the page you land on, and everything you are learning.
 *
 * How many words you know, then three doors — carry on, find something, bring your own —
 * then your shelf, then the words and phrases themselves. The count is one line rather
 * than a panel of numbers: the reader is a reader rather than a player, and the charts
 * that make an account of it live on Your Progress.
 *
 * Everything here is drawn from what already exists. `targum:opened` says which text you
 * had open last and already syncs; `/readers` says what is on your shelf and, since
 * today, how much of each one's vocabulary you have already marked known. Nothing new is
 * tracked to make this page possible.
 */
(function () {
  "use strict";

  var key = window.TARGUM_KEY;
  /* Hosted there is no start-up key: the session cookie identifies the reader, and a key
     riding in every URL is a bearer token in browser history, on a shared screen, and in
     a Referer. Local it stays, because there it proves the page came from the terminal
     that started the process. Both cases are this one branch. */
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }
  var charts = window.TargumCharts;
  var lists = window.TargumLists;
  var shelf = window.TargumShelf;
  var lang = window.TargumLang;
  var names = window.TARGUM_LANGUAGES || {};

  function el(tag, className, text) {
    return charts.el(tag, className, text);
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  function post(path, body) {
    return ask(path, body).then(function (answer) {
      if (answer && answer.error) throw new Error(answer.error);
      return answer;
    });
  }

  function reload() {
    location.reload();
  }

  Array.prototype.forEach.call(
    document.querySelectorAll(".site-nav a, .doors a[data-door], .see-all"),
    function (link) {
      link.href = keyed(link.getAttribute("href"));
    }
  );

  /* How much of each list this page holds. Learn is where you land, not where you study:
     what belongs here is the top of each list and the way to the rest of it. */
  var SHELF = 5;
  var WORDS = 10;
  var PHRASES = 5;

  /* --- folding a panel away --------------------------------------------------
   *
   * Three lists on one page is a long page, and which of them somebody wants open is
   * theirs to decide rather than ours to guess. Kept in this browser: it is a state of a
   * screen, not a fact about a person.
   */

  var FOLDED = "targum:folded";

  function folded() {
    try {
      return JSON.parse(localStorage.getItem(FOLDED) || "{}");
    } catch (e) {
      return {};
    }
  }

  function folds() {
    var shut = folded();
    Array.prototype.forEach.call(document.querySelectorAll(".fold"), function (press) {
      var panel = press.closest("section");
      var body = panel && panel.querySelector(".fold-body");
      if (!body) return;
      press.setAttribute("aria-controls", body.id);

      function show(open) {
        press.setAttribute("aria-expanded", open ? "true" : "false");
        body.hidden = !open;
      }

      show(!shut[body.id]);
      press.addEventListener("click", function () {
        var open = press.getAttribute("aria-expanded") !== "true";
        show(open);
        var now = folded();
        if (open) delete now[body.id];
        else now[body.id] = 1;
        try {
          localStorage.setItem(FOLDED, JSON.stringify(now));
        } catch (e) {}
      });
    });
  }

  folds();

  function named(code) {
    return names[code] || (code || "").toUpperCase();
  }

  /* --- what you have already ------------------------------------------------ */

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  var ago = shelf.ago;
  var base = shelf.base;

  /* Languages this reader has words in. Signed out with nothing kept, this is empty
     and the switcher does not appear, which is the intended resting state. */
  function kept() {
    var found = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var name = localStorage.key(i) || "";
        if (name.indexOf("targum:vocab:") === 0) {
          found.push({ language: name.slice("targum:vocab:".length) });
        }
      }
    } catch (e) {}
    return found;
  }


  /* --- what you came back for ------------------------------------------------ */

  function share(reader) {
    // `known` is absent for a targum built without word-level annotation, which is a
    // normal state rather than a fault. Saying nothing beats saying "0% known", because
    // "not measured" and "you know none of this" are very different claims about a book.
    if (typeof reader.known !== "number") return "";
    return Math.round(reader.known * 100) + "% of its words are ones you know";
  }

  function drawCarry(reader) {
    var panel = document.getElementById("carry");
    if (!reader) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    // The box is the link, so this is the only href on it.
    panel.href = keyed("/reader/" + encodeURIComponent(reader.name) + "/reader/index.html");

    var cover = document.getElementById("carry-cover");
    cover.textContent = "";
    cover.appendChild(
      window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(reader.entry || reader.name)), {
        title: reader.title,
        language: reader.language,
      })
    );

    var title = document.getElementById("carry-title");
    title.textContent = reader.title;
    title.setAttribute("lang", reader.language);

    var facts = [];
    if (reader.chapters && reader.chapters.length > 1) {
      facts.push(reader.readyChapters + " of " + reader.chapters.length + " chapters");
    } else if (reader.sections > 1) {
      facts.push(reader.sections + " parts");
    }
    facts.push(reader.opened ? "opened " + ago(reader.opened) : "not opened yet");
    document.getElementById("carry-meta").textContent = facts.join(" · ");

    var known = document.getElementById("carry-known");
    var said = share(reader);
    known.hidden = !said;
    known.textContent = said;
  }

  /* --- what to read next ------------------------------------------------------
   *
   * The catalogue rides in the page, trimmed to an id, a title and two numbers. The
   * suggestion is made here rather than on the server for the same reason the word
   * counts are: what this reader has already read is in this browser, and the server
   * has no business being told about it to answer a question this size.
   *
   * "Level" is the difficulty of the hardest thing they have built — measured as the
   * share of running words a reader has to look up, so it is a fact about the text
   * rather than a guess about the person. The suggestion is the easiest thing in the
   * catalogue that is harder than that, which is what a step up means.
   */

  var catalogue = window.TARGUM_CATALOGUE || [];

  /* What is on offer, and whether it is being taken up. Held here rather than passed to
     the listener, because the listener is attached once and the offer is redrawn every
     time the shelf is: a handler bound per draw stacks, and four presses of one card
     would start four builds. */
  var offered = null;
  var building = false;

  /* What the server says while it works, said the way a reader would. The same table the
     library keeps, because one build narrating itself differently depending on which page
     it was started from is two builds as far as anybody reading it is concerned. */
  var PLAIN = {
    "Finding each word's dictionary form…": "Reading the words…",
    "Adding vowel points…": "Adding vowel points…",
    "Building the reader…": "Setting the page…",
  };

  function say(message) {
    if (!message) return "";
    if (PLAIN[message]) return PLAIN[message];
    if (message.indexOf("Matching") === 0) return "Lining up…";
    if (message.indexOf("Looking up") === 0) return "Looking words up…";
    return "Almost there…";
  }

  /* The card narrates in the line that said why it was suggested — that line has done its
     job by the time somebody presses. Announced only while a build is running: live from
     the start would read the suggestion out on every draw. */
  function narrate(text) {
    var why = document.getElementById("suggest-why");
    if (why) why.textContent = text;
  }

  function watch(id) {
    var timer = setInterval(function () {
      ask("/job/" + id).then(function (job) {
        if (job.error) {
          clearInterval(timer);
          stopBuilding(job.error);
          return;
        }
        narrate(say(job.message) || "Almost there…");
        if (job.stage === "done") {
          clearInterval(timer);
          window.location.href = keyed("/reader/" + job.reader.split("/").map(encodeURIComponent).join("/"));
        }
      });
    }, 700);
  }

  /* Said and pressable again. The wording carries the failure on its own: §4's clay sits
     close to the accent under protanopia, and this line is read by whoever pressed. */
  function stopBuilding(message) {
    building = false;
    var card = document.getElementById("suggest");
    if (card) card.disabled = false;
    narrate(message);
  }

  /* Pressing the card. Continue Reading beside it is one press into a text; this is the
     same press for a text that has to be built first, which is the only difference
     between the two cards and not one a reader should have to think about. */
  function take() {
    if (building || !offered) return;
    building = true;
    var card = document.getElementById("suggest");
    var why = document.getElementById("suggest-why");
    if (card) card.disabled = true;
    if (why) why.setAttribute("aria-live", "polite");
    narrate("Getting ready…");
    var entry = offered;
    ask("/prepare", {
      source: entry.source,
      // The language this reader reads into, not English by assumption. They read in
      // two; a button that always bought one of them would be a button that reads their
      // mind wrong half the time. Clamped to what the account is offered, so a
      // remembered choice that no longer stands asks for English rather than a refusal.
      to: window.TargumSync ? window.TargumSync.into(lang.into()) : lang.into() || "en",
      from: entry.language,
      words: true,
      gloss: false,
      // Every published translation this text has. The reader switches between them.
      // Already a list of sources, which is the shape `/prepare` wants — the catalogue
      // this page carries is trimmed to what it uses.
      translations: entry.translations || [],
    })
      .then(function (job) {
        if (job.error) throw new Error(job.error);
        if (job.blocked) throw new Error(job.blocked);
        narrate("Lining up…");
        return ask("/build", { id: job.id }).then(function () {
          watch(job.id);
        });
      })
      .catch(function (problem) {
        stopBuilding(String(problem.message || problem));
      });
  }

  var offer = document.getElementById("suggest");
  if (offer) offer.addEventListener("click", take);

  function suggest(code, readers) {
    // Never over a build in progress: the shelf redraws for its own reasons, and this
    // would put the reason for the suggestion back over the line narrating it.
    if (building) return;
    var card = document.getElementById("suggest");
    if (!card) return;

    var built = {};
    readers.forEach(function (reader) {
      if (reader.entry) built[reader.entry] = true;
    });
    var open = catalogue
      .filter(function (entry) {
        return base(entry.language) === code && !built[entry.id] && entry.difficulty;
      })
      .sort(function (a, b) {
        return a.difficulty - b.difficulty;
      });
    if (!open.length) {
      offered = null;
      card.hidden = true;
      return;
    }

    var level = 0;
    readers.forEach(function (reader) {
      if (base(reader.language) === code && reader.difficulty > level) level = reader.difficulty;
    });

    var pick = null;
    var why = "";
    if (!level) {
      pick = open[0];
      why = "Where most people start";
    } else {
      open.forEach(function (entry) {
        if (!pick && entry.difficulty > level) pick = entry;
      });
      why = pick ? "A step up from what you have read" : "About where you are reading";
      if (!pick) pick = open[open.length - 1];
    }

    card.hidden = false;
    // What pressing the card would build. It used to be a link to the catalogue with this
    // text outlined somewhere in it, which handed back the choice that had just been made
    // for the reader — and the outline was lost altogether whenever the library had a
    // filter or a tab remembered from last time. `data-entry` is also the seam the tests
    // read the offer through, a button having no href to check.
    offered = pick;
    card.setAttribute("data-entry", pick.id);

    // The same tile the shelf and the library draw, which for most of the catalogue is a
    // cover somebody paid to have drawn and for the rest is the text's own first letter.
    var cover = document.getElementById("suggest-cover");
    cover.textContent = "";
    cover.appendChild(
      window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(pick.id)), {
        title: pick.title,
        language: pick.language,
      })
    );

    var title = document.getElementById("suggest-title");
    title.textContent = pick.title;
    title.setAttribute("lang", pick.language);
    document.getElementById("suggest-why").textContent =
      pick.minutes ? why + " · " + pick.minutes + " min" : why;
    document.getElementById("suggest-blurb").textContent = pick.blurb || "";
  }

  /* --- what you know --------------------------------------------------------- */

  function drawKnown(code, store) {
    var line = document.getElementById("known-line");
    var known = charts.known(store && store.words);
    // The same numbers the progress page opens with, said in one line as a reason to go
    // and look at the rest of them.
    var days = charts.days().length;
    document.getElementById("step-progress").textContent = known
      ? known + (known === 1 ? " word" : " words") + ", " + days + (days === 1 ? " day" : " days")
      : "What you have built.";
    // A count of a real thing, and nothing when there is nothing: "You know 0 words" is
    // a score of zero, which is the arcade the brand rules keep out.
    // Named, because a reader with Hebrew and Russian has two counts and this line is
    // only ever about the one the switcher is on.
    line.textContent = known
      ? "You know " + known + " " + named(code) + (known === 1 ? " word." : " words.")
      : "Mark a word while reading and it starts here.";
  }

  /* --- putting it together --------------------------------------------------- */

  var opened = stored("targum:opened");

  ask("/readers")
    .then(function (data) {
      var readers = (data && data.readers) || [];
      var trash = (data && data.trash) || [];
      readers.forEach(function (reader) {
        reader.opened = opened[reader.document] || 0;
      });
      // What you had open last, then what was built most recently.
      readers.sort(function (a, b) {
        return b.opened - a.opened || b.built * 1000 - a.built * 1000;
      });

      // `kept()` is a list of {language}, not a map — reading it with Object.keys put a
      // language called "0" in the switcher.
      var vocabulary = kept();
      var codes = [lang.HOME];
      readers.concat(vocabulary).forEach(function (thing) {
        var code = base(thing.language);
        if (code && codes.indexOf(code) < 0) codes.push(code);
      });
      codes = lang.order(codes, names);

      var nothing = !readers.length && !vocabulary.length;
      document.getElementById("nothing").hidden = !nothing;
      document.getElementById("page").hidden = nothing;
      if (nothing) return;

      var chosen = lang.current(codes);

      function show(code) {
        chosen = code;
        // Remembered here rather than inside the switcher: the same control now draws
        // two different preferences, and only the caller knows which one it is drawing.
        lang.set(code);
        lang.switcher(document.getElementById("langs"), codes, names, code, show);
        var mine = readers.filter(function (reader) {
          return base(reader.language) === code;
        });
        drawCarry(mine[0]);
        // The rest of the shelf. Repeating the one above it would be a list whose first
        // row is the thing already filling the top of the page.
        shelf.draw(
          code,
          readers.filter(function (reader) {
            return reader !== mine[0];
          }),
          { limit: SHELF, note: "Last read first." }
        );
        shelf.trash(code, trash);
        suggest(code, readers);
        // Meanings in the language this reader last read this one into. A word means
        // something different in each, and a table that mixed them would be handing out
        // definitions in a language nobody asked for.
        var store = charts.collect(charts.meaningLanguage(code))[code];
        drawKnown(code, store);
        lists.draw(code, store, { words: WORDS, phrases: PHRASES });
      }

      lists.onMeaningLanguage(function () {
        lists.draw(chosen, charts.collect(charts.meaningLanguage(chosen))[chosen], {
          words: WORDS,
          phrases: PHRASES,
        });
      });

      lists.mount({
        languages: names,
        // A word marked known in the table is a word the line above has to stop
        // promising. Same number, one place it is counted.
        onChanged: function () {
          drawKnown(chosen, charts.collect(charts.meaningLanguage(chosen))[chosen]);
        },
      });
      show(chosen);
    })
    .catch(function () {
      // Signed out, or the server went away. The page says nothing rather than half of
      // something, and the nav is still there to leave by.
      document.getElementById("nothing").hidden = false;
    });

  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (changed) reload();
    });
    // An export comes from the account, so signed out there is nothing to offer and the
    // two buttons stay away rather than handing back a subset of one browser.
    window.TargumSync.start().then(function () {
      lists.offerExports(!!window.TargumSync.who);
    });
  }
})();
