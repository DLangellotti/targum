/* Runs the list before a chapter against a stub page and says what it showed.
 *
 *   node tests/js/preread.js payload.json
 *
 * The payload is the list as the page carries it (`rows`, lemmas in the page's order),
 * how many it shows (`shown`), the ledger this browser holds (`vocab`), and optionally
 * a ledger the account hands over afterwards (`synced`). The answer is which rows are
 * on show before and after, the number in the fold's line, and whether the fold is
 * drawn at all.
 *
 * The rows are handed to the fold directly: the stub's selectors are classes only, and
 * the markup under test here is the template's, which `test_preread.py` reads as HTML.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");
const listeners = [];

install({
  stored: { "targum:vocab:he": JSON.stringify(payload.vocab || {}) },
  TargumSync: {
    onChange(listener) {
      listeners.push(listener);
    },
  },
});
document.documentElement.setAttribute("lang", "en");
document.documentElement.setAttribute("data-language", "he");

const box = document.getElementById("preread");
if (payload.shown) box.setAttribute("data-shown", String(payload.shown));
const rows = (payload.rows || []).map((lemma) => {
  const row = element("li");
  row.setAttribute("data-lemma", lemma);
  return row;
});
box.querySelectorAll = () => rows;

function seen() {
  return {
    on: rows.filter((row) => !row.hidden).map((row) => row.getAttribute("data-lemma")),
    total: byId["preread-total"] ? byId["preread-total"].textContent : null,
    drawn: !box.hidden,
  };
}

document.getElementById("preread-total");
require(path.join(assets, "preread.js"));
const before = seen();

let after = null;
if (payload.synced) {
  localStorage.setItem("targum:vocab:he", JSON.stringify(payload.synced));
  listeners.forEach((listener) => listener(true));
  after = seen();
}

process.stdout.write(JSON.stringify({ before, after }));
