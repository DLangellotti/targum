/* Talking to targum.
 *
 * A line goes up as `POST /chat/say`, which writes it down and hands it to a worker at
 * once; the answer arrives on `GET /chat/stream/<chat>/<n>` as server-sent events, or —
 * where a browser has no EventSource — by asking `/chat/turn/<chat>/<n>` until it is
 * done. Leaving the page cancels nothing: the conversation is the server's, and coming
 * back reads it from `/chat/<id>`.
 *
 * What the model writes is shown as text, never as HTML. The one thing made of it is a
 * link: a path to a reader or the library, on its own, becomes an anchor with this
 * session's key on it, because that is how every other page here links.
 */
(function () {
  "use strict";

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  var list = document.getElementById("chat-list");
  var fresh = document.getElementById("chat-new");
  var empty = document.getElementById("chat-empty");
  var turns = document.getElementById("turns");
  var said = document.getElementById("chat-said");
  var form = document.getElementById("composer");
  var field = document.getElementById("say");
  var send = document.getElementById("chat-send");
  if (!list || !turns || !form || !field || !send) return;

  var current = "";
  var chats = [];
  var busy = false;
  var usable = true;
  var hoursLine = document.getElementById("chat-hours");
  var mic = document.getElementById("chat-mic");
  // Push-to-talk needs a browser that records (`speak.js` says whether this one does)
  // and a reader with modern Hebrew to speak — `/chat/list` says which, as `talk`, and
  // the front door's box reads the same word. Without either the button never appears,
  // and nothing on the page says a thing it cannot do.
  var speak = window.TargumSpeak;
  var canRecord = !!(speak && speak.can);
  var talk = true;

  // Said by the script and not left to the template, so the two cannot disagree about
  // what a page shows on a browser that cannot record.
  function showMic() {
    if (mic) mic.hidden = !canRecord || !talk;
  }
  showMic();

  // The month's hours, above the box, and only past three quarters of them: the cap
  // should not be the first a reader hears of it, and a count on every visit was the
  // metric in everybody's face (2026-09-10, targum-internal#237). The whole count is on
  // Your Progress and in the account panel.
  function drawHours(got) {
    if (!hoursLine || !got) return;
    var line = window.TargumBring ? window.TargumBring.hoursWarning(got) : "";
    hoursLine.textContent = line;
    hoursLine.hidden = !line;
  }

  // A failed request is an answer with an error in it, never a rejection left to the
  // console: opened off the disk, or with the server gone, every fetch here fails, and
  // the page still has to stand and say so.
  var UNREACHED = { error: "targum could not be reached. Try again." };
  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    })
      .then(function (response) {
        return response.json();
      })
      .catch(function () {
        return UNREACHED;
      });
  }

  function tell(text) {
    if (!said) return;
    said.textContent = text || "";
    said.hidden = !text;
  }

  /* --- the record ------------------------------------------------------------
   *
   * In Hebrew the thread is drawn as the text it becomes (design.md §12, 2026-09-06):
   * each line's words arrive from the server read as a text is read, and take their
   * state from the reader's own ledger — the same `targum:vocab:he` the reader writes,
   * read here and never written. A word on the ledger is bare; a word not met is
   * marked and counted at the foot.
   */

  function ledger() {
    try {
      return JSON.parse(localStorage.getItem("targum:vocab:he") || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  // What the reader's ledger says about one dictionary form: "known", "learning", or
  // "new" — and nothing for a name or a number, which are not vocabulary.
  function stateOf(word, kept) {
    if (!word.lemma || word.pos === "PROPN" || word.pos === "NUM") return "";
    var row = kept[word.lemma];
    if (!row) return "new";
    if (row.status === 9) return "known";
    if (row.status === 0) return "";
    return "learning";
  }

  // The meanings looked up on this page, by dictionary form, on top of what the server
  // already held.
  var meanings = {};

  function glossLine(pair, word, sentence) {
    var open = pair.querySelector(".chat-gloss");
    if (open) {
      pair.removeChild(open);
      if (open.getAttribute("data-lemma") === word.lemma) return;
    }
    var line = document.createElement("span");
    line.className = "chat-gloss";
    line.setAttribute("data-lemma", word.lemma);
    var form = document.createElement("bdi");
    form.setAttribute("lang", "he");
    form.textContent = word.lemma;
    line.appendChild(form);
    var meaning = meanings[word.lemma] || word.meaning || "";
    if (meaning) {
      line.appendChild(document.createTextNode(" · " + meaning));
    } else {
      // Not held. Looking it up is the reader's own press and the reader's own spend,
      // the same door the word card in a text opens.
      var look = document.createElement("button");
      look.type = "button";
      look.className = "chat-look";
      look.textContent = "look it up";
      look.onclick = function () {
        look.disabled = true;
        look.textContent = "looking…";
        ask("/gloss", { lemma: word.lemma, source: "he", target: "en", sentence: sentence }).then(
          function (got) {
            if (got && got.meaning) {
              meanings[word.lemma] = got.meaning;
              line.removeChild(look);
              line.appendChild(document.createTextNode(" · " + got.meaning));
            } else {
              look.textContent = (got && got.error) || "nothing found";
            }
          }
        );
      };
      line.appendChild(look);
    }
    pair.appendChild(line);
  }

  // A Hebrew line with its words marked, where the server has read it; the bare line
  // where it has not (yet).
  function drawHebrew(he, text, read, pair) {
    he.textContent = "";
    if (!read || !read.length) {
      he.textContent = text;
      return;
    }
    var kept = ledger();
    var at = 0;
    read.forEach(function (word) {
      if (word.start > at) he.appendChild(document.createTextNode(text.slice(at, word.start)));
      var span = document.createElement("span");
      var state = stateOf(word, kept);
      span.className = "chat-w" + (state ? " " + state : "");
      span.setAttribute("data-lemma", word.lemma);
      span.textContent = text.slice(word.start, word.end);
      span.onclick = function () {
        glossLine(pair, word, text);
      };
      he.appendChild(span);
      at = word.end;
    });
    if (at < text.length) he.appendChild(document.createTextNode(text.slice(at)));
  }

  function wordsFor(words, text) {
    if (!words || !words.lines) return null;
    for (var i = 0; i < words.lines.length; i++) {
      if (words.lines[i].he === text) return words.lines[i].words;
    }
    return null;
  }

  /* --- drawing ------------------------------------------------------------- */

  // A Hebrew run is marked as one, so the stylesheet can give it its own leading and
  // the browser can shape it right-to-left inside an English line.
  var HEBREW = /[֐-׿][֐-׿\s.,:;!?()"'־׀׃-]*[֐-׿]|[֐-׿]/g;
  // A path the server returned, standing on its own. Nothing else becomes a link.
  var PATH = /(^|\s)(\/(?:reader|library)\/[^\s)]+)/g;
  var ONLY_PATH = /^\/(?:reader|library)\/\S+$/;

  // A path is drawn as a door: the model can say where a text is, and only the reader
  // opens it (design.md §9: the door-opening action is the ink call to action). The
  // door names the text by its folder, since a path is not something a person reads.
  function door(path) {
    var a = document.createElement("a");
    a.className = "chat-door";
    a.href = keyed(path);
    var name = path;
    try {
      name = decodeURIComponent(path);
    } catch (e) {
      /* a path that is not valid UTF-8 is still a door */
    }
    var folder = name.replace(/^\/(?:reader|library)\//, "").split("/")[0];
    folder = folder.replace(/-[a-z]{2}$/, "").replace(/-/g, " ");
    a.appendChild(document.createTextNode("Open "));
    var who = document.createElement("bdi");
    who.textContent = folder;
    a.appendChild(who);
    return a;
  }

  // The conversation's shape: a Hebrew line, then "= " and its English; "> " marks a
  // recast of the reader's words. Read here by the same rule `chat/hebrew.py` reads it.
  function pairs(text) {
    var out = [];
    var pending = null;
    String(text || "").split("\n").forEach(function (raw) {
      var line = raw.trim();
      if (!line) return;
      if (line.indexOf("= ") === 0) {
        if (pending) {
          pending.en = line.slice(2).trim();
          out.push(pending);
          pending = null;
        }
        return;
      }
      if (pending) {
        out.push(pending);
        pending = null;
      }
      if (ONLY_PATH.test(line)) {
        out.push({ path: line });
        return;
      }
      var recast = line.indexOf("> ") === 0;
      var body = recast ? line.slice(2).trim() : line;
      if (/[\u05d0-\u05ea]/.test(body)) pending = { he: body, en: "", recast: recast };
    });
    if (pending) out.push(pending);
    return out;
  }

  function render(target, text, words) {
    target.textContent = "";
    var found = pairs(text);
    // A turn written by the contract is drawn as pairs; anything else as a line.
    if (found.length && found.some(function (p) { return p.en; })) {
      found.forEach(function (p) {
        if (p.path) {
          target.appendChild(door(p.path));
          return;
        }
        var pair = document.createElement("div");
        pair.className = "chat-pair" + (p.recast ? " recast" : "");
        var he = document.createElement("span");
        he.className = "chat-he";
        he.setAttribute("lang", "he");
        he.setAttribute("dir", "rtl");
        drawHebrew(he, p.he, wordsFor(words, p.he), pair);
        var en = document.createElement("span");
        en.className = "chat-en";
        en.textContent = p.en;
        pair.appendChild(he);
        pair.appendChild(en);
        target.appendChild(pair);
      });
      return;
    }
    var pieces = String(text || "").split(PATH);
    // split with two groups yields [before, sep, path, before, sep, path, ...]
    for (var i = 0; i < pieces.length; i++) {
      var piece = pieces[i];
      if (piece === undefined) continue;
      if (i % 3 === 2) {
        target.appendChild(door(piece));
      } else {
        hebrewed(target, piece);
      }
    }
  }

  function hebrewed(target, text) {
    var at = 0;
    var found;
    HEBREW.lastIndex = 0;
    while ((found = HEBREW.exec(text)) !== null) {
      if (found.index > at) target.appendChild(document.createTextNode(text.slice(at, found.index)));
      var span = document.createElement("span");
      span.setAttribute("lang", "he");
      span.setAttribute("dir", "rtl");
      span.textContent = found[0];
      target.appendChild(span);
      at = found.index + found[0].length;
    }
    if (at < text.length) target.appendChild(document.createTextNode(text.slice(at)));
  }

  /* --- a quote, and a text brought by the + ------------------------------------ */

  // The card is bring.js's: the same one the Add page's press and the front door's +
  // draw, from the server's state of the job and never from what the model wrote.
  var bringing = window.TargumBring;
  function quoteCard(li, job) {
    return bringing.quoteCard(li, job);
  }

  // A file chosen by the + is held in the box until Send (2026-09-07), the way a line
  // is typed and then sent. Send with a file means open it: up in pieces or whole,
  // priced, built, the card in the thread as its progress, and — when nothing more
  // was said than "open this" — the reader opened when it is ready, with no turn said:
  // "when I wrote 'open this' with a file, I didn't want that to be the start of a
  // conversation." A line that says more is said after the card, with a note of what
  // was sent, and the reader is left to open from the card or the strip.
  var bring = document.getElementById("chat-bring");
  var file = document.getElementById("chat-file");
  var heldList = document.getElementById("chat-held");
  var held = [];
  function showHeld() {
    if (bringing && heldList) {
      bringing.held(heldList, held, function (index) {
        held.splice(index, 1);
        showHeld();
      });
    }
  }
  // Pictures sent are seen in the thread as the reader's own turn: the pictures
  // themselves, from the files still in hand, so a screenshot sent is a screenshot
  // seen and not a filename (2026-09-07). Drawn from the browser's copy and kept
  // nowhere — a conversation opened again shows the card the reading became. Any
  // other file is named by its card, which is enough.
  function sentTurn(chosen) {
    var pictures = chosen.filter(function (one) {
      return bringing.isPicture(one);
    });
    if (!pictures.length || typeof URL === "undefined" || !URL.createObjectURL) return null;
    var li = turn("user", "");
    var line = li.querySelector(".chat-line");
    var sent = document.createElement("div");
    sent.className = "chat-sent";
    pictures.forEach(function (one) {
      var img = document.createElement("img");
      img.src = URL.createObjectURL(one);
      img.alt = one.name;
      sent.appendChild(img);
    });
    line.appendChild(sent);
    return li;
  }

  function brought(chosen, opening) {
    if (!bringing) return Promise.resolve();
    chosen = bringing.listed(chosen);
    if (!chosen.length) return Promise.resolve();
    busy = true;
    send.disabled = true;
    tell("");
    sentTurn(chosen);
    var li = turn("assistant", "", "working");
    var line = li.querySelector(".chat-line");
    line.textContent = "Uploading…";
    var into = window.TargumLang ? window.TargumLang.into() || "en" : "en";
    return bringing
      .bring(chosen, { to: into }, function (share) {
        line.textContent = "Uploading… " + share + "%";
      })
      .then(function (job) {
        li.className = "chat-turn them";
        line.textContent = "";
        if (job.reader) {
          // The same bytes were already brought: the text is the answer.
          line.appendChild(
            door("/reader/" + String(job.reader).split("/").map(encodeURIComponent).join("/"))
          );
          return;
        }
        if (job.error) {
          li.className = "chat-turn them bad";
          line.textContent = job.error;
          return;
        }
        // Send with a file in the box is the press (2026-09-07): started here, and
        // the card is its progress. A quote the rails refused shows its sentence.
        if (job.stage !== "ready") {
          quoteCard(li, job);
          return job;
        }
        return bringing.start(job).then(function (state) {
          quoteCard(li, state);
          if (state.error || state.blocked) return state;
          if (!opening) return state;
          return bringing.follow(job.id).then(function (done) {
            if (done.stage === "done" && done.reader) {
              window.location.href = bringing.door(done.reader);
            }
            return done;
          });
        });
      })
      .catch(function (why) {
        li.className = "chat-turn them bad";
        line.textContent = String(why || "That did not go through. Try again.");
      })
      .then(function (job) {
        busy = false;
        send.disabled = false;
        if (file) file.value = "";
        return job;
      });
  }
  if (bring && file) {
    bring.onclick = function () {
      if (!busy) file.click();
    };
    file.onchange = function () {
      // All of them: several pictures chosen together are the pages of one text.
      held = held.concat(bringing ? bringing.listed(file.files) : []);
      file.value = "";
      showHeld();
    };
  }

  // What Send does: the held files first, as a card; then the line, if it said more
  // than "open this" — a bare "open this" is the file's own meaning, and the text
  // opens when it is ready instead.
  function submit() {
    var text = field.value.trim();
    if (held.length) {
      var files = held;
      var spec = bringing && bringing.justOpen(text) ? "" : text;
      held = [];
      showHeld();
      field.value = "";
      brought(files, !spec).then(function (job) {
        if (spec) say(spec, job && job.id);
      });
      return;
    }
    if (!text) return;
    field.value = "";
    say(text);
  }

  // A text brought from the front door with a line arrives as `job=<id>` in the hash:
  // its card is drawn as a turn in the conversation named beside it.
  function showJob(id) {
    return ask("/job/" + encodeURIComponent(id)).then(function (job) {
      if (job.error) return tell(job.error);
      var li = turn("assistant", "", "");
      quoteCard(li, job);
    });
  }

  /* --- speaking and hearing -------------------------------------------------- */

  // One press starts, the next stops. The clip goes up as itself, is written down by
  // the same transcriber a recording gets, and comes back as the reader's line.
  function toggleRecording() {
    if (!canRecord || busy) return;
    speak.toggle(mic, hear, tell);
  }

  function hear(clip) {
    busy = true;
    send.disabled = true;
    var pending = turn("user", "…", "working");
    var path = "/chat/hear?chat=" + encodeURIComponent(current);
    fetch(keyed(path), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": clip.type || "audio/webm" }),
      body: clip,
    })
      .then(function (response) {
        return response.json();
      })
      .catch(function () {
        return UNREACHED;
      })
      .then(function (got) {
        if (got.error) {
          pending.className = "chat-turn me bad";
          render(pending.querySelector(".chat-line"), got.error);
          busy = false;
          send.disabled = false;
          return;
        }
        pending.className = "chat-turn me";
        render(pending.querySelector(".chat-line"), got.heard);
        var answer = turn("assistant", "", "working");
        var wasNew = !current;
        current = got.chat;
        follow(got.chat, got.turn, answer);
        if (wasNew) load();
      });
  }

  // Hear an answer. The clip is made on the first press and kept, and its seconds come
  // out of the same hours a recording does — the press is the spend.
  function playButton(li, chat, n) {
    if (li.querySelector(".chat-play")) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "chat-play";
    button.textContent = "Hear";
    button.onclick = function () {
      button.disabled = true;
      var audio = document.createElement("audio");
      audio.src = keyed("/chat/audio/" + encodeURIComponent(chat) + "/" + n);
      audio.onended = function () {
        button.disabled = false;
      };
      audio.onerror = function () {
        // A refusal comes back as JSON the element cannot play; ask for it in words.
        ask("/chat/audio/" + encodeURIComponent(chat) + "/" + n).then(function (state) {
          button.disabled = false;
          if (state && state.error) tell(state.error);
        });
      };
      var playing = audio.play();
      if (playing && playing.catch) playing.catch(function () {});
    };
    li.appendChild(button);
  }

  function turn(role, text, state, words) {
    var li = document.createElement("li");
    li.className = "chat-turn " + (role === "user" ? "me" : "them") + (state ? " " + state : "");
    var who = document.createElement("span");
    who.className = "chat-who";
    who.textContent = role === "user" ? "You" : "targum";
    var line = document.createElement("p");
    line.className = "chat-line";
    render(line, text, words);
    li.appendChild(who);
    li.appendChild(line);
    turns.appendChild(li);
    if (empty) empty.hidden = true;
    return li;
  }

  function drawList() {
    list.textContent = "";
    chats.forEach(function (chat) {
      var li = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.textContent = chat.title || "Untitled";
      button.setAttribute("data-chat", chat.id);
      if (chat.id === current) button.className = "on";
      button.onclick = function () {
        open(chat.id);
      };
      li.appendChild(button);
      list.appendChild(li);
    });
  }

  /* --- the foot of the record -------------------------------------------------
   *
   * Under the last turn of a conversation in Hebrew: how long it has run, what the
   * reader has not met, what share they knew — measured off the words on the page and
   * the reader's own ledger, never a level — and the door out, Save as targum, which
   * is the quote the model's own save hands the page, reached by the reader's press.
   */

  var footSeconds = 0;

  function drawFoot(seconds) {
    if (seconds !== undefined && seconds !== null) footSeconds = Number(seconds) || 0;
    var old = turns.querySelector(".chat-sum");
    if (old) turns.removeChild(old);
    var marked = turns.querySelectorAll(".chat-w");
    if (!marked.length) return;
    var seen = {};
    var fresh = {};
    var known = 0;
    var vocabulary = 0;
    Array.prototype.forEach.call(marked, function (span) {
      var lemma = span.getAttribute("data-lemma");
      var state = span.className.replace("chat-w", "").trim();
      if (!state) return;
      vocabulary += 1;
      if (state === "known") known += 1;
      if (state === "new" && !seen[lemma]) fresh[lemma] = true;
      seen[lemma] = true;
    });
    var count = Object.keys(fresh).length;
    var li = document.createElement("li");
    li.className = "chat-sum";
    var counts = document.createElement("p");
    counts.className = "chat-counts";
    var minutes = Math.max(1, Math.round(footSeconds / 60));
    var parts = [];
    if (footSeconds > 0) parts.push(minutes + " min");
    // A reader with nothing marked yet is not told they knew 0%: that is a score of
    // zero, which the brand rules keep out. They are told how many words there were,
    // and that marking begins in a text.
    var marked = Object.keys(ledger()).length > 0;
    if (!marked) {
      parts.push(vocabulary + (vocabulary === 1 ? " word" : " words") + " · none marked yet");
    } else {
      parts.push(count + (count === 1 ? " word you have not met" : " words you have not met"));
      if (vocabulary) parts.push("you knew " + Math.round((known / vocabulary) * 100) + "% of this");
    }
    counts.textContent = parts.join(" · ");
    li.appendChild(counts);
    var save = document.createElement("button");
    save.type = "button";
    save.className = "chat-save";
    save.textContent = "Save as targum";
    var note = document.createElement("p");
    note.className = "note";
    save.onclick = function () {
      save.disabled = true;
      ask("/chat/save", { chat: current }).then(function (got) {
        if (got.error) {
          note.textContent = got.error;
          save.disabled = false;
          return;
        }
        li.removeChild(save);
        quoteCard(li, got.quote);
      });
    };
    li.appendChild(save);
    li.appendChild(note);
    turns.appendChild(li);
  }

  /* --- loading ------------------------------------------------------------- */

  function load() {
    return ask("/chat/list").then(function (answer) {
      if (answer.error) return tell(answer.error);
      chats = answer.chats || [];
      usable = answer.usable !== false;
      talk = answer.talk !== false;
      showMic();
      drawHours(answer.hours);
      if (!usable) tell("Nothing can be asked now. Everything you have still opens.");
      drawList();
      // Arrived from the front door with a conversation named in the hash: that one,
      // whose first answer is still streaming; otherwise the newest. A text sent there
      // with a line rides beside it as `job=<id>`, and its card follows in that thread.
      var wanted = "";
      var wantedJob = "";
      try {
        String(window.location.hash || "")
          .slice(1)
          .split("&")
          .forEach(function (part) {
            if (part.indexOf("job=") === 0) wantedJob = decodeURIComponent(part.slice(4));
            else if (part) wanted = decodeURIComponent(part);
          });
      } catch (e) {
        wanted = "";
        wantedJob = "";
      }
      if (current) return;
      var job = wantedJob;
      // Consumed once: `load` runs again when a first line makes a conversation.
      if (job) window.location.hash = wanted ? "#" + encodeURIComponent(wanted) : "";
      if (wanted && chats.some(function (chat) { return chat.id === wanted; })) {
        return open(wanted).then(function () {
          if (job) return showJob(job);
        });
      }
      if (chats.length) return open(chats[0].id);
      if (empty) empty.hidden = !!current;
    });
  }

  function open(id) {
    current = id;
    drawList();
    turns.textContent = "";
    tell("");
    return ask("/chat/" + encodeURIComponent(id)).then(function (answer) {
      if (answer.error) return tell(answer.error);
      var pending = null;
      var lastAsked = 0;
      var lastWords = null;
      (answer.turns || []).forEach(function (t) {
        if (t.role === "user") {
          turn("user", t.said);
          lastAsked = t.n;
          lastWords = t.words || null;
          pending = t.stage === "working" ? t.n : null;
          if (t.stage === "failed" && t.error) turn("assistant", t.error, "bad");
        } else if (t.said) {
          playButton(turn("assistant", t.said, "", lastWords), id, lastAsked);
        }
      });
      if (empty) empty.hidden = true;
      drawFoot(answer.seconds || 0);
      // Came back to an answer still being written: pick the stream up where it is.
      if (pending !== null) follow(id, pending, turn("assistant", "", "working"));
    });
  }

  function startNew() {
    current = "";
    drawList();
    turns.textContent = "";
    tell("");
    if (empty) empty.hidden = false;
    field.focus();
  }

  /* --- asking -------------------------------------------------------------- */

  function say(text, brought) {
    if (busy || !text) return;
    if (!usable) return tell("Nothing can be asked now. Everything you have still opens.");
    busy = true;
    send.disabled = true;
    turn("user", text);
    var answer = turn("assistant", "", "working");
    var line = { chat: current, text: text };
    // The text sent with the line, by its job, so the model knows what it was given.
    if (brought) line.brought = brought;
    ask("/chat/say", line).then(function (got) {
      if (got.error) {
        answer.className = "chat-turn them bad";
        render(answer.querySelector(".chat-line"), got.error);
        busy = false;
        send.disabled = false;
        return;
      }
      var wasNew = !current;
      current = got.chat;
      follow(got.chat, got.turn, answer);
      if (wasNew) load();
    });
  }

  function follow(chat, n, li) {
    var line = li.querySelector(".chat-line");
    var text = "";
    var words = null;
    function finish(kind, payload) {
      li.className = "chat-turn them" + (kind === "error" ? " bad" : "");
      render(line, kind === "error" ? payload.message : payload.text || text, words);
      if (kind !== "error") playButton(li, chat, n);
      if (kind !== "error") drawFoot(payload.seconds);
      busy = false;
      send.disabled = false;
      // The title is the first thing said, so the list learns it on the first answer.
      if (kind !== "error") load();
    }
    var path = "/chat/stream/" + encodeURIComponent(chat) + "/" + n;
    if (typeof EventSource === "function") {
      var source = new EventSource(keyed(path));
      source.addEventListener("text", function (event) {
        text += event.data;
        render(line, text);
      });
      source.addEventListener("tool", function () {
        // A lookup in progress. Said in the reader's words, not the tool's name.
        if (!text) line.textContent = "looking…";
      });
      source.addEventListener("quote", function (event) {
        quoteCard(li, JSON.parse(event.data || "{}"));
      });
      source.addEventListener("words", function (event) {
        // The lines read as a text is read: drawn again with their words marked.
        words = JSON.parse(event.data || "{}");
        render(line, text, words);
      });
      source.addEventListener("done", function (event) {
        source.close();
        finish("done", JSON.parse(event.data || "{}"));
      });
      source.addEventListener("error", function (event) {
        // Both the server's own `error` event, which carries a message, and the
        // browser's, which carries none and means the connection dropped.
        if (event.data) {
          source.close();
          finish("error", JSON.parse(event.data));
        } else if (source.readyState === 2) {
          poll();
        }
      });
      return;
    }
    poll();

    function poll() {
      ask("/chat/turn/" + encodeURIComponent(chat) + "/" + n).then(function (state) {
        if (state.error && state.done) return finish("error", { message: state.error });
        text = state.text || "";
        if (state.words) words = state.words;
        render(line, text, words);
        (state.quotes || []).forEach(function (job) {
          if (!li.querySelector('[data-job="' + job.id + '"]')) quoteCard(li, job);
        });
        if (state.done) return finish("done", { text: text });
        setTimeout(poll, 800);
      });
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    submit();
  });
  field.addEventListener("keydown", function (event) {
    // Enter sends, Shift+Enter breaks the line — the convention every chat shares.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  });
  if (fresh) fresh.onclick = startNew;
  if (mic) mic.onclick = toggleRecording;

  // The account, and the words. Every other page starts the sync — Learn, Library,
  // Progress, Add, Yours — and this one did not, so `/account/me` was never asked here.
  // Two things followed: the header kept the signed-out button it is rendered with, so a
  // reader talking to targum was told to sign in; and `start()`'s first `exchange()`
  // never ran, so a reader who came straight to the chat and stayed had no word sync at
  // all that visit. The page itself works either way — it authenticates server-side with
  // `TARGUM_KEY` — which is why nothing looked wrong (targum-internal#232).
  if (window.TargumSync) window.TargumSync.start();

  load();

  window.TargumChat = {
    say: say,
    open: open,
    render: render,
    quoteCard: quoteCard,
    pairs: pairs,
    hear: hear,
    stateOf: stateOf,
    drawFoot: drawFoot,
  };
})();
