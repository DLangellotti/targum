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

  function named(code) {
    return languageNames[code] || (code || "").toUpperCase();
  }
  var drop = document.getElementById("drop");
  var fileInput = document.getElementById("file");
  var sourceInput = document.getElementById("source");
  var go = document.getElementById("go");
  var status = document.getElementById("status");
  var chosen = null;

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

  // Typing a link puts the file down. Leaving the filename on screen while the link is
  // what gets used left no way to tell which of the two would win.
  sourceInput.addEventListener("input", function () {
    if (sourceInput.value.trim() && chosen) forget();
  });

  /* --- building ------------------------------------------------------------ */

  // The language chosen here is the one the library and the words page open on.
  (function () {
    var from = document.getElementById("from");
    var note = document.getElementById("from-beta");
    var names = window.TARGUM_LANGUAGES || {};
    var lang = window.TargumLang;
    var was = lang.current(Object.keys(names));
    if (was) from.value = was;
    function say() {
      var code = from.value;
      note.hidden = !code || !lang.beta(code);
      if (!note.hidden) note.textContent = lang.betaNote(code, names);
      if (code) lang.set(code);
    }
    from.addEventListener("change", say);
    say();
  })();

  // Nothing on this page is drawn from the word list, so there is nothing to redraw:
  // sync runs here only so the header can say who is signed in, and so that a browser
  // that lands here first still claims what it has been keeping.
  if (window.TargumSync) window.TargumSync.start();

  function options() {
    return {
      to: document.getElementById("to").value || "en",
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

    if (chosen) {
      prepared = readFile(chosen).then(function (content) {
        payload.name = chosen.name;
        payload.content = content;
        return ask("/prepare", payload);
      });
    } else {
      payload.source = sourceInput.value.trim();
      if (!payload.source) {
        go.disabled = false;
        say(line("Paste a link, drop a file, or give an id."), true);
        return;
      }
      prepared = ask("/prepare", payload);
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

  // This text is already in the library with a translation somebody published, which
  // is both better than a machine one and free. Said before anything is priced.
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
          " somebody published. Better than a machine, and free."
      )
    );
    var row = document.createElement("div");
    row.className = "row";
    var go = document.createElement("button");
    go.type = "button";
    go.textContent = "Open it";
    go.onclick = function () {
      window.location.href = keyed("/library");
    };
    row.appendChild(go);
    var anyway = document.createElement("button");
    anyway.type = "button";
    anyway.textContent = "Translate it anyway";
    anyway.onclick = function () {
      // Deliberate, so it is asked for a second time rather than assumed.
      go.disabled = anyway.disabled = true;
      var payload = options();
      payload.source = sourceInput.value.trim();
      payload.force_machine = true;
      say(waiting());
      ask("/prepare", payload).then(function (job) {
        if (job.error) return say(line(job.error), true);
        if (job.blocked) return refuse(job);
        offer(job);
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
          window.location.href =
            keyed("/reader/" + state.reader);
        }
      });
    }, 700);
  }

  /* --- getting about ------------------------------------------------------- */

  Array.prototype.forEach.call(document.querySelectorAll(".site-nav a, .to-library"), function (link) {
    link.href = keyed(link.getAttribute("href"));
  });
})();
