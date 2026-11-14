/* Runs Add's description box against a stub document and reports what it drew.
 *
 *   node tests/js/add.js payload.json
 *
 * Add had no harness at all until targum-internal#253 put a spending path on it: a
 * description pressed with Continue runs one turn of conversation in place. That press
 * is what spends, so what it does is worth running rather than reading.
 *
 * `payload` gives the answers the stub `fetch` hands back, by path, and the lines the
 * script is driven with. What comes out is the status area's text, the cards it drew,
 * and every request that was made — because the requests are the half that matters:
 * a description must never reach `/prepare` or `/build` by itself.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

/** Every request the script made, in order, so a test can say what it did not do. */
const asked = [];

function answerFor(url) {
  const where = String(url).split("?")[0];
  const answers = payload.answers || {};
  if (Object.prototype.hasOwnProperty.call(answers, where)) return answers[where];
  // A path answered with nothing is not an error: most of Add's chatter on load — the
  // library's "is it already here", the languages — is beside the point here.
  return {};
}

global.fetch = (url, options) => {
  asked.push({
    path: String(url).split("?")[0],
    method: (options && options.method) || "GET",
    body: options && options.body ? JSON.parse(options.body) : null,
  });
  return Promise.resolve({ json: () => Promise.resolve(answerFor(url)) });
};

const said = {};
install({
  TargumStrings: {
    // The English written in the template is what a key with no catalogue says, which
    // is what these assertions read: a test that matched Russian would be testing the
    // catalogue rather than the script.
    t: (key, english, fill) =>
      Object.keys(fill || {}).reduce(
        (text, name) => text.split("{" + name + "}").join(String(fill[name])),
        english
      ),
    tn: (key, n, one, other, fill) =>
      Object.keys(Object.assign({ n }, fill || {})).reduce(
        (text, name) =>
          text.split("{" + name + "}").join(String(Object.assign({ n }, fill || {})[name])),
        n === 1 ? one : other
      ),
  },
  TargumLang: {
    into: () => "he",
    current: () => "he",
    set: () => {},
    switcher: () => {},
    onChange: () => {},
  },
  TARGUM_KEY: "test-key",
  TARGUM_LANGUAGES: { he: "Hebrew", en: "English" },
  location: { href: "http://localhost/add", search: "" },
  setTimeout: (fn) => later(fn),
});
// Nothing waits, and a build that stays waiting is asked after a bounded number of times
// rather than for ever: a poll that never settles would otherwise run the harness out of
// memory (targum-internal#715's waiting card).
let ticks = 0;
function later(fn) {
  ticks += 1;
  if (ticks < 400) fn();
  return 0;
}
global.setTimeout = later;
global.URLSearchParams = URLSearchParams;
global.FormData = class {};
global.Promise = Promise;

/* The two drop zones' labels come from the template, and the script reads their text
   at load to remember what they said at rest. A stub document has no template, so they
   are put here — the same thing `tests/js/account.js` does for the account panel's two
   halves. */
for (const zone of ["drop", "drop-translation", "drop-transcript"]) {
  for (const name of ["drop-label", "drop-note"]) {
    const part = element("span");
    part.className = name;
    part.textContent = name === "drop-label" ? "Choose a file" : "or drop one here";
    document.getElementById(zone).appendChild(part);
  }
}
/* The two language pickers, which the template fills from `INTO` and `READING` and the
   script reads back as `<select>.options`. A stub element has children and no options,
   so they are the same list under both names. */
for (const id of ["from", "to"]) {
  const pick = document.getElementById(id);
  const option = element("option");
  option.value = id === "from" ? "he" : "en";
  pick.appendChild(option);
  pick.options = pick.children;
  pick.value = option.value;
}
document.getElementById("how").appendChild(element("button"));

// The card's own helpers, for a run that goes on past Continue to a priced card, a wait
// and its end (targum-internal#715): `bring.js` draws the price and follows the build,
// `cancel.js` the wait's Cancel.
if (payload.card) {
  // `status.innerHTML = ""` empties the card in a browser; the stub kept every earlier
  // drawing under the new one, and a stale Confirm then answered for the card.
  Object.defineProperty(document.getElementById("status"), "innerHTML", {
    set() {
      this.children = [];
      this._text = "";
    },
    get() {
      return "";
    },
  });
  require(path.join(assets, "bring.js"));
  require(path.join(assets, "cancel.js"));
}
require(path.join(assets, "add.js"));

/** The status area, as a reader would read it. */
function statusText() {
  const status = byId.status;
  const out = [];
  const walk = (node) => {
    if (!node) return;
    if (node.textContent && (!node.children || !node.children.length)) out.push(node.textContent);
    (node.children || []).forEach(walk);
  };
  (status.children || []).forEach(walk);
  return out.filter(Boolean);
}

/** Every card the results drew, with its Choose. */
function cards() {
  const found = [];
  const walk = (node) => {
    if (!node) return;
    if (String(node.className || "").indexOf("found-result") === 0) {
      const texts = [];
      let choose = null;
      const inside = (child) => {
        if (String(child.tagName || "").toLowerCase() === "button") choose = child;
        else if (child.textContent) texts.push(child.textContent);
        (child.children || []).forEach(inside);
      };
      (node.children || []).forEach(inside);
      found.push({ lines: texts, choose });
    }
    (node.children || []).forEach(walk);
  };
  (byId.status.children || []).forEach(walk);
  return found;
}

const out = { steps: [] };

// The line under the box, before any press: it has to say that looking spends.
byId.given.value = payload.typed || "";
document.fire("input", {});
if (byId.given.dispatchEvent) byId.given.dispatchEvent({ type: "input" });
(byId.given.listeners || {}).input?.forEach((fn) => fn({}));
out.under = byId.understood.textContent || "";

// Continue. The look is a chain of promises — say, then poll, then the turn's cost —
// so the report waits for them to settle rather than reading a half-drawn page.
if (byId.go.onclick) byId.go.onclick({});

const settled = () => new Promise((done) => setImmediate(done));

(async () => {
  for (let n = 0; n < 20; n++) await settled();

  out.status = statusText();
  out.cards = cards().map((card) => card.lines);

  // Choose the one the payload names, if any. What matters is where it goes: the box,
  // and then Continue — the same path a pasted link takes.
  const chosen = cards()[payload.choose === undefined ? -1 : payload.choose];
  if (chosen && chosen.choose && chosen.choose.onclick) {
    asked.length = 0;
    chosen.choose.onclick({});
    for (let n = 0; n < 20; n++) await settled();
    out.afterChoose = { box: byId.given.value, asked: asked.map((one) => one.path) };
  }

  // Presses on the card, by their words, each settled before the next.
  for (const words of payload.press || []) {
    const found = [];
    const look = (node) => {
      if (!node) return;
      const tag = String(node.tagName || "").toLowerCase();
      if ((tag === "button" || tag === "a") && node.textContent === words) found.push(node);
      (node.children || []).forEach(look);
    };
    look(byId.status);
    if (!found.length) break;
    if (found[0].onclick) found[0].onclick({});
    for (let n = 0; n < 40; n++) await settled();
  }
  if (payload.card) {
    out.status = statusText();
    // Every run drawn on the card, with the language and direction it carries, and
    // every press with its classes: what §9 and §14.3 are held to.
    out.drawn = [];
    out.presses = [];
    const look = (node) => {
      if (!node || node.hidden) return;
      const tag = String(node.tagName || "").toLowerCase();
      if (tag === "button" || tag === "a") {
        out.presses.push({ text: node.textContent, className: node.className });
        return;
      }
      if (node._text) {
        out.drawn.push({
          tag,
          className: node.className || "",
          lang: (node.attrs || {}).lang || "",
          dir: (node.attrs || {}).dir || "",
          text: node._text,
        });
      }
      (node.children || []).forEach(look);
    };
    look(byId.status);
    out.go = Array.from(byId.go.classList._names);
    out.underHidden = !!byId.understood.hidden;
  }
  out.asked = asked;
  // Where the page sent the reader, if it went anywhere (a reference opens its portion).
  out.went = window.location.href;
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
})();
