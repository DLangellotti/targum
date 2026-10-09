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

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var field = form.querySelector('input[type="email"]');
    var button = form.querySelector("button");
    if (!field || !field.value) return;
    button.disabled = true;
    said.hidden = true;
    said.classList.remove("bad");
    var fault = window.TargumFault;
    if (fault) fault.clear(field);

    fetch("/account/sign-in", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: field.value, into: carried() }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (answer) {
        said.hidden = false;
        if (answer.ok) {
          // Thanked, and told where the link went. The server says the same thing for
          // every address, so naming the one just typed confirms nothing about it.
          said.textContent = t("account.sent", "Thanks. We've sent a link to {address}.", { address: field.value });
          form.hidden = true;
          return;
        }
        button.disabled = false;
        var why = answer.body.error || t("account.could-not-send", "We couldn't send the link. Try again in a minute.");
        // About the address that was typed, so under its field, which keeps the focus
        // (design.md §12, 2026-10-09).
        if (fault) {
          said.hidden = true;
          fault.field(field, why);
          return;
        }
        said.classList.add("bad");
        said.textContent = why;
      })
      .catch(function () {
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
