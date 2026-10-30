/* Runs the Your Progress page's script against a stub document and reports the story.
 *
 *   node tests/js/progress.js payload.json
 *
 * The page's arithmetic is the thing worth running: the totals, the touchstones the
 * account's story places the reader on, how you got here, and what next.
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
const store = Object.assign({}, payload.stored || {}, payload.raw || {});
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
    body = { signedIn: true, measurable: 20, reading: payload.reading };
  } else if (String(url).indexOf("/account/reading") === 0 && payload.readingFails) {
    return Promise.reject(new Error("unreachable"));
  } else if (String(url).indexOf("/account/totals") === 0 && (payload.totals || payload.words)) {
    body = {
      signedIn: true,
      kept: true,
      on: !payload.recordOff,
      totals: payload.recordOff ? [] : payload.totals || [],
      words: payload.words || null,
    };
  } else if (String(url).indexOf("/account/story") === 0 && payload.storyFails) {
    return Promise.reject(new Error("unreachable"));
  } else if (String(url).indexOf("/account/story") === 0 && payload.storyHeld) {
    return new Promise(() => {});
  } else if (String(url).indexOf("/account/story") === 0 && payload.story) {
    body = Object.assign({ signedIn: true }, payload.story);
  }
  return Promise.resolve({ json: () => Promise.resolve(body) });
};

require(path.join(assets, "strings.js"));
require(path.join(assets, "charts.js"));
// The rule that writes the flag the "learned on targum" tile counts, asked of pairs of
// stages with no page: [stage it held (null for never on the list), stage it went to].
// A month's name as a date says it, for each month in a language: [language, months].
if (payload.monthsIn) {
  process.stdout.write(
    JSON.stringify([...Array(12).keys()].map((month) => window.TargumCharts.monthInDate(month, payload.monthsIn)))
  );
  process.exit(0);
}
if (payload.learnedBy) {
  process.stdout.write(
    JSON.stringify(payload.learnedBy.map(([was, now]) => window.TargumCharts.learnedBy(was, now)))
  );
  process.exit(0);
}
/* The period's three presses come from the template, which a stub document has none of:
   made here, class "button" so the stub's selector finds them, before the page wires them. */
// Hidden in the template until the account says recording is stopped.
global.document.getElementById("spent-off").hidden = true;
const howBy = global.document.getElementById("how-by");
["7", "30", ""].forEach((period) => {
  const press = element("button");
  press.className = "button";
  press.setAttribute("data-period", period);
  press.setAttribute("aria-pressed", period === "30" ? "true" : "false");
  howBy.appendChild(press);
});
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
  const points = picture && picture.children
    ? picture.children.filter((node) => String(node.getAttribute && node.getAttribute("class")) === "reading-point")
    : [];
  const ticks = picture
    ? (picture.children.find((node) => node.getAttribute && node.getAttribute("class") === "grid") || { children: [] })
        .children.filter((node) => node.tagName === "text")
        .map((node) => node.textContent)
    : [];
  const months = picture
    ? (picture.children.find((node) => node.getAttribute && node.getAttribute("class") === "axis") || { children: [] })
        .children.map((node) => node.textContent)
    : [];
  const empty = line && String(line.className).indexOf("chart-empty") >= 0 ? line.children[0].textContent : "";
  return {
    shown: panel.hidden === false,
    drawn: Boolean(picture) && !empty,
    by: (panel.getAttribute && panel.getAttribute("data-by")) || "",
    empty: empty,
    failed: at("reading-failed").hidden === false,
    focusable: picture && !empty ? picture.getAttribute("tabindex") : "",
    titles: picture && !empty
      ? picture.children
          .filter((node) => String(node.getAttribute && node.getAttribute("class")) === "reading-point")
          .map((node) => (node.children[0] || { textContent: "" }).textContent)
      : [],
    months: months,
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

/** Section 2, as drawn: the figures with their lines, the days, the words. */
function how() {
  const figures = at("spent-figures").children.map((one) => {
    const part = (name) => one.children.find((node) => String(node.className).split(" ")[0] === name);
    const vs = part("spent-vs");
    return {
      amount: (part("spent-amount") || { textContent: "" }).textContent,
      label: (part("spent-label") || { textContent: "" }).textContent,
      vs: vs ? vs.textContent : "",
      way: vs ? String(vs.className).replace("spent-vs", "").trim() : "",
      under: (part("spent-under") || { textContent: "" }).textContent,
    };
  });
  return {
    shown: at("how").hidden === false,
    by: at("how-by").hidden === false,
    pressed: at("how-by").children.map((press) => press.getAttribute("aria-pressed")),
    spent: at("spent").hidden === false,
    figures: figures,
    off: at("spent-off").hidden === false,
    days: at("how-days").hidden === false
      ? {
          title: at("days-title").textContent,
          label: at("days-grid").getAttribute("aria-label"),
          squares: at("days-grid").children.map((node) => (String(node.className) === "day on" ? 1 : 0)),
          range: at("days-range").textContent,
        }
      : null,
    words: at("how-words").hidden === false
      ? {
          title: at("words-title").textContent,
          bars: at("words-bars").children.map((line) => ({
            label: line.children[0].textContent,
            count: line.children[2].textContent,
            width: line.children[1].children[0].style.width,
          })),
          since: at("words-since").hidden === false ? at("words-since").textContent : "",
        }
      : null,
  };
}

function settle(then) {
  setImmediate(() => setImmediate(then));
}

settle(() => {
  if (payload.period !== undefined) {
    const press = howBy.children.find((node) => node.getAttribute("data-period") === payload.period);
    if (press) press.fire("click");
  }
  report();
});

function report() {
  process.stdout.write(
  JSON.stringify({
    reading: reading(),
    nothing: at("nothing").hidden === false,
    counts: counts(),
    tiles: counts_(),
    asked: asked,
    where: {
      head: at("where-title").textContent,
      step: at("where-step").hidden === false ? at("where-step").textContent : "",
      known: at("where-known").hidden === false ? at("where-known").textContent : "",
      go: at("where-go").hidden === false ? at("where-go").textContent : "",
      goHref: at("where-go").hidden === false ? at("where-go").href : "",
      shown: at("ladder").hidden === false,
      grid: at("level-grid").hidden === false,
      note: at("where-note").hidden === false ? at("where-note").textContent : "",
      mark: at("level-mark").hidden === false
        ? {
            spoken: at("level-spoken").textContent,
            big: at("level-big").textContent,
            lang: at("level-big").getAttribute("lang") || "",
            dir: at("level-big").getAttribute("dir") || "",
            hidden: at("level-big").getAttribute("aria-hidden") || "",
            cefr: at("level-cefr").textContent,
          }
        : null,
      toward: at("level-toward").hidden === false
        ? {
            line: at("level-togo").textContent,
            number: (at("level-togo").children.find((node) => node.tagName === "b") || { textContent: "" }).textContent,
            letter: (function () {
              const run = at("level-togo").children.find((node) => node.tagName === "bdi");
              return run ? { text: run.textContent, dir: run.getAttribute("dir"), lang: run.getAttribute("lang") } : null;
            })(),
            width: at("level-fill").style.width,
          }
        : null,
      rungs: at("touchstones")
        .children.filter((item) => String(item.className) === "touch")
        .map((item) => {
          const row = item.children[0];
          const words = row.children.find((node) => String(node.className) === "touch-words");
          const count = row.children.find((node) => String(node.className) === "touch-count");
          const chevron = row.children.find((node) => String(node.className) === "touch-go");
          return {
            name: words ? words.children[0].textContent : "",
            said: words ? words.children[1].textContent : "",
            count: count ? count.textContent : "",
            state: String(row.className).split(" ").pop().replace("touch-", ""),
            tag: String(row.tagName).toLowerCase(),
            href: row.href,
            current: row.getAttribute("aria-current") || "",
            chevron: chevron ? chevron.textContent : "",
            text: row.textContent,
          };
        }),
    },
    how: at("how-title").textContent,
    effort: how(),
    next: {
      wordsTitle: at("next-words-title").textContent,
      met: rows("met-rows"),
      metEmpty: at("met-empty").hidden === false ? at("met-empty").textContent : "",
      waiting: at("where-wait").hidden === false,
      failed: at("where-failed").hidden === false,
      practise: at("practise").hidden === false,
      textsTitle: at("next-texts-title").textContent,
      level: rows("level-rows"),
      levelClasses: at("level-rows").children.map((item) => String(item.className)),
      levelEmpty: at("level-empty").hidden === false ? at("level-empty").textContent : "",
      more: at("more-texts").textContent,
      moreHref: at("more-texts").href,
    },
  })
);
}
