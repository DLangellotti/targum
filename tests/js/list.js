/* Runs a playlist's neighbour arithmetic (`list.js`, targum-internal#366) with no page.
 *
 *   node tests/js/list.js payload.json
 *
 * The payload is a list of cases, each `{items, at}`; what comes back is, for each,
 * what `neighbours` answered and the address `addressOf` makes for the next one. With
 * `addUp` instead, a list of kept figures by place, and what the end card adds up.
 */

"use strict";

const fs = require("fs");
const path = require("path");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

// Off a disk: the file defines its arithmetic and does nothing else.
global.window = {};
global.location = { protocol: "file:", search: "" };
require(path.join(assets, "list.js"));

const list = global.window.TargumList;
if (payload.addUp) {
  process.stdout.write(JSON.stringify(payload.addUp.map((kept) => list.addUp(kept))));
  process.exit(0);
}
const out = payload.cases.map((one) => {
  const near = list.neighbours(one.items, one.at);
  const next = near.next === null ? null : list.addressOf(one.items[near.next], "7", near.next, true);
  const back = near.back === null ? null : list.addressOf(one.items[near.back], "7", near.back, false);
  return { near, next, back };
});
process.stdout.write(JSON.stringify(out));
