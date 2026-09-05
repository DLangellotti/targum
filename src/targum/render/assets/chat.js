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

  function render(target, text) {
    target.textContent = "";
    var pieces = String(text || "").split(PATH);
    // split with two groups yields [before, sep, path, before, sep, path, ...]
    for (var i = 0; i < pieces.length; i++) {
      var piece = pieces[i];
      if (piece === undefined) continue;
      if (i % 3 === 2) {
        var a = document.createElement("a");
        a.href = keyed(piece);
        a.textContent = piece;
        target.appendChild(a);
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

  function turn(role, text, state) {
    var li = document.createElement("li");
    li.className = "turn " + (role === "user" ? "me" : "them") + (state ? " " + state : "");
    var who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "user" ? "You" : "targum";
    var line = document.createElement("p");
    line.className = "line";
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
      var pending = null;
      (answer.turns || []).forEach(function (t) {
        if (t.role === "user") {
          turn("user", t.said);
          pending = t.stage === "working" ? t.n : null;
          if (t.stage === "failed" && t.error) turn("assistant", t.error, "bad");
        } else if (t.said) {
          turn("assistant", t.said);
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
    ask("/chat/say", { chat: current, text: text }).then(function (got) {
      if (got.error) {
        answer.className = "turn them bad";
        render(answer.querySelector(".line"), got.error);
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
    var line = li.querySelector(".line");
    var text = "";
    function finish(kind, payload) {
      li.className = "turn them" + (kind === "error" ? " bad" : "");
      render(line, kind === "error" ? payload.message : payload.text || text);
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

  load();

  window.TargumChat = { say: say, open: open, render: render };
})();
