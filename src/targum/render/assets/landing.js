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

  // The page's words, in the page's language (targum-internal#184). English is the
  // fallback written at every call, so a key the catalogue has not filled still says
  // something rather than its own name.
  var words = window.TargumStrings || {};
  var t =
    typeof words.t === "function"
      ? words.t
      : function (key, english) {
          return english;
        };
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
    samim: { he: "שָׂמִים", state: "known", head: "שָׂם", pos: t("landing.card.verb", "verb"), sense: t("landing.card.to-put-to-place", "to put, to place"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">שָׂמִים</span> · " + t("landing.card.pa-al-present", "pa’al, present") + " · " + t("landing.card.put", "put")], [t("landing.card.root", "Root"), "<span class=\"he\">שׂ־י־ם</span>"], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")], [t("landing.card.met-before", "Met before"), t("landing.card.genesis-2-8", "Genesis 2:8") + " · <span class=\"scripture\">וַיָּ֣שֶׂם</span> · " + t("landing.card.and-there-he-put", "“and there He put”")]] },
    shemen: { he: "שֶׁמֶן", state: "known", head: "שֶׁמֶן", pos: t("landing.card.noun-masculine", "noun, masculine"), sense: t("landing.card.oil", "oil"), facts: [[t("landing.card.plural", "Plural"), "<span class=\"he\">שְׁמָנִים</span>"], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")], [t("landing.card.met-before", "Met before"), t("landing.card.genesis-28-18", "Genesis 28:18") + " · <span class=\"scripture\">שֶׁ֖מֶן</span> · " + t("landing.card.and-poured-oil", "“and poured oil”")]] },
    bamachvat: { he: "בַּמַּחֲבַת", state: "learning", head: "מַחֲבַת", pos: t("landing.card.noun-feminine", "noun, feminine"), sense: t("landing.card.frying-pan", "frying pan"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">בַּ</span> + <span class=\"he\">מַּחֲבַת</span> · " + t("landing.card.in-the-pan", "in the pan")], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")], [t("landing.card.met-before", "Met before"), t("landing.card.leviticus-2-5", "Leviticus 2:5") + " · <span class=\"scripture\">הַֽמַּחֲבַ֖ת</span> · " + t("landing.card.baked-on-a-griddle", "“baked on a griddle”")]] },
    umechakim: { he: "וּמְחַכִּים", state: "known", head: "חִכָּה", pos: t("landing.card.verb", "verb"), sense: t("landing.card.to-wait", "to wait"), binyan: [["pi’el", "חִכָּה", true]], facts: [[t("landing.card.here", "Here"), "<span class=\"he\">וּ</span> + <span class=\"he\">מְחַכִּים</span> · " + t("landing.card.and-wait", "and wait")], [t("landing.card.root", "Root"), "<span class=\"he\">ח־כ־ה</span>"]] },
    sheyitchamem: { he: "שֶׁיִּתְחַמֵּם", state: "new", head: "הִתְחַמֵּם", pos: t("landing.card.verb", "verb"), sense: t("landing.card.to-heat-up-to-warm-up", "to heat up, to warm up"), binyan: [["pi’el", "חִמֵּם"], ["hitpa’el", "הִתְחַמֵּם", true]], facts: [[t("landing.card.here", "Here"), "<span class=\"he\">שֶׁ</span> + <span class=\"he\">יִּתְחַמֵּם</span> · " + t("landing.card.hitpa-el-future-it", "hitpa’el, future, it") + " · " + t("landing.card.for-it-to-heat-up", "for it to heat up")], [t("landing.card.root", "Root"), "<span class=\"he\">ח־מ־ם</span>"]] },
    mosifim: { he: "מוֹסִיפִים", state: "learning", head: "הוֹסִיף", pos: t("landing.card.verb", "verb"), sense: t("landing.card.to-add", "to add"), binyan: [["hif’il", "הוֹסִיף", true], ["nif’al", "נוֹסַף"]], facts: [[t("landing.card.here", "Here"), "<span class=\"he\">מוֹסִיפִים</span> · " + t("landing.card.hif-il-present", "hif’il, present") + " · " + t("landing.card.add", "add")], [t("landing.card.root", "Root"), "<span class=\"he\">י־ס־ף</span>"], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")]] },
    batzal: { he: "בָּצָל", state: "known", head: "בָּצָל", pos: t("landing.card.noun-masculine", "noun, masculine"), sense: t("landing.card.onion", "onion"), facts: [[t("landing.card.plural", "Plural"), "<span class=\"he\">בְּצָלִים</span>"], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")], [t("landing.card.met-before", "Met before"), t("landing.card.numbers-11-5", "Numbers 11:5") + " · <span class=\"scripture\">הַבְּצָלִ֖ים</span> · " + t("landing.card.and-the-onions", "“and the onions”")]] },
    pilpel: { he: "פִּלְפֵּל", state: "known", head: "פִּלְפֵּל", pos: t("landing.card.noun-masculine", "noun, masculine"), sense: t("landing.card.pepper", "pepper"), facts: [[t("landing.card.plural", "Plural"), "<span class=\"he\">פִּלְפְּלִים</span>"], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.rabbinic-and-modern", "Rabbinic and modern")]] },
    agvaniyot: { he: "וְעַגְבָנִיּוֹת", state: "learning", head: "עַגְבָנִיָּה", pos: t("landing.card.noun-feminine", "noun, feminine"), sense: t("landing.card.tomato", "tomato"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">וְ</span> + <span class=\"he\">עַגְבָנִיּוֹת</span> · " + t("landing.card.and-tomatoes", "and tomatoes")], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.modern", "Modern")], [t("landing.card.from", "From"), "<span class=\"he\">עָגַב</span>" + t("landing.card.to-desire-the-tomato-was-once-the-love", ", to desire. The tomato was once the love apple.")]] },
    umevashlim: { he: "וּמְבַשְּׁלִים", state: "known", head: "בִּשֵּׁל", pos: t("landing.card.verb", "verb"), sense: t("landing.card.to-cook", "to cook"), binyan: [["pi’el", "בִּשֵּׁל", true], ["pu’al", "בֻּשַּׁל"]], facts: [[t("landing.card.here", "Here"), "<span class=\"he\">וּ</span> + <span class=\"he\">מְבַשְּׁלִים</span> · " + t("landing.card.and-cook", "and cook")], [t("landing.card.root", "Root"), "<span class=\"he\">ב־שׁ־ל</span>"], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")]] },
    al: { he: "עַל", state: "known", head: "עַל", pos: t("landing.card.preposition", "preposition"), sense: t("landing.card.on-over", "on, over"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">עַל אֵשׁ</span> · " + t("landing.card.over-a-heat-on-the-stove", "over a heat, on the stove")]] },
    esh: { he: "אֵשׁ", state: "known", head: "אֵשׁ", pos: t("landing.card.noun-feminine", "noun, feminine"), sense: t("landing.card.fire", "fire"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">אֵשׁ קְטַנָּה</span> · " + t("landing.card.a-low-heat", "a low heat")], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")]] },
    ktana: { he: "קְטַנָּה", state: "known", head: "קָטָן", pos: t("landing.card.adjective", "adjective"), sense: t("landing.card.small", "small"), facts: [[t("landing.card.here", "Here"), t("landing.card.feminine-to-match", "feminine, to match") + " <span class=\"he\">אֵשׁ</span>"]] },
    achshav: { he: "עַכְשָׁיו", state: "known", head: "עַכְשָׁיו", pos: t("landing.card.adverb", "adverb"), sense: t("landing.card.now", "now"), facts: [[t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.rabbinic-and-modern", "Rabbinic and modern")]] },
    shovrim: { he: "שׁוֹבְרִים", state: "learning", head: "שָׁבַר", pos: t("landing.card.verb", "verb"), sense: t("landing.card.to-break", "to break"), binyan: [["pa’al", "שָׁבַר", true], ["nif’al", "נִשְׁבַּר"], ["pi’el", "שִׁבֵּר"]], facts: [[t("landing.card.here", "Here"), "<span class=\"he\">שׁוֹבְרִים</span> · " + t("landing.card.pa-al-present", "pa’al, present") + " · " + t("landing.card.crack", "crack")], [t("landing.card.root", "Root"), "<span class=\"he\">שׁ־ב־ר</span>"], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")], [t("landing.card.met-before", "Met before"), t("landing.card.exodus-34-1", "Exodus 34:1") + " · <span class=\"scripture\">שִׁבַּֽרְתָּ</span> · " + t("landing.card.which-thou-didst-break", "“which thou didst break”")]] },
    et: { he: "אֶת", state: "known", head: "אֶת", pos: t("landing.card.particle", "particle"), sense: t("landing.card.marks-a-definite-object", "marks a definite object"), facts: [[t("landing.card.here", "Here"), t("landing.card.before", "before") + " <span class=\"he\">הַבֵּיצִים</span>" + t("landing.card.which-is-definite", ", which is definite")]] },
    habeitzim: { he: "הַבֵּיצִים", state: "known", head: "בֵּיצָה", pos: t("landing.card.noun-feminine", "noun, feminine"), sense: t("landing.card.egg", "egg"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">הַ</span> + <span class=\"he\">בֵּיצִים</span> · " + t("landing.card.the-eggs", "the eggs")], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")], [t("landing.card.met-before", "Met before"), t("landing.card.deuteronomy-22-6", "Deuteronomy 22:6") + " · <span class=\"scripture\">בֵיצִ֔ים</span> · " + t("landing.card.or-eggs", "“or eggs”")]] },
    yeshirot: { he: "יְשִׁירוֹת", state: "new", head: "יְשִׁירוֹת", pos: t("landing.card.adverb", "adverb"), sense: t("landing.card.directly-straight", "directly, straight"), facts: [[t("landing.card.root", "Root"), "<span class=\"he\">י־שׁ־ר</span>"], [t("landing.card.from", "From"), "<span class=\"he\">יָשָׁר</span>" + t("landing.card.straight", ", straight")]] },
    letoch: { he: "לְתוֹךְ", state: "known", head: "תּוֹךְ", pos: t("landing.card.preposition", "preposition"), sense: t("landing.card.into", "into"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">לְ</span> + <span class=\"he\">תוֹךְ</span> · " + t("landing.card.into", "into")]] },
    harotev: { he: "הָרֹטֶב", state: "learning", head: "רֹטֶב", pos: t("landing.card.noun-masculine", "noun, masculine"), sense: t("landing.card.sauce", "sauce"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">הָ</span> + <span class=\"he\">רֹטֶב</span> · " + t("landing.card.the-sauce", "the sauce")], [t("landing.card.plural", "Plural"), "<span class=\"he\">רְטָבִים</span>"], [t("landing.card.from", "From"), "<span class=\"he\">ר־ט־ב</span>" + t("landing.card.moist", ", moist")]] },
    mechasim: { he: "מְכַסִּים", state: "learning", head: "כִּסָּה", pos: t("landing.card.verb", "verb"), sense: t("landing.card.to-cover", "to cover"), binyan: [["pi’el", "כִּסָּה", true], ["hitpa’el", "הִתְכַּסָּה"]], facts: [[t("landing.card.here", "Here"), "<span class=\"he\">מְכַסִּים</span> · " + t("landing.card.pi-el-present", "pi’el, present") + " · " + t("landing.card.cover", "cover")], [t("landing.card.root", "Root"), "<span class=\"he\">כ־ס־ה</span>"], [t("landing.card.which-hebrew", "Which Hebrew"), t("landing.card.biblical-and-modern", "Biblical and modern")]] },
    veacharei: { he: "וְאַחֲרֵי", state: "known", head: "אַחֲרֵי", pos: t("landing.card.preposition", "preposition"), sense: t("landing.card.after", "after"), facts: [[t("landing.card.here", "Here"), "<span class=\"he\">וְ</span> + <span class=\"he\">אַחֲרֵי</span> · " + t("landing.card.and-after", "and after")]] },
    chamesh: { he: "חָמֵשׁ", state: "known", head: "חָמֵשׁ", pos: t("landing.card.number", "number"), sense: t("landing.card.five", "five"), facts: [[t("landing.card.here", "Here"), t("landing.card.feminine-to-match", "feminine, to match") + " <span class=\"he\">דַּקּוֹת</span>"]] },
    dakot: { he: "דַּקּוֹת", state: "known", head: "דַּקָּה", pos: t("landing.card.noun-feminine", "noun, feminine"), sense: t("landing.card.minute", "minute"), facts: [[t("landing.card.plural", "Plural"), "<span class=\"he\">דַּקּוֹת</span>"], [t("landing.card.from", "From"), "<span class=\"he\">דַּק</span>" + t("landing.card.thin", ", thin")], [t("landing.card.met-before", "Met before"), t("landing.card.genesis-41-3", "Genesis 41:3") + " · <span class=\"scripture\">וְדַקּ֣וֹת</span> · " + t("landing.card.lean-fleshed", "“lean-fleshed”")]] },
    ze: { he: "זֶה", state: "known", head: "זֶה", pos: t("landing.card.pronoun", "pronoun"), sense: t("landing.card.this-it", "this, it"), facts: [[t("landing.card.here", "Here"), t("landing.card.it", "it")]] },
    muchan: { he: "מוּכָן", state: "known", head: "מוּכָן", pos: t("landing.card.adjective", "adjective"), sense: t("landing.card.ready", "ready"), facts: [[t("landing.card.root", "Root"), "<span class=\"he\">כ־ו־ן</span>"], [t("landing.card.from", "From"), "<span class=\"he\">הֵכִין</span>" + t("landing.card.to-prepare", ", to prepare")]] }
  };
  var LINES = [
    { start: 0, end: 4.4, words: ["samim", "shemen", "bamachvat", "umechakim", "sheyitchamem"], en: t("landing.demo.put-oil-in-the-pan-and-wait-for", "Put oil in the pan and wait for it to heat up."), stamp: "2:10" },
    { start: 4.4, end: 9.0, words: ["mosifim", "batzal", "pilpel", "agvaniyot", "umevashlim", "al", "esh", "ktana"], en: t("landing.demo.add-onion-pepper-and-tomatoes-and-cook-over", "Add onion, pepper and tomatoes, and cook over a low heat."), stamp: "2:14", comma: [1] },
    { start: 9.0, end: 13.6, words: ["achshav", "shovrim", "et", "habeitzim", "yeshirot", "letoch", "harotev"], en: t("landing.demo.now-crack-the-eggs-straight-into-the-sauce", "Now crack the eggs straight into the sauce."), stamp: "2:19" },
    { start: 13.6, end: 18, words: ["mechasim", "veacharei", "chamesh", "dakot", "ze", "muchan"], en: t("landing.demo.cover-it-and-after-five-minutes-it-s", "Cover it, and after five minutes it’s ready."), stamp: "2:23", comma: [0] }
  ];
  var DURATION = 18, BASE = 130;
  var RATES = [0.5, 0.75, 1];
  // `at` is where in the video we are. It was `t`, which is the catalogue's own
  // name for a sentence, and the clock quietly overwrote it (2026-09-16).
  var vowels = true, openId = "shovrim", at = 10.4, playing = false, rateIx = 2;

  function plain(s) { return vowels ? s : s.replace(MARKS, ""); }
  function lineAt(time) { for (var i = 0; i < LINES.length; i++) if (time >= LINES[i].start && time < LINES[i].end) return i; return -1; }
  function comma(line, i) { return line.comma && line.comma.indexOf(i) >= 0 ? "," : ""; }
  function hebrewOf(line) { return line.words.map(function (id, i) { return plain(W[id].he) + comma(line, i); }).join(" ") + "."; }

  var linesEl = document.getElementById("lines");
  function drawLines() {
    var now = lineAt(at);
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
    var html = "<div class=\"card-head\"><span class=\"label\">" + t("landing.page.word-card", "Word card") + "</span><p class=\"card-word\">" + w.head + "</p>" +
      "<p class=\"card-sense\">" + w.sense + " <span class=\"pos\">· " + w.pos + "</span></p></div>";
    if (w.binyan) html += "<div class=\"binyanim\">" + w.binyan.map(function (b) { return "<span class=\"" + (b[2] ? "here" : "") + "\">" + b[0] + " <span class=\"he\">" + b[1] + "</span></span>"; }).join("") + "</div>";
    html += "<dl class=\"facts-list\">" + w.facts.map(function (f) { return "<dt>" + f[0] + "</dt><dd>" + f[1] + "</dd>"; }).join("") + "</dl>";
    html += "<div class=\"card-actions\"><button class=\"btn tonal small\" type=\"button\" data-set=\"learning\" aria-pressed=\"" + (w.state === "learning") + "\">" + t("landing.demo.getting-there", "Getting there") + "</button>" +
      "<button class=\"btn tonal small\" type=\"button\" data-set=\"known\" aria-pressed=\"" + (w.state === "known") + "\">" + t("landing.demo.known", "Known") + "</button>" +
      "<button class=\"btn ghost small\" type=\"button\">" + t("landing.demo.ask", "Ask") + "</button></div>";
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
    var n = lineAt(at);
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
    film(at);
    clock.textContent = mmss(BASE + at) + " / 10:12";
    fill.style.inlineSize = (at / DURATION) * 100 + "%";
    track.setAttribute("aria-valuenow", String(Math.floor(at)));
    caption(false);
  }
  function seek(time) { at = Math.max(0, Math.min(DURATION - 0.01, time)); shown = -2; paint(); }

  var last = 0, raf = 0;
  function frame(now) {
    if (!playing) return;
    var dt = last ? Math.min(0.1, (now - last) / 1000) : 0; last = now;
    at += dt * RATES[rateIx];
    if (at >= DURATION) { at = 0; paint(); toggle(); return; }
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
    if (e.key === "ArrowRight") { e.preventDefault(); seek(at + 2); }
    if (e.key === "ArrowLeft") { e.preventDefault(); seek(at - 2); }
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
    { he: "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים אֵ֥ת הַשָּׁמַ֖יִם וְאֵ֥ת הָאָֽרֶץ׃", en: t("landing.demo.in-the-beginning-god-created-the-heaven-and", "In the beginning God created the heaven and the earth."), arc: "בְּקַדְמִין בְּרָא יְיָ יָת שְׁמַיָּא וְיָת אַרְעָא" },
    { he: "וְהָאָ֗רֶץ הָיְתָ֥ה תֹ֙הוּ֙ וָבֹ֔הוּ וְחֹ֖שֶׁךְ עַל־פְּנֵ֣י תְה֑וֹם וְר֣וּחַ אֱלֹהִ֔ים מְרַחֶ֖פֶת עַל־פְּנֵ֥י הַמָּֽיִם׃", en: t("landing.demo.now-the-earth-was-unformed-and-void-and", "Now the earth was unformed and void, and darkness was upon the face of the deep; and the spirit of God hovered over the face of the waters."), arc: "וְאַרְעָא הֲוַת צָדְיָא וְרֵיקַנְיָא וַחֲשׁוֹכָא פָּרַשׂ עַל אַפֵּי תְהוֹמָא וְרוּחָא מִן קֳדָם יְיָ מְנַשְּׁבָא עַל אַפֵּי מַיָּא" },
    { he: "וַיֹּ֥אמֶר אֱלֹהִ֖ים יְהִ֣י א֑וֹר וַֽיְהִי־אֽוֹר׃", en: t("landing.demo.and-god-said-let-there-be-light-and", "And God said: ‘Let there be light.’ And there was light."), arc: "וַאֲמַר יְיָ יְהֵי נְהוֹרָא וַהֲוָה נְהוֹרָא" }
  ];
  var READINGS = [t("landing.demo.first-reading-in-hebrew", "First reading, in Hebrew"), t("landing.demo.second-reading-in-hebrew", "Second reading, in Hebrew"), t("landing.demo.once-in-onkelos", "Once in Onkelos")];
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
    if (mode === "read") meta.textContent = t("landing.demo.hebrew-english", "Hebrew · English");
    if (mode === "verse") {
      meta.textContent = t("landing.demo.shnayim-mikra-verse", "Shnayim mikra · verse ") + Math.min(at + 1, 3) + t("landing.demo.of-3", " of 3");
      var lastVerse = at === VERSES.length - 1;
      var next = step === 0 ? [t("landing.demo.again", "Again"), "again"] : step === 1 ? [t("landing.demo.onkelos", "Onkelos"), "onkelos"] : lastVerse ? [t("landing.demo.finish", "Finish"), "finish"] : [t("landing.demo.next-verse", "Next verse"), "next"];
      var said = step === 0 ? t("landing.demo.read-the-verse-in-hebrew", "Read the verse in Hebrew.") : step === 1 ? t("landing.demo.once-more-in-hebrew", "Once more, in Hebrew.") : t("landing.demo.and-once-in-onkelos", "And once in Onkelos.");
      if (step === 3) { said = t("landing.demo.all-three-verses-twice-in-hebrew-and-once", "All three verses, twice in Hebrew and once in Onkelos."); next = [t("landing.demo.start-again", "Start again"), "restart"]; }
      foot.innerHTML = "<span class=\"say\">" + said + "</span><button class=\"btn filled small\" type=\"button\" data-go=\"" + next[1] + "\">" + next[0] + "</button>";
    }
    if (mode === "aliyah") {
      meta.textContent = t("landing.demo.shnayim-mikra-the-aliyah", "Shnayim mikra · the aliyah");
      var done = reading === 3;
      foot.innerHTML = "<span class=\"say\">" + (done ? "That aliyah is on your progress." : READINGS[reading]) + "</span>" +
        "<button class=\"btn filled small\" type=\"button\" data-go=\"" + (done ? "restart" : "reading") + "\">" + (done ? t("landing.demo.start-again", "Start again") : reading === 2 ? t("landing.demo.done", "Done") : "Next reading") + "</button>";
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
