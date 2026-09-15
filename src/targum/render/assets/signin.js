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

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var field = form.querySelector('input[type="email"]');
    var button = form.querySelector("button");
    if (!field || !field.value) return;
    button.disabled = true;
    said.hidden = true;
    said.classList.remove("bad");

    fetch("/account/sign-in", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: field.value, into: into() }),
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
        said.classList.add("bad");
        said.textContent = answer.body.error || t("account.could-not-send", "We couldn't send a link. Try again.");
        button.disabled = false;
      })
      .catch(function () {
        said.hidden = false;
        said.classList.add("bad");
        said.textContent = t("signin.unreachable", "We couldn't connect. Check your connection and try again.");
        button.disabled = false;
      });
  });
})();
