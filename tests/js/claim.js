/* Runs Words you may already know (`claim.js`) against a stub document and reports what
 * it drew and what it wrote (targum-internal#245).
 *
 *   node tests/js/claim.js payload.json
 *
 * The payload carries the pages `/words/common` answers, by offset, the ledger and the
 * passed-over list as the browser keeps them, and the presses to make.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const asked = [];
const touched = { sync: 0, lists: 0 };
const stored = {};
if (payload.ledger) stored["targum:vocab:he"] = JSON.stringify(payload.ledger);
if (payload.passed) stored["targum:claim-passed"] = JSON.stringify(payload.passed);

install({
  TARGUM_KEY: "k",
  stored,
  TargumLang: { current: () => payload.language || "he" },
  TargumSync: { touched: () => touched.sync++ },
  TargumLists: { changed: () => touched.lists++ },
});

global.fetch = (url) => {
  const clean = String(url).replace(/[?&]k=[^&]*/, "");
  asked.push(clean);
  const offset = Number((/offset=(\d+)/.exec(clean) || [0, 0])[1]);
  const answer = (payload.pages || {})[String(offset)] || { words: [], offset, next: null };
  return Promise.resolve({ json: () => Promise.resolve(answer) });
};

// The template draws the panel hidden until there are rows; the stub starts it that way.
document.getElementById("claim-panel").hidden = true;
require(path.join(assets, "claim.js"));

(async () => {
  for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
  for (const step of payload.do || []) {
    if (step.type === "yes") byId["claim-yes"].onclick();
    if (step.type === "no") byId["claim-no"].onclick();
    for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
  }
  console.log(
    JSON.stringify({
      asked,
      hidden: byId["claim-panel"].hidden,
      rows: (byId["claim-rows"].children || []).map((tr) => ({
        form: tr.children[0].textContent,
        meaning: tr.children[1].textContent,
        band: tr.children[2].textContent,
      })),
      said: byId["claim-said"].textContent,
      ledger: JSON.parse(global.localStorage.getItem("targum:vocab:he") || "{}"),
      passed: JSON.parse(global.localStorage.getItem("targum:claim-passed") || "{}"),
      touched,
    }),
  );
})();
