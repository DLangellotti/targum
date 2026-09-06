/* The box on Learn: the front door, since 2026-09-06.
 *
 * One field under the ledger's own sentence. A line typed here opens a conversation and
 * goes to it — `POST /chat/say` with no conversation named, then the conversation page
 * with the new id in the hash, where `chat.js` picks the answer up as it streams. A line
 * spoken here goes the same way through `/chat/hear`. Nothing is answered on this page:
 * the conversation is one more surface of the product (design.md §9), not a widget on
 * the front of it.
 *
 * Speak shows only where the browser records and where the reader has modern Hebrew to
 * speak — `/chat/list` says which, with the same `talk` the conversation page reads —
 * and the box is quiet rather than half-working when nothing can be asked at all.
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

  var form = document.getElementById("composer");
  var field = document.getElementById("say");
  var send = document.getElementById("chat-send");
  var mic = document.getElementById("chat-mic");
  var bring = document.getElementById("chat-bring");
  var said = document.getElementById("chat-said");
  if (!form || !field || !send) return;
  // The conversation page carries the same box and its own script for it; this one
  // stands down there rather than answering the same press twice.
  if (window.TargumChat) return;

  if (bring) bring.href = keyed(bring.getAttribute("href"));

  var speak = window.TargumSpeak;
  var busy = false;
  var usable = true;
  var talk = true;

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

  function showMic() {
    if (mic) mic.hidden = !(speak && speak.can) || !talk;
  }

  // The conversation page, opened on the conversation this line began. The id rides
  // in the hash rather than the path: `/chat/<id>` is the conversation as JSON, and
  // the page is one page whatever it is showing.
  function go(chat) {
    window.location.href = keyed("/chat") + "#" + encodeURIComponent(chat);
  }

  function refused(got) {
    tell(got.error);
    busy = false;
    send.disabled = false;
  }

  function say(text) {
    if (busy || !text) return;
    if (!usable) return tell("Nothing can be asked now. Everything you have still opens.");
    busy = true;
    send.disabled = true;
    tell("");
    ask("/chat/say", { chat: "", text: text }).then(function (got) {
      if (got.error) return refused(got);
      go(got.chat);
    });
  }

  function hear(clip) {
    if (busy) return;
    busy = true;
    send.disabled = true;
    tell("");
    fetch(keyed("/chat/hear?chat="), {
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
        if (got.error) return refused(got);
        go(got.chat);
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = field.value.trim();
    if (!text) return;
    say(text);
  });
  field.addEventListener("keydown", function (event) {
    // Enter sends, Shift+Enter breaks the line — the convention every chat shares.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      var text = field.value.trim();
      if (!text) return;
      say(text);
    }
  });
  if (mic) {
    mic.onclick = function () {
      if (busy || !speak) return;
      speak.toggle(mic, hear, tell);
    };
  }

  showMic();
  ask("/chat/list").then(function (answer) {
    if (answer.error) return;
    usable = answer.usable !== false;
    talk = answer.talk !== false;
    showMic();
  });

  window.TargumBox = { say: say, hear: hear };
})();
