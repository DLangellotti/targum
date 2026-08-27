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
  return Promise.resolve({ json: () => Promise.resolve(answers[at] || {}) });
};

require(path.join(assets, "you.js"));

const at = (id) => byId[id] || { textContent: "", value: "", hidden: true, children: [] };

/** The tick boxes in one list, as a person would read them. */
function ticks(id) {
  return at(id).children.map((label) => {
    const box = label.children[0];
    return {
      code: box.value,
      on: box.checked,
      fixed: box.disabled,
      experimental: label.children.some((child) => child.className === "beta"),
    };
  });
}

/** Do something to the page, the way a person would. */
function act(step) {
  if (step.type === "name") {
    at("you-name").value = step.value;
    at("you-name").fire("input", {});
  } else if (step.type === "press") {
    at(step.id).fire("click", {});
  } else if (step.type === "tick") {
    const box = at(step.list).children.map((label) => label.children[0]).find((one) => one.value === step.code);
    box.checked = !box.checked;
    box.fire("change", {});
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
          who: at("who").hidden,
          languages: at("languages").hidden,
          reading: at("reading").hidden,
          ending: at("ending").hidden,
        },
        name: at("you-name").value,
        email: at("you-email").textContent,
        avatar: at("you-avatar").textContent,
        kept: at("you-kept").textContent,
        learning: ticks("you-learning"),
        reads: ticks("you-reads"),
        said: { text: at("you-said").textContent, hidden: at("you-said").hidden },
        languagesSaid: {
          text: at("you-languages-said").textContent,
          hidden: at("you-languages-said").hidden,
        },
        ending: { text: at("you-ending-said").textContent, hidden: at("you-ending-said").hidden },
        forget: { label: at("you-forget").textContent, disabled: at("you-forget").disabled },
        posted,
        restarted,
      })
    );
  }, 600);
}, 20);
