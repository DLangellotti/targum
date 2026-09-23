/* The press, for a quote made through a connector (targum-internal#80).

   The page is a plain form posting to `/build/<id>`, so it works with script off: the
   press claims the job and sends the reader back here, where the page says it is being
   made and offers a look. This makes the same press without the reload, then narrates
   the build and opens the reader the moment there is one.

   **What a reader waiting on a build needs**, and this page had none of it (2026-09-23,
   watching a video build with nothing on screen but "Fetching the video…"): what is
   happening, how much longer, and somewhere to go meanwhile. The last is the one that
   matters — design.md §12 ("A build is on the shelf while it is building") settled that
   the answer to walking away is a destination and not a spinner, and the shelf is it, so
   the note under the press becomes a way to Your texts, where this build is already a
   row.

   It watches in both states. The ready state hangs the watch off the press form; the
   working state — a reload, or coming back to the link later — hangs it off
   `#press-watch`, which is there for no other reason. Looking for the form alone is what
   made a reloaded tab sit on "We're making it" forever and never open the reader.

   Nothing here decides to spend. The button is the press; this only carries it. */
(function () {
  "use strict";
  var form = document.getElementById("press");
  var watching = document.getElementById("press-watch");
  var host = form || watching;
  if (!host || !window.fetch) return;

  var button = form ? form.querySelector("button") : null;
  var job = host.getAttribute("data-job");
  /* What a build of this shape has taken here lately, in **seconds** — `Job.state` says
     so, and this page rendered it as minutes until 2026-09-23, promising "about 420
     minutes" for a seven-minute build. Zero means the box has not finished enough of
     them to have a middle worth quoting, and then nothing is said at all. */
  var usually = Number(host.getAttribute("data-usually") || 0);
  /* When the build actually started, in the same milliseconds as `Date.now()`. The
     working state knows it and says so; on the ready state nothing has started yet, so
     the clock begins at the press. */
  var started = Number(host.getAttribute("data-made") || 0) || 0;

  var doing = document.getElementById("press-doing");
  var left = document.getElementById("press-left");
  var note = document.getElementById("press-note");
  var away = document.getElementById("press-away");

  function say(node, words) {
    if (!node) return;
    node.textContent = words || "";
    node.hidden = !words;
  }

  /* How much longer, in the reader's own time (§6). Never a bar and never a share: what
     the server reports is chapters done out of chapters known, and a text whose chapter
     count arrives late would make a bar run backwards. A count cannot. */
  function howLong(state) {
    var far = "";
    if (state && state.total > 1) {
      far = t("press.page.done-of-total", "{done} of {total}", {
        done: state.done || 0,
        total: state.total,
      });
    }
    if (!usually || !started) return far;
    var over = Math.round((usually - (Date.now() - started) / 1000) / 60);
    /* Past the middle is not a failure and must not read as one — half of all builds
       are. Saying so beats counting down to zero and then standing there at zero. */
    var when =
      over >= 1
        ? tn("press.page.minutes-left", over, "About {n} minute left", "About {n} minutes left")
        : t("press.page.longer-than-usual", "Taking a little longer than usual");
    return far ? far + " · " + when : when;
  }

  function open(reader) {
    say(doing, t("press.page.opening", "Opening it now."));
    say(left, "");
    window.location.href = "/reader/" + encodeURIComponent(reader) + "/reader/index.html";
  }

  function stop(why) {
    if (button) {
      button.disabled = false;
      button.textContent = t("press.page.read-this", "Read this");
    }
    say(doing, why);
    say(left, "");
    if (away) away.hidden = true;
    if (note) note.hidden = false;
  }

  /* Ask how it is going, and open it when it is. A poll rather than a stream: this page
     is one press and one wait, reached from somebody else's app, and a reader who closes
     the tab has lost nothing — the build carries on without it and is a row on the
     shelf. */
  function watch() {
    window.setTimeout(function () {
      fetch("/job/" + encodeURIComponent(job))
        .then(function (answer) {
          return answer.json();
        })
        .then(function (state) {
          if (state.reader) return open(state.reader);
          if (state.error) return stop(state.error);
          if (state.message) say(doing, state.message);
          say(left, howLong(state));
          watch();
        })
        .catch(function () {
          /* A dropped poll is a dropped poll: the build is on the box and does not care
             whether this page can reach it. Keep asking. */
          watch();
        });
    }, 2000);
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      button.disabled = true;
      button.textContent = t("press.page.making", "Making it…");
      started = Date.now();
      say(doing, t("press.page.getting-started", "Getting started."));
      if (note) note.hidden = true;
      if (away) away.hidden = false;
      fetch("/build/" + encodeURIComponent(job), {
        method: "POST",
        headers: { "X-Targum-Press": "1" },
      })
        .then(function (answer) {
          return answer.json();
        })
        .then(function (state) {
          if (state.error || state.blocked) return stop(state.error || state.blocked);
          if (state.reader) return open(state.reader);
          say(left, howLong(state));
          watch();
        })
        .catch(function () {
          stop(t("press.page.couldn-t-start", "We couldn't start that. Try the link again."));
        });
    });
  } else {
    /* Already building when the page loaded. Nothing to press and nothing to reveal —
       the template drew both lines — so go straight to watching. */
    say(left, howLong(null));
    watch();
  }

  /* Words through the page's `TargumStrings`, with the English here as the fallback
     (targum-internal#184), the same shim every other script carries. */
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
})();
