/* The press, for a quote made through a connector (targum-internal#80).

   The page is a plain form posting to `/build/<id>`, so it works with script off: the
   press claims the job and sends the reader back here, where the page says it is being
   made and offers a look. This makes the same press without the reload, and then waits
   and opens the reader when there is one.

   Nothing here decides to spend. The button is the press; this only carries it. */
(function () {
  "use strict";
  var form = document.getElementById("press");
  if (!form || !window.fetch) return;
  var button = form.querySelector("button");
  var job = form.getAttribute("data-job");

  function say(words) {
    var said = document.createElement("p");
    said.className = "said";
    said.setAttribute("role", "status");
    said.textContent = words;
    form.parentNode.insertBefore(said, form.nextSibling);
    return said;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    button.disabled = true;
    var said = say("We're getting it ready.");
    fetch("/build/" + encodeURIComponent(job), {
      method: "POST",
      headers: { "X-Targum-Press": "1" },
    })
      .then(function (answer) {
        return answer.json();
      })
      .then(function (state) {
        if (state.error || state.blocked) {
          button.disabled = false;
          said.textContent = state.error || state.blocked;
          return;
        }
        watch(said);
      })
      .catch(function () {
        button.disabled = false;
        said.textContent = "We couldn't start that. Try the link again.";
      });
  });

  /* Ask how it is going, and open it when it is. A poll rather than a stream: this page
     is one press and one wait, and it is reached from another app — a reader who closes
     the tab has lost nothing, because the build carries on without it. */
  function watch(said) {
    window.setTimeout(function () {
      fetch("/job/" + encodeURIComponent(job))
        .then(function (answer) {
          return answer.json();
        })
        .then(function (state) {
          if (state.reader) {
            window.location.href =
              "/reader/" + encodeURIComponent(state.reader) + "/reader/index.html";
            return;
          }
          if (state.error) {
            said.textContent = state.error;
            button.disabled = false;
            return;
          }
          if (state.message) said.textContent = state.message;
          watch(said);
        })
        .catch(function () {
          watch(said);
        });
    }, 2000);
  }
})();
