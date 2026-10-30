/* The player: a recording or a film beside the text, and the transcript that follows
 * it. Only a reader whose text has a recording carries this file (reader QA,
 * targum-internal#464, 2026-10-19): everything here waited for `speech.audio` and
 * returned at once without it, and every other reader paid for it anyway, about a
 * fifth of the reader's script. It only defines `targumPlayer`; `targumReader` runs
 * it where this closure used to stand, so the order everything starts in is the order
 * it always was. It comes after `reader.js` since 2026-10-21 (targum-internal#409) and
 * runs itself on arrival when the reader got there first (the foot of this file).
 */

/* Playing a dialogue: one line, or the whole scene with the text following along.
 *
 * The scene is one audio file and each turn is a span of it, so a line is played by
 * seeking and then stopping at its end — never by loading a clip per line, because a
 * reader is one file and fifty small files is not a shape it has.
 *
 * A single line stops on a timer rather than a `timeupdate` handler: that event fires
 * about four times a second, which overshoots the end of a short turn by a syllable and
 * reads as the next speaker starting. A timer set from the span's own length lands where
 * the seam is. Following the whole scene is the opposite case — nothing is being stopped,
 * only marked — so there the coarse event is exactly right and costs nothing.
 */
var targumPlayer = function () {
(function () {
  "use strict";
  var node = document.getElementById("targum-data");
  if (!node) return;
  var speech;
  var spokenOf = "";
  var spokenPart = "1";
  try {
    var loaded = JSON.parse(node.textContent) || {};
    speech = loaded.speech;
    spokenOf = loaded.document || location.pathname;
    spokenPart = String(loaded.section || 1);
  } catch (e) {
    return;
  }
  if (!speech || !speech.audio) return;
  // The player's words in the reader's language, from the first closure's catalogue.
  var t = window.TargumStrings ? window.TargumStrings.t : function (key, english) {
    return english;
  };
  // Said for the first-run line, which is another closure's: there is something to play.
  document.body.classList.add("has-voice");

  /* Where the sound is. Inlined, it is the data URI itself; a portion's readings are
     files beside the page (targum-internal#412), asked for with the page's own query so
     a served reader's key travels with them, the way the video sidecar's does. */
  function addressOf(src) {
    return /^data:/.test(src) ? src : src + (location.search || "");
  }

  /* One media element, not two clocks. Where the import kept its pictures the page
     carries a <video> pointed at the sidecar beside this file, and that element is the
     player's whole instrument — same HTMLMediaElement, so every span, timer and rate
     below works on it unchanged. Showing and hiding the panel never touches playback:
     a hidden video keeps sounding, which is exactly the audio reader. The inlined
     audio stays in the page for the download button, and as the instrument the player
     falls back to if the sidecar did not travel with the file. */
  var videoBox = document.getElementById("video");
  var videoEl = videoBox ? videoBox.querySelector(".video-el") : null;
  if (videoEl) {
    /* The page's own address carries the serve key in its query, and the sidecar
       request must carry the same or be turned away as a stranger. Off a disk the
       search is empty and the relative address stands alone. */
    videoEl.src = videoEl.getAttribute("data-src") + (location.search || "");

    /* The film's own shape, taken from the film (design.md §12, 2026-09-17).
     *
     * The stylesheet wrote 16/9 into the docked panel and into the portrait frame, so
     * anything shot upright — a Short, a reel, a phone held the ordinary way — sat in a
     * letterbox with two thirds of the frame black. Nothing is fetched to learn better:
     * the element knows its own dimensions once the metadata lands, and the frame takes
     * them.
     *
     * Written on the panel rather than on the element, so the one custom property serves
     * the picture, the tap target over it and the full-screen frame at once, and so the
     * stylesheet keeps the 16/9 it had as the value before the metadata arrives. `tall`
     * is the switch the layout needs: a picture taller than it is wide is sized by its
     * height, or a 9:16 at the panel's width would be a column of video down the window.
     */
    /* And before it lands, the shape the build measured (2026-09-20). Until the metadata
     * arrived a reel stood in the 16/9 the stylesheet falls back to and then jumped
     * upright — on a slow line, for as long as the line was slow. The build reads the
     * cut's size and the page carries it as `data-film`; `tall` is already in the class
     * the page came with. As an attribute and not a style: a served page's policy allows
     * no inline style, and a property set from here is not one. The film still has the
     * last word below, in the same form, so a page that was told wrong is put right. */
    var builtFilm = videoBox ? videoBox.getAttribute("data-film") : "";
    if (builtFilm && /^\d+ \/ \d+$/.test(builtFilm)) videoBox.style.setProperty("--film", builtFilm);
    videoEl.addEventListener("loadedmetadata", function () {
      var wide = videoEl.videoWidth;
      var high = videoEl.videoHeight;
      if (!wide || !high || !videoBox) return;
      videoBox.style.setProperty("--film", wide + " / " + high);
      videoBox.classList.toggle("tall", high > wide);
      var reader = window.TargumReader;
      if (reader && reader.relayout) reader.relayout();
    });
  }
  var videoDead = false;
  var audio = videoEl || new Audio(addressOf(speech.audio));
  var spans = speech.spans || {};
  /* Each written word's clock, where the build could pair one: rows of
     [charStart, charEnd, start, end] per segment, in the bare text's own offsets. */
  var wordClocks = speech.words || {};
  /* In reading order, because the object came from the page in that order and following
     along means walking it. */
  function ordered(table) {
    return Object.keys(table).map(function (id) {
      return { id: id, start: table[id][0], end: table[id][1] };
    });
  }
  var order = ordered(spans);
  // No spans is a shape, not a failure: prose is recorded as one reading and played
  // straight through. Everything below works without them — what goes is the highlight
  // that would otherwise crawl down a sentence at a time, which is a thing to do to a
  // dialogue and not to an article.

  /* However many controls ask for it — the bar's button and the player's — there is one
     scene and one state, so they are held together rather than each keeping its own. */
  var scenes = Array.prototype.slice.call(document.querySelectorAll("[data-play-scene]"));
  var player = document.getElementById("player");
  var fill = player && player.querySelector(".player-fill");
  var clock = player && player.querySelector(".player-clock");
  var said = player && player.querySelector(".player-said");
  // The bar's copy of the player (targum-internal#421): play, a thin line and the clock.
  // It shows what the strip shows and keeps no state of its own.
  var listenBox = document.getElementById("listen");
  var barFill = listenBox && listenBox.querySelector(".listen-fill");
  var barClock = listenBox && listenBox.querySelector(".listen-clock");
  var scene = scenes[0] || null;
  var stopAt = null;
  var playing = null;      /* the one-line button, when a single line is playing */
  var playingEnd = 0;      /* where that line ends, for re-arming its timer at a new speed */
  // The strip's, and ⋯'s copy for while the picture is up and the strip is not (#422):
  // two presses, one switch.
  var hearFirsts = Array.prototype.slice.call(document.querySelectorAll(".player-first, .more-first"));
  var hearFirst = hearFirsts[0] || null;
  var hearing = null;      /* the pair whose text is hidden while its line plays */
  var following = false;   /* whether the whole scene is running */
  var marked = null;
  // How the transcript follows the voice while the picture is up (#422); set further down.
  var filmFollow = null;

  /* The same question the rest of the page asks, asked the same way. Read at the moment
     of scrolling rather than once at load, because a reader can change the setting while
     a scene is playing and the page should already be honouring it. */
  var quiet = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  function behaviour() {
    return quiet && quiet.matches ? "auto" : "smooth";
  }

  function mark(id) {
    if (marked && marked.getAttribute("data-id") === id) return;
    if (marked) marked.classList.remove("now");
    marked = id ? document.querySelector('.pair.voiced[data-id="' + CSS.escape(id) + '"]') : null;
    if (!marked) return;
    marked.classList.add("now");
    if (filmFollow && filmFollow(marked)) return;
    /* On pages, the verse's page first: the voice goes on past the foot of the page,
       and a verse on a page nobody can see is not followed (QA 2026-10-05, B1). */
    var reader = window.TargumReader;
    if (reader && reader.turnToPair) reader.turnToPair(marked);
    /* Only when it has gone off the page. Scrolling a line that is already in front of
       the reader moves the text under their eyes for no reason. */
    var box = marked.getBoundingClientRect();
    /* The scrolling reader reserves nothing — text passes under a fixed control there by
       definition — so the floor is the player's own top edge while it is out. The line
       being spoken is the one line that must not be behind it. */
    var floor = window.innerHeight - 24;
    if (player && !player.hidden) {
      var seat = player.getBoundingClientRect();
      if (seat.height) floor = Math.min(floor, seat.top - 12);
    }
    /* On a narrow window the player is a strip standing on whatever holds the band —
       the sheet, a card — and the reader's own stylesheet knows how tall the lot is. */
    var band = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--foot"));
    if (band > 0) floor = Math.min(floor, window.innerHeight - band - 12);
    var topBar = document.querySelector(".bar");
    var ceiling = Math.max(64, topBar ? topBar.getBoundingClientRect().bottom + 8 : 0);
    /* The verse's own line is what is being chanted, and it is what has to be in view:
       a verse with Rashi beside it is taller than the window, and centring the whole
       block put the Hebrew off the top of the screen and left the listener looking at
       the commentary (QA 2026-10-05, B1). */
    var line = sayingLine(marked) || marked;
    var said = line.getBoundingClientRect();
    var fits = box.height <= floor - ceiling;
    var seen = said.top >= ceiling && said.bottom <= floor;
    if (seen && (!fits || (box.top >= ceiling && box.bottom <= floor))) return;
    /* To the top third of what can be read, with as much of the verse under it as fits;
       a verse that fits whole is brought on whole. */
    var by = said.top - (ceiling + (floor - ceiling) / 4);
    if (fits) {
      by = Math.max(by, box.bottom - floor);
      by = Math.min(by, box.top - ceiling);
    }
    if (Math.abs(by) < 1) return;
    window.scrollBy({ top: by, behavior: behaviour() });
  }

  /* The cell of the verse the voice is saying: the Hebrew as it is showing. */
  function sayingLine(pair) {
    var cells = pair.querySelectorAll(".src");
    for (var i = 0; i < cells.length; i++) {
      if (cells[i].getClientRects().length) return cells[i];
    }
    return null;
  }

  /* Time listened and time watched (targum-internal#339), off the element's own events so a
     line pressed and a whole scene run are counted alike. Wall-clock seconds, because that
     is what a person spent; told apart by whether the picture was up, because a film played
     with its picture put away was listened to. Under a second is a mis-press.
     The picture is read when a stretch starts, and putting it up or away while the sound
     goes ends one stretch and starts the next (targum-internal#602): read only at the end,
     a film watched for forty minutes and put away for the last one was all "listened".
     And whether the text was on the screen (targum-internal#602, privacy notice clause
     3.6 as amended 2026-10-30): not with the page hidden (a locked phone, another app),
     not with the listening view open, and not while Hear first holds the line's text
     back. The line the research draws is there, not at the picture; a later figure says
     how much of the time was without the text. Any of the three changing while the sound
     goes ends one stretch and starts the next, as the picture does. */
  var begun = 0;
  var begunWatching = false;
  var begunText = true;
  function pictureUp() {
    var panel = document.getElementById("video");
    return !!(panel && !panel.hidden);
  }
  function textShown() {
    if (document.hidden) return false;
    if (document.body && document.body.classList.contains("listening")) return false;
    return !hearing;
  }
  function stretchBegins() {
    begun = Date.now();
    begunWatching = pictureUp();
    begunText = textShown();
  }
  function stretchOver() {
    if (!begun) return;
    var seconds = Math.round((Date.now() - begun) / 1000);
    begun = 0;
    if (seconds < 1 || !window.TargumEvents) return;
    var saying = document.querySelector(".pair.voiced.now");
    window.TargumEvents.note({
      kind: "play",
      amount: seconds,
      medium: begunWatching ? "watch" : "listen",
      segment: saying ? saying.getAttribute("data-id") || "" : "",
      text: begunText,
    });
  }
  /* Something the stretch is told apart by has moved: close it and, if the sound is
     still going, open the next. */
  function restand() {
    if (!begun) return;
    if (pictureUp() === begunWatching && textShown() === begunText) return;
    stretchOver();
    if (!audio.paused) stretchBegins();
  }
  audio.addEventListener("playing", function () {
    if (!begun) stretchBegins();
  });
  if (typeof MutationObserver === "function") {
    var restanding = new MutationObserver(restand);
    if (videoBox) restanding.observe(videoBox, { attributes: true, attributeFilter: ["hidden"] });
    // The listening view says itself on the body (`listen.js`).
    if (document.body) {
      restanding.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    }
  }
  document.addEventListener("visibilitychange", restand);
  audio.addEventListener("pause", stretchOver);
  audio.addEventListener("ended", stretchOver);
  window.addEventListener("pagehide", stretchOver);
  //: Lines asked for in this visit: a second press on one is a replay, which is the
  //: clearest thing a listener can say about a line.
  var askedFor = {};

  function pressed(on) {
    scenes.forEach(function (button) {
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (player) player.classList.toggle("playing", !!on);
    // The page, too: while a voice is going, the band on a line is where the voice is,
    // and a line the pointer is only passing over must not wear it (#420).
    document.body.classList.toggle("voicing", !!on);
    if (listenBox) {
      listenBox.classList.toggle("playing", !!on);
      if (on) listenBox.classList.add("placed");
    }
    // The first-run line is another closure's; it hears that a recording has started.
    if (on && typeof CustomEvent === "function") {
      document.dispatchEvent(new CustomEvent("targum:playing"));
    }
  }

  function clocked(seconds) {
    var whole = Math.max(0, Math.floor(seconds));
    return Math.floor(whole / 60) + ":" + ("0" + (whole % 60)).slice(-2);
  }

  function halt() {
    if (stopAt) { clearTimeout(stopAt); stopAt = null; }
    audio.pause();
    unlight();
    /* Hear first: the line is over, however it ended, so its text comes back. */
    if (hearing) { hearing.classList.remove("hearing"); hearing = null; restand(); }
    if (playing) { playing.classList.remove("saying"); playing = null; }
    if (following) {
      following = false;
      pressed(false);
    }
    if (marked) { marked.classList.remove("now"); marked = null; }
    pressed(false);
  }

  /* `quietly` is for a start nobody pressed for on this page — arriving with `?listen=1`
     (design.md §12, "Listening is a view of its own", 2026-10-10). A browser that has not
     yet seen a press on the page refuses it (NotAllowedError), and that is not a muted
     tab: the play button simply waits for the press, with nothing said. */
  function play(from, quietly) {
    try {
      audio.currentTime = from;
    } catch (why) {
      return refused(
        t(
          "reader.player.cannot-seek",
          "We can't play this recording in this browser. Try another browser."
        ),
        why
      );
    }
    /* Drawn before the first `timeupdate` rather than by it. The clock is empty until
       that tick, and the strip is anchored to the foot of the window — so when its text
       arrived the strip grew a line and the whole thing jumped ten pixels upward under
       whatever the reader had just pressed. Painting here makes it its final size in the
       frame the play button changes, which is also what stops a test measuring the bar
       and then pressing where it used to be. */
    paint();
    var done = audio.play();
    if (done && done.catch) {
      done.catch(function (why) {
        if (quietly === true && why && why.name === "NotAllowedError") {
          halt();
          return;
        }
        // Interrupted, not refused: a pause, or the film loaded again after an error
        // ("A film that errors after a picture is loaded again"), cuts the promise off
        // while what follows plays on. Said as a failure, "We couldn't play this
        // recording" stood under a film that was playing (reader QA, 2026-10-19).
        if (why && why.name === "AbortError") return;
        // Chrome rejects here when the tab is not allowed to make a sound — a site muted
        // in the address bar, or a policy about autoplay — and the promise is the only
        // place it says so. Silently stopping made that indistinguishable from a broken
        // file: the control flipped back and the page had nothing to say for itself.
        refused(
          why && why.name === "NotAllowedError"
            ? t(
                "reader.player.sound-blocked",
                "This tab is muted. Allow sound for targum in the address bar."
              )
            : t("reader.player.could-not-play", "We couldn't play this recording."),
          why,
          why && why.name === "NotAllowedError" ? null : from
        );
      });
    }
  }

  /* Playback failed, and the reader is told which. A control that reverts and explains
     nothing is the worst of both: it looks broken and gives nobody anything to act on. */
  function refused(message, why, again) {
    halt();
    if (player) {
      player.classList.add("refused");
      if (said) {
        said.textContent = message;
        // The clay mark before it, the sentence in ink (design.md §12, 2026-10-09).
        said.classList.add("fault-marked");
      }
      var retry = player.querySelector(".player-again");
      if (retry) retry.parentNode.removeChild(retry);
      // Try again, beside a recording that would not play, plays it again from where
      // it was asked to start.
      if (said && typeof again === "number") {
        retry = document.createElement("button");
        retry.type = "button";
        retry.className = "fault-act player-again";
        retry.textContent = t("fault.try-again", "Try again");
        retry.addEventListener("click", function (event) {
          event.stopPropagation();
          player.classList.remove("refused");
          said.classList.remove("fault-marked");
          if (retry.parentNode) retry.parentNode.removeChild(retry);
          play(again);
        });
        said.parentNode.insertBefore(retry, said.nextSibling);
      }
    }
    // The label is written where sighted eyes are; the live region is where everyone
    // else's are. A play button that reverts silently looks broken and says nothing.
    var reader = window.TargumReader;
    if (reader && reader.say) reader.say(message);
    try {
      var trouble = audio.error ? " (media error " + audio.error.code + ")" : "";
      console.error("targum: " + message + trouble, why || "");
    } catch (e) {}
  }

  /* How fast. Steps either side of the recording's own pace, and a pair of buttons rather
     than one that cycles: a cycle from 2× comes round to 0.5×, which is the one step
     nobody pressing "faster" means.

     Held per browser rather than per text — the opposite of the closed player below,
     and for the opposite reason. Which texts you would rather read in silence is a fact
     about each text; how fast you can follow a voice is a fact about you, like the type
     size, and a reader who wanted the last scene slower wants this one slower too.

     The pitch is kept. A slowed voice should drop in speed and not turn into somebody
     else; browsers default to keeping it, but the default is not what the file relies
     on. */
  var RATES = [0.5, 0.75, 1, 1.25, 1.5, 2];
  var RATE_STORE = "targum:player-rate";
  var slower = player && player.querySelector(".player-slower");
  var faster = player && player.querySelector(".player-faster");
  var rateNow = player && player.querySelector(".player-rate-now");
  // And the video's "1× ▾" with its six picks (#422), and the bar's own since 2026-10-08,
  // which all say the same figure.
  var filmRateNows = Array.prototype.slice.call(document.querySelectorAll(".film-rate-now"));
  var ratePicks = Array.prototype.slice.call(document.querySelectorAll(".film-rate-pick"));

  /* Whatever was stored, the nearest step — a number from a version of this table that
     no longer exists is snapped rather than obeyed, and anything else is the pace it was
     read at. */
  function nearestRate(value) {
    var n = parseFloat(value);
    if (isNaN(n)) return 1;
    var best = 1;
    RATES.forEach(function (rate) {
      if (Math.abs(rate - n) < Math.abs(best - n)) best = rate;
    });
    return best;
  }

  function setRate(value, chosen) {
    var rate = nearestRate(value);
    audio.playbackRate = rate;
    try {
      audio.preservesPitch = true;
      audio.webkitPreservesPitch = true;   // Safari answered to this one for years
    } catch (e) {}
    var i = RATES.indexOf(rate);
    if (rateNow) rateNow.textContent = rate + "×";
    filmRateNows.forEach(function (now) {
      now.textContent = rate + "×";
    });
    ratePicks.forEach(function (pick) {
      pick.setAttribute("aria-pressed", parseFloat(pick.getAttribute("data-rate")) === rate ? "true" : "false");
    });
    // aria-disabled rather than disabled: a disabled button drops the keyboard focus that
    // was on it, and the reader who just pressed it is still standing there.
    if (slower) slower.setAttribute("aria-disabled", i === 0 ? "true" : "false");
    if (faster) faster.setAttribute("aria-disabled", i === RATES.length - 1 ? "true" : "false");
    /* A single line stops on a timer set from its length at the old speed. Re-armed from
       what is left of it at the new one, or the line runs into the next speaker. */
    if (playing && stopAt) {
      clearTimeout(stopAt);
      stopAt = setTimeout(halt, Math.max(0, ((playingEnd - audio.currentTime) * 1000) / rate));
    }
    if (chosen) {
      try {
        targumKeep(RATE_STORE, String(rate));
      } catch (e) {}
      var reader = window.TargumReader;
      if (reader && reader.say) reader.say(rate + "×");
    }
  }

  function stepRate(by) {
    var i = RATES.indexOf(nearestRate(audio.playbackRate)) + by;
    if (i < 0 || i >= RATES.length) return;
    setRate(RATES[i], true);
  }

  var keptRate = 1;
  try {
    keptRate = localStorage.getItem(RATE_STORE) || 1;
  } catch (e) {}
  setRate(keptRate, false);
  // The speed's six picks, from "1× ▾" in the bar or under the picture. The panel shuts
  // itself and hands focus back.
  ratePicks.forEach(function (pick) {
    pick.addEventListener("click", function () {
      setRate(pick.getAttribute("data-rate"), true);
      var shut = document.querySelector('[data-pop-close="rates"]');
      if (shut) shut.click();
    });
  });
  if (slower) slower.addEventListener("click", function () { stepRate(-1); });
  if (faster) faster.addEventListener("click", function () { stepRate(1); });
  /* The figure itself steps on, and round: on a phone it is the only speed control there
     is room for, and one button that cycles is a control, where two arrows for a scale
     of six were a column. */
  if (rateNow) {
    rateNow.addEventListener("click", function () {
      var i = RATES.indexOf(nearestRate(audio.playbackRate));
      setRate(RATES[(i + 1) % RATES.length], true);
    });
  }

  /* Where in it. The bar was a readout for as long as the only way into the middle of a
     recording was to press the line said there — which works on a dialogue, where every
     line has a button, and not at all on an hour of prose read straight through.
     Dragging it is the one gesture every player on earth has already taught. */
  // The strip's, and the one under the picture (#422): the same slider twice.
  var trackEls = Array.prototype.slice.call(document.querySelectorAll(".player-track, .film-track"));
  // Said to by the picture's own code further down, once it has been set up.
  var filmPaint = null;

  // The bar's pill says the length before anything has played (2026-10-09).
  audio.addEventListener("loadedmetadata", function () {
    paint();
  });

  function span() {
    var length = audio.duration;
    return length && isFinite(length) ? length : 0;
  }

  /* The fill, the clock and what the slider tells a screen reader all read off the same
     two numbers, and all three are wanted when the reader drags the bar with nothing
     playing — which `timeupdate` never says. */
  /* Where it is, and of how long, as two pieces: on a phone the strip has room for the
     first only, and the whole clock ran under the play button beside it (reader QA,
     2026-10-19). The track beside it already says how far along. */
  function drawClock(now, whole) {
    var at = clock.querySelector(".clock-now");
    var of = clock.querySelector(".clock-whole");
    if (!at || !of) {
      clock.textContent = "";
      at = document.createElement("span");
      at.className = "clock-now";
      of = document.createElement("span");
      of.className = "clock-whole";
      clock.appendChild(at);
      clock.appendChild(of);
    }
    at.textContent = now;
    of.textContent = " / " + whole;
  }

  function paint() {
    var length = span();
    if (!length) return;
    var now = audio.currentTime;
    if (fill) fill.style.inlineSize = (now / length) * 100 + "%";
    if (clock) drawClock(clocked(now), clocked(length));
    // The bar's player (#421): the same line, thinner, and only where the voice is.
    if (barFill) barFill.style.inlineSize = (now / length) * 100 + "%";
    // At the start the pill says how long it is, and from the first second where it is
    // (board ReaderBeside: "▶ 14:01" before, "Ⅱ 0:31" playing).
    if (barClock) barClock.textContent = clocked(now > 0 ? now : length);
    trackEls.forEach(function (trackEl) {
      trackEl.setAttribute("aria-valuemax", String(Math.floor(length)));
      trackEl.setAttribute("aria-valuenow", String(Math.floor(now)));
      // The clock and not the percentage: "four ten of nine twenty" is where you are,
      // and "forty-six percent" is arithmetic about where you are.
      trackEl.setAttribute("aria-valuetext", clocked(now) + " of " + clocked(length));
    });
    if (filmPaint) filmPaint(now, length);
    caption(lineAt(now));
  }

  /* The last line the voice has begun, held through the silence after it, or the first
     before anything has been said. `lineAt` below is what asks it. */
  function heldAt(seconds) {
    var held = order.length ? order[0].id : null;
    for (var i = 0; i < order.length; i++) {
      if (seconds >= order[i].start) held = order[i].id;
      else break;
    }
    return held;
  }

  /* What the word clocks can say (2026-10-29). A recording aligned word by word gives
     each word a clock of its own. A transcript taken from a subtitle file gives every
     word of a cue the cue's clock (`ingest.subtitles.refined_from`), and a cue runs
     across sentences, so neighbouring lines' spans overlap: 39 of 48 in the first part of
     the Touring Israel interview. Read as word clocks, those lit a cue's first word for
     the whole cue; read as spans, two rules for the line being said disagreed inside the
     overlap and the transcript was scrolled back and forth four times a second.

     Read once here: `own`, the clocks that are one word's own, which are the only ones
     that light a word (design.md §12: the chip is "where the recording was aligned word
     by word"); and `said`, where each line is being said — a clock shared by several
     words split between them by their letters, which says when the voice crosses from
     one line to the next without claiming to know when any one word was said. */
  var heardTable = null;
  function heard() {
    if (heardTable) return heardTable;
    var rows = [];
    Object.keys(wordClocks).forEach(function (id) {
      (wordClocks[id] || []).forEach(function (row) {
        rows.push({ id: id, row: row });
      });
    });
    var own = {};
    var said = [];
    var i = 0;
    while (i < rows.length) {
      var start = rows[i].row[2];
      var end = rows[i].row[3];
      var j = i + 1;
      while (j < rows.length && rows[j].row[2] === start && rows[j].row[3] === end) j++;
      if (j - i === 1) {
        (own[rows[i].id] = own[rows[i].id] || []).push(rows[i].row);
        said.push({ id: rows[i].id, start: start, end: end });
      } else {
        var letters = 0;
        for (var k = i; k < j; k++) letters += Math.max(1, rows[k].row[1] - rows[k].row[0]);
        var from = start;
        var last = null;
        for (k = i; k < j; k++) {
          var to = from + ((end - start) * Math.max(1, rows[k].row[1] - rows[k].row[0])) / letters;
          if (last && last.id === rows[k].id) last.end = to;
          else said.push((last = { id: rows[k].id, start: from, end: to }));
          from = to;
        }
        last.end = end;
      }
      i = j;
    }
    heardTable = { own: own, said: said };
    return heardTable;
  }

  /* The line being said, and the one answer to it: the transcript's lit line, the line
     under the picture, the band on the hairline, Loop and the word lit all ask here.
     Where the word clocks place the voice, the line they place it in; otherwise the last
     line begun. The line under the picture (targum-internal#422) is a line of the
     transcript set large, not a caption over a film, so it stays put while nothing is
     said rather than blinking out between sentences. */
  function lineAt(seconds) {
    var said = heard().said;
    for (var i = 0; i < said.length; i++) {
      if (seconds >= said[i].start && seconds < said[i].end) return said[i].id;
    }
    return heldAt(seconds);
  }

  /* The form of a line the reader has on show — pointed, plain or unaccented — because a
     line in a form they turned off is the page arguing with them. */
  function shownForm(pair) {
    var forms = pair.querySelectorAll(".src");
    for (var i = 0; i < forms.length; i++) {
      // The pair itself may be a page away and hidden; its children's own display is
      // not, which is what is being asked about here.
      if (getComputedStyle(forms[i]).display !== "none") return forms[i];
    }
    return forms[0] || null;
  }

  // Drawn by the picture's own code, further down, where there is a picture.
  var filmCaption = null;
  function caption(id) {
    if (filmCaption) filmCaption(id);
  }

  /* Moving the voice. A single line that was running stops being a single line — the
     timer that would have halted it belongs to a span the reader has just left — and
     becomes the whole text running, which is what dragging the bar means everywhere
     else. */
  function seek(to) {
    var length = span();
    if (!length) return;
    var seconds = Math.min(length, Math.max(0, to));
    if (playing) {
      if (stopAt) { clearTimeout(stopAt); stopAt = null; }
      playing.classList.remove("saying");
      playing = null;
      if (!audio.paused) { following = true; pressed(true); }
    }
    try {
      audio.currentTime = seconds;
    } catch (e) {
      return;
    }
    if (player) player.classList.add("placed");
    if (listenBox) listenBox.classList.add("placed");
    if (following) mark(at(seconds));
    paint();
    keepHeard();
  }

  trackEls.forEach(function (trackEl) {
    var dragging = false;
    var along = function (event) {
      var box = trackEl.getBoundingClientRect();
      if (!box.width) return 0;
      var part = (event.clientX - box.left) / box.width;
      // The bar fills the way the page runs, so on a Hebrew page it starts at its right
      // edge. Read off the computed direction rather than assumed: the same drag has to
      // land on the same second in both.
      if (getComputedStyle(trackEl).direction === "rtl") part = 1 - part;
      return Math.min(1, Math.max(0, part));
    };

    trackEl.addEventListener("pointerdown", function (event) {
      if (!span()) return;
      dragging = true;
      if (trackEl.setPointerCapture) {
        try { trackEl.setPointerCapture(event.pointerId); } catch (e) {}
      }
      event.preventDefault();
      seek(along(event) * span());
    });
    trackEl.addEventListener("pointermove", function (event) {
      if (!dragging) return;
      event.preventDefault();
      seek(along(event) * span());
    });
    ["pointerup", "pointercancel"].forEach(function (name) {
      trackEl.addEventListener(name, function () { dragging = false; });
    });

    /* The keyboard's own way along, stopped here rather than let up to the page: the
       arrows walk the text a word at a time, and a reader whose focus is on the bar
       means the bar. Five seconds is the step every transport uses; the word-sized one
       is on the buttons below, where the label can say so. */
    trackEl.addEventListener("keydown", function (event) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      var length = span();
      if (!length) return;
      var back = getComputedStyle(trackEl).direction === "rtl" ? "ArrowRight" : "ArrowLeft";
      var to = null;
      if (event.key === back) to = audio.currentTime - 5;
      else if (event.key === (back === "ArrowLeft" ? "ArrowRight" : "ArrowLeft")) {
        to = audio.currentTime + 5;
      } else if (event.key === "Home") to = 0;
      else if (event.key === "End") to = length;
      if (to === null) return;
      event.preventDefault();
      event.stopPropagation();
      seek(to);
    });
  });

  /* A step either side. One word where the recording was aligned word by word, five
     seconds where it was not — and the label says which, because a control whose size
     changes silently is a control that lies. */
  // The strip's, and ⋯'s for while the picture is up (#422).
  var stepBacks = Array.prototype.slice.call(document.querySelectorAll(".player-back, .more-back"));
  var stepOns = Array.prototype.slice.call(document.querySelectorAll(".player-on, .more-on"));
  var wordStarts = null;

  function starts() {
    if (wordStarts) return wordStarts;
    var all = [];
    // A word's own clocks only: a subtitle cue's is five seconds of several words.
    var own = heard().own;
    Object.keys(own).forEach(function (id) {
      var rows = own[id];
      for (var i = 0; i < rows.length; i++) all.push(rows[i][2]);
    });
    all.sort(function (a, b) { return a - b; });
    wordStarts = all;
    return all;
  }

  function stepBy(back) {
    var all = starts();
    var now = audio.currentTime;
    var to;
    if (!all.length) {
      to = back ? now - 5 : now + 5;
    } else if (back) {
      // A little behind where the voice is, so pressing back at the top of a word goes
      // to the word before it and not to the top of the one being said.
      to = 0;
      for (var i = 0; i < all.length; i++) {
        if (all[i] >= now - 0.35) break;
        to = all[i];
      }
    } else {
      to = now + 5;
      for (var j = 0; j < all.length; j++) {
        if (all[j] > now + 0.05) { to = all[j]; break; }
      }
    }
    seek(to);
  }

  /* A function, because a portion's two readings need not both be timed word by word,
     and the labels follow whichever is playing. */
  function labelSteps() {
    var byWord = starts().length > 0;
    stepBacks.forEach(function (stepBack) {
      var back = byWord
        ? t("reader.player.back-a-word", "Back a word")
        : t("reader.player.back-five-seconds", "Back five seconds");
      stepBack.setAttribute("aria-label", back);
      stepBack.setAttribute("title", back);
    });
    stepOns.forEach(function (stepOn) {
      var on = byWord
        ? t("reader.player.forward-a-word", "Forward a word")
        : t("reader.player.forward-five-seconds", "Forward five seconds");
      stepOn.setAttribute("aria-label", on);
      stepOn.setAttribute("title", on);
    });
  }
  labelSteps();
  stepBacks.forEach(function (key) { key.addEventListener("click", function () { stepBy(true); }); });
  stepOns.forEach(function (key) { key.addEventListener("click", function () { stepBy(false); }); });

  /* Where the reader had got to, kept across the door. Per text, like the closed player
     and the shut picture; capped and pruned like `targum:place` further up, because a
     store that grows for every text ever opened is a store that one day will not parse.

     A text heard to its end keeps nothing. Resuming a finished text on its last second
     is a control that appears to do nothing, and a reader who comes back to a text they
     finished means to hear it again. */
  var HEARD = "targum:heard";
  var HEARDS = 100;
  var keptAt = 0;
  /* Whose place it is. The text's, for the reading a page opens on; a portion's other
     reading keeps its own, since the same verse is somewhere else in it. */
  var heardOf = spokenOf;

  /* How near the end counts as the end. Two seconds on anything long enough for two
     seconds to be a moment, and a tenth of the way on anything shorter — a fixed two on
     a three-second turn of dialogue calls two thirds of it "finished", and the reader
     who stopped in the middle of it comes back to the top. */
  function tail(length) {
    return Math.min(2, length / 10);
  }

  function keepHeard() {
    if (!heardOf) return;
    var length = span();
    if (!length) return;
    var now = audio.currentTime;
    try {
      var all = JSON.parse(localStorage.getItem(HEARD) || "{}");
      var over = now <= 0.5 || length - now <= tail(length);
      if (over) delete all[heardOf];
      else all[heardOf] = { at: Math.round(now * 100) / 100, when: Date.now() };
      // And the second, on the text's one place for Continue (targum-internal#430).
      if (heardOf === spokenOf && window.TargumSync && window.TargumSync.place) {
        window.TargumSync.place(spokenOf, { section: spokenPart, seconds: over ? 0 : now });
      }
      Object.keys(all)
        .sort(function (a, b) { return (all[b].when || 0) - (all[a].when || 0); })
        .slice(HEARDS)
        .forEach(function (stale) { delete all[stale]; });
      targumKeep(HEARD, JSON.stringify(all));
    } catch (e) {}
    keptAt = Date.now();
  }

  function resume() {
    if (!heardOf) return;
    var length = span();
    if (!length) return;
    var kept = null;
    try {
      kept = JSON.parse(localStorage.getItem(HEARD) || "{}")[heardOf];
    } catch (e) {}
    // Or the second the text's place says, which may be another device's (#430).
    if (!kept && heardOf === spokenOf && window.TargumSync && window.TargumSync.placeOf) {
      var far = window.TargumSync.placeOf(spokenOf);
      if (far && String(far.section) === spokenPart && far.seconds) kept = { at: Number(far.seconds) };
    }
    if (!kept || !kept.at || kept.at >= length - tail(length)) return;
    try {
      audio.currentTime = kept.at;
    } catch (e) {
      return;
    }
    if (player) player.classList.add("placed");
    if (listenBox) listenBox.classList.add("placed");
    paint();
  }

  /* The duration may already be in hand — a data URI's usually is — or may not, which is
     the video sidecar's case. Both, rather than either: waiting on an event that has
     already fired resumes nothing, and reading a duration that is not there yet resumes
     at the wrong second. */
  function whenKnown(run) {
    if (span()) run();
    else audio.addEventListener("loadedmetadata", run, { once: true });
  }
  whenKnown(resume);

  /* A window on the transport, like `TargumSpeech` below is one on the recording. The
     instrument is a closure variable and can be swapped once, so where it has got to is
     not a thing anything outside can read off the page: the clock in the card is rounded
     to the second, and the bar's width is a percentage of a duration nobody else holds.
     Asked at call time, so the swap changes nothing here. */
  window.TargumPlayer = {
    at: function () { return audio.currentTime; },
    length: function () { return span(); },
    seek: seek,
    /* Whether the transport will actually take a seek. A media element reports its
       duration as soon as the metadata is in and can still refuse every write to
       `currentTime` — a response without `Accept-Ranges`, or a decode that has not
       reached the end of the first cluster — and it refuses silently, leaving the fill,
       the clock and `aria-valuenow` at nought, because `paint` reads all three off
       `currentTime`. Nothing in the page needs to ask: `seek` already gives up quietly
       and the reader presses again. A test does, because knowing the length is not
       knowing the seek will land, and the two are far enough apart on a cold runner to
       be the whole of a flake. */
    seekable: function () {
      var ranges = audio.seekable;
      return !!(ranges && ranges.length && ranges.end(ranges.length - 1) > 0);
    },
    /* For a playlist (targum-internal#434; design.md §12, "Listening plays on by itself",
       2026-10-09): the one media element, whether the whole recording is running, a
       press of play that starts it where it stands, and `release`, which hands the
       element over to the next item's recording once this one has ended with the screen
       locked. Released, nothing here writes this text's place or marks its lines. */
    element: function () { return audio; },
    following: function () { return following && !audio.paused; },
    play: function (quietly) {
      if (!following || audio.paused) toggleScene(quietly === true);
    },
    release: release,
    /* For the listening view (design.md §12, "Listening is a view of its own",
       2026-10-10), which draws the same recording and keeps nothing of its own: a pause
       that keeps the place, play and pause as one press, the lines in reading order with
       their clocks, each word's clock, and the speed stepped round as the strip's figure
       steps it. */
    pause: function () {
      if (audio.paused) return;
      if (following && !playing) toggleScene();
      else halt();
    },
    paused: function () { return audio.paused; },
    toggle: function () { toggleScene(); },
    lines: function () { return order; },
    clocks: function () { return wordClocks; },
    handed: function () { return released; },
    nextRate: function () {
      var i = RATES.indexOf(nearestRate(audio.playbackRate));
      setRate(RATES[(i + 1) % RATES.length], true);
    },
  };

  var released = false;
  function release() {
    if (released) return audio;
    halt();
    released = true;
    audio.removeEventListener("timeupdate", onTime);
    audio.removeEventListener("ended", halt);
    audio.removeEventListener("pause", keepHeard);
    audio.removeEventListener("pause", stretchOver);
    audio.removeEventListener("ended", stretchOver);
    document.body.classList.add("player-handed");
    return audio;
  }

  /* How tall the strip is, for the things that stand above it. The picture's dock used
     a figure written into the stylesheet, and the strip is not one height: it grows a
     bar and a clock the moment a text has a place to show, which is every text the
     reader has been in before — and the picture sat on top of it. Measured rather than
     guessed, and only when it changes. */
  if (player && window.ResizeObserver) {
    var measure = new ResizeObserver(function () {
      var tall = player.hidden ? 0 : player.offsetHeight;
      document.documentElement.style.setProperty("--player-tall", tall + "px");
    });
    measure.observe(player);
  }

  /* Hear first (targum-internal#265). A switch and nothing more: off each time the page
     opens, written nowhere, and said in words when it moves. Pressing it off mid-line
     brings the text back at once rather than making the reader wait out the sentence. */
  hearFirsts.forEach(function (key) {
    key.addEventListener("click", function () {
      var on = key.getAttribute("aria-pressed") !== "true";
      hearFirsts.forEach(function (each) {
        each.setAttribute("aria-pressed", on ? "true" : "false");
      });
      if (!on && hearing) { hearing.classList.remove("hearing"); hearing = null; restand(); }
      var reader = window.TargumReader;
      if (reader && reader.say) {
        reader.say(
          on
            ? t("reader.player.hear-first-on", "Hear first. Press a line to hear it before you see it.")
            : t("reader.player.hear-first-off", "Hear first is off.")
        );
      }
    });
  });

  /* Word by word (targum-internal#265, step 2). A line played on its own lights each of
     its words as the voice reaches it, where the recording was aligned word by word — the
     sentence broken into the words it is made of, which is the listening a learner is
     practising. Read off the clocks each frame rather than from `timeupdate`, which comes
     four times a second and would light a short word late or not at all. Nothing moves:
     one underline goes from word to word. A line with no word clocks lights nothing. */
  var lit = null;
  var litFrame = 0;

  function unlight() {
    if (litFrame && window.cancelAnimationFrame) window.cancelAnimationFrame(litFrame);
    litFrame = 0;
    if (lit) lit.classList.remove("voiced-now");
    lit = null;
  }

  // The word on show whose letters a clock covers. Only the source cell: the cells not on
  // show hold no words, and an Onkelos cell's offsets are its own.
  function wordAt(id, from, to) {
    var pair = document.querySelector('#reader .pair[data-id="' + CSS.escape(id) + '"]');
    if (!pair) return null;
    var words = pair.querySelectorAll(".src .w[data-bare]");
    for (var i = 0; i < words.length; i++) {
      var span = words[i].getAttribute("data-bare").split(",");
      if (parseInt(span[0], 10) < to && parseInt(span[1], 10) > from) return words[i];
    }
    return null;
  }

  function follow(id) {
    var rows = heard().own[id];
    if (!rows || !rows.length || !window.requestAnimationFrame) return;
    function tick() {
      litFrame = 0;
      if (!playing) return unlight();
      var now = audio.currentTime;
      var word = null;
      for (var i = 0; i < rows.length; i++) {
        if (now >= rows[i][2] && now < rows[i][3]) {
          word = wordAt(id, rows[i][0], rows[i][1]);
          break;
        }
      }
      if (word !== lit) {
        if (lit) lit.classList.remove("voiced-now");
        lit = word;
        if (lit) lit.classList.add("voiced-now");
      }
      litFrame = window.requestAnimationFrame(tick);
    }
    tick();
  }

  /* One line. */
  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest(".say") : null;
    if (!button) return;
    var span = spans[button.getAttribute("data-id")];
    if (!span) return;
    var again = playing === button;
    halt();
    if (again) return;
    var line = button.getAttribute("data-id") || "";
    if (askedFor[line] && window.TargumEvents) {
      window.TargumEvents.note({ kind: "replay", medium: pictureUp() ? "watch" : "listen", segment: line });
    }
    askedFor[line] = true;
    playing = button;
    playingEnd = span[1];
    button.classList.add("saying");
    if (hearFirst && hearFirst.getAttribute("aria-pressed") === "true") {
      hearing = button.closest ? button.closest(".pair") : null;
      if (hearing) hearing.classList.add("hearing");
      restand();
    }
    play(span[0]);
    follow(button.getAttribute("data-id"));
    // Wall-clock, so the span's length is divided by the speed it is played at.
    stopAt = setTimeout(halt, Math.max(0, ((span[1] - span[0]) * 1000) / audio.playbackRate));
  });

  /* One word, or one run of them, for the cards. The audio and its timers live in this
     closure, so this window is the whole bridge — and it only exists on a page with a
     recording, which is how a card on a silent page finds no ear to offer. */
  window.TargumSpeech = {
    /* Where a tapped span's sound sits: the clocks of every written word it overlaps,
       breathing a little either side — the chapter cutter's move — but never into the
       neighbouring word. Null where the recording never said it. */
    clockFor: function (segmentId, start, end) {
      var rows = wordClocks[segmentId];
      if (!rows || !rows.length) return null;
      var from = null;
      var until = null;
      var before = 0;
      var after = Infinity;
      for (var i = 0; i < rows.length; i++) {
        var row = rows[i];
        if (row[0] < end && row[1] > start) {
          if (from === null || row[2] < from) from = row[2];
          if (until === null || row[3] > until) until = row[3];
        } else if (row[1] <= start) {
          if (row[3] > before) before = row[3];
        } else if (row[0] >= end && row[2] < after) {
          after = row[2];
        }
      }
      if (from === null || until <= from) return null;
      var PAD = 0.15;
      /* Rounded like the build side's clocks, so a slice is a tidy number and not
         float dust the tests would have to forgive. */
      var opens = Math.max(before, from - PAD, 0);
      var closes = Math.min(after, until + PAD);
      return [Math.round(opens * 1000) / 1000, Math.round(closes * 1000) / 1000];
    },
    playSlice: function (slice) {
      halt();
      play(slice[0]);
      stopAt = setTimeout(halt, Math.max(0, ((slice[1] - slice[0]) * 1000) / audio.playbackRate));
    },
  };

  /* The whole scene: play, and pause where it stands rather than starting over. A
     control that only restarts is a control nobody presses twice. */
  function at(seconds) {
    return lineAt(seconds);
  }

  // A click hands this an event, so only a literal `true` is quiet.
  function toggleScene(quietly) {
    // Handed to the next item of a playlist: play and pause are that player's (#434).
    if (released) {
      if (audio.paused) audio.play().catch(function () {});
      else audio.pause();
      return;
    }
    if (playing) {                      /* a single line was running; that ends here */
      if (stopAt) { clearTimeout(stopAt); stopAt = null; }
      playing.classList.remove("saying");
      playing = null;
      audio.pause();
    }
    if (following && !audio.paused) {   /* pause: keep the place and the mark */
      audio.pause();
      pressed(false);
      return;
    }
    following = true;
    pressed(true);
    var opening = order.length ? order[0].start : 0;
    var from = audio.ended || audio.currentTime <= 0 ? opening : audio.currentTime;
    play(from, quietly === true);
    mark(at(from));
  }

  scenes.forEach(function (button) {
    button.addEventListener("click", toggleScene);
  });

  function onTime() {
    paint();
    /* Written down as it goes, not only when it stops. A tab closed by the system, a
       phone that sleeps and never wakes to this page, a browser that crashes — none of
       them send `pause`, and every one of them is a reader who comes back. Five seconds
       is often enough to lose nothing worth hearing again and rare enough that a store
       written on every tick is not what this is. */
    if (Date.now() - keptAt > 5000) keepHeard();
    if (!following) return;
    // The same line `paint` just gave the picture's caption: two rules here took turns
    // where spans overlap, and each turn scrolled the transcript (2026-10-29).
    mark(lineAt(audio.currentTime));
  }

  /* Attached through a function because the instrument can be swapped once: a page
     whose sidecar video is gone falls back to the inlined audio, and the new element
     needs the same ears. The handlers read `audio` at call time, so nothing else
     changes hands. */
  function wire(element) {
    element.addEventListener("timeupdate", onTime);
    element.addEventListener("ended", halt);
    // Every stop the reader can cause arrives here: the play button, the space bar, the
    // tab going to the background, the end of the text.
    element.addEventListener("pause", keepHeard);
  }
  wire(audio);

  /* Space plays and pauses — on a dialogue, and only on a dialogue.
   *
   * Space is already spoken for here: in paged mode it turns the page. Two meanings for
   * one key is the thing this file says elsewhere means neither, so the split is by text:
   * where a text can be listened to, Space plays it, and nowhere else.
   *
   * This was narrower for a day — dialogues only, on the reasoning that a book is fifty
   * chapters and the pager should keep its key. That was overruled, and it is the right
   * call: a reader who has pressed Space on one recorded text has learned what Space
   * does, and having it mean something else on the next one is the confusion the rule
   * against two meanings exists to prevent. The arrows and the pager still turn pages,
   * and the help card says which it is.
   *
   * Captured, because the pager listens on the way back up and would turn the page as
   * well — one keystroke doing two things is exactly what this is avoiding.
   *
   * `<` and `>` step the speed, the keys every video player has taught. Read off the
   * physical key as well as the character: under a Hebrew layout Shift on the comma
   * arrives as something else entirely, the way the letters do further up. */
  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    var key = event.key;
    if (event.shiftKey && event.code === "Comma") key = "<";
    if (event.shiftKey && event.code === "Period") key = ">";
    if (!/^[ <>]$/.test(key)) return;
    var on = document.activeElement;
    // SELECT is in this list and not in the argument below: Space is how a keyboard
    // opens one, and a page that grows one must not lose it to the player.
    if (
      on &&
      (on.tagName === "INPUT" || on.tagName === "SELECT" || on.tagName === "TEXTAREA" || on.isContentEditable)
    )
      return;
    /* Not even for a focused button, which would otherwise answer Space itself. On a page
       that can be listened to Space plays and does nothing else, so a button under the
       keyboard must not quietly take it — walking to the end of a text puts the keyboard
       on Done, and Space there would finish the text instead of playing it. Enter is what
       presses a button. */
    event.preventDefault();
    event.stopPropagation();
    if (key === " ") toggleScene();
    else stepRate(key === "<" ? -1 : 1);
  }, true);

  /* Saving the audio. The file is already in the page, so this asks the network for
     nothing — the same reason the fonts and the icons ride inside it. A portion's is
     beside the page instead, and saving it asks for the file the player already has. */
  var offer = function () {};
  if (player) {
    /* Both copies: the strip's, and the one the `···` menu carries on a phone, where
       the strip's row has no width for a one-off action. Distinct classes on purpose —
       reusing `.player-get` made the selector match two elements and broke four browser
       tests on strict mode — collected here so one handler drives both. */
    var gets = Array.prototype.slice.call(document.querySelectorAll(".player-get, .more-get"));
    var get = gets[0];
    if (get) {
      var named = (document.title || "dialogue").replace(/[\\/:*?"<>|\u2066-\u2069]/g, "").trim();
      /* Named for what it actually is. The build inlines whatever the scene was voiced
         as, so a suffix written into the page rather than read off it hands the reader a
         file their machine opens with the wrong thing. */
      var ENDS = {
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/aac": "aac",
        "audio/ogg": "ogg",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/flac": "flac",
      };
      /* A file beside the page is named by its own suffix; a data URI by its type. */
      offer = function (src) {
        var kind = src.slice(5).split(";")[0].split(",")[0];
        var end = /^data:/.test(src) ? ENDS[kind] : (/\.([a-z0-9]+)$/i.exec(src) || [])[1];
        gets.forEach(function (one) {
          one.setAttribute("href", addressOf(src));
          one.setAttribute("download", (named || "dialogue") + "." + (end || "mp3"));
        });
      };
      offer(speech.audio);
    }

    /* Away until Listen (targum-internal#421, David, 2026-10-05). The strip used to stand
       at the foot the moment a recorded text opened, so a reader who did not know the
       audio was there would find it; the bar's own ▶ Listen does that now, and two
       Listens on one screen was one too many. So nothing stands at the foot when a text
       opens. The strip comes up when the voice starts — from Listen, from Space, from a
       line's own press — with the line, the step, the speed, Hear first and the file,
       and its × puts it away again. Nothing is kept: the next text opens the same way.
       (Before this the × was remembered per text, `targum:player-closed:<text>`; that
       store is no longer read.) */
    // The page needs to know a player is out: the blocks at the foot of a text sit after
    // the pairs, and the pairs are the only thing `room` budgets for — so the Done line
    // and the suggestion land inside the band the player is fixed in.
    function standing(out) {
      document.body.classList.toggle("has-player", !!out);
    }

    /* The pages were laid out before this ran, with room kept for a player that may be
       put away — so whenever that changes, they are laid out again. */
    function remeasure() {
      var reader = window.TargumReader;
      if (reader && reader.relayout) reader.relayout();
    }

    function bringUp() {
      // Not while the picture is up: its own controls are the transport then (#422).
      if (!player.hidden || (videoBox && !videoBox.hidden)) return;
      player.hidden = false;
      standing(true);
      remeasure();
    }

    // Only where the bar carries Listen, which is every page that has a recording; a
    // page built before the bar did keeps its strip standing. A text with a picture is
    // the same since #422: while the picture is up the controls under it play it, and
    // once it is put away the page is an audio reader, with Listen and this strip.
    var listenFirst = scenes.length > 1;
    /* On a phone the strip is the foot bar, and stands from the start (board ReaderPhone;
       design.md §12, 2026-10-09): play, the track, the speed and the view, where a thumb
       is. Not over a picture, whose own controls play it; when the picture is put away,
       the bar comes up (`showVideo`). */
    var footBar = window.matchMedia ? window.matchMedia("(max-width: 40rem)") : null;
    var standsAtFoot = function () {
      return !!(footBar && footBar.matches) && !(videoBox && !videoBox.hidden) && !videoEl;
    };
    if (listenFirst && !standsAtFoot()) {
      player.hidden = true;
      remeasure();
    }
    standing(!player.hidden);

    /* Both copies — the strip's ×, and the menu's on a phone. Put away, the strip leaves
       the bar's Listen as the way back, which is where focus goes. */
    Array.prototype.slice.call(document.querySelectorAll(".player-close, .more-close")).forEach(
      function (shut) {
        shut.addEventListener("click", function () {
          halt();
          player.hidden = true;
          standing(false);
          remeasure();
          if (listenFirst && scenes[0] && scenes[0].getClientRects().length) {
            scenes[0].focus({ preventScroll: true });
          }
        });
      }
    );

    /* Up as the voice starts, however it was started. */
    if (listenFirst) {
      scenes[0].addEventListener("click", bringUp);
      audio.addEventListener("playing", bringUp);
    }
    // And on its own, without starting the voice: for a page that frames this one, and
    // for the browser tests about the transport, which are about the transport.
    if (window.TargumPlayer) {
      window.TargumPlayer.show = bringUp;
      window.TargumPlayer.footBar = function () {
        return !!(footBar && footBar.matches);
      };
    }
  }

  /* Chanted or spoken (targum-internal#412). A portion's aliyah carries the chanting and
     the plain reading of the book, each its own file with its own verse spans, and the
     switch hands the one instrument the other file. Everything above reads `spans`,
     `order` and `wordClocks` at call time, so swapping them is the whole of it. The
     choice is the reader's and kept per browser, like the speed: which reading a person
     wants to follow is a fact about them and not about the aliyah. */
  var recordings = !videoEl && speech.voices && speech.voices.length > 1 ? speech.voices : null;
  if (recordings) {
    var RECORDING_STORE = "targum:recording";
    var recordingKeys = Array.prototype.slice.call(document.querySelectorAll("[data-recording]"));
    var useRecording = function (key, chosen) {
      var found = null;
      recordings.forEach(function (one) {
        if (one.key === key) found = one;
      });
      if (!found) return;
      var rate = nearestRate(audio.playbackRate);
      // Switched while the whole aliyah is playing, the voice goes on in the other
      // reading from the start of the verse it was on (QA 2026-10-05, S4): the same verse
      // is somewhere else in the other file, and its start is the one place both have.
      // Paused, it stays paused, at the other reading's own kept place.
      var going = following && !audio.paused && !playing && order.length > 0;
      var verse = going ? (marked && marked.getAttribute("data-id")) || at(audio.currentTime) : "";
      // Written now: the pause `halt` causes is told after the source has changed, by
      // which time the place it would keep is the new reading's nought.
      keepHeard();
      halt();
      audio.src = addressOf(found.audio);
      spans = found.spans || {};
      wordClocks = found.words || {};
      order = ordered(spans);
      wordStarts = null;
      heardTable = null;
      labelSteps();
      heardOf = found === recordings[0] ? spokenOf : spokenOf + "|" + found.key;
      // A new source puts the element back to its default speed; the reader's is kept.
      setRate(rate, false);
      offer(found.audio);
      if (fill) fill.style.inlineSize = "0%";
      if (clock) clock.textContent = "";
      if (player) player.classList.remove("placed");
      if (barFill) barFill.style.inlineSize = "0%";
      if (barClock) barClock.textContent = "";
      if (listenBox) listenBox.classList.remove("placed");
      whenKnown(function () {
        resume();
        paint();
        if (!going) return;
        var from = spans[verse] ? spans[verse][0] : order.length ? order[0].start : 0;
        following = true;
        pressed(true);
        play(from);
        mark(at(from));
      });
      var named = "";
      recordingKeys.forEach(function (button) {
        var on = button.getAttribute("data-recording") === found.key;
        button.classList.toggle("on", on);
        button.setAttribute("aria-pressed", on ? "true" : "false");
        // The name, not the credit beside it in the bar's choice (#421).
        var name = button.querySelector(".pick-name") || button;
        if (on) named = name.textContent;
      });
      // And the bar's player says which reading it now plays.
      var now = document.getElementById("voice-now");
      if (now && named) now.textContent = named;
      if (chosen) {
        try {
          targumKeep(RECORDING_STORE, found.key);
        } catch (e) {}
        var reader = window.TargumReader;
        if (reader && reader.say && named) reader.say(named);
      }
    };
    recordingKeys.forEach(function (button) {
      button.addEventListener("click", function () {
        if (button.getAttribute("aria-pressed") === "true") return;
        useRecording(button.getAttribute("data-recording"), true);
      });
    });
    var keptRecording = "";
    try {
      keptRecording = localStorage.getItem(RECORDING_STORE) || "";
    } catch (e) {}
    if (keptRecording && keptRecording !== recordings[0].key) useRecording(keptRecording, false);
  }

  /* The picture and its transcript (targum-internal#422, David, 2026-10-05; design.md
     §12). A text that carries a video opens with its picture up, in one of two ways of
     standing that the reader chooses in the bar and that are kept per reader, like the
     speed: Beside — the picture at the left, one thin row of controls under it, and the
     transcript beside it following the voice — and Theatre — the picture large, the
     line being said under it with its words tappable, and the transcript one press away,
     under the picture (2026-10-11). While it plays, all of that but the picture, the line of where the voice
     is and the line being said steps back; a pause, the pointer or a key brings it back.
     On a phone the picture stands above its controls and the transcript runs under it.

     It replaced a picture that stood in a corner, could be picked up, moved and sized,
     and went full screen with a second floating transport over it. The picture can
     still be put away — under ⋯ — and then the page is an audio reader, with Listen and
     the strip; and full screen is the browser's, under ⋯ as on every text.

     Whether the picture is up is kept per text, the way it was (`targum:video-shut:`,
     recording a reader who put it away). The old stores of how it stood — the corner,
     the place, the size, full screen — are left where they are and read by nothing. */
  if (videoBox && videoEl) {
    var body = document.body;
    var flips = Array.prototype.slice.call(document.querySelectorAll("[data-video]"));
    var VIDEO_STORE = "targum:video-shut:" + spokenOf;
    //: Beside or Theatre, kept per reader rather than per text: how somebody likes to
    //: watch is a fact about them, like the speed and the type size.
    var VIEW_STORE = "targum:film-view";
    var VIEWS = ["beside", "theatre"];
    var viewKeys = Array.prototype.slice.call(document.querySelectorAll("[data-film-view]"));
    var filmCtl = videoBox.querySelector(".film-ctl");
    var filmPlay = videoBox.querySelector(".film-play");
    var filmFill = videoBox.querySelector(".film-fill");
    var filmLine = videoBox.querySelector(".film-line");
    var filmAt = videoBox.querySelector(".film-at");
    var filmLength = videoBox.querySelector(".film-length");
    var filmLengthSaid = videoBox.querySelector(".film-length-said");
    var loopKey = videoBox.querySelector(".film-loop");
    var transcriptKey = videoBox.querySelector(".film-transcript");
    var panelHead = document.getElementById("film-panel-head");
    var panelShut = panelHead ? panelHead.querySelector(".film-panel-close") : null;
    var sub = document.getElementById("film-sub");
    var subBefore = sub ? sub.querySelector(".film-before") : null;
    var subNow = sub ? sub.querySelector(".film-now") : null;
    var subTr = sub ? sub.querySelector(".film-tr") : null;
    var subAfter = sub ? sub.querySelector(".film-after") : null;
    var card = document.getElementById("gloss-card");
    var wideFilm = window.matchMedia("(min-width: 60.01rem)");
    var S = window.TargumStrings || {
      t: function (key, english) {
        return english;
      },
    };
    var view = "beside";
    //: Whether Theatre's transcript is open, under the picture. Theatre always opens with
    //: it put away and the line being said under the picture (David, 2026-10-11; design.md
    //: §12, "Theatre is the picture with its text under it"), so nothing about it is
    //: kept; the old `targum:film-panel` is read by nothing.
    var panel = false;
    //: Theatre's picture as a share of the size the layout gives it (2026-10-07), kept
    //: per reader like the view; 1 is the default and is never written.
    var SIZE_STORE = "targum:film-size";
    var size = 1;
    //: Beside, where the line between the picture and the transcript stands (David,
    //: 2026-10-08), as a share of the room the two have; kept on this device, and 0 —
    //: the layout's own place — is never written.
    var SPLIT_STORE = "targum:film-split";
    var split = 0;
    try {
      split = parseFloat(localStorage.getItem(SPLIT_STORE)) || 0;
    } catch (e) {}
    if (!(split > 0 && split < 1)) split = 0;
    var splitEl = document.getElementById("film-split");
    //: The transcript keeps a column a line can be read in; the picture keeps a face.
    var SPLIT_TEXT = 352;
    var SPLIT_LEAST = 240;
    //: The bounds of the line, in pixels from the window's left, as `fit` last found them.
    var splitAt = { room: 0, least: 0, most: 0, col: 0 };
    var fullW = 0;
    var sizeGrip = videoBox.querySelector(".film-size");
    //: The smallest it goes: three tenths of the full size and never under 280px wide,
    //: which still shows a face — and never more than the full size on a small window.
    var SIZE_LEAST = 0.3;
    var SIZE_LEAST_PX = 280;
    var sizeFloor = function (full) {
      return Math.min(full, Math.max(Math.round(full * SIZE_LEAST), SIZE_LEAST_PX));
    };
    // The separator's numbers, in per cent of the full size.
    var sized = function (full) {
      if (!sizeGrip || !full) return;
      var least = Math.round((sizeFloor(full) / full) * 100);
      var now = Math.max(least, Math.round(size * 100));
      sizeGrip.setAttribute("aria-valuemin", String(least));
      sizeGrip.setAttribute("aria-valuenow", String(now));
      sizeGrip.setAttribute("aria-valuetext", S.t("reader.film.size-now", "{n}% of full size", { n: now }));
    };

    var filmUp = function () {
      return !videoBox.hidden;
    };
    var say = function (text) {
      var reader = window.TargumReader;
      if (reader && reader.say && text) reader.say(text);
    };
    var relay = function (held) {
      var reader = window.TargumReader;
      if (reader && reader.relayout) reader.relayout(held);
    };
    // The line a reader is on under the picture: the first whose foot is below it.
    var lineUnder = function () {
      var top = videoBox.getBoundingClientRect().bottom;
      var lines = document.querySelectorAll("#reader .pair");
      for (var i = 0; i < lines.length; i++) {
        if (!lines[i].getClientRects().length) continue;
        if (lines[i].getBoundingClientRect().bottom > top + 20) return lines[i];
      }
      return null;
    };
    var look = function () {
      var reader = window.TargumReader;
      if (reader && reader.look) reader.look();
    };

    /* The film's shape: off the file once it is known, off what the build measured
       before then, and 16:9 failing both. */
    var shape = function () {
      var wide = videoEl.videoWidth;
      var high = videoEl.videoHeight;
      if (wide && high) return wide / high;
      var built = (videoBox.getAttribute("data-film") || "").split(" / ");
      var w = parseFloat(built[0]);
      var h = parseFloat(built[1]);
      return w > 0 && h > 0 ? w / h : 16 / 9;
    };

    /* How big the picture is, worked out rather than left to the stylesheet, because it
       answers to the window's height as well as its width and to the film's own shape:
       a reel beside its transcript is a narrow column, and the transcript has the rest.
       Said to the stylesheet as `--film-w`, the picture's width, and `--film-col`, the
       width of the column the picture stands in — which the transcript is laid out
       beside. Under 60rem the stylesheet has it: the picture is the window's width. */
    var fit = function () {
      var root = document.documentElement.style;
      if (splitEl) splitEl.hidden = !(filmUp() && wideFilm.matches && view === "beside");
      if (!filmUp() || !wideFilm.matches) {
        root.removeProperty("--film-w");
        root.removeProperty("--film-col");
        return;
      }
      var W = document.documentElement.clientWidth || window.innerWidth;
      var H = window.innerHeight;
      var bar = document.querySelector(".bar");
      var top = bar ? bar.getBoundingClientRect().height : 56;
      var ratio = shape();
      var w;
      var col;
      // The word list, where a reader has it open, is a column at the window's edge.
      var list = document.getElementById("list");
      var listed = list && !list.hidden && body.classList.contains("list-open") ? 240 : 0;
      if (view === "theatre") {
        // The picture in the middle of what the word list leaves, and its text under it.
        var area = W - listed;
        // Room under it for the controls and the line being said; with the transcript
        // open under it, the picture stays at the top and is held to about half the
        // window, so the transcript scrolling below has room to be read (2026-10-11).
        // In a short window the picture keeps half the room whatever that leaves: the
        // flat reserve made it a small box in the middle of a wide page, and the line
        // under it scrolls in what is left (David, 2026-10-11).
        var high = panel ? (H - top) * 0.55 - 60 : Math.max(H - top - 300, (H - top) * 0.5);
        w = Math.min(area - 160, 1120, high * ratio);
        col = 0;
        // The reader's own size, a share of that (2026-10-07). At the full share this
        // is the line above untouched, so Theatre stands where it always stood.
        fullW = Math.max(160, Math.round(w));
        w = Math.max(sizeFloor(fullW), fullW * size);
        sized(fullW);
      } else {
        // Room under it for the controls and the lines that say what it is.
        var room = W - listed;
        var tallest = (H - top - 210) * ratio;
        w = Math.min(room * 0.6 - 80, tallest);
        col = w + 80;
        // Where the reader moved the line to (2026-10-08): between a picture that still
        // shows a face and a transcript a line can be read in, and never wider than the
        // picture's height lets it be, so the line never stands off in empty paper.
        var most = Math.max(SPLIT_LEAST + 80, Math.min(room - SPLIT_TEXT, tallest + 80));
        var least = Math.min(most, SPLIT_LEAST + 80);
        if (split) {
          col = Math.max(least, Math.min(most, split * room));
          w = col - 80;
        }
        splitAt = { room: room, least: least, most: most, col: col };
        if (splitEl) {
          var pc = function (px) {
            return String(Math.round((px / room) * 100));
          };
          splitEl.setAttribute("aria-valuemin", pc(least));
          splitEl.setAttribute("aria-valuemax", pc(most));
          splitEl.setAttribute("aria-valuenow", pc(col));
        }
      }
      w = Math.max(160, Math.round(w));
      root.setProperty("--film-w", w + "px");
      root.setProperty("--film-col", Math.round(Math.max(col, 0)) + "px");
    };

    /* --- the line under the picture -------------------------------------------- */

    /* Copied out of the transcript as the clock reaches it, words and all: the same
       spans with the same levels, inside a holder that answers to the line's id, so a
       tap on one opens the same card a tap in the transcript does. The transcript draws
       its words only where they are on screen, so the line is drawn first. When the
       transcript redraws a line — a word just marked known — the copy follows. */
    var subFor = null;
    var subWatch = null;
    var plainOf = function (pair) {
      var form = pair ? shownForm(pair) : null;
      return form ? form.textContent.replace(/[⁦-⁩]/g, "").trim() : "";
    };
    var neighbour = function (id, by) {
      for (var i = 0; i < order.length; i++) {
        if (order[i].id === id) {
          var next = order[i + by];
          return next ? document.querySelector('#reader .pair[data-id="' + CSS.escape(next.id) + '"]') : null;
        }
      }
      return null;
    };
    var copyLine = function (pair) {
      if (!subNow) return;
      var form = shownForm(pair);
      // A pointed cell with nothing in it is no line to say: the bare one is.
      if (form && !form.textContent.replace(/[⁦-⁩\s]/g, "")) {
        form = pair.querySelector(".src.plain") || form;
      }
      var holder = document.createElement("div");
      // Its own class rather than `pair`, so nothing that walks the transcript counts it;
      // the card's helpers answer to both.
      holder.className = "film-pair";
      holder.setAttribute("data-id", pair.getAttribute("data-id"));
      if (form) {
        var copy = form.cloneNode(true);
        copy.removeAttribute("id");
        Array.prototype.forEach.call(copy.querySelectorAll(".voiced-now, .looked-up, .queued"), function (w) {
          w.classList.remove("voiced-now", "looked-up", "queued");
          w.removeAttribute("tabindex");
          w.removeAttribute("aria-describedby");
        });
        holder.appendChild(copy);
      }
      // A word looked up from here stays marked while its card is up (C).
      var was = subNow.querySelector(".w.looked-up");
      var kept = was ? was.getAttribute("data-bare") : null;
      subNow.textContent = "";
      subNow.appendChild(holder);
      if (kept) {
        var again = holder.querySelector('.w[data-bare="' + kept + '"]');
        if (again) again.classList.add("looked-up");
      }
      subLit = null;
    };
    var drawSub = function (id) {
      if (!sub) return;
      var pair = id ? document.querySelector('#reader .pair[data-id="' + CSS.escape(id) + '"]') : null;
      if (subFor) subFor.classList.remove("film-said");
      if (subWatch) subWatch.disconnect();
      subFor = pair;
      sub.classList.toggle("empty", !pair);
      if (!pair) {
        if (subNow) subNow.textContent = "";
        if (subTr) subTr.textContent = "";
        if (subBefore) subBefore.textContent = "";
        if (subAfter) subAfter.textContent = "";
        return;
      }
      pair.classList.add("film-said");
      var reader = window.TargumReader;
      if (reader && reader.draw) reader.draw(pair);
      copyLine(pair);
      var said = plainOf(pair).length;
      sub.setAttribute("data-long", said > 170 ? "2" : said > 85 ? "1" : "0");
      var tr = pair.querySelector(".tr");
      if (subTr) subTr.textContent = tr ? tr.textContent.replace(/[⁦-⁩]/g, "").trim() : "";
      if (subBefore) subBefore.textContent = plainOf(neighbour(id, -1));
      if (subAfter) subAfter.textContent = plainOf(neighbour(id, 1));
      if (window.MutationObserver) {
        var pending = false;
        subWatch = new MutationObserver(function () {
          if (pending) return;
          pending = true;
          requestAnimationFrame(function () {
            pending = false;
            if (subFor === pair) copyLine(pair);
          });
        });
        Array.prototype.forEach.call(pair.querySelectorAll(".src"), function (cell) {
          subWatch.observe(cell, { childList: true });
        });
      }
    };
    var subId = null;
    /* At the end of the part (2026-10-07): the last line held, or the film over. The door
       to the next part stands under the picture from then (`film-next`), so a reader who
       stepped to the last line has it without playing to the end, and one who played to
       the end has it where they are looking. */
    var atEnd = function () {
      var last = order.length ? order[order.length - 1].id : null;
      var end = filmUp() && (videoEl.ended || (!!last && subId === last));
      body.classList.toggle("film-at-end", !!end);
      var ending =
        filmUp() && playedOut && videoEl.ended && view === "theatre" && wideFilm.matches && !lastOfMany();
      // The end of a part is the card under the picture (board ReaderTheatreEnd), with no
      // column beside it: the column steps aside for it, without the reader's choice
      // being written down, and is back with the next part. Inside a playlist too, where
      // the card is the playlist's foot, moved in the same way (audit Q10, 2026-10-09):
      // it stood at the foot of the transcript, far under the picture.
      if (ending && panel) {
        panel = false;
        place();
        return;
      }
      showEnd(ending);
    };
    // Played to its end, not only stood at it: a seek to the last frame with nothing
    // playing is a reader looking for something, and the line under the picture stays.
    // `running` is whether the film has been playing since the last such seek.
    var playedOut = false;
    var running = false;
    // The last part of a recording cut in parts ends at the foot of its transcript, where
    // the library's offer is as well, and Theatre opens the transcript to it (below).
    var lastOfMany = function () {
      var pages = document.querySelector(".pager[data-by-part]");
      return !!pages && !pages.querySelector("[data-next]");
    };

    /* The end of a part in Theatre (David, 2026-10-08; design.md §12). Played to its end,
       the line under the picture gives way to what ended, the words here never marked,
       and the foot of the text — moved in, not copied, so its press, its Undo and its
       count are the ones the transcript's foot has. Put back where it came from the
       moment the film plays or moves again, the view changes or the transcript opens. */
    var endBox = document.getElementById("film-end");
    var endFoot = endBox ? endBox.querySelector(".film-end-foot") : null;
    var endAsk = endBox ? endBox.querySelector(".film-end-ask") : null;
    var endWords = endBox ? endBox.querySelector(".film-end-words") : null;
    var footHome = null;
    var paintEnd = function () {
      var reader = window.TargumReader;
      var rest = reader && reader.unmarked ? reader.unmarked(4) : { count: 0, words: [] };
      if (endAsk) {
        endAsk.hidden = !rest.count;
        endAsk.textContent = !rest.count
          ? ""
          : rest.count === 1
            ? S.t("reader.film.end-ask-single", "Do you know this word?")
            : S.tn(
                "reader.film.end-ask",
                rest.count,
                "{n} word here you haven't marked. Do you know it?",
                "{n} words here you haven't marked. Do you know them?"
              );
      }
      if (endWords) {
        endWords.textContent = "";
        // The word as the text writes it, and what it means beside it in the reader's
        // language (board ReaderTheatreEnd; design.md §12, 2026-10-09).
        var glossed = rest.glossed || rest.words.map(function (word) {
          return { word: word, gloss: "" };
        });
        var glossLanguage = document.documentElement.lang || "en";
        glossed.forEach(function (one) {
          var chip = document.createElement("li");
          chip.className = "film-end-word";
          var word = document.createElement("span");
          word.className = "film-end-he";
          word.textContent = one.word;
          chip.appendChild(word);
          if (one.gloss) {
            var gloss = document.createElement("span");
            gloss.className = "film-end-gloss";
            gloss.setAttribute("lang", one.language || glossLanguage);
            gloss.setAttribute("dir", "ltr");
            gloss.textContent = String(one.gloss).split(/[;,]/)[0].trim();
            chip.appendChild(gloss);
          }
          endWords.appendChild(chip);
        });
        if (rest.count > rest.words.length) {
          var more = document.createElement("li");
          more.className = "film-end-more";
          more.setAttribute("dir", "ltr");
          more.setAttribute("lang", document.documentElement.lang || "en");
          more.textContent = S.t("reader.film.end-more", "+{n} more", { n: rest.count - rest.words.length });
          endWords.appendChild(more);
        }
        endWords.hidden = !rest.count;
      }
    };
    var showEnd = function (on) {
      if (!endBox || !endFoot) return;
      var foot = document.getElementById("foot");
      on = !!on && !!foot;
      var was = !endBox.hidden;
      if (on) paintEnd();
      if (on === was) return;
      endBox.hidden = !on;
      body.classList.toggle("film-ended", on);
      if (on) {
        footHome = { parent: foot.parentNode, next: foot.nextSibling };
        endFoot.appendChild(foot);
      } else if (footHome && foot.parentNode === endFoot) {
        footHome.parent.insertBefore(foot, footHome.next);
        footHome = null;
      }
    };
    filmCaption = function (id) {
      // The transcript lights the line held as well, paused or playing: moving the voice
      // with the picture up moves the lit line with it.
      if (id && filmUp() && !playing) mark(id);
      if (id === subId) return atEnd();
      subId = id;
      drawSub(id);
      atEnd();
    };

    /* --- the word being said ----------------------------------------------------- */

    /* Lit where the recording was aligned word by word, in the transcript and in the
       line under the picture at once, read off the clocks every frame while it plays:
       `timeupdate` comes four times a second and would light a short word late or not
       at all. Where there are no clocks, or no words, nothing is lit. */
    var tLit = null;
    var subLit = null;
    var ticking = 0;
    var loopSpan = null;

    var unlightFilm = function () {
      if (tLit) tLit.classList.remove("voiced-now");
      if (subLit) subLit.classList.remove("voiced-now");
      tLit = null;
      subLit = null;
    };
    var wordNow = function (now) {
      var id = lineAt(now);
      if (!id) return null;
      var rows = heard().own[id];
      if (!rows) return null;
      for (var i = 0; i < rows.length; i++) {
        if (now >= rows[i][2] && now < rows[i][3]) return { id: id, from: rows[i][0], to: rows[i][1] };
      }
      return null;
    };
    var inCopy = function (from, to) {
      if (!subNow) return null;
      var words = subNow.querySelectorAll(".w[data-bare]");
      for (var i = 0; i < words.length; i++) {
        var bare = words[i].getAttribute("data-bare").split(",");
        if (parseInt(bare[0], 10) < to && parseInt(bare[1], 10) > from) return words[i];
      }
      return null;
    };
    var tick = function () {
      ticking = 0;
      if (!filmUp() || audio.paused) {
        unlightFilm();
        return;
      }
      var now = audio.currentTime;
      // Loop this line: back to its start the moment the voice leaves it.
      if (loopSpan && (now >= loopSpan[1] || now < loopSpan[0] - 0.5)) {
        try {
          audio.currentTime = loopSpan[0];
        } catch (e) {}
        now = loopSpan[0];
      }
      var at = wordNow(now);
      var t = at ? wordAt(at.id, at.from, at.to) : null;
      var c = at && subFor && subFor.getAttribute("data-id") === at.id ? inCopy(at.from, at.to) : null;
      if (t !== tLit) {
        if (tLit) tLit.classList.remove("voiced-now");
        tLit = t;
        if (tLit) tLit.classList.add("voiced-now");
      }
      if (c !== subLit) {
        if (subLit) subLit.classList.remove("voiced-now");
        subLit = c;
        if (subLit) subLit.classList.add("voiced-now");
      }
      ticking = requestAnimationFrame(tick);
    };
    var startTicking = function () {
      if (!ticking && window.requestAnimationFrame) ticking = requestAnimationFrame(tick);
    };

    /* --- the row under the picture ---------------------------------------------- */

    filmPaint = function (now, length) {
      if (filmFill) filmFill.style.inlineSize = (now / length) * 100 + "%";
      if (filmAt) filmAt.textContent = clocked(now);
      if (filmLength) filmLength.textContent = clocked(length);
      if (filmLengthSaid && !filmLengthSaid.textContent) filmLengthSaid.textContent = clocked(length);
      // The faint band on the line is the line being said — or held, while it loops.
      var id = loopSpan ? null : lineAt(now);
      var band = loopSpan || (id && spans[id]) || null;
      if (filmLine) {
        filmLine.hidden = !band;
        if (band) {
          filmLine.style.insetInlineStart = (band[0] / length) * 100 + "%";
          filmLine.style.inlineSize = (Math.max(0, band[1] - band[0]) / length) * 100 + "%";
        }
      }
    };

    var loop = function (on) {
      if (on) {
        var id = lineAt(audio.currentTime);
        loopSpan = id && spans[id] ? spans[id].slice() : null;
        if (!loopSpan) on = false;
      } else {
        loopSpan = null;
      }
      if (loopKey) loopKey.setAttribute("aria-pressed", on ? "true" : "false");
      say(on ? S.t("reader.film.looping", "Looping this line.") : S.t("reader.film.not-looping", "Not looping."));
      if (on && !audio.paused) startTicking();
      paint();
    };
    if (loopKey) {
      loopKey.addEventListener("click", function () {
        loop(loopKey.getAttribute("aria-pressed") !== "true");
      });
    }


    /* --- how it stands ------------------------------------------------------------ */

    /* The transcript follows the voice. Beside, the line being said is kept in the top
       third of the column, so what is coming is under it; on a phone, in the top third of
       what the picture leaves. Only when it has left that stretch: a reader who scrolled
       to look back is not pulled away for every line, only once the voice has gone on
       past what they can see. Under a large picture with the transcript put away there
       is nothing to scroll. */
    var stepped = false;
    filmFollow = function (pair) {
      if (!filmUp()) return false;
      if (view === "theatre" && !panel && wideFilm.matches) return true;
      // Only a voice that is running, or a line stepped to: a reader paging through the
      // transcript with nothing playing keeps their place when the picture comes up.
      if (audio.paused && !stepped) return true;
      var top = 0;
      var bar = document.querySelector(".bar");
      if (bar) top = bar.getBoundingClientRect().bottom;
      // On a phone, and in Theatre with the transcript open under the picture, the
      // picture stays at the top and the transcript scrolls under it.
      if (!wideFilm.matches || panel) top = Math.max(top, videoBox.getBoundingClientRect().bottom);
      var room = window.innerHeight - top;
      var box = pair.getBoundingClientRect();
      if (box.top >= top + 8 && box.bottom <= top + room * 0.72) return true;
      var to = window.scrollY + box.top - top - room * 0.22;
      window.scrollTo({ top: Math.max(0, to), behavior: behaviour() });
      return true;
    };

    var place = function (held) {
      var up = filmUp();
      // A phone has one way of standing, the picture above its transcript, whatever was
      // chosen on a wide window; the choice waits for the window to be wide again.
      var standing = wideFilm.matches ? view : "beside";
      body.classList.toggle("film", up);
      body.classList.toggle("film-beside", up && standing === "beside");
      body.classList.toggle("film-theatre", up && standing === "theatre");
      body.classList.toggle("film-panel", up && standing === "theatre" && panel);
      viewKeys.forEach(function (key) {
        key.setAttribute("aria-pressed", key.getAttribute("data-film-view") === view ? "true" : "false");
      });
      if (transcriptKey) transcriptKey.setAttribute("aria-pressed", panel ? "true" : "false");
      if (panelHead) panelHead.hidden = !(up && standing === "theatre" && panel);
      atEnd();
      fit();
      relay(held);
      look();
      watchList();
      // The line being said, brought into what can now be seen of the transcript.
      var now = marked || (subFor && subFor.parentNode ? subFor : null);
      if (up && now && filmFollow) filmFollow(now);
    };

    var setView = function (name, chosen) {
      if (VIEWS.indexOf(name) < 0) return;
      view = name;
      panel = false;
      if (chosen) {
        try {
          targumKeep(VIEW_STORE, view);
        } catch (e) {}
        say(view === "theatre" ? S.t("reader.film.theatre-said", "Theatre.") : S.t("reader.film.beside-said", "Beside."));
      }
      place();
    };
    var setPanel = function (open) {
      if (view !== "theatre") return;
      panel = !!open;
      place();
      say(panel ? S.t("reader.film.transcript-said", "Transcript.") : S.t("reader.film.transcript-shut", "Transcript closed."));
    };
    viewKeys.forEach(function (key) {
      key.addEventListener("click", function () {
        setView(key.getAttribute("data-film-view"), true);
      });
    });
    if (transcriptKey) {
      transcriptKey.addEventListener("click", function () {
        setPanel(!panel);
      });
    }
    if (panelShut) {
      panelShut.addEventListener("click", function () {
        setPanel(false);
        if (transcriptKey && transcriptKey.getClientRects().length) transcriptKey.focus({ preventScroll: true });
      });
    }

    // The word list opening or closing changes the room the picture has.
    var listWatched = false;
    var watchList = function () {
      if (listWatched || !window.MutationObserver) return;
      listWatched = true;
      var was = body.classList.contains("list-open");
      new MutationObserver(function () {
        var now = body.classList.contains("list-open");
        if (now === was) return;
        was = now;
        fit();
      }).observe(body, { attributes: true, attributeFilter: ["class"] });
    };
    if (wideFilm.addEventListener) wideFilm.addEventListener("change", place);
    else if (wideFilm.addListener) wideFilm.addListener(place);
    var fitting = false;
    window.addEventListener("resize", function () {
      if (fitting) return;
      fitting = true;
      requestAnimationFrame(function () {
        fitting = false;
        fit();
      });
    });
    videoEl.addEventListener("loadedmetadata", fit);

    /* The picture up, or put away. Putting it away never stops the sound — the page
       becomes the audio reader, and the strip comes up for a voice that is still
       talking — and bringing it back puts the strip away again. */
    var showVideo = function (out, chosen) {
      if (videoDead) out = false;
      var held = !out && !videoBox.hidden && !wideFilm.matches ? lineUnder() : null;
      videoBox.hidden = !out;
      flips.forEach(function (button) {
        button.setAttribute("aria-pressed", out ? "true" : "false");
      });
      if (chosen) {
        try {
          if (out) targumForget(VIDEO_STORE);
          else targumKeep(VIDEO_STORE, "1");
        } catch (e) {}
      }
      if (player) {
        if (out && !player.hidden) {
          player.hidden = true;
          body.classList.remove("has-player");
        } else if (!out && !audio.paused && window.TargumPlayer && window.TargumPlayer.show) {
          window.TargumPlayer.show();
        }
      }
      if (!out) {
        unlightFilm();
        quiet(false);
      }
      place(held);
      // On a phone the strip is the foot bar and stands once the picture is put away
      // (#434): after the page is placed, and placed again once the bar has its room.
      if (
        player &&
        player.hidden &&
        !out &&
        window.TargumPlayer &&
        window.TargumPlayer.footBar &&
        window.TargumPlayer.footBar()
      ) {
        window.TargumPlayer.show();
        place(held);
      }
    };

    flips.forEach(function (button) {
      button.addEventListener("click", function () {
        showVideo(videoBox.hidden, true);
      });
    });

    /* --- Theatre's picture, made smaller --------------------------------------- */

    /* David, 2026-10-07 (design.md §12): "drag on the video and make it smaller or
       bigger, giving more room to text" — and "I like the theater default though". So
       the grip on the picture's lower edge scales it down from the size `fit` gives it
       and back, never past it, and keeps its shape: the picture and its row are one
       column, so the line under them takes whatever height the picture gives up, and
       the transcript panel beside it does not move. The lower edge rather than a
       corner because the picture stands in the middle and can only trade height; a
       corner would promise a free shape it cannot have. A share of the full size is
       kept, not pixels, so a window resized keeps the reader's proportion; the full
       size is never written. Nothing is animated — the picture follows the hand. */
    var setSize = function (share, keep) {
      var least = fullW ? sizeFloor(fullW) / fullW : SIZE_LEAST;
      size = Math.max(least, Math.min(1, share));
      if (size > 0.995) size = 1;
      fit();
      if (keep) {
        try {
          if (size === 1) targumForget(SIZE_STORE);
          else targumKeep(SIZE_STORE, String(Math.round(size * 1000) / 1000));
        } catch (e) {}
      }
    };
    // What depends on the picture's height once it has settled: the reader's own
    // layout, and the line being said brought back into view where the transcript shows.
    var sizeSettled = function () {
      relay();
      var now = marked || (subFor && subFor.parentNode ? subFor : null);
      if (now && filmFollow) filmFollow(now);
    };
    if (sizeGrip) {
      var grab = null;
      var lastTap = 0;
      sizeGrip.addEventListener("pointerdown", function (event) {
        if (event.button > 0 || !filmUp() || view !== "theatre" || !wideFilm.matches) return;
        event.preventDefault();
        var frame = sizeGrip.parentNode.getBoundingClientRect();
        grab = { id: event.pointerId, y: event.clientY, h: frame.height, moved: false };
        try {
          sizeGrip.setPointerCapture(event.pointerId);
        } catch (e) {}
        sizeGrip.classList.add("held");
        body.classList.add("film-sizing");
      });
      sizeGrip.addEventListener("pointermove", function (event) {
        if (!grab || event.pointerId !== grab.id || !fullW) return;
        var dy = event.clientY - grab.y;
        if (Math.abs(dy) > 3) grab.moved = true;
        if (!grab.moved) return;
        // The edge follows the pointer: the new height, in the film's shape, as a share.
        var high = Math.max(1, grab.h + dy);
        setSize((high * shape()) / fullW, false);
      });
      var letGo = function (event) {
        if (!grab || event.pointerId !== grab.id) return;
        var moved = grab.moved;
        grab = null;
        try {
          sizeGrip.releasePointerCapture(event.pointerId);
        } catch (e) {}
        sizeGrip.classList.remove("held");
        body.classList.remove("film-sizing");
        if (moved) {
          setSize(size, true);
          lastTap = 0;
        } else if (event.type === "pointerup") {
          // Two presses in a row put it back to the default: a double click, and a
          // double tap, which a touch screen does not always send as one.
          var at = Date.now();
          if (at - lastTap < 400) {
            lastTap = 0;
            setSize(1, true);
          } else {
            lastTap = at;
          }
        }
        sizeSettled();
      };
      sizeGrip.addEventListener("pointerup", letGo);
      sizeGrip.addEventListener("pointercancel", letGo);
      // A press on the grip is not a press on the picture under it.
      sizeGrip.addEventListener("click", function (event) {
        event.stopPropagation();
      });
      sizeGrip.addEventListener("keydown", function (event) {
        if (event.metaKey || event.ctrlKey || event.altKey) return;
        var to = null;
        // ↑ takes the edge up, so the picture smaller; ↓ down. A tenth a press.
        if (event.key === "ArrowUp" || event.key === "ArrowLeft") to = size - 0.1;
        else if (event.key === "ArrowDown" || event.key === "ArrowRight") to = size + 0.1;
        else if (event.key === "PageUp") to = size - 0.25;
        else if (event.key === "PageDown") to = size + 0.25;
        else if (event.key === "Home") to = 0;
        else if (event.key === "End") to = 1;
        if (to === null) return;
        event.preventDefault();
        event.stopPropagation();
        setSize(to, true);
        sizeSettled();
      });
    }

    /* --- Beside, the line between the picture and the transcript ------------------ */

    /* David, 2026-10-08 (design.md §12): Theatre's picture could be made smaller, and
       Beside should give the same say — a bigger picture, or more room for the text. The
       line between them is taken and moved; the picture keeps its shape and fills the
       column it is given, up to what the window's height allows. A share of the room is
       kept, not pixels, on this device; a double press puts the layout's own place back
       and forgets it. Nothing is animated — the line follows the hand. */
    var setSplit = function (col, keep) {
      if (col === null) split = 0;
      else if (splitAt.room) {
        var at = Math.max(splitAt.least, Math.min(splitAt.most, col));
        split = at / splitAt.room;
      }
      fit();
      if (keep) {
        try {
          if (!split) targumForget(SPLIT_STORE);
          else targumKeep(SPLIT_STORE, String(Math.round(split * 1000) / 1000));
        } catch (e) {}
      }
    };
    if (splitEl) {
      var splitHold = null;
      var splitTap = 0;
      splitEl.addEventListener("pointerdown", function (event) {
        if (event.button > 0 || !filmUp() || view !== "beside" || !wideFilm.matches) return;
        event.preventDefault();
        splitHold = { id: event.pointerId, x: event.clientX, col: splitAt.col, moved: false };
        try {
          splitEl.setPointerCapture(event.pointerId);
        } catch (e) {}
        splitEl.classList.add("held");
        body.classList.add("film-splitting");
      });
      splitEl.addEventListener("pointermove", function (event) {
        if (!splitHold || event.pointerId !== splitHold.id) return;
        var dx = event.clientX - splitHold.x;
        if (Math.abs(dx) > 3) splitHold.moved = true;
        if (!splitHold.moved) return;
        setSplit(splitHold.col + dx, false);
      });
      var release = function (event) {
        if (!splitHold || event.pointerId !== splitHold.id) return;
        var moved = splitHold.moved;
        splitHold = null;
        try {
          splitEl.releasePointerCapture(event.pointerId);
        } catch (e) {}
        splitEl.classList.remove("held");
        body.classList.remove("film-splitting");
        if (moved) {
          setSplit(splitAt.col, true);
          splitTap = 0;
        } else if (event.type === "pointerup") {
          var now = Date.now();
          if (now - splitTap < 400) {
            splitTap = 0;
            setSplit(null, true);
          } else {
            splitTap = now;
          }
        }
        sizeSettled();
      };
      splitEl.addEventListener("pointerup", release);
      splitEl.addEventListener("pointercancel", release);
      splitEl.addEventListener("keydown", function (event) {
        if (event.metaKey || event.ctrlKey || event.altKey) return;
        var step = splitAt.room * 0.05;
        var to;
        // → moves the line right: a bigger picture. A twentieth of the room a press.
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") to = splitAt.col - step;
        else if (event.key === "ArrowRight" || event.key === "ArrowDown") to = splitAt.col + step;
        else if (event.key === "Home") to = splitAt.least;
        else if (event.key === "End") to = splitAt.most;
        else return;
        event.preventDefault();
        event.stopPropagation();
        setSplit(to, true);
        sizeSettled();
      });
    }

    /* --- C: it steps back while it plays ---------------------------------------- */

    /* Playing, the bar and the controls fade, and what is left is the picture, a hairline
       of where the voice is and the line being said. A pause brings them back, and so
       does the pointer moving, a touch or a key; and nothing steps back while a panel or
       a word's card is out, or while the keyboard is in the controls. `prefers-reduced-
       motion` keeps the change and drops the fade. */
    var QUIET_AFTER = 2500;
    var quietWait = 0;
    var keyboardIn = function () {
      var on = document.activeElement;
      if (!on || on === document.body) return false;
      if (!videoBox.contains(on) && !(on.closest && on.closest(".bar"))) return false;
      try {
        return on.matches(":focus-visible");
      } catch (e) {
        return true;
      }
    };
    var mayQuiet = function () {
      if (!filmUp() || audio.paused) return false;
      if (body.classList.contains("pop-open")) return false;
      if (card && !card.hidden) return false;
      if (filmCtl && filmCtl.matches(":hover")) return false;
      if (body.classList.contains("film-sizing")) return false;
      return !keyboardIn();
    };
    var quiet = function (on) {
      body.classList.toggle("film-quiet", !!on && mayQuiet());
    };
    var settle = function () {
      clearTimeout(quietWait);
      quietWait = setTimeout(function () {
        quietWait = 0;
        quiet(true);
      }, QUIET_AFTER);
    };
    var wake = function () {
      if (body.classList.contains("film-quiet")) body.classList.remove("film-quiet");
      clearTimeout(quietWait);
      quietWait = 0;
      if (filmUp() && !audio.paused) settle();
    };
    ["pointermove", "pointerdown", "keydown", "touchstart", "wheel"].forEach(function (name) {
      document.addEventListener(name, wake, { passive: true, capture: true });
    });
    document.addEventListener("targum:pop", wake);

    /* --- a word, tapped -------------------------------------------------------- */

    /* A word pressed while the voice runs stops it there: the card opens over the paused
       frame, and the frame dims under it in Theatre (C). Captured, so the voice has
       stopped before the card is drawn. */
    document.addEventListener(
      "click",
      function (event) {
        if (!filmUp() || audio.paused) return;
        var word = event.target && event.target.closest ? event.target.closest(".w") : null;
        if (!word) return;
        if (!(sub && sub.contains(word)) && !word.closest("#reader")) return;
        toggleScene();
      },
      true
    );
    if (card && window.MutationObserver) {
      new MutationObserver(function () {
        var up = !card.hidden && filmUp();
        body.classList.toggle("film-card", up);
        if (up) wake();
        // The word stays marked in the line while its card is up, and lets go with it.
        if (!up && subNow) {
          Array.prototype.forEach.call(subNow.querySelectorAll(".w.looked-up"), function (w) {
            w.classList.remove("looked-up");
          });
        }
      }).observe(card, { attributes: true, attributeFilter: ["hidden"] });
    }

    /* --- the keys ------------------------------------------------------------- */

    /* A line at a time, from the keyboard: ↑ the line before, ↓ the line after, from
       wherever the voice is, playing or not. In Theatre with the transcript put away
       there are no words to walk, so ← → step lines as well, the way the page reads. */
    var stepLine = function (by) {
      if (!order.length) return;
      var id = lineAt(audio.currentTime);
      var i = 0;
      for (var n = 0; n < order.length; n++) {
        if (order[n].id === id) {
          i = n;
          break;
        }
      }
      // Back from the middle of a line is the top of that line, as a player's back is.
      if (by < 0 && audio.currentTime - order[i].start > 1.5) by = 0;
      var to = order[Math.max(0, Math.min(order.length - 1, i + by))];
      if (loopSpan) loopSpan = spans[to.id] ? spans[to.id].slice() : loopSpan;
      stepped = true;
      seek(to.start + 0.01);
      if (!following) mark(to.id);
      stepped = false;
      var pair = document.querySelector('#reader .pair[data-id="' + CSS.escape(to.id) + '"]');
      say(plainOf(pair));
    };
    document.addEventListener(
      "keydown",
      function (event) {
        if (!filmUp() || event.metaKey || event.ctrlKey || event.altKey) return;
        var on = document.activeElement;
        if (on && /^(INPUT|SELECT|TEXTAREA)$/.test(on.tagName)) return;
        // The size grip is a separator and its arrows are its own (2026-10-07).
        if (on && (on.isContentEditable || on.getAttribute("role") === "slider" || on === sizeGrip || on === splitEl)) return;
        if (body.classList.contains("pop-open")) return;
        var by = 0;
        if (event.key === "ArrowUp") by = -1;
        else if (event.key === "ArrowDown") by = 1;
        else if (view === "theatre" && !panel && wideFilm.matches && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
          var rtl = (document.documentElement.getAttribute("dir") || "ltr") === "rtl";
          by = (event.key === "ArrowLeft") === rtl ? 1 : -1;
        }
        if (!by) return;
        event.preventDefault();
        event.stopPropagation();
        stepLine(by);
      },
      true
    );

    /* The end of the part (2026-10-07). The door to the next one comes up under the
       picture (`atEnd`); nothing plays it, because the next part is a text of its own and
       opens waiting for its press. On the last part of a recording there is no next one,
       and the end is the foot of the transcript — Done, and after it the library's
       offer, as at the end of any text — so in Theatre the transcript opens to it, as a
       playlist's end opens it to its card (#422). Not inside a playlist, whose own end
       does that. */
    videoEl.addEventListener("ended", function () {
      playedOut = running;
      running = false;
      atEnd();
      var pages = document.querySelector(".pager[data-by-part]");
      if (!pages || pages.querySelector("[data-next]") || inList) return;
      if (view === "theatre" && !panel && wideFilm.matches) setPanel(true);
      var foot = document.getElementById("foot");
      // Into what the window shows of the text: under the picture where it stands at the
      // top over the transcript (Theatre, and a phone), under the bar where it is beside.
      if (!foot) return;
      var bar = document.querySelector(".bar");
      var under = bar ? bar.getBoundingClientRect().bottom : 0;
      if (panel || !wideFilm.matches) under = Math.max(under, videoBox.getBoundingClientRect().bottom);
      var room = window.innerHeight - under;
      var box = foot.getBoundingClientRect();
      var to = window.scrollY + box.top - under - Math.max(0, (room - box.height) / 2);
      window.scrollTo({ top: Math.max(0, to), behavior: behaviour() });
    });
    videoEl.addEventListener("seeking", function () {
      playedOut = false;
      if (videoEl.paused) running = false;
      atEnd();
    });

    /* The voice starts and stops. */
    audio.addEventListener("play", function () {
      playedOut = false;
      running = true;
      startTicking();
      if (filmUp()) settle();
      atEnd();
    });
    audio.addEventListener("pause", function () {
      unlightFilm();
      wake();
    });

    /* A film that has already shown a picture and then errors did travel: what broke is
       the stream under it, not the file (David, 2026-10-12: "it cuts off after the first
       few lines randomly and we go into full screen text", in every way of standing). So
       it is loaded again and put back at the second it was on, playing if it was, and
       only a film that keeps failing — three times in a minute — or one that never gave
       a picture is given up on below. Each time, which error the browser reported goes
       to the record as a control (`film-error:<code>:<again|gone>:<message>`) and to the
       console, because the cause has not been caught on a machine of ours yet and the
       next one should say what it was. */
    var filmShown = videoEl.readyState >= 2;
    var filmFailures = [];
    videoEl.addEventListener("loadeddata", function () {
      filmShown = true;
    });
    var reportFilm = function (outcome) {
      var fault = videoEl.error;
      var code = fault ? fault.code : 0;
      var message = fault && fault.message ? String(fault.message) : "";
      var said = message.replace(/[^A-Za-z0-9_.:-]+/g, "_").slice(0, 28);
      try {
        if (window.TargumEvents && window.TargumEvents.note) {
          window.TargumEvents.note({
            kind: "control",
            control: ("film-error:" + code + ":" + outcome + (said ? ":" + said : "")).slice(0, 60),
          });
        }
      } catch (e) {}
      try {
        if (window.console && console.warn) {
          console.warn("[targum] film error", code, message, outcome, "at", videoEl.currentTime);
        }
      } catch (e) {}
    };
    var filmAgain = function () {
      var now = Date.now();
      filmFailures = filmFailures.filter(function (at) {
        return now - at < 60000;
      });
      if (!filmShown || filmFailures.length >= 3) return false;
      filmFailures.push(now);
      var at = videoEl.currentTime || 0;
      var going = running || !videoEl.paused;
      reportFilm("again");
      var back = function () {
        videoEl.removeEventListener("loadedmetadata", back);
        try {
          videoEl.currentTime = at;
        } catch (e) {}
        if (going) {
          var playing = videoEl.play();
          if (playing && playing.catch) playing.catch(function () {});
        }
      };
      videoEl.addEventListener("loadedmetadata", back);
      videoEl.load();
      return true;
    };

    /* The sidecar did not travel — a reader folder copied without its video/, or a
       page opened somewhere the file is not. The player swaps to the inlined audio
       and the page becomes exactly the audio reader, toggle and all. */
    videoEl.addEventListener("error", function () {
      if (videoDead) return;
      if (filmAgain()) return;
      reportFilm("gone");
      videoDead = true;
      var rate = nearestRate(audio.playbackRate);
      halt();
      showVideo(false, false);
      flips.forEach(function (button) {
        var group = button.closest(".group");
        if (group) group.hidden = true;
        else button.hidden = true;
      });
      audio = new Audio(addressOf(speech.audio));
      wire(audio);
      setRate(rate, false);
      // The place was restored onto the element that has just been thrown away. The
      // inlined audio is the same recording at the same seconds, so it is restored
      // again rather than lost with the sidecar.
      whenKnown(resume);
    });

    /* How the `v` key reaches the switch, and how the playlist's end reaches the
       transcript. */
    window.TargumVideo = {
      hide: function () {
        showVideo(false, false);
      },
      turn: function () {
        if (!filmUp()) return false;
        setView(view === "beside" ? "theatre" : "beside", true);
        return true;
      },
      view: function () {
        return filmUp() ? view : "";
      },
      transcript: function (open) {
        if (filmUp() && view === "theatre") setPanel(open);
      },
    };

    /* On unless this reader put it away here before, and standing the way they last
       chose on any text. Not `chosen`, so opening a text never writes a preference the
       reader did not express. Inside a playlist the picture is the item (design.md §12,
       2026-09-23): a reader who swiped into a reel came to watch it, so it opens in
       Theatre whatever was kept, and writes nothing; `go` is the swipe that brought them
       here, which was the press. Opened any other way, nothing plays. */
    var putAway = false;
    try {
      putAway = localStorage.getItem(VIDEO_STORE) === "1";
      var keptView = localStorage.getItem(VIEW_STORE);
      if (VIEWS.indexOf(keptView) >= 0) view = keptView;
      var keptSize = parseFloat(localStorage.getItem(SIZE_STORE) || "");
      if (keptSize > 0 && keptSize < 1) size = keptSize;
    } catch (e) {}
    var inList = false;
    var swipedHere = false;
    try {
      var listed = new URLSearchParams(location.search);
      inList = /^https?:$/.test(location.protocol) && /^\d+$/.test(listed.get("list") || "");
      swipedHere = inList && listed.get("go") === "1";
    } catch (e) {}
    if (inList) view = "theatre";
    panel = false;
    showVideo(inList || !putAway, false);
    drawSub(lineAt(audio.currentTime || 0));
    subId = subFor ? subFor.getAttribute("data-id") : null;
    whenKnown(function () {
      paint();
    });
    if (swipedHere) toggleScene();
  }

  /* The video's home, opened at the line in front of the reader. The sidecar stays
     the instrument — it plays on a plane and this does not — and the link is a credit
     that happens to be useful: YouTube's own page, at the second this sentence starts.
     The address is fixed in the markup and only the time is decided, at the click
     rather than on every tick, because an address that changes forty times a minute
     is one nobody can copy. The spans are into this part's own cut, which begins
     `offset` seconds into the whole video; the two are added here. Two links since
     #422: the row in ⋯, and "Watch on YouTube" under the picture. */
  var homeOffset = Number(speech.offset) || 0;
  var homeAt = function () {
    // The line being spoken, then the one line playing, then the sentence in front
    // of the reader — and failing all three, the whole video from its start.
    var pair = marked || (playing && playing.closest(".pair"));
    if (!pair) {
      var reader = window.TargumReader;
      pair = reader && reader.inFront ? reader.inFront() : null;
    }
    var id = pair ? pair.getAttribute("data-id") : "";
    if (id && spans[id]) return homeOffset + spans[id][0];
    return audio.currentTime ? homeOffset + audio.currentTime : 0;
  };
  // Only an address that takes a time is given one. The "at" mark is YouTube's, and an
  // Instagram reel with `&t=` on the end is an address Instagram does not answer.
  Array.prototype.forEach.call(document.querySelectorAll("[data-home=at]"), function (home) {
    var homeBase = home.getAttribute("href");
    home.addEventListener("click", function () {
      var seconds = Math.max(0, Math.floor(homeAt()));
      home.href = homeBase + (seconds ? "&t=" + seconds + "s" : "");
    });
  });

  /* Leaving the page mid-sentence should not leave a voice talking into an empty room;
     a phone locked in a pocket is not an empty room (design.md §12, 2026-10-09). A whole
     recording that is playing goes on behind a locked screen or another app; a line
     pressed on its own stops. Handed to a playlist's next item, it is not this page's to
     stop. */
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden || released) return;
    if (following && !audio.paused) return;
    halt();
  });
  window.addEventListener("pagehide", function () {
    if (!released) halt();
  });
})();
};

/* After `reader.js` since 2026-10-21 (targum-internal#409): where the reader has already
   run and found no player, it left word to run this on arrival. Where the reader runs
   later (it waits on the store), it finds `targumPlayer` and runs it itself. Once,
   either way. */
if (window.targumPlayerWanted) {
  window.targumPlayerWanted = false;
  targumPlayer();
}
