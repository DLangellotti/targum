/* The account control in the corner, on every page that has a header.
 *
 * Everything it does is one of three things: say who is signed in, ask for an email
 * address, or sign out. The syncing itself is not here — that is `sync.js`, which runs
 * whether or not this panel is ever opened.
 *
 * The copy is deliberately about what the reader gets rather than what the software
 * does. Nobody signs in to "enable server-side persistence"; they sign in so the words
 * they kept on the sofa are there on the train.
 */

(function () {
  "use strict";

  var open = document.getElementById("account-open");
  if (!open || !window.TargumSync) return;

  var panel = document.getElementById("account-panel");
  var out = document.getElementById("account-out");
  var form = document.getElementById("account-form");
  var field = document.getElementById("account-email");
  var said = document.getElementById("account-said");
  var whom = document.getElementById("account-whom");
  var kept = document.getElementById("account-kept");
  var signedOut = panel.querySelector(".signed-out");
  var signedIn = panel.querySelector(".signed-in");

  function say(message, showing) {
    said.hidden = !message;
    said.textContent = message || "";
    if (showing) show(true);
  }

  function show(showing) {
    panel.hidden = !showing;
    open.setAttribute("aria-expanded", showing ? "true" : "false");
    open.classList.toggle("on", showing);
    if (showing && !signedOut.hidden && field) field.focus();
  }

  // A count is the honest version of "your data is safe": it says what is actually up
  // there, in the units the reader thinks in.
  function tally(counts) {
    if (!counts) return "";
    var parts = [];
    if (counts.words) parts.push(counts.words + (counts.words === 1 ? " word" : " words"));
    if (counts.phrases) {
      parts.push(counts.phrases + (counts.phrases === 1 ? " phrase" : " phrases"));
    }
    if (!parts.length) return "Nothing kept yet. Tap a word while reading and it lands here.";
    return "Keeping " + parts.join(" and ") + " for you.";
  }

  function draw(who) {
    signedOut.hidden = !!who;
    signedIn.hidden = !who;
    if (who) {
      open.textContent = who.email.split("@")[0];
      open.title = "Signed in as " + who.email;
      whom.textContent = who.email;
      kept.textContent = tally(who.counts);
    } else {
      open.textContent = "Sign in";
      open.title = "Sign in so your words follow you";
    }
  }

  open.addEventListener("click", function () {
    show(panel.hidden);
  });

  document.addEventListener("click", function (event) {
    if (panel.hidden) return;
    if (!panel.contains(event.target) && event.target !== open) show(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !panel.hidden) show(false);
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    say("Sending…");
    window.TargumSync.signIn(field.value)
      .then(function (answer) {
        say(answer.message || answer.error || "Check your email.");
        if (answer.sent) form.hidden = true;
      })
      .catch(function () {
        say("That did not go through. Try again in a moment.");
      });
  });

  out.addEventListener("click", function () {
    window.TargumSync.signOut().then(function () {
      draw(null);
      show(false);
      // Everything on this page was drawn from a store that has just been emptied, so
      // the page has to be drawn again rather than left showing what is no longer here.
      location.reload();
    });
  });

  // The panel says nothing until sync has been able to ask, which is a moment after
  // load. Until then the button reads "Sign in", which is the right thing to show to
  // the majority of visits and is not a lie during the ones where it is wrong.
  window.TargumSync.onChange(function () {
    draw(window.TargumSync.who);
  });

  // A link that has just been used, or one that had expired. Said on the page it lands
  // on rather than on a page of its own.
  var arrived = new URLSearchParams(location.search).get("signin");
  if (arrived === "welcome") say("You are signed in. Your words follow you from here.", true);
  if (arrived === "expired") {
    say("That link had already been used. Ask for another and it will work.", true);
  }
  if (arrived) {
    // Take it out of the address so a refresh does not say it again.
    try {
      var clean = new URL(location.href);
      clean.searchParams.delete("signin");
      history.replaceState(null, "", clean.toString());
    } catch (e) {}
  }
})();
