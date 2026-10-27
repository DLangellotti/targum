/* Correcting a text you brought (targum-internal#533; design.md §12, "The owner of a text
 * corrects its words, and cuts it into parts", 2026-10-27).
 *
 * ⋯ → Correct the text puts the page in correcting mode: a tap on a line opens it to be
 * written again, with Save and Cancel, and a press that starts a new part at that line
 * or joins the part it starts to the one before. Only on a text the reader added, and
 * the server says which those are (`/text/edit`); a library text keeps its proposals on
 * the word's card and never draws this row.
 *
 * Nothing here spends. A corrected line keeps the translation it had until Translate
 * again is pressed, which is a press on a quote like any other: "Uses none of your
 * credits", because a text costs none, and the server claims it through the rails.
 */
(function () {
  "use strict";
  if (location.protocol === "file:" || typeof fetch !== "function") return;
  var open = document.getElementById("correct-open");
  var main = document.querySelector("main");
  if (!open || !main) return;
  var parts = location.pathname.split("/");
  if (parts[1] !== "reader") return;
  // /reader/<folder>/reader/<file>: the folder is the one before the *last* "reader".
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;
  var S = window.TargumStrings || {
    t: function (key, english) {
      return english;
    },
  };
  var key = "";
  try {
    key = new URLSearchParams(location.search).get("k") || "";
  } catch (e) {
    key = "";
  }
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  function send(path, body) {
    var head = { "Content-Type": "application/json" };
    if (key) head["X-Targum-Key"] = key;
    return fetch(keyed(path), { method: "POST", headers: head, body: JSON.stringify(body) }).then(
      function (response) {
        return response.json().then(function (answer) {
          answer.status = response.status;
          return answer;
        });
      }
    );
  }

  var breaks = [];
  var before = {};
  var bar = null;
  var said = null;
  var editing = null;
  // The free pass that reads corrected lines again and redraws the page, while it runs.
  var redraw = "";
  // Where to go once it has: a cut can move a line onto another page.
  var landing = "";
  // A pass that finished while the reader was still correcting: drawn on Done.
  var owed = false;

  function correcting() {
    return document.body.classList.contains("correcting");
  }
  function reading() {
    var cell = document.querySelector(".pair .tr");
    return cell ? cell.getAttribute("lang") || "" : "";
  }
  function plain(pair) {
    var cell = pair.querySelector(".src.plain");
    return cell ? cell.textContent.replace(/[⁦-⁩]/g, "").trim() : "";
  }
  function first(pair) {
    var file = parts[parts.length - 1] || "index.html";
    return (file === "index.html" || file === "sec-0001.html") && main.querySelector(".pair[data-id]") === pair;
  }

  function tell(text) {
    if (said) said.textContent = text;
  }

  function drawBar() {
    bar = document.createElement("div");
    bar.className = "correct-bar";
    // The chrome's direction, as the bar's own pops are: a Hebrew page is right to left,
    // and this is targum talking, not the text.
    bar.dir = "ltr";
    bar.hidden = true;
    said = document.createElement("p");
    said.className = "correct-said";
    said.setAttribute("aria-live", "polite");
    said.textContent = S.t("reader.correct.tap-a-line", "Tap a line to correct it.");
    var done = document.createElement("button");
    done.type = "button";
    done.className = "correct-done";
    done.textContent = S.t("reader.correct.done", "Done");
    done.addEventListener("click", function () {
      setCorrecting(false);
    });
    bar.appendChild(said);
    bar.appendChild(done);
    main.parentNode.insertBefore(bar, main);
  }

  function setCorrecting(on) {
    if (!bar) drawBar();
    document.body.classList.toggle("correcting", on);
    open.setAttribute("aria-pressed", on ? "true" : "false");
    bar.hidden = !on && !redraw;
    // Reached by Tab while correcting, so a line can be opened from the keyboard.
    Array.prototype.forEach.call(main.querySelectorAll(".pair[data-id]"), function (pair) {
      if (on) pair.setAttribute("tabindex", "0");
      else pair.setAttribute("tabindex", "-1");
    });
    if (!on) {
      close();
      if (owed) return land();
      if (redraw) tell(S.t("reader.correct.updating", "We're updating the page."));
    } else {
      tell(S.t("reader.correct.tap-a-line", "Tap a line to correct it."));
    }
  }

  function close() {
    if (!editing) return;
    editing.pair.classList.remove("correcting-this");
    if (editing.form.parentNode) editing.form.parentNode.removeChild(editing.form);
    var pair = editing.pair;
    editing = null;
    if (correcting()) pair.focus();
  }

  function button(className, text) {
    var made = document.createElement("button");
    made.type = "button";
    made.className = className;
    made.textContent = text;
    return made;
  }

  function edit(pair) {
    if (editing && editing.pair === pair) return;
    close();
    var source = pair.querySelector(".src.plain");
    var form = document.createElement("form");
    form.className = "correct-form";
    form.dir = "ltr";
    var field = document.createElement("textarea");
    field.className = "correct-field";
    field.value = plain(pair);
    field.rows = Math.min(6, Math.max(2, Math.ceil(field.value.length / 60)));
    field.setAttribute("aria-label", S.t("reader.correct.this-line", "This line"));
    if (source) {
      field.lang = source.getAttribute("lang") || "";
      field.dir = source.getAttribute("dir") || "auto";
    }
    var keys = document.createElement("div");
    keys.className = "correct-keys";
    var save = document.createElement("button");
    save.type = "submit";
    save.className = "correct-save";
    save.textContent = S.t("reader.correct.save", "Save");
    var cancel = button("correct-cancel", S.t("reader.correct.cancel", "Cancel"));
    keys.appendChild(save);
    keys.appendChild(cancel);
    var id = pair.getAttribute("data-id");
    var joins = breaks.indexOf(id) >= 0;
    var cut = null;
    if (joins || !first(pair)) {
      cut = button(
        "correct-cut",
        joins
          ? S.t("reader.correct.join", "Join with the part before")
          : S.t("reader.correct.cut", "Start a new part here")
      );
      keys.appendChild(cut);
    }
    var note = document.createElement("p");
    note.className = "correct-note";
    note.setAttribute("aria-live", "polite");
    form.appendChild(field);
    form.appendChild(keys);
    form.appendChild(note);
    pair.parentNode.insertBefore(form, pair.nextSibling);
    pair.classList.add("correcting-this");
    editing = { pair: pair, form: form };
    field.focus();

    function refused(answer) {
      save.disabled = false;
      if (cut) cut.disabled = false;
      note.textContent =
        (answer && answer.error) || S.t("reader.correct.could-not-save", "We couldn't save that. Try again.");
    }
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      save.disabled = true;
      send("/text/correct", { name: name, line: pair.getAttribute("data-id"), text: field.value })
        .then(function (answer) {
          if (answer.status !== 200) return refused(answer);
          rewrite(pair, answer);
          close();
          if (answer.job) follow(answer.job.id);
          tell(S.t("reader.correct.saved", "Saved. Thanks for fixing it."));
        })
        .catch(function () {
          refused(null);
        });
    });
    cancel.addEventListener("click", close);
    form.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.stopPropagation();
        close();
      }
    });
    if (cut) {
      cut.addEventListener("click", function () {
        cut.disabled = true;
        send("/text/part", { name: name, line: pair.getAttribute("data-id"), join: joins })
          .then(function (answer) {
            if (answer.status !== 200) return refused(answer);
            breaks = answer.breaks || [];
            landing = answer.page || "";
            close();
            tell(S.t("reader.correct.cutting", "We're dividing it into parts."));
            // Shown as soon as it is made: the part the reader is on has just changed.
            if (answer.job) follow(answer.job.id, true);
          })
          .catch(function () {
            refused(null);
          });
      });
    }
  }

  /* The line as it now reads, until the page is drawn again with its words: the new text
     in every form of the line, since the pointed and unaccented forms were the old words'
     and whichever the page is showing has to show the correction, and its translation
     said to be from before where it is. */
  function rewrite(pair, answer) {
    Array.prototype.forEach.call(pair.querySelectorAll(".src"), function (cell) {
      cell.textContent = answer.text;
    });
    pair.setAttribute("data-id", answer.line);
    if ((answer.before || []).indexOf(reading()) >= 0) {
      (before[reading()] = before[reading()] || []).push(answer.line);
      markBefore(pair);
    }
  }

  /* "From before your correction", under a translation that is, and the one press that
     translates every such line again. */
  function markBefore(pair) {
    if (pair.querySelector(".correct-before")) return;
    var cell = pair.querySelector(".tr");
    if (!cell) return;
    pair.classList.add("translated-before");
    var note = document.createElement("p");
    note.className = "correct-before";
    note.dir = "ltr";
    var line = document.createElement("span");
    line.textContent = S.t("reader.correct.from-before", "This translation is from before your correction.");
    var again = button("correct-again", S.t("reader.correct.translate-again", "Translate again"));
    var cost = document.createElement("span");
    cost.className = "correct-cost";
    cost.textContent = S.t("reader.chapter.uses-no-credits", "Uses none of your credits");
    note.appendChild(line);
    note.appendChild(again);
    note.appendChild(cost);
    cell.parentNode.insertBefore(note, cell.nextSibling);
    again.addEventListener("click", function (event) {
      event.stopPropagation();
      again.disabled = true;
      line.textContent = S.t("reader.correct.translating", "We're translating your corrections…");
      send("/text/translate", { name: name, to: reading() })
        .then(function (answer) {
          if (answer.ready) return location.reload();
          if (answer.blocked || answer.stage === "blocked" || answer.status >= 400) {
            again.disabled = false;
            line.textContent =
              answer.blocked || answer.error || S.t("reader.correct.could-not-translate", "We couldn't translate it. Try again.");
            return;
          }
          follow(answer.id, true);
        })
        .catch(function () {
          again.disabled = false;
          line.textContent = S.t("reader.correct.could-not-translate", "We couldn't translate it. Try again.");
        });
    });
  }

  function land() {
    if (landing) location.href = landing + location.search;
    else location.reload();
  }

  //: How often the page asks after a pass. A test sets it lower.
  var POLL = 2000;
  window.TargumCorrect = { POLL: POLL };

  /* A pass is followed until it is done, and the page is drawn again then — at once for
     Translate again, which the reader asked to see, and for a correction once the reader
     has pressed Done, so a page being corrected is never reloaded from under them. */
  function follow(id, now) {
    redraw = id;
    fetch(keyed("/job/" + encodeURIComponent(id)))
      .then(function (response) {
        return response.json();
      })
      .then(function (job) {
        if (job.stage === "done") {
          if (redraw === id) redraw = "";
          if (now || !correcting()) return land();
          owed = true;
          return;
        }
        if (job.stage === "failed" || job.stage === "blocked") {
          redraw = "";
          if (!bar) drawBar();
          bar.hidden = false;
          tell(job.error || job.blocked || S.t("reader.correct.could-not-update", "We couldn't update the page."));
          return;
        }
        setTimeout(function () {
          follow(id, now);
        }, window.TargumCorrect.POLL);
      })
      .catch(function () {
        setTimeout(function () {
          follow(id, now);
        }, window.TargumCorrect.POLL * 4);
      });
  }

  // Ahead of the page's own handler, which would open a word's card.
  document.addEventListener(
    "click",
    function (event) {
      if (!correcting()) return;
      var at = event.target;
      if (!at || !at.closest || at.closest(".correct-form, .correct-bar, .correct-before")) return;
      var pair = at.closest(".pair[data-id]");
      if (!pair || !main.contains(pair)) return;
      event.preventDefault();
      event.stopPropagation();
      edit(pair);
    },
    true
  );
  main.addEventListener("keydown", function (event) {
    if (!correcting() || event.key !== "Enter") return;
    var pair = event.target && event.target.matches && event.target.matches(".pair[data-id]") ? event.target : null;
    if (!pair) return;
    event.preventDefault();
    edit(pair);
  });
  open.addEventListener("click", function () {
    setCorrecting(!correcting());
  });

  fetch(keyed("/text/edit?name=" + encodeURIComponent(name)))
    .then(function (response) {
      return response.json();
    })
    .then(function (answer) {
      if (!answer || !answer.editable) return;
      open.hidden = false;
      breaks = answer.breaks || [];
      before = answer.before || {};
      (before[reading()] || []).forEach(function (id) {
        var pair = main.querySelector('.pair[data-id="' + id + '"]');
        if (pair) markBefore(pair);
      });
      if (answer.reading && answer.reading.id) follow(answer.reading.id);
    })
    .catch(function () {
      /* no row, which is what a reader that could not ask should show */
    });
})();
