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

require(path.join(assets, "lang.js"));
const lang = global.window.TargumLang;

const nav = document.getElementById("langs");
nav.id = "langs";
const picked = [];
lang.switcher(nav, payload.pageCodes || ["he"], window.TARGUM_LANGUAGES, payload.chosen || "he", (code) =>
  picked.push(code)
);

const open = nav.children[0];
const panel = nav.children[1];
const items = panel ? panel.children.filter((c) => c.getAttribute("role") === "menuitemradio") : [];
const before = {
  hidden: nav.hidden,
  label: open ? open.textContent : "",
  items: items.map((i) => i.getAttribute("data-code")),
  checked: items.filter((i) => i.getAttribute("aria-checked") === "true").map((i) => i.getAttribute("data-code")),
  more: panel ? (panel.children.find((c) => String(c.className) === "lang-more") || {}).href || "" : "",
  panelHidden: panel ? panel.hidden : true,
};
if (open) open.fire("click", { stopPropagation() {} });
const openedPanel = panel ? !panel.hidden : false;
const target = items.find((i) => i.getAttribute("data-code") === payload.press);
if (target) target.fire("click", {});

// The same call anywhere but the nav: tabs, as the definition-language control has them.
const other = document.getElementById("definitions");
lang.switcher(other, ["en", "ru"], { en: "English", ru: "Russian" }, "en", () => {}, {
  tag: () => false,
});

process.stdout.write(
  JSON.stringify({
    before,
    openedPanel,
    picked,
    told,
    heard,
    stored: global.localStorage.getItem("targum:language"),
    afterPanelHidden: panel ? panel.hidden : true,
    tabs: other.children.map((c) => c.getAttribute("role")),
    // What sits beside each name: a drawn flag, or the empty room one would take.
    flags: Object.fromEntries(
      items.map((item) => {
        const named = item.children[0];
        const box = named && named.children ? named.children[0] : null;
        const drawn = box && String(box.className).includes("none") ? "none" : box && box.innerHTML ? "flag" : "";
        return [item.getAttribute("data-code"), drawn];
      })
    ),
  })
);
