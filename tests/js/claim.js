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

// The template draws the panel hidden until there are rows, with an empty body the
// script builds the table into (2026-09-11); the stub starts it that way.
document.getElementById("claim-panel").hidden = true;
const body = document.getElementById("claim-body");
require(path.join(assets, "claim.js"));
// The parts, by the class each carries: the script builds them, so none has an id
// the stub would know.
const part = (name) => body.querySelector("." + name) || { hidden: true, children: [], textContent: "" };

(async () => {
  for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
  const boxOf = (form) =>
    (part("claim-rows").children || [])
      .map((tr) => tr.children[0].children[0])
      .find((box) => box.attrs["data-form"] === form);
  for (const step of payload.do || []) {
    // The button is a real one: disabled, a press does nothing, as in a browser.
    if (step.type === "yes" && !part("claim-yes").disabled) part("claim-yes").onclick();
    if (step.type === "no") part("claim-no").onclick();
    if (step.type === "check") {
      const box = boxOf(step.form);
      box.checked = step.on !== false;
      box.onchange();
    }
    if (step.type === "all") {
      part("claim-all").checked = step.on !== false;
      part("claim-all").onchange();
    }
    for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
  }
  console.log(
    JSON.stringify({
      asked,
      hidden: byId["claim-panel"].hidden,
      rows: (part("claim-rows").children || []).map((tr) => ({
        form: tr.children[1].textContent,
        meaning: tr.children[2].textContent,
        band: tr.children[3].textContent,
        checked: !!tr.children[0].children[0].checked,
        labelled: tr.children[1].children[0].attrs["for"] === tr.children[0].children[0].id,
      })),
      yesDisabled: !!part("claim-yes").disabled,
      all: { checked: !!part("claim-all").checked, some: !!part("claim-all").indeterminate },
      said: part("claim-said").textContent,
      ledger: JSON.parse(global.localStorage.getItem("targum:vocab:he") || "{}"),
      passed: JSON.parse(global.localStorage.getItem("targum:claim-passed") || "{}"),
      touched,
    }),
  );
})();
