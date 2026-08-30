/* A build you can walk away from.
 *
 * The id of a build used to live only in the page that started it, so leaving that page
 * made the build look cancelled. It was not: the server kept it, and the reader turned
 * up on the shelf later with nothing to say how. This asks the server for every build
 * of yours and says, on whichever page you are on, where it has got to — and when it is
 * done, hands over the link.
 *
 * Polls only while something is unfinished, and stops the moment nothing is. A build
 * dismissed with × stays dismissed in this browser.
 */
(function () {
  "use strict";
  var strip = document.getElementById("building");
  var text = document.getElementById("building-text");
  var link = document.getElementById("building-link");
  var dismiss = document.getElementById("building-dismiss");
  if (!strip || !text || !link || !dismiss || typeof fetch !== "function") return;

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  var DISMISSED = "targum:dismissed";
  function dismissed() {
    try {
      return JSON.parse(localStorage.getItem(DISMISSED) || "{}");
    } catch (e) {
      return {};
    }
  }

  // The pipeline narrates itself in its own vocabulary. This is the reader's.
  var PLAIN = {
    "Finding each word's dictionary form…": "reading the words",
    "Adding vowel points…": "adding vowel points",
    "Building the reader…": "setting the page",
  };
  function plain(message) {
    if (!message) return "";
    if (PLAIN[message]) return PLAIN[message];
    if (message.indexOf("Matching") === 0) return "lining up";
    if (message.indexOf("Looking up") === 0) return "looking words up";
    return "";
  }

  function line(job) {
    // The English first where there is one: this strip is read by somebody waiting, and
    // a title they can read is the one that tells them which build this is.
    var title = job.title || "your text";
    if (job.english) title = job.english + " · " + title;
    if (job.stage === "done") return title + " is ready.";
    if (job.stage === "failed") return title + ": " + (job.error || "that did not work.");
    if (job.stage === "blocked") return title + ": " + (job.blocked || "not now.");
    if (job.stage === "queued") {
      return job.behind === 1
        ? "Waiting behind one other build: " + title
        : job.behind > 1
          ? "Waiting behind " + job.behind + " other builds: " + title
          : "Waiting: " + title;
    }
    var far = job.total ? Math.round((job.done / job.total) * 100) + "%" : plain(job.message);
    return "Building " + title + (far ? " · " + far : "");
  }

  var showing = null;
  var timer = null;

  function draw(jobs) {
    var gone = dismissed();
    var mine = jobs.filter(function (job) {
      return !gone[job.id];
    });
    if (!mine.length) {
      strip.hidden = true;
      showing = null;
      return false;
    }
    // The one that matters most: anything still going before anything finished.
    var live = mine.filter(function (job) {
      return job.stage !== "done" && job.stage !== "failed" && job.stage !== "blocked";
    });
    var job = live[0] || mine[0];
    showing = job;
    text.textContent = line(job);
    link.hidden = job.stage !== "done" || !job.reader;
    if (!link.hidden) {
      link.href = keyed("/reader/" + job.reader.split("/").map(encodeURIComponent).join("/"));
    }
    strip.hidden = false;
    return live.length > 0;
  }

  function ask() {
    fetch(keyed("/jobs"), { credentials: "same-origin" })
      .then(function (r) {
        return r.ok ? r.json() : { jobs: [] };
      })
      .then(function (data) {
        var going = draw((data && data.jobs) || []);
        if (going && !timer) timer = setInterval(ask, 3000);
        if (!going && timer) {
          clearInterval(timer);
          timer = null;
        }
      })
      .catch(function () {});
  }

  // Putting it away is asking to be told another way. The server says whether it can
  // — hosted, signed in, with an address to send — and only then is the promise made.
  var PROMISE = "You'll be updated by email when your targum is ready.";
  var promising = null;

  // Following the link is as final as the ×: a reader who has opened the text has no
  // further use for a strip that says it is ready, and it used to follow them from
  // page to page until they found the × themselves.
  link.addEventListener("click", function () {
    if (!showing) return;
    var gone = dismissed();
    gone[showing.id] = Date.now();
    try {
      localStorage.setItem(DISMISSED, JSON.stringify(gone));
    } catch (e) {}
  });

  dismiss.addEventListener("click", function () {
    if (!showing) return;
    var was = showing;
    var gone = dismissed();
    gone[was.id] = Date.now();
    try {
      localStorage.setItem(DISMISSED, JSON.stringify(gone));
    } catch (e) {}
    showing = null;
    var live = was.stage !== "done" && was.stage !== "failed" && was.stage !== "blocked";
    if (!live || !was.mail) {
      strip.hidden = true;
      ask();
      return;
    }
    fetch(keyed("/jobs/watch"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ id: was.id }),
    })
      .then(function (r) {
        return r.ok ? r.json() : {};
      })
      .then(function (answer) {
        if (!answer || !answer.watching) {
          strip.hidden = true;
          ask();
          return;
        }
        text.textContent = PROMISE;
        link.hidden = true;
        dismiss.hidden = true;
        strip.classList.add("promised");
        clearTimeout(promising);
        promising = setTimeout(function () {
          strip.hidden = true;
          strip.classList.remove("promised");
          dismiss.hidden = false;
          ask();
        }, 6000);
      })
      .catch(function () {
        strip.hidden = true;
        ask();
      });
  });

  ask();
})();
