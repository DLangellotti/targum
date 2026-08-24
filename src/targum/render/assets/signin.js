/* The sign-in form, posted without leaving the page.

   The form works without this: it is a real <form> with a real action, so a browser
   with no JavaScript still signs in. This only replaces the page reload with a
   sentence, because "check your email" belongs next to the field you just filled in. */
(function () {
  "use strict";
  var form = document.getElementById("ask");
  var said = document.getElementById("sent");
  if (!form || !said) return;

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
      body: JSON.stringify({ email: field.value }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (answer) {
        said.hidden = false;
        if (answer.ok) {
          said.textContent = answer.body.message || "Check your email.";
          form.hidden = true;
          return;
        }
        said.classList.add("bad");
        said.textContent = answer.body.error || "That did not work. Try again.";
        button.disabled = false;
      })
      .catch(function () {
        said.hidden = false;
        said.classList.add("bad");
        said.textContent = "targum could not be reached. Try again in a moment.";
        button.disabled = false;
      });
  });
})();
