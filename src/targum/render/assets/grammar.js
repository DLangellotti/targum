/* The Grammar tab: a practice for each hard spot (targum-internal#440; design.md §12, "A
 * practice for every hard spot", 2026-10-13).
 *
 * Each spot says how often the reader has met it in what they finished, and is offered
 * once that is often enough to practise. A round is one worked example and five items,
 * each a choice between two answers about one word in a line the reader has read; after
 * each, the right answer, the rule that decided it, and one real line where the other
 * answer is right. Nothing is scored on the page and nothing is counted against the
 * reader: the answers go to the server only to choose the next round's lines and its day.
 */
(function () {
  "use strict";

  if (window.TARGUM_LIST !== "grammar") return;

  var t = window.TargumStrings
    ? window.TargumStrings.t
    : function (key, fallback, fill) {
        return String(fallback).replace(/\{(\w+)\}/g, function (_, name) {
          return fill && name in fill ? fill[name] : "";
        });
      };
  var DIRECTION = { he: "rtl", yi: "rtl", arc: "rtl", ar: "rtl" };
  var NAMES = {
    binyan: ["practice.spot.binyan", "Root and binyan"],
    homograph: ["practice.spot.homograph", "Vowels and look-alike words"],
    tense: ["practice.spot.tense", "Tense and person"],
    governed: ["practice.spot.governed", "Prepositions a verb takes"],
    agreement: ["practice.spot.agreement", "Gender and number"],
    construct: ["practice.spot.construct", "The construct state"],
    stress: ["practice.spot.stress", "Stress"],
    vav: ["practice.spot.vav", "The vav-consecutive"],
    suffix: ["practice.spot.suffix", "Pronoun suffixes"],
  };

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

  function headers() {
    var out = { "Content-Type": "application/json" };
    if (window.TARGUM_KEY) out["X-Targum-Key"] = window.TARGUM_KEY;
    return out;
  }

  var codes = Object.keys(window.TARGUM_LANGUAGES || {});
  var lang = window.TargumLang;
  var language = lang && lang.current ? lang.current(codes.length ? codes : ["he"]) : "he";
  var into = (document.documentElement.getAttribute("lang") || "en").split("-")[0];

  var state = { round: null, at: 0, chosen: -1, right: 0, asked: 0 };

  /* The first answer is the page's (Your Words QA, 2026-10-20; design.md §14, line 1):
     `yours.js` says the wait, says it again past three seconds, and draws the refusal
     with Try again from `loaded`. A refusal is not an answer: a 500 with a JSON body was
     drawn as "Grammar practice is in Hebrew for now". A later press that fails is said
     in place, and the press is the way to ask again. */
  function ask(spot) {
    var path =
      "/account/practice?language=" +
      encodeURIComponent(language) +
      "&into=" +
      encodeURIComponent(into) +
      (spot ? "&spot=" + encodeURIComponent(spot) : "");
    return fetch(keyed(path), { headers: headers() }).then(function (response) {
      if (response.status === 401) return { signedIn: false };
      if (!response.ok) {
        var refused = new Error(String(response.status));
        refused.answered = true;
        throw refused;
      }
      return response.json();
    });
  }

  /* Whether the reader just pressed something in the round (Your Words QA, 2026-10-20).
     The page's first draw took focus to the worked example's Start, which scrolled a
     phone past the list to the card before anybody had touched the page. Only a press
     moves the keyboard: to Start or Next once an answer is shown, to the first answer
     when a new item asks. */
  var moved = false;

  function load(spot) {
    moved = true;
    return ask(spot)
      .then(draw)
      .catch(function () {
        say(t("practice.page.round-failed", "We couldn't open that practice. Press Practise to try again."));
      });
  }

  function post(body) {
    body.language = language;
    return fetch(keyed("/practice"), {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    }).catch(function () {});
  }

  function say(text) {
    var empty = at("grammar-empty");
    if (!empty) return;
    empty.textContent = text;
    empty.hidden = !text;
  }

  function draw(data) {
    var page = at("page");
    if (page) page.hidden = false;
    var waiting = at("home-waiting");
    if (waiting) waiting.hidden = true;
    if (!data || data.signedIn === false) {
      say(t("practice.page.signed-out", "Sign in to practise with the texts you've read."));
      return;
    }
    var spots = data.spots || [];
    drawSpots(spots);
    if (!spots.length) {
      say(t("practice.page.hebrew-only", "Grammar practice is in Hebrew for now."));
    } else {
      say("");
    }
    state.round = data.round && data.round.items && data.round.items.length ? data.round : null;
    state.at = 0;
    state.chosen = -1;
    state.right = 0;
    state.asked = 0;
    drawRound();
  }

  function drawSpots(spots) {
    var host = at("grammar-spots");
    if (!host) return;
    host.textContent = "";
    spots.forEach(function (spot) {
      var name = NAMES[spot.key] || [spot.key, spot.key];
      var row = el("li", "grammar-spot" + (spot.ready ? " is-ready" : ""));
      row.setAttribute("data-spot", spot.key);
      var text = el("div", "grammar-spot-text");
      text.appendChild(el("p", "grammar-spot-name", t(name[0], name[1])));
      var met = spot.ready
        ? t("practice.page.met", "Met in {n} lines across {texts} texts.", {
            n: spot.encounters,
            texts: spot.texts,
          })
        : t("practice.page.not-yet", "We'll offer this once you've met it in {need} lines across {texts} texts. So far: {n}.", {
            need: spot.needs.encounters,
            texts: spot.needs.texts,
            n: spot.encounters,
          });
      text.appendChild(el("p", "grammar-spot-met", met));
      row.appendChild(text);
      if (spot.kind === "lens") {
        text.appendChild(
          el("p", "grammar-spot-lens", t("practice.page.lens", "Practised with a lens in the reader: Aa, then Prepositions verbs take, once you've finished a part."))
        );
      }
      if (spot.ready && spot.kind === "choice") {
        var go = el("button", "btn grammar-go", t("practice.page.practise", "Practise"));
        go.type = "button";
        // Four presses all called Practise read as one to a screen reader: each says its spot.
        go.setAttribute("aria-label", t("practice.page.practise-spot", "Practise {spot}", { spot: t(name[0], name[1]) }));
        go.addEventListener("click", function () {
          load(spot.key);
        });
        row.appendChild(go);
      }
      host.appendChild(row);
    });
  }

  function lineOf(item, className) {
    var line = el("p", className || "practise-line");
    line.setAttribute("lang", language);
    line.setAttribute("dir", DIRECTION[language] || "ltr");
    var text = String(item.line || "");
    var start = Math.max(0, Math.min(text.length, item.start || 0));
    var end = Math.max(start, Math.min(text.length, item.end || 0));
    line.appendChild(document.createTextNode(text.slice(0, start)));
    line.appendChild(el("mark", "practise-word", text.slice(start, end)));
    line.appendChild(document.createTextNode(text.slice(end)));
    return line;
  }

  // An answer is a word of the text's language (a binyan's name, a form) or of the
  // reader's (masculine, past): said with the language its letters are in, so a Hebrew
  // one carries its lang and reads in the Hebrew face (design.md §14, line 3).
  var HEBREW = /[֐-׿]/;
  function answerText(text, className) {
    var node = el("bdi", className || "grammar-answer", text);
    if (HEBREW.test(String(text || ""))) {
      node.setAttribute("lang", language === "yi" || language === "arc" ? language : "he");
      node.setAttribute("dir", "rtl");
    } else {
      node.setAttribute("dir", "auto");
    }
    return node;
  }

  // A sentence of the page's with a word of the answer's inside it: "Yes, {said}." Said
  // through a literal t() at each call, with the place kept, which is how the page's
  // strings are found for it (a key passed in a variable reached no catalogue, and the
  // Russian round said "It's פעל here").
  var KEEP = { said: "{said}" };
  function sentence(whole, said, className) {
    var line = el("p", className);
    var cut = whole.indexOf("{said}");
    if (cut < 0) {
      line.textContent = whole;
      return line;
    }
    line.appendChild(document.createTextNode(whole.slice(0, cut)));
    line.appendChild(answerText(said, "grammar-said"));
    line.appendChild(document.createTextNode(whole.slice(cut + "{said}".length)));
    return line;
  }

  function drawRound() {
    var host = at("grammar-round");
    if (!host) return;
    var round = state.round;
    host.hidden = !round;
    if (!round) return;
    var items = round.items;
    var name = NAMES[round.spot] || [round.spot, round.spot];
    at("grammar-round-heading").textContent = t(name[0], name[1]);
    var count = items.length - 1;
    var where = at("grammar-round-at");
    var body = at("grammar-round-body");
    body.textContent = "";
    // The practice card's frame hides what follows the line on a phone until a press;
    // here the press is the answer, so nothing waits.
    body.classList.add("is-shown");

    if (state.at >= items.length) {
      where.textContent = "";
      body.appendChild(el("p", "grammar-done", t("practice.page.done", "That's the round. We'll bring this one back in a few days, with other lines.")));
      var again = el("button", "btn grammar-again", t("practice.page.another", "Practise another"));
      again.type = "button";
      again.addEventListener("click", function () {
        load("");
      });
      body.appendChild(again);
      // Next had the keyboard and is gone now: it goes on to the way on, not back to the
      // top of the page (Your Words QA, 2026-10-20).
      if (moved && again.focus) again.focus();
      moved = false;
      return;
    }

    var item = items[state.at];
    where.textContent = item.example
      ? t("practice.page.example", "Worked example")
      : t("lists.practise.at", "{n} of {total}", { n: state.at, total: count });

    var well = el("div", "practise-well");
    if (item.title) {
      var from = el("p", "practise-from");
      var title = answerText(item.title, "practise-title");
      from.appendChild(document.createTextNode(t("lists.practise.from", "From") + " "));
      from.appendChild(title);
      well.appendChild(from);
    }
    well.appendChild(lineOf(item));
    if (item.translation && (item.example || state.chosen >= 0)) {
      well.appendChild(el("p", "practise-translation", item.translation));
    }
    well.appendChild(el("p", "practise-question", item.ask));

    var shown = item.example || state.chosen >= 0;
    var options = el("div", "grammar-options");
    item.options.forEach(function (option, n) {
      var press = el("button", "grammar-option");
      press.type = "button";
      press.appendChild(answerText(option));
      if (shown) {
        press.disabled = true;
        if (n === item.answer) press.classList.add("is-right");
        else if (n === state.chosen) press.classList.add("is-wrong");
      } else {
        press.addEventListener("click", function () {
          choose(item, n);
        });
      }
      options.appendChild(press);
    });
    well.appendChild(options);

    if (shown) {
      var said = el("div", "grammar-feedback");
      said.appendChild(
        item.example
          ? sentence(t("practice.page.example-said", "Here it's {said}.", KEEP), item.said, "grammar-verdict")
          : state.chosen === item.answer
            ? sentence(t("practice.page.right", "Yes, {said}.", KEEP), item.said, "grammar-verdict")
            : sentence(t("practice.page.wrong", "It's {said} here.", KEEP), item.said, "grammar-verdict")
      );
      said.appendChild(el("p", "grammar-rule", item.rule));
      if (item.contrast) {
        said.appendChild(sentence(t("practice.page.other", "Where it's {said}:", KEEP), item.contrast.said, "grammar-other"));
        said.appendChild(lineOf(item.contrast, "practise-line grammar-other-line"));
      }
      well.appendChild(said);
    }
    body.appendChild(well);

    if (shown) {
      var next = el(
        "button",
        "btn practise-next grammar-next",
        item.example ? t("practice.page.start", "Start") : t("practice.page.next", "Next")
      );
      next.type = "button";
      next.addEventListener("click", function () {
        state.at += 1;
        state.chosen = -1;
        if (state.at >= items.length && state.asked) {
          post({ spot: round.spot, done: [state.right, state.asked] });
        }
        moved = true;
        drawRound();
      });
      body.appendChild(next);
    }
    if (moved) {
      moved = false;
      var to = shown ? next : options.querySelector("button");
      if (to && to.focus) to.focus();
    }
  }

  function choose(item, n) {
    state.chosen = n;
    var right = n === item.answer;
    state.asked += 1;
    if (right) state.right += 1;
    post({ spot: state.round.spot, key: item.key, right: right });
    moved = true;
    drawRound();
  }

  window.TargumGrammar = { loaded: ask("").then(draw) };
})();
