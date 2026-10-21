/* The reader's closures that wait for nothing it does first: hearing a silent text,
 * the ⋯ menu's playlist and sheet, the columns that switch themselves and the bar that
 * steps back. They stood at the foot of `reader.js` and ran right after it, and still
 * do, from the script after it — split off so that a word answers a tap as soon as
 * `reader.js` has arrived, rather than when these have too (reader QA,
 * targum-internal#464, 2026-10-20).
 */

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
