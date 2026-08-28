/* Adding a text targum does not have. Reads a file or a link, prices the translation, and only spends
   once you have seen the number. */

(function () {
  "use strict";

  var key = window.TARGUM_KEY;
  /* Hosted there is no start-up key: the session cookie identifies the reader, and a key
     riding in every URL is a bearer token in browser history, on a shared screen, and in
     a Referer. Local it stays, because there it proves the page came from the terminal
     that started the process. Both cases are this one branch. */
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }
  var languageNames = window.TARGUM_LANGUAGES || {};
  // At the top, not inside the picker that first needed it: two other things on this page
  // ask it which language you read into, and a `var` in an IIFE is not a binding they can
  // see. Reaching for it from out here threw on load, and a throw here is the whole page —
  // `go.onclick` is assigned below it, so the Add button was never wired to anything.
  var lang = window.TargumLang;

  function named(code) {
    return languageNames[code] || (code || "").toUpperCase();
  }
  var drop = document.getElementById("drop");
  var fileInput = document.getElementById("file");
  var sourceInput = document.getElementById("source");
  var pasted = document.getElementById("pasted");
  var go = document.getElementById("go");
  var status = document.getElementById("status");
  var chosen = null;
  //: The translation the reader brought, if they brought one.
  var theirs = null;

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  function say(html, bad) {
    status.hidden = false;
    status.className = "status" + (bad ? " bad" : "");
    status.innerHTML = "";
    status.appendChild(html);
  }

  function line(text) {
    var p = document.createElement("p");
    p.style.margin = "0";
    p.textContent = text;
    return p;
  }

  /* --- choosing something -------------------------------------------------- */

  document.getElementById("choose").onclick = function () {
    fileInput.click();
  };

  fileInput.onchange = function () {
    if (fileInput.files[0]) take(fileInput.files[0]);
  };

  ["dragenter", "dragover"].forEach(function (name) {
    drop.addEventListener(name, function (event) {
      event.preventDefault();
      drop.classList.add("over");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    drop.addEventListener(name, function (event) {
      event.preventDefault();
      drop.classList.remove("over");
    });
  });
  drop.addEventListener("drop", function (event) {
    var file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) take(file);
  });

  var unchoose = document.getElementById("unchoose");
  var DROP_LABEL = drop.querySelector(".drop-label").textContent;
  var DROP_NOTE = drop.querySelector(".drop-note").textContent;

  function showChosen() {
    var picked = chosen !== null;
    drop.querySelector(".drop-label").textContent = picked ? chosen.name : DROP_LABEL;
    drop.querySelector(".drop-note").textContent = picked
      ? Math.round(chosen.size / 1024) + " KB"
      : DROP_NOTE;
    document.getElementById("choose").hidden = picked;
    if (unchoose) unchoose.hidden = !picked;
  }

  function take(file) {
    chosen = file;
    sourceInput.value = "";
    showChosen();
  }

  function forget() {
    chosen = null;
    fileInput.value = "";
    showChosen();
  }

  if (unchoose) unchoose.onclick = forget;

  // Typing a link puts the file down, and so does pasting the text. Leaving the filename
  // on screen while something else is what gets used left no way to tell which would win.
  sourceInput.addEventListener("input", function () {
    if (sourceInput.value.trim() && chosen) forget();
  });
  if (pasted) {
    pasted.addEventListener("input", function () {
      if (!pasted.value.trim()) return;
      if (chosen) forget();
      sourceInput.value = "";
    });
  }

  /* --- the translation, where the reader has one ----------------------------- */

  /* Same drop zone, same three states, one text down. Its own copy rather than a shared
     one: the two zones hold different files and say different things, and a version of
     this that took both had four arguments and told you less than this does. */
  (function () {
    var half = document.getElementById("have-translation");
    var zone = document.getElementById("drop-translation");
    var field = document.getElementById("translation");
    var choose = document.getElementById("choose-translation");
    var undo = document.getElementById("unchoose-translation");
    var how = document.getElementById("how");
    var note = document.getElementById("how-note");
    if (!zone || !field || !how) return;

    var LABEL = zone.querySelector(".drop-label").textContent;
    var NOTE = zone.querySelector(".drop-note").textContent;

    function show() {
      var picked = theirs !== null;
      zone.querySelector(".drop-label").textContent = picked ? theirs.name : LABEL;
      zone.querySelector(".drop-note").textContent = picked
        ? Math.round(theirs.size / 1024) + " KB"
        : NOTE;
      choose.hidden = picked;
      undo.hidden = !picked;
    }

    function take(file) {
      theirs = file;
      show();
    }

    choose.onclick = function () {
      field.click();
    };
    field.onchange = function () {
      if (field.files[0]) take(field.files[0]);
    };
    undo.onclick = function () {
      theirs = null;
      field.value = "";
      show();
    };
    ["dragenter", "dragover"].forEach(function (name) {
      zone.addEventListener(name, function (event) {
        event.preventDefault();
        zone.classList.add("over");
      });
    });
    ["dragleave", "drop"].forEach(function (name) {
      zone.addEventListener(name, function (event) {
        event.preventDefault();
        zone.classList.remove("over");
      });
    });
    zone.addEventListener("drop", function (event) {
      var file = event.dataTransfer && event.dataTransfer.files[0];
      if (file) take(file);
    });

    Array.prototype.forEach.call(how.querySelectorAll("[data-how]"), function (press) {
      press.addEventListener("click", function () {
        var mine = press.getAttribute("data-how") === "mine";
        Array.prototype.forEach.call(how.querySelectorAll("[data-how]"), function (other) {
          other.setAttribute(
            "aria-pressed",
            other === press ? "true" : "false"
          );
        });
        half.hidden = !mine;
        note.textContent = mine
          ? "targum lines it up with the Hebrew, sentence by sentence."
          : "targum translates it, sentence by sentence.";
        // Switching back to Make one puts down whatever was brought: leaving it attached
        // would send a translation the reader had just said they did not want to use.
        if (!mine) {
          var typed = document.getElementById("pasted-translation");
          if (typed) typed.value = "";
          if (theirs) {
            theirs = null;
            field.value = "";
            show();
          }
        }
      });
    });
  })();

  /* --- building ------------------------------------------------------------ */

  // The language chosen here is the one the library and the words page open on.
  //
  // The note under it says how far along that language is, in the word the picker beside
  // it uses. `TargumLang.betaNote` is not enough here: it calls everything that is not
  // Hebrew beta, and it names a language from a list this page does not carry — Aramaic
  // came out of it as "ARC".
  (function () {
    var from = document.getElementById("from");
    var note = document.getElementById("from-beta");
    var stages = window.TARGUM_READING || [];
    var was = lang.current(
      stages.map(function (row) {
        return row.code;
      })
    );
    if (was) from.value = was;

    function say() {
      var code = from.value;
      var found = null;
      stages.forEach(function (row) {
        if (row.code === code) found = row;
      });
      note.hidden = !found || found.stage === "alpha";
      if (!note.hidden) {
        // Both say experimental, which is what the picker says. This is where the two
        // part company: one has no word levels at all, the other simply is not Hebrew.
        note.textContent =
          found.name +
          (found.stage === "R&D"
            ? " is experimental: no word levels yet, and everything works best in Hebrew."
            : " is experimental. Everything works best in Hebrew.");
      }
      if (code) lang.set(code);
    }
    from.addEventListener("change", say);
    say();
  })();

  /* And which language to read it into, remembered the same way. Both pickers are then
   * narrowed to what this account said on its profile: what it is learning, and what it
   * reads into.
   *
   * Redrawn from the lists rather than pruned. A picker that removed an option could
   * never put it back, so a language ticked on the profile page stayed missing here
   * until a reload. The narrowing waits for the account to answer, so the picker starts
   * as the page was built and settles a moment later. That is the right way round: the
   * server refuses a language the account may not have whatever this was showing, so
   * being briefly generous here costs nothing and being briefly wrong the other way
   * would hide a language from somebody who does read it.
   */
  (function () {
    var from = document.getElementById("from");
    var to = document.getElementById("to");
    if (!to) return;

    function fill(select, rows, allowed) {
      var was = select.value;
      select.textContent = "";
      rows.forEach(function (row) {
        if (allowed && allowed.indexOf(row.code) < 0) return;
        var option = document.createElement("option");
        option.value = row.code;
        option.textContent = row.name + " (" + row.label + ")";
        select.appendChild(option);
      });
      // Whatever was chosen may be a language this account no longer has; the first
      // that is left stands in for it.
      for (var n = 0; n < select.options.length; n++) {
        if (select.options[n].value === was) select.selectedIndex = n;
      }
    }

    if (window.TargumSync) {
      window.TargumSync.onChange(function () {
        fill(from, window.TARGUM_READING || [], window.TargumSync.learning());
        fill(to, window.TARGUM_INTO || [], window.TargumSync.reads());
        // The note under the first picker is about whatever it now shows.
        from.dispatchEvent(new Event("change"));
      });
    }

    var was = lang.into();
    if (was) {
      for (var n = 0; n < to.options.length; n++) {
        if (to.options[n].value === was) to.selectedIndex = n;
      }
    }
    to.addEventListener("change", function () {
      if (to.value) lang.into(to.value);
    });
  })();

  // Nothing on this page is drawn from the word list, so there is nothing to redraw:
  // sync runs here only so the header can say who is signed in, and so that a browser
  // that lands here first still claims what it has been keeping.
  if (window.TargumSync) window.TargumSync.start();

  /* Pasted text is a file like any other; the server has one door for a text and this
     is how something on a clipboard walks through it. Named for its first line, because
     a title is the one thing a paste has no way of carrying. */
  function fromPaste(text) {
    var first = text.split("\n").find(function (line) {
      return line.trim();
    });
    var name = (first || "pasted").trim().slice(0, 60).replace(/[\\/:*?"<>|]+/g, " ");
    return {
      name: name + ".txt",
      // The escape rather than the character: a browser's own base64 refuses anything
      // above U+00FF, and every text this page is for is Hebrew.
      content: btoa(unescape(encodeURIComponent(text))),
    };
  }

  function options() {
    return {
      to: lang.into(document.getElementById("to").value || "en"),
      from: document.getElementById("from").value || "",
      // Always. Being able to tap a word is most of what this is for, and a checkbox
      // asking whether you want that is a question nobody should have to answer.
      words: true,
      // Never from here. A glossary of the whole text is about half of what a build
      // costs and most of it is never read; words are looked up one at a time, from
      // the card, when you actually want one. `targum build --gloss` still buys the lot.
      gloss: false,
    };
  }

  function readFile(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        // Only the base64 payload, not the data: prefix in front of it.
        resolve(String(reader.result).split(",")[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  // One blocking request covers fetching the text, reading it through, and the first
  // time a language is used, some setting up that only ever happens once. A single
  // unchanging line for all of that reads as a hang, so it keeps talking.
  function waiting() {
    var box = document.createDocumentFragment();
    var text = line("Fetching it…");
    var note = document.createElement("p");
    note.className = "hint plain";
    note.textContent = "";
    box.appendChild(text);
    box.appendChild(note);
    var started = Date.now();
    var timer = setInterval(function () {
      var seconds = Math.round((Date.now() - started) / 1000);
      if (!status.contains(note)) return clearInterval(timer);
      note.textContent =
        seconds < 12
          ? ""
          : "Still going. The first in a language takes longer.";
    }, 1000);
    return box;
  }

  go.onclick = function () {
    var payload = options();
    var prepared;

    go.disabled = true;
    say(waiting());

    /* Whatever the reader gave, and then — if they brought a translation — that too,
       read in the same way and sent alongside. */
    function withTranslation(body) {
      var typed = document.getElementById("pasted-translation");
      var text = typed ? typed.value.trim() : "";
      if (!theirs && text) {
        var file = fromPaste(text);
        body.translationName = file.name;
        body.translationContent = file.content;
        return Promise.resolve(body);
      }
      if (!theirs) return Promise.resolve(body);
      return readFile(theirs).then(function (content) {
        body.translationName = theirs.name;
        body.translationContent = content;
        return body;
      });
    }

    var text = pasted ? pasted.value.trim() : "";
    if (chosen) {
      prepared = readFile(chosen).then(function (content) {
        payload.name = chosen.name;
        payload.content = content;
        return withTranslation(payload).then(function (body) {
          return ask("/prepare", body);
        });
      });
    } else if (text) {
      var file = fromPaste(text);
      payload.name = file.name;
      payload.content = file.content;
      prepared = withTranslation(payload).then(function (body) {
        return ask("/prepare", body);
      });
    } else {
      payload.source = sourceInput.value.trim();
      if (!payload.source) {
        go.disabled = false;
        say(line("Paste a link, drop a file, paste the text, or give an id."), true);
        return;
      }
      prepared = withTranslation(payload).then(function (body) {
        return ask("/prepare", body);
      });
    }

    prepared
      .then(function (job) {
        go.disabled = false;
        if (job.error) return say(line(job.error), true);
        if (job.catalogue) return instead(job.catalogue);
        if (job.blocked) return refuse(job);
        offer(job);
      })
      .catch(function (error) {
        go.disabled = false;
        say(line(String(error)), true);
      });
  };

  function describe(job) {
    var what =
      job.chapters > 1
        ? job.chapters + " chapters"
        : job.segments + " sentences";
    return named(job.language) + " · " + what;
  }

  // What it will take, in the only currency the reader is spending: their time. What
  // it costs us is our business and never theirs — they pay by the month.
  function price(job) {
    if (!job.estimate) return "Ready in a moment.";
    // A book opens on its first chapter, so the wait is that chapter's — not the
    // novel's. `total` is what is being translated now.
    var minutes = Math.max(1, Math.round((job.total || job.segments) / 25));
    var start = job.chapters > 1 ? "First chapter in " : "";
    if (minutes <= 1) return start ? start + "about a minute." : "About a minute.";
    if (minutes <= 4) return start ? start + "a couple of minutes." : "A couple of minutes.";
    return start + "about " + minutes + " minutes.";
  }

  // This text is already in the library with a translation somebody published, which is
  // better than a machine one. Said before anything else happens.
  function instead(entry) {
    var box = document.createDocumentFragment();
    var head = document.createElement("p");
    head.className = "instead";
    head.innerHTML = "<b></b>";
    head.querySelector("b").textContent = entry.title;
    head.appendChild(
      document.createTextNode(
        " is in the library already, with " +
          (entry.translations.length === 1
            ? "a translation"
            : entry.translations.length + " translations") +
          " somebody published. Better than a machine."
      )
    );
    var row = document.createElement("div");
    row.className = "row";
    var go = document.createElement("button");
    go.type = "button";
    go.textContent = "Open it";
    go.onclick = function () {
      // The text it just named, not the index it happens to sit on. Every catalogue text
      // has its own page now, so the button can go where it says it goes.
      window.location.href = keyed("/library/" + entry.id);
    };
    row.appendChild(go);
    var anyway = document.createElement("button");
    anyway.type = "button";
    anyway.textContent = "Translate it anyway";
    anyway.onclick = function () {
      // Deliberate, so it is asked for a second time rather than assumed.
      go.disabled = anyway.disabled = true;
      var payload = options();
      payload.force_machine = true;
      say(waiting());
      // The same two ways in as the first attempt. Re-sending only `source` meant a
      // dropped file could never take this branch: the override worked for a pasted
      // link and silently did nothing for an upload.
      var again;
      if (chosen) {
        again = readFile(chosen).then(function (content) {
          payload.name = chosen.name;
          payload.content = content;
          return ask("/prepare", payload);
        });
      } else {
        payload.source = sourceInput.value.trim();
        again = ask("/prepare", payload);
      }
      again
        .then(function (job) {
          if (job.error) return say(line(job.error), true);
          if (job.blocked) return refuse(job);
          offer(job);
        })
        .catch(function () {
          // A dropped connection used to leave both buttons dead with no way forward.
          go.disabled = anyway.disabled = false;
          say(line("That did not go through. Try again."), true);
        });
    };
    row.appendChild(anyway);
    head.appendChild(row);
    box.appendChild(head);
    say(box);
  }

  // Too long or too expensive to translate, said plainly rather than by failing.
  function refuse(job) {
    var box = document.createDocumentFragment();
    var head = document.createElement("p");
    head.style.margin = "0";
    head.innerHTML = "<b></b>";
    head.querySelector("b").textContent = job.title;
    head.appendChild(document.createTextNode(" · " + describe(job)));
    box.appendChild(head);
    var why = document.createElement("span");
    why.className = "cost";
    why.textContent = job.blocked;
    box.appendChild(why);
    say(box, true);
  }

  // The cost is shown before anything is spent, the same gate the command line uses.
  function offer(job) {
    var box = document.createDocumentFragment();
    var head = document.createElement("p");
    head.style.margin = "0";
    head.innerHTML = "<b></b>";
    head.querySelector("b").textContent = job.title;
    head.appendChild(document.createTextNode(" · " + describe(job)));
    box.appendChild(head);

    var cost = document.createElement("span");
    cost.className = "cost";
    cost.textContent = price(job);
    box.appendChild(cost);

    var row = document.createElement("div");
    row.className = "row";
    var confirm = document.createElement("button");
    confirm.type = "button";
    confirm.textContent = "Start reading";
    confirm.onclick = function () {
      ask("/build", { id: job.id }).then(function (state) {
        if (state.blocked) return refuse(state);
        watch(job);
      });
    };
    row.appendChild(confirm);
    box.appendChild(row);
    say(box);
  }

  var PLAIN = {
    "Finding each word's dictionary form…": "Reading the words…",
    "Adding vowel points…": "Adding vowel points…",
    "Building the reader…": "Setting the page…",
  };

  function plain(message) {
    if (!message) return "Getting it ready…";
    if (PLAIN[message]) return PLAIN[message];
    if (message.indexOf("Matching") === 0) return "Lining up…";
    if (message.indexOf("Looking up") === 0) return "Looking words up…";
    return "Getting it ready…";
  }

  function watch(job) {
    var box = document.createDocumentFragment();
    var text = line("Getting it ready…");
    var bar = document.createElement("div");
    bar.className = "bar";
    bar.appendChild(document.createElement("i"));
    box.appendChild(text);
    box.appendChild(bar);
    say(box);

    var timer = setInterval(function () {
      ask("/job/" + job.id).then(function (state) {
        if (state.error) {
          clearInterval(timer);
          return say(line(state.error), true);
        }
        // The pipeline narrates itself in its own vocabulary. This is the reader's.
        text.textContent = state.done
          ? "Getting it ready… " + Math.round((state.done / state.total) * 100) + "%"
          : plain(state.message);
        var share = state.total ? state.done / state.total : 0;
        status.querySelector(".bar i").style.width = (share * 100).toFixed(1) + "%";
        if (state.stage === "done") {
          clearInterval(timer);
          // A cover, always, and after the text is readable rather than before it: it is
          // a picture for the shelf and nobody should wait on a picture to start reading.
          // Asked for and left running — the server has the job either way.
          var name = String(state.reader || "").split("/")[0];
          var drawing = name
            ? ask("/cover", { name: name }).catch(function () {})
            : Promise.resolve();
          drawing.then(function () {
            window.location.href = keyed("/reader/" + state.reader.split("/").map(encodeURIComponent).join("/"));
          });
        }
      });
    }, 700);
  }

  /* --- getting about ------------------------------------------------------- */

  Array.prototype.forEach.call(document.querySelectorAll(".site-nav a, .to-library"), function (link) {
    link.href = keyed(link.getAttribute("href"));
  });
})();
