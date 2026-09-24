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
   made a reloaded tab sit on "We're getting it ready" forever and never open the reader.

   Nothing here decides to spend. The button is the press; this only carries it. */
(function () {
  "use strict";
  var form = document.getElementById("press");
  var watching = document.getElementById("press-watch");
  var host = form || watching;
  if (!host || !window.fetch) return;

  var button = form ? form.querySelector("button") : null;
  /* The label alone, never the button: the press carries an arrow beside its
     words (2026-09-24), and `button.textContent = ...` would take the arrow with
     it the first time this said anything. */
  var says = button ? button.querySelector(".go-says") || button : null;
  var job = host.getAttribute("data-job");
  /* What a build of this shape has taken here lately, in **seconds** — `Job.state` says
     so, and this page rendered it as minutes until 2026-09-23, promising "about 420
     minutes" for a seven-minute build. Zero means the box has not finished enough of
     them to have a middle worth quoting. It is only ever the *first* guess: see below. */
  var usually = Number(host.getAttribute("data-usually") || 0);
  /* When the build actually started, in the same milliseconds as `Date.now()`. The
     working state knows it and says so; on the ready state nothing has started yet, so
     the clock begins at the press. */
  var started = Number(host.getAttribute("data-made") || 0) || 0;

  var doing = document.getElementById("press-doing");
  var left = document.getElementById("press-left");
  var note = document.getElementById("press-note");
  var away = document.getElementById("press-away");
  var quoted = document.getElementById("press-quoted");

  function say(node, words) {
    if (!node) return;
    node.textContent = words || "";
    node.hidden = !words;
  }

  function minutes(seconds) {
    return Math.max(1, Math.round(seconds / 60));
  }

  /* How far along, and how much longer — measured from this build rather than quoted
     from the last one (2026-09-23).

     `usually` is what builds of this shape took here lately, and it is a poor guide to
     any particular one: a 68-chapter text was quoted a minute, so the card said "Ready
     in about 1 minute" while the line under it already said this was taking longer than
     usual. Two numbers about one wait, disagreeing, on one card.

     So the quote is only the opening guess. The moment a chapter lands there is a real
     rate — seconds elapsed per chapter done — and the rest is arithmetic on this text's
     own pace, which corrects itself every poll and cannot be contradicted by the card.
     The share is honest for the same reason: it is chapters done of chapters known, not
     a bar filling on a timer. */
  function howLong(state) {
    var done = (state && state.done) || 0;
    var total = (state && state.total) || 0;
    var gone = started ? (Date.now() - started) / 1000 : 0;
    var parts = [];
    if (total > 1) {
      parts.push(t("press.page.share-done", "{n}% done", { n: Math.floor((done / total) * 100) }));
    }
    var over = 0;
    if (done > 0 && total > done && gone > 0) {
      over = (gone / done) * (total - done);
    } else if (usually && gone < usually) {
      over = usually - gone;
    }
    if (over > 0) {
      parts.push(
        tn(
          "press.page.minutes-left",
          minutes(over),
          "about {n} minute left",
          "about {n} minutes left"
        )
      );
    } else if (!parts.length) {
      /* Past the quote with nothing measured yet. Half of all builds are past it, so it
         must not read as a fault. */
      parts.push(t("press.page.longer-than-usual", "this one's taking a little longer"));
    }
    return parts.join(" · ");
  }

  /* Where the reader actually is. `Job.reader` already carries "<folder>/reader/index.html"
     — `serve.py` writes it that way — and this put the suffix on a second time and ran the
     whole thing through `encodeURIComponent`, which escapes the slashes too. So every
     finished build landed on "We can't find that page" (2026-09-24). Each segment is
     encoded, the separators are not, and nothing is appended. */
  function readerUrl(reader) {
    return (
      "/reader/" +
      String(reader)
        .split("/")
        .map(function (bit) {
          return encodeURIComponent(bit);
        })
        .join("/")
    );
  }

  /* And it is looked at before the reader is sent there. A build is written to disk while
     the box may also be rewriting every reader it holds — a deploy's rebuild does exactly
     that — so "the job says done" and "the page is served" are not the same instant. Three
     tries over a few seconds, then go anyway: a reader who sees the page a moment late is
     better served than one sent to a 404, and better than one left on this page forever. */
  function open(reader, tries) {
    var where = readerUrl(reader);
    say(doing, t("press.page.opening", "It's ready. Opening it now."));
    say(left, "");
    var togo = tries === undefined ? 3 : tries;
    fetch(where, { method: "HEAD", credentials: "same-origin" })
      .then(function (answer) {
        if (answer.ok || togo <= 0) {
          window.location.href = where;
          return;
        }
        window.setTimeout(function () {
          open(reader, togo - 1);
        }, 1500);
      })
      .catch(function () {
        window.location.href = where;
      });
  }

  function stop(why) {
    if (button) {
      button.disabled = false;
      says.textContent = t("press.page.read-this", "Read this");
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

  function working() {
    started = Date.now();
    // The quote's guess is put away; from here the line below it is measured and true.
    if (quoted) quoted.hidden = true;
    say(doing, t("press.page.getting-started", "We're getting it ready."));
    if (note) note.hidden = true;
    if (away) away.hidden = false;
  }

  if (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      button.disabled = true;
      says.textContent = t("press.page.making", "We're getting it ready");
      working();
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
