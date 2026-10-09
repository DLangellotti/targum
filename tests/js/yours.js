/* Runs the Your Words page's script against a stub document and reports what it drew.
 *
 *   node tests/js/yours.js payload.json
 *
 * The page behind the account (2026-09-11): the words you are learning, the commonest
 * words you may already know, and your phrases. What comes back is what the lists drew
 * — the word rows, the phrase groups, the titles with their counts, the empty lines —
 * and what the checklist wrote. `collect()` is real, because the lists are drawn from it
 * and stubbing it would leave the test asserting against its own fixture.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

install({
  TARGUM_KEY: "k",
  TARGUM_LIST: payload.which || "words",
  TARGUM_LANGUAGES: { he: "Hebrew", en: "English", ru: "Russian" },
  stored: payload.stored || {},
  TargumLang: {
    HOME: "he",
    order: (codes) => codes,
    current: () => "he",
    set: () => {},
    into: () => "",
    switcher: () => {},
    beta: () => false,
    betaNote: () => "",
  },
  /* Signed in, when the payload says so. `onChange` and `start` are as much of sync as
     the page calls, and both were missing until 2026-09-18 — so passing `who` at all
     threw before a row was drawn, and the whole signed-in half of this page (the export
     buttons, and nothing else) had never been run. */
  TargumSync: payload.who
    ? {
        who: payload.who,
        touched: () => {},
        onChange: () => {},
        start: () => Promise.resolve(),
      }
    : undefined,
});

/* The search field and the filter come from the template, so a stub document has
   neither. Made here with the value the payload asks for: the page reads `.value`
   before it has drawn a row. */
byId.search = Object.assign(element("input"), { value: payload.search || "" });
// The stage the table opens on, as the chips remember it (design.md §12, 2026-10-09).
if (payload.filter) global.localStorage.setItem("targum:words-stage", payload.filter);
// The panel the checklist fills, hidden until it has rows, as the template draws it.
document.getElementById("claim-panel").hidden = true;
const claimBody = document.getElementById("claim-body");

require(path.join(assets, "charts.js"));
require(path.join(assets, "vocab.js"));
global.window.TargumVocab.migrate = () => {};
/* The editor is `vocab.js`'s and tested there. Here it is a scale and nothing else, so a
   card that carries one can be pressed: a level is a button that hands its value on. */
global.window.TargumVocab.editor = (options) => {
  const box = element("div");
  box.className = "vocab-editor";
  const scale = element("div");
  scale.className = "levels";
  [1, 2, 3, 9, 0].forEach((value) => {
    const button = element("button");
    button.className = "level level-" + value + (options.status === value ? " on" : "");
    button.setAttribute("data-value", String(value));
    button.textContent = value === 9 ? "known" : value === 0 ? "ignore" : String(value);
    button.addEventListener("click", () => options.onStatus && options.onStatus(value));
    scale.appendChild(button);
  });
  box.appendChild(scale);
  return box;
};
require(path.join(assets, "lists.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "shelf.js"));

/* Files the page saved. `saveFile` makes a Blob, turns it into a URL, clicks an anchor
   at it and revokes it — so the Blob is the only place the bytes ever exist, and
   capturing it here is the only way to read what a reader would have downloaded. */
const saved = [];
global.Blob = class {
  constructor(parts, options) {
    this.text = parts.join("");
    this.type = (options || {}).type || "";
  }
};
global.URL = {
  createObjectURL: (blob) => {
    saved.push(blob);
    return "blob:saved";
  },
  revokeObjectURL: () => {},
};
/* The name is on the anchor rather than on the Blob, and the anchor is gone a line
   later — so it is taken on the way past. It is half of what an export is: a file
   called "targum Hebrew words.txt" is an Anki deck and one called ".csv" is not. */
const appendChild = document.body.appendChild.bind(document.body);
document.body.appendChild = (child) => {
  if (child.download && saved.length) saved[saved.length - 1].name = child.download;
  return appendChild(child);
};

const asked = [];
// What the page said to the server, as opposed to what it asked: `{url, body}`.
const told = [];
global.fetch = (url, options) => {
  const clean = String(url).replace(/[?&]k=[^&]*/, "");
  if (options && options.method === "POST") {
    told.push({ url: clean, body: JSON.parse(options.body || "null") });
    return Promise.resolve({ ok: !payload.refuse, json: () => Promise.resolve({ ok: true }) });
  }
  asked.push(clean);
  const offset = Number((/offset=(\d+)/.exec(clean) || [0, 0])[1]);
  let answer = (payload.pages || {})[String(offset)] || { words: [], offset, next: null };
  // Your targums (2026-09-11): the shelf rows moved here from Learn, and so did the
  // answer the shelf is drawn from.
  if (clean.indexOf("/readers") === 0) {
    answer = { readers: payload.readers || [], shared: payload.shared || [], trash: [], covers: true };
  }
  // What is building (design.md §12, 2026-09-25): a row at the top of Your targums.
  if (clean.indexOf("/jobs") === 0) answer = { jobs: payload.jobs || [] };
  // Lines that came back changed (targum-internal#290): the queue, and with `all=1` the
  // record, which is the queue and the ones already known.
  if (clean.indexOf("/slips") === 0) {
    answer = { slips: clean.indexOf("all=1") > 0 ? payload.slips || [] : payload.queue || payload.slips || [] };
  }
  // What the server knows about the list (design.md §12, "Your Words is one table and
  // a practice card", 2026-10-09). Signed out, refused.
  if (clean.indexOf("/account/words") === 0) answer = payload.facts || { signedIn: false };
  return Promise.resolve({ ok: true, json: () => Promise.resolve(answer) });
};

require(path.join(assets, "claim.js"));
require(path.join(assets, "yours.js"));

const at = (id) => byId[id] || { textContent: "", children: [], hidden: true };
const part = (name) => claimBody.querySelector("." + name) || { hidden: true, children: [], textContent: "" };

/** The word rows the table drew: term, dictionary form, meaning, in how many texts it
 *  was met, its stage by name, and the five stages to press. */
function words() {
  return at("word-rows").children.map((row) => {
    const [word, said, met, status, stage] = row.children;
    const find = (node, name) => (node && node.querySelector(name)) || null;
    const form = (word.children || []).find((node) => String(node.className).includes("form"));
    const scale = ((stage || { children: [] }).children[0] || { children: [] }).children[0];
    const on = scale ? scale.children.find((b) => String(b.className).includes(" on")) : null;
    return {
      term: word.children[0] ? word.children[0].textContent : "",
      lemma: form ? form.textContent : "",
      said: (find(word, ".said") || {}).textContent || "",
      meaning: (find(said, ".sense") || {}).textContent || "",
      notes: (said.children || [])
        .filter((node) => String(node.className).includes("word-note"))
        .map((node) => node.textContent),
      lang: said.getAttribute ? said.getAttribute("lang") || "" : "",
      dir: said.getAttribute ? said.getAttribute("dir") || "" : "",
      met: met ? met.textContent : "",
      status: status ? (find(status, ".status-name") || {}).textContent || "" : "",
      stage: on ? Number(on.getAttribute("data-value")) : null,
      press: (value) => {
        const button = scale.children.find((b) => b.getAttribute("data-value") === String(value));
        button.fire("click");
      },
    };
  });
}

/** The practice card (board WordsDesk): what it says about the word it is on. */
function practise() {
  const host = at("practise");
  if (host.hidden) return null;
  const body = at("practise-body");
  const find = (name) => body.querySelector(name);
  const line = find(".practise-line");
  const scale = find(".levels");
  const on = scale ? scale.children.find((b) => String(b.className).includes(" on")) : null;
  const next = find(".practise-next");
  return {
    count: at("practise-at").textContent,
    from: (find(".practise-place") || {}).textContent || "",
    line: line ? line.textContent : "",
    word: (find(".practise-word") || {}).textContent || "",
    lang: line ? line.getAttribute("lang") : "",
    meaning: (find(".practise-sense") || {}).textContent || "",
    note: (find(".word-note") || {}).textContent || "",
    translation: (find(".practise-translation") || {}).textContent || "",
    stage: on ? Number(on.getAttribute("data-value")) : null,
    next: next ? !next.hidden : false,
    coming: (find(".practise-coming-words") || { children: [] }).children.map((b) => b.textContent),
  };
}

/** A tile, if one was drawn there: its class, and the letter it rests on. */
function tile(node) {
  const found = (node.children || []).find((child) => String(child.className).includes("thumb"));
  if (!found) return null;
  const glyph = found.children[0];
  return { className: found.className, letter: glyph ? glyph.textContent : "" };
}

/** The shelf rows (design.md §12, 2026-09-24): the picture, the title with its English
 *  and its line of facts, the status, and the row's keys. */
function shelf() {
  return at("library-list").children.map((row) => {
    // A build keeps its cells in one box; a text's and a series' are the row's own
    // children, with the title as the press (2026-09-27).
    const first = row.children[0] || { children: [] };
    const cells = String(first.className).includes("building") ? first : row;
    const kids = cells.children || [];
    const named = (name) => kids.find((c) => String(c.className).split(" ").includes(name));
    const what = named("book-what") || { children: [] };
    const deep = (node, name) => {
      for (const child of node.children || []) {
        if (String(child.className).split(" ").includes(name)) return child;
        const found = deep(child, name);
        if (found) return found;
      }
      return null;
    };
    const part = (name) => (deep(what, name) || {}).textContent || "";
    const controls = (row.children || []).find((c) => c.className === "row-controls");
    return {
      cover: tile(cells),
      title: part("book-title"),
      english: part("book-english"),
      facts: part("book-facts"),
      // The tag on a build; the quiet line's own status on a text (board Main, P4).
      status: (named("row-status") || deep(what, "fact-status") || {}).textContent || "",
      controls: controls ? controls.children.map((c) => c.textContent) : [],
    };
  });
}

/** Phrases, grouped the way the page grouped them: {text: [phrase, ...]}. */
function phrases() {
  const out = {};
  at("phrase-list").children.forEach((group) => {
    const [head, list] = group.children;
    out[head.textContent] = list.children.map((item) => item.children[0].textContent);
  });
  return out;
}

(async () => {
  for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
  for (const step of payload.do || []) {
    if (step.type === "all") {
      part("claim-all").checked = true;
      part("claim-all").onchange();
    }
    if (step.type === "yes" && !part("claim-yes").disabled) part("claim-yes").onclick();
    /* A press on an export: `{type: "export", which: "anki"}`. The buttons are hidden
       until sync says there is an account, and a test that only wants the file should
       not have to stand up an account to get one — so the press is on the button
       whatever its `hidden` says, which is what a signed-in reader is pressing. */
    if (step.type === "export") at("export-" + step.which).fire("click");
    // The practice card: `{type: "next"}`, `{type: "practise", value: 9}`, and a word
    // under Coming up by its place, `{type: "go", at: 1}`.
    if (step.type === "next") at("practise-body").querySelector(".practise-next").fire("click");
    if (step.type === "practise") {
      const button = at("practise-body").querySelector(".levels").children.find(
        (b) => b.getAttribute("data-value") === String(step.value),
      );
      if (button) button.fire("click");
    }
    if (step.type === "go") {
      at("practise-body").querySelector(".practise-coming-words").children[step.at].fire("click");
    }
    // "I know this" on a corrected line in the record: `{type: "slip", id: 7}`.
    if (step.type === "slip") {
      const row = at("rewrote-rows").children.find((item) => item.getAttribute("data-slip") === String(step.id));
      const button = row && row.querySelector(".work-known");
      if (button) button.fire("click");
    }
    /* A press on a row that opens its card (2026-09-18): `{type: "open", in: "word-rows",
       term: "…"}`, where `in` is the list the row stands in and `term` its first word. */
    if (step.type === "open") {
      const host = at(step.in);
      const rows = step.in === "phrase-list"
        ? host.children.flatMap((group) => group.children[1].children)
        : host.children;
      const row = rows.find((item) => {
        const first = item.querySelector(".term") || item.querySelector(".rewrote-recast");
        return first && first.textContent === step.term;
      });
      if (row) row.fire("click", { target: row });
    }
    // A level said on the open card: `{type: "level", value: 9}`.
    if (step.type === "level") {
      const button = at("list-card").querySelector(".level-" + step.value);
      if (button) button.fire("click", { stopPropagation() {} });
    }
    // A step pressed on a table row: `{type: "stage", word: "…", value: 9}`.
    if (step.type === "stage") {
      const row = words().find((one) => one.term === step.word);
      if (row) row.press(step.value);
    }
    // A stage tab over the table: `{type: "chip", stage: "9"}`, "often" for Met often.
    if (step.type === "chip") {
      const chip = at("stage-chips").children.find((c) => c.getAttribute("data-stage") === step.stage);
      if (chip) chip.fire("click");
    }
    for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
  }
  process.stdout.write(
    JSON.stringify({
      asked,
      told,
      shown: !at("page").hidden,
      nothing: !at("nothing").hidden,
      words: words(),
      copies: {
        words: at("word-rows")
          .children.filter((row) => !String(row.className).includes("editor-row"))
          .map((row) => (row.children[0].querySelector(".copy") || { attrs: {} }).attrs["aria-label"]),
        phrases: at("phrase-list").children.flatMap((group) =>
          group.children[1].children.map(
            (item) => (item.querySelector(".copy") || { attrs: {} }).attrs["aria-label"],
          ),
        ),
      },
      practise: practise(),
      order: at("words-order").textContent,
      hasMet: !!(byId["word-table"] && byId["word-table"].classList.contains("has-met")),
      rewrote: {
        hidden: at("rewrote-heading").hidden,
        rows: at("rewrote-rows").children.map((item) => ({
          wrote: (item.querySelector(".rewrote-wrote") || {}).textContent || "",
          recast: (item.querySelector(".rewrote-recast") || {}).textContent || "",
          // The words marked as changed, which is the whole of what a `mark` is for.
          changed: (item.querySelector(".rewrote-recast") || { children: [] }).children
            .filter((bit) => String(bit.className).includes("rewrote-changed"))
            .map((bit) => bit.textContent),
          why: (item.querySelector(".rewrote-why") || {}).textContent || "",
          known: !!item.querySelector(".work-known"),
        })),
      },
      // The head (design.md §12, 2026-10-09): what the list adds up to, the tab counts,
      // and the stage chips with the one pressed.
      summary: at("words-summary").textContent,
      counts: { words: at("count-words").textContent, phrases: at("count-phrases").textContent },
      chips: at("stage-chips").children.map((c) => c.textContent),
      chipOn: (at("stage-chips").children.find((c) => c.getAttribute("aria-pressed") === "true") || {}).textContent || "",
      stored: global.localStorage.getItem("targum:vocab:he"),
      wordsEmpty: at("words-empty").hidden ? "" : at("words-empty").textContent,
      phrases: phrases(),
      phrasesTitle: at("phrases-title").textContent,
      exports: {
        words: at("export-words").hidden,
        anki: at("export-anki").hidden,
        phrases: at("export-phrases").hidden,
      },
      /* What the presses above downloaded: the name off the anchor is not readable here,
         so a file is its type and its text, which is the half a format test is about. */
      saved: saved.map((file) => ({ name: file.name || "", type: file.type, text: file.text })),
      claim: {
        hidden: at("claim-panel").hidden,
        rows: (part("claim-rows").children || []).map((tr) => tr.children[1].textContent),
        said: part("claim-said").textContent,
      },
      /* The card a row opened, and what it says: the word, the line under it, the
         meaning, and whether the level scale is on it. */
      card: (() => {
        const card = byId["list-card"];
        if (!card || card.hidden) return null;
        const find = (name) => (card.querySelector(name) || {}).textContent || "";
        return {
          head: find(".lemma"),
          form: find(".form"),
          meaning: find(".meaning"),
          levels: !!card.querySelector(".levels"),
          role: card.attrs.role || "",
        };
      })(),
      ledger: JSON.parse(global.localStorage.getItem("targum:vocab:he") || "{}"),
      // The phrases kept from the one text the fixtures keep them from.
      picked: JSON.parse(global.localStorage.getItem("targum:picked:h1") || "{}"),
      head: at("shelf-head").hidden,
      shelf: shelf(),
    }),
  );
  // A build on the shelf is followed every three seconds for as long as it runs, and a
  // fixture's build runs for ever.
  process.exit(0);
})();
