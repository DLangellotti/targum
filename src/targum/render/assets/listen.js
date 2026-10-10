/* Listening: the page put away, the picture, the line being said and the player under
 * them (design.md §12, "Listening is a view of its own", 2026-10-10; boards ListenPhone,
 * ListenWordPhone and ListenLock).
 *
 * The view is drawn over the reader and drives the reader's own recording through
 * `TargumPlayer`. It plays nothing, seeks nothing and keeps no place of its own: the
 * strip, the bar's play and this view are three faces on one player, so they cannot
 * disagree, and where the voice stopped is the place Continue already reads.
 *
 * What it adds is what someone listening on the move needs and a reader at a desk does
 * not: steps of a line rather than a word, a line held on a loop, the queue of what plays
 * next, and the lock screen, which says the line being said and steps a line too. And,
 * with Play in order on, a part that ends with the screen locked hands the player to the
 * next part's recording, the way a playlist hands it between items (`list.js`).
 *
 * Off a disk this still works on the page it is in, and fetches nothing: no picture
 * from `/thumb/` (the letter stands), and no next part is asked for.
 */
(function () {
  "use strict";

  /* --- arithmetic, with no page (tests/js/listen.js) ----------------------------- */

  /* The line the voice has begun last, held through the silence after it, or the first
     before anything is said: the same rule as the line under a picture. */
  function heldIndex(order, seconds) {
    var held = 0;
    for (var i = 0; i < order.length; i++) {
      if (seconds >= order[i].start) held = i;
      else break;
    }
    return held;
  }

  function around(order, seconds) {
    if (!order || !order.length) return { before: null, now: null, after: null, index: -1 };
    var i = heldIndex(order, seconds);
    return { before: order[i - 1] || null, now: order[i], after: order[i + 1] || null, index: i };
  }

  /* Where a step of a line lands, or null where there is no line that way. Back from the
     middle of a line is the top of that line, as a player's back is; back at its top is
     the line before. */
  function lineStep(order, seconds, by) {
    if (!order || !order.length) return null;
    var i = heldIndex(order, seconds);
    if (by < 0 && seconds - order[i].start > 1.5) by = 0;
    var to = i + by;
    if (to < 0) to = 0;
    if (to >= order.length) return null;
    return order[to].start;
  }

  /* Where a held line sends the voice back to: its start, once the voice has left it. */
  function looped(span, now) {
    if (!span) return null;
    return now >= span[1] || now < span[0] - 0.5 ? span[0] : null;
  }

  function partsAhead(section, sections) {
    var ahead = [];
    for (var n = section + 1; n <= sections; n++) ahead.push(n);
    return ahead;
  }

  // The file a part is written to (`builder.Section.filename`).
  function partFile(n) {
    return "sec-" + ("000" + n).slice(-4) + ".html";
  }

  function clocked(seconds) {
    var whole = Math.max(0, Math.floor(seconds || 0));
    return Math.floor(whole / 60) + ":" + ("0" + (whole % 60)).slice(-2);
  }

  function ordered(table) {
    return Object.keys(table || {}).map(function (id) {
      return { id: id, start: table[id][0], end: table[id][1] };
    });
  }

  window.TargumListen = {
    around: around,
    lineStep: lineStep,
    looped: looped,
    partsAhead: partsAhead,
    partFile: partFile,
    clocked: clocked,
    ordered: ordered,
  };

  if (typeof document === "undefined") return;
  // After the reader, whose whole file waits for the durable store (`durable.js`): the
  // player this drives does not exist until it has run.
  if (window.TargumStore && window.TargumStore.ready) window.TargumStore.ready(start);
  else start();

  function start() {
    var view = document.getElementById("listen-view");
    var player = window.TargumPlayer;
    if (!view || !player || !player.element) return;

    /* --- the page ------------------------------------------------------------------ */

    var body = document.body;
    var strings = window.TargumStrings;
    function t(key, english, fill) {
      if (strings && strings.t) return strings.t(key, english, fill);
      return english.replace(/\{(\w+)\}/g, function (all, name) {
        return fill && name in fill ? String(fill[name]) : all;
      });
    }
    function tn(key, n, one, other) {
      if (strings && strings.tn) return strings.tn(key, n, one, other);
      return (n === 1 ? one : other).replace("{n}", String(n));
    }
    var asked;
    try {
      asked = new URLSearchParams(location.search);
    } catch (e) {
      asked = { get: function () { return null; } };
    }
    var inList = /^\d+$/.test(asked.get("list") || "");
    var served = /^https?:$/.test(location.protocol);
    var key = asked.get("k") || "";
    function keyed(path) {
      if (!key) return path;
      return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
    }
    var section = Number(view.getAttribute("data-section")) || 1;
    var sections = Number(view.getAttribute("data-sections")) || 1;
    var byPart = view.hasAttribute("data-by-part");
    var reduced = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

    function el() {
      return player.element();
    }
    function one(selector) {
      return view.querySelector(selector);
    }
    function all(selector) {
      return Array.prototype.slice.call(document.querySelectorAll(selector));
    }
    function say(words) {
      var reader = window.TargumReader;
      if (reader && reader.say) reader.say(words);
    }

    var openers = all("[data-listen-view]");
    var down = one(".lv-down");
    var more = one(".lv-more");
    var lines = one(".lv-lines");
    var before = one(".lv-before");
    var now = one(".lv-now");
    var tr = one(".lv-tr");
    var after = one(".lv-after");
    var paused = one(".lv-paused");
    var saved = one(".lv-saved");
    var handedNote = one(".lv-handed");
    var handedSaid = one(".lv-handed-said");
    var handedOpen = one(".lv-handed-open");
    var at = one(".lv-at");
    var length = one(".lv-length");
    var track = one(".lv-track");
    var fill = one(".lv-fill");
    var plays = Array.prototype.slice.call(view.querySelectorAll(".lv-play"));
    var back = one(".lv-back");
    var on = one(".lv-on");
    var rate = one(".lv-rate");
    var loopKey = one(".lv-loop");
    var nextKey = one(".lv-next");
    var nextName = one(".lv-next-name");
    var queueOpen = one(".lv-queue-open");
    var queue = one(".lv-queue");
    var queueCount = one(".lv-qcount");
    var queueList = one(".lv-qlist");
    var queueEmpty = one(".lv-qempty");
    var order = one(".lv-order");
    var nowFacts = one(".lv-qnow-facts");
    var miniLine = one(".lv-mini-line");
    var card = document.getElementById("gloss-card");
    var titleText = (one(".lv-title") || {}).textContent || "";
    var whereText = ((one(".lv-where") || {}).textContent || "").replace(/\s+/g, " ").trim();

    /* --- what is playing ----------------------------------------------------------- */

    // After a part ended with the screen locked: the part the player now plays.
    var handed = null;

    function currentOrder() {
      return handed ? handed.order : player.lines() || [];
    }

    function pairOf(id) {
      if (!id || handed) return null;
      return document.querySelector('#reader .pair[data-id="' + CSS.escape(id) + '"]');
    }

    /* The form of the line the reader has on show: pointed, plain or unaccented. */
    function shownForm(pair) {
      var forms = pair.querySelectorAll(".src");
      var shown = forms[0] || null;
      for (var i = 0; i < forms.length; i++) {
        if (getComputedStyle(forms[i]).display !== "none") {
          shown = forms[i];
          break;
        }
      }
      // A pointed cell with nothing in it is no line to say: the bare one is.
      if (shown && !shown.textContent.replace(/[⁦-⁩\s]/g, "")) {
        shown = pair.querySelector(".src.plain") || shown;
      }
      return shown;
    }

    function plainOf(pair) {
      var form = pair ? shownForm(pair) : null;
      return form ? form.textContent.replace(/[⁦-⁩]/g, "").replace(/\s+/g, " ").trim() : "";
    }

    var drawnId = null;
    var lit = null;

    /* The line being said, copied in with its words, so a word in it is a word on the page:
       the card answers to `.film-pair` as it does under a picture. */
    function copyLine(pair) {
      now.textContent = "";
      lit = null;
      if (!pair) return;
      var form = shownForm(pair);
      var holder = document.createElement("div");
      holder.className = "film-pair lv-pair";
      holder.setAttribute("data-id", pair.getAttribute("data-id"));
      if (form) {
        var copy = form.cloneNode(true);
        copy.removeAttribute("id");
        Array.prototype.forEach.call(copy.querySelectorAll(".w"), function (w) {
          w.classList.remove("voiced-now", "looked-up", "queued");
          w.removeAttribute("tabindex");
          w.removeAttribute("aria-describedby");
        });
        holder.appendChild(copy);
      }
      now.appendChild(holder);
    }

    function drawLines(force) {
      var lineup = currentOrder();
      var shown = !handed && lineup.length > 0;
      lines.hidden = !shown;
      if (!shown) {
        drawnId = null;
        return;
      }
      var spot = around(lineup, el().currentTime);
      var id = spot.now ? spot.now.id : null;
      if (!force && id === drawnId) return;
      drawnId = id;
      var pair = pairOf(id);
      before.textContent = plainOf(pairOf(spot.before && spot.before.id));
      after.textContent = plainOf(pairOf(spot.after && spot.after.id));
      copyLine(pair);
      if (tr) {
        var said = pair ? pair.querySelector(".tr") : null;
        tr.textContent = said ? said.textContent.replace(/[⁦-⁩]/g, "").trim() : "";
      }
      var line = plainOf(pair);
      if (miniLine) miniLine.textContent = line;
      lockLine(line);
    }

    /* The word being said: read off the word clocks every frame, which `timeupdate` is too
       coarse for. Where there are no clocks nothing is lit. */
    function lightWord(seconds) {
      var word = null;
      if (!handed && drawnId) {
        var rows = (player.clocks() || {})[drawnId] || [];
        for (var i = 0; i < rows.length; i++) {
          if (seconds >= rows[i][2] && seconds < rows[i][3]) {
            var words = now.querySelectorAll(".w[data-bare]");
            for (var j = 0; j < words.length; j++) {
              var bare = words[j].getAttribute("data-bare").split(",");
              if (parseInt(bare[0], 10) < rows[i][1] && parseInt(bare[1], 10) > rows[i][0]) {
                word = words[j];
                break;
              }
            }
            break;
          }
        }
      }
      if (word === lit) return;
      if (lit) lit.classList.remove("voiced-now");
      lit = word;
      if (lit) lit.classList.add("voiced-now");
    }

    function span() {
      var whole = el().duration;
      return whole && isFinite(whole) ? whole : 0;
    }

    function paintClock() {
      var whole = span();
      var here = el().currentTime || 0;
      at.textContent = clocked(here);
      length.textContent = whole ? clocked(whole) : "";
      fill.style.inlineSize = whole ? (here / whole) * 100 + "%" : "0%";
      track.setAttribute("aria-valuemax", String(Math.floor(whole)));
      track.setAttribute("aria-valuenow", String(Math.floor(here)));
      track.setAttribute("aria-valuetext", clocked(here) + " / " + clocked(whole));
      if (nowFacts) {
        var part = handed ? handed.where : whereText;
        nowFacts.textContent = whole ? part + " · " + clocked(here) + " / " + clocked(whole) : part;
      }
    }

    function paintPlay() {
      var going = !el().paused;
      plays.forEach(function (press) {
        press.setAttribute("aria-pressed", going ? "true" : "false");
        var named = press.getAttribute(going ? "data-pause" : "data-play");
        press.setAttribute("aria-label", named);
        press.setAttribute("title", named);
      });
      view.classList.toggle("is-playing", going);
    }

    var frame = 0;
    function tick() {
      frame = 0;
      if (view.hidden) return;
      var element = el();
      var here = element.currentTime;
      if (loopSpan && !element.paused) {
        var to = looped(loopSpan, here);
        if (to !== null) {
          seekTo(to);
          here = to;
        }
      }
      drawLines(false);
      paintClock();
      lightWord(here);
      if (!element.paused && window.requestAnimationFrame) frame = window.requestAnimationFrame(tick);
    }
    function startTick() {
      if (!frame && window.requestAnimationFrame) frame = window.requestAnimationFrame(tick);
      else if (!window.requestAnimationFrame) tick();
    }

    function seekTo(seconds) {
      if (handed) {
        try {
          el().currentTime = Math.max(0, seconds);
        } catch (e) {}
      } else {
        player.seek(seconds);
      }
    }

    /* --- the presses ----------------------------------------------------------------- */

    function step(by) {
      var lineup = currentOrder();
      var here = el().currentTime;
      var to;
      if (lineup.length) {
        to = lineStep(lineup, here, by);
        if (to === null) return;
        to += 0.01;
        if (loopSpan) {
          var held = around(lineup, to).now;
          loopSpan = held ? [held.start, held.end] : null;
        }
      } else {
        // A recording read straight through has no lines: a step is fifteen seconds.
        to = here + by * 15;
      }
      seekTo(to);
      drawLines(true);
      paintClock();
      lightWord(el().currentTime);
    }

    function labelSteps() {
      var byLine = currentOrder().length > 0;
      var backSaid = byLine
        ? t("reader.listen.back-one-line", "Back one line")
        : t("reader.listen.back-fifteen", "Back 15 seconds");
      var onSaid = byLine
        ? t("reader.listen.forward-one-line", "Forward one line")
        : t("reader.listen.forward-fifteen", "Forward 15 seconds");
      back.setAttribute("aria-label", backSaid);
      back.setAttribute("title", backSaid);
      on.setAttribute("aria-label", onSaid);
      on.setAttribute("title", onSaid);
      loopKey.hidden = !byLine;
    }

    plays.forEach(function (press) {
      press.addEventListener("click", function () {
        player.toggle();
      });
    });
    back.addEventListener("click", function () {
      step(-1);
    });
    on.addEventListener("click", function () {
      step(1);
    });
    rate.addEventListener("click", function () {
      if (player.nextRate) player.nextRate();
    });

    /* Loop this line: held until it is pressed again, and moved with a step. */
    var loopSpan = null;
    loopKey.addEventListener("click", function () {
      var holding = loopKey.getAttribute("aria-pressed") !== "true";
      loopSpan = null;
      if (holding) {
        var held = around(currentOrder(), el().currentTime).now;
        if (held) loopSpan = [held.start, held.end];
        else holding = false;
      }
      loopKey.setAttribute("aria-pressed", holding ? "true" : "false");
      say(holding ? t("reader.film.looping", "Looping this line.") : t("reader.film.not-looping", "Not looping."));
      if (holding && !el().paused) startTick();
    });

    /* The track: pressed or dragged to a second, and the arrows five seconds either way. */
    (function () {
      var dragging = false;
      function along(event) {
        var box = track.getBoundingClientRect();
        if (!box.width) return 0;
        return Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
      }
      track.addEventListener("pointerdown", function (event) {
        if (!span()) return;
        dragging = true;
        if (track.setPointerCapture) {
          try {
            track.setPointerCapture(event.pointerId);
          } catch (e) {}
        }
        event.preventDefault();
        seekTo(along(event) * span());
        tick();
      });
      track.addEventListener("pointermove", function (event) {
        if (!dragging) return;
        event.preventDefault();
        seekTo(along(event) * span());
        tick();
      });
      ["pointerup", "pointercancel"].forEach(function (name) {
        track.addEventListener(name, function () {
          dragging = false;
        });
      });
      track.addEventListener("keydown", function (event) {
        if (event.metaKey || event.ctrlKey || event.altKey) return;
        var to = null;
        var here = el().currentTime;
        if (event.key === "ArrowLeft") to = here - 5;
        else if (event.key === "ArrowRight") to = here + 5;
        else if (event.key === "Home") to = 0;
        else if (event.key === "End") to = span();
        if (to === null) return;
        event.preventDefault();
        event.stopPropagation();
        seekTo(Math.min(span(), Math.max(0, to)));
        tick();
      });
    })();

    /* --- open and put away ------------------------------------------------------------ */

    var STORE = "targum:listen-view";
    var openedFrom = null;

    function remember(open) {
      try {
        if (open) sessionStorage.setItem(STORE, "1");
        else sessionStorage.removeItem(STORE);
      } catch (e) {}
    }

    function shutMenus() {
      // ⋯ and Aa put themselves away on a press elsewhere; a row of ⋯ pressed is not
      // elsewhere, so the menu is shut here, the way its own × shuts it.
      var menu = document.querySelector(".bar-more.open");
      var press = document.querySelector(".bar-tools [data-more]");
      if (menu && press) press.click();
    }

    function show(open, keep) {
      if (open === !view.hidden) return;
      view.hidden = !open;
      body.classList.toggle("listening", open);
      openers.forEach(function (press) {
        press.setAttribute("aria-expanded", open ? "true" : "false");
      });
      if (keep) remember(open);
      if (open) {
        labelSteps();
        drawLines(true);
        drawHanded();
        paintClock();
        paintPlay();
        drawNext();
        startTick();
        if (down) down.focus({ preventScroll: true });
      } else {
        showQueue(false);
        if (frame && window.cancelAnimationFrame) window.cancelAnimationFrame(frame);
        frame = 0;
        if (openedFrom && openedFrom.getClientRects().length) openedFrom.focus({ preventScroll: true });
        var reader = window.TargumReader;
        if (reader && reader.relayout) reader.relayout();
      }
    }

    openers.forEach(function (press) {
      press.addEventListener("click", function () {
        openedFrom = press.closest(".bar-more") ? document.querySelector(".bar-tools [data-more]") : press;
        shutMenus();
        show(true, true);
      });
    });
    down.addEventListener("click", function () {
      show(false, true);
    });
    // ⋯ in the view is the reader's own ⋯, which stands over it while it is open.
    more.addEventListener("click", function () {
      var press = document.querySelector(".bar-tools [data-more]");
      if (press) press.click();
    });
    document.addEventListener("keydown", function (event) {
      if (view.hidden || event.key !== "Escape") return;
      if (card && !card.hidden) return;
      if (document.querySelector(".bar-more.open, .bar-pop.open")) return;
      event.preventDefault();
      if (!queue.hidden) {
        showQueue(false);
        if (queueOpen) queueOpen.focus({ preventScroll: true });
        return;
      }
      show(false, true);
    });

    /* --- Up next ------------------------------------------------------------------------ */

    var PLAY_ON = "targum:play-on";
    function inOrder() {
      var list = window.TargumList;
      if (inList && list && list.playOn) return list.playOn();
      try {
        return localStorage.getItem(PLAY_ON) === "1";
      } catch (e) {
        return false;
      }
    }
    function chooseOrder(yes) {
      var list = window.TargumList;
      if (list && list.choosePlayOn) list.choosePlayOn(yes);
      else {
        try {
          if (yes) localStorage.setItem(PLAY_ON, "1");
          else localStorage.removeItem(PLAY_ON);
        } catch (e) {}
      }
      order.setAttribute("aria-checked", yes ? "true" : "false");
    }
    order.addEventListener("click", function () {
      chooseOrder(order.getAttribute("aria-checked") !== "true");
    });

    function partWord(n) {
      return byPart
        ? t("reader.listen.part", "Part {n}", { n: n })
        : t("reader.listen.chapter", "Chapter {n}", { n: n });
    }
    function partOfWord(n) {
      return byPart
        ? t("reader.film.part", "Part {n} of {count}", { n: n, count: sections })
        : t("reader.listen.chapter-of", "Chapter {n} of {count}", { n: n, count: sections });
    }

    /* Where a part is opened from here: listening, with the serve key carried along. */
    function partAddress(n, seconds) {
      var join = "?listen=1" + (seconds > 0 ? "&t=" + Math.floor(seconds) : "");
      return partFile(n) + join + (key ? "&k=" + encodeURIComponent(key) : "");
    }

    /* What comes next: the playlist's next items inside one, this text's next parts
       outside it. One row each, a press that opens it listening. */
    function upNext() {
      if (inList) {
        var list = window.TargumList;
        var asked = list && list.queue ? list.queue() : null;
        return {
          group: asked ? t("reader.listen.from-playlist", "From your playlist · {name}", { name: asked.name }) : "",
          rows: asked ? asked.rows : [],
        };
      }
      return {
        group: t("reader.listen.from-text", "From {title}", { title: titleText }),
        rows: partsAhead(handed ? handed.n : section, sections).map(function (n) {
          return { title: partWord(n), facts: "", thumb: coverCopy("lv-qcover"), href: partAddress(n, 0) };
        }),
      };
    }

    function drawNext() {
      var next = upNext();
      var first = next.rows[0];
      nextKey.hidden = !first;
      if (first) {
        nextName.textContent = inList ? first.title : partOfWord((handed ? handed.n : section) + 1);
      }
    }

    function drawQueue() {
      var next = upNext();
      queueList.textContent = "";
      queueCount.textContent = next.rows.length
        ? tn("reader.listen.queued", next.rows.length, "{n} queued", "{n} queued")
        : "";
      queueEmpty.hidden = next.rows.length > 0;
      order.setAttribute("aria-checked", inOrder() ? "true" : "false");
      if (!next.rows.length) return;
      var head = document.createElement("p");
      head.className = "lv-grp";
      head.textContent = next.group;
      queueList.appendChild(head);
      next.rows.forEach(function (row) {
        var link = document.createElement("a");
        link.className = "lv-qrow";
        link.href = row.href;
        if (row.thumb) link.appendChild(row.thumb);
        var text = document.createElement("span");
        text.className = "lv-qtext";
        var name = document.createElement("bdi");
        name.className = "lv-qname";
        name.setAttribute("dir", "auto");
        name.textContent = row.title;
        text.appendChild(name);
        if (row.facts) {
          var facts = document.createElement("span");
          facts.className = "lv-qfacts";
          facts.textContent = row.facts;
          text.appendChild(facts);
        }
        link.appendChild(text);
        queueList.appendChild(link);
      });
    }

    function showQueue(open) {
      if (open === !queue.hidden) return;
      queue.hidden = !open;
      view.classList.toggle("queue-open", open);
      queueOpen.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        drawQueue();
        var first = queue.querySelector(".lv-qdown");
        if (first) first.focus({ preventScroll: true });
      }
    }
    queueOpen.addEventListener("click", function () {
      showQueue(queue.hidden);
    });
    nextKey.addEventListener("click", function () {
      showQueue(true);
    });
    Array.prototype.forEach.call(view.querySelectorAll(".lv-qdown, .lv-qdone"), function (press) {
      press.addEventListener("click", function () {
        showQueue(false);
        queueOpen.focus({ preventScroll: true });
      });
    });
    document.addEventListener("targum:list-ready", function () {
      drawNext();
      if (!queue.hidden) drawQueue();
    });

    /* --- the picture ------------------------------------------------------------------- */

    /* The text's picture from this box, where the page is served from it; its letter where
       it is not, so a reader off a disk fetches nothing. */
    var picture = null;
    var named = served ? /^\/reader\/([^/]+)\/reader\//.exec(location.pathname) : null;
    if (named) {
      var image = new Image();
      image.alt = "";
      image.onload = function () {
        picture = image;
        Array.prototype.forEach.call(document.querySelectorAll(".lv-cover, .lv-qcover.is-text"), placePicture);
      };
      image.src = keyed("/thumb/" + named[1] + "?drawn=1");
    }
    Array.prototype.forEach.call(view.querySelectorAll(".lv-qrow.is-now .lv-qcover, .lv-mini-cover"), function (box) {
      box.classList.add("is-text");
    });
    function placePicture(box) {
      if (!picture || box.querySelector("img")) return;
      var copy = picture.cloneNode();
      var letter = box.querySelector(".lv-letter");
      if (letter) letter.remove();
      box.appendChild(copy);
    }
    function coverCopy(className) {
      var box = document.createElement("span");
      box.className = className + " is-text";
      box.setAttribute("aria-hidden", "true");
      var letter = view.querySelector(".lv-cover .lv-letter");
      if (letter) box.appendChild(letter.cloneNode(true));
      placePicture(box);
      return box;
    }

    // "Saved", where this device keeps the text (`offline.js`), asked of its index only.
    var offline = window.TargumOffline;
    if (saved && offline && offline.ready && served) {
      offline
        .ready()
        .then(function () {
          saved.hidden = !offline.savedText(location.href);
        })
        .catch(function () {});
    }

    /* --- a word, tapped ---------------------------------------------------------------- */

    /* The voice stops on the word and the card opens over the view (board ListenWordPhone).
       Closing it, by its × or by Keep listening, plays on from the second it stopped: the
       word said from the card moves the voice, and this puts it back. Captured, so the voice
       has stopped before the card is drawn. */
    var resumeAt = null;
    document.addEventListener(
      "click",
      function (event) {
        if (view.hidden) return;
        var word = event.target && event.target.closest ? event.target.closest(".w") : null;
        if (!word || !now.contains(word)) return;
        Array.prototype.forEach.call(now.querySelectorAll(".w.looked-up"), function (w) {
          w.classList.remove("looked-up");
        });
        if (!el().paused && resumeAt === null) {
          resumeAt = el().currentTime;
          player.pause();
        }
        body.classList.add("listen-carded");
        if (paused) paused.hidden = false;
      },
      true
    );

    function keepListening() {
      var shut = card && card.querySelector(".card-x");
      if (shut) shut.click();
      else if (card) card.hidden = true;
    }

    function dressCard() {
      if (!card || card.hidden || !body.classList.contains("listen-carded")) return;
      var shut = card.querySelector(".card-x");
      if (shut && resumeAt !== null) {
        var keepSaid = t("reader.listen.close-and-keep-listening", "Close and keep listening");
        shut.setAttribute("aria-label", keepSaid);
        shut.setAttribute("title", keepSaid);
      }
      if (card.querySelector(".card-keep")) return;
      var keep = document.createElement("button");
      keep.type = "button";
      keep.className = "card-keep";
      var NS = "http://www.w3.org/2000/svg";
      var drawn = document.createElementNS(NS, "svg");
      drawn.setAttribute("viewBox", "0 0 14 14");
      drawn.setAttribute("aria-hidden", "true");
      drawn.setAttribute("focusable", "false");
      var shape = document.createElementNS(NS, "path");
      shape.setAttribute("d", "M3.5 2.2v9.6L11.5 7z");
      drawn.appendChild(shape);
      keep.appendChild(drawn);
      keep.appendChild(document.createTextNode(t("reader.listen.keep-listening", "Keep listening")));
      keep.addEventListener("click", function (event) {
        event.stopPropagation();
        keepListening();
      });
      card.appendChild(keep);
    }

    function cardGone() {
      if (!body.classList.contains("listen-carded")) return;
      body.classList.remove("listen-carded");
      Array.prototype.forEach.call(now.querySelectorAll(".w.looked-up"), function (w) {
        w.classList.remove("looked-up");
      });
      var from = resumeAt;
      resumeAt = null;
      if (from === null) {
        if (paused) paused.hidden = !el().paused;
        return;
      }
      if (paused) paused.hidden = true;
      seekTo(from);
      player.play();
    }

    if (card && window.MutationObserver) {
      new MutationObserver(function () {
        if (card.hidden) cardGone();
        else dressCard();
      }).observe(card, { attributes: true, attributeFilter: ["hidden"], childList: true });
    }

    /* --- the lock screen ------------------------------------------------------------------ */

    /* Outside a playlist (inside one, `list.js` says the playlist's title and place): the
       text and its part, the line being said under it, and a line either way. */
    var session = !inList && typeof navigator !== "undefined" ? navigator.mediaSession : null;
    var partSaid = view.getAttribute("data-part") || "";
    var lockTitle = titleText + (partSaid ? " · " + partSaid : "");
    var lockSaid = "";
    function lockLine(line) {
      if (!session || typeof MediaMetadata === "undefined") return;
      if (line === lockSaid && session.metadata) return;
      lockSaid = line;
      try {
        session.metadata = new MediaMetadata({
          title: handed ? titleText + " · " + handed.where : lockTitle,
          artist: line || "",
          album: "targum",
          artwork: named ? [{ src: new URL(keyed("/thumb/" + named[1] + "?drawn=1"), location.href).href, sizes: "512x512" }] : [],
        });
      } catch (e) {}
    }
    function lockPlace() {
      if (!session || !session.setPositionState) return;
      var whole = span();
      if (!whole) return;
      try {
        session.setPositionState({
          duration: whole,
          playbackRate: el().playbackRate || 1,
          position: Math.min(whole, Math.max(0, el().currentTime)),
        });
      } catch (e) {}
    }
    if (session) {
      var handle = function (action, run) {
        try {
          session.setActionHandler(action, run);
        } catch (e) {}
      };
      handle("play", function () {
        if (el().paused) player.toggle();
      });
      handle("pause", function () {
        if (handed) el().pause();
        else player.pause();
      });
      handle("previoustrack", function () {
        step(-1);
      });
      handle("nexttrack", function () {
        step(1);
      });
      handle("seekto", function (details) {
        if (details && typeof details.seekTime === "number") seekTo(details.seekTime);
        lockPlace();
      });
    }

    /* --- the voice moving ----------------------------------------------------------------- */

    var wasFollowing = false;
    function wire(element) {
      element.addEventListener("play", function () {
        paintPlay();
        if (paused && !body.classList.contains("listen-carded")) paused.hidden = true;
        if (session) {
          try {
            session.playbackState = "playing";
          } catch (e) {}
        }
        lockSaid = null;
        var held = around(currentOrder(), element.currentTime).now;
        lockLine(held && !handed ? plainOf(pairOf(held.id)) : "");
        startTick();
        ahead();
      });
      element.addEventListener("pause", function () {
        paintPlay();
        if (session) {
          try {
            session.playbackState = "paused";
          } catch (e) {}
        }
        tick();
      });
      element.addEventListener("timeupdate", function () {
        if (!handed && !element.paused) wasFollowing = !!(player.following && player.following());
        if (view.hidden) {
          // Closed, the lock screen still follows the line.
          var held = around(currentOrder(), element.currentTime).now;
          if (held && !handed) lockLine(plainOf(pairOf(held.id)));
          else if (handed) lockLine("");
        } else if (element.paused) {
          tick();
        }
        lockPlace();
      });
      element.addEventListener("ratechange", lockPlace);
      element.addEventListener("loadedmetadata", function () {
        paintClock();
        lockPlace();
      });
      element.addEventListener("ended", ended);
    }
    wire(el());

    /* --- one part to the next --------------------------------------------------------------- */

    /* A part's recording, read off its own page, as `list.js` reads an item's: the voice and
       its lines, asked for ahead so it is in hand the moment this one ends. Only where the
       page is served; a reader off a disk asks for nothing. */
    var heard = {};
    function recordingOf(n) {
      if (!served || !window.fetch || typeof DOMParser === "undefined") return Promise.resolve(null);
      if (heard[n]) return heard[n];
      var page = new URL(keyed(partFile(n)), location.href);
      heard[n] = fetch(page.href, { credentials: "same-origin" })
        .then(function (answer) {
          return answer.ok ? answer.text() : "";
        })
        .then(function (html) {
          if (!html) return null;
          var doc = new DOMParser().parseFromString(html, "text/html");
          var node = doc.getElementById("targum-data");
          var data = node ? JSON.parse(node.textContent || "{}") : {};
          var speech = data && data.speech;
          if (!speech || !speech.audio) return null;
          var src = speech.audio;
          if (!/^data:/.test(src)) {
            var beside = new URL(src, page.href);
            beside.search = page.search;
            src = beside.href;
          }
          return { src: src, order: ordered(speech.spans) };
        })
        .catch(function () {
          return null;
        });
      return heard[n];
    }

    function ahead() {
      if (inList || !inOrder()) return;
      var next = (handed ? handed.n : section) + 1;
      if (next <= sections) recordingOf(next);
    }

    function openNext(n) {
      location.href = partAddress(n, 0);
    }

    function handOff(n) {
      return recordingOf(n).then(function (found) {
        if (!found) return;
        var element = el();
        if (!handed) {
          var released = player.release ? player.release() : null;
          if (!released) return;
          element = released;
        }
        var rate = element.playbackRate || 1;
        handed = { n: n, order: found.order, where: partOfWord(n) };
        element.src = found.src;
        element.playbackRate = rate;
        element.defaultPlaybackRate = rate;
        var started = element.play();
        if (started && started.catch) started.catch(function () {});
        lockSaid = null;
        lockLine("");
        drawHanded();
        drawLines(true);
        drawNext();
        labelSteps();
        ahead();
      });
    }

    function drawHanded() {
      var list = document.getElementById("list-now");
      if (handed) {
        handedNote.hidden = false;
        handedSaid.textContent = t("reader.listen.now-playing-part", "Now playing {part}.", { part: handed.where });
        handedOpen.hidden = false;
        return;
      }
      // A playlist's next item, handed over by `list.js`: its own line says what and where.
      if (player.handed && player.handed() && list) {
        handedNote.hidden = false;
        var said = list.cloneNode(true);
        Array.prototype.forEach.call(said.querySelectorAll("a"), function (link) {
          link.remove();
        });
        handedSaid.textContent = said.textContent.trim();
        handedOpen.hidden = !list.querySelector("a");
        return;
      }
      handedNote.hidden = true;
    }
    handedOpen.addEventListener("click", function (event) {
      if (handed) {
        handedOpen.href = partAddress(handed.n, el().currentTime);
        return;
      }
      var link = document.querySelector("#list-now a");
      if (link) {
        event.preventDefault();
        link.click();
      }
    });

    function ended() {
      if (handed) {
        if (handed.n < sections && inOrder()) handOff(handed.n + 1);
        return;
      }
      var listening = wasFollowing;
      wasFollowing = false;
      if (inList || !listening || !inOrder() || section >= sections) return;
      var locked = document.hidden;
      if (!locked && view.hidden) return;
      // Heard to its end: finished, without marking, as a swipe finishes it.
      var reader = window.TargumReader;
      if (reader && reader.press) reader.press(false);
      if (locked && served) handOff(section + 1);
      else openNext(section + 1);
    }

    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && !view.hidden) {
        drawHanded();
        tick();
      }
    });

    /* --- arriving ------------------------------------------------------------------------- */

    labelSteps();
    paintPlay();
    var wantsView = false;
    try {
      wantsView = sessionStorage.getItem(STORE) === "1";
    } catch (e) {}
    if (wantsView) show(true, false);
    /* Opened from Up next or by Play in order, outside a playlist (inside one, `list.js`
       starts it): where the voice had got to, and on from there. */
    if (!inList && (asked.get("listen") === "1" || Number(asked.get("t") || 0) > 0)) {
      var seconds = Number(asked.get("t") || 0);
      var arrive = function () {
        setTimeout(function () {
          if (seconds > 0) player.seek(seconds);
          if (asked.get("listen") === "1") player.play();
        }, 0);
      };
      if (span()) arrive();
      else el().addEventListener("loadedmetadata", arrive, { once: true });
    }
  }
})();
