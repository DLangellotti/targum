/* Runs what home's Continue would hold (`home.js`, `TargumHome.gather`) and reports it.
 *
 *   node tests/js/home.js payload.json
 *
 * The payload is the shelf's readers, the places the account handed back, newest first,
 * and the language the page is in. What comes back is one entry a card: the document of
 * the reader it carries, if any, and the hash and path of the place it picks up at.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

install({
  TARGUM_KEY: "k",
  TARGUM_LANGUAGES: { he: "Hebrew", en: "English", ru: "Russian" },
  TargumLang: { HOME: "he", order: (codes) => codes, current: () => "he", set: () => {} },
  // This browser's own records, where a test says: `targum:places`, `targum:docs`.
  stored: payload.stored || {},
});

require(path.join(assets, "strings.js"));
require(path.join(assets, "charts.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "shelf.js"));
require(path.join(assets, "home.js"));

/* `next`: where a card for this reader and place picks up, given `targum:docs`. */
if (payload.next) {
  const { reader, place, docs } = payload.next;
  process.stdout.write(JSON.stringify(global.window.TargumHome.next(reader, place, docs || {})));
  process.exit(0);
}

/* `account` is what `/account/places` handed back. Given, the places are the page's own
   merge of it with this browser's, as home draws them; otherwise `places` as given. */
const places = payload.account
  ? global.window.TargumHome.places(payload.account)
  : payload.places || [];
const cards = global.window.TargumHome.gather(
  payload.readers || [],
  places,
  payload.building || [],
  payload.opened || {},
  payload.code || "he"
);
process.stdout.write(
  JSON.stringify(
    cards.map((card) => ({
      reader: card.reader ? card.reader.document : null,
      place: card.place
        ? { hash: card.place.hash, path: card.place.path, title: card.place.title || "" }
        : null,
    }))
  )
);
