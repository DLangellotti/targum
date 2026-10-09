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
    if (step.tab) {
      const tab = byId["where"].children.find((c) => c.textContent === step.tab);
      if (tab) tab.fire("click", {});
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
  const textCards = byId["cards"].children.filter(
    (c) => String(c.className).indexOf("door-item") < 0
  );
  const browsing = byId["catalogue"].children.length === 0 && textCards.length > 0;
  const rows = browsing ? textCards : byId["catalogue"].children;
  const readCard = (item) => {
    const open = item.children[0];
    const what = open.children[1] || { children: [] };
    /* By word, not by whole string: the lately-arrived mark shares the scene label's
       element and its class, and an exact match came back empty for both. */
    const wearing = (c, name) => String(c.className || "").split(" ").indexOf(name) >= 0;
    // Anywhere under the card's words: the title and its English share a line since
    // 2026-10-09, inside `.card-head`.
    const below = (node, name) => {
      for (const c of node.children || []) {
        if (wearing(c, name)) return c;
        const deeper = below(c, name);
        if (deeper) return deeper;
      }
      return null;
    };
    const find = (name) => below(what, name) || {};
    return {
      id: item.getAttribute("data-row") || "",
      title: find("card-title").textContent || "",
      blurb: find("card-blurb").textContent || "",
      blurbLang: (find("card-blurb").attrs || {})["lang"] || "",
      near: String(find("card-known").className || "").indexOf("near") >= 0,
      fit: "",
      media: (open.children[0].children.find((c) => c.className === "card-media") || {}).attrs
        ? open.children[0].children.find((c) => c.className === "card-media").attrs["aria-label"] || ""
        : "",
      english: find("card-english").textContent || "",
      englishLang: (find("card-english").attrs || {})["lang"] || "",
      after: "",
      scene: find("card-scene").textContent || "",
      // Arrived lately (targum-internal#315). Its own field: it stands where the scene
      // label does, and a test asking "is this marked new" should not have to know that.
      fresh: find("card-new").textContent || "",
      chip: find("row-next").textContent || "",
      state: find("row-state").textContent || "",
      // A build in progress, drawn as a card that is not a press (design.md §12,
      // 2026-09-17): the word over the title, and the sentence saying where it has got.
      making: find("card-making").textContent || "",
      meta: find("card-meta").textContent || "",
      known: (find("card-known").children || []).map((c) => c.textContent).join(""),
      group: open.getAttribute("data-group") || "",
      expanded: open.getAttribute("aria-expanded") || "",
      member: false,
      cells: [],
      draws: "",
      opens: open.tagName,
      href: open.href || "",
    };
  };
  const read = (row) => {
    // A collection stays a row even among cards, so the shape is read off the element
    // rather than off the mode: `.card` is a card and anything else is a row.
    if (browsing && String(row.children[0].className || "").indexOf("card") === 0) {
      return readCard(row);
    }
    const open = row.children[0];
    return {
      id: row.getAttribute("data-row") || "",
      // The title cell holds a scene label and a chip beside the Hebrew; the bdi is it.
      title: (open.children[1].children[0].children.find((c) => c.tagName === "bdi") || open.children[1].children[0]).textContent,
      fit: (open.children[1].children.find((c) => c.className === "row-fit") || {}).textContent || "",
      // The one word beside the title that says what can be played: "audio", "video",
      // or nothing. One word, never two — a video row does not also say audio.
      media: (open.children[1].children.find((c) => c.className === "row-audio" || c.className === "row-video") || {}).textContent || "",
      english: (open.children[1].children.find((c) => c.className === "row-english") || {}).textContent || "",
      // The language that cell claims to be in (targum-internal#289): `en` until the
      // catalogue had a title in anything else.
      englishLang: (() => {
        const line = open.children[1].children.find((c) => c.className === "row-english");
        return line ? line.attrs["lang"] || "" : "";
      })(),
      // What follows the English on the same line: a byline on a text, "· 6 texts" on a
      // collection. Its own child, so the stub's textContent does not carry it.
      after: (() => {
        const line = open.children[1].children.find((c) => c.className === "row-english");
        const tail = line && line.children.find((c) => c.className === "row-by-after");
        return tail ? tail.textContent : "";
      })(),
      scene: (open.children[1].children[0].children.find((c) => c.className === "row-scene") || {}).textContent || "",
      chip: (open.children[1].children[0].children.find((c) => c.className === "row-next") || {}).textContent || "",
      state: open.children[open.children.length - 1].textContent,
      // A collection, and whether it is open; and whether this row is one of its
      // members. Empty on an ordinary row, which is most of them.
      group: open.getAttribute("data-group") || "",
      expanded: open.getAttribute("aria-expanded") || "",
      // Off the className, not the classList: the stub's list keeps its own set and a
      // class given at construction never reaches it.
      member: String(row.className || "").split(" ").indexOf("member") >= 0,
      cells: open.children.slice(2).map((cell) => cell.textContent.trim()),
      draws: row.children.length > 1 ? row.children[1].textContent : "",
      opens: open.tagName,
      href: open.href || "",
    };
  };
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
      kinds: byId["kind-chips"].children.map((c) => c.textContent),
      registers: byId["register-chips"].children.map((c) => c.textContent),
      /* What the page is browsed by since 2026-09-17: the subjects with rows behind
         them, each with its count, and the sentence above the list saying how far it has
         been narrowed to fit the reader. A subject chip's name and number are separate
         children, so the name alone is the first of them. */
      subjects: byId["subject-chips"].hidden
        ? []
        : byId["subject-chips"].children.map((c) => (c.children[0] || {}).textContent || c.textContent),
      subjectCounts: byId["subject-chips"].hidden
        ? []
        : byId["subject-chips"].children.map((c) =>
            Number((c.children.find((k) => k.className === "chip-n") || {}).textContent || 0)
          ),
      subjectOn: (byId["subject-chips"].children.find((c) => c.getAttribute("aria-pressed") === "true") || {
        children: [],
      }).children[0]
        ? byId["subject-chips"].children.find((c) => c.getAttribute("aria-pressed") === "true").children[0].textContent
        : "",
      said: byId["said"].textContent,
      /* Which band the list is narrowed to. Read off the selected option rather than off
         the line's text: a stub's textContent walks every child, so the sentence comes
         back with all three options run together. */
      fitOn: (() => {
        const pick = byId["said"].children
          .map((c) => (c.children || []).find((k) => k.tagName === "select"))
          .find(Boolean);
        const chosen = pick && (pick.children || []).find((o) => o.selected);
        return chosen ? chosen.textContent : "";
      })(),
      shape: browsing ? "cards" : "list",
      shapeOn:
        (byId["shape"].children.find((c) => c.getAttribute("aria-pressed") === "true") || {}).textContent || "",
      empty: byId["picked-empty"].textContent,
      // The one line that says what the list is.
      note: byId["picked-note"].textContent,
      /* The shelves (design.md §12, 2026-10-09): whether they are up, and each shelf drawn,
         in order, with its heading, its note and its cards. */
      pictures: asked,
      shelving: !byId["shelves"].hidden,
      /* The Tanakh's door at the head of the shelves (design.md §12, 2026-10-09). */
      tanakhDoor: (() => {
        const row = (byId["shelves"].children || []).find((c) => String(c.className) === "band-doors");
        const door = row && row.children[0];
        return door ? { href: door.href || "", says: door.children.map((c) => c.textContent) } : null;
      })(),
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
      shareHead: (() => {
        const head = byId["rows-head"].children.find((c) => c.className === "drop" && /^(?:Level|In order)/.test(c.textContent));
        return head ? { text: head.textContent.trim(), disabled: head.getAttribute("aria-disabled") === "true" } : null;
      })(),
      find: byId["find"].value || "",
      // The Beit Midrash: the tabs on offer, the doors drawn, the trail, and the address.
      tabs: byId["where"].children.map((c) => c.textContent),
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
      kindOn: (byId["kind-chips"].children.find((c) => c.getAttribute("aria-pressed") === "true") || {}).textContent || "",
      // The hard-words gauge is a column, so it exists on a row and not on a card.
      gauges: rows.map(
        (row) =>
          (row.children[0].children.find((c) => String(c.className).includes("gauge")) || {
            getAttribute: () => "",
          }).getAttribute("aria-label") || ""
      ),
    })
  );
  process.exit(0);
}, 20);
