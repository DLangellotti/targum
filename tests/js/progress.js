/* Runs the Your Progress page's script against a stub document and reports the story.
 *
 *   node tests/js/progress.js payload.json
 *
 * The page's arithmetic is the thing worth running: the totals, the touchstones the
 * account's story places the reader on, the words taken up week by week, and what next.
 * Everything, including `collect()`, is the page's own code.
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
  TARGUM_STRINGS: payload.strings,
  stored: payload.stored || {},
  TargumLang: {
    HOME: "he",
    order: (codes) => codes.sort(),
    current: (codes) => payload.chosen || codes[0],
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

/* What the account says — the reading line (targum-internal#291), the totals and the
   story (§12, 2026-10-09) — when a test hands one over; every other fetch the page makes
   answers as a server with nothing to say. Settled in microtasks, so the report below
   waits a turn for them. */
const asked = [];
global.fetch = global.window.fetch = (url) => {
  asked.push(String(url));
  let body = { signedIn: false };
  if (String(url).indexOf("/account/reading") === 0 && payload.reading) {
    body = { signedIn: true, reading: payload.reading };
  } else if (String(url).indexOf("/account/totals") === 0 && payload.totals) {
    body = { signedIn: true, kept: true, on: true, totals: payload.totals };
  } else if (String(url).indexOf("/account/story") === 0 && payload.story) {
    body = Object.assign({ signedIn: true }, payload.story);
  }
  return Promise.resolve({ json: () => Promise.resolve(body) });
};

require(path.join(assets, "strings.js"));
require(path.join(assets, "charts.js"));
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

/** The reading panel: whether it is shown, what it says, and the line it drew. */
function reading() {
  const panel = at("reading");
  const line = at("reading-line").children[0];
  const picture = line ? line.children[0] : null;
  const points = picture
    ? picture.children.filter((node) => String(node.getAttribute && node.getAttribute("class")) === "reading-point")
    : [];
  const ticks = picture
    ? (picture.children.find((node) => node.getAttribute && node.getAttribute("class") === "grid") || { children: [] })
        .children.filter((node) => node.tagName === "text")
        .map((node) => node.textContent)
    : [];
  return {
    shown: panel.hidden === false,
    drawn: Boolean(picture),
    said: at("reading-said").children.map((node) => node.textContent),
    points: points.map((node) => node.getAttribute("aria-label")),
    ticks: ticks,
    label: picture ? picture.getAttribute("aria-label") : "",
  };
}

function rows(id) {
  return at(id).children.map((item) => ({
    text: item.children.map((node) => node.textContent).join(" | "),
    href: item.children[0] ? item.children[0].href || "" : "",
  }));
}

setImmediate(() => setImmediate(() => process.stdout.write(
  JSON.stringify({
    reading: reading(),
    nothing: at("nothing").hidden === false,
    counts: counts(),
    tiles: counts_(),
    asked: asked,
    where: {
      head: at("where-title").textContent,
      shown: at("touchstones").hidden === false,
      note: at("where-note").hidden === false ? at("where-note").textContent : "",
      rungs: at("touchstones")
        .children.filter((item) => String(item.className) === "touch")
        .map((item) => {
          const link = item.children[0];
          return {
            text: link.textContent,
            state: String(link.className).replace("touch-", ""),
            href: link.href,
            current: link.getAttribute("aria-current") || "",
            ticked: Boolean(link.innerHTML),
          };
        }),
    },
    how: at("how-title").textContent,
    weeks: (function () {
      const bars = at("weeks").children[0];
      if (!bars || bars.tagName !== "ol") {
        return { columns: 0, said: (bars || { textContent: "" }).textContent, label: "", parts: [] };
      }
      return {
        columns: bars.children.length,
        label: bars.getAttribute("aria-label"),
        said: "",
        parts: bars.children.map((bar) => bar.children[0].children.length),
        titles: bars.children.map((bar) => bar.title),
      };
    })(),
    next: {
      wordsTitle: at("next-words-title").textContent,
      met: rows("met-rows"),
      metEmpty: at("met-empty").hidden === false ? at("met-empty").textContent : "",
      textsTitle: at("next-texts-title").textContent,
      level: rows("level-rows"),
      levelEmpty: at("level-empty").hidden === false ? at("level-empty").textContent : "",
      more: at("more-texts").textContent,
      moreHref: at("more-texts").href,
    },
  })
)));
