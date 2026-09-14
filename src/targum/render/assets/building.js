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
 *
 * Since 2026-09-14 the panel stays open while you put lines away — the × used to close
 * it, because redrawing the list took the pressed button out of the page before the
 * press outside was judged — and Clear all puts every line away at once.
 */
(function () {
  "use strict";
  var open = document.getElementById("notices-open");
  var panel = document.getElementById("notices-panel");
  var count = document.getElementById("notices-count");
  var empty = document.getElementById("notices-empty");
  var list = document.getElementById("notices-list");
  var head = document.getElementById("notices-head");
  var clear = document.getElementById("notices-clear");
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
    if (message.indexOf("Matching") === 0) return "lining it up";
    if (message.indexOf("Looking up") === 0) return "looking up the words";
    return "";
  }

  // A title inside an English line, isolated (U+2068 … U+2069): unisolated, a Hebrew
  // title took the words beside it into its own direction, and a question mark at its
  // end jumped to the other side of the line (2026-09-14).
  function iso(text) {
    return "\u2068" + text + "\u2069";
  }

  function line(job) {
    // The English first where there is one: this line is read by somebody waiting, and
    // a title they can read is the one that tells them which build this is.
    var title = job.title ? iso(job.title) : "your text";
    if (job.english) title = iso(job.english) + " · " + title;
    if (job.stage === "done") return title + " is ready.";
    if (job.stage === "failed") return title + ": " + (job.error || "we couldn't get it ready.");
    if (job.stage === "blocked") return title + ": " + (job.blocked || "we can't do this one right now.");
    if (job.stage === "queued") {
      return job.behind === 1
        ? "We'll start " + title + " after one other text."
        : job.behind > 1
          ? "We'll start " + title + " after " + job.behind + " other texts."
          : "We'll start " + title + " next.";
    }
    var far = job.total ? Math.round((job.done / job.total) * 100) + "%" : plain(job.message);
    return "We're getting " + title + " ready" + (far ? " · " + far : "");
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
        show(false);
        entry.action();
      };
      li.appendChild(act);
    }
    var x = document.createElement("button");
    x.type = "button";
    x.className = "notices-x";
    x.setAttribute("aria-label", "Dismiss");
    x.textContent = "×";
    x.onclick = function () {
      pressed = Array.prototype.indexOf.call(list.querySelectorAll(".notices-x"), x);
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

  // Which × the keyboard was on, so a redraw — the one a × makes, or the poll's after it
  // — puts it on the line that took that place, or on the bell when none is left.
  var pressed = -1;

  function draw() {
    var rows = entries();
    var at = Array.prototype.indexOf.call(list.querySelectorAll(".notices-x"), document.activeElement);
    if (at < 0) at = pressed;
    pressed = -1;
    list.textContent = "";
    rows.forEach(function (entry) {
      list.appendChild(row(entry));
    });
    if (at >= 0) {
      var xs = list.querySelectorAll(".notices-x");
      (xs[Math.min(at, xs.length - 1)] || open).focus();
    }
    empty.hidden = rows.length > 0;
    if (head) head.hidden = rows.length === 0;
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
  var PROMISE = "We'll email you when it's ready.";
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

  // Clear all: each line as its own × would put it away, then one look at the server
  // rather than one for every build.
  function clearAll() {
    entries().forEach(function (entry) {
      if (entry.job && live(entry.job) && entry.job.mail) return dismissJob(entry.job);
      putAway(entry.job ? entry.job.id : entry.id);
      delete notes[entry.id];
    });
    draw();
    ask();
    open.focus();
  }
  if (clear) clear.addEventListener("click", clearAll);

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
        note("chat:" + chat.id + ":" + chat.answered, "New reply in " + (chat.title ? iso(chat.title) : "your conversation"), {
          label: "Open",
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
  // Inside is judged on the path the press took, not where its target is now: a × or
  // Clear all redraws the list, and the button pressed is no longer in the page by the
  // time the press reaches the document.
  var notices = document.getElementById("notices");
  document.addEventListener("click", function (event) {
    if (panel.hidden) return;
    var path = event.composedPath ? event.composedPath() : [];
    if (path.indexOf(notices) < 0) show(false);
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
      var reset = hours.ends ? " They reset on " + hours.ends + "." : "";
      note("hours:" + (hours.ends || "now"), "You've used " + hours.used + " of your " + hours.allowed + " hours this month." + reset, {
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
        note("series:" + one.id + ":" + inst.id, one.name + ": " + iso(inst.hebrew || inst.title), {
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
