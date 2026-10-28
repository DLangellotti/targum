/* Rewriting a text you brought at your level (targum-internal#535; design.md §12, "A text
 * you brought, rewritten at your level", 2026-10-28).
 *
 * ⋯ → Rewrite at my level opens an offer above the text: the level it will be written
 * for, chosen from what targum knows of the reader and theirs to change, and what it
 * uses, "Uses none of your credits", said before anything is asked of a model. The press
 * is `/text/rewrite`, claimed through the rails like any build; the page follows the job
 * and opens the new text when it is ready.
 *
 * And the two texts point at each other: a rewrite says which text it was written from,
 * and the original lists the rewrites made of it, both off `/text/edit`.
 */
(function () {
  "use strict";
  if (location.protocol === "file:" || typeof fetch !== "function") return;
  var open = document.getElementById("rewrite-open");
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
  function fill(text, values) {
    return text.replace(/\{(\w+)\}/g, function (whole, field) {
      return Object.prototype.hasOwnProperty.call(values, field) ? values[field] : whole;
    });
  }

  var offer = null;
  var panel = null;

  function reading() {
    var cell = document.querySelector(".pair .tr");
    return cell ? cell.getAttribute("lang") || "" : "";
  }

  function button(className, text) {
    var made = document.createElement("button");
    made.type = "button";
    made.className = className;
    made.textContent = text;
    return made;
  }

  /* The offer: which level, what it uses, and the press. */
  function draw() {
    panel = document.createElement("div");
    panel.className = "rewrite-offer";
    panel.dir = "ltr";
    panel.id = "rewrite-offer";
    var said = document.createElement("p");
    said.className = "rewrite-said";
    said.textContent = S.t(
      "reader.rewrite.what",
      "We'll write this text again in simpler words, as a new text linked to this one."
    );
    var row = document.createElement("div");
    row.className = "rewrite-row";
    var label = document.createElement("label");
    label.className = "rewrite-level";
    label.textContent = S.t("reader.rewrite.for", "Write it for") + " ";
    var choose = document.createElement("select");
    (offer.levels || []).forEach(function (level) {
      var option = document.createElement("option");
      option.value = level.id;
      option.textContent = level.label;
      if (level.id === offer.level) option.selected = true;
      choose.appendChild(option);
    });
    label.appendChild(choose);
    var cost = document.createElement("span");
    cost.className = "rewrite-cost";
    cost.textContent = S.t("reader.chapter.uses-no-credits", "Uses none of your credits");
    row.appendChild(label);
    row.appendChild(cost);
    var keys = document.createElement("div");
    keys.className = "rewrite-keys";
    var go = button("rewrite-go", S.t("reader.rewrite.go", "Rewrite it"));
    var cancel = button("rewrite-cancel", S.t("reader.correct.cancel", "Cancel"));
    keys.appendChild(go);
    keys.appendChild(cancel);
    var note = document.createElement("p");
    note.className = "rewrite-note";
    note.setAttribute("aria-live", "polite");
    panel.appendChild(said);
    panel.appendChild(row);
    panel.appendChild(keys);
    panel.appendChild(note);
    main.parentNode.insertBefore(panel, main);

    cancel.addEventListener("click", function () {
      show(false);
    });
    go.addEventListener("click", function () {
      go.disabled = true;
      choose.disabled = true;
      note.textContent = S.t("reader.rewrite.working", "We're rewriting it. This takes a minute or two.");
      var head = { "Content-Type": "application/json" };
      if (key) head["X-Targum-Key"] = key;
      fetch(keyed("/text/rewrite"), {
        method: "POST",
        headers: head,
        body: JSON.stringify({ name: name, level: choose.value, to: reading() }),
      })
        .then(function (response) {
          return response.json().then(function (answer) {
            answer.status = response.status;
            return answer;
          });
        })
        .then(function (answer) {
          if (answer.status !== 200 || answer.stage === "blocked" || answer.stage === "failed") {
            go.disabled = false;
            choose.disabled = false;
            note.textContent =
              answer.blocked || answer.error || S.t("reader.rewrite.could-not", "We couldn't rewrite it. Try again.");
            return;
          }
          follow(answer.id, note, go, choose);
        })
        .catch(function () {
          go.disabled = false;
          choose.disabled = false;
          note.textContent = S.t("reader.rewrite.could-not", "We couldn't rewrite it. Try again.");
        });
    });
  }

  function show(on) {
    if (on && !panel) draw();
    if (panel) panel.hidden = !on;
    open.setAttribute("aria-expanded", on ? "true" : "false");
    if (on && panel) {
      var first = panel.querySelector("select, button");
      if (first) first.focus();
    }
  }

  //: How often the page asks after the job. A test sets it lower.
  var POLL = 2000;
  window.TargumRewrite = { POLL: POLL };

  /* Followed until the new text opens, which is where the reader is going. */
  function follow(id, note, go, choose) {
    fetch(keyed("/job/" + encodeURIComponent(id)))
      .then(function (response) {
        return response.json();
      })
      .then(function (job) {
        if (job.stage === "done" && job.reader) {
          location.href = keyed("/reader/" + job.reader.split("/").map(encodeURIComponent).join("/"));
          return;
        }
        if (job.stage === "failed" || job.stage === "blocked") {
          go.disabled = false;
          choose.disabled = false;
          note.textContent =
            job.error || job.blocked || S.t("reader.rewrite.could-not", "We couldn't rewrite it. Try again.");
          return;
        }
        if (job.message) note.textContent = job.message;
        setTimeout(function () {
          follow(id, note, go, choose);
        }, window.TargumRewrite.POLL);
      })
      .catch(function () {
        setTimeout(function () {
          follow(id, note, go, choose);
        }, window.TargumRewrite.POLL * 4);
      });
  }

  /* The other half of the pair: where a rewrite came from, or what was made of this. */
  function links() {
    var lines = [];
    if (offer.from) {
      lines.push([
        fill(S.t("reader.rewrite.from", "Rewritten for {level} from"), { level: offer.from.level || "" }) + " ",
        offer.from,
      ]);
    }
    (offer.made || []).forEach(function (one) {
      lines.push([fill(S.t("reader.rewrite.made", "Also written for {level}:"), { level: one.level || "" }) + " ", one]);
    });
    if (!lines.length) return;
    var box = document.createElement("div");
    box.className = "rewrite-links";
    box.dir = "ltr";
    lines.forEach(function (line) {
      var p = document.createElement("p");
      p.appendChild(document.createTextNode(line[0]));
      var a = document.createElement("a");
      a.href = keyed(line[1].reader);
      a.textContent = line[1].title;
      a.dir = "auto";
      p.appendChild(a);
      box.appendChild(p);
    });
    main.parentNode.insertBefore(box, main);
  }

  open.addEventListener("click", function () {
    show(!panel || panel.hidden);
  });

  fetch(keyed("/text/edit?name=" + encodeURIComponent(name)))
    .then(function (response) {
      return response.json();
    })
    .then(function (answer) {
      offer = answer && answer.editable ? answer.rewrite : null;
      if (!offer) return;
      links();
      if (!offer.offered) return;
      open.hidden = false;
      // A chat or a connector's link to this offer ends `?rewrite=1`: the offer is
      // opened, never pressed (`chat.tools.quote_rewrite`).
      var asked = "";
      try {
        asked = new URLSearchParams(location.search).get("rewrite") || "";
      } catch (e) {
        asked = "";
      }
      if (asked) show(true);
    })
    .catch(function () {
      /* no row, which is what a reader that could not ask should show */
    });
})();
