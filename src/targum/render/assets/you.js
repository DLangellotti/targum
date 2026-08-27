/* The profile page: who you are, your languages, and the two things that end an account.
 *
 * The corner popover answers "who is signed in" in one line. This is the rest — a name,
 * which languages you are learning and which you read into, and the half of an account
 * that is slow or impossible to undo.
 *
 * The languages live on the account and nowhere else. A preference in the browser is
 * swept on sign-out with everything else `targum:*`, on purpose, and would be forgotten
 * every time somebody signed out on their own machine; `sync.js` keeps a copy of the
 * account's answer the way it keeps a copy of the words, and that copy is a cache, not a
 * second setting. What the reader is looking at right now — which switcher is pressed —
 * is a different question and stays in the browser.
 */

(function () {
  "use strict";

  var key = window.TARGUM_KEY;

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: key
        ? { "Content-Type": "application/json", "X-Targum-Key": key }
        : { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  var panels = ["who", "languages", "reading", "ending"];

  function at(id) {
    return document.getElementById(id);
  }

  function show(signedIn) {
    at("stranger").hidden = signedIn;
    panels.forEach(function (name) {
      at(name).hidden = !signedIn;
    });
  }

  function say(where, message) {
    var node = at(where);
    node.hidden = !message;
    node.textContent = message || "";
  }

  /* --- who you are ----------------------------------------------------------- */

  function drawWho(who) {
    var avatar = at("you-avatar");
    avatar.textContent = "";
    if (who.picture) {
      var image = new Image();
      image.alt = "";
      image.onload = function () {
        avatar.textContent = "";
        avatar.appendChild(image);
      };
      image.src = who.picture;
    }
    avatar.appendChild(document.createTextNode(who.initials || "?"));
    at("you-email").textContent = who.email || "";
    at("you-name").value = who.name || "";

    var counts = who.counts || {};
    var kept = (counts.words || 0) + " words, " + (counts.phrases || 0) + " phrases";
    at("you-kept").textContent = kept;
  }

  var saving = null;

  function saveName() {
    // On the way out of the field, and once: a request per keystroke would be a request
    // per keystroke.
    clearTimeout(saving);
    saving = setTimeout(function () {
      ask("/account/name", { name: at("you-name").value }).then(function (answer) {
        // A session that ended while the page was open answers `signedIn: false` with no
        // error in it, and that is not "Saved."
        if (answer.error || answer.signedIn === false) {
          return say("you-said", answer.error || "Sign in again.");
        }
        say("you-said", "Saved.");
        drawWho(answer);
        // The corner draws from /account/me, so asking sync to look again is what makes
        // the initials in it agree with the name just typed.
        if (window.TargumSync) window.TargumSync.start();
      });
    }, 400);
  }

  /* --- your languages ---------------------------------------------------------- */

  // Every language targum has, drawn from the lists the page was built with, and ticked
  // from what the account said. The boxes are kept here rather than found again: the
  // question is only ever "which of these are ticked", and this is the list.
  var boxes = { "you-learning": [], "you-reads": [] };

  function ticked(id) {
    return boxes[id]
      .filter(function (box) {
        return box.checked;
      })
      .map(function (box) {
        return box.value;
      });
  }

  function drawTicks(id, rows, chosen, required) {
    var host = at(id);
    host.textContent = "";
    boxes[id] = [];
    rows.forEach(function (row) {
      var label = document.createElement("label");
      label.className = "tick";
      var box = document.createElement("input");
      box.type = "checkbox";
      box.value = row.code;
      box.checked = chosen.indexOf(row.code) >= 0;
      // The one that stays on is drawn on and cannot be pressed off. The server holds
      // the same line, so this is not the only thing keeping it there.
      box.disabled = required.indexOf(row.code) >= 0;
      box.addEventListener("change", function () {
        tickChanged(id, box);
      });
      label.appendChild(box);
      label.appendChild(document.createTextNode(row.name));
      if (row.stage !== "alpha") {
        var mark = document.createElement("span");
        mark.className = "beta";
        mark.textContent = "experimental";
        label.appendChild(mark);
      }
      host.appendChild(label);
      boxes[id].push(box);
    });
  }

  function drawLanguages(who) {
    drawTicks(
      "you-learning",
      window.TARGUM_READING || [],
      who.learning || ["he"],
      window.TARGUM_REQUIRED || []
    );
    drawTicks("you-reads", window.TARGUM_INTO || [], who.reads || ["en"], []);
  }

  function tickChanged(id, box) {
    if (!box.checked && !ticked(id).length) {
      // The last one cannot go: a reader with no language to read into has no reader.
      // Put back here rather than sent, so the box never shows a state the account
      // would refuse.
      box.checked = true;
      return say("you-languages-said", "Keep at least one.");
    }
    saveLanguages();
  }

  var savingLanguages = null;

  function saveLanguages() {
    // Once, a moment after the last tick: two boxes pressed together are one change.
    clearTimeout(savingLanguages);
    savingLanguages = setTimeout(function () {
      ask("/account/languages", {
        learning: ticked("you-learning"),
        reads: ticked("you-reads"),
      }).then(function (answer) {
        // Ticked back from the answer either way. What the account kept is what stands,
        // and a refused change puts its boxes back rather than showing what was asked.
        if (answer.learning || answer.reads) drawLanguages(answer);
        if (answer.error || answer.signedIn === false) {
          return say("you-languages-said", answer.error || "Sign in again.");
        }
        say("you-languages-said", "Saved.");
        // The pages that offer a language read the account's answer through sync, so
        // asking it to look again is what makes them agree with the boxes.
        if (window.TargumSync) window.TargumSync.start();
      });
    }, 400);
  }

  /* --- ending it -------------------------------------------------------------- */

  function ending() {
    at("you-export").href = keyed("/account/export");
    at("you-out").addEventListener("click", function () {
      // Through sync, not straight at the endpoint: signing out empties this browser's
      // store as well as ending the session, and only sync knows how to do both.
      window.TargumSync.signOut().then(function () {
        location.href = keyed("/");
      });
    });
    at("you-forget").addEventListener("click", function () {
      var press = at("you-forget");
      if (press.getAttribute("data-sure") !== "yes") {
        // Asked twice, in the button itself. A dialog for this would be a dialog nobody
        // reads; a button that changes what it says is read by everybody who presses it.
        press.setAttribute("data-sure", "yes");
        press.textContent = "Delete for good?";
        return;
      }
      press.disabled = true;
      ask("/account/forget", {}).then(function (answer) {
        say("you-ending-said", answer.message || "Your account is closing.");
      });
    });
  }

  /* --- putting it together ---------------------------------------------------- */

  ask("/account/me")
    .then(function (who) {
      show(!!who.signedIn);
      if (!who.signedIn) return;
      drawWho(who);
      drawLanguages(who);
      at("you-name").addEventListener("input", saveName);
      ending();
      if (window.TargumSync) window.TargumSync.start();
    })
    // A server that cannot be reached is a reader who is not signed in as far as this
    // page can tell, and saying so is the whole of what it can do. Without this the
    // request failed, nothing was shown, and the page sat blank — not even the line that
    // tells somebody where to sign in.
    .catch(function () {
      show(false);
    });
})();
