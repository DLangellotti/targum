/* Cancel on a reader's own build (targum-internal#694): the waiting card, a building row
 * in Your targums, and a getting-ready card on Home all draw it from here, so the three
 * say the same thing and ask the same question.
 *
 * A build that is waiting is cancelled at the press, and every credit it held goes back:
 * nothing is lost, so nothing is asked. A build that is running asks once, in place, before
 * it stops, with the safe answer focused; it then stops at the step it is on and is
 * settled to its receipt like any build (David, 2026-11-13). The question and the end
 * say credits, never money (design.md §6): a recording's done part uses its credits, a
 * text uses none, and the end says what the receipt used (targum-internal#715). The press is quiet, `.btn.ghost.outline.small`, never a
 * card's primary (design.md §13), and `.btn` gives it 44px under a thumb (§8).
 *
 * The server decides whose build it is (`/jobs/cancel` answers 404 for anybody else's), and
 * what it can do (`cancellable`, `stopping` on every row of `/jobs`). This file only says it.
 */
(function () {
  "use strict";

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
  function keyed(path) {
    var key = window.TARGUM_KEY || "";
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  //: How often a stopping build is asked after, until it has stopped.
  var POLL = 2000;

  // `waiting`: the page last saw it waiting, so a press that finds it started is not a
  // stop; the server says so and the page asks first (qa-claude on #1199).
  function post(id, waiting) {
    var body = { id: id };
    if (waiting) body.waiting = true;
    return fetch(keyed("/jobs/cancel"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    }).then(function (r) {
      return r.json().then(
        function (answer) {
          return answer || {};
        },
        function () {
          return {};
        }
      );
    });
  }

  // Follows a build that is stopping until it is not running any more.
  function until(id, done) {
    function look() {
      fetch(keyed("/job/" + encodeURIComponent(id)), { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : {};
        })
        .then(
          function (state) {
            if (state && (state.stage === "working" || state.stage === "queued")) {
              return setTimeout(look, POLL);
            }
            done(state || {});
          },
          function () {
            setTimeout(look, POLL * 2);
          }
        );
    }
    setTimeout(look, POLL);
  }

  function button(className, text) {
    var press = document.createElement("button");
    press.type = "button";
    press.className = "btn " + className + " small";
    press.textContent = text;
    return press;
  }

  function line(text) {
    var said = document.createElement("span");
    said.className = "cancel-said";
    said.setAttribute("role", "status");
    said.textContent = text;
    return said;
  }

  /* The control for one build: a span holding Cancel, or the question, or how it went.
     `job` is a row of `/jobs` (or `/job/<id>`): its `id`, `stage`, `title`,
     `cancellable` and `stopping`. `options.gone(state, words)` is told once the build has
     left the line — cancelled while it waited, or stopped — with what was said about it.
     `options.host`, where given, is where the words go (a row's line under its title),
     while the presses stay in the span; without it, both are in the span. Returns null
     where there is nothing to press. */
  function control(job, options) {
    var settings = options || {};
    if (!job || !job.id || (!job.cancellable && !job.stopping)) return null;
    var box = document.createElement("span");
    box.className = "cancel";
    var talk = document.createElement("span");
    talk.className = "cancel-talk";
    talk.hidden = true;
    (settings.host || box).appendChild(talk);

    function say(text, className, live) {
      talk.textContent = "";
      talk.hidden = !text;
      if (!text) return;
      var said = line(text);
      said.className = className || "cancel-said";
      if (!live) said.removeAttribute("role");
      talk.appendChild(said);
    }
    function presses() {
      Array.prototype.slice.call(box.children).forEach(function (kid) {
        if (kid !== talk) box.removeChild(kid);
      });
    }

    function gone(state, words) {
      presses();
      say(words, "cancel-said", true);
      if (settings.gone) settings.gone(state, words);
    }

    function stopping() {
      presses();
      say(t("building.cancel.stopping", "Stopping it after the step it's on…"), "cancel-said", true);
      until(job.id, function (state) {
        if (state.stage === "done") {
          say(t("building.cancel.finished", "It finished before we could stop it."), "cancel-said", true);
          if (settings.finished) settings.finished(state);
          return;
        }
        gone(state, stopped(state));
      });
    }

    // What the stop used, from the build's own receipt (`used`, in credits).
    function stopped(state) {
      var used = Number(state && state.used) || 0;
      if (used > 0) return tn("building.cancel.stopped", used, "Stopped. It used {n} credit.", "Stopped. It used {n} credits.");
      return t("building.cancel.stopped-none", "Stopped. Nothing was used.");
    }

    function refused(answer) {
      draw();
      say((answer && answer.error) || t("building.cancel.failed", "We couldn't cancel it. Try again in a moment."), "cancel-said", true);
    }

    function send(press, waiting) {
      if (press) press.disabled = true;
      post(job.id, waiting).then(
        function (answer) {
          if (answer.cancelled) return gone({ id: job.id, stage: "cancelled" }, t("building.cancel.cancelled", "Cancelled. Nothing was used."));
          if (answer.stopping) return stopping();
          if (answer.started) {
            // It started since the page last looked: a stop now asks first.
            job.stage = "working";
            return ask();
          }
          refused(answer);
        },
        function () {
          refused(null);
        }
      );
    }

    function ask() {
      // Asked once, in place: a dialog for this is a dialog nobody reads (you.js's Delete
      // account). The safe choice has the focus.
      presses();
      say(
        job.audio
          ? t("building.cancel.ask", "Stop it? What's done so far still uses credits.")
          : t("building.cancel.ask-none", "Stop it? It uses none of your credits."),
        "cancel-ask",
        false
      );
      var stop = button("ghost outline danger", t("building.cancel.stop", "Stop it"));
      var keep = button("text", t("building.cancel.keep", "Keep building"));
      stop.onclick = function () {
        send(stop);
      };
      keep.onclick = function () {
        draw();
        var again = box.querySelector("button");
        if (again) again.focus();
      };
      box.appendChild(stop);
      box.appendChild(keep);
      keep.focus();
    }

    function draw() {
      presses();
      say("");
      var press = button("ghost outline", settings.label || t("building.cancel.press", "Cancel"));
      if (job.title) press.setAttribute("aria-label", t("building.cancel.named", "Cancel {title}", { title: job.title }));
      press.onclick = function () {
        if (job.stage === "queued" && !job.stopping) return send(press, true);
        ask();
      };
      box.appendChild(press);
    }

    if (job.stopping) stopping();
    else draw();
    return box;
  }

  /* The waiting card's line about the builds ahead of this one (David, 2026-11-13): each
     of the reader's own, named, with its Cancel; and how many are other people's, which
     only they can cancel. `options.changed()` is told when one of the reader's own leaves
     the line, so the card can ask where it now stands. */
  function ahead(job, options) {
    var settings = options || {};
    var mine = (job && job.ahead) || [];
    var others = Number((job && job.ahead_others) || 0);
    if (!mine.length && !others) return null;
    var box = document.createElement("div");
    box.className = "cancel-ahead";
    if (mine.length) {
      var head = document.createElement("p");
      head.className = "cancel-ahead-head";
      head.textContent = t("building.cancel.ahead", "Yours, ahead of it:");
      box.appendChild(head);
      var list = document.createElement("ul");
      list.className = "cancel-ahead-list";
      mine.forEach(function (one) {
        var item = document.createElement("li");
        var name = document.createElement("bdi");
        name.className = "cancel-ahead-title";
        name.setAttribute("dir", "auto");
        // Its language, so a Hebrew title is read and set as Hebrew (design.md §14.3).
        if (one.language) name.setAttribute("lang", one.language);
        name.textContent = one.title || "";
        item.appendChild(name);
        var press = control(one, {
          gone: function () {
            if (settings.changed) settings.changed();
          },
        });
        if (press) item.appendChild(press);
        list.appendChild(item);
      });
      box.appendChild(list);
    }
    if (others) {
      var theirs = document.createElement("p");
      theirs.className = "cancel-ahead-others";
      theirs.textContent = tn(
        "building.cancel.others",
        others,
        "{n} ahead is someone else's. Only they can cancel it.",
        "{n} ahead are other people's. Only they can cancel them."
      );
      box.appendChild(theirs);
    }
    return box;
  }

  window.TargumCancel = { control: control, ahead: ahead };
})();
