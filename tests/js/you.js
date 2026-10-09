/* Runs the profile page's script against a stub document and reports what it did.
 *
 *   node tests/js/you.js payload.json
 *
 * The page draws who is signed in, which languages they are learning and read into, and
 * holds the two controls that end an account. All of these are things that are either
 * wrong quietly or wrong forever, which is why the script is run rather than read.
 *
 * The payload carries the answer `/account/me` should give and a list of things to do
 * to the page afterwards. What comes back is what was drawn and what was posted.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const posted = [];
const restarted = { count: 0, signedOut: 0 };

install({
  TARGUM_KEY: "k",
  TARGUM_STRINGS: payload.strings,
  // What the page is built with: every language targum has, and which stay on.
  TARGUM_READING: [
    { code: "he", name: "Hebrew", stage: "alpha", label: "alpha" },
    { code: "arc", name: "Aramaic", stage: "R&D", label: "Experimental" },
    { code: "yi", name: "Yiddish", stage: "R&D", label: "Experimental" },
  ],
  TARGUM_INTO: [
    { code: "en", name: "English", stage: "alpha", label: "alpha" },
    { code: "ru", name: "Russian", stage: "beta", label: "Experimental" },
  ],
  TARGUM_REQUIRED: ["he"],
  TargumSync: {
    start: () => restarted.count++,
    signOut: () => {
      restarted.signedOut++;
      return Promise.resolve({});
    },
  },
});

const answers = payload.answers || {};

global.fetch = (url, options) => {
  const at = String(url).split("?")[0];
  if (options && options.method === "POST") {
    posted.push({ path: at, body: JSON.parse(options.body || "{}") });
  }
  // An answer of "fail" is a request that never came back.
  if (answers[at] === "fail") return Promise.reject(new Error("offline"));
  return Promise.resolve({ json: () => Promise.resolve(answers[at] || {}) });
};

require(path.join(assets, "strings.js"));
require(path.join(assets, "you.js"));

const at = (id) => byId[id] || { textContent: "", value: "", hidden: true, children: [] };

/** The languages being learned, as rows: which, and whether it has a Remove. */
function learningRows() {
  return at("you-learning").children.map((row) => ({
    code: row.getAttribute("data-code"),
    removable: row.children.length > 1,
  }));
}

/** A select's options, as a person would read them. */
function options(id) {
  return at(id).children.map((option) => ({
    value: option.value,
    label: option.textContent,
    on: Boolean(option.selected),
  }));
}

/** Do something to the page, the way a person would. */
function act(step) {
  if (step.type === "press") {
    /* `id`, or `id:row:child` for a press inside a list the page drew — a connector's
       Disconnect is a button in a row that did not exist when the page loaded. */
    const path = String(step.id).split(":");
    let node = at(path[0]);
    for (let n = 1; n < path.length; n++) node = node.children[Number(path[n])];
    node.fire("click", {});
  } else if (step.type === "write") {
    at(step.id).value = step.value;
  } else if (step.type === "pick") {
    at(step.id).value = step.value;
    at(step.id).fire("change", {});
  } else if (step.type === "remove") {
    const row = at("you-learning").children.find((one) => one.getAttribute("data-code") === step.code);
    row.children[1].fire("click", {});
  }
}

/* Two beats: one for the fetch that draws the page, one for the debounce on the name
   field and the tick boxes, which is the whole reason a keystroke is not a request. */
setTimeout(() => {
  (payload.do || []).forEach(act);
  setTimeout(() => {
    process.stdout.write(
      JSON.stringify({
        stranger: at("stranger").hidden,
        panels: {
          languages: at("languages").hidden,
          ending: at("ending").hidden,
        },
        /* Its own key and not one of `panels` above: those are shown to everybody who is
           signed in, and this one is drawn only where there is something in it. */
        connectionsPanel: at("connections").hidden,
        email: at("you-email").textContent,
        learning: learningRows(),
        start: options("you-start"),
        reads: options("you-reads"),
        /* The rung named on arrival: what the picker offers, which it shows as chosen, and
           the browser's copy the reader page reads. */
        level: at("you-level").children.map((option) => ({
          value: option.value,
          label: option.textContent,
          on: Boolean(option.selected),
        })),
        declaredHere: localStorage.getItem("targum:declared"),
        /* How the conversation says "you" in Hebrew: whether its row is drawn, and which
           of the two forms is marked. */
        address: {
          hidden: at("you-address-row").hidden,
          m: byId["address-m"] ? byId["address-m"].getAttribute("aria-checked") : null,
          f: byId["address-f"] ? byId["address-f"].getAttribute("aria-checked") : null,
        },
        languagesSaid: {
          text: at("you-languages-said").textContent,
          hidden: at("you-languages-said").hidden,
        },
        ending: { text: at("you-ending-said").textContent, hidden: at("you-ending-said").hidden },
        forget: { label: at("you-forget").textContent, disabled: at("you-forget").disabled },
        /* One row an app: what it says it is, what it may do, and nothing that could be
           a credential (targum-internal#80). */
        connections: Array.from(at("connection-rows").children).map((row) => ({
          name: (row.querySelector(".conn-name") || {}).textContent,
          when: (row.querySelector(".conn-when") || {}).textContent,
          may: row.querySelector(".conn-scopes")
            ? row.querySelector(".conn-scopes").children.map((line) => line.children[1].textContent)
            : [],
          press: row.children[row.children.length - 1].textContent,
        })),
        promptsPanel: at("prompts").hidden,
        prompts: Array.from(at("prompt-rows").children).map((row) => ({
          name: row.children[0].textContent,
          says: row.children[1].textContent,
        })),
        promptsSaid: { text: at("prompts-said").textContent, hidden: at("prompts-said").hidden },
        connectionsSaid: {
          text: at("connections-said").textContent,
          hidden: at("connections-said").hidden,
        },
        /* The plan with plans on (design.md §12, "Free and Plan, behind a switch"): which
           card is drawn and what it says. Off, none of it is touched. */
        plan: {
          on: at("plan-on").hidden,
          free: at("plan-free").hidden,
          paid: at("plan-paid").hidden,
          freeSays: at("plan-free-says").textContent,
          offer: at("plan-offer").textContent,
          words: at("plan-words").textContent,
          wordsHidden: at("plan-words-row").hidden,
          paidSays: at("plan-paid-says").textContent,
          back: at("plan-back").textContent,
          topUps: at("plan-top-ups").children.map((one) => one.textContent),
        },
        posted,
        restarted,
      })
    );
  }, 600);
}, 20);
