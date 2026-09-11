/* Runs the Learn page's script against a stub document and reports what it drew.
 *
 *   node tests/js/learn.js payload.json
 *
 * The page a reader lands on: how many words they know, the three doors, the shelf, and
 * the two lists of what they are learning. What comes back is what each of those decided
 * — the count, the carry title and its cover, the shelf rows, and the word and phrase
 * rows the lists drew.
 *
 * The two charts and the vocabulary editor are stubbed: they draw into an SVG and are not
 * what this is for. `collect()` is real, because the lists and the count are both drawn
 * from it and stubbing it would leave the test asserting against its own fixture.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const windowListeners = {};
install({
  TARGUM_KEY: "k",
  TARGUM_LANGUAGES: { he: "Hebrew" },
  addEventListener: (type, handler) => {
    (windowListeners[type] = windowListeners[type] || []).push(handler);
  },
  // The bell (2026-09-11): what the page told it.
  TargumNotices: { note: (id, text, extra) => notices.push({ id, text, href: (extra || {}).href || "" }) },
  TARGUM_CATALOGUE: payload.catalogue || [],
  // The drawer (2026-09-11): what the page asked it to do.
  TargumTalk: { show: (on) => talks.push(on), open: (id) => talks.push("open:" + id) },
  stored: payload.stored || {},
  TargumLang: {
    HOME: "he",
    order: (codes) => codes,
    current: () => "he",
    // The switcher draws; the caller remembers. Both are asked for now.
    set: () => {},
    into: () => "",
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

/* The two form controls the word table reads on every draw. A stub element has no
   `value`, and the page asks for `search.value.trim()` before it has drawn a row. The
   filter starts where the markup starts it: still learning, not everything. */
byId.search = Object.assign(element("input"), { value: payload.search || "" });
byId["status-filter"] = Object.assign(element("select"), { value: payload.filter || "learning" });

/* The real vocabulary module, because the rows it draws carry its copy control; the
   move it runs on load and the editor it draws into a row are still not what this is
   for, and are stubbed back out. */
require(path.join(assets, "vocab.js"));
global.window.TargumVocab.migrate = () => {};
global.window.TargumVocab.editor = () => element("div");

require(path.join(assets, "charts.js"));
// After charts.js and before the page, so the page binds these rather than the real ones.
global.window.TargumCharts.growth = () => {};
global.window.TargumCharts.tiles = () => {};

require(path.join(assets, "covers.js"));
require(path.join(assets, "shelf.js"));
require(path.join(assets, "scenes.js"));
require(path.join(assets, "follow.js"));
require(path.join(assets, "learn.js"));

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

/** The word rows the table drew: term, dictionary form, meaning, how well. */
function words() {
  return at("word-rows")
    .children.filter((row) => !String(row.className).includes("editor-row"))
    .map((row) => {
      const cells = row.children.map((cell) => cell.textContent);
      // The meaning's own language, which the cell has to carry: it is written in one
      // language inside a page written in another.
      const said = row.children[2] || {};
      return {
        term: cells[0],
        lemma: cells[1],
        meaning: cells[2],
        lang: said.getAttribute ? said.getAttribute("lang") || "" : "",
        dir: said.getAttribute ? said.getAttribute("dir") || "" : "",
        well: cells[4],
      };
    });
}

/** Phrases, grouped the way the page grouped them: {text: [phrase, ...]}. */
function phrases() {
  const out = {};
  at("phrase-list").children.forEach((group) => {
    const [head, list] = group.children;
    out[head.textContent] = list.children.map((item) => item.children[0].textContent);
  });
  return out;
}

/** Do something to the page, the way a person would. */
function act(step) {
  if (step.press) byId[step.press].fire("click", {});
  // A door in the row above the sheet (2026-09-11), by its id.
  if (step.door) {
    const found = at("doors").children.find((p) => p.attrs["data-door"] === step.door);
    if (found) found.fire("click", {});
  }
  // A text offered by the conversation in the drawer, handed over by `talk.js`.
  if (step.offer) global.window.TargumLearn.open(step.offer);
  if (step.changed) global.window.TargumLearn.changed();
}

setTimeout(() => {
  (payload.do || []).forEach(act);
  const carry = at("carry-cover");
  process.stdout.write(
    JSON.stringify({
      asked: asked,
      went: global.location.href,
      known: at("known-line").textContent,
      // The greeting and today, and the row of doors (2026-09-11).
      greeting: at("greeting").textContent,
      today: at("today").textContent,
      doors: at("doors").hidden
        ? []
        : at("doors").children.map((p) => ({ id: p.attrs["data-door"], label: p.textContent, on: p.classList.contains("on") })),
      hands: Object.keys(global.window.TargumLearn || {}),
      seeAll: { shelf: at("shelf-more").hidden ? "" : at("shelf-more").textContent },
      shelfNote: at("shelf-note").textContent,
      carry: {
        english: at("carry-english").hidden ? "" : at("carry-english").textContent,
        known: at("carry-known").hidden ? "" : at("carry-known").textContent,
        title: at("carry-title").textContent,
        hidden: at("carry-sheet").hidden,
        // The window: the reader itself, framed as a picture (§13, 2026-09-11).
        frame: at("carry-window").hidden ? "" : at("carry-frame").getAttribute("src") || "",
        heading: at("carry-heading").textContent,
        track: at("carry-track").hidden ? "" : at("carry-track").textContent,
        meta: at("carry-meta").textContent,
        primary: at("carry").classList.contains("primary"),
        entry: at("carry").getAttribute("data-entry") || "",
        cover: tile(carry),
        // Open, in the foot, goes to the reader's own page.
        href: at("carry").href || "",
        // How far through: the line's share, or nothing while it is hidden.
        progress: at("carry-progress").hidden ? "" : String(at("carry-progress").style["--done"] || ""),
      },
      // A subscription that landed (2026-09-11): what the bell was told, what was seen.
      notices,
      talks,
      wheres,
      seen: JSON.parse(global.localStorage.getItem("targum:series-seen") || "{}"),
      head: at("shelf-head").hidden,
      shelf: at("library-list").children.map((row) => {
        const link = row.children[0];
        const controls = row.children[1];
        const cells = (link.children || []).map((child) => child.textContent);
        // The title cell holds the Hebrew title and, under it, its English if any.
        const what = link.children[1] || { children: [] };
        const part = (name) => (what.children.find((c) => c.className === name) || {}).textContent || "";
        return {
          cover: tile(link),
          // thumb, title, chapters, last opened — one cell each, in column order.
          title: part("book-title") || cells[1] || "",
          english: part("book-english"),
          chapters: cells[2] || "",
          opened: cells[3] || "",
          controls: controls ? controls.children.map((c) => c.textContent) : [],
        };
      }),
    })
  );
}, 30);
