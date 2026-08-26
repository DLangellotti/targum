/* Runs the library page's own script against a stub document and reports what it drew.
 *
 *   node tests/js/library.js payload.json
 *
 * The payload carries the catalogue (as the page receives it), the readers the server
 * would answer with, and the view — the filters and sort a reader has chosen. What comes
 * back on stdout is JSON: the rows drawn, in order, and the controls around them.
 *
 * Read by `tests/test_library_js.py`, which supplies a real catalogue from the package
 * so the fixtures cannot drift from the thing being tested.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const byId = install({
  TARGUM_KEY: "k",
  TARGUM_CATALOGUE: payload.catalogue,
  TARGUM_LANGUAGES: { he: "Hebrew", ru: "Russian" },
  stored: { "targum:library": JSON.stringify(payload.view || {}) },
  // The language switcher is not what is under test, and the real one wants a document
  // to hang tabs off. Its answer is fixed here so the rows are the only variable.
  TargumLang: {
    HOME: "he",
    order: (codes) => codes,
    current: () => payload.language || "he",
    switcher: () => {},
    beta: () => false,
    betaNote: () => "",
  },
});

global.fetch = () =>
  Promise.resolve({ json: () => Promise.resolve({ readers: payload.readers || [], covers: !!payload.covers }) });

require(path.join(assets, "covers.js"));
require(path.join(assets, "library.js"));

// The page draws once its own request for /readers resolves. One turn of the microtask
// queue is enough; nothing here waits on a timer.
setTimeout(() => {
  const rows = byId["catalogue"].children;
  const read = (row) => {
    const open = row.children[0];
    return {
      title: open.children[1].children[0].textContent,
      cells: open.children.slice(2).map((cell) => cell.textContent.trim()),
      draws: row.children.length > 1 ? row.children[1].textContent : "",
      opens: open.tagName,
    };
  };
  process.stdout.write(
    JSON.stringify({
      rows: rows.map(read),
      columns: byId["rows-head"].children.map((c) => c.textContent.trim()).filter(Boolean),
      tally: byId["tally"].textContent,
      kinds: byId["kind-chips"].children.map((c) => c.textContent),
      registers: byId["register-chips"].children.map((c) => c.textContent),
      empty: byId["picked-empty"].textContent,
    })
  );
}, 20);
