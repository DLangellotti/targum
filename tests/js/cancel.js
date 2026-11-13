/* Cancel on a reader's own build (targum-internal#694), run rather than read: Your
 * targums' building row, Home's getting-ready card, and the waiting card's line about
 * the builds ahead, each drawn from `cancel.js`, and pressed.
 *
 *   node tests/js/cancel.js payload.json
 *
 * The payload is `{job, press, answers}`: the build as `/jobs` lists it, which place to
 * draw it in (`row`, `card` or `ahead`), how many presses to make on the first button
 * each time (`press`), and what `/jobs/cancel` and `/job/<id>` answer. What comes back
 * is the words and presses drawn before and after, and every request made.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const asked = [];
const answers = payload.answers || {};
install({
  TARGUM_KEY: "k",
  TARGUM_LANGUAGES: { he: "Hebrew", en: "English" },
  TargumLang: { HOME: "he", order: (codes) => codes, current: () => "he", set: () => {} },
});
global.fetch = (address, options) => {
  const where = String(address).split("?")[0];
  asked.push({ path: where, method: (options && options.method) || "GET", body: options && options.body ? JSON.parse(options.body) : null });
  const answer = answers[where] || {};
  return Promise.resolve({ ok: true, json: () => Promise.resolve(answer) });
};
global.window.fetch = global.fetch;
// Nothing waits: a stopping build's follow-up is asked once, at once.
let timers = 0;
global.setTimeout = (fn) => {
  timers += 1;
  if (timers < 5) Promise.resolve().then(fn);
  return 0;
};
global.window.setTimeout = global.setTimeout;

require(path.join(assets, "strings.js"));
require(path.join(assets, "charts.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "cancel.js"));
require(path.join(assets, "shelf.js"));
require(path.join(assets, "home.js"));

function walk(node, out) {
  if (!node) return out;
  const tag = String(node.tagName || "").toLowerCase();
  if (tag === "button") {
    out.presses.push({ text: node.textContent, className: node.className, label: (node.attrs || {})["aria-label"] || "" });
    return out;
  }
  if (node.hidden) return out;
  if (node.textContent && (!node.children || !node.children.length)) out.words.push(node.textContent);
  (node.children || []).forEach((child) => walk(child, out));
  return out;
}

function buttons(node, found) {
  if (!node) return found;
  if (String(node.tagName || "").toLowerCase() === "button") found.push(node);
  (node.children || []).forEach((child) => buttons(child, found));
  return found;
}

function drawn() {
  const job = payload.job;
  if (payload.place === "row") return global.window.TargumShelf.buildingRow(job);
  if (payload.place === "card") return global.window.TargumHome.buildCard(job);
  return global.window.TargumCancel.ahead(job, {}) || document.createElement("div");
}

const host = document.createElement("div");
host.appendChild(drawn());
const before = walk(host, { words: [], presses: [] });

(async () => {
  for (const which of payload.press || []) {
    const all = buttons(host, []);
    const press = all.find((one) => one.textContent === which) || null;
    if (!press) break;
    press.click();
    for (let i = 0; i < 10; i += 1) await Promise.resolve();
  }
  const after = walk(host, { words: [], presses: [] });
  process.stdout.write(JSON.stringify({ before, after, asked, gone: host.children.length === 0 }));
})();
