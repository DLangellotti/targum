/* The Sentences tab: dictation and fill the gap, in lines the reader has read
 * (targum-internal#534; design.md §12, "Sentences: dictation and fill the gap",
 * 2026-10-27).
 *
 * Dictation plays one line from a recording the text already has, from its clock, and
 * the reader writes what they hear; Check shows the line with the words they missed or
 * wrote another way marked, and what they wrote with the words the line does not have
 * struck. Fill the gap shows a line with one of the words they are learning taken out.
 *
 * Nothing is scored, nothing is kept and nothing is sent: the comparison is made here,
 * the server is asked only for lines, and a new visit draws new ones. A word's stage
 * moves only where the reader presses it, on Practise these or the word's card.
 */
(function () {
  "use strict";

  /* --- the comparison, with no page (tests/js/sentences.js) ----------------------
   *
   * Forgiven, because a learner writing what they hear is not being asked to point it:
   * the points and the chanting marks (U+0591-U+05C7, the maqaf, paseq and sof pasuq
   * read as the space or the stop they are), a final letter written as its plain form or
   * the other way round, a vav or yod written in or left out (full and defective spelling
   * are both Hebrew), the stress mark and ё in Russian, capitals, and punctuation.
   * Nothing else: a wrong letter is a different word.
   */
  var BREAKS = /[־׀׃׆]/g;
  var POINTS = /[֑-ׇ]/g;
  var STRESS = /([Ѐ-ӿ])́/g;
  var FINALS = { "ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ" };
  var LETTERS = /[^\p{L}\p{N}]+/gu;
  var HEBREW = /[א-ת]/;
  var WRITTEN_IN = "וי";

  function fold(word) {
    return String(word || "")
      .normalize("NFD")
      .replace(BREAKS, " ")
      .replace(POINTS, "")
      .replace(STRESS, "$1")
      .normalize("NFC")
      .toLowerCase()
      .replace(/ё/g, "е")
      .replace(/[ךםןףץ]/g, function (letter) {
        return FINALS[letter];
      })
      .replace(LETTERS, "");
  }

  /* Whether `longer` is `shorter` with only vavs and yods written in. */
  function plene(shorter, longer) {
    if (longer.length <= shorter.length) return false;
    var at = 0;
    for (var n = 0; n < longer.length; n++) {
      if (at < shorter.length && longer[n] === shorter[at]) at += 1;
      else if (WRITTEN_IN.indexOf(longer[n]) < 0) return false;
    }
    return at === shorter.length;
  }

  function same(a, b) {
    var one = fold(a);
    var two = fold(b);
    if (one === two) return !!one;
    if (!one || !two || !HEBREW.test(one) || !HEBREW.test(two)) return false;
    return plene(one, two) || plene(two, one);
  }

  /* A line in its pieces: each word, and what stands between them, kept as written so
     the line can be drawn back exactly. A piece with no letters in it is not a word. */
  function pieces(text) {
    var out = [];
    String(text || "")
      .split(/([\s־]+)/)
      .forEach(function (piece) {
        if (!piece) return;
        out.push({ text: piece, word: !!fold(piece) });
      });
    return out;
  }

  /* The line and what was written, word against word in order (the longest run the two
     share), each word marked as found in the other or not. `whole` is every word of the
     line written and nothing else. */
  function compare(line, written) {
    var said = pieces(line);
    var wrote = pieces(written);
    var a = said.filter(function (piece) {
      return piece.word;
    });
    var b = wrote.filter(function (piece) {
      return piece.word;
    });
    var table = [];
    for (var i = 0; i <= a.length; i++) {
      table.push([]);
      for (var j = 0; j <= b.length; j++) table[i].push(0);
    }
    for (i = a.length - 1; i >= 0; i--) {
      for (j = b.length - 1; j >= 0; j--) {
        table[i][j] = same(a[i].text, b[j].text)
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
      }
    }
    i = 0;
    j = 0;
    while (i < a.length && j < b.length) {
      if (same(a[i].text, b[j].text) && table[i][j] === table[i + 1][j + 1] + 1) {
        a[i].found = true;
        b[j].found = true;
        i += 1;
        j += 1;
      } else if (table[i + 1][j] >= table[i][j + 1]) i += 1;
      else j += 1;
    }
    var shown = function (piece) {
      return { text: piece.text, word: piece.word, found: !piece.word || !!piece.found };
    };
    return {
      line: said.map(shown),
      written: wrote.map(shown),
      whole:
        a.length > 0 &&
        a.every(function (piece) {
          return piece.found;
        }) &&
        b.every(function (piece) {
          return piece.found;
        }),
    };
  }

  window.TargumSentences = { fold: fold, same: same, compare: compare };

  if (typeof document === "undefined" || window.TARGUM_LIST !== "sentences") return;

  var t = window.TargumStrings
    ? window.TargumStrings.t
    : function (key, fallback, fill) {
        return String(fallback).replace(/\{(\w+)\}/g, function (_, name) {
          return fill && name in fill ? fill[name] : "";
        });
      };
  var DIRECTION = { he: "rtl", yi: "rtl", arc: "rtl", ar: "rtl" };

  function at(id) {
    return document.getElementById(id);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function keyed(path) {
    var key = window.TARGUM_KEY || "";
    if (!key) return path;
    return path + (path.indexOf("?") >= 0 ? "&" : "?") + "k=" + encodeURIComponent(key);
  }

  var codes = Object.keys(window.TARGUM_LANGUAGES || {});
  var lang = window.TargumLang;
  var language = lang && lang.current ? lang.current(codes.length ? codes : ["he"]) : "he";
  var into = (document.documentElement.getAttribute("lang") || "en").split("-")[0];

  var data = { dictation: [], gaps: [] };
  var state = { kind: "", at: 0, written: null };
  // Only a press moves the keyboard, as on the Grammar tab: the first draw leaves it.
  var moved = false;

  function ask() {
    var path =
      "/account/sentences?language=" + encodeURIComponent(language) + "&into=" + encodeURIComponent(into);
    var headers = {};
    if (window.TARGUM_KEY) headers["X-Targum-Key"] = window.TARGUM_KEY;
    return fetch(keyed(path), { headers: headers }).then(function (response) {
      if (response.status === 401) return { signedIn: false };
      if (!response.ok) {
        var refused = new Error(String(response.status));
        refused.answered = true;
        throw refused;
      }
      return response.json();
    });
  }

  function say(text) {
    var empty = at("sentences-empty");
    if (!empty) return;
    empty.textContent = text;
    empty.hidden = !text;
  }

  function draw(answer) {
    var page = at("page");
    if (page) page.hidden = false;
    var waiting = at("home-waiting");
    if (waiting) waiting.hidden = true;
    if (!answer || answer.signedIn === false) {
      say(t("practice.page.signed-out", "Sign in to practise with the texts you've read."));
      return;
    }
    say("");
    data = { dictation: answer.dictation || [], gaps: answer.gaps || [] };
    drawKinds();
    if (!state.kind || !data[state.kind].length) {
      state.kind = data.dictation.length ? "dictation" : data.gaps.length ? "gaps" : "";
    }
    state.at = 0;
    state.written = null;
    drawRound();
  }

  function load(kind) {
    moved = true;
    state.kind = kind;
    return ask()
      .then(draw)
      .catch(function () {
        say(t("sentences.page.round-failed", "We couldn't open that. Press Start to try again."));
      });
  }

  function names(kind) {
    return kind === "dictation"
      ? t("sentences.dictation.name", "Dictation")
      : t("sentences.gaps.name", "Fill the gap");
  }

  function drawKinds() {
    var host = at("sentence-kinds");
    if (!host) return;
    host.textContent = "";
    [
      [
        "dictation",
        t("sentences.dictation.about", "Hear a line from a text you've read, and write it down."),
        t(
          "sentences.dictation.none",
          "None of the texts you've finished has a recording yet. Dictation only uses recordings your texts already have."
        ),
      ],
      [
        "gaps",
        t("sentences.gaps.about", "A line you've read, with one of the words you're learning taken out."),
        t("sentences.gaps.none", "Once you've finished a part with words you're still learning, they'll be here."),
      ],
    ].forEach(function (kind) {
      var ready = data[kind[0]].length > 0;
      var row = el("li", "grammar-spot" + (ready ? " is-ready" : ""));
      row.setAttribute("data-kind", kind[0]);
      var text = el("div", "grammar-spot-text");
      text.appendChild(el("p", "grammar-spot-name", names(kind[0])));
      text.appendChild(el("p", "grammar-spot-met", ready ? kind[1] : kind[2]));
      row.appendChild(text);
      if (ready) {
        var go = el("button", "btn grammar-go", t("sentences.start", "Start"));
        go.type = "button";
        go.setAttribute("aria-label", t("sentences.start-one", "Start {name}", { name: names(kind[0]) }));
        go.addEventListener("click", function () {
          load(kind[0]);
        });
        row.appendChild(go);
      }
      host.appendChild(row);
    });
  }

  /* --- one recording, played a line at a time ------------------------------------ */

  var voice = null;
  var stopAt = 0;
  var watching = 0;

  function stop() {
    if (watching) clearInterval(watching);
    watching = 0;
    if (voice && !voice.paused) voice.pause();
  }

  function play(item, press) {
    stop();
    if (!voice || voice.getAttribute("data-src") !== item.src) {
      voice = new Audio();
      voice.preload = "auto";
      voice.setAttribute("data-src", item.src);
      voice.src = item.src;
    }
    var heard = voice;
    stopAt = item.end;
    var begin = function () {
      heard.currentTime = item.start;
      var playing = heard.play();
      if (playing && playing.catch) {
        playing.catch(function () {
          unplayable(press);
        });
      }
      watching = setInterval(function () {
        if (heard.currentTime >= stopAt) stop();
      }, 40);
    };
    heard.onerror = function () {
      unplayable(press);
    };
    if (heard.readyState >= 1) begin();
    else heard.addEventListener("loadedmetadata", begin, { once: true });
  }

  function unplayable(press) {
    stop();
    if (press) {
      press.disabled = true;
      press.textContent = t("sentences.no-sound", "We couldn't play this line.");
    }
  }

  /* --- the line ---------------------------------------------------------------- */

  function inLanguage(node, item) {
    var code = item.language || language;
    node.setAttribute("lang", code);
    node.setAttribute("dir", DIRECTION[code] || "ltr");
    return node;
  }

  function from(item) {
    var said = el("p", "practise-from");
    var place = el("span", "practise-place");
    place.appendChild(document.createTextNode(t("lists.practise.from", "From") + " "));
    var title = el("bdi", "practise-title", item.title || "");
    title.setAttribute("dir", "auto");
    if (/[֐-׿]/.test(item.title || "")) {
      title.setAttribute("lang", DIRECTION[item.language] ? item.language : "he");
      title.setAttribute("dir", "rtl");
    }
    place.appendChild(title);
    if (item.chapter) {
      place.appendChild(
        document.createTextNode(" · " + t("lists.practise.chapter", "chapter {n}", { n: item.chapter }))
      );
    }
    said.appendChild(place);
    return said;
  }

  function marked(parts, className, tag) {
    var line = el("p", className);
    parts.forEach(function (piece) {
      if (piece.found) line.appendChild(document.createTextNode(piece.text));
      else line.appendChild(el(tag, tag === "mark" ? "practise-word said-missed" : "said-extra", piece.text));
    });
    return line;
  }

  function field(item, label) {
    var input = inLanguage(el("input", "sentence-field"), item);
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.setAttribute("autocapitalize", "off");
    input.setAttribute("aria-label", label);
    if (state.written !== null) {
      input.value = state.written;
      input.disabled = true;
    }
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        check(input.value);
      }
    });
    return input;
  }

  function check(value) {
    state.written = String(value || "");
    moved = true;
    drawRound();
  }

  function drawDictation(item, well) {
    var played = el("button", "btn sentence-play", t("sentences.play", "Play the line"));
    played.type = "button";
    played.addEventListener("click", function () {
      played.textContent = t("sentences.again", "Play again");
      play(item, played);
    });
    well.appendChild(played);
    var input = field(item, t("sentences.write", "Write what you hear"));
    well.appendChild(input);
    if (state.written === null) return input;
    var result = compare(item.line, state.written);
    var said = el("div", "grammar-feedback");
    if (result.whole) {
      said.appendChild(el("p", "grammar-verdict", t("sentences.whole", "Every word is there.")));
      said.appendChild(inLanguage(marked(result.line, "practise-line", "mark"), item));
    } else {
      said.appendChild(el("p", "grammar-other", t("sentences.it-said", "It said:")));
      said.appendChild(inLanguage(marked(result.line, "practise-line", "mark"), item));
      if (state.written.trim()) {
        said.appendChild(el("p", "grammar-other", t("sentences.you-wrote", "You wrote:")));
        said.appendChild(inLanguage(marked(result.written, "practise-line sentence-written", "del"), item));
      }
    }
    if (item.translation) said.appendChild(el("p", "practise-translation", item.translation));
    well.appendChild(said);
    return null;
  }

  var KEEP = { said: "{said}" };
  function sentence(whole, word, item) {
    var line = el("p", "grammar-verdict");
    var cut = whole.indexOf("{said}");
    line.appendChild(document.createTextNode(whole.slice(0, cut)));
    line.appendChild(inLanguage(el("bdi", "grammar-said", word), item));
    line.appendChild(document.createTextNode(whole.slice(cut + "{said}".length)));
    return line;
  }

  function drawGap(item, well) {
    var text = String(item.line || "");
    var start = Math.max(0, Math.min(text.length, item.start || 0));
    var end = Math.max(start, Math.min(text.length, item.end || 0));
    var line = inLanguage(el("p", "practise-line"), item);
    line.appendChild(document.createTextNode(text.slice(0, start)));
    if (state.written === null) {
      var gap = el("span", "sentence-gap", "   ");
      gap.setAttribute("aria-label", t("sentences.gap", "a missing word"));
      line.appendChild(gap);
    } else {
      line.appendChild(el("mark", "practise-word", text.slice(start, end)));
    }
    line.appendChild(document.createTextNode(text.slice(end)));
    well.appendChild(line);
    if (item.translation) well.appendChild(el("p", "practise-translation", item.translation));
    var input = field(item, t("sentences.fill", "The missing word"));
    well.appendChild(input);
    if (state.written === null) return input;
    var said = el("div", "grammar-feedback");
    var word = text.slice(start, end);
    said.appendChild(
      same(word, state.written)
        ? sentence(t("sentences.gap-right", "Yes, {said}.", KEEP), word, item)
        : sentence(t("sentences.gap-other", "It's {said} here.", KEEP), word, item)
    );
    well.appendChild(said);
    return null;
  }

  function drawRound() {
    var host = at("sentence-round");
    if (!host) return;
    stop();
    var items = state.kind ? data[state.kind] : [];
    host.hidden = !items.length;
    if (!items.length) return;
    at("sentence-round-heading").textContent = names(state.kind);
    var where = at("sentence-round-at");
    var body = at("sentence-round-body");
    body.textContent = "";

    if (state.at >= items.length) {
      where.textContent = "";
      body.appendChild(
        el("p", "grammar-done", t("sentences.done", "That's all of them. We draw new lines every time you come."))
      );
      var again = el("button", "btn grammar-again", t("sentences.more", "New lines"));
      again.type = "button";
      again.addEventListener("click", function () {
        load(state.kind);
      });
      body.appendChild(again);
      if (moved && again.focus) again.focus();
      moved = false;
      return;
    }

    var item = items[state.at];
    where.textContent = t("lists.practise.at", "{n} of {total}", { n: state.at + 1, total: items.length });
    var well = el("div", "practise-well");
    well.appendChild(from(item));
    var input = state.kind === "dictation" ? drawDictation(item, well) : drawGap(item, well);
    body.appendChild(well);

    var press;
    if (state.written === null) {
      press = el("button", "btn grammar-next sentence-check", t("sentences.check", "Check"));
      press.type = "button";
      press.addEventListener("click", function () {
        check(input ? input.value : "");
      });
    } else {
      press = el("button", "btn grammar-next sentence-next", t("sentences.next", "Next line"));
      press.type = "button";
      press.addEventListener("click", function () {
        state.at += 1;
        state.written = null;
        moved = true;
        drawRound();
      });
    }
    body.appendChild(press);
    if (moved) {
      moved = false;
      var to = state.written === null ? input : press;
      if (to && to.focus) to.focus();
    }
  }

  var loaded = ask().then(draw);
  loaded.catch(function () {});
  window.TargumSentences.loaded = loaded;
})();
