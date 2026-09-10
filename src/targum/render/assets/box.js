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
  var file = document.getElementById("chat-file");
  var heldList = document.getElementById("chat-held");
  var said = document.getElementById("chat-said");
  var hoursLine = document.getElementById("chat-hours");
  if (!form || !field || !send) return;
  // The conversation page carries the same box and its own script for it; this one
  // stands down there rather than answering the same press twice.
  if (window.TargumChat) return;

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
  // the page is one page whatever it is showing. A text sent with a line that says
  // more than "open this" rides the same way, as `job=<id>`, and the page draws its
  // card as a turn in that conversation.
  function go(chat, job) {
    var hash = chat ? encodeURIComponent(chat) : "";
    if (job) hash += (hash ? "&" : "") + "job=" + encodeURIComponent(job);
    window.location.href = keyed("/chat") + "#" + hash;
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
    if (held.length) return bringHeld(text);
    if (!text) return;
    say(text);
  });
  field.addEventListener("keydown", function (event) {
    // Enter sends, Shift+Enter breaks the line — the convention every chat shares.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      var text = field.value.trim();
      if (held.length) return bringHeld(text);
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

  // A file chosen by the + is held in the box until Send, the way a line is typed
  // and then sent (2026-09-07): choosing is not bringing. Send with a file means open
  // it: the file goes up, is priced and built, the strip in the header carries the
  // build, and the reader opens when it is ready. No conversation is started for a
  // bare file or a line that only says "open this" — "when I wrote 'open this' with
  // a file, I didn't want that to be the start of a conversation." A line that says
  // more is a specification: it is said, with a note of what was sent, and the
  // conversation page opens on it with the card as a turn.
  var bringing = window.TargumBring;
  var held = [];
  function showHeld() {
    if (bringing && heldList) {
      bringing.held(heldList, held, function (index) {
        held.splice(index, 1);
        showHeld();
      });
    }
  }
  function bringHeld(text) {
    if (busy || !bringing || !held.length) return;
    var spec = bringing.justOpen(text) ? "" : text;
    busy = true;
    send.disabled = true;
    tell("Uploading…");
    var into = window.TargumLang ? window.TargumLang.into() || "en" : "en";
    bringing
      .bring(held, { to: into }, function (share) {
        tell("Uploading… " + share + "%");
      })
      .then(function (job) {
        tell("");
        if (job.reader) {
          // The same bytes were already brought: the text is the answer.
          window.location.href = bringing.door(job.reader);
          return;
        }
        if (job.error) return refused(job);
        if (job.stage !== "ready") return refused({ error: job.blocked || job.error });
        // Send with a file in the box is the press: the reader chose the file and
        // sent it, and a card asking them to say so again was a second surface
        // ("I originally just gave the file… it should have been enough to just
        // open it", 2026-09-07). Started here, followed to its end, and opened.
        return bringing.start(job).then(function (state) {
          if (state.error || state.blocked) return refused({ error: state.error || state.blocked });
          held = [];
          showHeld();
          if (spec) {
            // Said with the note of what was sent; the card follows it as a turn.
            return ask("/chat/say", { chat: "", text: spec, brought: job.id }).then(function (got) {
              if (got.error) return refused(got);
              go(got.chat, job.id);
            });
          }
          tell("Building. It will open when it is ready.");
          if (window.TargumBuilding && window.TargumBuilding.ask) window.TargumBuilding.ask();
          return bringing.follow(job.id).then(function (done) {
            if (done.stage === "done" && done.reader) {
              window.location.href = bringing.door(done.reader);
              return;
            }
            refused({ error: done.error || "That did not build. The strip above has the detail." });
          });
        });
      })
      .catch(function (why) {
        refused({ error: String(why || "That did not go through. Try again.") });
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

  showMic();
  ask("/chat/list").then(function (answer) {
    if (answer.error) return;
    usable = answer.usable !== false;
    talk = answer.talk !== false;
    showMic();
    // The month's hours, only when they are nearly gone (targum-internal#237).
    if (hoursLine && bringing) {
      var line = bringing.hoursWarning(answer.hours);
      hoursLine.textContent = line;
      hoursLine.hidden = !line;
    }
  });

  window.TargumBox = { say: say, hear: hear, bring: bringHeld };
})();
