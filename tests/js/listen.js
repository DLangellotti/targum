/* Runs the listening view's arithmetic (`listen.js`; design.md §12, "Listening is a view
 * of its own", 2026-10-10) with no page.
 *
 *   node tests/js/listen.js payload.json
 *
 * The payload is a list of calls, each `{fn, args}`; what comes back is each answer.
 */

"use strict";

const fs = require("fs");
const path = require("path");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

// No document: the file defines its arithmetic and does nothing else.
global.window = {};
require(path.join(assets, "listen.js"));

const listen = global.window.TargumListen;
const out = payload.calls.map((call) => {
  const answer = listen[call.fn].apply(null, call.args);
  return answer === undefined ? null : answer;
});
process.stdout.write(JSON.stringify(out));
