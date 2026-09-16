/* The front door's four moving parts (targum-internal#69, 2026-09-16).

   The vowel switches, the reading modes, the box's Start and the video that plays
   itself. Nothing here is required to read the page: with JavaScript off the words, the
   verses and the waitlist's form all still work, and the demos sit still.

   The dish in the video frame is drawn here rather than in the stylesheet because it is
   a picture, not an interface: its colours are a tomato and an egg, and the palette in
   `design.md` §4 is for the parts of the page a person operates.
*/
(function () {
  "use strict";
  var MARKS = /[\u0591-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]/g;
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- the box: nothing happens until the person presses Start ---- */
  var boxStart = document.getElementById("boxStart");
  boxStart.addEventListener("click", function () {
    document.getElementById("boxFoot").innerHTML =
      "<span class=\"when tnum\">Working on it\u2026 ready in about 4 minutes</span>";
  });

  /* ---- the words ---- */
  var W = {
    samim: { he: "שָׂמִים", state: "known", head: "שָׂם", pos: "verb", sense: "to put, to place", facts: [["Here", "<span class=\"he\">שָׂמִים</span> · pa’al, present · put"], ["Root", "<span class=\"he\">שׂ־י־ם</span>"], ["Which Hebrew", "Biblical and modern"], ["Met before", "Genesis 2:8 · <span class=\"scripture\">וַיָּ֣שֶׂם</span> · “and there He put”"]] },
    shemen: { he: "שֶׁמֶן", state: "known", head: "שֶׁמֶן", pos: "noun, masculine", sense: "oil", facts: [["Plural", "<span class=\"he\">שְׁמָנִים</span>"], ["Which Hebrew", "Biblical and modern"], ["Met before", "Genesis 28:18 · <span class=\"scripture\">שֶׁ֖מֶן</span> · “and poured oil”"]] },
    bamachvat: { he: "בַּמַּחֲבַת", state: "learning", head: "מַחֲבַת", pos: "noun, feminine", sense: "frying pan", facts: [["Here", "<span class=\"he\">בַּ</span> + <span class=\"he\">מַּחֲבַת</span> · in the pan"], ["Which Hebrew", "Biblical and modern"], ["Met before", "Leviticus 2:5 · <span class=\"scripture\">הַֽמַּחֲבַ֖ת</span> · “baked on a griddle”"]] },
    umechakim: { he: "וּמְחַכִּים", state: "known", head: "חִכָּה", pos: "verb", sense: "to wait", binyan: [["pi’el", "חִכָּה", true]], facts: [["Here", "<span class=\"he\">וּ</span> + <span class=\"he\">מְחַכִּים</span> · and wait"], ["Root", "<span class=\"he\">ח־כ־ה</span>"]] },
    sheyitchamem: { he: "שֶׁיִּתְחַמֵּם", state: "new", head: "הִתְחַמֵּם", pos: "verb", sense: "to heat up, to warm up", binyan: [["pi’el", "חִמֵּם"], ["hitpa’el", "הִתְחַמֵּם", true]], facts: [["Here", "<span class=\"he\">שֶׁ</span> + <span class=\"he\">יִּתְחַמֵּם</span> · hitpa’el, future, it · for it to heat up"], ["Root", "<span class=\"he\">ח־מ־ם</span>"]] },
    mosifim: { he: "מוֹסִיפִים", state: "learning", head: "הוֹסִיף", pos: "verb", sense: "to add", binyan: [["hif’il", "הוֹסִיף", true], ["nif’al", "נוֹסַף"]], facts: [["Here", "<span class=\"he\">מוֹסִיפִים</span> · hif’il, present · add"], ["Root", "<span class=\"he\">י־ס־ף</span>"], ["Which Hebrew", "Biblical and modern"]] },
    batzal: { he: "בָּצָל", state: "known", head: "בָּצָל", pos: "noun, masculine", sense: "onion", facts: [["Plural", "<span class=\"he\">בְּצָלִים</span>"], ["Which Hebrew", "Biblical and modern"], ["Met before", "Numbers 11:5 · <span class=\"scripture\">הַבְּצָלִ֖ים</span> · “and the onions”"]] },
    pilpel: { he: "פִּלְפֵּל", state: "known", head: "פִּלְפֵּל", pos: "noun, masculine", sense: "pepper", facts: [["Plural", "<span class=\"he\">פִּלְפְּלִים</span>"], ["Which Hebrew", "Rabbinic and modern"]] },
    agvaniyot: { he: "וְעַגְבָנִיּוֹת", state: "learning", head: "עַגְבָנִיָּה", pos: "noun, feminine", sense: "tomato", facts: [["Here", "<span class=\"he\">וְ</span> + <span class=\"he\">עַגְבָנִיּוֹת</span> · and tomatoes"], ["Which Hebrew", "Modern"], ["From", "<span class=\"he\">עָגַב</span>, to desire. The tomato was once the love apple."]] },
    umevashlim: { he: "וּמְבַשְּׁלִים", state: "known", head: "בִּשֵּׁל", pos: "verb", sense: "to cook", binyan: [["pi’el", "בִּשֵּׁל", true], ["pu’al", "בֻּשַּׁל"]], facts: [["Here", "<span class=\"he\">וּ</span> + <span class=\"he\">מְבַשְּׁלִים</span> · and cook"], ["Root", "<span class=\"he\">ב־שׁ־ל</span>"], ["Which Hebrew", "Biblical and modern"]] },
    al: { he: "עַל", state: "known", head: "עַל", pos: "preposition", sense: "on, over", facts: [["Here", "<span class=\"he\">עַל אֵשׁ</span> · over a heat, on the stove"]] },
    esh: { he: "אֵשׁ", state: "known", head: "אֵשׁ", pos: "noun, feminine", sense: "fire", facts: [["Here", "<span class=\"he\">אֵשׁ קְטַנָּה</span> · a low heat"], ["Which Hebrew", "Biblical and modern"]] },
    ktana: { he: "קְטַנָּה", state: "known", head: "קָטָן", pos: "adjective", sense: "small", facts: [["Here", "feminine, to match <span class=\"he\">אֵשׁ</span>"]] },
    achshav: { he: "עַכְשָׁיו", state: "known", head: "עַכְשָׁיו", pos: "adverb", sense: "now", facts: [["Which Hebrew", "Rabbinic and modern"]] },
    shovrim: { he: "שׁוֹבְרִים", state: "learning", head: "שָׁבַר", pos: "verb", sense: "to break", binyan: [["pa’al", "שָׁבַר", true], ["nif’al", "נִשְׁבַּר"], ["pi’el", "שִׁבֵּר"]], facts: [["Here", "<span class=\"he\">שׁוֹבְרִים</span> · pa’al, present · crack"], ["Root", "<span class=\"he\">שׁ־ב־ר</span>"], ["Which Hebrew", "Biblical and modern"], ["Met before", "Exodus 34:1 · <span class=\"scripture\">שִׁבַּֽרְתָּ</span> · “which thou didst break”"]] },
    et: { he: "אֶת", state: "known", head: "אֶת", pos: "particle", sense: "marks a definite object", facts: [["Here", "before <span class=\"he\">הַבֵּיצִים</span>, which is definite"]] },
    habeitzim: { he: "הַבֵּיצִים", state: "known", head: "בֵּיצָה", pos: "noun, feminine", sense: "egg", facts: [["Here", "<span class=\"he\">הַ</span> + <span class=\"he\">בֵּיצִים</span> · the eggs"], ["Which Hebrew", "Biblical and modern"], ["Met before", "Deuteronomy 22:6 · <span class=\"scripture\">בֵיצִ֔ים</span> · “or eggs”"]] },
    yeshirot: { he: "יְשִׁירוֹת", state: "new", head: "יְשִׁירוֹת", pos: "adverb", sense: "directly, straight", facts: [["Root", "<span class=\"he\">י־שׁ־ר</span>"], ["From", "<span class=\"he\">יָשָׁר</span>, straight"]] },
    letoch: { he: "לְתוֹךְ", state: "known", head: "תּוֹךְ", pos: "preposition", sense: "into", facts: [["Here", "<span class=\"he\">לְ</span> + <span class=\"he\">תוֹךְ</span> · into"]] },
    harotev: { he: "הָרֹטֶב", state: "learning", head: "רֹטֶב", pos: "noun, masculine", sense: "sauce", facts: [["Here", "<span class=\"he\">הָ</span> + <span class=\"he\">רֹטֶב</span> · the sauce"], ["Plural", "<span class=\"he\">רְטָבִים</span>"], ["From", "<span class=\"he\">ר־ט־ב</span>, moist"]] },
    mechasim: { he: "מְכַסִּים", state: "learning", head: "כִּסָּה", pos: "verb", sense: "to cover", binyan: [["pi’el", "כִּסָּה", true], ["hitpa’el", "הִתְכַּסָּה"]], facts: [["Here", "<span class=\"he\">מְכַסִּים</span> · pi’el, present · cover"], ["Root", "<span class=\"he\">כ־ס־ה</span>"], ["Which Hebrew", "Biblical and modern"]] },
    veacharei: { he: "וְאַחֲרֵי", state: "known", head: "אַחֲרֵי", pos: "preposition", sense: "after", facts: [["Here", "<span class=\"he\">וְ</span> + <span class=\"he\">אַחֲרֵי</span> · and after"]] },
    chamesh: { he: "חָמֵשׁ", state: "known", head: "חָמֵשׁ", pos: "number", sense: "five", facts: [["Here", "feminine, to match <span class=\"he\">דַּקּוֹת</span>"]] },
    dakot: { he: "דַּקּוֹת", state: "known", head: "דַּקָּה", pos: "noun, feminine", sense: "minute", facts: [["Plural", "<span class=\"he\">דַּקּוֹת</span>"], ["From", "<span class=\"he\">דַּק</span>, thin"], ["Met before", "Genesis 41:3 · <span class=\"scripture\">וְדַקּ֣וֹת</span> · “lean-fleshed”"]] },
    ze: { he: "זֶה", state: "known", head: "זֶה", pos: "pronoun", sense: "this, it", facts: [["Here", "it"]] },
    muchan: { he: "מוּכָן", state: "known", head: "מוּכָן", pos: "adjective", sense: "ready", facts: [["Root", "<span class=\"he\">כ־ו־ן</span>"], ["From", "<span class=\"he\">הֵכִין</span>, to prepare"]] }
  };
  var LINES = [
    { start: 0, end: 4.4, words: ["samim", "shemen", "bamachvat", "umechakim", "sheyitchamem"], en: "Put oil in the pan and wait for it to heat up.", stamp: "2:10" },
    { start: 4.4, end: 9.0, words: ["mosifim", "batzal", "pilpel", "agvaniyot", "umevashlim", "al", "esh", "ktana"], en: "Add onion, pepper and tomatoes, and cook over a low heat.", stamp: "2:14", comma: [1] },
    { start: 9.0, end: 13.6, words: ["achshav", "shovrim", "et", "habeitzim", "yeshirot", "letoch", "harotev"], en: "Now crack the eggs straight into the sauce.", stamp: "2:19" },
    { start: 13.6, end: 18, words: ["mechasim", "veacharei", "chamesh", "dakot", "ze", "muchan"], en: "Cover it, and after five minutes it’s ready.", stamp: "2:23", comma: [0] }
  ];
  var DURATION = 18, BASE = 130;
  var RATES = [0.5, 0.75, 1];
  var vowels = true, openId = "shovrim", t = 10.4, playing = false, rateIx = 2;

  function plain(s) { return vowels ? s : s.replace(MARKS, ""); }
  function lineAt(time) { for (var i = 0; i < LINES.length; i++) if (time >= LINES[i].start && time < LINES[i].end) return i; return -1; }
  function comma(line, i) { return line.comma && line.comma.indexOf(i) >= 0 ? "," : ""; }
  function hebrewOf(line) { return line.words.map(function (id, i) { return plain(W[id].he) + comma(line, i); }).join(" ") + "."; }

  var linesEl = document.getElementById("lines");
  function drawLines() {
    var now = lineAt(t);
    linesEl.textContent = "";
    LINES.forEach(function (line, n) {
      var pair = document.createElement("div");
      pair.className = "pair" + (n === now ? " now" : "");
      var at = document.createElement("button");
      at.type = "button"; at.className = "at tnum"; at.textContent = line.stamp; at.dataset.line = n;
      at.setAttribute("aria-label", "Play from " + line.stamp);
      var he = document.createElement("p");
      he.className = "line-he";
      line.words.forEach(function (id, i) {
        var w = W[id], span = document.createElement("span");
        span.className = "w " + w.state + (id === openId ? " open" : "");
        span.textContent = plain(w.he);
        span.tabIndex = 0; span.setAttribute("role", "button"); span.dataset.id = id;
        he.appendChild(span);
        he.appendChild(document.createTextNode(comma(line, i) + (i === line.words.length - 1 ? "." : " ")));
      });
      var en = document.createElement("p");
      en.className = "line-en"; en.textContent = line.en;
      pair.appendChild(at); pair.appendChild(he); pair.appendChild(en);
      linesEl.appendChild(pair);
    });
  }

  function drawCard() {
    var w = W[openId];
    var html = "<div class=\"card-head\"><span class=\"label\">Word card</span><p class=\"card-word\">" + w.head + "</p>" +
      "<p class=\"card-sense\">" + w.sense + " <span class=\"pos\">· " + w.pos + "</span></p></div>";
    if (w.binyan) html += "<div class=\"binyanim\">" + w.binyan.map(function (b) { return "<span class=\"" + (b[2] ? "here" : "") + "\">" + b[0] + " <span class=\"he\">" + b[1] + "</span></span>"; }).join("") + "</div>";
    html += "<dl class=\"facts-list\">" + w.facts.map(function (f) { return "<dt>" + f[0] + "</dt><dd>" + f[1] + "</dd>"; }).join("") + "</dl>";
    html += "<div class=\"card-actions\"><button class=\"btn tonal small\" type=\"button\" data-set=\"learning\" aria-pressed=\"" + (w.state === "learning") + "\">Getting there</button>" +
      "<button class=\"btn tonal small\" type=\"button\" data-set=\"known\" aria-pressed=\"" + (w.state === "known") + "\">Known</button>" +
      "<button class=\"btn ghost small\" type=\"button\">Ask</button></div>";
    document.getElementById("card").innerHTML = html;
  }

  linesEl.addEventListener("click", function (e) {
    var at = e.target.closest(".at");
    if (at) { seek(LINES[+at.dataset.line].start); if (!playing) toggle(); return; }
    var w = e.target.closest(".w");
    if (w) { openId = w.dataset.id; if (playing) toggle(); drawLines(); drawCard(); }
  });
  linesEl.addEventListener("keydown", function (e) {
    var w = e.target.closest(".w");
    if (w && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault(); openId = w.dataset.id; drawLines(); drawCard();
      var f = linesEl.querySelector('.w[data-id="' + openId + '"]'); if (f) f.focus();
    }
  });
  document.getElementById("card").addEventListener("click", function (e) {
    var b = e.target.closest("[data-set]");
    if (!b) return;
    var head = W[openId].head, next = W[openId].state === b.dataset.set ? "new" : b.dataset.set;
    Object.keys(W).forEach(function (id) { if (W[id].head === head) W[id].state = next; });
    drawLines(); drawCard();
  });
  document.getElementById("vowels").addEventListener("click", function () {
    vowels = !vowels; this.setAttribute("aria-pressed", String(vowels)); drawLines(); caption(true);
  });

  /* ---- the player ---- */
  var stage = document.getElementById("stage"), canvas = document.getElementById("film"), ctx = canvas.getContext("2d");
  var capHe = document.getElementById("capHe"), capEn = document.getElementById("capEn"), captions = document.getElementById("captions");
  var clock = document.getElementById("clock"), fill = document.getElementById("fill"), track = document.getElementById("track");
  var PLAY = '<path d="M5 3v10l8-5z" fill="currentColor"/>';
  var PAUSE = '<rect x="4" y="3" width="3" height="10" rx="0.8" fill="currentColor"/><rect x="9" y="3" width="3" height="10" rx="0.8" fill="currentColor"/>';
  var shown = -2;

  function mmss(s) { s = Math.floor(s); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
  function caption(force) {
    var n = lineAt(t);
    if (n === shown && !force) return;
    var moved = n !== shown;
    shown = n;
    if (n < 0) { captions.classList.add("quiet"); return; }
    captions.classList.remove("quiet");
    capHe.textContent = hebrewOf(LINES[n]); capEn.textContent = LINES[n].en;
    if (moved) drawLines();
  }

  function film(time) {
    var w = canvas.width, h = canvas.height, cx = w * 0.5, cy = h * 0.5, R = h * 0.43;
    function ease(a, b) { var k = Math.max(0, Math.min(1, (time - a) / (b - a))); return k * k * (3 - 2 * k); }
    function rnd(n) { var x = Math.sin(n * 91.7) * 43758.5; return x - Math.floor(x); }
    ctx.fillStyle = "#5b3d27"; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(30, 18, 10, 0.25)"; ctx.lineWidth = 2;
    for (var g = 0; g < 14; g++) {
      ctx.beginPath();
      for (var x = 0; x <= w; x += 24) { var y = g * (h / 13) + Math.sin(x * 0.01 + g) * 6; if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }
      ctx.stroke();
    }
    ctx.fillStyle = "#191614";
    ctx.beginPath(); ctx.roundRect(cx + R * 0.9, cy - R * 0.1, R * 1.05, R * 0.2, R * 0.1); ctx.fill();
    ctx.fillStyle = "rgba(0, 0, 0, 0.35)"; ctx.beginPath(); ctx.arc(cx + 8, cy + 10, R * 1.02, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#2a2624"; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#1a1715"; ctx.beginPath(); ctx.arc(cx, cy, R * 0.9, 0, Math.PI * 2); ctx.fill();
    var oil = ease(0.3, 3.5) * (1 - ease(5, 8));
    if (oil > 0) {
      var sheen = ctx.createRadialGradient(cx - R * 0.25, cy - R * 0.25, R * 0.05, cx, cy, R * 0.9);
      sheen.addColorStop(0, "rgba(214, 170, 70, " + 0.55 * oil + ")"); sheen.addColorStop(1, "rgba(214, 170, 70, 0)");
      ctx.fillStyle = sheen; ctx.beginPath(); ctx.arc(cx, cy, R * 0.9, 0, Math.PI * 2); ctx.fill();
    }
    var sauce = ease(4.6, 8.4);
    if (sauce > 0) {
      ctx.fillStyle = "#a83a26"; ctx.beginPath(); ctx.arc(cx, cy, R * 0.88 * sauce, 0, Math.PI * 2); ctx.fill();
      for (var c = 0; c < 46; c++) {
        var a = rnd(c) * Math.PI * 2, r = Math.sqrt(rnd(c + 7)) * R * 0.8 * sauce, kind = c % 3;
        ctx.fillStyle = kind === 0 ? "#c9522f" : kind === 1 ? "#e8d8b4" : "#4f7d34";
        ctx.beginPath(); ctx.ellipse(cx + Math.cos(a) * r, cy + Math.sin(a) * r, R * 0.035, R * 0.022, a, 0, Math.PI * 2); ctx.fill();
      }
      for (var b = 0; b < 9; b++) {
        var pulse = (Math.sin(time * 4 + b * 1.7) + 1) / 2, ba = rnd(b + 40) * Math.PI * 2, br = rnd(b + 50) * R * 0.7 * sauce;
        ctx.strokeStyle = "rgba(255, 210, 190, " + 0.35 * pulse * sauce + ")"; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(cx + Math.cos(ba) * br, cy + Math.sin(ba) * br, R * 0.02 + pulse * R * 0.02, 0, Math.PI * 2); ctx.stroke();
      }
    }
    var EGGS = [[-0.38, -0.3], [0.36, -0.28], [-0.3, 0.36], [0.34, 0.32]];
    EGGS.forEach(function (e, n) {
      var k = ease(9.4 + n * 1.0, 10.2 + n * 1.0);
      if (k <= 0) return;
      var ex = cx + e[0] * R, ey = cy + e[1] * R;
      ctx.fillStyle = "rgba(250, 246, 236, " + k + ")";
      ctx.beginPath(); ctx.ellipse(ex, ey, R * 0.2 * k, R * 0.17 * k, n, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(231, 160, 50, " + k + ")";
      ctx.beginPath(); ctx.arc(ex + R * 0.02, ey - R * 0.01, R * 0.075 * k, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = "rgba(255, 255, 255, " + 0.5 * k + ")";
      ctx.beginPath(); ctx.arc(ex, ey - R * 0.035, R * 0.02 * k, 0, Math.PI * 2); ctx.fill();
    });
    var lid = ease(13.8, 15.4);
    if (lid > 0) {
      var lx = cx + (1 - lid) * w * 0.7;
      ctx.fillStyle = "rgba(210, 225, 230, 0.16)"; ctx.beginPath(); ctx.arc(lx, cy, R * 0.93, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "rgba(200, 200, 200, 0.7)"; ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(lx, cy, R * 0.93, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = "rgba(255, 255, 255, 0.35)"; ctx.lineWidth = 5; ctx.beginPath(); ctx.arc(lx, cy, R * 0.75, Math.PI * 1.1, Math.PI * 1.45); ctx.stroke();
      ctx.fillStyle = "#191614"; ctx.beginPath(); ctx.arc(lx, cy, R * 0.07, 0, Math.PI * 2); ctx.fill();
    }
    var steam = ease(15.4, 17);
    if (steam > 0) {
      ctx.strokeStyle = "rgba(255, 255, 255, " + 0.22 * steam + ")"; ctx.lineWidth = 5; ctx.lineCap = "round";
      for (var s2 = 0; s2 < 3; s2++) {
        ctx.beginPath();
        for (var yy = 0; yy < R * 0.9; yy += 6) { var xx = cx - R * 0.3 + s2 * R * 0.3 + Math.sin(yy * 0.05 + time * 3 + s2) * 10; if (yy === 0) ctx.moveTo(xx, cy - R * 0.2 - yy); else ctx.lineTo(xx, cy - R * 0.2 - yy); }
        ctx.stroke();
      }
    }
  }

  function paint() {
    film(t);
    clock.textContent = mmss(BASE + t) + " / 10:12";
    fill.style.inlineSize = (t / DURATION) * 100 + "%";
    track.setAttribute("aria-valuenow", String(Math.floor(t)));
    caption(false);
  }
  function seek(time) { t = Math.max(0, Math.min(DURATION - 0.01, time)); shown = -2; paint(); }

  var last = 0, raf = 0;
  function frame(now) {
    if (!playing) return;
    var dt = last ? Math.min(0.1, (now - last) / 1000) : 0; last = now;
    t += dt * RATES[rateIx];
    if (t >= DURATION) { t = 0; paint(); toggle(); return; }
    paint();
    raf = requestAnimationFrame(frame);
  }
  function toggle() {
    playing = !playing;
    stage.classList.toggle("playing", playing);
    document.getElementById("playGlyph").innerHTML = playing ? PAUSE : PLAY;
    document.getElementById("play").setAttribute("aria-label", playing ? "Pause" : "Play");
    if (playing) { last = 0; raf = requestAnimationFrame(frame); } else cancelAnimationFrame(raf);
  }
  document.getElementById("play").addEventListener("click", toggle);
  document.getElementById("stageTap").addEventListener("click", toggle);
  document.getElementById("rate").addEventListener("click", function () {
    rateIx = (rateIx + RATES.length - 1) % RATES.length;
    this.textContent = RATES[rateIx] + "×";
  });
  track.addEventListener("click", function (e) {
    var r = track.getBoundingClientRect();
    seek(((e.clientX - r.left) / r.width) * DURATION);
  });
  track.addEventListener("keydown", function (e) {
    if (e.key === "ArrowRight") { e.preventDefault(); seek(t + 2); }
    if (e.key === "ArrowLeft") { e.preventDefault(); seek(t - 2); }
  });
  document.getElementById("pin").addEventListener("click", function () {
    var on = !stage.classList.contains("pinned");
    stage.classList.toggle("pinned", on);
    this.setAttribute("aria-pressed", String(on));
    document.getElementById("pinWord").textContent = on ? "Back" : "Corner";
  });
  document.getElementById("watchIt").addEventListener("click", function () {
    document.getElementById("reader").scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    seek(0);
    if (!playing) toggle();
  });

  drawLines(); drawCard(); paint();

  /* ---- the media tiles ---- */
  var waveHtml = "";
  for (var i = 0; i < 48; i++) {
    var hgt = 18 + Math.abs(Math.sin(i * 0.7) * 40 + Math.sin(i * 0.23) * 25);
    waveHtml += "<i class=\"" + (i < 29 ? "on" : "") + "\" style=\"block-size:" + Math.min(92, hgt) + "%\"></i>";
  }
  document.getElementById("wave").innerHTML = waveHtml;
  var miniHtml = "";
  for (var j = 0; j < 22; j++) miniHtml += "<i style=\"block-size:" + (25 + Math.abs(Math.sin(j * 1.3)) * 75) + "%\"></i>";
  document.getElementById("mini").innerHTML = miniHtml;


  /* ---- the vowel switches ---- */
  var POINTS = /[\u05B0-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]/g, CANT = /[\u0591-\u05AF]/g;
  var RECIPE = "שָׂמִים שֶׁמֶן בַּמַּחֲבַת וּמְחַכִּים שֶׁיִּתְחַמֵּם.";
  var GEN = "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃";
  function layers(el, forms) {
    el.innerHTML = forms.map(function (f) { return "<span>" + f + "</span>"; }).join("");
    return el.children;
  }
  var rec = layers(document.getElementById("vsRecipe"), [RECIPE, RECIPE.replace(POINTS, "").replace(CANT, "")]);
  var tor = layers(document.getElementById("vsTorah"), [GEN, GEN.replace(CANT, ""), GEN.replace(CANT, "").replace(POINTS, "")]);
  var swV = document.getElementById("swVowels"), swC = document.getElementById("swChant");
  function showVowels() {
    var v = swV.getAttribute("aria-checked") === "true", c = swC.getAttribute("aria-checked") === "true";
    swC.disabled = !v;
    // `plain` is the line with its points stripped off, and is the one shown when
    // the vowel switch is off. Named rather than inlined because the two toggles
    // on one line read as a pair of opposites, and one of them was the wrong way.
    var plain = v === false;
    rec[0].classList.toggle("off", plain);
    rec[1].classList.toggle("off", v);
    var torah = !v ? 2 : c ? 0 : 1;
    for (var n = 0; n < tor.length; n++) tor[n].classList.toggle("off", n !== torah);
  }
  [swV, swC].forEach(function (b) {
    b.addEventListener("click", function () { b.setAttribute("aria-checked", String(b.getAttribute("aria-checked") !== "true")); showVowels(); });
  });
  showVowels();

  /* ---- the Torah ---- */
  var VERSES = [
    { he: "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃", en: "In the beginning God created the heaven and the earth.", arc: "בְּקַדְמִין בְּרָא יְיָ יָת שְׁמַיָּא וְיָת אַרְעָא" },
    { he: "וְהָאָ֗רֶץ הָיְתָ֥ה תֹ֙הוּ֙ וָבֹ֔הוּ וְחֹ֖שֶׁךְ עַל־פְּנֵ֣י תְה֑וֹם וְר֣וּחַ אֱלֹהִ֔ים מְרַחֶ֖פֶת עַל־פְּנֵ֥י הַמָּֽיִם׃", en: "Now the earth was unformed and void, and darkness was upon the face of the deep; and the spirit of God hovered over the face of the waters.", arc: "וְאַרְעָא הֲוַת צָדְיָא וְרֵיקַנְיָא וַחֲשׁוֹכָא פָּרַשׂ עַל אַפֵּי תְהוֹמָא וְרוּחָא מִן קֳדָם יְיָ מְנַשְּׁבָא עַל אַפֵּי מַיָּא" },
    { he: "וַיֹּ֥אמֶר אֱלֹהִ֖ים יְהִ֣י א֑וֹר וַֽיְהִי־אֽוֹר׃", en: "And God said: ‘Let there be light.’ And there was light.", arc: "וַאֲמַר יְיָ יְהֵי נְהוֹרָא וַהֲוָה נְהוֹרָא" }
  ];
  var READINGS = ["First reading, in Hebrew", "Second reading, in Hebrew", "Once in Onkelos"];
  var mode = "read", at = 0, step = 0, reading = 0;
  var versesEl = document.getElementById("verses"), foot = document.getElementById("torahFoot"), meta = document.getElementById("torahMeta");

  function drawTorah() {
    versesEl.textContent = "";
    VERSES.forEach(function (v, n) {
      var row = document.createElement("div");
      row.className = "verse";
      var html = "<span class=\"num\">" + (n + 1) + "</span><p class=\"v-he\">" + v.he + "</p>";
      if (mode === "read") html += "<p class=\"v-en\">" + v.en + "</p>";
      if (mode === "verse") {
        if (n === at) row.className += " current";
        if (n < at) row.className += " done";
        if (n === at && step >= 2) html += "<p class=\"v-arc\">" + v.arc + "</p>";
      }
      if (mode === "aliyah" && reading === 2) html += "<p class=\"v-arc\">" + v.arc + "</p>";
      row.innerHTML = html;
      versesEl.appendChild(row);
    });
    foot.hidden = mode === "read";
    if (mode === "read") meta.textContent = "Hebrew · English";
    if (mode === "verse") {
      meta.textContent = "Shnayim mikra · verse " + Math.min(at + 1, 3) + " of 3";
      var lastVerse = at === VERSES.length - 1;
      var next = step === 0 ? ["Again", "again"] : step === 1 ? ["Onkelos", "onkelos"] : lastVerse ? ["Finish", "finish"] : ["Next verse", "next"];
      var said = step === 0 ? "Read the verse in Hebrew." : step === 1 ? "Once more, in Hebrew." : "And once in Onkelos.";
      if (step === 3) { said = "All three verses, twice in Hebrew and once in Onkelos."; next = ["Start again", "restart"]; }
      foot.innerHTML = "<span class=\"say\">" + said + "</span><button class=\"btn filled small\" type=\"button\" data-go=\"" + next[1] + "\">" + next[0] + "</button>";
    }
    if (mode === "aliyah") {
      meta.textContent = "Shnayim mikra · the aliyah";
      var done = reading === 3;
      foot.innerHTML = "<span class=\"say\">" + (done ? "That aliyah is on your progress." : READINGS[reading]) + "</span>" +
        "<button class=\"btn filled small\" type=\"button\" data-go=\"" + (done ? "restart" : "reading") + "\">" + (done ? "Start again" : reading === 2 ? "Done" : "Next reading") + "</button>";
    }
  }
  document.querySelectorAll(".torah .seg button").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll(".torah .seg button").forEach(function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      mode = b.dataset.mode; at = 0; step = 0; reading = 0;
      drawTorah();
    });
  });
  foot.addEventListener("click", function (e) {
    var b = e.target.closest("[data-go]");
    if (!b) return;
    var go = b.dataset.go;
    if (go === "again") step = 1;
    else if (go === "onkelos") step = 2;
    else if (go === "next") { at += 1; step = 0; }
    else if (go === "finish") { at = VERSES.length; step = 3; }
    else if (go === "reading") reading += 1;
    else if (go === "restart") { at = 0; step = 0; reading = 0; }
    drawTorah();
    var nb = foot.querySelector("button"); if (nb) nb.focus();
  });
  drawTorah();

  /* ---- the ladder ---- */
  var RUNGS = [[250, "א", "aleph", "A1"], [900, "א+", "aleph plus", "A1"], [1800, "ב", "bet", "A2"], [3000, "ב+", "bet plus", "A2+"], [4500, "ג", "gimel", "B1"], [6500, "ד", "dalet", "B2"], [9000, "ה", "hey", "C1"], [12000, "ו", "vav", "C2"]];
  var known = 2140;
  document.getElementById("ladder").innerHTML = RUNGS.map(function (r, n) {
    var lo = n ? RUNGS[n - 1][0] : 0, share = Math.max(0, Math.min(1, (known - lo) / (r[0] - lo)));
    return "<div class=\"step\" title=\"" + r[2] + " · " + r[0].toLocaleString("en") + " words\"><span class=\"bar-s\" style=\"block-size:" + (18 + n * 11.5) + "%\"><i style=\"block-size:" + share * 100 + "%\"></i></span>" +
      "<span class=\"cap\"><span class=\"he\">" + r[1] + "</span><span class=\"n\">" + r[0].toLocaleString("en") + "</span></span></div>";
  }).join("");

  /* ---- conversation fold ---- */
  var whyFold = document.getElementById("whyFold"), why = document.getElementById("why");
  whyFold.addEventListener("click", function () {
    var on = whyFold.getAttribute("aria-expanded") !== "true";
    whyFold.setAttribute("aria-expanded", String(on)); why.hidden = !on;
  });

})();
