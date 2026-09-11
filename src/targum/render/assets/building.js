/* Notifications: a build you can walk away from, and anything else the page has to say.
 *
 * The id of a build used to live only in the page that started it, so leaving that page
 * made the build look cancelled. It was not: the server kept it, and the reader turned
 * up on the shelf later with nothing to say how. This asks the server for every build
 * of yours and says, on whichever page you are on, where each has got to — and when one
 * is done, hands over the link.
 *
 * Since 2026-09-11 it is a bell in the bar with a count, and a panel under it listing
 * every build, newest first, each with its own ×; it used to be one pill fixed at the
 * foot of the window that showed one build at a time. Polls only while something is
 * unfinished, and stops the moment nothing is. A build dismissed with × stays dismissed
 * in this browser. Other scripts may add a line of their own with `TargumNotices.note`.
 */
(function () {
  "use strict";
  var open = document.getElementById("notices-open");
  var panel = document.getElementById("notices-panel");
  var count = document.getElementById("notices-count");
  var empty = document.getElementById("notices-empty");
  var list = document.getElementById("notices-list");
  if (!open || !panel || !count || !empty || !list || typeof fetch !== "function") return;

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
  function putAway(id) {
    var gone = dismissed();
    gone[id] = Date.now();
    try {
      localStorage.setItem(DISMISSED, JSON.stringify(gone));
    } catch (e) {}
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
    // The English first where there is one: this line is read by somebody waiting, and
    // a title they can read is the one that tells them which build this is.
    var title = job.title || "your text";
    if (job.english) title = job.english + " · " + title;
    if (job.stage === "done") return title + " is ready.";
    if (job.stage === "failed") return title + ": " + (job.error || "that did not work.");
    if (job.stage === "blocked") return title + ": " + (job.blocked || "not now.");
    if (job.stage === "queued") {
      return job.behind === 1
        ? "Waiting behind one other text: " + title
        : job.behind > 1
          ? "Waiting behind " + job.behind + " other texts: " + title
          : "Waiting: " + title;
    }
    var far = job.total ? Math.round((job.done / job.total) * 100) + "%" : plain(job.message);
    return "Building " + title + (far ? " · " + far : "");
  }

  function live(job) {
    return job.stage !== "done" && job.stage !== "failed" && job.stage !== "blocked";
  }

  // Lines other scripts add, by id, beside the builds; a promise made on a dismissed
  // build stands here for a moment too.
  var notes = {};
  var jobsNow = [];
  var timer = null;

  function row(entry) {
    var li = document.createElement("li");
    if (entry.live) li.className = "live";
    var text = document.createElement("span");
    text.textContent = entry.text;
    li.appendChild(text);
    if (entry.href) {
      var link = document.createElement("a");
      link.href = entry.href;
      link.textContent = entry.label || "Open";
      // Following the link is as final as the ×: a reader who has opened the text has
      // no further use for a line that says it is ready.
      link.onclick = function () {
        if (entry.job) putAway(entry.job.id);
      };
      li.appendChild(link);
    } else if (entry.action) {
      // A press that acts on this page rather than going to another: the drawer.
      var act = document.createElement("button");
      act.type = "button";
      act.className = "notices-act";
      act.textContent = entry.label || "Open";
      act.onclick = function () {
        putAway(entry.id);
        delete notes[entry.id];
        draw();
        entry.action();
      };
      li.appendChild(act);
    }
    var x = document.createElement("button");
    x.type = "button";
    x.setAttribute("aria-label", "Dismiss");
    x.textContent = "×";
    x.onclick = function () {
      if (entry.job) dismissJob(entry.job);
      else {
        // Put away for good, in this browser: a landed instalment or the month's hours
        // said once is said; it does not come back on the next page.
        putAway(entry.id);
        delete notes[entry.id];
        draw();
      }
    };
    li.appendChild(x);
    return li;
  }

  function entries() {
    var gone = dismissed();
    var out = [];
    jobsNow.forEach(function (job) {
      if (gone[job.id]) return;
      var href = "";
      if (job.stage === "done" && job.reader) {
        href = keyed("/reader/" + job.reader.split("/").map(encodeURIComponent).join("/"));
      }
      out.push({ id: "job:" + job.id, job: job, text: line(job), href: href, live: live(job) });
    });
    Object.keys(notes).forEach(function (id) {
      if (!gone[id]) out.push(notes[id]);
    });
    return out;
  }

  function draw() {
    var rows = entries();
    list.textContent = "";
    rows.forEach(function (entry) {
      list.appendChild(row(entry));
    });
    empty.hidden = rows.length > 0;
    count.hidden = rows.length === 0;
    count.textContent = String(rows.length);
    open.classList.toggle("live", rows.some(function (entry) { return entry.live; }));
  }

  function ask() {
    fetch(keyed("/jobs"), { credentials: "same-origin" })
      .then(function (r) {
        return r.ok ? r.json() : { jobs: [] };
      })
      .then(function (data) {
        jobsNow = (data && data.jobs) || [];
        draw();
        var going = entries().some(function (entry) { return entry.live; });
        if (going && !timer) timer = setInterval(ask, 3000);
        if (!going && timer) {
          clearInterval(timer);
          timer = null;
        }
      })
      .catch(function () {});
  }

  // Putting a live build away is asking to be told another way. The server says whether
  // it can — hosted, signed in, with an address to send — and only then is the promise
  // made, and said once.
  var PROMISE = "You'll be updated by email when your targum is ready.";
  function dismissJob(job) {
    putAway(job.id);
    draw();
    if (!live(job) || !job.mail) {
      ask();
      return;
    }
    fetch(keyed("/jobs/watch"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ id: job.id }),
    })
      .then(function (r) {
        return r.ok ? r.json() : {};
      })
      .then(function (answer) {
        if (!answer || !answer.watching) return ask();
        note("promise:" + job.id, PROMISE, { live: false });
        setTimeout(function () {
          delete notes["promise:" + job.id];
          draw();
          ask();
        }, 6000);
      })
      .catch(function () {
        ask();
      });
  }

  function note(id, text, extra) {
    extra = extra || {};
    notes[id] = {
      id: id,
      text: text,
      href: extra.href || "",
      action: extra.action || null,
      label: extra.label || "",
      live: !!extra.live,
    };
    draw();
  }

  // An answer that arrived while you were away (2026-09-11): a conversation targum
  // finished answering after the person last opened it. Opening it from here is the
  // drawer, by name; the note is put away as the press is made.
  fetch(keyed("/chat/list?limit=20"), { credentials: "same-origin" })
    .then(function (r) {
      return r.ok ? r.json() : null;
    })
    .then(function (got) {
      ((got && got.chats) || []).forEach(function (chat) {
        if (!chat.answered || !(chat.answered > (chat.opened || 0))) return;
        note("chat:" + chat.id + ":" + chat.answered, "targum answered: " + (chat.title || "a conversation"), {
          label: "Read",
          action: function () {
            if (window.TargumTalk && window.TargumTalk.open) window.TargumTalk.open(chat.id);
            else window.location.href = keyed("/chat") + "#" + encodeURIComponent(chat.id);
          },
        });
      });
    })
    .catch(function () {});

  // The panel opens and closes like the account's: the bell, a press outside, Escape.
  function show(on) {
    panel.hidden = !on;
    open.setAttribute("aria-expanded", on ? "true" : "false");
    open.classList.toggle("on", on);
  }
  open.addEventListener("click", function () {
    show(panel.hidden);
  });
  document.addEventListener("click", function (event) {
    if (panel.hidden) return;
    var inside = event.target && event.target.closest ? event.target.closest("#notices") : null;
    if (!inside) show(false);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !panel.hidden) show(false);
  });

  ask();

  // The month's hours, once they are nearly gone (2026-09-11): the same threshold the
  // box uses, three quarters, said in the inbox with the door to the count.
  fetch(keyed("/account/me"), { credentials: "same-origin" })
    .then(function (r) {
      return r.ok ? r.json() : null;
    })
    .then(function (me) {
      var hours = me && me.signedIn && me.hours;
      if (!hours || !hours.allowed || !(hours.used >= hours.allowed * 0.75)) return;
      var month = hours.ends ? " until " + hours.ends : " this month";
      note("hours:" + (hours.ends || "now"), hours.used + " of " + hours.allowed + " hours used" + month, {
        href: keyed("/progress"),
        label: "See",
      });
    })
    .catch(function () {});

  // A followed series' instalment that landed (2026-09-11): said here on every page,
  // with a door to its page; Learn puts it in the sheet as well.
  if (window.TargumFollow) {
    window.TargumFollow.list().then(function (series) {
      window.TargumFollow.fresh(series).forEach(function (one) {
        var inst = one.instalment;
        note("series:" + one.id + ":" + inst.id, one.name + ": " + (inst.hebrew || inst.title), {
          href: keyed(one.page || window.TargumFollow.readerOf(one)),
          label: "Open",
        });
      });
    });
  }

  // Another script on the page that has just started a build asks the bell to look
  // again, rather than waiting for a poll that only runs while something is unfinished.
  window.TargumBuilding = { ask: ask };
  window.TargumNotices = { note: note, ask: ask };
})();
