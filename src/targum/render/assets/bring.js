/* Bringing a text: what the Add page does, as one script the box can do too.
 *
 * Three pages bring a text in — the Add page with its form, the conversation page and
 * Learn through the `+` on the box (2026-09-06) — and one text goes up one way: a
 * recording in pieces through the chunked upload, anything else read whole; then
 * `/prepare`, which prices it and never spends; then a card the reader presses, whose
 * button posts `/build`. The card, the price in the reader's own time, and the plain
 * words for a build's progress used to be written twice, on two pages, and two answers
 * to one question drift. They are written here once.
 */
(function () {
  "use strict";

  /* Words said through the page's `TargumStrings`, looked up when a thing is said: this
     file runs before the page has handed its strings over. Where there are none, the
     English here (targum-internal#184). */
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

  // How much of a text the reader already has, said in their language the way
  // `level.known_line` says it in English: an exact percentage, never a count in ten
  // (David, 2026-10-29, targum-internal#560). "" where the share was not measured.
  function knownLine(share) {
    if (share === null || share === undefined) return "";
    var percent = Math.max(0, Math.min(100, Math.round(share * 100)));
    // Never rounded into a lie, as `level.known_percent` keeps it.
    if (share < 1 && percent >= 100) percent = 99;
    if (share > 0 && percent <= 0) percent = 1;
    return t("bring.known.share", "You know {n}% of the words here.", { n: percent });
  }

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }
  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  //: What goes up in pieces rather than whole: the recordings, and since 2026-09-07 the
  //: pictures and the PDFs, which are a phone photo's ten megabytes rather than a text's
  //: ten kilobytes (targum-internal#217).
  var MEDIA = /\.(mp3|m4a|m4b|aac|ogg|opus|flac|wav|mp4|m4v|mov|webm|mkv)$/i;
  var PICTURE = /\.(png|jpe?g|webp|heic|heif)$/i;
  var PDF = /\.pdf$/i;

  function isMedia(file) {
    return !!(file && MEDIA.test(file.name));
  }
  function isPicture(file) {
    return !!(file && PICTURE.test(file.name));
  }
  function isPdf(file) {
    return !!(file && PDF.test(file.name));
  }

  // One file or several: a FileList, an array, or a lone File, as an array.
  function listed(files) {
    if (!files) return [];
    if (typeof files.length === "number" && !files.name) {
      return Array.prototype.slice.call(files);
    }
    return [files];
  }

  /* A recording goes up in pieces: the JSON door reads its whole body into memory as
     base64, which for an audiobook is the wrong door. Sequential on purpose — the
     server is one worker and the reader's uplink is the bottleneck either way. */
  function uploadInChunks(file, tell) {
    return ask("/upload/begin", { name: file.name, size: file.size }).then(function (opened) {
      if (opened.error) throw opened.error;
      var piece = opened.chunk;
      var count = Math.ceil(file.size / piece);

      function send(n) {
        if (n >= count) {
          return ask("/upload/" + opened.upload + "/end", {});
        }
        return fetch(keyed("/upload/" + opened.upload + "/" + n), {
          method: "POST",
          headers: keyHeaders({ "Content-Type": "application/octet-stream" }),
          body: file.slice(n * piece, (n + 1) * piece),
        })
          .then(function (response) {
            return response.json();
          })
          .then(function (state) {
            if (state.error) throw state.error;
            if (tell) tell(Math.round(((n + 1) / count) * 100));
            return send(n + 1);
          });
      }
      return send(0);
    });
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

  // What every build from the box asks for: words, always, because tapping a word is
  // most of what this is for; no whole-text glossary, because most of one is never
  // read and a word is looked up from its card when wanted.
  function options(into, from) {
    // In the language the switcher shows, not Hebrew by assumption (2026-09-13): a French
    // file brought into the conversation is a French text.
    var lang = window.TargumLang;
    var here = lang && lang.learning ? lang.current(lang.learning()) : "he";
    return { to: into || "en", from: from || here, words: true, gloss: false };
  }

  /* What the reader gave, sent up, as the fields `/prepare` takes: `{ upload }` for a
     recording or a PDF, `{ uploads }` for pictures — several at once are one text, in
     the order chosen — `{ name, content }` for anything read whole, or `{ reader }`
     when the same bytes were already brought and the text is the answer. Rejects with
     a sentence. `tell(share)` hears the upload as a whole. */
  function upload(files, tell) {
    var chosen = listed(files);
    if (!chosen.length) return Promise.reject(t("bring.choose-first", "Choose a file first."));
    var pictures = chosen.filter(isPicture);
    if (pictures.length) {
      if (pictures.length !== chosen.length) {
        return Promise.reject(
          t("bring.several", "We can take several files at once only when they're pictures of one text.")
        );
      }
      var ids = [];
      function next(n) {
        if (n >= pictures.length) return Promise.resolve({ uploads: ids });
        return uploadInChunks(pictures[n], function (share) {
          if (tell) tell(Math.round(((n + share / 100) / pictures.length) * 100));
        }).then(function (done) {
          if (done.error) throw done.error;
          ids.push(done.upload);
          return next(n + 1);
        });
      }
      return next(0);
    }
    var file = chosen[0];
    if (isMedia(file) || isPdf(file)) {
      return uploadInChunks(file, tell).then(function (done) {
        if (done.error) throw done.error;
        if (done.reader) return { reader: done.reader };
        return { upload: done.upload };
      });
    }
    return readFile(file).then(function (content) {
      return { name: file.name, content: content };
    });
  }

  /* One file, or the pictures of one text, brought: up in pieces or whole, then
     priced. Resolves to the job the server quoted, or to `{ reader }` when the same
     bytes were already brought and the text is the answer; rejects with a sentence.
     `tell(share)` hears the upload. */
  function bring(files, choices, tell) {
    var payload = options(choices && choices.to, choices && choices.from);
    // The link that was refused before this file was dropped, where there was one: the
    // film's own home, so the reader page still says whose it is. The server keeps it
    // only in the host table's canonical shape (targum-internal#331).
    var from = (choices && choices.cameFrom) || "";
    return upload(files, tell).then(function (sent) {
      if (sent.reader) return { reader: sent.reader };
      Object.keys(sent).forEach(function (name) {
        payload[name] = sent[name];
      });
      if (from) payload.came_from = from;
      return ask("/prepare", payload);
    });
  }

  // What a build will take, in the only currency the reader spends: their time. What
  // it costs us is our business and never theirs — they pay by the month.
  // "globes.co.il" for a link into Globes: the host without its www.
  function siteOf(url) {
    var host = String(url).replace(/^https?:\/\//, "").split(/[/?#]/)[0];
    return host.replace(/^www\./, "");
  }

  /* How long a build of this shape has actually taken on this box lately, in minutes,
     or 0 where it has not finished enough of them to have a middle worth quoting
     (targum-internal#303).

     The formulas below — a segment takes a twenty-fifth of a minute, audio runs at six
     times real time — are guesses that nobody ever checked against a clock, because
     until `job.finished` existed there was no clock to check them against. Where the
     box can answer from its own history it does, and the guesses stay as the fallback
     for a new box and for the first dozen builds on any box. */
  function measured(job) {
    if (!job.usually) return 0;
    return Math.max(1, Math.round(job.usually / 60));
  }

  function wait(job) {
    var seen = measured(job);
    if (job.audio && job.parts > 0) {
      // The wait is the first part's: hearing it, then translating it.
      // Numbers or nought: a quote without one says "about a minute", never "NaN".
      var spoken = (Number(job.seconds) || 0) / job.parts / 60;
      var listening = Math.max(1, Math.round(spoken / 6));
      var translating = Math.max(1, Math.round((job.total || 25) / 25));
      var minutes = seen || listening + translating;
      var part = job.parts > 1;
      if (minutes <= 1) {
        return part
          ? t("bring.wait.part-minute", "Your first part will be ready in about a minute.")
          : t("bring.wait.minute", "Ready in about a minute.");
      }
      if (minutes <= 4) {
        return part
          ? t("bring.wait.part-few", "Your first part will be ready in a few minutes.")
          : t("bring.wait.few", "Ready in a few minutes.");
      }
      return part
        ? t("bring.wait.part-minutes", "Your first part will be ready in about {n} minutes.", { n: minutes })
        : t("bring.wait.minutes", "Ready in about {n} minutes.", { n: minutes });
    }
    if (!job.estimate) return t("bring.wait.moment", "Ready in a moment.");
    // A book opens on its first chapter, so the wait is that chapter's — not the
    // novel's. `total` is what is being translated now.
    var mins = seen || Math.max(1, Math.round((Number(job.total || job.segments) || 0) / 25));
    var chapter = job.chapters > 1;
    if (mins <= 1) {
      return chapter
        ? t("bring.wait.chapter-minute", "Your first chapter will be ready in about a minute.")
        : t("bring.wait.minute", "Ready in about a minute.");
    }
    if (mins <= 4) {
      return chapter
        ? t("bring.wait.chapter-couple", "Your first chapter will be ready in a couple of minutes.")
        : t("bring.wait.couple", "Ready in a couple of minutes.");
    }
    return chapter
      ? t("bring.wait.chapter-minutes", "Your first chapter will be ready in about {n} minutes.", { n: mins })
      : t("bring.wait.minutes", "Ready in about {n} minutes.", { n: mins });
  }

  /* What pressing spends, said beside the press (copy audit, 2026-09-28): a recording
     or a film in credits — a credit is a minute and any part of one is a whole one, the
     way the server counts it (`builder.credits_of`) — and a text none, as Telegram's
     quote already said. "" for a recording whose length is not known: no guess. */
  function uses(job) {
    if (!job) return "";
    if (job.audio) {
      var seconds = Number(job.seconds) || 0;
      if (seconds <= 0) return "";
      var n = Math.ceil(seconds / 60 - 1e-9);
      var whole = tn("bring.uses-credits", n, "Uses {n} credit", "Uses {n} credits");
      // One press gets every part, a part at a time (David, 2026-10-07; design.md §12):
      // the credits are the whole recording's, and the card says how it arrives.
      var parts = Number(job.parts) || 0;
      if (parts > 1) {
        whole += " · " + tn("bring.in-parts", parts, "in {n} part, each made as you reach it", "in {n} parts, each made as you reach it");
      }
      return whole;
    }
    return t("bring.uses-no-credits", "Uses none of your credits");
  }

  //: Past this share of the month's hours the box says so, above the field. Below it
  //: the count is on Your Progress and in the account panel, and nowhere else
  //: (2026-09-10, targum-internal#237).
  var HOURS_WARN = 0.75;

  // The line above the box when the month's credits are nearly gone, or nothing.
  function hoursWarning(got) {
    if (!got || got.allowed === null || got.allowed === undefined) return "";
    if (!(got.used >= got.allowed * HOURS_WARN)) return "";
    /* Credits with the rate beside them, and what is left rather than what is gone
       (design.md §12, 2026-09-23). The same two strings the inbox warning uses, because
       it is the same warning in a different place and two wordings would drift. */
    var spare = Math.max(0, (Number(got.allowed) || 0) - (Number(got.used) || 0));
    var line =
      tn(
        "building.credits.left",
        Math.round(spare * 60),
        "{n} credit left this month.",
        "{n} credits left this month."
      ) +
      " " +
      t("building.credits.rate", "That's about {clock} of audio or video.", { clock: said(spare) });
    // The date never breaks from its month at a line's end (#472 polish 6): the server
    // sends it unbroken, and an answer that does not is kept whole here too.
    if (got.ends) {
      line += " " + t("building.hours.reset", "They reset on {date}.", { date: String(got.ends).replace(/ /g, "\u00a0") });
    }
    return line;
  }

  // Hours as a person says them: "6 hours 30 minutes", never "6.5" (2026-09-14).
  function said(hours) {
    var minutes = Math.round((Number(hours) || 0) * 60);
    var whole = Math.floor(minutes / 60);
    var rest = minutes % 60;
    var parts = [];
    if (whole) parts.push(tn("account.hours", whole, "{n} hour", "{n} hours"));
    if (rest || !whole) parts.push(tn("account.minutes", rest, "{n} minute", "{n} minutes"));
    return parts.join(" ");
  }

  function hours(seconds) {
    var h = seconds / 3600;
    if (h < 1) return t("bring.audio.minutes", "{n} min of audio", { n: Math.max(1, Math.round(seconds / 60)) });
    return t("bring.audio.hours", "{n} h of audio", { n: Math.round(h * 10) / 10 });
  }

  // Keyed by the pipeline's English, which is what arrives; said in the reader's.
  var PLAIN = {
    "Finding each word's dictionary form…": function () {
      return t("bring.build.words", "We're reading the words…");
    },
    "Adding vowel points…": function () {
      return t("bring.build.points", "We're adding vowel points…");
    },
    "Building the reader…": function () {
      return t("bring.build.page", "We're setting the page…");
    },
  };

  // The pipeline narrates itself in its own vocabulary. This is the reader's.
  function plain(message) {
    var readying = t("bring.build.getting-ready", "We're getting it ready…");
    if (!message) return readying;
    if (Object.prototype.hasOwnProperty.call(PLAIN, message)) return PLAIN[message]();
    if (message.indexOf("Matching") === 0) return t("bring.build.lining-up", "We're lining it up…");
    if (message.indexOf("Transcribing") === 0) return t("bring.build.transcribing", "We're writing down what's said…");
    if (message.indexOf("Finding the pauses") === 0) return t("bring.build.pauses", "We're finding the pauses…");
    if (message.indexOf("Looking up") === 0) return t("bring.build.looking-up", "We're looking up the words…");
    return readying;
  }

  // The card the reader presses. Drawn from the quote itself — the server's state of
  // the job — never from what anybody wrote about it. The button posts to /build, the
  // same door the Add page's button posts to: the press is the spend, and nothing the
  // model holds can make it. "More options" is the Add page, for the two things only
  // its form can say: a translation you have, a transcript you have.
  // Start the build a quote priced: the press, made by the reader's own hand — on the
  // card's button for the model's quote, or by Send with a file in the box, which is
  // the same person saying the same thing (2026-09-07). Resolves to the job's state.
  function start(job) {
    return ask("/build", { id: job.id });
  }

  // The door to a reader that a finished build opened.
  function door(reader) {
    return keyed("/reader/" + String(reader).split("/").map(encodeURIComponent).join("/"));
  }

  //: How often a page asks after a build it is waiting to open. A test sets it to 0.
  var POLL = 2000;

  //: The languages a text may be in that are written right to left: Yiddish and Aramaic
  //: as much as Hebrew.
  var RIGHT_TO_LEFT = { he: true, yi: true, arc: true, ar: true };

  //: A line sent with a file that only says to open it, in English or Hebrew: "open
  //: this", "read it please", "תפתח את זה". Such a line is the file's own meaning and
  //: starts no conversation; anything that says more is a specification for the model.
  var JUST_OPEN = new RegExp(
    "^(?:(?:please|בבקשה)\\s+)?" +
      "(?:open|read|build|load|show|translate|start|" +
      "פתח|תפתח|לפתוח|תפתחי|פתחי|קרא|תקרא|לקרוא|תרגם|תתרגם|לתרגם|בנה|תבנה)" +
      "(?:\\s+(?:this|it|that|the|my|this one|" +
      "(?:the\\s+)?(?:file|picture|photo|image|text|pdf|message|letter|page|pages|screenshot)|" +
      "את\\s+זה|זה|את\\s+הקובץ|הקובץ|את\\s+התמונה|התמונה|את\\s+הטקסט|הטקסט|לי))*" +
      "(?:\\s+(?:please|בבקשה|now|עכשיו|for me|לי))*$",
    "i"
  );

  function justOpen(text) {
    var line = String(text || "")
      .trim()
      .replace(/[.!?,;:״"']+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return !line || JUST_OPEN.test(line);
  }

  //: A build still under way: waiting its turn, being read, or being made. Anything
  //: else — done, failed, refused, lost to a restart — is where following stops.
  var UNDER_WAY = { queued: true, working: true, reading: true, "looking up words": true };
  function underWay(state) {
    return !!state && !state.error && !state.blocked && UNDER_WAY[state.stage] === true;
  }

  //: Asks in a row that reach nobody before a follow gives up rather than asking for ever.
  var MISSES = 5;

  // Follow a started build to its end: resolves to the job's state once it is done or
  // has failed. A reader who sent a text to open it is waiting for exactly this.
  // `step(state)` hears every answer on the way, which is how a card draws its progress;
  // `still()`, where given, says whether anybody is still looking — a card taken off the
  // page stops asking, and resolves to `{}`.
  function follow(id, step, still) {
    return new Promise(function (resolve) {
      var misses = 0;
      function look() {
        ask("/job/" + encodeURIComponent(id)).then(
          function (state) {
            misses = 0;
            if (still && !still()) return resolve({});
            if (step) step(state);
            if (!underWay(state)) return resolve(state);
            setTimeout(look, window.TargumBring.POLL);
          },
          function () {
            // A dropped connection is not a failed build: ask again, more slowly.
            misses += 1;
            if (misses >= MISSES || (still && !still())) return resolve({});
            setTimeout(look, window.TargumBring.POLL * (misses + 1));
          }
        );
      }
      look();
    });
  }

  function quoteCard(host, job) {
    var card = document.createElement("div");
    // Not `quote`: that is the reader's own class for a quotation inside a text, and
    // `reader.css` rides on every page, so a card by that name came out italic with a
    // rule down its side.
    card.className = "quote-card";
    card.setAttribute("data-job", job.id);
    var title = document.createElement("p");
    title.className = "quote-title";
    var he = document.createElement("bdi");
    var language = job.language || "he";
    he.setAttribute("lang", language);
    he.setAttribute("dir", RIGHT_TO_LEFT[language] ? "rtl" : "ltr");
    he.textContent = job.title || "";
    title.appendChild(he);
    if (job.english) {
      var en = document.createElement("span");
      en.className = "quote-english";
      en.textContent = job.english;
      title.appendChild(en);
    }
    card.appendChild(title);
    // Where the text is from, as a link, when it is a page on the web (2026-09-11:
    // "don't see the link to the article"): the site's name, opening in its own tab
    // — from the drawer as much as from the page, and never inside the frame.
    if (/^https?:\/\//.test(String(job.source || ""))) {
      var from = document.createElement("a");
      from.className = "quote-source";
      from.href = job.source;
      from.target = "_blank";
      from.rel = "noopener";
      from.textContent = siteOf(job.source);
      card.appendChild(from);
    }
    var meta = document.createElement("p");
    meta.className = "quote-meta";
    var facts = [];
    if (job.audio) facts.push(hours(job.seconds || 0));
    else if (job.chapters > 1) facts.push(tn("add.job.chapters", job.chapters, "{n} chapter", "{n} chapters"));
    else {
      if (job.pages > 1) facts.push(tn("add.job.pages", job.pages, "{n} page", "{n} pages"));
      if (job.segments) facts.push(tn("add.job.sentences", job.segments, "{n} sentence", "{n} sentences"));
    }
    if (job.stage === "ready") facts.push(wait(job));
    meta.textContent = facts.join(" · ");
    card.appendChild(meta);
    // How much of it the reader already has, in words, never a percentage or a level
    // (targum-internal#244). Absent where it was not measured.
    if (job.known_line) {
      var known = document.createElement("p");
      known.className = "quote-known";
      var line = knownLine(job.known_share);
      known.textContent = line || job.known_line;
      card.appendChild(known);
    }
    // A silent text can be read aloud once it is built (targum-internal#246). One line
    // under the facts, no button: the press is in the reader, beside the section it
    // would read, and this card is quoting a build that has not happened yet.
    if (job.voice_later) {
      var voice = document.createElement("p");
      voice.className = "quote-voice";
      voice.textContent = t("add.job.voice-later", "You can add audio later, in the reader.");
      card.appendChild(voice);
    }
    // A text that arrived as pages shows its first lines as read: for a picture the
    // filename says nothing, and what will be built should be seen before it is.
    if (job.excerpt && job.excerpt.length) {
      var lines = document.createElement("p");
      lines.className = "quote-excerpt";
      lines.setAttribute("lang", language);
      lines.setAttribute("dir", RIGHT_TO_LEFT[language] ? "rtl" : "ltr");
      job.excerpt.forEach(function (text, n) {
        if (n) lines.appendChild(document.createElement("br"));
        var read = document.createElement("bdi");
        read.textContent = text;
        lines.appendChild(read);
      });
      card.appendChild(lines);
    }
    if (job.doubtful > 0) {
      var doubt = document.createElement("p");
      doubt.className = "quote-doubt";
      doubt.textContent = tn("add.doubtful", job.doubtful, "We couldn't read {n} line clearly.", "We couldn't read {n} lines clearly.");
      card.appendChild(doubt);
    }
    var note = document.createElement("p");
    note.className = "quote-note";
    // Where the card follows its build once it is pressed (David, 2026-10-10: "it wasn't
    // clear for a long time that it was loading, and it required me to refresh the page
    // to see it"): the stage in words and the bar while it is made, the Open press when
    // it is ready. Empty and hidden until then.
    var progress = document.createElement("div");
    progress.className = "quote-progress";
    progress.hidden = true;
    var bar = null;
    var fill = null;
    var stage = null;
    var said = null;
    function drawWorking(state) {
      if (!stage) {
        progress.textContent = "";
        stage = document.createElement("p");
        stage.className = "quote-stage";
        // Said when the stage changes; the bar carries the count.
        stage.setAttribute("aria-live", "polite");
        progress.appendChild(stage);
        bar = document.createElement("span");
        bar.className = "meter is-building quote-meter";
        bar.setAttribute("role", "progressbar");
        bar.setAttribute("aria-label", t("building.stage.progress", "How much is ready"));
        bar.setAttribute("aria-valuemin", "0");
        bar.setAttribute("aria-valuemax", "100");
        fill = document.createElement("span");
        bar.appendChild(fill);
        progress.appendChild(bar);
        said = document.createElement("p");
        said.className = "quote-said";
        progress.appendChild(said);
      }
      progress.hidden = false;
      var behind = Number(state.behind) || 0;
      stage.textContent =
        state.stage === "queued" && behind > 0
          ? tn("shelf.building.behind", behind, "Waiting behind {n} other text", "Waiting behind {n} other texts")
          : plain(state.message);
      // A sliver while nothing is counted yet, as the shelf's building row draws it, so
      // the bar reads as begun rather than as empty.
      var total = Number(state.total) || 0;
      var done = Math.min(Number(state.done) || 0, total);
      var share = total > 0 ? Math.max(0.04, done / total) : 0.04;
      fill.style.setProperty("--done", String(share));
      bar.setAttribute("aria-valuenow", String(Math.round(share * 100)));
      // The server's own line about it, the one `check_job` gives a host, so the card
      // here and the card in someone else's chat say the same thing.
      said.textContent = state.said || "";
      said.hidden = !state.said;
    }
    function drawReady(state) {
      progress.textContent = "";
      stage = null;
      var open = document.createElement("a");
      open.className = "quote-go quote-open";
      open.href = door(state.reader);
      open.textContent = t("bring.open-it", "Open it");
      progress.appendChild(open);
      progress.hidden = false;
      note.textContent = state.said || t("job.said.ready", "It's ready to read.");
      card.classList.add("ready");
    }
    // Pressed: from here the card is its build's progress, to its end, with no refresh.
    function followBuild(state) {
      card.classList.add("started");
      note.textContent = t("bring.started", "We're getting it ready. You'll find it in Your targums.");
      drawWorking(state);
      if (window.TargumBuilding && window.TargumBuilding.ask) window.TargumBuilding.ask();
      card.finished = follow(
        state.id || job.id,
        function (now) {
          if (underWay(now)) drawWorking(now);
        },
        function () {
          // Off the page — another conversation opened — nobody is looking.
          return card.isConnected !== false;
        }
      ).then(function (end) {
        if (end.stage === "done" && end.reader) {
          drawReady(end);
        } else if (end.error || end.blocked || end.stage === "failed" || end.stage === "blocked") {
          progress.hidden = true;
          progress.textContent = "";
          stage = null;
          refuse(
            { blocked: end.blocked, error: end.said || end.error, fact: end.fact, act: end.act },
            t("bring.cannot", "We can't get this ready right now.")
          );
        } else {
          // Lost sight of it: the note still says where it will be.
          progress.hidden = true;
          return end;
        }
        // The bell, told to look again, so the strip and the card agree.
        if (window.TargumBuilding && window.TargumBuilding.ask) window.TargumBuilding.ask();
        return end;
      });
      return card.finished;
    }
    // A refusal on the card: the sentence with the clay mark, or, where the rail that
    // stopped it sent what still works, a panel with its way on (design.md §12,
    // 2026-10-09). It was a sentence in clay.
    function refuse(state, fallback) {
      var said = state.blocked || state.error || fallback;
      card.classList.add("refused");
      if (window.TargumFault && state.blocked && (state.fact || state.act)) {
        note.textContent = "";
        note.hidden = true;
        card.appendChild(window.TargumFault.refusal(said, state.fact, state.act));
        return;
      }
      note.textContent = said;
      note.classList.add("fault-marked");
    }
    if (job.stage === "ready") {
      var spends = uses(job);
      var cost = null;
      if (spends) {
        cost = document.createElement("p");
        cost.className = "quote-uses";
        cost.textContent = spends;
        card.appendChild(cost);
      }
      var go = document.createElement("button");
      go.type = "button";
      go.className = "quote-go";
      go.textContent = t("bring.read-this", "Open this");
      go.onclick = function () {
        go.disabled = true;
        start(job).then(function (state) {
          if (state.error || state.blocked) {
            go.hidden = true;
            refuse(state, "");
            return;
          }
          // The press is made: the button and its options give way to the progress.
          go.hidden = true;
          more.hidden = true;
          if (cost) cost.hidden = true;
          followBuild(state);
        });
      };
      card.appendChild(go);
      var more = document.createElement("a");
      more.className = "quote-more";
      more.href = keyed("/add");
      more.textContent = t("bring.more-options", "More options");
      card.appendChild(more);
    } else if (underWay(job)) {
      // Sent from the box, or come back to, so already pressed: the card is its
      // progress. "Getting it ready", never "building" (2026-09-11): a text is getting
      // ready, then ready.
      followBuild(job);
    } else if (job.stage === "done" && job.reader) {
      card.classList.add("started");
      drawReady(job);
    } else {
      refuse(job, t("bring.cannot", "We can't get this ready right now."));
    }
    card.appendChild(progress);
    card.appendChild(note);
    host.appendChild(card);
    return card;
  }

  /* The files the + chose, held in the box until Send: one chip a file, each with a
     way to let it go. Drawn here so both boxes hold a file the same way. */
  function held(host, files, drop) {
    host.textContent = "";
    files.forEach(function (file, index) {
      var chip = document.createElement("li");
      chip.className = "chat-chip";
      var name = document.createElement("span");
      name.textContent = file.name;
      chip.appendChild(name);
      var out = document.createElement("button");
      out.type = "button";
      out.className = "chat-drop";
      out.setAttribute("aria-label", t("bring.do-not-bring", "Remove {file}", { file: file.name }));
      out.textContent = "×";
      out.onclick = function () {
        drop(index);
      };
      chip.appendChild(out);
      host.appendChild(chip);
    });
    host.hidden = files.length === 0;
  }

  window.TargumBring = {
    isMedia: isMedia,
    held: held,
    isPicture: isPicture,
    isPdf: isPdf,
    listed: listed,
    upload: upload,
    start: start,
    door: door,
    follow: follow,
    underWay: underWay,
    justOpen: justOpen,
    POLL: POLL,
    uploadInChunks: uploadInChunks,
    readFile: readFile,
    options: options,
    bring: bring,
    wait: wait,
    uses: uses,
    hours: hours,
    hoursWarning: hoursWarning,
    HOURS_WARN: HOURS_WARN,
    plain: plain,
    knownLine: knownLine,
    quoteCard: quoteCard,
  };
})();
