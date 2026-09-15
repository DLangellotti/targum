/* Runs the parasha page's script against a stub document and reports which parts of this
 * week's reading it marked as read.
 *
 *   node tests/js/parasha.js payload.json
 *
 * The list is the template's; this is what the script does with it (targum-internal#203):
 * a part is read when the reader finished it after the week began, and nothing else.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

// Each part as the template draws it: a link carrying its document, section and the week,
// with the word "read" inside it, hidden.
const parts = (payload.parts || []).map((given) => {
  const link = element("a");
  link.className = "week-part";
  link.setAttribute("data-document", given.document);
  link.setAttribute("data-section", String(given.section || 0));
  link.setAttribute("data-sections", String(given.sections || 0));
  link.setAttribute("data-began", String(payload.began));
  link.removeAttribute = (name) => delete link.attrs[name];
  const said = element("span");
  said.className = "read";
  said.hidden = true;
  link.appendChild(said);
  return link;
});

const heard = {};
install({
  stored: { "targum:docs": JSON.stringify(payload.docs || {}) },
  selectors: { ".week-part": parts },
});
global.window.addEventListener = (type, handler) => {
  heard[type] = handler;
};

require(path.join(assets, "parasha.js"));

const marks = () =>
  parts.map((link) => ({
    read: "data-read" in link.attrs,
    said: !link.children[0].hidden,
  }));
const first = marks();

// A finish written inside a frame arrives as a storage event on this window.
let after = null;
if (payload.later) {
  localStorage.setItem("targum:docs", JSON.stringify(payload.later));
  if (heard.storage) heard.storage({ key: "targum:docs" });
  after = marks();
}

process.stdout.write(JSON.stringify({ first, after }));
