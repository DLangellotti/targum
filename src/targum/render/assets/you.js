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

  // The page's words in the reader's language, from `strings.js` (targum-internal#184).
  var t = window.TargumStrings.t;
  var tn = window.TargumStrings.tn;
  var SIGNED_OUT = t("you.signed-out", "You've been signed out. Sign in again.");
  var SAVED = t("you.saved", "Saved.");

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

  function say(where, message, bad) {
    var node = at(where);
    node.hidden = !message;
    node.textContent = message || "";
    // §4 gives errors to --clay. Without this an error and "Saved." were the same
    // sentence in the same ink, and the only way to tell them apart was to read them.
    node.classList.toggle("bad", !!bad);
  }

  function grouped(count) {
    return String(count).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
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
    var address = who.address || "";
    Array.prototype.forEach.call(document.querySelectorAll('input[name="address"]'), function (box) {
      box.checked = box.value === address;
    });

    var counts = who.counts || {};
    // Every language's, said so, and grouped: beside Your Progress's one language this
    // read as a different number for the same thing (2026-09-14).
    var words = counts.words || 0;
    var phrases = counts.phrases || 0;
    at("you-kept").textContent =
      t("you.kept", "{words} and {phrases}, across all your languages.", {
        words: tn("you.kept.words", words, "{n} word", "{n} words", { n: grouped(words) }),
        phrases: tn("you.kept.phrases", phrases, "{n} phrase", "{n} phrases", { n: grouped(phrases) }),
      });
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
          return say("you-said", answer.error || SIGNED_OUT, true);
        }
        say("you-said", SAVED);
        drawWho(answer);
        // The corner draws from /account/me, so asking sync to look again is what makes
        // the initials in it agree with the name just typed.
        if (window.TargumSync) window.TargumSync.start();
      });
    }, 400);
  }

  // How the conversation addresses them in Hebrew. Saved on the press, as a name is.
  function saveAddress(event) {
    var box = event && event.target;
    if (!box || box.name !== "address") return;
    ask("/account/address", { address: box.value }).then(function (answer) {
      if (answer.error || answer.signedIn === false) {
        return say("you-said", answer.error || SIGNED_OUT, true);
      }
      say("you-said", SAVED);
    });
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
      // And in its own name, where the menu knows it (2026-09-14).
      var own = window.TargumLang && window.TargumLang.native ? window.TargumLang.native(row.code) : null;
      if (own && own.textContent !== row.name) {
        label.appendChild(document.createTextNode(" "));
        label.appendChild(own);
      }
      // "Experimental" is said once, in the note under the lists, rather than six times
      // down them (2026-09-14).
      host.appendChild(label);
      boxes[id].push(box);
    });
  }

  /* What is recorded of a sitting, and the reader's two controls over it
     (targum-internal#127). Absent where the box keeps no such record. Erasing asks twice,
     the way leaving does: it cannot be put back. */
  function drawRecord(who) {
    var panel = at("record");
    var events = who && who.events;
    if (!panel || !events || !events.kept) return;
    panel.hidden = false;
    var toggle = at("record-switch");
    var erase = at("record-erase");
    var said = at("record-said");
    function tell(text) {
      said.textContent = text;
      said.hidden = !text;
    }
    function paint(on) {
      toggle.setAttribute("aria-pressed", on ? "true" : "false");
      toggle.textContent = on
        ? t("you.record.stop", "Stop recording")
        : t("you.record.start", "Start recording again");
    }
    paint(!!events.on);
    toggle.onclick = function () {
      var next = toggle.getAttribute("aria-pressed") !== "true";
      ask("/account/events", { collect: next }).then(function (answer) {
        var on = !!(answer && answer.events && answer.events.on);
        paint(on);
        tell(
          on
            ? t("you.record.started", "We're recording again from now.")
            : t("you.record.stopped", "Stopped. What's already recorded is still here until you erase it.")
        );
      });
    };
    erase.onclick = function () {
      if (erase.getAttribute("data-sure") !== "yes") {
        erase.setAttribute("data-sure", "yes");
        erase.textContent = t("you.record.sure", "Erase it for good");
        return;
      }
      ask("/account/events", { forget: true }).then(function () {
        erase.removeAttribute("data-sure");
        erase.textContent = t("you.page.record-erase", "Erase what's recorded");
        tell(t("you.record.erased", "Erased. Your words and your texts are untouched."));
      });
    };
  }

  /* Accepting the contribution grant (targum-internal#164, door 3), which is the whole
     of what decides whether a word's card offers a way to correct a meaning.

     Once, and not undone from here: a correction already offered stays under the terms
     it arrived with, and withdrawing means offering no more rather than unmaking what
     was given. So the control says what it does and then says it is done, instead of
     becoming a switch that implies the first half can be taken back. */
  function drawGrant(who) {
    var panel = at("correcting");
    var go = at("grant-go");
    var said = at("grant-said");
    if (!panel || !go) return;
    if (who && who.granted) {
      go.hidden = true;
      said.hidden = false;
      said.textContent = t("you.grant.done", "You've accepted the grant, so a word's card offers a correction.");
      return;
    }
    go.textContent = t("you.page.correcting-accept", "Accept and turn it on");
    go.onclick = function () {
      go.disabled = true;
      ask("/account/grant", {}).then(function (answer) {
        if (!(answer && answer.granted)) {
          go.disabled = false;
          return;
        }
        go.hidden = true;
        said.hidden = false;
        said.textContent = t("you.grant.thanks", "Thank you. A word's card now offers a correction.");
      });
    };
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
      return say("you-languages-said", t("you.keep-one", "Keep at least one."));
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
          return say("you-languages-said", answer.error || SIGNED_OUT);
        }
        say("you-languages-said", SAVED);
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
        // And a way back beside it (2026-09-14): the second question had no answer but
        // reloading the page.
        press.setAttribute("data-sure", "yes");
        press.textContent = t("you.forget.sure", "Delete my account and words");
        var keep = at("you-keep");
        if (keep) {
          keep.hidden = false;
          keep.onclick = function () {
            press.removeAttribute("data-sure");
            press.textContent = t("you.forget", "Delete account");
            keep.hidden = true;
          };
        }
        return;
      }
      press.disabled = true;
      var keeping = at("you-keep");
      if (keeping) keeping.hidden = true;
      ask("/account/forget", {})
        .then(function (answer) {
          say("you-ending-said", answer.message || t("you.closing", "We're closing your account."));
          // The words were left in this browser and the page went on showing the profile
          // (2026-09-14). Signed out here too, the way Sign out empties the browser.
          if (window.TargumSync && window.TargumSync.signOut) {
            window.TargumSync.signOut().then(function () {
              setTimeout(function () {
                location.href = keyed("/");
              }, 1500);
            });
          }
        })
        .catch(function () {
          press.disabled = false;
          say(
            "you-ending-said",
            t("you.forget.unreachable", "We couldn't reach targum, so nothing was deleted. Try again."),
            true
          );
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
      drawRecord(who);
      drawGrant(who);
      at("you-name").addEventListener("input", saveName);
      var address = at("you-address");
      if (address) address.addEventListener("change", saveAddress);
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
