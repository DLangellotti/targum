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

  //: What goes up in pieces rather than whole: the recordings, and the pictures.
  var MEDIA = /\.(mp3|m4a|m4b|aac|ogg|opus|flac|wav|mp4|m4v|mov|webm|mkv)$/i;

  function isMedia(file) {
    return !!(file && MEDIA.test(file.name));
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
    return { to: into || "en", from: from || "he", words: true, gloss: false };
  }

  /* One file, brought: up in pieces or whole, then priced. Resolves to the job the
     server quoted, or to `{ reader }` when the same bytes were already brought and the
     text is the answer; rejects with a sentence. `tell(share)` hears the upload. */
  function bring(file, choices, tell) {
    var payload = options(choices && choices.to, choices && choices.from);
    if (isMedia(file)) {
      return uploadInChunks(file, tell).then(function (done) {
        if (done.error) throw done.error;
        if (done.reader) return { reader: done.reader };
        payload.upload = done.upload;
        return ask("/prepare", payload);
      });
    }
    return readFile(file).then(function (content) {
      payload.name = file.name;
      payload.content = content;
      return ask("/prepare", payload);
    });
  }

  // What a build will take, in the only currency the reader spends: their time. What
  // it costs us is our business and never theirs — they pay by the month.
  function wait(job) {
    if (job.audio && job.parts > 0) {
      // The wait is the first part's: hearing it, then translating it.
      var spoken = job.seconds / job.parts / 60;
      var listening = Math.max(1, Math.round(spoken / 6));
      var translating = Math.max(1, Math.round((job.total || 25) / 25));
      var minutes = listening + translating;
      var opener = job.parts > 1 ? "First part in " : "Ready in ";
      if (minutes <= 1) return opener + "about a minute.";
      if (minutes <= 4) return opener + "a few minutes.";
      return opener + "about " + minutes + " minutes.";
    }
    if (!job.estimate) return "Ready in a moment.";
    // A book opens on its first chapter, so the wait is that chapter's — not the
    // novel's. `total` is what is being translated now.
    var mins = Math.max(1, Math.round((job.total || job.segments) / 25));
    var start = job.chapters > 1 ? "First chapter in " : "";
    if (mins <= 1) return start ? start + "about a minute." : "About a minute.";
    if (mins <= 4) return start ? start + "a couple of minutes." : "A couple of minutes.";
    return start + "about " + mins + " minutes.";
  }

  function hours(seconds) {
    var h = seconds / 3600;
    if (h < 1) return Math.max(1, Math.round(seconds / 60)) + " minutes of audio";
    return Math.round(h * 10) / 10 + " hours of audio";
  }

  var PLAIN = {
    "Finding each word's dictionary form…": "Reading the words…",
    "Adding vowel points…": "Adding vowel points…",
    "Building the reader…": "Setting the page…",
  };

  // The pipeline narrates itself in its own vocabulary. This is the reader's.
  function plain(message) {
    if (!message) return "Getting it ready…";
    if (PLAIN[message]) return PLAIN[message];
    if (message.indexOf("Matching") === 0) return "Lining up…";
    if (message.indexOf("Transcribing") === 0) return "Writing down what is said…";
    if (message.indexOf("Finding the pauses") === 0) return "Finding the pauses…";
    if (message.indexOf("Looking up") === 0) return "Looking words up…";
    return "Getting it ready…";
  }

  // The card the reader presses. Drawn from the quote itself — the server's state of
  // the job — never from what anybody wrote about it. The button posts to /build, the
  // same door the Add page's button posts to: the press is the spend, and nothing the
  // model holds can make it. "More options" is the Add page, for the two things only
  // its form can say: a translation you have, a transcript you have.
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
    he.setAttribute("dir", language === "he" ? "rtl" : "ltr");
    he.textContent = job.title || "";
    title.appendChild(he);
    if (job.english) {
      var en = document.createElement("span");
      en.className = "quote-english";
      en.textContent = job.english;
      title.appendChild(en);
    }
    card.appendChild(title);
    var meta = document.createElement("p");
    meta.className = "quote-meta";
    var facts = [];
    if (job.audio) facts.push(hours(job.seconds || 0));
    else if (job.chapters > 1) facts.push(job.chapters + " chapters");
    else if (job.segments) facts.push(job.segments + " sentences");
    if (job.stage === "ready") facts.push(wait(job));
    meta.textContent = facts.join(" · ");
    card.appendChild(meta);
    var note = document.createElement("p");
    note.className = "quote-note";
    if (job.stage === "ready") {
      var go = document.createElement("button");
      go.type = "button";
      go.className = "quote-go";
      go.textContent = "Read this";
      go.onclick = function () {
        go.disabled = true;
        ask("/build", { id: job.id }).then(function (state) {
          if (state.error || state.blocked) {
            note.textContent = state.error || state.blocked;
            card.classList.add("refused");
            return;
          }
          note.textContent = "Building. It will appear above when it is ready.";
          card.classList.add("started");
          if (window.TargumBuilding && window.TargumBuilding.ask) window.TargumBuilding.ask();
        });
      };
      card.appendChild(go);
      var more = document.createElement("a");
      more.className = "quote-more";
      more.href = keyed("/add");
      more.textContent = "More options";
      card.appendChild(more);
    } else {
      note.textContent = job.blocked || job.error || "This cannot be built now.";
      card.classList.add("refused");
    }
    card.appendChild(note);
    host.appendChild(card);
    return card;
  }

  window.TargumBring = {
    isMedia: isMedia,
    uploadInChunks: uploadInChunks,
    readFile: readFile,
    options: options,
    bring: bring,
    wait: wait,
    hours: hours,
    plain: plain,
    quoteCard: quoteCard,
  };
})();
