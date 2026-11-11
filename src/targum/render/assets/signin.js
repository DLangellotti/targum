/* The sign-in form, posted without leaving the page.

   The form works without this: it is a real <form> with a real action, so a browser
   with no JavaScript still signs in. This only replaces the page reload with a
   sentence, because "check your email" belongs next to the field you just filled in. */
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
  /* The page a mailed link opens carries the language the link was asked for in, and
     keeps it the way the form below does: as what this browser reads into, which the
     arrival then hands to the new account. A link asked for in Russian and opened on a
     phone that never saw the form would otherwise ask its questions in English (arrival
     QA, 2026-10-18). Only where this browser has not already said. */
  var entering = document.querySelector("form.enter[data-asked]");
  if (entering) {
    try {
      if (!localStorage.getItem("targum:into")) {
        localStorage.setItem("targum:into", entering.getAttribute("data-asked"));
      }
    } catch (e) {
      /* nowhere to keep it; the page itself is still in it */
    }
  }

  var form = document.getElementById("ask");
  var said = document.getElementById("sent");
  if (!form || !said) return;

  /* The status line is the last thing in the page, which put it under the footnote
     rather than where the form was: hiding the form left "Signed in, your words follow
     you between browsers." sitting above "Check your email.", promising a state the
     reader is not in yet. Moved to just after the form, it takes the form's place on
     success and sits under the button on an error, which is where each belongs. */
  form.parentNode.insertBefore(said, form.nextSibling);

  // What this browser reads into, so the link arrives in that language (targum-internal#186).
  function into() {
    try {
      return localStorage.getItem("targum:into") || "";
    } catch (e) {
      return "";
    }
  }

  /* The language pressed on the front door, carried here on the link (2026-09-20). It was
     a press, so it is kept the way any other is: as what this browser reads into, which
     the sign-in email is then written in and which Learn hands to the new account — so
     somebody who chose Russian before they had an account is not asked again after.
     Only where this browser has not already said; a press on a landing page does not
     overrule a choice made inside the product. */
  var asked = form.getAttribute("data-asked") || "";
  function carried() {
    var held = into();
    if (held || !asked) return held;
    try {
      localStorage.setItem("targum:into", asked);
    } catch (e) {
      /* nowhere to keep it; the email still arrives in it */
    }
    return asked;
  }

  /* What to do once the link has gone (design.md §14, line 1: every state says what to do
     next). The mail is the next step, so it is named; and an address typed wrong is the
     likeliest reason no mail comes, so the way back to the field is a press beside it
     rather than a reload somebody has to think of. */
  var next = null;
  function sentNext(field, button) {
    if (!next) {
      next = document.createElement("div");
      next.className = "sent-next";
      var line = document.createElement("p");
      line.className = "said";
      line.textContent = t("signin.sent.open", "Open it to sign in. It works once, for 20 minutes.");
      var again = document.createElement("button");
      again.type = "button";
      again.className = "sent-again";
      again.textContent = t("signin.sent.another", "Use another address");
      again.addEventListener("click", function () {
        next.hidden = true;
        said.hidden = true;
        form.hidden = false;
        button.disabled = false;
        field.focus();
        field.select();
      });
      next.appendChild(line);
      next.appendChild(again);
      said.parentNode.insertBefore(next, said.nextSibling);
    }
    next.hidden = false;
  }

  /* The refusal's "Join the waitlist", as a link (beta review PUB-05, 2026-11-03). The
     server names the words to wrap, in the sentence's own language, and where the
     waitlist is; where the words are not found in the line, the link follows it. */
  function joinLink(line, body) {
    if (!line || !body || !body.join || !body.join_link) return;
    var link = document.createElement("a");
    link.href = body.join;
    link.className = "join-link";
    link.textContent = body.join_link;
    var walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT, null);
    for (var node = walker.nextNode(); node; node = walker.nextNode()) {
      var at = node.nodeValue.indexOf(body.join_link);
      if (at < 0) continue;
      var rest = node.splitText(at);
      rest.nodeValue = rest.nodeValue.slice(body.join_link.length);
      rest.parentNode.insertBefore(link, rest);
      return;
    }
    line.appendChild(document.createTextNode(" "));
    line.appendChild(link);
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var field = form.querySelector('input[type="email"]');
    var button = form.querySelector("button");
    if (!field || !field.value) return;
    button.disabled = true;
    said.hidden = true;
    said.classList.remove("bad", "fault-marked");
    var fault = window.TargumFault;
    if (fault) fault.clear(field);
    /* Past three seconds the wait is said (design.md §14, line 1): a pressed button that
       only greys out looks like one that did nothing, and gets pressed again. */
    var slow = window.setTimeout(function () {
      said.hidden = false;
      said.textContent = t("signin.still-sending", "We're still sending your link.");
    }, 3000);

    fetch("/account/sign-in", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // The room a signed-out reader was turned away from, so the mailed link lands
      // back in it (QA 2026-10-11, D2). The server checks it again; this only carries it.
      body: JSON.stringify({ email: field.value, into: carried(), next: form.getAttribute("data-next") || "" }),
    })
      .then(function (response) {
        /* An answer that is not ours: a 502 from the proxy while targum restarts is a
           page of HTML, and reading it as JSON threw into the catch below, which told a
           server's fault as the connection's ("We can't reach targum"; design's #477
           pass, 2026-11-10). targum was reached; it couldn't send. */
        return response.json().then(
          function (body) {
            body = body || {};
            /* Any 5xx is the server's fault, not the address's, whatever it says:
               targum's own 502 when the mailer fails carries an `error`, and that sent
               it under the field with the clay outline as if the address were wrong
               (#677, #681). Its sentence is still the one said, on the form's line. */
            if (response.status >= 500) return { ok: false, body: body, serverFault: true };
            return { ok: response.ok, body: body };
          },
          function () {
            return { ok: false, body: {}, serverFault: true };
          }
        );
      })
      .then(function (answer) {
        window.clearTimeout(slow);
        said.hidden = false;
        if (answer.serverFault) {
          // Not about the address, so not under its field: a line with the clay mark
          // where the form's answer goes, and the press is still there to try again with.
          button.disabled = false;
          said.classList.add("bad", "fault-marked");
          said.textContent =
            answer.body.error || t("signin.server-fault", "We couldn't send a link just now. Try again.");
          /* The press went grey while it waited, which dropped the keyboard to the page;
             it goes back to the press, which is the way to try again. Never taken from
             anything the reader moved on to meanwhile. The line itself is a status, so
             it is read out where it stands. */
          var on = document.activeElement;
          if (!on || on === document.body || on === document.documentElement) button.focus();
          return;
        }
        if (answer.ok) {
          // Thanked, and told where the link went. The server says the same thing for
          // every address, so naming the one just typed confirms nothing about it.
          said.textContent = t("account.sent", "Thanks. We've sent a link to {address}.", { address: field.value });
          sentNext(field, button);
          form.hidden = true;
          return;
        }
        button.disabled = false;
        var why = answer.body.error || t("account.could-not-send", "We couldn't send the link. Try again in a minute.");
        // About the address that was typed, so under its field, which keeps the focus
        // (design.md §12, 2026-10-09).
        if (fault) {
          said.hidden = true;
          joinLink(fault.field(field, why), answer.body);
          return;
        }
        said.classList.add("bad");
        said.textContent = why;
        joinLink(said, answer.body);
      })
      .catch(function () {
        window.clearTimeout(slow);
        said.hidden = true;
        button.disabled = false;
        // The connection's banner, whose Try again sends the form again.
        if (fault) {
          fault.unreachable(function () {
            button.click();
          });
          return;
        }
        said.hidden = false;
        said.classList.add("bad");
        said.textContent = t("signin.unreachable", "We can't reach targum.");
      });
  });
})();
