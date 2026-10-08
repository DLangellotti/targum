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
 *
 * Since 2026-10-06 a build that is getting ready opens in place: its line is a button,
 * and under it the stage, a bar and the server's own sentence about it, followed live
 * while it is open (David: "I want to be able to click on one that is getting ready and
 * see the status live"). And every title in the bell is a <bdi> drawn as one box.
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
  // Keyed by the pipeline's English, which is what arrives; said in the reader's.
  var PLAIN = {
    "Finding each word's dictionary form…": function () {
      return t("building.plain.words", "reading the words");
    },
    "Adding vowel points…": function () {
      return t("building.plain.points", "adding vowel points");
    },
    "Building the reader…": function () {
      return t("building.plain.page", "setting the page");
    },
  };
  function plain(message) {
    if (!message) return "";
    if (Object.prototype.hasOwnProperty.call(PLAIN, message)) return PLAIN[message]();
    if (message.indexOf("Matching") === 0) return t("building.plain.lining-up", "lining it up");
    if (message.indexOf("Looking up") === 0) return t("building.plain.looking-up", "looking up the words");
    return "";
  }

  /* A title inside an English line, in a <bdi> drawn as one box (2026-10-06). Since
     2026-09-14 it was U+2068 … U+2069 inside the string, which isolated the title's
     direction and still let the line break inside it: a Hebrew title longer than the
     room left on the line was split over two lines, each reordered on its own, and
     "We're getting {title} ready" came out of the bell in pieces (David, 2026-10-06).
     The element isolates as the characters did, and as an inline block it moves to the
     next line whole and wraps inside itself, right to left. design.md §12, "The
     Hebrew-first audit", amended the same day: the characters are for plain text, and
     the bell is a page. */
  var SLOT = "\uE000";
  function bdi(text, language) {
    var b = document.createElement("bdi");
    b.className = "notices-title";
    b.textContent = text;
    // Hebrew script in its own face (the audit: anything tagged Hebrew-script takes the
    // Hebrew stack), named by the build's language where it is one of the three.
    if (/[\u0590-\u05ff]/.test(text)) b.lang = language === "yi" || language === "arc" ? language : "he";
    return b;
  }
  // A sentence said with SLOT where its title goes, and the title put there.
  function filled(text, title) {
    var out = document.createDocumentFragment();
    var parts = String(text).split(SLOT);
    parts.forEach(function (part, at) {
      if (part) out.appendChild(document.createTextNode(part));
      if (at < parts.length - 1) out.appendChild(title.cloneNode(true));
    });
    return out;
  }

  function titleOf(job) {
    // The English first where there is one: this line is read by somebody waiting, and
    // a title they can read is the one that tells them which build this is.
    var out = document.createDocumentFragment();
    if (job.english) {
      out.appendChild(bdi(job.english));
      out.appendChild(document.createTextNode(" · "));
    }
    if (job.title) out.appendChild(bdi(job.title, job.language));
    else out.appendChild(document.createTextNode(t("building.your-text", "your text")));
    return out;
  }

  function line(job) {
    var title = titleOf(job);
    var slot = { title: SLOT };
    if (job.stage === "done") return filled(t("building.ready", "{title} is ready.", slot), title);
    if (job.stage === "failed") {
      var failed = job.error || t("building.failed", "we couldn't get it ready. Try uploading it again.");
      return filled(SLOT + ": " + failed, title);
    }
    if (job.stage === "blocked") {
      var blocked = job.blocked || t("building.blocked", "we can't do this one right now.");
      return filled(SLOT + ": " + blocked, title);
    }
    if (job.stage === "queued") {
      return filled(
        job.behind > 0
          ? tn(
              "building.queued",
              job.behind,
              "We'll start {title} after one other text.",
              "We'll start {title} after {n} other texts.",
              slot
            )
          : t("building.next", "We'll start {title} next.", slot),
        title
      );
    }
    var far = job.total ? percent(job) + "%" : plain(job.message);
    var going = t("building.getting-ready", "We're getting {title} ready", slot);
    return filled(going + (far ? " · " + far : ""), title);
  }

  function percent(job) {
    return job.total ? Math.min(100, Math.round((job.done / job.total) * 100)) : 0;
  }

  function live(job) {
    return job.stage !== "done" && job.stage !== "failed" && job.stage !== "blocked";
  }

  /* --- A build opened in place (David, 2026-10-06: "I want to be able to click on one
     that is getting ready and see the status live") ---------------------------------
     A row that is getting ready, or that has failed, is a button; pressing it opens
     under it the stage in words, a bar from done and total, and the server's own line
     about it — `said`, the sentence `check_job` gives a host, with the time left only
     where a rate was counted. One open at a time. While it is open, the panel is open
     and the tab is in view, `/job/<id>` is asked every two seconds; collapsing it, its
     finishing or failing, closing the panel or leaving the tab stops that, and the
     list's own poll goes on by its old rule. A finished one turns back into the done
     row with its Open.

     A book needs nothing of its own here: its build ends when the first chapter is
     ready (the rest are made as they are read), so the done row's Open already opens
     what is ready, and while it runs `said` says it is the first chapter being made. */
  var STAGE = {
    "We're drawing…": function () {
      return t("building.stage.drawing", "Drawing the pictures");
    },
    "We're reading it aloud…": function () {
      return t("building.stage.voicing", "Recording the voice");
    },
    "Finding each word's dictionary form…": function () {
      return t("building.stage.words", "Reading the words");
    },
    "Adding vowel points…": function () {
      return t("building.stage.points", "Adding vowel points");
    },
    "Building the reader…": function () {
      return t("building.stage.page", "Setting the page");
    },
  };
  function stageOf(job) {
    if (job.stage === "queued") return t("building.stage.waiting", "Waiting to start");
    var message = job.message || "";
    if (Object.prototype.hasOwnProperty.call(STAGE, message)) return STAGE[message]();
    // The count moves only while sentences are translated, and whatever the pipeline
    // printed before that is still standing then: it is not what is happening.
    if (job.total > 0 && job.done < job.total) return t("building.stage.translating", "Translating");
    if (message.indexOf("Matching") === 0) return t("building.stage.lining-up", "Lining it up");
    if (message.indexOf("Looking up") === 0) return t("building.stage.looking-up", "Looking up the words");
    return t("building.stage.working", "Working on it");
  }

  function opens(job) {
    return live(job) || job.stage === "failed";
  }

  function statusId(job) {
    return "notices-status-" + String(job.id).replace(/[^\w-]/g, "_");
  }

  function status(job) {
    var box = document.createElement("div");
    box.className = "notices-status";
    box.id = statusId(job);
    if (job.stage === "failed") {
      // What happened and what to do, in the server's one sentence: the build's own
      // reason, and whether anything was used.
      var why = document.createElement("p");
      why.className = "notices-said";
      why.textContent =
        job.said || job.error || t("building.failed", "we couldn't get it ready. Try uploading it again.");
      box.appendChild(why);
      return box;
    }
    var stage = document.createElement("p");
    stage.className = "notices-stage";
    // Said when the stage changes, and not at every count: the bar carries the count.
    stage.setAttribute("aria-live", "polite");
    stage.textContent = stageOf(job);
    box.appendChild(stage);
    if (job.stage === "working" && job.total > 0) {
      var bar = document.createElement("div");
      bar.className = "notices-bar";
      bar.setAttribute("role", "progressbar");
      bar.setAttribute("aria-label", t("building.stage.progress", "How much is ready"));
      bar.setAttribute("aria-valuemin", "0");
      bar.setAttribute("aria-valuemax", String(job.total));
      bar.setAttribute("aria-valuenow", String(Math.min(job.done, job.total)));
      var fill = document.createElement("span");
      fill.style.inlineSize = percent(job) + "%";
      bar.appendChild(fill);
      box.appendChild(bar);
    }
    if (job.said) {
      var said = document.createElement("p");
      said.className = "notices-said";
      said.textContent = job.said;
      box.appendChild(said);
    }
    return box;
  }

  // An open status is changed where it stands rather than drawn again, so the bar moves
  // to its new width instead of jumping, and a screen reader is not handed it afresh.
  function refresh(box, job) {
    var next = status(job);
    var kids = box.children;
    var same =
      kids.length === next.children.length &&
      Array.prototype.every.call(next.children, function (kid, at) {
        return kid.className === kids[at].className;
      });
    if (!same) {
      box.textContent = "";
      while (next.firstChild) box.appendChild(next.firstChild);
      return;
    }
    Array.prototype.forEach.call(next.children, function (kid, at) {
      var old = kids[at];
      if (kid.className === "notices-bar") {
        old.setAttribute("aria-valuemax", kid.getAttribute("aria-valuemax"));
        old.setAttribute("aria-valuenow", kid.getAttribute("aria-valuenow"));
        old.firstChild.style.inlineSize = kid.firstChild.style.inlineSize;
      } else if (old.textContent !== kid.textContent) {
        old.textContent = kid.textContent;
      }
    });
  }

  // Lines other scripts add, by id, beside the builds; a promise made on a dismissed
  // build stands here for a moment too.
  var notes = {};
  var jobsNow = [];
  var timer = null;

  // The build whose status is open in the panel, by id, or "" for none; and the clock
  // that follows it.
  var opened = "";
  var follow = null;

  // A line's words: a string another script handed over, or nodes this file built with
  // its titles isolated.
  function words(entry) {
    var text = document.createElement("span");
    if (typeof entry.text === "string") text.textContent = entry.text;
    else if (entry.text) text.appendChild(entry.text.cloneNode(true));
    return text;
  }

  function row(entry) {
    var li = document.createElement("li");
    li.setAttribute("data-id", entry.id);
    if (entry.live) li.className = "live";
    var text = words(entry);
    if (entry.job && opens(entry.job)) {
      // The line itself is the press that opens it: a button saying whether it is open,
      // and what it opens.
      var flip = document.createElement("button");
      flip.type = "button";
      flip.className = "notices-row";
      var on = opened === entry.job.id;
      flip.setAttribute("aria-expanded", on ? "true" : "false");
      flip.setAttribute("aria-controls", statusId(entry.job));
      flip.appendChild(text);
      flip.onclick = function () {
        opened = opened === entry.job.id ? "" : entry.job.id;
        draw();
      };
      li.appendChild(flip);
      if (on) li.classList.add("opened");
    } else {
      li.appendChild(text);
    }
    if (entry.href) {
      var link = document.createElement("a");
      link.href = entry.href;
      link.textContent = entry.label || t("building.open", "Open");
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
      act.textContent = entry.label || t("building.open", "Open");
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
    x.setAttribute("aria-label", t("building.dismiss", "Dismiss"));
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
    // After the ×, so the × keeps its place on the line's first row of the grid.
    if (li.classList.contains("opened")) li.appendChild(status(entry.job));
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

  function lineOf(id) {
    for (var at = 0; at < list.children.length; at++) {
      if (list.children[at].getAttribute("data-id") === id) return list.children[at];
    }
    return null;
  }

  function draw() {
    var rows = entries();
    // A build that is no longer there, or no longer has a status to show, is not open:
    // a finished one turns back into the done row with its Open.
    var still = rows.some(function (entry) {
      return entry.job && entry.job.id === opened && opens(entry.job);
    });
    if (!still) opened = "";
    var at = Array.prototype.indexOf.call(list.querySelectorAll(".notices-x"), document.activeElement);
    if (at < 0) at = pressed;
    pressed = -1;
    // The line the keyboard was on, when it was not a ×: the button that opens a build,
    // so focus follows that build — onto its Open when it finishes.
    var active = document.activeElement;
    var held = "";
    if (at < 0 && active && active !== list && list.contains(active)) {
      var up = active;
      while (up && up.parentNode !== list) up = up.parentNode;
      held = up ? up.getAttribute("data-id") || "" : "";
    }
    // The open line is kept where it stands and changed in place; everything else is
    // drawn again around it.
    var kept = opened ? lineOf("job:" + opened) : null;
    if (kept && !kept.classList.contains("opened")) kept = null;
    var drawn = rows.map(function (entry) {
      if (kept && entry.id === kept.getAttribute("data-id")) {
        var flip = kept.querySelector(".notices-row");
        flip.replaceChild(words(entry), flip.firstChild);
        kept.className = entry.live ? "live opened" : "opened";
        refresh(kept.querySelector(".notices-status"), entry.job);
        return kept;
      }
      return row(entry);
    });
    Array.prototype.slice.call(list.children).forEach(function (child) {
      if (child !== kept) list.removeChild(child);
    });
    var past = false;
    drawn.forEach(function (li) {
      if (li === kept) past = true;
      else if (kept && !past) list.insertBefore(li, kept);
      else list.appendChild(li);
    });
    if (at >= 0) {
      var xs = list.querySelectorAll(".notices-x");
      (xs[Math.min(at, xs.length - 1)] || open).focus();
    } else if (held && !list.contains(document.activeElement)) {
      var back = lineOf(held);
      var to = back && back.querySelector(".notices-row, a, .notices-act, .notices-x");
      if (to) to.focus();
    }
    empty.hidden = rows.length > 0;
    if (head) head.hidden = rows.length === 0;
    count.hidden = rows.length === 0;
    count.textContent = String(rows.length);
    open.classList.toggle("live", rows.some(function (entry) { return entry.live; }));
    track();
  }

  // The open build is followed only while somebody could be watching it: open, in an
  // open panel, in a tab in view, and not yet finished. Anything else stops the clock.
  function watched() {
    if (!opened || panel.hidden || document.visibilityState === "hidden") return false;
    return jobsNow.some(function (job) {
      return job.id === opened && live(job);
    });
  }
  function track() {
    var want = watched();
    if (want && !follow) {
      follow = setInterval(lookAt, 2000);
      lookAt();
    }
    if (!want && follow) {
      clearInterval(follow);
      follow = null;
    }
  }
  function lookAt() {
    var id = opened;
    if (!id) return;
    fetch(keyed("/job/" + encodeURIComponent(id)), { credentials: "same-origin" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (fresh) {
        // A build the server lost answers with an error and no id; the list's own poll
        // is what takes it off.
        if (!fresh || fresh.id !== id) return;
        jobsNow = jobsNow.map(function (job) {
          if (job.id !== id) return job;
          var both = { mail: job.mail, behind: fresh.stage === "queued" ? job.behind : 0 };
          for (var name in fresh) both[name] = fresh[name];
          return both;
        });
        draw();
      })
      .catch(function () {});
  }
  document.addEventListener("visibilitychange", function () {
    track();
  });

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
  function promise() {
    return t("building.promise", "We'll email you when it's ready.");
  }
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
        note("promise:" + job.id, promise(), { live: false });
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
        var about = chat.title
          ? bdi(chat.title)
          : document.createTextNode(t("building.your-conversation", "your chat"));
        var said = filled(t("building.new-reply", "New reply in {title}", { title: SLOT }), about);
        note("chat:" + chat.id + ":" + chat.answered, said, {
          label: t("building.open", "Open"),
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
    track();
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

  // Hours as a person says them: "6 hours 30 minutes", never "6.5" (2026-09-14).
  function clockOf(hours) {
    var minutes = Math.round((Number(hours) || 0) * 60);
    var whole = Math.floor(minutes / 60);
    var rest = minutes % 60;
    var parts = [];
    if (whole) parts.push(tn("account.hours", whole, "{n} hour", "{n} hours"));
    if (rest || !whole) parts.push(tn("account.minutes", rest, "{n} minute", "{n} minutes"));
    return parts.join(" ");
  }

  // The month's credits, once they are nearly gone (2026-09-11): the same threshold the
  // box uses, three quarters, said in the inbox with the door to the count.
  fetch(keyed("/account/me"), { credentials: "same-origin" })
    .then(function (r) {
      return r.ok ? r.json() : null;
    })
    .then(function (me) {
      var hours = me && me.signedIn && me.hours;
      if (!hours || !hours.allowed || !(hours.used >= hours.allowed * 0.75)) return;
      var reset = hours.ends ? " " + t("building.hours.reset", "They come back on {date}.", { date: hours.ends }) : "";
      /* Credits with the rate beside them (design.md §12, 2026-09-23), and what is left
         rather than what is gone — this is a warning, and what remains is the thing it
         is warning about. It said "You've used 6.2 of your 8 hours", a decimal nobody
         reads as six hours twelve, which is the fault the account page was fixed for on
         2026-09-14 and this line kept. */
      var spare = Math.max(0, (Number(hours.allowed) || 0) - (Number(hours.used) || 0));
      var used =
        tn(
          "building.credits.left",
          Math.round(spare * 60),
          "{n} credit left this month.",
          "{n} credits left this month."
        ) +
        " " +
        t("building.credits.rate", "That's about {clock} of audio.", { clock: clockOf(spare) });
      note("hours:" + (hours.ends || "now"), used + reset, {
        href: keyed("/progress"),
        label: t("building.hours.see", "See usage"),
      });
    })
    .catch(function () {});

  // A followed series' instalment that landed (2026-09-11): said here on every page,
  // with a door to its reader; Learn puts it in the sheet as well. The reader and not the
  // series' public page, as Learn's own door does (David, 2026-09-11: "it should open the
  // reader, not their marketing landing pages") — the week's portion included, which a
  // signed-in reader opens in the Library's reader (targum-internal#410).
  if (window.TargumFollow) {
    window.TargumFollow.list().then(function (series) {
      window.TargumFollow.fresh(series).forEach(function (one) {
        var inst = one.instalment;
        // Both names isolated: a series can be named in Hebrew as well as its instalment.
        var said = document.createDocumentFragment();
        said.appendChild(bdi(one.name));
        said.appendChild(document.createTextNode(": "));
        said.appendChild(bdi(inst.hebrew || inst.title));
        note("series:" + one.id + ":" + inst.id, said, {
          href: keyed(window.TargumFollow.readerOf(one) || one.page),
          label: t("building.open", "Open"),
        });
      });
    });
  }

  // Another script on the page that has just started a build asks the bell to look
  // again, rather than waiting for a poll that only runs while something is unfinished.
  window.TargumBuilding = { ask: ask };
  window.TargumNotices = { note: note, ask: ask, bdi: bdi };
})();
