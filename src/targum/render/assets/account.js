/* The account control in the corner, on every page that has a header.
 *
 * Everything it does is one of three things: say who is signed in, ask for an email
 * address, or sign out. The syncing itself is not here — that is `sync.js`, which runs
 * whether or not this panel is ever opened.
 *
 * The copy is deliberately about what the reader gets rather than what the software
 * does. Nobody signs in to "enable server-side persistence"; they sign in so the words
 * they kept on the sofa are there on the train.
 *
 * It used to count them back — "Keeping 214 words and 3 phrases for you." A reader who
 * has signed in does not need telling their words are still there every time they open
 * the corner, and the page they go to for counts already has better ones.
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

  function draw(who) {
    signedOut.hidden = !!who;
    signedIn.hidden = !who;
    open.textContent = "";
    if (!who) {
      open.className = "";
      open.textContent = "Sign in";
      open.title = "Sign in";
      return;
    }

    // The address is nobody else's business on a shared screen, and it never fitted the
    // corner anyway. Two letters do, and they are the same two whatever the window.
    open.className = "avatar";
    open.title = who.name ? who.name + " — " + who.email : who.email;
    if (who.picture) {
      var image = new Image();
      image.alt = "";
      image.onload = function () {
        open.textContent = "";
        open.appendChild(image);
      };
      image.src = who.picture;
    }
    open.appendChild(document.createTextNode(who.initials || "?"));
    whom.textContent = who.name ? who.name + " · " + who.email : who.email;
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
        say("That did not go through.");
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
  if (arrived === "welcome") say("Signed in.", true);
  if (arrived === "expired") {
    say("That link was used. Ask for another.", true);
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
