/* Runs the Library's subscriptions row (`follow.js`, 2026-09-11) against a stub document.
 *
 *   node tests/js/follow.js payload.json
 *
 * The payload carries what `/series` answers, what this browser already follows and has
 * seen, and the presses to make. What comes back is the rows drawn, the state of each
 * Follow, what the store now says, and what `fresh()` would hand Learn.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const stored = {};
if (payload.follows) stored["targum:follows"] = JSON.stringify(payload.follows);
if (payload.seen) stored["targum:series-seen"] = JSON.stringify(payload.seen);
install({ TARGUM_KEY: "k", stored });

const asked = [];
global.fetch = (url, options) => {
  const clean = String(url).replace(/[?&]k=[^&]*/, "");
  asked.push(options && options.method === "POST" ? { path: clean, body: JSON.parse(options.body) } : clean);
  // The account, where the payload says somebody is signed in; 401 otherwise.
  if (clean === "/account/follows") {
    const signedIn = !!payload.account;
    return Promise.resolve({
      ok: signedIn,
      json: () => Promise.resolve(signedIn ? { signedIn: true, follows: payload.account } : {}),
    });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ series: payload.series || [] }) });
};

const section = document.getElementById("subscriptions");
section.hidden = true;
const host = document.getElementById("series");
require(path.join(assets, "follow.js"));

(async () => {
  for (let i = 0; i < 8; i++) await new Promise((resolve) => setImmediate(resolve));
  const rowOf = (id) => host.children.find((li) => li.attrs["data-series"] === id);
  for (const step of payload.do || []) {
    if (step.type === "follow") rowOf(step.id).querySelector(".series-follow").onclick();
  }
  const follow = global.window.TargumFollow;
  process.stdout.write(
    JSON.stringify({
      asked,
      shown: !section.hidden,
      rows: host.children.map((li) => {
        const by = (cls) => li.querySelector("." + cls);
        return {
          id: li.attrs["data-series"],
          name: by("series-name").textContent,
          now: by("series-now").textContent,
          follow: by("series-follow").textContent,
          pressed: by("series-follow").attrs["aria-pressed"],
          open: by("series-open") ? by("series-open").href : "",
        };
      }),
      follows: follow.follows(),
      fresh: follow.fresh(payload.series || []).map((one) => one.id),
      readers: (payload.series || []).map((one) => follow.readerOf(one)),
    }),
  );
})();
