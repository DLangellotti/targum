/* The profile page: who you are, and the two things that end an account.
 *
 * The corner popover answers "who is signed in" in one line. This is the rest — a name,
 * and the half of an account that is slow or impossible to undo.
 *
 * Reading preferences stay in the reader, in that browser. Carrying them to the account
 * was built and taken out again: it is a second place for the same setting to live, and
 * two places disagreeing is worse than one place forgetting.
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

  var panels = ["who", "reading", "ending"];

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
        if (answer.error) return say("you-said", answer.error);
        say("you-said", "Saved.");
        drawWho(answer);
        // The corner draws from /account/me, so asking sync to look again is what makes
        // the initials in it agree with the name just typed.
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
