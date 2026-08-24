/* The vocabulary store, and the one-time move into it.
 *
 * Shared by the reader, which writes it, and the words page, which reads it. The move
 * lived in the reader alone to begin with, which meant anyone who opened the words page
 * before opening a text was told they had kept nothing: their words were still in the
 * per-document lists that came before, and nothing on that page knew to look there.
 */
(function () {
  "use strict";

  var LEARNING = [1, 2, 3];

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback) || JSON.parse(fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
  }

  function write(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {}
  }

  function stamp(index) {
    return Date.now() + index;
  }

  // Everything kept before words became a per-language thing, moved across once.
  //
  // `language` and `documentId` are what the caller knows about the page it is on; the
  // reader passes both, the words page neither. They are only a fallback for a saved
  // list whose language cannot be worked out from the indexes.
  function migrate(language, documentId) {
    var done = read("targum:migrated", "{}");
    if (done.vocab) return;

    var master = read("targum:master", "{}");
    var docs = read("targum:docs", "{}");
    var moved = {};
    var order = 0;

    function bucket(code) {
      var tag = (code || "und").split("-")[0].toLowerCase();
      var name = "targum:vocab:" + tag;
      if (!moved[name]) moved[name] = read(name, "{}");
      return moved[name];
    }

    function keep(into, lemma, surface, meaning, band, at) {
      if (!lemma || into[lemma]) return;
      into[lemma] = {
        status: LEARNING[0],
        surface: surface || lemma,
        meaning: meaning || "",
        // The old field called "level" held a difficulty band, never a status.
        band: band || "",
        at: at || stamp(order++),
      };
    }

    // Every per-document list still in the browser, whichever text it belongs to. The
    // language comes from one of the two indexes, or from the page asking.
    var saved = [];
    for (var i = 0; i < localStorage.length; i++) {
      var name = localStorage.key(i);
      if (name && name.indexOf("targum:saved:") === 0) saved.push(name);
    }
    saved.forEach(function (name) {
      var hash = name.slice("targum:saved:".length);
      var code =
        (master[hash] || {}).language ||
        (docs[hash] || {}).language ||
        (hash === documentId ? language : "");
      if (!code) return;
      var into = bucket(code);
      var list = read(name, "{}");
      Object.keys(list).forEach(function (lemma) {
        var item = list[lemma] || {};
        keep(into, lemma, item.surface, item.meaning, item.level, item.at);
      });
    });

    // And the index itself, which is where a list lives once its own key has gone.
    Object.keys(master).forEach(function (hash) {
      var record = master[hash] || {};
      var into = bucket(record.language);
      (record.entries || []).forEach(function (row) {
        if (row.kind !== "word") return;
        keep(into, row.lemma, row.text, row.meaning, row.level, 0);
      });
    });

    Object.keys(moved).forEach(function (name) {
      write(name, moved[name]);
    });
    done.vocab = Date.now();
    write("targum:migrated", done);
  }

  /* --- saying how well you know it, and what you think it means -------------- */

  var KNOWN = 9;
  var IGNORED = 0;

  var STEPS = [
    { value: 1, label: "1", title: "Just met it" },
    { value: 2, label: "2", title: "Getting there" },
    { value: 3, label: "3", title: "Nearly know it" },
    { value: KNOWN, label: "known", title: "Known" },
    { value: IGNORED, label: "ignore", title: "A name or a number" },
  ];

  // One control, used by the word card, the phrase card, the list beside the text and
  // the words page. They ask the same two questions — how well do you know this, and
  // what do you want it to say — so they ask them the same way.
  //
  // `options.status` is what it is now; `onStatus` is handed the new one, or null when
  // the setting is taken off by pressing the one already chosen. `onNote` is handed the
  // text you typed, on the way out of the field rather than on every keystroke.
  function editor(options) {
    var box = document.createElement("div");
    box.className = "vocab-editor";
    var field = null;

    // Typing a meaning and then pressing a level is the ordinary way to use this, so
    // the note is saved as it is typed rather than on the way out of the field. Waiting
    // for blur put the save between the press and its handling, and the press was lost.
    var pending = null;

    function commitNote() {
      if (!field || !options.onNote) return;
      var text = field.value.trim();
      if (text === (options.note || "")) return;
      options.note = text;
      options.onNote(text);
    }

    var scale = document.createElement("div");
    scale.className = "levels";
    STEPS.forEach(function (step) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "level level-" + step.value;
      button.textContent = step.label;
      button.title = step.title;
      var on = options.status === step.value;
      button.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) button.classList.add("on");
      button.addEventListener("click", function (event) {
        event.stopPropagation();
        commitNote();
        if (options.onStatus) options.onStatus(on ? null : step.value);
      });
      scale.appendChild(button);
    });
    box.appendChild(scale);

    if (options.onNote) {
      var note = (field = document.createElement("input"));
      note.type = "text";
      note.className = "note-field";
      note.value = options.note || "";
      note.placeholder = options.placeholder || "Your own meaning";
      note.setAttribute("aria-label", "Your own meaning");
      note.addEventListener("click", function (event) {
        event.stopPropagation();
      });
      note.addEventListener("keydown", function (event) {
        event.stopPropagation();
        if (event.key === "Enter") note.blur();
        if (event.key === "Escape") {
          note.value = options.note || "";
          note.blur();
        }
      });
      // On the way out, not on every keystroke: a store written per character is a
      // store written a hundred times for one definition.
      note.addEventListener("input", function () {
        clearTimeout(pending);
        pending = setTimeout(commitNote, 400);
      });
      // Belt and braces for a field left in a hurry.
      note.addEventListener("change", commitNote);
      note.addEventListener("blur", commitNote);
      box.appendChild(note);
    }
    return box;
  }

  window.TargumVocab = {
    migrate: migrate,
    read: read,
    editor: editor,
    STEPS: STEPS,
    LEARNING: LEARNING,
    KNOWN: KNOWN,
    IGNORED: IGNORED,
  };
})();
