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

  /* Words said through the page's `TargumStrings`, looked up when a thing is said: this
     file runs before the page has handed its strings over. Where there are none, the
     English here (targum-internal#184). */
  function t(key, english, fill) {
    var said = window.TargumStrings;
    if (said) return said.t(key, english, fill);
    return english.replace(/\{(\w+)\}/g, function (all, name) {
      return fill && Object.prototype.hasOwnProperty.call(fill, name) ? String(fill[name]) : all;
    });
  }
  function tn(key, count, one, other, fill) {
    var said = window.TargumStrings;
    if (said) return said.tn(key, count, one, other, fill);
    var values = { n: count };
    for (var name in fill || {}) values[name] = fill[name];
    return t(key, count === 1 ? one : other, values);
  }

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

  function say(message, showing, bad) {
    if (window.TargumFault && field) window.TargumFault.clear(field);
    said.hidden = !message;
    said.textContent = message || "";
    said.classList.toggle("bad", !!bad);
    if (showing) show(true);
    // A refusal about the address is said under its field, which keeps the focus
    // (design.md §12, 2026-10-09); it was a clay line under the form.
    if (bad && message && window.TargumFault && field && !signedOut.hidden && !panel.hidden) {
      said.hidden = true;
      window.TargumFault.field(field, message);
    }
  }

  function show(showing) {
    panel.hidden = !showing;
    open.setAttribute("aria-expanded", showing ? "true" : "false");
    open.classList.toggle("on", showing);
    if (showing && !signedOut.hidden && field) field.focus();
  }

  /* The initials this browser was last signed in with, so the corner says who you are
     from the first paint rather than "Sign in" until sync has asked, which read as being
     signed out on every page of the live site (2026-09-27). Initials only; forgotten the
     moment sync says nobody is here. */
  var HELD = "targum:initials";

  function avatar(initials) {
    open.className = "avatar";
    open.setAttribute("aria-label", t("account.yours", "Your account"));
    open.appendChild(document.createTextNode(initials || "?"));
  }

  try {
    var held = localStorage.getItem(HELD);
    if (held) {
      open.textContent = "";
      avatar(held);
    }
  } catch (e) {
    // Nowhere to read it from: "Sign in" until sync answers, as before.
  }

  function draw(who) {
    signedOut.hidden = !!who;
    signedIn.hidden = !who;
    open.textContent = "";
    if (!who) {
      if (window.targumForget) window.targumForget(HELD);
      open.removeAttribute("aria-label");
      open.className = "";
      open.textContent = t("account.sign-in", "Sign in");
      open.title = t("account.sign-in", "Sign in");
      drawHours(null);
      return;
    }

    // The address is nobody else's business on a shared screen, and it never fitted the
    // corner anyway. Two letters do, and they are the same two whatever the window.
    open.title = who.name ? who.name + " — " + who.email : who.email;
    // Named for what it opens: its text is two initials, and "D" is not a name for a
    // button to a screen reader (2026-09-14).
    if (window.targumKeep) window.targumKeep(HELD, who.initials || "?");
    if (who.picture) {
      var image = new Image();
      image.alt = "";
      image.onload = function () {
        open.textContent = "";
        open.appendChild(image);
      };
      image.src = who.picture;
    }
    avatar(who.initials);
    whom.textContent = who.name ? who.name + " · " + who.email : who.email;
    drawHours(who.hours);
  }

  // The month's credits, in the panel and — where the page has the line — on the
  // account page's Credits panel: the real count, off the chat page where it stood in
  // every reader's face on every visit (2026-09-10, targum-internal#237), and off Your
  // Progress since it became a story (design.md §12, 2026-10-09). Nothing where there is
  // no cap.
  var hoursLine = document.getElementById("account-hours");
  var ledgerLine = document.getElementById("hours-line");
  var creditsPanel = document.getElementById("credits");
  // "50 minutes", "1 hour 5 minutes", "3 hours": the hours as a person says them. "0.83
  // of 8 hours" was a decimal nobody reads as fifty minutes (2026-09-14).
  function spoken(hours) {
    var minutes = Math.round((Number(hours) || 0) * 60);
    var whole = Math.floor(minutes / 60);
    var rest = minutes % 60;
    var parts = [];
    if (whole) parts.push(tn("account.hours", whole, "{n} hour", "{n} hours"));
    if (rest || !whole) parts.push(tn("account.minutes", rest, "{n} minute", "{n} minutes"));
    return parts.join(" ");
  }
  /* A balance is credits, and one credit is one minute of audio or video (design.md §12,
     2026-09-23). **The rate is shown wherever the balance is**: a credit a reader has to
     convert from memory is the invented currency §6 forbids, and a credit with its
     equivalence beside it is a minute with a better name. This says what is left rather
     than what is gone, because "is that a lot?" is the question a balance is asked and
     what remains is the answer. */
  function credits(hours) {
    return Math.round((Number(hours) || 0) * 60);
  }
  function drawHours(got) {
    var has = got && got.allowed !== null && got.allowed !== undefined;
    var spare = has ? Math.max(0, (Number(got.allowed) || 0) - (Number(got.used) || 0)) : 0;
    var said = has
      ? tn(
          "account.credits.left",
          credits(spare),
          "{n} credit left this month",
          "{n} credits left this month"
        ) +
        " — " +
        t("account.credits.rate", "about {clock} of audio", { clock: spoken(spare) })
      : "";
    if (hoursLine) {
      hoursLine.textContent = said;
      hoursLine.hidden = !has;
    }
    if (ledgerLine) {
      ledgerLine.textContent = said
        ? said + (got.ends ? " · " + t("account.hours.resets", "resets {date}", { date: got.ends }) : "")
        : "";
      ledgerLine.hidden = !has;
    }
    if (creditsPanel) creditsPanel.hidden = !has;
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
    say(t("account.sending", "We're sending your link…"));
    window.TargumSync.signIn(field.value)
      .then(function (answer) {
        if (answer.error && !answer.message) return say(answer.error, false, true);
        say(
          answer.sent
            ? t("account.sent", "Thanks. We've sent a link to {address}.", { address: field.value })
            : answer.message || t("account.check-email", "Thanks. Check your email.")
        );
        if (answer.sent) form.hidden = true;
      })
      .catch(function () {
        say(t("account.could-not-send", "We couldn't send the link. Try again in a minute."), false, true);
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
  // load. Until then the button says what this browser last knew (`HELD`, above).
  window.TargumSync.onChange(function () {
    draw(window.TargumSync.who);
  });

  // A link that has just been used, or one that had expired. Said on the page it lands
  // on rather than on a page of its own.
  var arrived = new URLSearchParams(location.search).get("signin");
  if (arrived === "welcome") say(t("account.welcome", "You're signed in."), true);
  if (arrived === "expired") {
    say(t("account.expired", "This link has expired. Enter your email and we'll send a new one."), true, true);
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
