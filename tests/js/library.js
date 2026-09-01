/* Runs the library page's own script against a stub document and reports what it drew.
 *
 *   node tests/js/library.js payload.json
 *
 * The payload carries the catalogue (as the page receives it), the readers the server
 * would answer with, the view — the filters and sort a reader has chosen — and a hash,
 * which is how Learn names the one text it sent this reader for. What comes back on
 * stdout is JSON: the rows drawn, in order, the controls around them, and which row (if
 * any) was marked as the one somebody was sent to.
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
  TARGUM_COLLECTIONS: payload.collections || [],
  TARGUM_LANGUAGES: { he: "Hebrew", ru: "Russian" },
  // A first visit is a browser with no view remembered at all; every other run hands
  // the page the view a reader chose. `stored` lets a test put anything else in the
  // browser's store — the vocabulary the page counts, for one, and which collections
  // this reader has opened.
  stored: Object.assign(
    payload.firstVisit ? {} : { "targum:library": JSON.stringify(payload.view || {}) },
    payload.opened ? { "targum:opened-groups": JSON.stringify(payload.opened) } : {},
    payload.stored || {}
  ),
  // The language switcher is not what is under test, and the real one wants a document
  // to hang tabs off. Its answer is fixed here so the rows are the only variable.
  TargumLang: {
    HOME: "he",
    order: (codes) => codes,
    current: () => payload.language || "he",
    // The switcher draws; the caller remembers. Both are asked for now.
    set: () => {},
    into: () => "",
    switcher: () => {},
    beta: () => false,
    betaNote: () => "",
  },
});

// Learn links here with the id in the hash, and `pointAt` is what answers it.
if (payload.hash) global.location.hash = payload.hash;

global.fetch = () =>
  Promise.resolve({
    json: () =>
      Promise.resolve({ readers: payload.readers || [], shared: payload.shared || [], covers: !!payload.covers }),
  });

require(path.join(assets, "charts.js"));
require(path.join(assets, "scenes.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "library.js"));

// The page draws once its own request for /readers resolves. One turn of the microtask
// queue is enough; nothing here waits on a timer.
setTimeout(() => {
  const rows = byId["catalogue"].children;
  const read = (row) => {
    const open = row.children[0];
    return {
      // The title cell holds a scene label and a chip beside the Hebrew; the bdi is it.
      title: (open.children[1].children[0].children.find((c) => c.tagName === "bdi") || open.children[1].children[0]).textContent,
      fit: (open.children[1].children.find((c) => c.className === "row-fit") || {}).textContent || "",
      english: (open.children[1].children.find((c) => c.className === "row-english") || {}).textContent || "",
      // What follows the English on the same line: a byline on a text, "· 6 texts" on a
      // collection. Its own child, so the stub's textContent does not carry it.
      after: (() => {
        const line = open.children[1].children.find((c) => c.className === "row-english");
        const tail = line && line.children.find((c) => c.className === "row-by-after");
        return tail ? tail.textContent : "";
      })(),
      scene: (open.children[1].children[0].children.find((c) => c.className === "row-scene") || {}).textContent || "",
      chip: (open.children[1].children[0].children.find((c) => c.className === "row-next") || {}).textContent || "",
      state: open.children[open.children.length - 1].textContent,
      // A collection, and whether it is open; and whether this row is one of its
      // members. Empty on an ordinary row, which is most of them.
      group: open.getAttribute("data-group") || "",
      expanded: open.getAttribute("aria-expanded") || "",
      // Off the className, not the classList: the stub's list keeps its own set and a
      // class given at construction never reaches it.
      member: String(row.className || "").split(" ").indexOf("member") >= 0,
      cells: open.children.slice(2).map((cell) => cell.textContent.trim()),
      draws: row.children.length > 1 ? row.children[1].textContent : "",
      opens: open.tagName,
    };
  };
  process.stdout.write(
    JSON.stringify({
      rows: rows.map(read),
      // The stub's classList keeps its own set and never writes className back.
      pointed: rows.filter((row) => row.classList.contains("pointed")).map((row) => read(row).title),
      columns: byId["rows-head"].children.map((c) => c.textContent.trim()).filter(Boolean),
      tally: byId["tally"].textContent,
      kinds: byId["kind-chips"].children.map((c) => c.textContent),
      registers: byId["register-chips"].children.map((c) => c.textContent),
      empty: byId["picked-empty"].textContent,
      // The one line that says what the list is, and whether it was drawn under the
      // heading (a first visit that opened on the Scenes) or under the controls.
      note: byId["picked-lead"].hidden ? byId["picked-note"].textContent : byId["picked-lead"].textContent,
      noteLeads: !byId["picked-lead"].hidden,
      // The heading over the share column, and whether it can be pressed.
      shareHead: (() => {
        const head = byId["rows-head"].children.find((c) => c.className === "drop" && /New words|Scene number/.test(c.textContent));
        return head ? { text: head.textContent.trim(), disabled: head.getAttribute("aria-disabled") === "true" } : null;
      })(),
      kindOn: (byId["kind-chips"].children.find((c) => c.getAttribute("aria-pressed") === "true") || {}).textContent || "",
      gauges: rows.map((row) => row.children[0].children.find((c) => String(c.className).includes("gauge")).getAttribute("aria-label") || ""),
    })
  );
}, 20);
