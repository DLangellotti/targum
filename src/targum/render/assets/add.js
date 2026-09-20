/* Adding a text targum does not have, in any medium. One box takes a file, several
   files, a link, some of the language being added or a description; a line under it says what targum thinks it
   was given; every choice sits behind Change. Prices before anything is spent, and only
   spends once you have seen the number (design.md §12, 2026-09-13, targum-internal#249). */

(function () {
  "use strict";

  // The page's words in the reader's language, from `strings.js` (targum-internal#184).
  var t = window.TargumStrings.t;
  var tn = window.TargumStrings.tn;
  var CHANGE_LANGUAGE = t("add.change-language", "Choose its language under Change.");
  var WE_TRANSLATE = t("add.summary.we-translate", "we translate");

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
  //: The one box: a link, a text, or what the reader wants to read.
  var given = document.getElementById("given");
  var understood = document.getElementById("understood");
  var givenFiles = document.getElementById("given-files");
  var askTargum = document.getElementById("ask-targum");
  var summary = document.getElementById("summary");
  var summaryLine = document.getElementById("summary-line");
  var change = document.getElementById("change");
  var choices = document.getElementById("options");
  var go = document.getElementById("go");
  var status = document.getElementById("status");
  var chosen = null;
  //: The translation the reader brought, if they brought one.
  var theirs = null;
  //: The last link that could not be fetched. A reel Instagram refused, downloaded and
  //: dropped in next, is still that reel: the link goes up with the file, and the server
  //: keeps it only if it is a video host's own address (targum-internal#255).
  var cameFrom = "";

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

  /* --- the box -------------------------------------------------------------
   *
   * It never asks what kind of thing it was given. A file is known by its name, words
   * by their script and their length, and files that belong together are paired: a
   * recording with a subtitle file is a recording with its own transcript, and a text
   * with another in a Latin script is a text with its translation. Where a pairing
   * cannot tell, the first file is kept and the line says what to do with the other.
   *
   * The language is not guessed. Hebrew, Yiddish and Aramaic share a script, and a
   * reader cannot check a guess on a build they are about to pay for; the summary line
   * names the language last chosen, where it can be seen, and Change is where it is
   * changed. What the box does know is which letters that language is written in, and
   * those are the letters it looks for: with Italian chosen a paste of Italian is a text,
   * and nothing on the page says Hebrew (2026-09-14).
   */

  var RESTING = understood ? understood.textContent : "";
  var SUBTITLES = /\.(srt|vtt)$/i;
  var TEXTUAL = /\.(txt|md|markdown)$/i;
  var MOVING = /\.(mp4|m4v|mov|webm|mkv)$/i;
  var LINK = /^https?:\/\/\S+$/i;
  //: A source targum reads directly, by its id (`ingest/fetch/__init__.py` FETCHERS).
  var IDENTIFIER = /^(gutenberg|sefaria|siddur|wikisource|dialogue|weekly|video):\S+$/i;
  //: Under this many words, a text is as likely a request as a text to read.
  var FEW = 12;
  //: Over this many words, words that are not the language being added are a text in
  //: some other language, not a request.
  var DESCRIBED = 40;

  //: Which letters each language that may be added is written in, and what they are
  //: called. A fact about writing rather than a setting; a language missing here is read
  //: as Hebrew letters, which is what the page did for all of them before 2026-09-14.
  var HEBREW = { letters: /[\u0590-\u05FF\uFB1D-\uFB4F]/g, called: t("add.script.hebrew", "Hebrew letters"), rtl: true };
  var LATIN = { letters: /\p{Script=Latin}/gu, called: t("add.script.latin", "the Latin alphabet"), rtl: false };
  var SCRIPTS = {
    he: HEBREW,
    yi: HEBREW,
    arc: HEBREW,
    ru: { letters: /\p{Script=Cyrillic}/gu, called: t("add.script.cyrillic", "Cyrillic letters"), rtl: false },
    fr: LATIN,
    it: LATIN,
  };

  //: English words that are not also words of French or Italian. A request is written in
  //: English and so is a translation, and with a language in the Latin alphabet chosen
  //: the letters alone cannot tell either of them from a text.
  var ENGLISH = /^(the|and|of|to|is|are|was|were|be|been|with|about|what|which|who|why|how|where|when|that|this|these|those|my|you|your|it|for|from|some|something|want|would|could|like|please|find|read|much|any|can|not|does|have|has|by|at|there|they|we|our|their|its|an|into|than|then)$/;

  // The language being added: the one the menu at the top shows.
  function adding() {
    var from = document.getElementById("from");
    return (from && from.value) || "he";
  }

  function scriptOf(code) {
    return SCRIPTS[code] || HEBREW;
  }

  // The share of the letters that are in the script of the language being added.
  function share(text, code) {
    var letters = String(text).match(/\p{L}/gu) || [];
    if (!letters.length) return 0;
    var ours = String(text).match(scriptOf(code).letters) || [];
    return ours.length / letters.length;
  }

  // Whether the words are English rather than the language being added. Only asked where
  // the two share an alphabet; anywhere else the letters have already said.
  function english(text, code) {
    if (scriptOf(code) !== LATIN) return false;
    var words = String(text).toLowerCase().match(/[a-z']+/g) || [];
    if (!words.length) return false;
    var hits = words.filter(function (word) {
      return ENGLISH.test(word);
    }).length;
    return hits / words.length >= 0.2;
  }

  // Whether some words are a text in the language being added.
  function inLanguage(text, code) {
    return share(text, code) >= 0.5 && !english(text, code);
  }

  // What the words in the box are.
  function readGiven() {
    var text = given ? given.value.trim() : "";
    if (!text) return { kind: "empty", text: "" };
    if (LINK.test(text) || IDENTIFIER.test(text)) return { kind: "link", text: text };
    // A link with a few words after it — "https://… the article about the election" —
    // is still the link (2026-09-14). It was read as a description, and Continue then
    // said the same sentence again, as an error.
    var leading = /^(https?:\/\/\S+)\s+(?!https?:)[\s\S]*$/i.exec(text);
    if (leading) return { kind: "link", text: leading[1] };
    var words = text.split(/\s+/).length;
    if (inLanguage(text, adding())) {
      var sentence = /[.!?׃:]\s*$|[.!?׃]\s/.test(text);
      return { kind: words <= FEW && !sentence ? "few" : "text", text: text, words: words };
    }
    if (words <= DESCRIBED) return { kind: "description", text: text, words: words };
    return { kind: "foreign", text: text, words: words };
  }

  function medium(file) {
    if (isAudio(file)) return MOVING.test(file.name) ? "video" : "recording";
    if (SUBTITLES.test(file.name)) return "subtitles";
    if (bringing.isPicture(file)) return "picture";
    if (bringing.isPdf(file)) return "pdf";
    if (/\.epub$/i.test(file.name)) return "book";
    if (TEXTUAL.test(file.name)) return "text";
    return "other";
  }

  // The first few kilobytes of a text file, which is enough to know its script.
  function head(file) {
    return new Promise(function (resolve) {
      var reader = new FileReader();
      reader.onload = function () {
        resolve(String(reader.result || ""));
      };
      reader.onerror = function () {
        resolve("");
      };
      reader.readAsText(file.slice(0, 4096));
    });
  }

  //: What the last pairing had to say, when it could not pair.
  var unpaired = "";
  //: What the box paired by itself, so that new files put down only that, and never a
  //: translation or a transcript the reader brought under Change.
  var paired = { translation: false, transcript: false };

  function putDownPaired() {
    if (paired.translation) translationHalf.putDown();
    if (paired.transcript) transcriptHalf.putDown();
    paired = { translation: false, transcript: false };
  }

  function hold(files) {
    chosen = files && files.length ? files : null;
    if (window.TargumAddAudio) {
      window.TargumAddAudio.toggle(!!chosen && chosen.length === 1 && isAudio(chosen[0]));
    }
    var row = document.getElementById("translation-row");
    // A recording, a PDF or pictures go up in pieces, and a translation is not sent
    // with them: the row that offers one is not there.
    if (row) row.hidden = !!chosen && inPieces(chosen);
  }

  // Files from the box, the picker or the clipboard: whatever was held is put down,
  // along with anything paired to it, and the new files are paired afresh.
  function take(files) {
    var list = bringing.listed(files);
    if (!list.length) return Promise.resolve();
    if (given) given.value = "";
    unpaired = "";
    putDownPaired();
    var kinds = list.map(medium);
    function count(kind) {
      return kinds.filter(function (one) {
        return one === kind;
      }).length;
    }
    function first(kind) {
      return list[kinds.indexOf(kind)];
    }

    if (list.length === 2 && count("recording") + count("video") === 1 && count("subtitles") === 1) {
      hold([first("recording") || first("video")]);
      transcriptHalf.take(first("subtitles"));
      paired.transcript = true;
      settle();
      return Promise.resolve();
    }
    if (list.length === 2 && count("text") === 2) {
      return Promise.all(list.map(head)).then(function (heads) {
        var code = adding();
        var ours = heads.map(function (text) {
          return inLanguage(text, code);
        });
        var text = ours[0] ? 0 : ours[1] ? 1 : -1;
        if (text < 0 || ours[1 - text]) {
          hold([list[0]]);
          unpaired =
            text < 0
              ? t(
                  "add.unpaired.neither",
                  "Neither reads as {language}, so we'll use only {file}. You can add a translation under Change.",
                  { language: named(code), file: list[0].name }
                )
              : t(
                  "add.unpaired.both",
                  "Both read as {language}, so we'll use only {file}. You can add a translation under Change.",
                  { language: named(code), file: list[0].name }
                );
        } else {
          hold([list[text]]);
          translationHalf.take(list[1 - text]);
          paired.translation = true;
        }
        settle();
      });
    }
    if (list.length > 1 && count("picture") === list.length) {
      hold(list);
    } else if (list.length > 1) {
      hold([list[0]]);
      unpaired = t(
        "add.unpaired.many",
        "We'll use only {file}. Files go together as a recording and its subtitles, or a text and its translation.",
        { file: list[0].name }
      );
    } else {
      hold(list);
    }
    settle();
    return Promise.resolve();
  }

  function forget() {
    unpaired = "";
    hold(null);
    putDownPaired();
    fileInput.value = "";
    settle();
  }

  function sized(files) {
    var total = 0;
    files.forEach(function (file) {
      total += file.size || 0;
    });
    return total >= 1048576 ? (total / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(total / 1024)) + " KB";
  }

  // One chip per file in the box, and one for whatever was paired to it.
  function drawFiles() {
    if (!givenFiles) return;
    givenFiles.textContent = "";
    var rows = [];
    if (chosen) {
      rows.push({
        label: chosen.length === 1 ? chosen[0].name : tn("add.photos", chosen.length, "{n} photo of pages", "{n} photos of pages"),
        size: sized(chosen),
        remove: forget,
      });
    }
    var transcript = transcriptHalf.held();
    if (transcript) rows.push({ label: transcript.name, role: t("add.role.transcript", "transcript"), size: sized([transcript]), remove: transcriptHalf.putDown });
    if (theirs) rows.push({ label: theirs.name, role: t("add.role.translation", "translation"), size: sized([theirs]), remove: translationHalf.putDown });
    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.className = "given-file";
      var name = document.createElement("span");
      name.className = "given-file-name";
      name.textContent = row.label;
      li.appendChild(name);
      var meta = document.createElement("span");
      meta.className = "given-file-meta";
      meta.textContent = (row.role ? row.role + " · " : "") + row.size;
      li.appendChild(meta);
      var x = document.createElement("button");
      x.type = "button";
      x.className = "given-file-x";
      x.setAttribute("aria-label", t("add.remove", "Remove {file}", { file: row.label }));
      x.textContent = "×";
      x.onclick = function () {
        row.remove();
        settle();
      };
      li.appendChild(x);
      givenFiles.appendChild(li);
    });
    givenFiles.hidden = !rows.length;
    if (given) given.hidden = !!chosen;
  }

  // What targum thinks it was given, in a sentence.
  function understanding() {
    if (chosen) {
      var kind = medium(chosen[0]);
      var transcript = transcriptHalf.held();
      var said = {
        recording: t("add.thanks.recording", "Thanks for the recording."),
        video: t("add.thanks.video", "Thanks for the video."),
        subtitles: t("add.thanks.subtitles", "Thanks for the subtitles. We'll read them as a text."),
        picture:
          chosen.length > 1
            ? t("add.thanks.photos", "Thanks for the photos. We'll read all {n} pages as one text.", { n: chosen.length })
            : t("add.thanks.photo", "Thanks for the photo. We'll read the page as it's printed."),
        pdf: t("add.thanks.pdf", "Thanks for the PDF."),
        book: t("add.thanks.book", "Thanks for the book."),
        text: t("add.thanks.text", "Thanks for the text."),
        other: t("add.thanks.other", "Thanks for the file."),
      }[kind];
      if (kind === "recording" || kind === "video") {
        said +=
          " " +
          (transcript
            ? t("add.spoken.theirs", "We'll use the transcript that came with it, so there's nothing to write down.")
            : t("add.spoken.ours", "We'll write down what's said, and that uses some of your hours."));
      }
      if (theirs) said += " " + t("add.translation.theirs", "We'll line up your translation with it, sentence by sentence.");
      return unpaired ? said + " " + unpaired : said;
    }
    var read = readGiven();
    if (read.kind === "link") return t("add.thanks.link", "Thanks for the link. We'll work out how long it'll take.");
    if (read.kind === "text") {
      return tn("add.words", read.words, "That's {n} word of {language}.", "That's {n} words of {language}.", {
        language: named(adding()),
      });
    }
    if (read.kind === "few") {
      return talks()
        ? t("add.few.talks", "A few words. Continue and we'll read them as a text, or Ask targum and we'll find something to read.")
        : t("add.few", "A few words. We'll read them as a text.");
    }
    if (read.kind === "description") {
      return talks()
        ? t("add.description.talks", "That sounds like what you want to read. Ask targum and we'll look for it.")
        : t("add.description", "That sounds like what you want to read. Paste a link or the text itself here.");
    }
    if (read.kind === "foreign") {
      var code = adding();
      return english(read.text, code)
        ? t("add.foreign.english", "You're adding {language}, and this reads as English.", { language: named(code) }) +
            " " +
            CHANGE_LANGUAGE
        : t("add.foreign.script", "You're adding {language}, and this isn't in {script}.", {
            language: named(code),
            script: scriptOf(code).called,
          }) +
            " " +
            CHANGE_LANGUAGE;
    }
    return RESTING;
  }

  // What Translation says under its two choices.
  function lineUp(mine) {
    return mine
      ? t("add.how.mine", "We'll line it up with the {language}, sentence by sentence.", { language: named(adding()) })
      : t("add.how.ours", "We'll translate it, sentence by sentence.");
  }

  // Whether the conversation is on this page to ask in.
  function talks() {
    return !!(window.TargumTalk && window.TargumTalk.say);
  }

  // Every choice on one line, and Change at the end of it.
  function summarise() {
    var from = document.getElementById("from");
    var to = document.getElementById("to");
    var parts = [named(from && from.value) + " → " + named(to && to.value)];
    var typed = document.getElementById("pasted-translation");
    if (!(chosen && inPieces(chosen))) {
      parts.push(theirs || (typed && typed.value.trim()) ? t("add.summary.your-translation", "your translation") : WE_TRANSLATE);
    } else {
      parts.push(WE_TRANSLATE);
    }
    if (chosen && chosen.length === 1 && isAudio(chosen[0])) {
      parts.push(
        transcriptHalf.held() ? t("add.summary.your-transcript", "your transcript") : t("add.summary.we-transcribe", "we transcribe")
      );
    }
    return parts.join(" · ");
  }

  // Everything the box says, drawn again from what it holds.
  function settle() {
    drawFiles();
    var name = named(adding());
    if (given) {
      given.placeholder = t("add.given.placeholder", "Paste a link or some {language}, drop a file, or say what you want", {
        language: name,
      });
      given.setAttribute(
        "aria-label",
        t("add.given.label", "A link, some {language}, or what you're looking for", { language: name })
      );
    }
    var note = document.getElementById("how-note");
    var mine = document.querySelector('[data-how="mine"]');
    if (note && mine) note.textContent = lineUp(mine.getAttribute("aria-pressed") === "true");
    var read = readGiven();
    if (understood) understood.textContent = understanding();
    var something = !!chosen || read.kind === "link" || read.kind === "text" || read.kind === "few";
    if (askTargum) askTargum.hidden = chosen !== null || !talks() || (read.kind !== "description" && read.kind !== "few");
    if (summary) {
      summary.hidden = !something && (!choices || choices.hidden);
      summaryLine.textContent = summarise();
    }
  }

  // Change: the manual page, open for whoever opened it last in this browser.
  var OPENED = "targum:add-choices";
  function openChoices(on) {
    if (!choices || !change) return;
    choices.hidden = !on;
    change.setAttribute("aria-expanded", on ? "true" : "false");
    change.textContent = on ? t("add.done", "Done") : t("add.change", "Change");
    try {
      if (on) localStorage.setItem(OPENED, "open");
      else localStorage.removeItem(OPENED);
    } catch (e) {
      /* nowhere to keep it; the choices still open */
    }
    settle();
  }
  if (change) {
    change.onclick = function () {
      openChoices(choices.hidden);
    };
  }
  if (choices) {
    // A choice made there is said on the line at once.
    choices.addEventListener("click", function () {
      setTimeout(settle, 0);
    });
    choices.addEventListener("change", settle);
    choices.addEventListener("input", settle);
  }

  document.getElementById("choose").onclick = function () {
    fileInput.click();
  };

  fileInput.onchange = function () {
    if (fileInput.files[0]) take(Array.prototype.slice.call(fileInput.files));
  };

  // The whole box is where a file is dropped.
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
    var files = event.dataTransfer && event.dataTransfer.files;
    if (files && files[0]) take(Array.prototype.slice.call(files));
  });

  if (given) {
    given.addEventListener("input", settle);
    // Typing is starting over; a file dropped after that is not the refused link's.
    given.addEventListener("input", function () {
      cameFrom = "";
    });
    // A screenshot on the clipboard is a file like any other.
    given.addEventListener("paste", function (event) {
      var files = event.clipboardData && event.clipboardData.files;
      if (files && files.length) {
        event.preventDefault();
        take(Array.prototype.slice.call(files));
      }
    });
    // A pasted text keeps its lines; ⌘ or Ctrl with Enter is Continue.
    given.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        go.click();
      }
    });
  }

  // Said in the conversation, by the reader's own press: a description is a turn of it.
  if (askTargum) {
    askTargum.onclick = function () {
      var read = readGiven();
      if (!read.text || !talks()) return;
      window.TargumTalk.say(read.text);
    };
  }

  /* --- the translation, where the reader has one ----------------------------- */

  /* Same drop zone, same three states, one text down. Its own copy rather than a shared
     one: the two zones hold different files and say different things, and a version of
     this that took both had four arguments and told you less than this does. */
  var translationHalf = (function () {
    var half = document.getElementById("have-translation");
    var zone = document.getElementById("drop-translation");
    var field = document.getElementById("translation");
    var choose = document.getElementById("choose-translation");
    var undo = document.getElementById("unchoose-translation");
    var how = document.getElementById("how");
    var note = document.getElementById("how-note");
    if (!zone || !field || !how) return { take: function () {}, putDown: function () {} };

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
        note.textContent = lineUp(mine);
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

    // For the box, which pairs a translation without anybody pressing I have one.
    return {
      take: function (file) {
        how.querySelector('[data-how="mine"]').click();
        take(file);
      },
      putDown: function () {
        if (theirs || !half.hidden) how.querySelector('[data-how="make"]').click();
      },
    };
  })();

  /* --- a recording, and the transcript it may have come with ----------------- */

  var AUDIO = /\.(mp3|m4a|m4b|aac|ogg|opus|flac|wav|mp4|m4v|mov|webm|mkv)$/i;

  function isAudio(file) {
    return !!(file && AUDIO.test(file.name));
  }
  // Anything that goes up the chunked door: a recording, a picture, a PDF.
  function inPieces(files) {
    return files.some(function (file) {
      return isAudio(file) || bringing.isPicture(file) || bringing.isPdf(file);
    });
  }

  //: The transcript the reader brought for their recording, if they brought one.
  var spokenText = null;

  var transcriptHalf = (function () {
    var step = document.getElementById("audio-extra");
    var zone = document.getElementById("drop-transcript");
    var field = document.getElementById("transcript");
    var choose = document.getElementById("choose-transcript");
    var undo = document.getElementById("unchoose-transcript");
    var how = document.getElementById("spoken-how");
    var note = document.getElementById("spoken-note");
    var half = document.getElementById("have-transcript");
    if (!step || !zone || !field || !how) {
      return { take: function () {}, putDown: function () {}, held: function () { return null; } };
    }

    var LABEL = zone.querySelector(".drop-label").textContent;
    var NOTE = zone.querySelector(".drop-note").textContent;

    function show() {
      var picked = spokenText !== null;
      zone.querySelector(".drop-label").textContent = picked ? spokenText.name : LABEL;
      zone.querySelector(".drop-note").textContent = picked
        ? Math.round(spokenText.size / 1024) + " KB"
        : NOTE;
      choose.hidden = picked;
      undo.hidden = !picked;
    }

    choose.onclick = function () {
      field.click();
    };
    field.onchange = function () {
      if (field.files[0]) {
        spokenText = field.files[0];
        show();
      }
    };
    undo.onclick = function () {
      spokenText = null;
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
      if (file) {
        spokenText = file;
        show();
      }
    });

    Array.prototype.forEach.call(how.querySelectorAll("[data-spoken]"), function (press) {
      press.addEventListener("click", function () {
        var mine = press.getAttribute("data-spoken") === "mine";
        Array.prototype.forEach.call(how.querySelectorAll("[data-spoken]"), function (other) {
          other.setAttribute("aria-pressed", other === press ? "true" : "false");
        });
        half.hidden = !mine;
        note.textContent = mine
          ? t("add.spoken.timings", "We'll keep its timings, so there's nothing to write down.")
          : t("add.spoken.parts", "We'll write down what's said, part by part.");
        if (!mine && spokenText) {
          spokenText = null;
          field.value = "";
          show();
        }
      });
    });

    // The step exists only while the chosen file is a recording.
    window.TargumAddAudio = {
      toggle: function (on) {
        step.hidden = !on;
        if (!on && spokenText) {
          spokenText = null;
          field.value = "";
          show();
        }
      },
    };

    // For the box, which pairs a subtitle file with its recording without anybody
    // pressing I have one.
    return {
      take: function (file) {
        how.querySelector('[data-spoken="mine"]').click();
        spokenText = file;
        show();
      },
      putDown: function () {
        if (spokenText || !half.hidden) how.querySelector('[data-spoken="make"]').click();
      },
      held: function () {
        return spokenText;
      },
    };
  })();

  // The upload, the price and the plain words for a build are bring.js's now: the same
  // three the box on Learn and the conversation page use, so no page answers the one
  // question differently.
  var bringing = window.TargumBring;
  function uploadInChunks(file, tell) {
    return bringing.uploadInChunks(file, tell);
  }

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
          found.stage === "R&D"
            ? t("add.stage.rd", "{language} is experimental. It has no word levels yet.", { language: found.name })
            : t("lang.beta-note", "{language} is new here, and still experimental.", { language: found.name });
      }
      if (code) lang.set(code);
    }
    from.addEventListener("change", say);
    say();

    // The nav's language menu is the same choice (2026-09-13). Picking there sets this
    // picker rather than opening the page again, so switching language never throws away
    // what is already in the box; picking here moves the menu with it.
    var names = window.TARGUM_LANGUAGES || {};
    function drawMenu() {
      var codes = [];
      for (var n = 0; n < from.options.length; n++) codes.push(from.options[n].value);
      lang.switcher(document.getElementById("langs"), codes, names, from.value, function (code) {
        if (codes.indexOf(code) < 0) return;
        from.value = code;
        from.dispatchEvent(new Event("change"));
      });
    }
    drawMenu();
    // The box's own words name the language, and a change here bubbles to Change's
    // listener, which says them again.
    from.addEventListener("change", drawMenu);
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
      // above U+00FF, and most of the texts this page is for are not in Latin letters.
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
    var text = line(t("add.fetching", "We're fetching it…"));
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
          : t("add.still-working", "Still working. The first text in a language takes us longer.");
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

    /* The transcript the reader brought for their recording, read the same way a
       translation is. */
    function withTranscript(body) {
      if (!spokenText) return Promise.resolve(body);
      return readFile(spokenText).then(function (content) {
        body.transcriptName = spokenText.name;
        body.transcriptContent = content;
        return body;
      });
    }

    var read = readGiven();
    if (chosen && inPieces(chosen)) {
      // A recording, a PDF, or the pictures of one text: up the chunked door, the
      // fields it answers with merged into the request, then priced.
      prepared = bringing
        .upload(chosen, function (share) {
          say(line(t("add.uploading", "We're uploading it… {share}%", { share: share })));
        })
        .then(function (sent) {
          // The same bytes were already imported: the reader is the answer.
          if (sent.reader) {
            window.location.href = keyed(
              "/reader/" + sent.reader.split("/").map(encodeURIComponent).join("/")
            );
            return { id: "" };
          }
          Object.keys(sent).forEach(function (name) {
            payload[name] = sent[name];
          });
          if (cameFrom) payload.came_from = cameFrom;
          say(waiting());
          return withTranscript(payload).then(function (body) {
            return ask("/prepare", body);
          });
        });
    } else if (chosen) {
      prepared = readFile(chosen[0]).then(function (content) {
        payload.name = chosen[0].name;
        payload.content = content;
        return withTranslation(payload).then(function (body) {
          return ask("/prepare", body);
        });
      });
    } else if (read.kind === "text" || read.kind === "few") {
      var file = fromPaste(read.text);
      payload.name = file.name;
      payload.content = file.content;
      prepared = withTranslation(payload).then(function (body) {
        return ask("/prepare", body);
      });
    } else {
      // A description is never priced: it is a request, and Ask targum is where it
      // goes. Words in another script are not a text targum reads.
      if (read.kind !== "link") {
        go.disabled = false;
        // What to do instead, not the line under the box said a second time in red.
        say(
          line(
            read.kind === "description"
              ? talks()
                ? t("add.continue.talks", "Continue reads a link, a file or the text itself. Press Ask targum and we'll look for it.")
                : t("add.continue", "Continue reads a link, a file or the text itself. Paste one of those here.")
              : read.kind === "foreign"
                ? t("add.continue.foreign", "Choose its language under Change, then press Continue.")
                : t("add.continue.empty", "Paste a link or some {language}, or drop a file.", { language: named(adding()) })
          ),
          true
        );
        return;
      }
      payload.source = read.text;
      // What is there, before what it costs (targum-internal#250). Metadata only, and
      // it never decides anything: a describe that fails or is refused is passed over
      // in silence and the price follows exactly as it did. The reader is told what the
      // link is while `/prepare` is still fetching it.
      var source = read.text;
      prepared = ask("/describe", { url: source, language: adding() })
        .then(function (said) {
          found = said && !said.error ? said : null;
          var block = foundBlock(found);
          if (block) say(block);
        })
        .catch(function () {
          found = null;
        })
        .then(function () {
          // A YouTube address goes to /prepare like any other link. It was turned away
          // here while the box would not fetch one; now it does, and a page that still
          // refused would be refusing something that works.
          return withTranslation(payload).then(function (body) {
            return ask("/prepare", body);
          });
        });
    }

    prepared
      .then(function (job) {
        go.disabled = false;
        if (!job.id && !job.error && !job.blocked && !job.catalogue) return;
        if (job.error) {
          if (payload.source) cameFrom = payload.source;
          return refusedWith(job);
        }
        if (job.catalogue) return instead(job.catalogue);
        if (job.blocked) return refuse(job);
        offer(job);
      })
      .catch(function () {
        go.disabled = false;
        // Never the exception itself: "TypeError: Failed to fetch" is not a sentence
        // anybody should be handed (2026-09-14).
        say(line(t("add.unreachable", "We couldn't reach targum. Check your connection and try again.")), true);
      });
  };

  function clock(seconds) {
    var whole = Math.round(seconds);
    var h = Math.floor(whole / 3600);
    var m = Math.floor((whole % 3600) / 60);
    var s = whole % 60;
    function two(n) {
      return (n < 10 ? "0" : "") + n;
    }
    return h ? h + ":" + two(m) + ":" + two(s) : m + ":" + two(s);
  }

  function describe(job) {
    if (job.audio) {
      var box = document.createDocumentFragment();
      box.appendChild(document.createTextNode(named(job.language) + " · "));
      var when = document.createElement("span");
      when.className = "clock";
      when.textContent = clock(job.seconds);
      box.appendChild(when);
      if (job.parts > 1) {
        box.appendChild(document.createTextNode(" · " + tn("add.job.parts", job.parts, "{n} part", "{n} parts")));
      }
      return box;
    }
    var what =
      job.chapters > 1
        ? tn("add.job.chapters", job.chapters, "{n} chapter", "{n} chapters")
        : (job.pages > 1 ? tn("add.job.pages", job.pages, "{n} page", "{n} pages") + " · " : "") +
          tn("add.job.sentences", job.segments, "{n} sentence", "{n} sentences");
    return document.createTextNode(named(job.language) + " · " + what);
  }

  //: What `/describe` said about the link now in the box, or null. Kept so the price,
  //: when it arrives, is drawn under it rather than over it (targum-internal#250).
  var found = null;

  /* What targum found at the end of a link, in plain words and before any price.
     `describe_source` has read this for the model since #126 — a video's length and
     whether anybody wrote its subtitles, an episode's own transcript, an article's
     minutes and how much of it this reader already knows — and the Add box showed a
     price and a title and nothing about what was being bought.

     Nothing here is a control: it is what the reader is about to pay for, said before
     they press. The advice lines are the server's own sentences, which is why they are
     set as text and never as markup. */
  function foundBlock(said) {
    if (!said || said.error) return null;
    var body = [];

    var facts = [];
    var medium = {
      video: t("add.found.video", "a video"),
      recording: t("add.found.recording", "a recording"),
      post: t("add.found.post", "a post"),
      article: t("add.found.article", "an article"),
    }[String(said.kind || "")];
    if (medium) facts.push(medium);
    if (said.seconds) facts.push(clock(said.seconds));
    if (said.minutes) facts.push(tn("add.found.minutes", said.minutes, "{n} minute to read", "{n} minutes to read"));
    if (said.words) facts.push(tn("add.found.words", said.words, "{n} word", "{n} words"));
    if (said.licence) facts.push(String(said.licence));
    if (facts.length) {
      var line = document.createElement("p");
      line.className = "found-facts";
      line.textContent = facts.join(" · ");
      body.push(line);
    }

    // How much of it this reader already has, in words and never a percentage or a
    // level — the same sentence the quote card says (targum-internal#244).
    var known = bringing && bringing.knownLine ? bringing.knownLine(said.known_share) : "";
    if (known) {
      var mine = document.createElement("p");
      mine.className = "found-known";
      mine.textContent = known;
      body.push(mine);
    }

    (said.advice || []).forEach(function (one) {
      var note = document.createElement("p");
      note.className = "found-note";
      note.textContent = String(one);
      body.push(note);
    });

    // A heading over nothing says the page is broken. An answer that carried no facts,
    // no share and no advice — a route that fell over, a medium nothing is known about
    // — is passed over in silence, and the price follows as it always did.
    if (!body.length) return null;
    var box = document.createElement("div");
    box.className = "found";
    var head = document.createElement("p");
    head.className = "found-head";
    head.textContent = t("add.found", "What targum found");
    box.appendChild(head);
    body.forEach(function (one) {
      box.appendChild(one);
    });
    return box;
  }

  function price(job) {
    return bringing.wait(job);
  }

  // This text is already in the library with a translation somebody published, which is
  // better than a machine one. Said before anything else happens.
  function instead(entry) {
    var box = document.createDocumentFragment();
    var head = document.createElement("p");
    head.className = "instead";
    // The title in bold wherever the sentence puts it: `{title}` marks the place.
    var sentence = tn(
      "add.instead",
      entry.translations.length,
      "{title} is already in the library, with a translation a person published. It'll read better than ours.",
      "{title} is already in the library, with {n} translations a person published. It'll read better than ours."
    );
    var at = sentence.indexOf("{title}");
    if (at < 0) at = 0;
    head.appendChild(document.createTextNode(sentence.slice(0, at)));
    var bold = document.createElement("b");
    bold.textContent = entry.title;
    head.appendChild(bold);
    head.appendChild(document.createTextNode(sentence.slice(at).replace("{title}", "")));
    var row = document.createElement("div");
    row.className = "row";
    var go = document.createElement("button");
    go.type = "button";
    go.className = "filled";
    go.textContent = t("add.open-it", "Open it");
    go.onclick = function () {
      // The text it just named, not the index it happens to sit on. Every catalogue text
      // has its own page now, so the button can go where it says it goes.
      window.location.href = keyed("/library/" + entry.id);
    };
    row.appendChild(go);
    var anyway = document.createElement("button");
    anyway.type = "button";
    anyway.className = "ghost";
    anyway.textContent = t("add.translate-anyway", "Translate it anyway");
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
      if (chosen && inPieces(chosen)) {
        // A recording, a PDF or pictures: up the chunked door again — the first
        // upload was gathered into the quote and cannot be named twice.
        again = bringing.upload(chosen).then(function (sent) {
          Object.keys(sent).forEach(function (name) {
            payload[name] = sent[name];
          });
          return ask("/prepare", payload);
        });
      } else if (chosen) {
        again = readFile(chosen[0]).then(function (content) {
          payload.name = chosen[0].name;
          payload.content = content;
          return ask("/prepare", payload);
        });
      } else if (readGiven().kind === "link") {
        payload.source = readGiven().text;
        again = ask("/prepare", payload);
      } else {
        var pastedAgain = fromPaste(readGiven().text);
        payload.name = pastedAgain.name;
        payload.content = pastedAgain.content;
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
          say(line(t("add.could-not-send", "We couldn't send that. Try again.")), true);
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
    head.appendChild(document.createTextNode(" · "));
    head.appendChild(describe(job));
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
    // What was found stays above what it costs: the reader read it while the price was
    // being worked out, and it should not vanish the moment the price lands.
    var was = foundBlock(found);
    if (was) box.appendChild(was);
    var head = document.createElement("p");
    head.style.margin = "0";
    head.innerHTML = "<b></b>";
    head.querySelector("b").textContent = job.title;
    head.appendChild(document.createTextNode(" · "));
    head.appendChild(describe(job));
    box.appendChild(head);

    // A text that arrived as pages: its first lines as read, and how many it could
    // not read cleanly, so the reader sees what will be built before pressing.
    if (job.excerpt && job.excerpt.length) {
      var lines = document.createElement("p");
      lines.className = "excerpt";
      lines.setAttribute("lang", job.language || "he");
      lines.setAttribute("dir", scriptOf(job.language || "he").rtl ? "rtl" : "ltr");
      job.excerpt.forEach(function (read, n) {
        if (n) lines.appendChild(document.createElement("br"));
        var bdi = document.createElement("bdi");
        bdi.textContent = read;
        lines.appendChild(bdi);
      });
      box.appendChild(lines);
    }
    if (job.doubtful > 0) {
      box.appendChild(
        line(tn("add.doubtful", job.doubtful, "We couldn't read {n} line clearly.", "We couldn't read {n} lines clearly."))
      );
    }

    var cost = document.createElement("span");
    cost.className = "cost";
    cost.textContent = price(job);
    box.appendChild(cost);

    var row = document.createElement("div");
    row.className = "row";
    var confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "filled";
    confirm.textContent = t("add.start-reading", "Open it");
    confirm.onclick = function () {
      ask("/build", { id: job.id }).then(function (state) {
        if (state.blocked) return refuse(state);
        watch(job);
      });
    };
    row.appendChild(confirm);
    if (job.pictures_offered > 0) row.appendChild(readPictures(job.pictures_offered));
    box.appendChild(row);
    say(box);
  }

  /* An Instagram post read from its caption, with pictures it did not read. Offered and
     never run unasked: this press is the consent, and it sends the link again with the
     pictures asked for, to be read and quoted like pictures brought in by hand
     (targum-internal#255). */
  function readPictures(count) {
    var more = document.createElement("button");
    more.type = "button";
    more.className = "ghost";
    more.textContent = tn("add.read-pictures", count, "Also read the picture", "Also read the {n} pictures");
    more.onclick = function () {
      more.disabled = true;
      var payload = options();
      payload.source = readGiven().text;
      payload.pictures = true;
      say(waiting());
      ask("/prepare", payload)
        .then(function (job) {
          if (job.error) return say(line(job.error), true);
          if (job.blocked) return refuse(job);
          offer(job);
        })
        .catch(function () {
          more.disabled = false;
          say(line(t("add.could-not-send", "We couldn't send that. Try again.")), true);
        });
    };
    return more;
  }

  // A refusal that has a way forward on the card: a post whose words are all in its
  // pictures says so, with the one button that reads them.
  function refusedWith(job) {
    if (!(job.pictures_offered > 0)) return say(line(job.error), true);
    var box = document.createDocumentFragment();
    box.appendChild(line(job.error));
    var row = document.createElement("div");
    row.className = "row";
    row.appendChild(readPictures(job.pictures_offered));
    box.appendChild(row);
    say(box, true);
  }

  function plain(message) {
    return bringing.plain(message);
  }

  function watch(job) {
    var box = document.createDocumentFragment();
    var text = line(t("add.getting-ready", "We're getting it ready…"));
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
          ? t("add.getting-ready.share", "We're getting it ready… {share}%", {
              share: Math.round((state.done / state.total) * 100),
            })
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

  /* --- arriving with a link already in hand ---------------------------------
   *
   * The weekly's sources each carry a "Read the whole thing", which is this page with
   * the article's address in the query. Signed out it goes to the door first and comes
   * back here afterwards, so the address has to survive the round trip — which it does,
   * because it rides in the URL rather than in anything this page remembers.
   *
   * Only http and https are accepted. The address came from somebody else's feed, and
   * `javascript:` in a field that is later fetched or rendered is exactly the thing that
   * `facts.canonical` refuses at the other end; refused here too, because a query string
   * is typed by whoever sends the link and not only by us.
   */
  (function () {
    if (!given || !window.URLSearchParams) return;
    var asked = new URLSearchParams(window.location.search).get("source");
    if (!asked) return;
    var url;
    try {
      url = new URL(asked, window.location.href);
    } catch (error) {
      return;
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") return;
    given.value = url.href;
    settle();
  })();

  // Change stays open for whoever opened it last; otherwise the box says what it holds.
  var wasOpen = false;
  try {
    wasOpen = localStorage.getItem(OPENED) === "open";
  } catch (e) {
    wasOpen = false;
  }
  if (wasOpen) openChoices(true);
  else settle();

  /* --- what the hours are, before any are spent ---------------------------- */

  /* targum-internal#299. The page already said "a recording or a video uses some of your
     hours" and never what those hours were, so the first time most readers met the
     number was the month they ran out of it. `/account/me` has carried it since #237.

     Time, not price: the plan is eight hours, and dollars are not a thing a reader
     should have to think about to decide whether to paste a link. And the library is
     named here as costing none of them, because the sentence above is about limits and
     somebody reading it quickly could take the whole page to be metered. */
  var hoursLine = document.getElementById("hours");
  if (hoursLine) {
    fetch(keyed("/account/me"), { credentials: "same-origin" })
      .then(function (answer) {
        return answer.ok ? answer.json() : null;
      })
      .then(function (me) {
        var hours = me && me.hours;
        // No allowance to quote: an admin, or a machine somebody runs themselves. Saying
        // nothing is right — an unmetered reader told about a limit would be told a
        // thing that is not true of them.
        if (!hours || typeof hours.allowed !== "number") return;
        var left = Math.max(0, hours.allowed - (hours.used || 0));
        // One decimal, and no trailing nought: "6.5 hours" and "8 hours", never "8.0".
        var said = String(Math.round(left * 10) / 10);
        var whole = String(hours.allowed);
        hoursLine.textContent =
          left > 0
            ? t("add.hours.left", "You have {left} of your {all} hours this month. The library costs none of them.", {
                left: said,
                all: whole,
              })
            : t("add.hours.none", "You've used your {all} hours this month. They come back on {date}, and the library is always free.", {
                all: whole,
                date: hours.ends || "",
              });
        hoursLine.hidden = false;
      })
      .catch(function () {
        /* The page works without it; a line that could not be fetched is no line. */
      });
  }

  /* --- getting about ------------------------------------------------------- */

  Array.prototype.forEach.call(document.querySelectorAll(".site-nav a, .to-library"), function (link) {
    link.href = keyed(link.getAttribute("href"));
  });
})();
