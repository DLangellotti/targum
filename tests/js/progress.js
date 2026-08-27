/* Runs the Your Progress page's script against a stub document and reports the ledger.
 *
 *   node tests/js/progress.js payload.json
 *
 * The page's arithmetic is the thing worth running: how many words count as known, which
 * milestone that has passed, how many are left to the next one, and which of the last
 * twelve weeks of days were read on. All of it was written here and none of it is
 * checked by a parse check or a grep.
 *
 * The growth line and the tiles are stubbed — they draw into an SVG and are not what
 * this is for. Everything else, including `collect()`, is the page's own code. The word
 * table and the phrase list used to be stubbed here too; they live on Learn now, and
 * `tests/js/learn.js` runs them.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

install({
  TARGUM_KEY: "k",
  TARGUM_LANGUAGES: { he: "Hebrew" },
  stored: payload.stored || {},
  TargumLang: {
    HOME: "he",
    order: (codes) => codes.sort(),
    current: (codes) => codes[0],
    // The switcher draws; the caller remembers. Both are asked for now.
    set: () => {},
    into: () => "",
    switcher: () => {},
    beta: () => false,
    betaNote: () => "",
  },
  TargumVocab: { migrate: () => {}, editor: () => element("div") },
});

/* `collect()` walks localStorage by index, which the shared stub does not offer: it
   reports a length of zero and hands back null for every key. The page cannot be run at
   all without that, so the store is replaced here rather than in dom.js — the reader and
   library harnesses want the inert one. */
const store = payload.stored || {};
const names = Object.keys(store);
global.localStorage = {
  get length() {
    return names.length;
  },
  key: (i) => (i < names.length ? names[i] : null),
  getItem: (name) => (name in store ? store[name] : null),
  setItem: () => {},
};

/* An SVG element is made through createElementNS, which the stub document has no need of
   until a page draws a chart. Same plain element: nothing here reads a namespace. */
global.document.createElementNS = (namespace, tag) => element(tag);

require(path.join(assets, "charts.js"));
/* After charts.js and before the page, so the page binds these rather than the real
   ones. `collect` and `days` stay real — they are the shape everything else is drawn
   from, and stubbing them would leave the test asserting against its own fixture. */
global.window.TargumCharts.growth = () => {};

require(path.join(assets, "progress.js"));

const at = (id) => byId[id] || { textContent: "", children: [], hidden: true };

/** Every count in the block, as {label: number}. */
function counts() {
  const out = {};
  at("counts").children.forEach((box) => {
    const [value, label] = box.children;
    out[label.textContent] = Number(value.textContent.replace(/,/g, ""));
  });
  return out;
}

/** The same, as a list, for a test that wants the label and the figure together. */
function counts_() {
  return at("counts").children.map((box) => ({
    value: box.children[0] ? box.children[0].textContent : "",
    label: box.children[1] ? box.children[1].textContent : "",
    delta: box.children[2] ? box.children[2].textContent : "",
  }));
}

/** Which milestones are lit, and which are only listed. */
function marks() {
  const row = at("milestones").children[0];
  if (!row) return { on: [], off: [] };
  const on = [];
  const off = [];
  row.children.forEach((chip) => {
    const value = Number(chip.textContent.replace(/,/g, ""));
    (String(chip.className).includes("on") ? on : off).push(value);
  });
  return { on, off };
}

/* The rung lives in one of two places: Hebrew's ulpan ladder has a block of its own
   under the milestones, and every other language's milestone line sits under the chips it
   belongs to. Whichever drew is the one to report. */
const rung = at("rung-standing");
const standing = rung.children.length ? rung : at("standing");
const strip = at("days").children[0];

process.stdout.write(
  JSON.stringify({
    nothing: at("nothing").hidden === false,
    counts: counts(),
    reached: (standing.children.find((c) => String(c.className) === "reached") || { textContent: "" })
      .textContent,
    next: (standing.children.find((c) => String(c.className) === "next") || { textContent: "" })
      .textContent,
    marks: marks(),
    // Which band each marked word fell in, as the chart labelled them.
    bands: at("bands")
      .children.map((node) => node.textContent)
      .join(" "),
    progressNote: at("progress-note").textContent,
    // Every figure lives in the one block at the top now, so they are read from there.
    tiles: counts_(),
    ulpan: {
      shown: at("basis").hidden === false,
      rung: (standing.children.find((c) => String(c.className) === "reached") || {
        textContent: "",
      }).textContent,
      next: (standing.children.find((c) => String(c.className) === "next") || {
        textContent: "",
      }).textContent,
    },
    days: {
      cells: strip ? strip.children.length : 0,
      read: strip ? strip.children.filter((c) => String(c.className) === "read").length : 0,
      label: strip ? strip.getAttribute("aria-label") : "",
      said: (at("days").children[1] || { textContent: "" }).textContent,
    },
  })
);
