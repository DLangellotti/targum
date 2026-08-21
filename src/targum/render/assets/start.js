/* The start page. Reads a file or a link, prices the translation, and only spends
   once you have seen the number. */

(function () {
  "use strict";

  var key = window.TARGUM_KEY;
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
    return fetch(path + "?k=" + encodeURIComponent(key), {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", "X-Targum-Key": key },
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

  function take(file) {
    chosen = file;
    sourceInput.value = "";
    drop.querySelector(".drop-label").textContent = file.name;
    drop.querySelector(".drop-note").textContent = Math.round(file.size / 1024) + " KB";
  }

  sourceInput.addEventListener("input", function () {
    if (sourceInput.value.trim()) chosen = null;
  });

  /* --- building ------------------------------------------------------------ */

  function options() {
    return {
      to: document.getElementById("to").value || "en",
      from: document.getElementById("from").value || "",
      // Always. Being able to tap a word is most of what this is for, and a checkbox
      // asking whether you want that is a question nobody should have to answer.
      words: true,
      gloss: true,
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

  go.onclick = function () {
    var payload = options();
    var prepared;

    go.disabled = true;
    say(line("Reading and splitting into sentences…"));

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
        say(line("Give a link, an identifier, or a file."), true);
        return;
      }
      prepared = ask("/prepare", payload);
    }

    prepared
      .then(function (job) {
        go.disabled = false;
        if (job.error) return say(line(job.error), true);
        if (job.blocked) return refuse(job);
        offer(job);
      })
      .catch(function (error) {
        go.disabled = false;
        say(line(String(error)), true);
      });
  };

  // Too long or too expensive to translate, said plainly rather than by failing.
  function refuse(job) {
    var box = document.createDocumentFragment();
    var head = document.createElement("p");
    head.style.margin = "0";
    head.innerHTML = "<b></b>";
    head.querySelector("b").textContent = job.title;
    head.appendChild(
      document.createTextNode(" — " + job.language + ", " + job.segments + " sentences")
    );
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
    head.appendChild(
      document.createTextNode(" — " + job.language + ", " + job.segments + " sentences")
    );
    box.appendChild(head);

    var cost = document.createElement("span");
    cost.className = "cost";
    cost.textContent = job.estimate
      ? "Translating it costs about $" + job.estimate.toFixed(2) + "."
      : "Nothing to pay for this one.";
    box.appendChild(cost);

    var row = document.createElement("div");
    row.className = "row";
    var confirm = document.createElement("button");
    confirm.type = "button";
    confirm.textContent = "Translate it";
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

  function watch(job) {
    var box = document.createDocumentFragment();
    var text = line("Translating…");
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
        text.textContent =
          state.message || "Translating… " + state.done + " of " + state.total;
        var share = state.total ? state.done / state.total : 0;
        status.querySelector(".bar i").style.width = (share * 100).toFixed(1) + "%";
        if (state.stage === "done") {
          clearInterval(timer);
          window.location.href =
            "/reader/" + state.reader + "?k=" + encodeURIComponent(key);
        }
      });
    }, 700);
  }

  /* --- your library ------------------------------------------------------- */

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  function ago(stamp) {
    if (!stamp) return "";
    var minutes = Math.round((Date.now() - stamp) / 60000);
    if (minutes < 2) return "just now";
    if (minutes < 60) return minutes + " minutes ago";
    var hours = Math.round(minutes / 60);
    if (hours < 24) return hours === 1 ? "an hour ago" : hours + " hours ago";
    var days = Math.round(hours / 24);
    if (days === 1) return "yesterday";
    if (days < 30) return days + " days ago";
    return new Date(stamp).toLocaleDateString();
  }

  function plural(count, one) {
    return count + " " + one + (count === 1 ? "" : "s");
  }

  /* --- exporting everything ------------------------------------------------ */

  function csvCell(value) {
    var text = value === undefined || value === null ? "" : String(value);
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function download(name, csv) {
    // A byte order mark, so a spreadsheet opens Hebrew and Russian as UTF-8.
    var blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  // Everything kept in one language, across every text, with the same word from two
  // articles folded into one row that names both.
  function exportLanguage(master, language) {
    var byKey = {};
    var order = [];
    Object.keys(master).forEach(function (id) {
      var book = master[id];
      if (book.language !== language) return;
      (book.entries || []).forEach(function (entry) {
        var key = entry.kind + ":" + (entry.lemma || entry.text);
        if (!byKey[key]) {
          byKey[key] = {
            text: entry.text,
            lemma: entry.lemma,
            level: entry.level,
            kind: entry.kind,
            meaning: entry.meaning,
            from: [],
          };
          order.push(key);
        }
        if (byKey[key].from.indexOf(book.title) === -1) byKey[key].from.push(book.title);
      });
    });

    var header = ["text", "dictionary form", "difficulty", "kind", "meaning", "from"];
    var rows = order.map(function (key) {
      var row = byKey[key];
      return [row.text, row.lemma, row.level, row.kind, row.meaning, row.from.join("; ")];
    });
    download(
      "targum " + language + " words.csv",
      [header].concat(rows).map(function (row) {
        return row.map(csvCell).join(",");
      }).join("\n")
    );
  }

  function exportButtons(master, languages) {
    var box = document.getElementById("library-export");
    var note = document.getElementById("library-note");
    if (!box) return;
    box.textContent = "";

    languages.forEach(function (language) {
      var button = document.createElement("button");
      button.type = "button";
      button.textContent =
        languages.length > 1 ? named(language) + " CSV" : "Export CSV";
      button.onclick = function () {
        exportLanguage(master, language);
      };
      box.appendChild(button);
    });

    // Said on the page rather than hidden in a tooltip, and next to the button it
    // describes: this is the list you built as you read, not the meanings that appear
    // when you tap a word.
    if (note) {
      note.hidden = !languages.length;
      note.textContent = languages.length ? "words and phrases you saved" : "";
    }
  }

  ask("/library").then(function (data) {
    var readers = data.readers || [];
    if (!readers.length) return;

    var master = stored("targum:master");
    var opened = stored("targum:opened");
    var list = document.getElementById("library-list");

    // What you are part way through comes first, then whatever is newest.
    readers.forEach(function (reader) {
      reader.saved = (master[reader.document] || {}).entries || [];
      reader.opened = opened[reader.document] || 0;
    });
    readers.sort(function (a, b) {
      return b.opened - a.opened || b.built * 1000 - a.built * 1000;
    });

    // What you have kept, counted per language: someone reading Hebrew and Russian
    // wants two totals, not one meaningless sum.
    var tally = {};
    Object.keys(master).forEach(function (id) {
      var book = master[id];
      (book.entries || []).forEach(function (entry) {
        var counts = tally[book.language] || (tally[book.language] = { words: 0, phrases: 0 });
        if (entry.kind === "phrase") counts.phrases += 1;
        else counts.words += 1;
      });
    });

    var languages = Object.keys(tally).sort();
    var summary = document.getElementById("library-sum");
    summary.textContent = languages
      .map(function (code) {
        var counts = tally[code];
        var parts = [plural(counts.words, "word")];
        if (counts.phrases) parts.push(plural(counts.phrases, "phrase"));
        return named(code) + ": " + parts.join(", ");
      })
      .join(" · ");

    // One export per language, since a study list mixing two is not much use.
    exportButtons(master, languages);

    readers.forEach(function (reader) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href =
        "/reader/" + reader.name + "/reader/index.html?k=" + encodeURIComponent(key);

      var main = document.createElement("span");
      main.className = "book-main";

      var title = document.createElement("span");
      title.className = "book-title";
      var name = document.createElement("bdi");
      name.setAttribute("lang", reader.language || "und");
      name.textContent = reader.title;
      title.appendChild(name);
      main.appendChild(title);

      var facts = [];
      if (reader.saved.length) facts.push(plural(reader.saved.length, "word") + " kept");
      if (reader.sections > 1) facts.push(plural(reader.sections, "section"));
      facts.push(reader.opened ? "read " + ago(reader.opened) : "not opened yet");

      var meta = document.createElement("span");
      meta.className = "book-meta";
      meta.textContent = facts.join(" · ");
      main.appendChild(meta);
      link.appendChild(main);

      var lang = document.createElement("span");
      lang.className = "book-lang";
      lang.textContent = reader.language;
      link.appendChild(lang);

      item.appendChild(link);
      list.appendChild(item);
    });
    document.getElementById("library").hidden = false;
  });
})();
