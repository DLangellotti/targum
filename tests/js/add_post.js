/* Runs Add's "Bring a post" form against a stub document and reports what it asked.
 *
 *   node tests/js/add_post.js payload.json
 *
 * targum-internal#158. The form quotes a post the reader typed in, and the one thing on
 * it that spends — reading the words in its pictures — is a press on the card, never the
 * form's own Continue. So what is reported is every request, in order, with its body:
 * the half a test can say "and nothing else" about.
 *
 * `payload.answers` gives what the stub `fetch` hands back, by path; `payload.fields`
 * what is typed; `payload.files` the names of the files chosen; `payload.press` the
 * card's buttons to press afterwards, by their words. `payload.refusal` runs the box
 * instead: a link typed there and refused, and the form opened from the refusal.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const asked = [];
const uploaded = [];

function answerFor(url, n) {
  const where = String(url).split("?")[0];
  const answers = payload.answers || {};
  if (!Object.prototype.hasOwnProperty.call(answers, where)) return {};
  const said = answers[where];
  // A list answers each ask in turn: the quote, then the quote with its pictures read.
  return Array.isArray(said) ? said[Math.min(n, said.length - 1)] : said;
}

const times = {};
global.fetch = (url, options) => {
  const where = String(url).split("?")[0];
  asked.push({
    path: where,
    body: options && options.body ? JSON.parse(options.body) : null,
  });
  times[where] = (times[where] || 0) + 1;
  const said = answerFor(url, times[where] - 1);
  return Promise.resolve({ ok: true, json: () => Promise.resolve(said) });
};

install({
  TargumStrings: {
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
    into: () => "en",
    current: () => "he",
    set: () => {},
    switcher: () => {},
    onChange: () => {},
  },
  // The upload and the wait are bring.js's. Stood in: the upload names what went up and
  // answers as the chunked door does — `uploads` for pictures, `upload` for one video.
  TargumBring: {
    isPicture: (file) => /\.(png|jpe?g|webp|heic|heif)$/i.test(file.name),
    isPdf: () => false,
    upload(files) {
      uploaded.push(files.map((file) => file.name));
      const pictures = files.filter((file) => /\.(png|jpe?g|webp)$/i.test(file.name));
      return Promise.resolve(
        pictures.length ? { uploads: pictures.map((_, n) => "u" + n) } : { upload: "v0" }
      );
    },
    wait: () => "About a minute.",
    plain: (message) => message,
  },
  TARGUM_KEY: "test-key",
  TARGUM_LANGUAGES: { he: "Hebrew", en: "English" },
  location: { href: "http://localhost/add", search: "" },
});
global.setTimeout = (fn) => fn();
global.setInterval = () => 0;
global.clearInterval = () => {};
global.URLSearchParams = URLSearchParams;

/* `innerHTML` as the page uses it: cleared, or set to one empty `<b>` for a title. */
const make = document.createElement;
document.createElement = (tag) => {
  const made = make(tag);
  Object.defineProperty(made, "innerHTML", {
    get: () => "",
    set(value) {
      made.children = [];
      if (value === "<b></b>") {
        const bold = make("b");
        bold.className = "b";
        made.appendChild(bold);
      }
    },
  });
  return made;
};
for (const id of ["status"]) {
  const status = document.getElementById(id);
  Object.defineProperty(status, "innerHTML", {
    get: () => "",
    set() {
      status.children = [];
    },
  });
}

for (const zone of ["drop", "drop-translation", "drop-transcript"]) {
  for (const name of ["drop-label", "drop-note"]) {
    const part = element("span");
    part.className = name;
    part.textContent = "at rest";
    document.getElementById(zone).appendChild(part);
  }
}
for (const id of ["from", "to"]) {
  const pick = document.getElementById(id);
  const option = element("option");
  option.value = id === "from" ? "he" : "en";
  pick.appendChild(option);
  pick.options = pick.children;
  pick.value = option.value;
}
document.getElementById("how").appendChild(element("button"));
/* The switch the template draws: three segments, Instagram pressed. */
for (const platform of ["instagram", "tiktok", "x"]) {
  const segment = element("button");
  segment.className = "segment";
  segment.setAttribute("data-platform", platform);
  segment.setAttribute("aria-pressed", platform === "instagram" ? "true" : "false");
  document.getElementById("post-where").appendChild(segment);
}
document.getElementById("post-form").hidden = true;

require(path.join(assets, "add.js"));

const settled = () => new Promise((done) => setImmediate(done));
async function calm() {
  for (let n = 0; n < 30; n++) await settled();
}

function statusText() {
  const out = [];
  const walk = (node) => {
    if (!node) return;
    if (node.textContent && (!node.children || !node.children.length)) out.push(node.textContent);
    (node.children || []).forEach(walk);
  };
  (byId.status.children || []).forEach(walk);
  return out.filter(Boolean);
}

function buttons() {
  const found = [];
  const walk = (node) => {
    if (String(node.tagName || "").toLowerCase() === "button") found.push(node);
    (node.children || []).forEach(walk);
  };
  (byId.status.children || []).forEach(walk);
  return found;
}

function pressed() {
  return byId["post-where"].children
    .filter((one) => one.getAttribute("aria-pressed") === "true")
    .map((one) => one.getAttribute("data-platform"));
}

(async () => {
  const out = {};
  if (payload.refusal) {
    byId.given.value = payload.refusal;
    (byId.given.listeners.input || []).forEach((fn) => fn({}));
    byId.go.onclick({});
    await calm();
    out.refused = statusText();
    const bring = buttons().find((one) => one.textContent === "Bring a post");
    out.offered = !!bring;
    if (bring) {
      bring.onclick({});
      out.link = byId["post-link"].value;
      out.platform = pressed();
      out.open = !byId["post-form"].hidden && byId["bring-box"].hidden;
    }
    out.asked = asked;
    process.stdout.write(JSON.stringify(out));
    process.exit(0);
  }

  byId["post-open"].onclick({});
  out.open = !byId["post-form"].hidden && byId["bring-box"].hidden;
  out.expanded = byId["post-open"].getAttribute("aria-expanded");
  const fields = payload.fields || {};
  for (const [id, value] of Object.entries(fields)) byId["post-" + id].value = value;
  if (fields.link) (byId["post-link"].listeners.input || []).forEach((fn) => fn({}));
  out.platform = pressed();
  if (payload.files) {
    byId["post-file"].files = payload.files.map((name) => ({ name, size: 2048 }));
    byId["post-file"].onchange({});
  }
  out.chips = (byId["post-files"].children || []).length;
  byId["post-go"].onclick({});
  await calm();
  out.status = statusText();
  out.uploaded = uploaded;
  for (const words of payload.press || []) {
    const button = buttons().find((one) => one.textContent === words);
    if (!button) {
      out.missing = words;
      break;
    }
    button.onclick({});
    await calm();
  }
  out.after = statusText();
  out.asked = asked;
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
})();
