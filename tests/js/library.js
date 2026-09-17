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
  // The page's words in a reader's language, as the builder hands them over; none is English.
  TARGUM_STRINGS: payload.strings,
  // A first visit is a browser with no view remembered at all; every other run hands
  // the page the view a reader chose. `stored` lets a test put anything else in the
  // browser's store — the vocabulary the page counts, for one, and which collections
  // this reader has opened.
  stored: Object.assign(
    payload.firstVisit ? {} : { "targum:library": JSON.stringify(payload.views || payload.view || {}) },
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
    // Kept so a test can press another language once the page has drawn (`switchTo`).
    switcher: (host, codes, names, code, pick) => {
      global.targumPick = pick;
    },
    beta: () => false,
    betaNote: () => "",
  },
});

// Learn links here with the id in the hash, and `pointAt` is what answers it.
if (payload.hash) global.location.hash = payload.hash;

/* Two answers now: the shelf, and what is building on it (design.md §12, 2026-09-17).
   The library asks for both at once, so the stub tells them apart by the address rather
   than answering everything with the readers. */
var shelfAnswer = {
  readers: payload.readers || [],
  shared: payload.shared || [],
  covers: !!payload.covers,
  // How much of each catalogue text this reader knows, for the rows they have not
  // built (targum-internal#293). It is what "at my level" is measured with, so a
  // test of that has to be able to set it.
  catalogue: payload.catalogueKnown || {},
};

global.fetch = (address) =>
  Promise.resolve({
    ok: true,
    json: () =>
      Promise.resolve(
        String(address).indexOf("/jobs") >= 0 ? { jobs: payload.jobs || [] } : shelfAnswer
      ),
  });

require(path.join(assets, "strings.js"));
require(path.join(assets, "charts.js"));
require(path.join(assets, "scenes.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "library.js"));

// The page draws once its own request for /readers resolves. One turn of the microtask
// queue is enough; nothing here waits on a timer.
setTimeout(() => {
  if (payload.switchTo) global.targumPick(payload.switchTo);
  /* Two shapes over one list since 2026-09-17 (design.md §12): cards by default, the
     table one press away. Whichever is on is the one filled, so the rows reported are
     read off the host that has them. A card has no columns, so `cells` comes back empty
     there and a test wanting them asks for the table — see `draw()` in the Python. */
  const browsing = byId["catalogue"].children.length === 0 && byId["cards"].children.length > 0;
  const rows = browsing ? byId["cards"].children : byId["catalogue"].children;
  const readCard = (item) => {
    const open = item.children[0];
    const what = open.children[1] || { children: [] };
    /* By word, not by whole string: the lately-arrived mark shares the scene label's
       element and its class, and an exact match came back empty for both. */
    const wearing = (c, name) => String(c.className || "").split(" ").indexOf(name) >= 0;
    const find = (name) => what.children.find((c) => wearing(c, name)) || {};
    return {
      title: (what.children.find((c) => c.className === "card-title") || {}).textContent || "",
      fit: "",
      media: (open.children[0].children.find((c) => c.className === "card-media") || {}).attrs
        ? open.children[0].children.find((c) => c.className === "card-media").attrs["aria-label"] || ""
        : "",
      english: find("card-english").textContent || "",
      englishLang: (find("card-english").attrs || {})["lang"] || "",
      after: "",
      scene: find("card-scene").textContent || "",
      // Arrived lately (targum-internal#315). Its own field: it stands where the scene
      // label does, and a test asking "is this marked new" should not have to know that.
      fresh: find("card-new").textContent || "",
      chip: find("row-next").textContent || "",
      state: find("row-state").textContent || "",
      // A build in progress, drawn as a card that is not a press (design.md §12,
      // 2026-09-17): the word over the title, and the sentence saying where it has got.
      making: find("card-making").textContent || "",
      meta: find("card-meta").textContent || "",
      known: (find("card-known").children || []).map((c) => c.textContent).join(""),
      group: open.getAttribute("data-group") || "",
      expanded: open.getAttribute("aria-expanded") || "",
      member: false,
      cells: [],
      draws: "",
      opens: open.tagName,
    };
  };
  const read = (row) => {
    // A collection stays a row even among cards, so the shape is read off the element
    // rather than off the mode: `.card` is a card and anything else is a row.
    if (browsing && String(row.children[0].className || "").indexOf("card") === 0) {
      return readCard(row);
    }
    const open = row.children[0];
    return {
      // The title cell holds a scene label and a chip beside the Hebrew; the bdi is it.
      title: (open.children[1].children[0].children.find((c) => c.tagName === "bdi") || open.children[1].children[0]).textContent,
      fit: (open.children[1].children.find((c) => c.className === "row-fit") || {}).textContent || "",
      // The one word beside the title that says what can be played: "audio", "video",
      // or nothing. One word, never two — a video row does not also say audio.
      media: (open.children[1].children.find((c) => c.className === "row-audio" || c.className === "row-video") || {}).textContent || "",
      english: (open.children[1].children.find((c) => c.className === "row-english") || {}).textContent || "",
      // The language that cell claims to be in (targum-internal#289): `en` until the
      // catalogue had a title in anything else.
      englishLang: (() => {
        const line = open.children[1].children.find((c) => c.className === "row-english");
        return line ? line.attrs["lang"] || "" : "";
      })(),
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
  /* Written, then done. The page polls while anything is building (design.md §12,
     2026-09-17) and an interval keeps node alive for ever; this is a reporter, so it
     says what it drew and stops rather than waiting for a build that will never
     finish. */
  process.stdout.write(
    JSON.stringify({
      rows: rows.map(read),
      // The stub's classList keeps its own set and never writes className back.
      pointed: rows.filter((row) => row.classList.contains("pointed")).map((row) => read(row).title),
      columns: byId["rows-head"].children.map((c) => c.textContent.trim()).filter(Boolean),
      tally: byId["tally"].textContent,
      kinds: byId["kind-chips"].children.map((c) => c.textContent),
      registers: byId["register-chips"].children.map((c) => c.textContent),
      /* What the page is browsed by since 2026-09-17: the subjects with rows behind
         them, each with its count, and the sentence above the list saying how far it has
         been narrowed to fit the reader. A subject chip's name and number are separate
         children, so the name alone is the first of them. */
      subjects: byId["subject-chips"].hidden
        ? []
        : byId["subject-chips"].children.map((c) => (c.children[0] || {}).textContent || c.textContent),
      subjectCounts: byId["subject-chips"].hidden
        ? []
        : byId["subject-chips"].children.map((c) =>
            Number((c.children.find((k) => k.className === "chip-n") || {}).textContent || 0)
          ),
      subjectOn: (byId["subject-chips"].children.find((c) => c.getAttribute("aria-pressed") === "true") || {
        children: [],
      }).children[0]
        ? byId["subject-chips"].children.find((c) => c.getAttribute("aria-pressed") === "true").children[0].textContent
        : "",
      said: byId["said"].textContent,
      /* Which band the list is narrowed to. Read off the selected option rather than off
         the line's text: a stub's textContent walks every child, so the sentence comes
         back with all three options run together. */
      fitOn: (() => {
        const pick = byId["said"].children
          .map((c) => (c.children || []).find((k) => k.tagName === "select"))
          .find(Boolean);
        const chosen = pick && (pick.children || []).find((o) => o.selected);
        return chosen ? chosen.textContent : "";
      })(),
      shape: browsing ? "cards" : "list",
      shapeOn:
        (byId["shape"].children.find((c) => c.getAttribute("aria-pressed") === "true") || {}).textContent || "",
      empty: byId["picked-empty"].textContent,
      // The one line that says what the list is, and whether it was drawn under the
      // heading (a first visit that opened on the Scenes) or under the controls.
      note: byId["picked-lead"].hidden ? byId["picked-note"].textContent : byId["picked-lead"].textContent,
      noteLeads: !byId["picked-lead"].hidden,
      // The heading over the share column, and whether it can be pressed.
      shareHead: (() => {
        const head = byId["rows-head"].children.find((c) => c.className === "drop" && /Hard words|Scene number/.test(c.textContent));
        return head ? { text: head.textContent.trim(), disabled: head.getAttribute("aria-disabled") === "true" } : null;
      })(),
      find: byId["find"].value || "",
      views: JSON.parse(global.localStorage.getItem("targum:library") || "{}"),
      kindOn: (byId["kind-chips"].children.find((c) => c.getAttribute("aria-pressed") === "true") || {}).textContent || "",
      // The hard-words gauge is a column, so it exists on a row and not on a card.
      gauges: rows.map(
        (row) =>
          (row.children[0].children.find((c) => String(c.className).includes("gauge")) || {
            getAttribute: () => "",
          }).getAttribute("aria-label") || ""
      ),
    })
  );
  process.exit(0);
}, 20);
