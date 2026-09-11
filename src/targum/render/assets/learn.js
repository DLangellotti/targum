/* Learn — the page you land on, and everything you are learning.
 *
 * How many words you know, then three doors — carry on, find something, bring your own —
 * then your shelf, then the words and phrases themselves. The count is one line rather
 * than a panel of numbers: engagement is welcome and arcade is not (design.md §1), and
 * the charts that make an account of it live on Your Progress. That rule used to be
 * written "the reader is a reader rather than a player"; the sentence was withdrawn on
 * 2026-09-03 when a text that carries media began opening as its media, but the half of
 * it that keeps a scoreboard off this page still stands.
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
    return "You know " + Math.round(reader.known * 100) + "%";
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
    var sheet = document.getElementById("carry-sheet");
    var panel = document.getElementById("carry");
    if (!reader) {
      sheet.hidden = true;
      settleTalk();
      return;
    }
    door = door || { state: "carry" };
    sheet.hidden = false;
    settleTalk();
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
    } else if (door.src) {
      panel.href = keyed(door.src);
    } else {
      panel.href = keyed("/reader/" + readerPath(reader, door));
    }
    panel.setAttribute("data-entry", reader.entry || reader.id || "");

    var cover = document.getElementById("carry-cover");
    cover.textContent = "";
    var pictured = reader.entry || reader.id || reader.name;
    if (pictured) {
      cover.appendChild(
        window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(pictured)), {
          title: reader.title,
          language: reader.language,
          drawn: reader.drawn,
        })
      );
    }

    var title = document.getElementById("carry-title");
    title.textContent = reader.title;
    title.setAttribute("lang", reader.language);
    english("carry-english", reader.english);

    document.getElementById("carry-meta").textContent = door.meta !== undefined ? door.meta : facts(reader, door);

    var known = document.getElementById("carry-known");
    var said = share(reader);
    known.hidden = !said;
    known.textContent = said;
    drawFrame(reader, door);
  }

  // The reader's own path under `/reader/`: the text's opening page, or the page the
  // conversation offered (`<name>/reader/<file>`), each segment encoded on its own.
  function readerPath(reader, door) {
    var path = door.path || reader.name + "/reader/index.html";
    return path.split("/").map(encodeURIComponent).join("/");
  }

  // The sheet's window (§13): the reader itself, framed and working, at the place it
  // was left — `preview=1` tells it it is on the front page, so it draws no bar, keeps
  // its own links in the frame and counts a visit at the first press. Only where the
  // door is the reader: a step up past the sequence is a library row, and a library
  // row is not a text to look at.
  function drawFrame(reader, door) {
    var window_ = document.getElementById("carry-window");
    var frame = document.getElementById("carry-frame");
    if (!window_ || !frame) return;
    if (!door.src && (door.href || !reader.name)) {
      window_.hidden = true;
      return;
    }
    window_.hidden = false;
    frame.title = reader.title || "";
    // A series' instalment names its reader's page itself (`door.src`): the weekly
    // portion's and a cycle's live under their own `/read/`, not under `/reader/`.
    var src = keyed(door.src || "/reader/" + readerPath(reader, door));
    src += (src.indexOf("?") < 0 ? "?" : "&") + "preview=1";
    // Set only when it changes: a frame reloads on every write to its address.
    if (frame.getAttribute("src") === src) return;
    frame.setAttribute("src", src);
  }

  /* --- the conversation, put away and brought back ------------------------------
   * "Let's make it so the chat can collapse and then be accessible through a sticky
   * CTA ... the user should be able to expand the reader on the learn page, by
   * minimizing the chat" (2026-09-11). One state, remembered in this browser: the
   * conversation shown beside the sheet, or put away — the sheet takes the row and
   * grows, and a pill at the foot of the window brings the conversation back. With no
   * sheet to give the row to, the conversation is always shown.
   */
  var TALK = "targum:front-talk";
  var talkAway = false;
  try {
    talkAway = localStorage.getItem(TALK) === "away";
  } catch (e) {
    talkAway = false;
  }

  function settleTalk() {
    var front = document.getElementById("front");
    var sheet = document.getElementById("carry-sheet");
    var cta = document.getElementById("talk-cta");
    var expand = document.getElementById("carry-expand");
    if (!front) return;
    var away = talkAway && !!sheet && !sheet.hidden;
    front.classList.toggle("expanded", away);
    if (cta) cta.hidden = !away;
    if (expand) {
      expand.textContent = away ? "Shrink" : "Expand";
      expand.setAttribute("aria-pressed", away ? "true" : "false");
    }
  }

  function putTalk(away) {
    talkAway = away;
    try {
      if (away) localStorage.setItem(TALK, "away");
      else localStorage.removeItem(TALK);
    } catch (e) {
      /* nothing to keep it in; the page still stands */
    }
    settleTalk();
  }

  function onPress(id, act) {
    var control = document.getElementById(id);
    if (control) control.addEventListener("click", act);
  }
  onPress("talk-hide", function () {
    putTalk(true);
  });
  onPress("talk-cta", function () {
    putTalk(false);
  });
  onPress("carry-expand", function () {
    putTalk(!talkAway);
  });
  settleTalk();

  /* --- a text offered in the conversation ----------------------------------------
   * The framed conversation cannot open a page of its own; it offers the text to this
   * page, which opens it in the sheet — "opened first in the reader on this page, then
   * they can expand or go to the dedicated page" (2026-09-11). Same origin only, and
   * only from the conversation's own frame.
   */
  var everything = [];
  function offeredText(path) {
    var name = "";
    try {
      name = decodeURIComponent(String(path).split("/")[0]);
    } catch (e) {
      name = String(path).split("/")[0];
    }
    if (!name) return;
    var found = null;
    everything.forEach(function (reader) {
      if (!found && reader.name === name) found = reader;
    });
    var reader = found || { name: name, title: name, language: "he" };
    drawCarry(reader, {
      state: "carry",
      heading: "From the conversation",
      primary: true,
      path: path,
      meta: found ? undefined : "",
    });
    var sheet = document.getElementById("carry-sheet");
    if (sheet && typeof sheet.scrollIntoView === "function") {
      var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      sheet.scrollIntoView({ block: "start", behavior: still ? "auto" : "smooth" });
    }
  }
  window.addEventListener("message", function (event) {
    var talk = document.getElementById("talk-frame");
    if (event.origin !== window.location.origin) return;
    if (talk && talk.contentWindow && event.source !== talk.contentWindow) return;
    var data = event.data || {};
    if (data.type === "targum:open" && data.reader) offeredText(String(data.reader));
    // A page of words marked known in the conversation's first exchange: the count
    // above the sheet is drawn again from the ledger it just changed.
    if (data.type === "targum:changed") reload();
  });

  /* --- what to read next ------------------------------------------------------
   *
   * The catalogue rides in the page, trimmed to an id, a title and two numbers. The
   * step up is worked out here rather than on the server for the same reason the word
   * counts are: what this reader has already read is in this browser, and the server
   * has no business being told about it to answer a question this size.
   *
   * "Level" is the difficulty of the hardest thing they have built — measured as the
   * share of running words a reader has to look up, so it is a fact about the text
   * rather than a guess about the person. The step up is the easiest thing in the
   * catalogue that is harder than that. It is drawn in the sheet only when there is
   * nothing of this reader's own to carry on with; the suggestion card that stood
   * beside the sheet left this page on 2026-09-11 with the rest of the lobby.
   */

  var catalogue = window.TARGUM_CATALOGUE || [];

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

  function drawKnown(code, store) {
    var line = document.getElementById("known-line");
    var known = charts.known(store && store.words);
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
      everything = readers.concat(shared);
      everything.forEach(function (reader) {
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
          // Hebrew: two tracks, one sheet. The track opened most recently takes it; on
          // a first sign-in modern does, and the Biblical track is on the Library.
          var modern = trackDoor(code, "modern", readers, shared);
          var biblical = trackDoor(code, "biblical", readers, shared);
          var door = biblical.reader && biblical.opened > modern.opened ? biblical : modern;
          door.primary = true;
          if (door.reader) {
            drawCarry(door.reader, door);
            inDoors.push(door.reader);
          } else {
            // Past the scenes: the catalogue's next step, as a link to its library row;
            // and past the catalogue, the Biblical track's own start.
            var up = stepUp(code, readers.concat(shared), "modern");
            if (!up && biblical.reader) {
              biblical.primary = true;
              drawCarry(biblical.reader, biblical);
              inDoors.push(biblical.reader);
            } else if (up) {
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
                  primary: true,
                  href: "/library#" + encodeURIComponent(up.pick.id),
                  meta: up.pick.minutes ? up.why + " · " + up.pick.minutes + " min" : up.why,
                }
              );
            } else {
              drawCarry(null);
            }
          }
        } else {
          // One track: carry on with your own, or start on what was handed to you.
          var start = !mine.length && handed.length ? handed[0] : null;
          var carrying = mine[0] || start;
          drawCarry(carrying, { state: start ? "start" : "carry", primary: !!carrying });
          if (carrying) inDoors.push(carrying);
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
        // Meanings in the language this reader last read this one into, for the count.
        var store = charts.collect(charts.meaningLanguage(code))[code];
        drawKnown(code, store);
      }

      show(chosen);
      landed();
    })
    .catch(function () {
      // Signed out, or the server went away. The page says nothing rather than half of
      // something, and the nav is still there to leave by.
      document.getElementById("nothing").hidden = false;
    });

  /* --- a subscription that landed (2026-09-11) ------------------------------------
   * A followed series' newest instalment, the first time this browser sees it, takes
   * the sheet as what to read next and is said in the bell; seen once, the sheet goes
   * back to what the reader was reading. The Library is where following is done.
   */
  function landed() {
    var follow = window.TargumFollow;
    if (!follow) return;
    follow.list().then(function (series) {
      var fresh = follow.fresh(series);
      if (!fresh.length) return;
      fresh.forEach(function (one) {
        var line = one.name + ": " + (one.instalment.hebrew || one.instalment.title);
        if (window.TargumNotices && window.TargumNotices.note) {
          window.TargumNotices.note("series:" + one.id + ":" + one.instalment.id, line, {
            href: keyed(one.page || follow.readerOf(one)),
            label: "Open",
          });
        }
      });
      var newest = fresh[0];
      var src = follow.readerOf(newest);
      if (!src) return;
      var inst = newest.instalment;
      drawCarry(
        {
          name: "",
          title: inst.hebrew || inst.title,
          english: inst.hebrew ? inst.title : "",
          language: "he",
        },
        {
          state: "carry",
          heading: "New: " + newest.name,
          primary: true,
          src: src,
          href: newest.page || src,
          meta: follow.whenSaid(inst.when),
        }
      );
      follow.markSeen(newest.id, inst.id);
    });
  }

  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (changed) reload();
    });
    // An export comes from the account, so signed out there is nothing to offer and the
    // two buttons stay away rather than handing back a subset of one browser.
    window.TargumSync.start();
  }

})();
