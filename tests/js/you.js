/* Runs the profile page's script against a stub document and reports what it did.
 *
 *   node tests/js/you.js payload.json
 *
 * The page draws who is signed in and holds the two controls that end an account. Both
 * are things that are either wrong quietly or wrong forever, which is why the script is
 * run rather than read.
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

/** Do something to the page, the way a person would. */
function act(step) {
  if (step.type === "name") {
    at("you-name").value = step.value;
    at("you-name").fire("input", {});
  } else if (step.type === "press") {
    at(step.id).fire("click", {});
  }
}

/* Two beats: one for the fetch that draws the page, one for the debounce on the name
   field, which is the whole reason a keystroke is not a request. */
setTimeout(() => {
  (payload.do || []).forEach(act);
  setTimeout(() => {
    process.stdout.write(
      JSON.stringify({
        stranger: at("stranger").hidden,
        panels: {
          who: at("who").hidden,
          reading: at("reading").hidden,
          ending: at("ending").hidden,
        },
        name: at("you-name").value,
        email: at("you-email").textContent,
        avatar: at("you-avatar").textContent,
        kept: at("you-kept").textContent,
        said: { text: at("you-said").textContent, hidden: at("you-said").hidden },
        ending: { text: at("you-ending-said").textContent, hidden: at("you-ending-said").hidden },
        forget: { label: at("you-forget").textContent, disabled: at("you-forget").disabled },
        posted,
        restarted,
      })
    );
  }, 600);
}, 20);
