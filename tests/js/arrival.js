/* Runs the arrival's script against a stub document and reports what it drew.
 *
 *   node tests/js/arrival.js payload.json
 *
 * The three questions a new reader is asked on `/welcome` (design.md §12, "The arrival is
 * three plain questions", 2026-10-09): which screen is up, what it offers, what the
 * answers kept and posted, and where the page went — into the text the last answer
 * chose, or home in the language chosen.
 * `first` is that choice for the shelf as given, which is what home's "One to start
 * with" stands in for once the questions are answered.
 *
 * `collect()` is real, because the rung is seeded from the words the reader has marked
 * and stubbing it would leave the test asserting against its own fixture.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const windowListeners = {};
// The browser's languages (2026-09-28): the arrival asks which language a reader reads
// only where one of them is of the Russian-reading world. English unless a test says.
const browserLanguages = payload.browser || ["en-US"];
install({
  TARGUM_KEY: "k",
  navigator: { language: browserLanguages[0], languages: browserLanguages },
  TARGUM_LANGUAGES: {
    he: "Hebrew",
    ru: "Russian",
    fr: "French",
    it: "Italian",
    arc: "Aramaic",
    yi: "Yiddish",
  },
  TARGUM_STRINGS: payload.strings,
  addEventListener: (type, handler) => {
    (windowListeners[type] = windowListeners[type] || []).push(handler);
  },
  // The bell (2026-09-11): what the page told it.
  TargumNotices: { note: (id, text, extra) => notices.push({ id, text, href: (extra || {}).href || "" }) },
  TARGUM_CATALOGUE: payload.catalogue || [],
  // The languages a translation can be in (2026-09-20). None unless a test says, so the
  // arrival asks which one a reader reads only in the tests that are about that.
  TARGUM_INTO: payload.into || [],
  // The drawer (2026-09-11): what the page asked it to do.
  TargumTalk: { show: (on) => talks.push(on), open: (id) => talks.push("open:" + id) },
  stored: payload.stored || {},
  TargumLang: {
    HOME: "he",
    order: (codes) => codes,
    // The language the switcher shows, where a test says one.
    current: () => payload.language || "he",
    learning: () => [payload.language || "he"],
    // The switcher draws; the caller remembers. What the arrival set is reported.
    set: (code) => {
      languageSet = code;
    },
    // The menu's own badge, as `lang.js` draws it: a span with the word.
    badge: (code) => {
      const which = { he: "Beta", ru: "Alpha", fr: "Alpha", it: "Alpha" }[code] || "Experimental";
      const mark = element("span");
      mark.className = "lang-status";
      mark.textContent = which;
      return mark;
    },
    // What this browser reads into: what a test says it already holds, then whatever the
    // page tells it.
    into: (code) => {
      if (code !== undefined) heldInto = code;
      return heldInto;
    },
    switcher: () => {},
    beta: () => false,
    betaNote: () => "",
  },
});

/* Every call the page makes, in order. The shelf only ever asked for `/readers` and one
   answer served; pressing the suggestion starts a build, and what a test needs to know
   about that is which text was sent — a card that offered one book and built its
   neighbour would be unnoticeable and expensive. */
const asked = [];
let heldInto = payload.held || "";
let languageSet = "";
let reloaded = 0;
/* One visit's store, for what has to outlive the page being loaded again in the language
   a reader chose. A test says what the visit already holds. */
const visit = Object.assign({}, payload.visit || {});
global.window.sessionStorage = {
  getItem: (key) => (key in visit ? visit[key] : null),
  setItem: (key, value) => {
    visit[key] = String(value);
  },
};
global.location.reload = () => {
  reloaded += 1;
};
// Home, where the arrival sends anybody it has nothing to ask (`arrival.js`).
let replaced = "";
global.location.replace = (where) => {
  replaced = String(where);
};
global.document.documentElement.lang = payload.pageLanguage || "en";
const notices = [];
const talks = [];
const wheres = [];
global.CustomEvent = function (type, init) {
  this.type = type;
  this.detail = init && init.detail;
};
global.document.dispatchEvent = (event) => wheres.push(event.detail);

global.fetch = (path, options) => {
  asked.push({
    path: String(path),
    body: options && options.body ? JSON.parse(options.body) : null,
  });
  let answer = { id: "j1" }; // enough for `/prepare` to hand `/build` an id
  if (String(path).indexOf("/readers") === 0) {
    answer = { readers: payload.readers || [], shared: payload.shared || [], trash: [], covers: true };
  } else if (String(path).indexOf("/series") === 0) {
    answer = { series: payload.series || [] };
  } else if (String(path).indexOf("/account/me") === 0) {
    answer = payload.me || { signedIn: false };
  } else if (String(path).indexOf("/suggest") === 0) {
    answer = { suggestion: payload.suggest || null };
  } else if (String(path).indexOf("/account/follows") === 0) {
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
  } else if (String(path).indexOf("/job/") === 0) {
    /* Finished on the first ask. A job that never reaches "done" leaves the page polling
       it every 700ms, and node does not exit while a timer is pending — the first run of
       this hung for two minutes rather than failing. */
    answer = { stage: "done", reader: "built" };
  }
  return Promise.resolve({ json: () => Promise.resolve(answer) });
};

/* An SVG element is made through createElementNS, which the stub document has no need of
   until a page draws a chart. Same plain element: nothing here reads a namespace. */
global.document.createElementNS = (namespace, tag) => element(tag);

require(path.join(assets, "strings.js"));
require(path.join(assets, "charts.js"));

require(path.join(assets, "covers.js"));
require(path.join(assets, "shelf.js"));
require(path.join(assets, "scenes.js"));
// The day the fixtures were written about, so "new for a week" is decided by them and
// not by the day the suite happens to run.
global.window.TargumClock = Object.assign({}, global.window.TargumClock, {
  now: () => Date.parse(payload.now || "2026-09-14T12:00:00Z"),
});
require(path.join(assets, "follow.js"));
require(path.join(assets, "arrival.js"));

/** A tile, if one was drawn there: its class, and the letter it rests on. */
function tile(node) {
  const found = (node.children || []).find((child) => String(child.className).includes("thumb"));
  if (!found) return null;
  const glyph = found.children[0];
  return { className: found.className, letter: glyph ? glyph.textContent : "" };
}

/* An id the page never asked for was never created — which is itself an answer: with an
   empty shelf, nothing draws a carry panel at all. */
const at = (id) => byId[id] || { textContent: "", children: [], hidden: true, href: "" };

/** Do something to the page, the way a person would. */
function act(step) {
  if (step.press) byId[step.press].fire("click", {});
  // A rung of the ladder on the arrival's second screen, by its words.
  if (step.rung) {
    const row = Array.from(at("arrival-levels").children).find(
      (p) => p.textContent.indexOf(step.rung) === 0
    );
    if (row) row.fire("click", {});
  }
  // A language on the arrival's first screen, by its own name (2026-09-20).
  if (step.tongue) {
    const press = Array.from(at("arrival-tongues").children).find(
      (p) => p.textContent === step.tongue
    );
    if (press) press.fire("click", {});
  }
  // A language on the first of the three, by its name (2026-10-09).
  if (step.learn) {
    const card = Array.from(at("arrival-langs").children).find(
      (p) => p.textContent.indexOf(step.learn) >= 0
    );
    if (card) card.fire("click", {});
  }
  // "I'm not sure, show me a page", under the levels.
  if (step.unsure) byId["arrival-unsure"].fire("click", {});
  // Back, in the foot at a desk and as a chevron on a phone: the same press.
  if (step.back) byId["arrival-back"].fire("click", {});
  // A code on the arrival's EN · RU switch (2026-09-28).
  if (step.switchTo) {
    const key = Array.from(at("arrival-switch").children).find(
      (p) => p.textContent === step.switchTo
    );
    if (key) key.fire("click", {});
  }
  // A subject on the arrival, by its label.
  if (step.subject) {
    const chip = Array.from(at("arrival-doors").children).find(
      (p) => p.textContent === step.subject
    );
    if (chip) chip.fire("click", {});
  }
}

setTimeout(() => {
  (payload.do || []).forEach(act);
  /* Read a beat later, not in the same tick as the last press (2026-09-20): choosing a
     language tells the account first and goes on when the account has answered. */
  setTimeout(() => setTimeout(report, 10), 10);
}, 30);

function report() {
  const shared = (payload.shared || []).filter((row) => (row.language || "he") === "he");
  const first = global.window.TargumArrival ? global.window.TargumArrival.firstText(shared, "he") : null;
  process.stdout.write(
    JSON.stringify({
      asked: asked,
      went: global.location.href,
      // Home, where the page sent a reader it had nothing to ask (or who finished with
      // nothing the shelf could open).
      home: replaced,
      first: first ? first.title : "",
      arrival: at("arrival").hidden
        ? []
        : Array.from(at("arrival-doors").children).map((p) => p.textContent),
      picked: at("arrival").hidden
        ? []
        : Array.from(at("arrival-doors").children)
            .filter((p) => p.getAttribute("aria-pressed") === "true")
            .map((p) => p.textContent),
      levels:
        at("arrival").hidden || at("arrival-level").hidden
          ? []
          : Array.from(at("arrival-levels").children).map((p) => p.textContent),
      tongues:
        at("arrival").hidden || at("arrival-language").hidden
          ? []
          : Array.from(at("arrival-tongues").children).map((p) => p.textContent),
      tongueAsks: Array.from(at("arrival-asks-language").children || []).map((p) => p.textContent),
      switchKeys:
        at("arrival").hidden || at("arrival-switch").hidden
          ? []
          : Array.from(at("arrival-switch").children).map((p) => p.textContent),
      heldInto,
      reloaded,
      visit,
      backShown: !at("arrival").hidden && !at("arrival-back").hidden,
      step: at("arrival").hidden || at("arrival-step").hidden ? "" : at("arrival-step").textContent,
      subjectsUp: !at("arrival").hidden && !at("arrival-subjects").hidden,
      done: at("arrival").hidden ? null : !at("arrival-done").disabled,
      nextShown: !at("arrival").hidden && !at("arrival-done").hidden,
      learningUp: !at("arrival").hidden && !at("arrival-learning").hidden,
      levelUp: !at("arrival").hidden && !at("arrival-level").hidden,
      langs: at("arrival").hidden
        ? []
        : Array.from(at("arrival-langs").children).map((p) => p.textContent),
      chosen: at("arrival").hidden
        ? ""
        : (Array.from(at("arrival-langs").children).find(
            (p) => p.getAttribute("aria-checked") === "true"
          ) || { getAttribute: () => "" }).getAttribute("data-code"),
      levelAsks: at("arrival-asks-level").textContent,
      footNote: at("arrival-foot-note").hidden ? "" : at("arrival-foot-note").textContent,
      languageSet,
      doneSays: at("arrival-done").textContent,
      arriving: global.document.body.classList.contains("arriving"),
      kept: (() => {
        const out = {};
        for (let i = 0; i < global.localStorage.length; i++) {
          const key = global.localStorage.key(i);
          out[key] = global.localStorage.getItem(key);
        }
        return out;
      })(),
      posted: asked.map((call) => call.path),
      sent: asked.filter((call) => call.body).map((call) => ({ path: call.path, body: call.body })),
    })
  );
}
