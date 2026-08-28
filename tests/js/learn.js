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

/* The fold buttons and the bodies they fold come from the template, so a stub document
   has neither. Built here, wired the way the markup wires them — a button inside a panel
   that also holds a `.fold-body` — because what is being tested is what learn.js does
   with them: the toggle, the aria, and remembering it. */
function foldPair(name) {
  const body = element("div");
  body.id = name + "-body";
  const panel = element("section");
  panel.querySelector = (selector) => (selector === ".fold-body" ? body : null);
  const press = element("button");
  press.closest = () => panel;
  byId["fold-" + name] = press;
  byId[name + "-body"] = body;
  return press;
}

const folds = ["shelf", "words", "phrases"].map(foldPair);

install({
  TARGUM_KEY: "k",
  TARGUM_LANGUAGES: { he: "Hebrew" },
  TARGUM_CATALOGUE: payload.catalogue || [],
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
  TargumVocab: { migrate: () => {}, editor: () => element("div") },
  selectors: { ".fold": folds },
});

/* Every call the page makes, in order. The shelf only ever asked for `/readers` and one
   answer served; pressing the suggestion starts a build, and what a test needs to know
   about that is which text was sent — a card that offered one book and built its
   neighbour would be unnoticeable and expensive. */
const asked = [];

global.fetch = (path, options) => {
  asked.push({
    path: String(path),
    body: options && options.body ? JSON.parse(options.body) : null,
  });
  let answer = { id: "j1" }; // enough for `/prepare` to hand `/build` an id
  if (String(path).indexOf("/readers") === 0) {
    answer = { readers: payload.readers || [], shared: payload.shared || [], trash: [], covers: true };
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

require(path.join(assets, "charts.js"));
// After charts.js and before the page, so the page binds these rather than the real ones.
global.window.TargumCharts.growth = () => {};
global.window.TargumCharts.tiles = () => {};

require(path.join(assets, "lists.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "shelf.js"));
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
  if (step.fold) byId["fold-" + step.fold].fire("click", {});
  if (step.press) byId[step.press].fire("click", {});
}

setTimeout(() => {
  (payload.do || []).forEach(act);
  const carry = at("carry-cover");
  process.stdout.write(
    JSON.stringify({
      asked: asked,
      went: global.location.href,
      known: at("known-line").textContent,
      progress: at("step-progress").textContent,
      suggested: at("suggest").hidden
        ? null
        : {
            heading: at("suggest-heading").textContent,
            title: at("suggest-title").textContent,
            why: at("suggest-why").textContent,
            blurb: at("suggest-blurb").textContent,
            cover: tile(at("suggest-cover")),
            // A button has no href. What it is offering is on the card itself.
            entry: at("suggest").getAttribute("data-entry"),
            disabled: at("suggest").disabled,
          },
      seeAll: {
        shelf: at("shelf-more").hidden ? "" : at("shelf-more").textContent,
        words: at("words-more").hidden ? "" : at("words-more").textContent,
        phrases: at("phrases-more").hidden ? "" : at("phrases-more").textContent,
      },
      folds: ["shelf", "words", "phrases"].reduce(function (out, name) {
        out[name] = {
          open: byId["fold-" + name].getAttribute("aria-expanded"),
          shown: !byId[name + "-body"].hidden,
        };
        return out;
      }, {}),
      remembered: global.localStorage.getItem("targum:folded") || "",
      exports: {
        words: at("export-words").hidden,
        phrases: at("export-phrases").hidden,
      },
      words: words(),
      wordsTitle: at("words-title").textContent,
      wordsEmpty: at("words-empty").hidden ? "" : at("words-empty").textContent,
      editors: at("word-rows").children.filter((row) =>
        String(row.className).includes("editor-row")
      ).length,
      phrases: phrases(),
      phrasesTitle: at("phrases-title").textContent,
      carry: {
        known: at("carry-known").hidden ? "" : at("carry-known").textContent,
        title: at("carry-title").textContent,
        hidden: at("carry").hidden,
        heading: at("carry-heading").textContent,
        cover: tile(carry),
        // The box is the link now, so this is where the href is.
        href: at("carry").href || "",
      },
      head: at("shelf-head").hidden,
      shelf: at("library-list").children.map((row) => {
        const link = row.children[0];
        const controls = row.children[1];
        const cells = (link.children || []).map((child) => child.textContent);
        return {
          cover: tile(link),
          // thumb, title, chapters, last opened — one cell each, in column order.
          title: cells[1] || "",
          chapters: cells[2] || "",
          opened: cells[3] || "",
          controls: controls ? controls.children.map((c) => c.textContent) : [],
        };
      }),
    })
  );
}, 30);
