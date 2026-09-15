/* Runs the account corner against a stub document and reports the hours it drew.
 *
 *   node tests/js/account.js payload.json
 *
 * The month's hours stand in the account panel and, where the page has the line, under
 * the ledger on Your Progress (targum-internal#237): drawn whenever there is an
 * allowance, with the day it resets, and never where there is none.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

let changed = null;
install({
  TargumSync: {
    who: payload.who || null,
    onChange: (handler) => {
      changed = handler;
    },
    signIn: () => Promise.resolve({}),
    signOut: () => Promise.resolve(),
  },
});
global.URLSearchParams = URLSearchParams;

// The panel's two halves are the template's; the script finds them by class.
const panel = document.getElementById("account-panel");
for (const name of ["signed-out", "signed-in"]) {
  const half = element("div");
  half.className = name;
  panel.appendChild(half);
}
if (payload.ledgerLine !== false) document.getElementById("hours-line").hidden = true;
document.getElementById("account-hours").hidden = true;

require(path.join(assets, "account.js"));
if (changed) changed();

const line = (id) => ({ hidden: Boolean(byId[id].hidden), text: byId[id].textContent });
process.stdout.write(JSON.stringify({ ledger: line("hours-line"), panel: line("account-hours") }));
