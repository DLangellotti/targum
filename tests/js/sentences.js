/* Runs the Sentences tab's comparison (`sentences.js`; design.md §12, "Sentences:
 * dictation and fill the gap", 2026-10-27) with no page.
 *
 *   node tests/js/sentences.js payload.json
 *
 * The payload is a list of calls, each `{fn, args}`; what comes back is each answer.
 */

"use strict";

const fs = require("fs");
const path = require("path");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

// No document: the file defines its comparison and does nothing else.
global.window = {};
require(path.join(assets, "sentences.js"));

const sentences = global.window.TargumSentences;
const out = payload.calls.map((call) => {
  const answer = sentences[call.fn].apply(null, call.args);
  return answer === undefined ? null : answer;
});
process.stdout.write(JSON.stringify(out));
