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
  TargumSync: payload.who ? { who: payload.who, touched: () => {} } : undefined,
});

/* The search field and the filter come from the template, so a stub document has
   neither. Made here with the value the payload asks for: the page reads `.value`
   before it has drawn a row. */
byId.search = Object.assign(element("input"), { value: payload.search || "" });
byId["status-filter"] = Object.assign(element("select"), { value: payload.filter || "learning" });
// The panel the checklist fills, hidden until it has rows, as the template draws it.
document.getElementById("claim-panel").hidden = true;
const claimBody = document.getElementById("claim-body");

require(path.join(assets, "charts.js"));
require(path.join(assets, "vocab.js"));
global.window.TargumVocab.migrate = () => {};
global.window.TargumVocab.editor = () => element("div");
require(path.join(assets, "lists.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "shelf.js"));

const asked = [];
global.fetch = (url) => {
  const clean = String(url).replace(/[?&]k=[^&]*/, "");
  asked.push(clean);
  const offset = Number((/offset=(\d+)/.exec(clean) || [0, 0])[1]);
  const answer = (payload.pages || {})[String(offset)] || { words: [], offset, next: null };
  return Promise.resolve({ json: () => Promise.resolve(answer) });
};

require(path.join(assets, "claim.js"));
require(path.join(assets, "yours.js"));

const at = (id) => byId[id] || { textContent: "", children: [], hidden: true };
const part = (name) => claimBody.querySelector("." + name) || { hidden: true, children: [], textContent: "" };

/** The word rows the table drew: term, dictionary form, meaning, how well. */
function words() {
  return at("word-rows")
    .children.filter((row) => !String(row.className).includes("editor-row"))
    .map((row) => {
      const cells = row.children.map((cell) => cell.textContent);
      const said = row.children[2] || {};
      return {
        term: cells[0],
        lemma: cells[1],
        meaning: cells[2],
        lang: said.getAttribute ? said.getAttribute("lang") || "" : "",
        dir: said.getAttribute ? said.getAttribute("dir") || "" : "",
        well: cells[4],
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
    for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
  }
  process.stdout.write(
    JSON.stringify({
      asked,
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
      wordsTitle: at("words-title").textContent,
      wordsEmpty: at("words-empty").hidden ? "" : at("words-empty").textContent,
      phrases: phrases(),
      phrasesTitle: at("phrases-title").textContent,
      exports: { words: at("export-words").hidden, phrases: at("export-phrases").hidden },
      claim: {
        hidden: at("claim-panel").hidden,
        rows: (part("claim-rows").children || []).map((tr) => tr.children[1].textContent),
        said: part("claim-said").textContent,
      },
      ledger: JSON.parse(global.localStorage.getItem("targum:vocab:he") || "{}"),
    }),
  );
})();
