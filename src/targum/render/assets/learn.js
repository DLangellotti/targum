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
    // "0% of its words" on the first card a new reader sees is true and unkind; the
    // line starts once there is something to say.
    if (!reader.known) return "";
    return Math.round(reader.known * 100) + "% of its words are ones you know";
  }

  // The title in English under the Hebrew one, where the catalogue has one. An upload
  // has none and the line stays away.
  function english(id, text) {
    var line = document.getElementById(id);
    if (!line) return;
    line.hidden = !text;
    line.textContent = text || "";
  }

  /* --- the doors ---------------------------------------------------------------
   *
   * Two Hebrews, two doors. Readers of modern Hebrew and readers of the Bible are two
   * cohorts with little crossover, each with its beginners, its false beginners and its
   * advanced readers; so the page always shows both tracks, Modern on the left and
   * Biblical on the right, each carrying its own next step. The track is the register,
   * never a level: nobody is asked how good they are, and nothing is stored about which
   * track they are "on". What tells a beginner from a false beginner is what they have
   * marked, which the app already measures.
   *
   * A door's state is one word. Start here: nothing of this Hebrew opened yet, and the
   * first of its sequence waits. Continue: the text last opened, unfinished. Up next:
   * the last one is finished and the sequence has more. A step up: the sequence is done
   * and the catalogue's nearest harder text is offered instead.
   */
  var TRACKS = { modern: "Modern Hebrew", biblical: "Biblical Hebrew" };
  var STATES = { start: "Start here", carry: "Continue", next: "Up next", up: "A step up" };

  var scenes = window.TargumScenes || null;

  function sceneOf(reader) {
    return scenes && reader ? scenes.numberOf(reader.entry) : 0;
  }

  // The facts under a title: which scene of how many, how much is left, how long it
  // is, whether it can be heard. Never "ready" — build vocabulary — and never a share
  // of zero.
  function facts(reader, door) {
    var out = [];
    var number = sceneOf(reader);
    if (number) {
      out.push("Scene " + number + (door.total ? " of " + door.total : ""));
      if (door.state === "carry" && typeof reader.fresh === "number" && reader.fresh > 0) {
        out.push(reader.fresh + (reader.fresh === 1 ? " word left" : " words left"));
      } else if (reader.words) {
        out.push(reader.words + " words");
      }
    } else if (reader.chapters && reader.chapters.length > 1) {
      // "4 of 4" is a fraction with nothing left to say; "2 of 4 translated" says what
      // the fraction is a fraction of.
      out.push(
        reader.readyChapters === reader.chapters.length
          ? reader.chapters.length + " chapters"
          : reader.readyChapters + " of " + reader.chapters.length + " translated"
      );
    } else if (reader.sections > 1) {
      out.push(reader.sections + " parts");
    } else if (reader.minutes && door.state !== "carry") {
      out.push(reader.minutes + " min");
    }
    // One word, as on the library's rows: a video can be heard too, and saying both
    // says less than "video" does.
    if (reader.video) out.push("video");
    else if (reader.spoken) out.push("audio");
    if (door.state === "carry" && !number) {
      out.push(reader.opened ? "opened " + ago(reader.opened) : "not opened yet");
    }
    return out.join(" · ");
  }

  // The label above a door's heading, naming the track; none for a language with one.
  function trackLabel(id, register) {
    var label = document.getElementById(id);
    if (!label) return;
    var name = register ? TRACKS[register] || "" : "";
    label.hidden = !name;
    label.textContent = name;
  }

  function drawCarry(reader, door) {
    var panel = document.getElementById("carry");
    if (!reader) {
      panel.hidden = true;
      return;
    }
    door = door || { state: "carry" };
    panel.hidden = false;
    var heading = document.getElementById("carry-heading");
    if (heading) heading.textContent = door.heading || STATES[door.state] || "Continue";
    trackLabel("carry-track", door.register);
    panel.classList.toggle("primary", !!door.primary);
    // The box is the link, so this is the only href on it. A step up past the sequence
    // is a text not yet built, and this door is a link rather than a button: it goes to
    // the library row, which is where building is pressed for.
    if (door.href) {
      // The key rides in the query, and a query belongs before the fragment.
      var parts = door.href.split("#");
      panel.href = keyed(parts[0]) + (parts[1] ? "#" + parts[1] : "");
    } else {
      panel.href = keyed("/reader/" + encodeURIComponent(reader.name) + "/reader/index.html");
    }
    panel.setAttribute("data-entry", reader.entry || reader.id || "");

    var cover = document.getElementById("carry-cover");
    cover.textContent = "";
    cover.appendChild(
      window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(reader.entry || reader.id || reader.name)), {
        title: reader.title,
        language: reader.language,
        drawn: reader.drawn,
      })
    );

    var title = document.getElementById("carry-title");
    title.textContent = reader.title;
    title.setAttribute("lang", reader.language);
    english("carry-english", reader.english);

    document.getElementById("carry-meta").textContent = door.meta !== undefined ? door.meta : facts(reader, door);

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
  // A shared text offered beside the start: already built, so pressing the card opens
  // it rather than building anything.
  var offeredShared = null;

  function take() {
    if (offeredShared) {
      window.location.href = keyed(
        "/reader/" + encodeURIComponent(offeredShared.name) + "/reader/index.html"
      );
      return;
    }
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

  // A built text on the right-hand door — the Biblical track's next step, or for a
  // language with no tracks the second shared text — already built, one press to open.
  function suggestShared(reader, door) {
    var card = document.getElementById("suggest");
    if (!card) return;
    door = door || { state: "start" };
    offered = null;
    offeredShared = reader;
    card.hidden = false;
    card.disabled = false;
    card.classList.toggle("primary", !!door.primary);
    var heading = document.getElementById("suggest-heading");
    if (heading) heading.textContent = door.heading || STATES[door.state] || "Start here";
    trackLabel("suggest-track", door.register);
    card.setAttribute("data-entry", reader.entry || reader.name);
    var cover = document.getElementById("suggest-cover");
    cover.textContent = "";
    cover.appendChild(
      window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(reader.entry || reader.name)), {
        title: reader.title,
        language: reader.language,
        drawn: reader.drawn,
      })
    );
    var title = document.getElementById("suggest-title");
    title.textContent = reader.title;
    title.setAttribute("lang", reader.language);
    english("suggest-english", reader.english);
    document.getElementById("suggest-why").textContent = facts(reader, door);
    document.getElementById("suggest-blurb").textContent = "";
  }

  /* The nearest harder text in the catalogue, for one register or for all of them.
     "Level" is the difficulty of the hardest thing built in that Hebrew — a fact about
     the texts rather than a guess about the person — and the pick is the easiest thing
     harder than it. Nothing built counts as level nought, and the pick is then where
     most people start. */
  function stepUp(code, readers, register) {
    var built = {};
    readers.forEach(function (reader) {
      if (reader.entry) built[reader.entry] = true;
    });
    var open = catalogue
      .filter(function (entry) {
        // `difficulty >= 0` rather than a truth test. Zero is a measurement, not a
        // missing one: a twenty-word beginner scene has no uncommon word in it, and
        // reading it as "not measured" dropped the seven easiest texts in the library
        // out of the one list a beginner is shown.
        return (
          base(entry.language) === code &&
          !built[entry.id] &&
          entry.difficulty >= 0 &&
          (!register || entry.register === register)
        );
      })
      .sort(function (a, b) {
        return a.difficulty - b.difficulty;
      });
    if (!open.length) return null;
    var level = 0;
    readers.forEach(function (reader) {
      if (base(reader.language) !== code) return;
      if (register && reader.register !== register) return;
      if (reader.difficulty > level) level = reader.difficulty;
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
    return { pick: pick, why: why, level: level };
  }

  function suggest(code, readers, door) {
    // Never over a build in progress: the shelf redraws for its own reasons, and this
    // would put the reason for the suggestion back over the line narrating it.
    if (building) return;
    var card = document.getElementById("suggest");
    if (!card) return;
    door = door || {};
    offeredShared = null;
    card.classList.toggle("primary", !!door.primary);
    trackLabel("suggest-track", door.register);

    var found = stepUp(code, readers, door.register || "");
    if (!found) {
      offered = null;
      card.hidden = true;
      return;
    }
    var pick = found.pick;
    var suggestHeading = document.getElementById("suggest-heading");
    if (suggestHeading) {
      // On a track: "Start here" while nothing of that Hebrew has been built, "A step
      // up" after. Off a track it is the suggestion it always was.
      suggestHeading.textContent = door.register
        ? found.level
          ? STATES.up
          : STATES.start
        : "Suggested";
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
    english("suggest-english", pick.english);
    document.getElementById("suggest-why").textContent =
      pick.minutes ? found.why + " · " + pick.minutes + " min" : found.why;
    document.getElementById("suggest-blurb").textContent = pick.blurb || "";
  }

  /* One track's door: which text, in which state, with the accent if this is the Hebrew
     the reader opened most recently. `readers` are their own, `shared` the seeded ones.
     The fixed sequence is the numbered scenes for modern Hebrew and the shared Biblical
     texts (Ruth) for the other; a box with no scenes seeded falls back to whatever
     shared modern text it has. */
  function trackDoor(code, register, readers, shared) {
    var docs = stored("targum:docs");
    function ofHere(list) {
      return list.filter(function (reader) {
        return base(reader.language) === code && reader.register === register;
      });
    }
    function done(reader) {
      return !!(scenes && scenes.finished(reader, docs));
    }
    var own = ofHere(readers);
    var pool = ofHere(shared);
    var numbered = pool.filter(function (reader) {
      return sceneOf(reader) > 0;
    });
    var sequence = pool;
    if (register === "modern" && numbered.length && scenes) {
      sequence = scenes
        .ordered(
          numbered.map(function (reader) {
            return { id: reader.entry, reader: reader };
          })
        )
        .map(function (item) {
          return item.reader;
        });
    }
    // The text last opened: any of the reader's own, or a shared one they have opened.
    // An upload never opened is still theirs, and newest of those wins over a sequence
    // they have not started.
    var last = null;
    own.concat(
      pool.filter(function (reader) {
        return reader.opened > 0;
      })
    ).forEach(function (reader) {
      if (!last || reader.opened > last.opened || (reader.opened === last.opened && reader.built > last.built)) {
        last = reader;
      }
    });
    var next = null;
    for (var i = 0; i < sequence.length; i++) {
      if (!done(sequence[i])) {
        next = sequence[i];
        break;
      }
    }
    var anyDone = own.concat(pool).some(done);
    var door = {
      register: register,
      total: numbered.length,
      opened: last ? last.opened : 0,
      reader: null,
      state: "up",
    };
    if (last && !done(last)) {
      door.state = "carry";
      door.reader = last;
    } else if (next) {
      // Finished on another device, where `opened` never synced: any finish at all
      // means this is not a start.
      door.state = last || anyDone ? "next" : "start";
      door.reader = next;
    }
    return door;
  }

  /* --- what you know --------------------------------------------------------- */

  // Whether both doors are at Start here — the first sign-in, one Hebrew or the other
  // still to be chosen — and so whether the line above them should say so rather than
  // count.
  var choosing = false;

  function drawKnown(code, store) {
    var line = document.getElementById("known-line");
    var known = charts.known(store && store.words);
    if (choosing && !known) {
      line.textContent = "Modern or Biblical. Start with one.";
      document.getElementById("step-progress").textContent = "Words known, days reading.";
      return;
    }
    // The same numbers the progress page opens with, said in one line as a reason to go
    // and look at the rest of them.
    var days = charts.days().length;
    document.getElementById("step-progress").textContent = known
      ? known + (known === 1 ? " word" : " words") + ", " + days + (days === 1 ? " day" : " days")
      : "Words known, days reading.";
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
      var shared = (data && data.shared) || [];
      var trash = (data && data.trash) || [];
      readers.concat(shared).forEach(function (reader) {
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

      // An empty shelf used to swap the whole page for three lines pointing at the
      // Library. The suggestion — the one thing on this page that says where to start
      // — lives inside the page, so the reader with nothing was the one reader who
      // never saw it. The page draws with its panels empty and the suggestion drawn.
      document.getElementById("nothing").hidden = true;
      document.getElementById("page").hidden = false;

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
        var handed = shared.filter(function (reader) {
          return base(reader.language) === code;
        });
        var inDoors = [];
        if (code === lang.HOME) {
          // Hebrew: two tracks, two doors, each its own next step. The accent goes to
          // the track opened most recently; on a first sign-in, where the choice is
          // genuinely two-way, to neither.
          var modern = trackDoor(code, "modern", readers, shared);
          var biblical = trackDoor(code, "biblical", readers, shared);
          if (modern.opened || biblical.opened) {
            (modern.opened >= biblical.opened ? modern : biblical).primary = true;
          }
          choosing = modern.state === "start" && biblical.state === "start";
          if (modern.reader) {
            drawCarry(modern.reader, modern);
            inDoors.push(modern.reader);
          } else {
            // Past the scenes: the catalogue's next step, as a link to its library row.
            var up = stepUp(code, readers.concat(shared), "modern");
            if (up) {
              drawCarry(
                {
                  id: up.pick.id,
                  entry: up.pick.id,
                  title: up.pick.title,
                  english: up.pick.english,
                  language: up.pick.language,
                  minutes: up.pick.minutes,
                },
                {
                  state: up.level ? "up" : "start",
                  register: "modern",
                  primary: modern.primary,
                  href: "/library#" + encodeURIComponent(up.pick.id),
                  meta: up.pick.minutes ? up.why + " · " + up.pick.minutes + " min" : up.why,
                }
              );
            } else {
              drawCarry(null);
            }
          }
          if (biblical.reader) {
            suggestShared(biblical.reader, biblical);
            inDoors.push(biblical.reader);
          } else {
            suggest(code, readers.concat(shared), biblical);
          }
        } else {
          // One track: carry on with your own, or start on what was handed to you, and
          // the catalogue's suggestion beside it.
          choosing = false;
          var start = !mine.length && handed.length ? handed[0] : null;
          var carrying = mine[0] || start;
          drawCarry(carrying, { state: start ? "start" : "carry", primary: !!carrying });
          if (carrying) inDoors.push(carrying);
          if (!mine.length && handed.length > 1) suggestShared(handed[1], { state: "start" });
          else suggest(code, readers.concat(shared), {});
        }
        // The rest of the shelf. Repeating the one above it would be a list whose first
        // row is the thing already filling the top of the page.
        shelf.draw(
          code,
          readers.filter(function (reader) {
            return inDoors.indexOf(reader) < 0;
          }),
          { limit: SHELF, note: "Last read first." }
        );
        shelf.trash(code, trash);
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

  /* --- the week's issue ------------------------------------------------------
   *
   * A line above the doors, not a third box. The weekly is written three times over and
   * this is the one page that knows who is reading, so it opens at the reader's own
   * rung — `charts.levelFor` weighs their marked words on the same ladder the progress
   * page draws, rather than a second count that would disagree with it.
   *
   * Once they have opened this week's issue the line goes quiet rather than away: gone,
   * there is no way back to it from here, and nagging is what the brand rules refuse.
   */
  function drawWeekly() {
    var issue = window.TARGUM_WEEKLY;
    var line = document.getElementById("weekly-line");
    if (!issue || !line || !issue.levels || !issue.levels.length) return;

    var READ = "targum:weekly:opened";
    var opened = false;
    try {
      opened = window.localStorage.getItem(READ) === issue.id;
    } catch (error) {
      opened = false;
    }

    // The same store the progress page reads, asked for Hebrew. Empty is the ordinary
    // state for somebody who has marked nothing yet, and the ladder answers with its
    // lowest rung, which is the right issue for them.
    var words = [];
    try {
      var store = charts.collect(charts.meaningLanguage("he"))["he"];
      words = (store && store.words) || [];
    } catch (error) {
      words = [];
    }
    var level = charts.levelFor(words, issue.levels) || issue.levels[0];

    var link = document.getElementById("weekly-link");
    document.getElementById("weekly-title").textContent = issue.title;
    document.getElementById("weekly-at").textContent = "in " + level.name;
    document.getElementById("weekly-when").textContent = opened ? "read" : "this week";
    link.href = keyed("/reader/" + encodeURIComponent(level.folder) + "/reader/index.html");
    line.classList.toggle("done", opened);
    line.hidden = false;

    link.addEventListener("click", function () {
      try {
        window.localStorage.setItem(READ, issue.id);
      } catch (error) {
        /* A private window. The line offers itself again next time, which is no worse
           than the first time. */
      }
    });
  }

  drawWeekly();


})();
