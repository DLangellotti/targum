/* Runs the language menu against a stub document and reports what it drew and did.
 *
 *   node tests/js/lang.js payload.json
 *
 * The menu is the one control every desk page shares (design.md §13, 2026-09-13): which
 * languages it lists, which one it says the page is in, what a press remembers — on the
 * page and on the account — and that the same call pointed anywhere but the nav still
 * draws tabs.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const told = [];
install({
  TARGUM_LANGUAGES: { he: "Hebrew", yi: "Yiddish", arc: "Aramaic" },
  stored: payload.stored || {},
  TargumSync: { language: (code) => told.push(code) },
  CustomEvent: function (type, init) {
    this.type = type;
    this.detail = init && init.detail;
  },
});
global.CustomEvent = global.window.CustomEvent;
const heard = [];
global.window.dispatchEvent = (event) => heard.push(event.detail);
// The address the page was arrived at, for a link out of a reader that carries the text's
// language (2026-10-07), and what the page put in its place.
const replaced = [];
if (payload.href) {
  const at = new URL(payload.href);
  Object.assign(global.location, { href: at.href, search: at.search, hash: at.hash, pathname: at.pathname });
}
global.history = { state: null, replaceState: (state, title, url) => replaced.push(url) };
global.window.history = global.history;

require(path.join(assets, "lang.js"));
const lang = global.window.TargumLang;

// Which language a page settles on as it loads, given only what it has something in.
const current = payload.currentOf ? lang.current(payload.currentOf) : null;

const nav = document.getElementById("langs");
nav.id = "langs";
const picked = [];
lang.switcher(nav, payload.pageCodes || ["he"], window.TARGUM_LANGUAGES, payload.chosen || "he", (code) =>
  picked.push(code)
);

const open = nav.children[0];
const panel = nav.children[1];
const items = panel ? panel.children.filter((c) => c.getAttribute("role") === "menuitemradio") : [];
const starts = panel ? panel.children.filter((c) => c.getAttribute("role") === "menuitem") : [];
// Everything drawn under the menu, for what must not be there (a flag, since 2026-10-09).
const everything = (node) => [node].concat((node.children || []).flatMap(everything));
const before = {
  hidden: nav.hidden,
  // The name alone; the badge beside it is its own field (design.md §12, 2026-10-09).
  label: open ? (open.children.find((c) => String(c.className) === "lang-name") || {}).textContent || "" : "",
  badge: open ? (open.children.find((c) => String(c.className).indexOf("lang-status") === 0) || {}).textContent || "" : "",
  badges: items.map((i) => {
    const named = i.children.find((c) => String(c.className) === "lang-item") || { children: [] };
    return (named.children.find((c) => String(c.className).indexOf("lang-status") === 0) || {}).textContent || "";
  }),
  items: items.map((i) => i.getAttribute("data-code")),
  checked: items.filter((i) => i.getAttribute("aria-checked") === "true").map((i) => i.getAttribute("data-code")),
  heads: panel ? panel.children.filter((c) => String(c.className) === "lang-head").map((c) => c.textContent) : [],
  starts: starts.map((i) => i.getAttribute("data-code")),
  greetings: Object.fromEntries(
    items.concat(starts).map((i) => [
      i.getAttribute("data-code"),
      (i.children.find((c) => String(c.className) === "lang-greeting") || {}).textContent || "",
    ])
  ),
  flags: everything(nav).filter((n) => String(n.className || "").indexOf("flag") >= 0).length,
  panelHidden: panel ? panel.hidden : true,
};
if (open) open.fire("click", { stopPropagation() {} });
const openedPanel = panel ? !panel.hidden : false;
const target = items.concat(starts).find((i) => i.getAttribute("data-code") === payload.press);
if (target) target.fire("click", {});

// The same call anywhere but the nav: tabs, as the definition-language control has them.
const other = document.getElementById("definitions");
lang.switcher(other, ["en", "ru"], { en: "English", ru: "Russian" }, "en", () => {}, {
  tag: () => false,
});

process.stdout.write(
  JSON.stringify({
    before,
    current,
    carried: lang.carried(),
    replaced,
    learning: global.localStorage.getItem("targum:learning"),
    openedPanel,
    picked,
    told,
    heard,
    stored: global.localStorage.getItem("targum:language"),
    afterPanelHidden: panel ? panel.hidden : true,
    tabs: other.children.map((c) => c.getAttribute("role")),
  })
);
