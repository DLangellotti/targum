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
  // What this conversation is for: "find" (the shelf) or "talk" (Hebrew). Sent with
  // every line, so a switch mid-conversation takes from the next line.
  var mode = "find";
  var modes = document.getElementById("chat-mode");
  var hoursLine = document.getElementById("chat-hours");
  var mic = document.getElementById("chat-mic");
  // Push-to-talk needs a browser that records. Without one the button never appears,
  // and nothing on the page says a thing it cannot do.
  var canRecord =
    typeof navigator !== "undefined" &&
    navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function" &&
    typeof MediaRecorder === "function";

  function setMode(next) {
    mode = next === "talk" ? "talk" : "find";
    if (!modes) return;
    Array.prototype.forEach.call(modes.querySelectorAll(".segment"), function (button) {
      button.setAttribute("aria-pressed", button.getAttribute("data-mode") === mode ? "true" : "false");
    });
    if (field) field.placeholder = mode === "talk" ? "Write in Hebrew, or in English" : "Ask targum";
    if (mic) mic.hidden = !(mode === "talk" && canRecord);
  }
  if (modes) {
    modes.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest(".segment") : null;
      if (button) setMode(button.getAttribute("data-mode"));
    });
  }

  function drawHours(got) {
    if (!hoursLine || !got) return;
    if (got.allowed === null || got.allowed === undefined) {
      hoursLine.hidden = true;
      return;
    }
    hoursLine.textContent = got.used + " of " + got.allowed + " hours this month";
    hoursLine.hidden = false;
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

  // The Hebrew mode's own shape: a Hebrew line, then "= " and its English; "> " marks a
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

  function render(target, text) {
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
        he.textContent = p.he;
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

  /* --- a quote ------------------------------------------------------------- */

  // What a build will take, in the only currency the reader spends: their time. The
  // same arithmetic as the Add page's, because two answers to one question would
  // disagree. What it costs us is our business and never theirs.
  function wait(job) {
    if (job.audio && job.parts > 0) {
      var spoken = job.seconds / job.parts / 60;
      var listening = Math.max(1, Math.round(spoken / 6));
      var translating = Math.max(1, Math.round((job.total || 25) / 25));
      var minutes = listening + translating;
      var opener = job.parts > 1 ? "First part in " : "Ready in ";
      if (minutes <= 1) return opener + "about a minute.";
      if (minutes <= 4) return opener + "a few minutes.";
      return opener + "about " + minutes + " minutes.";
    }
    if (!job.estimate) return "Ready in a moment.";
    var mins = Math.max(1, Math.round((job.total || job.segments) / 25));
    var start = job.chapters > 1 ? "First chapter in " : "";
    if (mins <= 1) return start ? start + "about a minute." : "About a minute.";
    if (mins <= 4) return start ? start + "a couple of minutes." : "A couple of minutes.";
    return start + "about " + mins + " minutes.";
  }

  function hours(seconds) {
    var h = seconds / 3600;
    if (h < 1) return Math.max(1, Math.round(seconds / 60)) + " minutes of audio";
    return (Math.round(h * 10) / 10) + " hours of audio";
  }

  // The card the reader presses. Drawn from the quote itself — the server's state of
  // the job — never from what the model wrote about it. The button posts to /build,
  // the same door the Add page's button posts to: the press is the spend, and nothing
  // the model holds can make it.
  function quoteCard(li, job) {
    var card = document.createElement("div");
    card.className = "quote";
    card.setAttribute("data-job", job.id);
    var title = document.createElement("p");
    title.className = "quote-title";
    var he = document.createElement("bdi");
    var language = job.language || "he";
    he.setAttribute("lang", language);
    he.setAttribute("dir", language === "he" ? "rtl" : "ltr");
    he.textContent = job.title || "";
    title.appendChild(he);
    if (job.english) {
      var en = document.createElement("span");
      en.className = "quote-english";
      en.textContent = job.english;
      title.appendChild(en);
    }
    card.appendChild(title);
    var meta = document.createElement("p");
    meta.className = "quote-meta";
    var facts = [];
    if (job.audio) facts.push(hours(job.seconds || 0));
    else if (job.chapters > 1) facts.push(job.chapters + " chapters");
    else if (job.segments) facts.push(job.segments + " sentences");
    if (job.stage === "ready") facts.push(wait(job));
    meta.textContent = facts.join(" · ");
    card.appendChild(meta);
    var note = document.createElement("p");
    note.className = "quote-note";
    if (job.stage === "ready") {
      var go = document.createElement("button");
      go.type = "button";
      go.className = "quote-go";
      go.textContent = "Read this";
      go.onclick = function () {
        go.disabled = true;
        ask("/build", { id: job.id }).then(function (state) {
          if (state.error || state.blocked) {
            note.textContent = state.error || state.blocked;
            card.classList.add("refused");
            return;
          }
          note.textContent = "Building. It will appear above when it is ready.";
          card.classList.add("started");
          if (window.TargumBuilding && window.TargumBuilding.ask) window.TargumBuilding.ask();
        });
      };
      card.appendChild(go);
    } else {
      note.textContent = job.blocked || job.error || "This cannot be built now.";
      card.classList.add("refused");
    }
    card.appendChild(note);
    li.appendChild(card);
    return card;
  }

  /* --- speaking and hearing -------------------------------------------------- */

  var recorder = null;
  var recorded = [];

  // One press starts, the next stops. The clip goes up as itself, is written down by
  // the same transcriber a recording gets, and comes back as the reader's line.
  function toggleRecording() {
    if (!canRecord || busy) return;
    if (recorder) {
      recorder.stop();
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(
      function (stream) {
        recorded = [];
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = function (event) {
          if (event.data && event.data.size) recorded.push(event.data);
        };
        recorder.onstop = function () {
          stream.getTracks().forEach(function (track) {
            track.stop();
          });
          var clip = new Blob(recorded, { type: recorder.mimeType || "audio/webm" });
          recorder = null;
          mic.setAttribute("aria-pressed", "false");
          mic.textContent = "Speak";
          hear(clip);
        };
        recorder.start();
        mic.setAttribute("aria-pressed", "true");
        mic.textContent = "Stop";
      },
      function () {
        tell("The microphone could not be opened.");
      }
    );
  }

  function hear(clip) {
    busy = true;
    send.disabled = true;
    var pending = turn("user", "…", "working");
    var path = "/chat/hear?chat=" + encodeURIComponent(current) + "&mode=" + mode;
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
    if (mode !== "talk" || li.querySelector(".chat-play")) return;
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

  function turn(role, text, state) {
    var li = document.createElement("li");
    li.className = "chat-turn " + (role === "user" ? "me" : "them") + (state ? " " + state : "");
    var who = document.createElement("span");
    who.className = "chat-who";
    who.textContent = role === "user" ? "You" : "targum";
    var line = document.createElement("p");
    line.className = "chat-line";
    render(line, text);
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

  /* --- loading ------------------------------------------------------------- */

  function load() {
    return ask("/chat/list").then(function (answer) {
      if (answer.error) return tell(answer.error);
      chats = answer.chats || [];
      usable = answer.usable !== false;
      drawHours(answer.hours);
      if (!usable) tell("Nothing can be asked now. Everything you have still opens.");
      drawList();
      if (!current && chats.length) return open(chats[0].id);
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
      setMode(answer.chat && answer.chat.mode);
      var pending = null;
      var lastAsked = 0;
      (answer.turns || []).forEach(function (t) {
        if (t.role === "user") {
          turn("user", t.said);
          lastAsked = t.n;
          pending = t.stage === "working" ? t.n : null;
          if (t.stage === "failed" && t.error) turn("assistant", t.error, "bad");
        } else if (t.said) {
          playButton(turn("assistant", t.said), id, lastAsked);
        }
      });
      if (empty) empty.hidden = true;
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

  function say(text) {
    if (busy || !text) return;
    if (!usable) return tell("Nothing can be asked now. Everything you have still opens.");
    busy = true;
    send.disabled = true;
    turn("user", text);
    var answer = turn("assistant", "", "working");
    ask("/chat/say", { chat: current, text: text, mode: mode }).then(function (got) {
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
    function finish(kind, payload) {
      li.className = "chat-turn them" + (kind === "error" ? " bad" : "");
      render(line, kind === "error" ? payload.message : payload.text || text);
      if (kind !== "error") playButton(li, chat, n);
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
        render(line, text);
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
    var text = field.value.trim();
    if (!text) return;
    field.value = "";
    say(text);
  });
  field.addEventListener("keydown", function (event) {
    // Enter sends, Shift+Enter breaks the line — the convention every chat shares.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      var text = field.value.trim();
      if (!text) return;
      field.value = "";
      say(text);
    }
  });
  if (fresh) fresh.onclick = startNew;
  if (mic) mic.onclick = toggleRecording;

  // The page opens finding, with the microphone put away: said by the script and not
  // left to the template, so the two cannot disagree about what a fresh page shows.
  setMode("find");
  load();

  window.TargumChat = { say: say, open: open, render: render, quoteCard: quoteCard, pairs: pairs, hear: hear };
})();
