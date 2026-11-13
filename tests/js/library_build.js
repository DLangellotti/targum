/* Presses a Library row's build and follows it, against scripted answers.
 *
 *   node tests/js/library_build.js payload.json
 *
 * The payload is `tests/js/library.js`'s (a catalogue, the view, the hash) plus `press`:
 * the row's id, what `/prepare` answers, the `/job/<id>` answers in order (the last one
 * repeats), and what `/jobs/cancel` answers. The page's interval is driven by hand: each
 * tick is one poll, and what the row says after it is reported, with whether the row's
 * Cancel is there, whether its press can be pressed again and whether the poll stopped.
 *
 * Read by `tests/test_library_js.py` (targum-internal#696, P1-3).
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");
const press = payload.press;

const byId = install({
  TARGUM_KEY: "k",
  TARGUM_CATALOGUE: payload.catalogue,
  TARGUM_COLLECTIONS: payload.collections || [],
  TARGUM_SETS: [],
  TARGUM_LANGUAGES: { he: "Hebrew", ru: "Russian" },
  TARGUM_STRINGS: payload.strings,
  stored: { "targum:library": JSON.stringify(payload.view || { shape: "list" }) },
  TargumLang: {
    HOME: "he",
    order: (codes) => codes,
    current: () => "he",
    set: () => {},
    into: () => "",
    switcher: () => {},
    beta: () => false,
    betaNote: () => "",
  },
});
global.history = global.window.history = { replaceState: () => {} };
global.location.hash = "#see";

/* The page's poll, by hand. */
const intervals = new Map();
let nextTimer = 1;
global.setInterval = global.window.setInterval = (fn) => {
  const id = nextTimer++;
  intervals.set(id, fn);
  return id;
};
global.clearInterval = global.window.clearInterval = (id) => intervals.delete(id);

const asked = [];
let polls = 0;
const answer = (address, body) => {
  const where = String(address);
  asked.push(where.split("?")[0]);
  if (where.indexOf("/prepare") >= 0) return press.prepare;
  if (where.indexOf("/jobs/cancel") >= 0) return press.cancel || {};
  if (where.indexOf("/build") >= 0) return { stage: "queued" };
  if (where.indexOf("/job/") >= 0) {
    const at = Math.min(polls, press.jobs.length - 1);
    polls += 1;
    return press.jobs[at];
  }
  if (where.indexOf("/jobs") >= 0) return { jobs: [] };
  return { readers: [], shared: [], covers: false, catalogue: {}, signedIn: true };
};
global.fetch = (address, options) =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(answer(address, options && options.body)) });

require(path.join(assets, "strings.js"));
require(path.join(assets, "charts.js"));
require(path.join(assets, "scenes.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "cancel.js"));
require(path.join(assets, "library.js"));

const settle = () => new Promise((resolve) => setTimeout(resolve, 5));
const wearing = (node, name) => String(node.className || "").split(" ").indexOf(name) >= 0;

function rowOf(id) {
  const hosts = [byId["catalogue"], byId["cards"]].filter(Boolean);
  for (const host of hosts) {
    const hit = (host.children || []).find((c) => c.getAttribute && c.getAttribute("data-row") === id);
    if (hit) return { host, item: hit };
  }
  return null;
}

(async () => {
  await settle();
  const found = rowOf(press.id);
  if (!found) throw new Error("no row " + press.id);
  const { host, item } = found;
  // The stub has no insertBefore and no closest; a browser has both.
  item.insertBefore = function (node, before) {
    const at = this.children.indexOf(before);
    if (at < 0) this.children.push(node);
    else this.children.splice(at, 0, node);
    node.parentNode = this;
    return node;
  };
  const open = item.children.find((c) => c.getAttribute("data-build") === press.id);
  open.closest = (selector) => (selector === "[data-build]" ? open : null);
  host.fire("click", { target: open });
  await settle();
  const go = item.children.find((c) => wearing(c, "row-go"));
  if (!go) throw new Error("no ask on the row");
  go.fire("click", {});
  await settle();

  const state = open.querySelector(".row-state");
  // The stub's classList keeps its own set and never writes className back.
  const cancelOf = () => item.children.find((c) => c.classList && c.classList.contains("row-cancel")) || null;
  const ticks = [];
  for (let n = 0; n < (press.ticks || 3); n++) {
    intervals.forEach((fn) => fn());
    await settle();
    const undo = cancelOf();
    ticks.push({
      says: state.textContent,
      cancel: undo ? undo.textContent : null,
      polling: intervals.size > 0,
      pressable: !open.disabled,
    });
    if (press.cancelAt === n && undo) {
      const button = undo.children.find((c) => c.tagName === "button");
      button.fire("click", {});
      await settle();
      const after = cancelOf();
      ticks.push({
        says: state.textContent,
        cancel: after ? after.textContent : null,
        polling: intervals.size > 0,
        pressable: !open.disabled,
        pressed: "cancel",
      });
    }
  }
  process.stdout.write(JSON.stringify({ ticks, asked }));
  process.exit(0);
})().catch((problem) => {
  process.stderr.write(String((problem && problem.stack) || problem));
  process.exit(1);
});
