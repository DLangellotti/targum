/* The reader's closures that wait for nothing it does first: hearing a silent text,
 * the ⋯ menu's playlist and sheet, the columns that switch themselves and the bar that
 * steps back. They stood at the foot of `reader.js` and ran right after it, and still
 * do, from the script after it — split off so that a word answers a tap as soon as
 * `reader.js` has arrived, rather than when these have too (reader QA,
 * targum-internal#464, 2026-10-20). Where to go next, the next chapter bought ahead and
 * the chapter nobody has paid for yet followed them (targum-internal#503): each was its
 * own scope already, and none reads the store `reader.js` waits for.
 */

/* Where to go next, shown only where there is somewhere to go.
 *
 * The address is the library's, so it means nothing to a reader opened from a disk —
 * which is a real way to read one of these and the reason nothing here is fetched. The
 * suggestion is written into the page either way and revealed only when the page arrived
 * over a connection, rather than offering a link that leads nowhere.
 */
(function () {
  "use strict";
  if (location.protocol === "file:") return;
  var next = document.getElementById("next-up");
  // The near one is the next section of this same folder, on a relative address that
  // works off a disk — it is not waiting to find out how the page was opened, and it is
  // waiting for something else entirely: the section being finished.
  if (next && !next.classList.contains("here")) next.hidden = false;

  /* And a way to disagree with it (targum-internal#233).
   *
   * One offer, and a link beside it that draws again. No state, no preference, nothing
   * sent anywhere: the alternatives are written into the page, because the page fetches
   * nothing, and a refusal the server remembered would turn a door into a profile
   * nobody asked to build. The point of the offer is that saying yes costs nothing, and
   * this is what makes saying no cost nothing too.
   *
   * Each pick carries its own reason, so the second is "a step up, in a different
   * Hebrew" or "easier than this one" and never "another one". The list runs out rather
   * than looping: a control that offers for ever is offering nothing.
   */
  var elsewhere = document.getElementById("next-up-else");
  if (!next || !elsewhere) return;
  var more;
  try {
    more = JSON.parse(elsewhere.getAttribute("data-more") || "[]");
  } catch (error) {
    return;
  }
  if (!more.length) return;
  elsewhere.hidden = false;

  var link = next.querySelector(".next-up-link");
  var lead = next.querySelector(".next-up-lead");
  var why = next.querySelector(".next-up-why");

  elsewhere.addEventListener("click", function () {
    var pick = more.shift();
    if (!pick) return;
    if (link) {
      // The same door the first offer uses: straight to the text where it is built, to
      // its row with the offer up where it is not (targum-internal#313).
      link.href = "/open/" + encodeURIComponent(pick.id);
      link.textContent = "";
      var named = document.createElement("bdi");
      named.lang = document.documentElement.getAttribute("data-language") || "";
      named.dir = "auto";
      named.textContent = pick.title;
      link.appendChild(named);
      if (pick.english) {
        var english = document.createElement("span");
        english.className = "next-up-english";
        english.lang = "en";
        english.textContent = "· " + pick.english;
        link.appendChild(document.createTextNode(" "));
        link.appendChild(english);
      }
    }
    var say = window.TargumStrings || { t: function (key, english) { return english; } };
    if (lead) lead.textContent = say.t("reader.next.lead", "Up next");
    if (why) {
      why.textContent =
        pick.because +
        (pick.minutes ? " · " + say.t("reader.next.minutes", "{n} min").replace("{n}", pick.minutes) : "");
      why.hidden = !pick.because;
    }
    // The count of words known was about the first offer, and this is another.
    var known = next.querySelector(".next-up-known");
    if (known) known.hidden = true;
    // Nothing left to draw, so the control goes rather than sitting there inert.
    if (!more.length) elsewhere.hidden = true;
  });
})();

/* --- the next chapter, bought before it is needed ---------------------------
 *
 * A book is paid for a chapter at a time. Waiting until somebody finishes one puts a
 * minute of dead time at every boundary — translating a chapter takes well under a
 * minute and reading one takes ten — so the next is started once they are most of the
 * way through this one. Nothing is bought from a reader who leaves early, and nobody
 * waits at the turn of a page.
 */
(function () {
  "use strict";
  if (location.protocol === "file:") return;

  var pager = document.querySelector(".pager[data-chapter]");
  var link = pager && pager.querySelector("[data-next]");
  if (!link) return;
  // Not from a part still waiting to be heard. Its page is a clock and nothing else, so
  // it is "most of the way through" the moment it opens, and every waiting part a reader
  // looked at bought the one after it — ahead of the part they came to press for.
  if (document.querySelector("#waiting-note[data-audio]")) return;
  // Its own, because this is its own scope: it read `passKey` and called `keyed` across
  // the boundary, and neither was ever in reach. No key hosted, where the session cookie
  // identifies the reader; a key locally. This used to stop when there was no key — so
  // on the live site the next chapter was never bought, and the first alpha reader
  // followed the arrow into a page of blank translations.
  var key = new URLSearchParams(location.search).get("k") || "";

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  // The path is /reader/<folder>/reader/<file>: the route prefix and the folder inside
  // the build are both called "reader", so it is the *last* one the name sits before.
  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  // Far enough in that they are reading it rather than glancing at it.
  var ENOUGH = 0.6;
  var asked = false;

  function through() {
    // Paged, the page says; otherwise the scroll does. Its own scope, so it asks the
    // reader above it through the one seam that scope leaves open.
    var reader = window.TargumReader;
    if (reader && reader.through) {
      var far = reader.through();
      if (far !== null && far !== undefined) return far;
    }
    var height = document.documentElement.scrollHeight - window.innerHeight;
    return height > 0 ? window.scrollY / height : 1;
  }

  function maybe() {
    if (asked || through() < ENOUGH) return;
    asked = true;
    window.removeEventListener("scroll", maybe);
    // In the language this page is being read in. Its own scope, so it asks the page
    // rather than the reader above it — and the page is kept honest by the picker, which
    // restamps every cell it swaps. Without this the next chapter of a Russian book was
    // bought in English, because the server's fallback was English and nothing said
    // otherwise.
    var reading = document.querySelector(".pair .tr");
    var into = reading ? reading.getAttribute("lang") || "" : "";
    fetch(keyed("/chapter"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        name: name,
        number: Number(link.getAttribute("data-next")),
        to: into,
      }),
    }).catch(function () {});
  }

  /* An imported recording is not a book (David, 2026-10-07; design.md §12, "One press
     gets the whole video, a part at a time"): the press on its quote took every part's
     credits, so the next part is asked for once, the moment this one is opened — the
     reader is on it — and the box makes it if the part before it, this one, is ready.
     Never further: the box refuses a part whose page before it is still waiting. And
     the door under the picture says what became of it, from the answer and from the
     job the waiting press already watches, so nothing new is fetched. */
  if (pager.hasAttribute("data-by-part")) {
    var S = window.TargumStrings || {
      t: function (k, english) {
        return english;
      },
    };
    var door = document.getElementById("film-next");
    var go = door && door.querySelector(".film-next-go");
    var said = door && door.querySelector(".film-next-said");
    var again = door && door.querySelector(".film-next-again");
    var making = "";
    var wanted = false;
    var timer = 0;
    var tell = function (state, text, job) {
      if (door) door.setAttribute("data-state", state);
      if (said) said.textContent = text || "";
      if (again) again.hidden = state !== "failed";
      // A refusal wears the clay mark, and one that was refused by a rail says what still
      // works and draws its way on: Top up greyed, until there is somewhere to pay
      // (design.md §12, 2026-10-09).
      if (said) said.classList.toggle("fault-marked", state === "failed" || state === "refused");
      var extra = door && door.querySelector(".film-next-extra");
      if (extra) extra.parentNode.removeChild(extra);
      if (state === "refused" && job && job.act === "plan" && said && window.TargumFault) {
        // A free reader out of credits is offered the plan, as a panel of its own in
        // place of the line (design.md §12, "A free reader meets the plan where they
        // reach for it", 2026-10-09).
        said.textContent = "";
        said.classList.remove("fault-marked");
        extra = window.TargumFault.upgrade(text || "", job.fact || "");
        extra.classList.add("film-next-extra");
        said.parentNode.insertBefore(extra, said.nextSibling);
      } else if (state === "refused" && job && (job.fact || job.act === "top-up") && said) {
        extra = document.createElement("span");
        extra.className = "film-next-extra fault-panel-row";
        if (job.act === "top-up") {
          var up = document.createElement("button");
          up.type = "button";
          up.className = "fault-go";
          up.disabled = true;
          up.textContent = S.t("fault.top-up", "Top up");
          extra.appendChild(up);
          var soon = document.createElement("span");
          soon.className = "fault-fact";
          soon.textContent = S.t("fault.payments-soon", "Payments open soon");
          extra.appendChild(soon);
        }
        if (job.fact) {
          var fact = document.createElement("span");
          fact.className = "fault-fact";
          fact.textContent = job.fact;
          extra.appendChild(fact);
        }
        said.parentNode.insertBefore(extra, said.nextSibling);
      }
    };
    var stop = function () {
      clearInterval(timer);
      timer = 0;
      making = "";
    };
    var ready = function () {
      stop();
      tell("ready", "");
      // Pressed while it was being made: the press was the reader's, so it opens now,
      // through the door's own link rather than a second way out of the page.
      if (wanted && go) go.click();
    };
    var failed = function (text) {
      stop();
      tell("failed", text || S.t("reader.film.next-part-trouble", "We couldn't get the next part ready."));
    };
    var refused = function (text, job) {
      stop();
      tell("refused", text, job);
    };
    // Looked at only while the door is on screen or was pressed: a part takes minutes
    // and the reader is watching this one, so nobody needs a clock ticking under it.
    var look = function () {
      if (!making) return;
      if (!wanted && !document.body.classList.contains("film-at-end")) return;
      fetch(keyed("/job/" + making))
        .then(function (r) {
          return r.json();
        })
        .then(function (state) {
          if (state.stage === "done") ready();
          else if (state.stage === "blocked" || state.blocked) refused(state.blocked || state.error, state);
          else if (state.stage === "failed" || (state.error && !state.stage)) failed(state.error);
        })
        .catch(function () {});
    };
    var watch = function (id) {
      making = id;
      tell(
        "making",
        wanted
          ? S.t("reader.film.next-part-opening", "We'll open it when it's ready.")
          : S.t("reader.film.next-part-making", "We're getting it ready.")
      );
      if (!timer) timer = setInterval(look, 4000);
    };
    var ask = function () {
      var reading = document.querySelector(".pair .tr");
      fetch(keyed("/chapter"), {
        method: "POST",
        headers: keyHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          name: name,
          number: Number(link.getAttribute("data-next")),
          to: reading ? reading.getAttribute("lang") || "" : "",
          ahead: true,
        }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (job) {
          if (job.ready || job.stage === "done") return ready();
          if (job.blocked || job.stage === "blocked") return refused(job.blocked || job.error, job);
          if (job.stage === "failed") return failed(job.error);
          if (job.id) return watch(job.id);
          // `waiting`: this part is not ready itself, so nothing is made ahead of it.
        })
        .catch(function () {});
    };
    // The door's press, and Next part in the row under the picture (David, 2026-10-11),
    // which is the same press from the middle of a part: a part still being made is
    // waited for, and pressed from the row the door comes up under the picture to say
    // so, with its Try again, rather than a second way of saying it.
    var pressed = function (event) {
      if (!making) return;
      event.preventDefault();
      wanted = true;
      document.body.classList.add("film-next-asked");
      tell("making", S.t("reader.film.next-part-opening", "We'll open it when it's ready."));
      look();
    };
    if (go) go.addEventListener("click", pressed);
    var onward = document.querySelector(".film-part-next");
    if (onward) onward.addEventListener("click", pressed);
    // Within the consent the quote's press gave: the same ask, for the same part.
    if (again) {
      again.addEventListener("click", function () {
        tell("making", S.t("reader.film.next-part-making", "We're getting it ready."));
        ask();
      });
    }
    ask();
    return;
  }

  // Nothing to buy where the next chapter is already on the page's own say, and nothing
  // that is not a reader's own: a portion is served from its own shelf, and a text off
  // the shared one is complete. Asked anyway, each answered 404 in the console on every
  // first text (known issues 2026-10-12, m6). A page built before `data-ready` asks as
  // it always did, until it is rebuilt.
  if (link.hasAttribute("data-ready")) return;
  if (parts[1] !== "reader") return;

  // Fetched ahead only for an account: signed out `/chapter` refuses, and the refusal
  // was a console error at the foot of every chapter (QA 2026-10-11).
  (window.TargumSync && window.TargumSync.mayAsk ? window.TargumSync.mayAsk() : Promise.resolve(true)).then(function (may) {
    if (!may) return;
    window.addEventListener("scroll", maybe, { passive: true });
    document.addEventListener("targum:page", maybe);
    maybe();
  });
})();

/* --- a chapter nobody has paid for yet ----------------------------------------
 *
 * The page says so above the text, and this is the button on it. Its own scope, like
 * the prefetch above: it needs the key helpers and the folder name and nothing else.
 * Off a disk there is no server to ask, and the button stays hidden; the line above
 * it still says what the page is.
 */
(function () {
  "use strict";
  var note = document.getElementById("waiting-note");
  var press = document.getElementById("translate-chapter");
  if (!note || !press || location.protocol === "file:") return;

  var key = new URLSearchParams(location.search).get("k") || "";
  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  // The reader's own words (targum-internal#184), where the page is read in another language.
  var said = window.TargumStrings || { t: function (key, english) { return english; } };
  var trouble = said.t("reader.chapter.could-not-start", "We couldn't start that.");

  // A part of an imported recording is not pressed for (David, 2026-10-07; design.md §12,
  // "One press gets the whole video, a part at a time"): the press on the recording's
  // quote was consent to every part, so opening the page is what starts it, and the page
  // says it is being made and opens itself when it is. The button stands only to try
  // again after a failure, under the same consent. A book's chapter keeps its press.
  var hearing = note.hasAttribute("data-audio");
  var status = document.getElementById("waiting-said");
  press.hidden = hearing;
  // Its cost beside it, where the page knows one; shown with the press it prices.
  var costs = document.getElementById("waiting-cost");
  if (costs) costs.hidden = false;
  var pressWord = press.textContent;
  // What went wrong is a line, and the press under it says Try again. A book's chapter
  // used to put the sentence on the button itself, so the reason became the label of a
  // press that only asked again (reader QA, 2026-10-19).
  function fail(text) {
    press.disabled = false;
    if (status) {
      status.textContent = text;
      status.classList.add("fault-marked");
    }
    press.textContent = said.t("reader.film.next-part-again", "Try again");
    press.hidden = false;
  }
  press.onclick = function () {
    press.disabled = true;
    if (status) status.classList.remove("fault-marked");
    if (status && !hearing) status.textContent = "";
    if (hearing) {
      press.hidden = true;
      if (status) status.textContent = said.t("reader.film.next-part-making", "We're getting it ready.");
    }
    // The page says which work is owed — a translation, or for an imported recording a
    // transcript — and the working form keeps that promise. Read off the attribute, not
    // the button's word, which is the reader's language.
    press.textContent =
      press.getAttribute("data-owed") === "transcript"
        ? said.t("reader.chapter.transcribing", "Transcribing…")
        : said.t("reader.chapter.translating", "Translating…");
    fetch(keyed("/chapter"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      // In the language this page is being read in, as the prefetch asks: without it the
      // server bought its most complete language, which in a folder holding English and
      // Russian was English (targum-internal#287).
      body: JSON.stringify({
        name: name,
        number: Number(note.getAttribute("data-chapter")),
        to: (function () {
          var reading = document.querySelector(".pair .tr");
          return reading ? reading.getAttribute("lang") || "" : "";
        })(),
      }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (job) {
        if (job.ready) return location.reload();
        // Refused at the door — over the month's hours, or the day's — says so now. A
        // refusal still carries an id, and polling a job that was never kept waited on
        // "Translating…" for ever (2026-09-14).
        if (job.blocked || job.stage === "blocked") throw new Error(job.blocked || job.error);
        if (!job.id) throw new Error(job.error || job.blocked || trouble);
        var timer = setInterval(function () {
          fetch(keyed("/job/" + job.id))
            .then(function (r) {
              return r.json();
            })
            .then(function (state) {
              if (state.stage === "done") {
                clearInterval(timer);
                location.reload();
              } else if (state.stage === "failed" || state.blocked || (state.error && !state.stage)) {
                clearInterval(timer);
                fail(state.error || state.blocked || trouble);
              }
            })
            .catch(function () {
              clearInterval(timer);
              if (!window.TargumFault) return fail(said.t("reader.chapter.could-not-reach", "We can't reach targum."));
              // The connection's banner (design.md §12, 2026-10-09), whose Try again asks
              // again; the server hands back the job already under way.
              press.disabled = false;
              press.textContent = pressWord;
              window.TargumFault.unreachable(function () {
                press.onclick();
              });
            });
        }, 1500);
      })
      .catch(function (problem) {
        fail(String(problem.message || problem));
      });
  };
  if (hearing) press.onclick();
})();

/* --- hear a silent text ---------------------------------------------------------
 *
 * The door in This text on a section with no recording (targum-internal#246): the press
 * asks the server to read the section aloud, waits for the build the way the strip does,
 * and reopens the page, which now carries the audio and every per-line control. Its own
 * scope, like the chapter buy: the key helpers and the folder name and nothing else.
 * Off a disk there is no server to ask, and the door stays hidden.
 */
(function () {
  "use strict";

  var offer = document.getElementById("voice-offer");
  var go = document.getElementById("voice-go");
  var said = document.getElementById("voice-said");
  var making = document.getElementById("voice-making");
  var meter = document.getElementById("voice-meter");
  var share = document.getElementById("voice-share");
  if (!offer || !go) return;
  var S = window.TargumStrings || {
    t: function (key, english, fill) {
      return fill ? english.replace("{n}", String(fill.n)) : english;
    },
    tn: function (key, count, one, other) {
      return (count === 1 ? one : other).replace("{n}", String(count));
    },
  };
  if (location.protocol === "file:") {
    offer.hidden = true;
    return;
  }
  var passKey = "";
  try {
    passKey = new URLSearchParams(location.search).get("k") || "";
  } catch (e) {
    passKey = "";
  }
  function keyed(path) {
    if (!passKey) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(passKey);
  }
  function keyHeaders(extra) {
    var head = extra || {};
    if (passKey) head["X-Targum-Key"] = passKey;
    return head;
  }
  var parts = location.pathname.split("/");
  var name = decodeURIComponent(parts[parts.lastIndexOf("reader") - 1] || "");
  if (!name) return;

  function tell(text) {
    if (said) said.textContent = text || "";
  }

  // Whether this page is following the section's audio, from a press or from a job it
  // found underway when it opened: either way the button is not offered again.
  var busy = false;

  /* The audio on its way (2026-10-10): the button stands aside, and the meter fills to
   * the share of lines said where the job counts them, or only says it is working where
   * it does not yet — waiting in line, or just pressed. */
  function showMaking(state) {
    busy = true;
    go.hidden = true;
    if (!making || !meter) return;
    making.hidden = false;
    var total = Number((state && state.total) || 0);
    var done = Math.min(total, Number((state && state.done) || 0));
    if (total > 0 && state.stage === "working") {
      var part = Math.round((done / total) * 100);
      meter.classList.remove("is-waiting");
      meter.style.setProperty("--done", String(done / total));
      meter.setAttribute("aria-valuenow", String(part));
      if (share) share.textContent = S.t("reader.voice.share-done", "{n}% done", { n: part });
    } else {
      meter.classList.add("is-waiting");
      meter.style.removeProperty("--done");
      meter.removeAttribute("aria-valuenow");
      if (share) share.textContent = "";
    }
  }

  function stopMaking() {
    busy = false;
    if (making) making.hidden = true;
    go.hidden = false;
  }

  //: How often the page asks after the build. A test sets it to 0.
  var POLL = 2000;

  function follow(id) {
    fetch(keyed("/job/" + encodeURIComponent(id)), { headers: keyHeaders({}) })
      .then(function (response) {
        return response.json();
      })
      .then(function (state) {
        if (state.error && !state.stage) return failed(state.error);
        if (state.stage === "failed" || state.stage === "blocked") {
          return failed(
            state.error ||
              state.blocked ||
              S.t("reader.voice.could-not-make", "We couldn't make the audio. Try again.")
          );
        }
        if (state.stage === "done") {
          tell(S.t("reader.voice.ready", "Ready."));
          location.reload();
          return;
        }
        showMaking(state);
        setTimeout(function () {
          follow(id);
        }, window.TargumVoice.POLL);
      })
      .catch(function () {
        lost(function () {
          follow(id);
        }, true);
      });
  }

  function failed(message) {
    tell(message);
    stopMaking();
    go.disabled = false;
  }

  // targum out of reach: the connection's banner (`fault.js`; design.md §12,
  // 2026-10-09), whose Try again picks up where this stopped.
  function lost(again, following) {
    if (!window.TargumFault) return failed(S.t("reader.error.connect", "We can't reach targum."));
    tell("");
    // A job already found is still being made while the connection is away, so the
    // button stays aside and the banner's Try again goes on following it.
    if (!following) stopMaking();
    go.disabled = false;
    window.TargumFault.unreachable(again);
  }

  go.onclick = function () {
    busy = true;
    go.disabled = true;
    var minutes = Math.max(1, Math.round(Number(offer.getAttribute("data-seconds") || 0) / 60));
    tell(
      S.tn(
        "reader.voice.recording-now",
        minutes,
        "Thanks. We're making the audio for this section now. It will be about {n} minute long, and it plays here when it's ready.",
        "Thanks. We're making the audio for this section now. It will be about {n} minutes long, and it plays here when it's ready."
      )
    );
    showMaking(null);
    fetch(keyed("/voice"), {
      method: "POST",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name: name, section: Number(offer.getAttribute("data-section") || 1) }),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (state) {
        if (state.error) return failed(state.error);
        if (state.ready) {
          location.reload();
          return;
        }
        follow(state.id);
      })
      .catch(function () {
        lost(function () {
          go.click();
        });
      });
  };

  window.TargumVoice = { POLL: POLL };

  /* Already on its way (2026-10-10): a page left after the press and come back to asks
   * whether this section's audio is being made, and if it is, shows how far and follows
   * it to the end rather than offering the press again. Only a question: the server
   * joins a second press to the first anyway, so nothing is ever paid for twice. Signed
   * out or offline, nothing answers and the offer stands as it is. */
  function ask() {
    if (offer.hidden || navigator.onLine === false) return;
    var section = Number(offer.getAttribute("data-section") || 1);
    fetch(keyed("/voice?name=" + encodeURIComponent(name) + "&section=" + section), {
      headers: keyHeaders({}),
    })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (answer) {
        var job = answer && answer.job;
        if (!job || !job.id || busy) return;
        go.disabled = true;
        tell(
          S.t(
            "reader.voice.making",
            "We're making the audio for this section. It plays here when it's ready."
          )
        );
        showMaking(job);
        follow(job.id);
      })
      .catch(function () {});
  }
  (window.TargumSync && window.TargumSync.mayAsk ? window.TargumSync.mayAsk() : Promise.resolve(true)).then(function (may) {
    if (may) ask();
  });

  /* Sent here to hear this section (targum-internal#407): a link a chat handed over
   * ends `?hear=1`. The offer is opened and the button given focus, never pressed: the
   * press is still the reader's, with what it uses beside it. */
  var asked = "";
  try {
    asked = new URLSearchParams(location.search).get("hear") || "";
  } catch (e) {
    asked = "";
  }
  /* After the page is up: the ⋯ button is wired by the reader itself, which may wait
   * on the store, and a click before then opens nothing. */
  function bring(tries) {
    var more = document.querySelector("[data-more]");
    if (more && more.getAttribute("aria-expanded") !== "true") more.click();
    if (more && more.getAttribute("aria-expanded") !== "true" && tries > 0) {
      setTimeout(function () {
        bring(tries - 1);
      }, 100);
      return;
    }
    go.focus();
  }
  if (asked && !offer.hidden) {
    if (document.readyState === "complete") bring(20);
    else
      window.addEventListener("load", function () {
        bring(20);
      });
  }
})();

/* Into a playlist (targum-internal#364), from the ⋯ menu.
 *
 * Only where the page arrived over a connection: a playlist is kept on the account, and a
 * reader opened off a disk has none. The address names this reader's folder, read off
 * where the page is, because the built file does not know the name it is served under.
 */
(function () {
  "use strict";
  if (location.protocol === "file:") return;
  var group = document.getElementById("to-playlist");
  var link = document.getElementById("more-playlist");
  var served = /^\/reader\/([^/]+)\/reader\//.exec(location.pathname);
  if (!group || !link || !served) return;
  var name = decodeURIComponent(served[1]);
  var address = "/playlists?add=" + encodeURIComponent(name) +
    "&title=" + encodeURIComponent(link.getAttribute("data-title") || name);
  var key = new URLSearchParams(location.search).get("k");
  if (key) address += "&k=" + encodeURIComponent(key);
  link.href = address;
  // A menu in place (2026-09-24); the address above is where a middle-click still goes.
  if (window.TargumPlaylistMenu) {
    window.TargumPlaylistMenu.attach(
      link,
      { name: name, title: link.getAttribute("data-title") || name },
      key
    );
  }
  group.hidden = false;
  /* And "Play next" (targum-internal#434), where the reader is in a playlist and this
     text was not opened from it: it goes straight after the one they are on. */
  var lists = window.TargumPlaylistMenu;
  if (lists && lists.current && !new URLSearchParams(location.search).get("list")) {
    lists.current(key).then(function () {
      // In a playlist in this text's own language only (2026-10-12).
      var playing = lists.playing(document.documentElement.getAttribute("data-language"));
      if (!playing) return;
      group.appendChild(
        lists.nextButton(
          { name: name, title: link.getAttribute("data-title") || name },
          key,
          playing,
          "m-row more-playlist more-play-next"
        )
      );
    });
  }
})();

/* The week's sheet as a PDF (targum-internal#415), from the ⋯ menu, as the page is.
 *
 * Only on a portion's reader served from the corpus: its folder is the portion's name,
 * and the box sets the sheet for that name when the link is pressed. A haftarah's
 * folder is not a portion, and a reader opened off a disk has no box behind it.
 *
 * The link carries the view the reader is in when it is pressed, read off the page
 * rather than kept in step with it: which companions stand beside the verse, the vowels
 * and the te'amim, beside or under, whether words are marked, and this aliyah or the
 * whole portion with its haftarah. The box reads the same names (`parasha.sheet.
 * view_from`), and a name it does not know it passes over.
 */
(function () {
  "use strict";
  if (location.protocol === "file:") return;
  var group = document.getElementById("to-sheet");
  var whole = document.getElementById("more-sheet");
  var one = document.getElementById("more-sheet-aliyah");
  var served = /^\/parasha\/read\/([a-z0-9-]+)\/reader\/(?:sec-(\d+)\.html)?/.exec(location.pathname);
  if (!group || !whole || !served || served[1].indexOf("haftarah-") === 0) return;
  var base = "/parasha/" + served[1] + ".pdf";
  var body = document.body;

  function prefs() {
    try {
      return JSON.parse(localStorage.getItem("targum:prefs") || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  // The form of the text that is showing, from the reader's own state: the vowels and
  // the te'amim are classes on the body, and which cells a verse has is in its markup.
  // Not from a verse's cell on screen — on any page but the first the first verse is
  // hidden, and the sheet went out bare (QA 2026-10-05, B3).
  function vowelsOn() {
    return body.classList.contains("nikkud") && !!document.querySelector(".pair.points");
  }
  function taamimOn(kept) {
    if (!vowelsOn()) return false;
    // A text with no te'amim to take off is as published, which the box reads as on.
    if (!document.querySelector(".pair.accented")) return kept.taamim !== false;
    return body.classList.contains("taamim");
  }

  // The companions on, in the order they stand. Where the page has its own switches for
  // them (targum-internal#414) those say; otherwise the one translation showing.
  function companions() {
    if (body.classList.contains("mode-source")) return [];
    var keys = [];
    var language = "";
    var column = document.querySelector(".pair .tr[lang]");
    if (column) language = (column.getAttribute("lang") || "").split("-")[0].toLowerCase();
    var switches = document.querySelectorAll("#companions .companion[data-companion]");
    if (!switches.length) return language ? [language] : [];
    Array.prototype.forEach.call(switches, function (key) {
      var on = key.getAttribute("aria-pressed") === "true" || key.classList.contains("on");
      if (!on) return;
      var name = key.getAttribute("data-companion");
      keys.push(name === "translation" ? language : name);
    });
    return keys.filter(function (key) {
      return !!key;
    });
  }

  function view(aliyah) {
    var kept = prefs();
    var asked = [
      ["with", companions().join(",")],
      ["vowels", vowelsOn() ? "1" : "0"],
      ["taamim", taamimOn(kept) ? "1" : "0"],
      ["layout", body.classList.contains("mode-inter") ? "under" : "beside"],
      ["gloss", kept.marking === false ? "0" : "1"],
    ];
    if (aliyah) asked.push(["aliyah", aliyah]);
    return (
      base +
      "?" +
      asked
        .map(function (pair) {
          return pair[0] + "=" + encodeURIComponent(pair[1]);
        })
        .join("&")
    );
  }

  var aliyah = served[2] ? String(Number(served[2])) : "1";
  var said = document.getElementById("sheet-said");
  var t = window.TargumStrings ? window.TargumStrings.t : function (key, english) {
    return english;
  };
  var NOT_NOW = t("reader.page.pdf-not-now", "We can't make the PDF right now. Try again in a minute.");
  var OFFLINE = t("reader.page.pdf-offline", "You're offline. The PDF is made on targum, so it needs a connection.");

  function tell(text) {
    if (said) {
      said.textContent = text;
      said.hidden = !text;
    }
    var reader = window.TargumReader;
    if (text && reader && reader.say) reader.say(text);
  }

  // The sheet is set on the box when it is asked for, five or six seconds for a portion
  // (QA 2026-10-05, S5), and a link that downloads says nothing while it waits. So it is
  // fetched here, the press says "Preparing PDF…" until the file is in hand, and the
  // file is handed to the browser to save. A refusal is the box's own sentence.
  function fetchSheet(link) {
    var name = link.querySelector(".pick-name");
    var was = name ? name.textContent : "";
    link.classList.add("making");
    link.setAttribute("aria-busy", "true");
    if (name) name.textContent = t("reader.page.preparing-pdf", "Preparing PDF…");
    tell("");
    // Past three seconds the press says it is still at it (§14.1; targum-internal#409):
    // the sheet takes five or six on the box, and a press quiet for that long is pressed
    // again.
    var slow = setTimeout(function () {
      tell(t("reader.page.pdf-still", "Still making your PDF…"));
    }, 3000);
    function done() {
      clearTimeout(slow);
      link.classList.remove("making");
      link.removeAttribute("aria-busy");
      if (name) name.textContent = was;
    }
    // Offline, the sheet cannot be made, and saying "try again in a minute" was wrong.
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      done();
      return tell(OFFLINE);
    }
    fetch(link.href, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          return response.text().then(function (text) {
            var sentence = (text || "").trim();
            var plain = /^text\/plain/.test(response.headers.get("Content-Type") || "");
            throw { said: plain && sentence && sentence.length < 200 && response.status !== 404 ? sentence : NOT_NOW };
          });
        }
        var named = /filename="?([^";]+)"?/.exec(response.headers.get("Content-Disposition") || "");
        return response.blob().then(function (blob) {
          var file = URL.createObjectURL(blob);
          var save = document.createElement("a");
          save.href = file;
          save.download = named ? named[1] : served[1] + ".pdf";
          save.hidden = true;
          document.body.appendChild(save);
          save.click();
          save.remove();
          setTimeout(function () {
            URL.revokeObjectURL(file);
          }, 60000);
          done();
          // The file is here: "Still making your PDF…" goes with the wait (qa on #857).
          tell("");
        });
      })
      .catch(function (why) {
        done();
        var away = typeof navigator !== "undefined" && navigator.onLine === false;
        tell(why && why.said ? why.said : away ? OFFLINE : NOT_NOW);
      });
  }

  function press(link, which) {
    link.href = view(which);
    // Read again as it is pressed, so a switch turned after the page opened is on paper.
    link.addEventListener("click", function (event) {
      link.href = view(which);
      // A modified press — a new tab, a save-as — is the browser's to do.
      if (event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (!window.fetch || !window.URL || !URL.createObjectURL) return;
      event.preventDefault();
      if (link.classList.contains("making")) return;
      fetchSheet(link);
    });
  }
  press(whole, "");
  if (one) press(one, aliyah);
  group.hidden = false;
  // And the bar's print press, which has nothing to offer anywhere else (#421).
  var opener = document.getElementById("print-open");
  if (opener) opener.hidden = false;
})();

/* The columns switch themselves (targum-internal#421, B).
 *
 * Beside the verse, each companion's name carries a quiet × under the pointer, which
 * turns that column off; a column that is off leaves a faint "+ Rashi · English" at the
 * head of the first verse while any column stands, which turns it back on. Both press the Aa panel's own switch,
 * so there is one idea of what is on and it is kept where it always was. On a phone
 * there is no hover and no ×: Aa is the way in there, and the + stays.
 */
(function () {
  "use strict";
  var group = document.getElementById("companions");
  if (!group) return;
  var keys = Array.prototype.slice.call(group.querySelectorAll(".companion[data-companion]"));
  var columns = keys.filter(function (key) {
    return key.getAttribute("data-companion") !== "translation";
  });
  if (!columns.length) return;
  var first = null;
  var pairs = document.querySelectorAll(".pair");
  for (var i = 0; i < pairs.length && !first; i++) {
    if (pairs[i].querySelector(":scope > .beside")) first = pairs[i];
  }
  if (!first) return;
  var beside = first.querySelector(":scope > .beside");
  first.classList.add("beside-first");

  function nameOf(key) {
    var named = key.querySelector(".aa-name");
    return (named || key).textContent.trim();
  }

  function keyFor(name) {
    for (var n = 0; n < columns.length; n++) {
      if (columns[n].getAttribute("data-companion") === name) return columns[n];
    }
    return null;
  }

  // The × on every column's name. Drawn, not a control in the tab order: there is one
  // per verse per column, and the keyboard's way to the same switch is Aa.
  Array.prototype.forEach.call(document.querySelectorAll(".cmp .cmp-name"), function (label) {
    var x = document.createElement("span");
    x.className = "cmp-x";
    x.setAttribute("aria-hidden", "true");
    x.textContent = "\u00d7";
    label.appendChild(x);
  });

  // The + for each column that is off, at the head of the first verse.
  var add = document.createElement("span");
  add.className = "beside-add";
  beside.insertBefore(add, beside.firstChild);

  function paint() {
    add.textContent = "";
    columns.forEach(function (key) {
      if (key.getAttribute("aria-pressed") === "true") return;
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "cmp-add";
      chip.setAttribute("data-add", key.getAttribute("data-companion") || "");
      var shown = window.TargumStrings
        ? window.TargumStrings.t("reader.page.show-column", "Show {name}", { name: nameOf(key) })
        : "Show " + nameOf(key);
      chip.setAttribute("aria-label", shown);
      chip.title = shown;
      chip.textContent = "+ " + nameOf(key);
      add.appendChild(chip);
    });
    add.hidden = !add.childNodes.length;
  }

  document.addEventListener("click", function (event) {
    var at = event.target;
    if (!at || !at.closest) return;
    var x = at.closest(".cmp-x");
    if (x) {
      var cell = x.closest(".cmp");
      var key = cell && keyFor(cell.getAttribute("data-companion"));
      if (key && key.getAttribute("aria-pressed") === "true") key.click();
      event.stopPropagation();
      return;
    }
    var chip = at.closest(".cmp-add");
    if (chip) {
      var off = keyFor(chip.getAttribute("data-add"));
      if (off && off.getAttribute("aria-pressed") !== "true") off.click();
      event.stopPropagation();
    }
  }, true);

  new MutationObserver(paint).observe(group, {
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-pressed"],
  });
  paint();
})();

/* The bar steps back (targum-internal#421, C).
 *
 * While a reader reads on down the page, or listens, the bar fades to the mark, the
 * count and the player's pause with its thin line; the rest waits. It comes back for the
 * pointer near the top, a scroll up, a pause, Escape, or keyboard focus anywhere in the
 * bar, and it never steps back while one of its panels is out. Its ground stays paper
 * the whole time, so the text never shows through it, and its height never changes, so
 * nothing on the page moves. `prefers-reduced-motion` keeps the change and drops the fade.
 */
(function () {
  "use strict";
  var bar = document.querySelector(".bar");
  if (!bar) return;
  var body = document.body;
  var listen = document.getElementById("listen");
  var tools = bar.querySelector(".bar-tools");
  //: How near the top the pointer has to come, in pixels below the bar's foot.
  var NEAR = 56;
  //: How far a reader scrolls down, in one go, before the bar steps back.
  var DOWN = 48;
  //: How long the bar waits, once a recording is playing, before it steps back.
  var SETTLE = 2500;
  var lastY = window.scrollY;
  var travelled = 0;
  var waiting = 0;
  var pointerNear = false;
  var focusInside = false;
  // Whether the last pointer was a finger. A tap is a pointer event at the place it
  // landed, and on a phone the tap on Listen landed by the bar: the bar took it for a
  // pointer resting at the top and never stepped back, and `:hover` stays on whatever
  // was last touched (QA 2026-10-05, S3). A finger at the top has its own rule below.
  var coarse = window.matchMedia ? window.matchMedia("(hover: none), (pointer: coarse)") : null;
  var touching = !!(coarse && coarse.matches);
  document.addEventListener(
    "pointerdown",
    function (event) {
      touching = event.pointerType === "touch";
      if (touching && pointerNear) pointerNear = false;
    },
    { passive: true, capture: true }
  );

  function playing() {
    return !!(listen && listen.classList.contains("playing"));
  }

  // Anything that holds the bar out: a panel, the keys card, focus inside it, the
  // pointer at the top, or the reader at the top of the page.
  function held() {
    if (body.classList.contains("pop-open")) return true;
    var keys = document.getElementById("keys");
    if (keys && !keys.hidden) return true;
    if (pointerNear) return true;
    if (focusInside && keyboardFocus(document.activeElement)) return true;
    if (!touching && bar.matches(":hover")) return true;
    return false;
  }

  function quiet(on) {
    if (on && held()) on = false;
    if (on === bar.classList.contains("quiet")) return;
    if (on && tools) {
      // How far the player rides to the edge into the room the tools leave.
      var gap = parseFloat(getComputedStyle(tools.parentNode).columnGap) || 0;
      bar.style.setProperty("--tools", Math.round(tools.getBoundingClientRect().width + gap) + "px");
    }
    bar.classList.toggle("quiet", !!on);
  }

  function back() {
    clearTimeout(waiting);
    waiting = 0;
    travelled = 0;
    quiet(false);
  }

  function settleSoon() {
    clearTimeout(waiting);
    waiting = setTimeout(function () {
      waiting = 0;
      if (playing()) quiet(true);
    }, SETTLE);
  }

  window.addEventListener(
    "scroll",
    function () {
      var y = window.scrollY;
      var moved = y - lastY;
      lastY = y;
      if (y <= bar.offsetHeight) {
        back();
        return;
      }
      if (moved < -6) {
        back();
        if (playing()) settleSoon();
        return;
      }
      if (moved > 0) {
        travelled += moved;
        if (travelled > DOWN) quiet(true);
      }
    },
    { passive: true }
  );

  document.addEventListener(
    "pointermove",
    function (event) {
      if (event.pointerType === "touch") return;
      touching = false;
      var near = event.clientY <= bar.getBoundingClientRect().bottom + NEAR;
      if (near === pointerNear) return;
      pointerNear = near;
      if (near) back();
      else if (playing()) settleSoon();
    },
    { passive: true }
  );
  // A finger at the top of a phone, where nothing hovers.
  document.addEventListener(
    "touchstart",
    function (event) {
      var touch = event.touches && event.touches[0];
      if (!touch || touch.clientY > bar.getBoundingClientRect().bottom + NEAR) return;
      back();
      // A finger lifts, where a pointer stays: with the voice going the bar steps back
      // again after the same moment it waits after Listen.
      if (playing()) settleSoon();
    },
    { passive: true }
  );

  // Keyboard focus, not the focus a pointer leaves on what it pressed: pressing play
  // with the mouse leaves the button focused, and that is not a reader in the bar.
  function keyboardFocus(element) {
    try {
      return !!element && element.matches(":focus-visible");
    } catch (e) {
      return true;
    }
  }
  bar.addEventListener("focusin", function (event) {
    focusInside = keyboardFocus(event.target);
    if (focusInside) back();
  });
  bar.addEventListener("focusout", function (event) {
    if (event.relatedTarget && bar.contains(event.relatedTarget)) return;
    focusInside = false;
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") back();
  });
  document.addEventListener("targum:pop", function (event) {
    if (event.detail) back();
  });

  // Play steps it back after a moment; pause brings it straight back.
  if (listen && window.MutationObserver) {
    var was = playing();
    new MutationObserver(function () {
      var now = playing();
      if (now === was) return;
      was = now;
      if (now) settleSoon();
      else back();
    }).observe(listen, { attributes: true, attributeFilter: ["class"] });
  }
})();
