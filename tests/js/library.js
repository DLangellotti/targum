/* Runs the library page's own script against a stub document and reports what it drew.
 *
 *   node tests/js/library.js payload.json
 *
 * The payload carries the catalogue (as the page receives it), the readers the server
 * would answer with, the view — the filters and sort a reader has chosen — and a hash,
 * which is how Learn names the one text it sent this reader for. What comes back on
 * stdout is JSON: the rows drawn, in order, the controls around them, and which row (if
 * any) was marked as the one somebody was sent to.
 *
 * Read by `tests/test_library_js.py`, which supplies a real catalogue from the package
 * so the fixtures cannot drift from the thing being tested.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const byId = install({
  TARGUM_KEY: "k",
  TARGUM_CATALOGUE: payload.catalogue,
  TARGUM_COLLECTIONS: payload.collections || [],
  // targum's own playlists, a shelf of their own (design.md §12, 2026-10-09).
  TARGUM_SETS: payload.sets || [],
  TARGUM_LANGUAGES: { he: "Hebrew", ru: "Russian" },
  // The page's words in a reader's language, as the builder hands them over; none is English.
  TARGUM_STRINGS: payload.strings,
  // A first visit is a browser with no view remembered at all; every other run hands
  // the page the view a reader chose. `stored` lets a test put anything else in the
  // browser's store — the vocabulary the page counts, for one, and which collections
  // this reader has opened.
  stored: Object.assign(
    payload.firstVisit ? {} : { "targum:library": JSON.stringify(payload.views || payload.view || {}) },
    payload.opened ? { "targum:opened-groups": JSON.stringify(payload.opened) } : {},
    payload.stored || {}
  ),
  // The language switcher is not what is under test, and the real one wants a document
  // to hang tabs off. Its answer is fixed here so the rows are the only variable.
  TargumLang: {
    HOME: "he",
    order: (codes) => codes,
    current: () => payload.language || "he",
    // The switcher draws; the caller remembers. Both are asked for now.
    set: () => {},
    into: () => "",
    // Kept so a test can press another language once the page has drawn (`switchTo`).
    switcher: (host, codes, names, code, pick) => {
      global.targumPick = pick;
    },
    beta: () => false,
    betaNote: () => "",
  },
});

/* Every picture the page asks the server for, so a test can see the address. */
const asked = [];
global.Image = function () {
  return {
    set src(value) {
      asked.push(String(value));
    },
  };
};

/* The tree writes its address with `replaceState` (targum-internal#340). The stub keeps
   the hash the way a browser would, so a test can read where the page says it is. */
global.history = global.window.history = {
  replaceState: (state, title, url) => {
    const at = String(url).indexOf("#");
    global.location.hash = at < 0 ? "" : String(url).slice(at);
  },
};
// Learn links here with the id in the hash, and `pointAt` is what answers it.
/* The Library lands on its shelves since 2026-10-09 and the list is `#see`. Nearly every
   test here is about the list, so that is where they open unless they say `shelves` —
   which is a reader arriving at the Library with no address at all. */
if (payload.hash) global.location.hash = payload.hash;
else if (!payload.shelves) global.location.hash = "#see";

/* Two answers now: the shelf, and what is building on it (design.md §12, 2026-09-17).
   The library asks for both at once, so the stub tells them apart by the address rather
   than answering everything with the readers. */
var shelfAnswer = {
  readers: payload.readers || [],
  shared: payload.shared || [],
  covers: !!payload.covers,
  // How much of each catalogue text this reader knows, for the rows they have not
  // built (targum-internal#293). It is what "at my level" is measured with, so a
  // test of that has to be able to set it.
  catalogue: payload.catalogueKnown || {},
  // Whether somebody is signed in: a row's Subscribe is the account's.
  signedIn: !!payload.signedIn,
};

/* The hook `subscribe.js` hands a Library row (design.md §12, "A subscription is the
   account's"): what it is asked for is what a test reads. Its own switch is tested with
   the page that owns it (`test_subscribe_connector.py`). */
global.TargumSubscribe = global.window.TargumSubscribe = {
  button: (kind, given, words) => {
    const press = global.document.createElement(kind === "series" ? "button" : "a");
    press.textContent = words.subscribe;
    press.setAttribute("data-kind", kind);
    press.setAttribute("data-given", given);
    if (kind !== "series") press.href = "/subscribe?kind=" + kind + "&source=" + given;
    return press;
  },
};

global.fetch = (address) =>
  Promise.resolve({
    ok: true,
    json: () =>
      Promise.resolve(
        String(address).indexOf("/jobs") >= 0
          ? { jobs: payload.jobs || [] }
          : String(address).indexOf("/portions") >= 0
            ? payload.portions || {}
            : shelfAnswer
      ),
  });

/* The one search (design.md §12, "One search, everywhere", 2026-10-09): the Library's box
   opens it rather than narrowing the list, so what it was opened with is what a test reads. */
const searched = [];
global.TargumPalette = global.window.TargumPalette = {
  show: (on, options) => searched.push(Object.assign({ on: on }, options || {})),
};

require(path.join(assets, "strings.js"));
require(path.join(assets, "charts.js"));
require(path.join(assets, "scenes.js"));
require(path.join(assets, "covers.js"));
require(path.join(assets, "library.js"));

// The page draws once its own request for /readers resolves. One turn of the microtask
// queue is enough; nothing here waits on a timer.
setTimeout(() => {
  if (payload.switchTo) global.targumPick(payload.switchTo);
  /* Two shapes over one list since 2026-09-17 (design.md §12): cards by default, the
     table one press away. Whichever is on is the one filled, so the rows reported are
     read off the host that has them. A card has no columns, so `cells` comes back empty
     there and a test wanting them asks for the table — see `draw()` in the Python. */
  /* Presses, in order, before anything is read (targum-internal#340): `{tab: "Beit
     Midrash"}`, `{door: "tanakh"}`, `{crumb: true}` for the way back to the doors. */
  const doorItems = () =>
    byId["cards"].children.filter((c) => String(c.className).indexOf("door-item") >= 0);
  (payload.do || []).forEach((step) => {
    /* A kind door on the shelves (board Library): `{kindDoor: "midrash"}` is the Jewish
       texts, `{kindDoor: "article"}` News. `{tab: …}` is the old name for the first. */
    const kindDoor = step.kindDoor || (step.tab ? "midrash" : "");
    if (kindDoor) {
      const row = (byId["lib-doors"].children || []).find((c) => String(c.className) === "lib-doors-row");
      const door = row && row.children.find((c) => c.getAttribute("data-door") === kindDoor);
      if (door) door.fire("click", {});
    }
    /* A See all menu: `{menu: "kind", pick: "story"}`. */
    if (step.menu) {
      const box = byId["see-menus"].children.find((c) => c.getAttribute("data-menu") === step.menu);
      const list = box && box.children[1];
      const item = list && list.children.find((c) => c.getAttribute("data-value") === step.pick);
      if (box) box.children[0].fire("click", {});
      if (item) item.fire("click", {});
    }
    /* Show more, `{more: true}`, and a column head, `{sort: "title"}`. */
    if (step.more) byId["see-more"].fire("click", {});
    if (step.sort) {
      const head = byId["rows-head"].children.find((c) => String(c.className) === "see-head-" + step.sort);
      if (head) head.fire("click", {});
    }
    if (step.door) {
      const item = doorItems().find((c) => c.children[0].getAttribute("data-door") === step.door);
      if (item) item.children[0].fire("click", {});
    }
    /* The Weekly portion shelf's calendar (targum-internal#411): `{schedule: "Israel"}`. */
    if (step.schedule) {
      const press = byId["portion-schedule"].children.find((c) => c.textContent === step.schedule);
      if (press) press.fire("click", {});
    }
    /* The shelves: `{see: "now"}` presses a shelf's See all, `{back: true}` the way back,
       `{type: "ruth"}` types into the search box. */
    if (step.see) {
      const section = byId["shelves"].children.find((c) => c.getAttribute && c.getAttribute("data-band") === step.see);
      const all = section && section.children[0].children.find((c) => c.className === "band-all");
      if (all) all.fire("click", {});
    }
    if (step.back) byId["see-back-link"].fire("click", {});
    if (step.type !== undefined) {
      byId["find"].value = step.type;
      byId["find"].fire("input", {});
    }
    if (step.crumb) {
      const back = byId["crumbs"].children.find((c) => c.tagName === "button");
      if (back) back.fire("click", {});
    }
  });
  const doors = doorItems().map((item) => ({
    id: item.children[0].getAttribute("data-door"),
    says: item.children[0].children.map((c) => c.textContent),
  }));
  const rows = byId["catalogue"].children;
  const wearing = (c, name) => String(c.className || "").split(" ").indexOf(name) >= 0;
  const below = (node, name) => {
    for (const c of node.children || []) {
      if (wearing(c, name)) return c;
      const deeper = below(c, name);
      if (deeper) return deeper;
    }
    return null;
  };
  /* One row of See all (board SeeAllDesk): the picture, the title and its English, what it
     is and whose, the blurb, its length, how much is known, and the build's cell. */
  const read = (row) => {
    const open = row.children[0];
    const find = (name) => below(open, name) || { textContent: "", attrs: {}, children: [] };
    const sub = row.children.find((c) => wearing(c, "row-sub"));
    const press = sub && sub.children[0];
    return {
      id: row.getAttribute("data-row") || "",
      title: find("row-name").textContent,
      english: find("row-english").textContent,
      englishLang: find("row-english").attrs["lang"] || "",
      meta: find("row-meta").textContent,
      by: find("row-by").textContent,
      blurb: find("row-blurb").textContent,
      blurbLang: find("row-blurb").attrs["lang"] || "",
      level: find("row-level").textContent,
      chip: find("row-next").textContent,
      fresh: find("row-new").textContent,
      media: (below(open, "card-media") || { attrs: {} }).attrs["aria-label"] || "",
      length: find("see-length-said").textContent,
      kind: find("see-length-kind").textContent.replace(/ · $/, ""),
      known: find("see-known-say").textContent,
      near: wearing(find("see-known"), "near"),
      meter: !!below(find("see-known"), "meter"),
      state: open.children[open.children.length - 1].textContent,
      group: open.getAttribute("data-group") || "",
      expanded: open.getAttribute("aria-expanded") || "",
      member: wearing(row, "member"),
      cells: [find("see-length-said").textContent, find("see-known-say").textContent],
      draws: (row.children.find((c) => wearing(c, "draw")) || {}).textContent || "",
      subscribe: press
        ? { kind: press.getAttribute("data-kind"), given: press.getAttribute("data-given"), text: press.textContent }
        : null,
      opens: open.tagName,
      href: open.href || "",
    };
  };
  const menus = (byId["see-menus"].children || []).map((box) => {
    const press = box.children[0];
    const list = box.children[1];
    return {
      id: box.getAttribute("data-menu"),
      value: (press.children.find((c) => wearing(c, "see-menu-value")) || {}).textContent || "",
      options: list.children.map((c) => c.textContent),
      on: (list.children.find((c) => c.getAttribute("aria-checked") === "true") || {}).textContent || "",
    };
  });
  const menu = (id) => menus.find((m) => m.id === id) || { options: [], on: "", value: "" };
  /* Written, then done. The page polls while anything is building (design.md §12,
     2026-09-17) and an interval keeps node alive for ever; this is a reporter, so it
     says what it drew and stops rather than waiting for a build that will never
     finish. */
  process.stdout.write(
    JSON.stringify({
      rows: rows.map(read),
      // The stub's classList keeps its own set and never writes className back.
      pointed: rows.filter((row) => row.classList.contains("pointed")).map((row) => read(row).title),
      columns: byId["rows-head"].children.map((c) => c.textContent.trim()).filter(Boolean),
      tally: byId["tally"].textContent,
      more: !byId["see-more"].hidden,
      listShown: !byId["picked"].hidden,
      kinds: menu("kind").options,
      kindOn: menu("kind").on,
      fitOn: menu("level").on,
      languageOn: menu("language").on,
      menus: menus.map((m) => m.id),
      menusShown: !byId["see-menus"].hidden,
      seeTitle: byId["see-title"].hidden ? "" : byId["see-title"].textContent,
      seeing: !!(global.document.body.classList && global.document.body.classList.contains("is-seeing")),
      empty: byId["picked-empty"].textContent,
      // The one line that says what the list is.
      note: byId["picked-note"].textContent,
      /* The shelves (design.md §12, 2026-10-09): whether they are up, and each shelf drawn,
         in order, with its heading, its note and its cards. */
      pictures: asked,
      shelving: !byId["shelves"].hidden,
      /* The Tanakh's door at the head of the shelves (design.md §12, 2026-10-09). */
      /* The kind doors on the shelves (board Library). */
      kindDoors: byId["lib-doors"].hidden
        ? []
        : ((byId["lib-doors"].children || []).find((c) => String(c.className) === "lib-doors-row") || { children: [] }).children.map(
            (door) => ({ id: door.getAttribute("data-door"), href: door.href || "", says: door.children.map((c) => c.textContent) })
          ),
      backShown: !!byId["see-back"] && !byId["see-back"].hidden,
      shelves: (byId["shelves"].children || [])
        .filter((c) => c.getAttribute && c.getAttribute("data-band"))
        .map((section) => {
          const head = section.children[0];
          const note = section.children.find((c) => c.className === "band-note");
          const list = section.children.find((c) => c.className === "band-cards");
          return {
            band: section.getAttribute("data-band"),
            name: head.children[0].textContent,
            seeAll: !!head.children.find((c) => c.className === "band-all"),
            note: note ? note.textContent : "",
            cards: list.children.map((item) => {
              const open = item.children[0];
              const part = (name) =>
                (open.children.find((c) => String(c.className).split(" ").indexOf(name) >= 0) || {}).textContent || "";
              const cover = open.children[0];
              const pictures = (cover.children || []).filter((c) => String(c.className).indexOf("thumb") >= 0);
              return {
                id: item.getAttribute("data-row") || item.getAttribute("data-set") || "",
                kind: part("band-kind"),
                title: part("band-title"),
                known: part("band-known"),
                near: !!open.children.find((c) => String(c.className) === "band-known near"),
                chip: part("row-next"),
                opens: open.tagName,
                href: open.href || "",
                pictures: pictures.length,
              };
            }),
          };
        }),
      shelvesNote: ((byId["shelves"].children || []).find((c) => String(c.className).indexOf("shelves-note") >= 0) || {}).textContent || "",
      // The heading over the share column, and whether it can be pressed.
      find: byId["find"].value || "",
      searched,
      // The Beit Midrash: the tabs on offer, the doors drawn, the trail, and the address.
      doors,
      crumbs: byId["crumbs"].hidden ? "" : byId["crumbs"].textContent,
      hash: global.location.hash || "",
      /* The Weekly portion shelf (targum-internal#411): whether it is up, its cards in
         order, and the calendar switch where the two calendars part company. */
      portions: {
        hidden: !byId["portions"] || !!byId["portions"].hidden,
        cards: (byId["portion-cards"] ? byId["portion-cards"].children : []).map((item) => {
          const open = item.children[0];
          const part = (name) => (open.children.find((c) => c.className === name) || {}).textContent || "";
          return {
            slug: item.getAttribute("data-portion") || "",
            thisWeek: String(item.className).indexOf("this-week") >= 0,
            when: part("portion-when"),
            name: part("portion-name"),
            english: part("portion-english"),
            span: part("portion-span"),
            href: open.href || "",
            tag: open.tagName,
          };
        }),
        schedule: !byId["portion-schedule"] || byId["portion-schedule"].hidden
          ? []
          : byId["portion-schedule"].children.map((c) => ({
              text: c.textContent,
              on: c.getAttribute("aria-pressed") === "true",
            })),
        kept: global.localStorage.getItem("targum:schedule") || "",
      },
      views: JSON.parse(global.localStorage.getItem("targum:library") || "{}"),
    })
  );
  process.exit(0);
}, 20);
