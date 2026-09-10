/* Runs the chat page's script against a stub document and reports what it did.
 *
 *   node tests/js/chat.js payload.json
 *
 * The payload carries what each path should answer and a list of things to do to the
 * page — say a line, feed the stream an event. What comes back is what was drawn and
 * what was posted.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

const posted = [];
const opened = [];
const sources = [];

class EventSource {
  constructor(url) {
    this.url = url;
    this.readyState = 1;
    this.handlers = {};
    sources.push(this);
  }
  addEventListener(type, handler) {
    (this.handlers[type] = this.handlers[type] || []).push(handler);
  }
  close() {
    this.readyState = 2;
  }
  fire(type, data) {
    (this.handlers[type] || []).forEach((h) => h({ data }));
  }
}
global.EventSource = EventSource;

const strip = { asked: 0 };
const plays = [];
// A browser that can record, when the payload says so: getUserMedia hands back a stream
// with one track, and MediaRecorder fires ondataavailable once and onstop on stop().
if (payload.record) {
  // Newer Node has a `navigator` of its own, as a getter-only global; defining the
  // property replaces it where assignment throws.
  Object.defineProperty(globalThis, "navigator", {
    value: {
      mediaDevices: {
        getUserMedia: () => Promise.resolve({ getTracks: () => [{ stop() {} }] }),
      },
    },
    configurable: true,
    writable: true,
  });
  global.MediaRecorder = class {
    constructor() {
      this.mimeType = "audio/webm";
    }
    start() {}
    stop() {
      this.ondataavailable({ data: { size: 3 } });
      this.onstop();
    }
  };
  global.Blob = class {
    constructor(parts, options) {
      this.type = (options && options.type) || "";
    }
  };
}
// What the page listens to on the window — `hashchange`, since #238 — so a step can fire it.
const windowListeners = {};
install({
  TARGUM_KEY: payload.key === undefined ? "k" : payload.key,
  addEventListener: (type, handler) => {
    (windowListeners[type] = windowListeners[type] || []).push(handler);
  },
  TargumBuilding: { ask: () => strip.asked++ },
  // The reader's own ledger, as the reader writes it, when the payload gives one.
  stored: Object.assign(
    payload.ledger ? { "targum:vocab:he": JSON.stringify(payload.ledger) } : {},
    payload.stored || {},
  ),
});
/* A glyph is made through createElementNS, which the stub document has no need of
   otherwise: the Hear button draws its loudspeaker this way (2026-09-10). */
const { element } = require("./dom.js");
global.document.createElementNS = (namespace, tag) => element(tag);

// An <audio> element that records what it was asked to play rather than playing it.
const madeElement = global.document.createElement;
global.document.createElement = (tag) => {
  const node = madeElement(tag);
  if (tag === "audio") {
    node.play = () => {
      plays.push(node.src);
      return Promise.resolve();
    };
  }
  return node;
};

const answers = payload.answers || {};
global.fetch = (url, options) => {
  const at = String(url).split("?")[0];
  opened.push(String(url));
  if (options && options.method === "POST") {
    posted.push({
      path: at,
      body:
        options.body && options.body.type
          ? "<blob " + options.body.type + ">"
          : typeof options.body === "string" || !options.body
            ? JSON.parse(options.body || "{}")
            : "<chunk>",
    });
  }
  // An answer keyed by the whole path with its query, the key left out, comes first —
  // "/chat/list?limit=50&offset=50" is a different page from "/chat/list" (#238).
  const full = String(url).replace(/[?&]k=[^&]*/, "");
  return Promise.resolve({ json: () => Promise.resolve(answers[full] || answers[at] || {}) });
};

// Arrived from the front door with a conversation in the hash, when the payload says so.
if (payload.hash) global.location.hash = global.window.location.hash = payload.hash;


// A file the reader chose, and the two things a script does with one: read it whole
// (`FileReader`, answering base64 of what the payload gave), or cut it into pieces.
function fakeFile(spec) {
  return {
    name: spec.name,
    size: spec.size || 12,
    slice: () => ({ piece: true }),
    _content: spec.content || "text",
  };
}
// A picture sent is drawn from the browser's own copy of the file.
global.URL = { createObjectURL: (file) => "blob:" + file.name };
global.FileReader = class {
  readAsDataURL(file) {
    this.result = "data:text/plain;base64," + Buffer.from(file._content).toString("base64");
    setImmediate(() => this.onload());
  }
};

// The sync, as every page's script finds it. Recorded rather than stubbed away: the
// chat page did not start it for a while, and nothing said so (targum-internal#232).
let syncStarted = false;
global.window.TargumSync = {
  start: () => {
    syncStarted = true;
    return Promise.resolve(true);
  },
  onChange: () => {},
};

require(path.join(assets, "bring.js"));
require(path.join(assets, "chips.js"));
// A build is followed with no wait between looks, so a test sees its end at once.
global.window.TargumBring.POLL = 0;
require(path.join(assets, "speak.js"));
require(path.join(assets, "chat.js"));

const turns = byId["turns"];

function lineOf(li) {
  return li.children.find((child) => child.className === "chat-line");
}

function cards() {
  const out = [];
  const walk = (node) => {
    if (String(node.className).split(" ")[0] === "quote-card") {
      const by = (cls) => node.children.find((c) => String(c.className).split(" ").includes(cls));
      const title = by("quote-title");
      out.push({
        // The stub keeps classList apart from className; a card is named by both.
        cls: [node.className, ...node.classList._names].join(" "),
        title: title ? title.children[0].textContent : "",
        english: title && title.children[1] ? title.children[1].textContent : "",
        meta: by("quote-meta") ? by("quote-meta").textContent : "",
        note: by("quote-note") ? by("quote-note").textContent : "",
        button: by("quote-go") ? by("quote-go").textContent : "",
        more: by("quote-more") ? by("quote-more").href : "",
              excerpt: by("quote-excerpt")
          ? by("quote-excerpt")
              .children.filter((c) => String(c.tagName).toUpperCase() === "BDI")
              .map((c) => c.textContent)
          : [],
        doubt: by("quote-doubt") ? by("quote-doubt").textContent : "",
});
    }
    (node.children || []).forEach(walk);
  };
  walk(turns);
  return out;
}

function pairsDrawn() {
  const out = [];
  const walk = (node) => {
    if (String(node.className).split(" ")[0] === "chat-pair") {
      const he = node.children[0];
      const gloss = node.children.find((c) => String(c.className).split(" ")[0] === "chat-gloss");
      out.push({
        he: he.textContent,
        en: node.children[1].textContent,
        // Folded or open (#241).
        enHidden: node.children[1].hidden,
        recast: String(node.className).split(" ").includes("recast"),
        // The words the line was drawn with, each with its state on the ledger.
        words: he.children
          .filter((c) => String(c.className).split(" ")[0] === "chat-w")
          .map((c) => ({ text: c.textContent, lemma: c.attrs["data-lemma"], state: String(c.className).replace("chat-w", "").trim() })),
        gloss: gloss ? gloss.textContent : null,
      });
    }
    (node.children || []).forEach(walk);
  };
  walk(turns);
  return out;
}

function foot() {
  const li = (turns.children || []).find((c) => String(c.className).split(" ")[0] === "chat-sum");
  if (!li) return null;
  const by = (cls) => li.children.find((c) => String(c.className).split(" ").includes(cls));
  return {
    counts: by("chat-counts") ? by("chat-counts").textContent : "",
    save: !!by("chat-save"),
    note: by("note") ? by("note").textContent : "",
  };
}

function doors() {
  const out = [];
  const walk = (node) => {
    if (String(node.className).split(" ")[0] === "chat-door") {
      out.push({ href: node.href, text: node.textContent });
    }
    (node.children || []).forEach(walk);
  };
  walk(turns);
  return out;
}

function pictured(node) {
  const out = [];
  const walk = (n) => {
    if (n.tagName === "img") out.push(n.src);
    (n.children || []).forEach(walk);
  };
  walk(node);
  return out;
}

function drawn() {
  return (turns.children || []).map((li) => {
    const line = lineOf(li);
    return {
      cls: li.className,
      text: line ? line.textContent : "",
      links: line ? line.children.filter((c) => c.tagName === "a").map((a) => a.href) : [],
      hebrew: line ? line.children.filter((c) => c.attrs && c.attrs.lang === "he").length : 0,
      pictures: pictured(li),
    };
  });
}

(async () => {
  // Let `/chat/list` answer before anything is pressed or read back.
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  for (const step of payload.do || []) {
    if (step.type === "say") {
      byId["say"].value = step.text;
      byId["composer"].fire("submit", { preventDefault() {} });
    }
    if (step.type === "stream") {
      sources[sources.length - 1].fire(step.event, step.data || "");
    }
    if (step.type === "file") {
      // One file, or several chosen together (`files`): the pages of one text.
      byId["chat-file"].files = (step.files || [step.file]).map(fakeFile);
      byId["chat-file"].onchange();
      // An upload is several round trips; let them all settle.
      for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
    }
    if (step.type === "send") {
      byId["say"].value = step.text || "";
      byId["composer"].fire("submit", { preventDefault() {} });
      for (let i = 0; i < 24; i++) await new Promise((resolve) => setImmediate(resolve));
    }
    if (step.type === "drop") {
      byId["chat-held"].children[step.index].children[1].onclick();
    }
    if (step.type === "record") {
      // Two presses: start, then stop — which is when the clip goes up.
      byId["chat-mic"].onclick();
      await new Promise((resolve) => setImmediate(resolve));
      byId["chat-mic"].onclick();
    }
    if (step.type === "hash") {
      // The address changed by the back button or a typed link: the page opens what
      // it names (#238).
      global.location.hash = global.window.location.hash = step.hash || "";
      (windowListeners.hashchange || []).forEach((h) => h({}));
      for (let i = 0; i < 6; i++) await new Promise((resolve) => setImmediate(resolve));
    }
    if (step.type === "chip") {
      // A press on the chip with that id (#240).
      const chip = (byId["chat-chips"].children || [])
        .map((li) => li.children[0])
        .find((b) => b.attrs["data-chip"] === step.id);
      chip.onclick();
      for (let i = 0; i < 8; i++) await new Promise((resolve) => setImmediate(resolve));
    }
    if (step.type === "pair") {
      // A tap on the n-th pair, off its Hebrew line (#241).
      const found = [];
      const walk = (node) => {
        if (String(node.className).split(" ")[0] === "chat-pair") found.push(node);
        (node.children || []).forEach(walk);
      };
      walk(turns);
      const pair = found[step.n || 0];
      if (pair.onclick) pair.onclick({ target: pair.children[0] });
    }
    if (step.type === "english") {
      byId["chat-english"].onclick();
    }
    if (step.type === "pill") {
      byId["chat-open-list"].onclick();
    }
    if (step.type === "press") {
      // The newest control with that class, anywhere in the thread.
      const found = [];
      const walk = (node) => {
        if (String(node.className).split(" ").includes(step.selector)) found.push(node);
        (node.children || []).forEach(walk);
      };
      walk(turns);
      walk(byId["chat-list"]);
      found[found.length - 1].onclick();
      for (let i = 0; i < 6; i++) await new Promise((resolve) => setImmediate(resolve));
    }
    // Let the promises settle between steps.
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
  }
  console.log(
    JSON.stringify({
      posted,
      streams: sources.map((s) => s.url),
      turns: drawn(),
      cards: cards(),
      went: global.location.href,
      held: (byId["chat-held"].children || []).map((chip) => chip.children[0].textContent),
      field: byId["say"].value,
      placeholder: byId["say"].placeholder,
      pairs: pairsDrawn(),
      foot: foot(),
      doors: doors(),
      hours: byId["chat-hours"] ? byId["chat-hours"].textContent : "",
      hoursHidden: byId["chat-hours"] ? byId["chat-hours"].hidden : true,
      stripAsked: strip.asked,
      mic: {
        hidden: byId["chat-mic"].hidden,
        pressed: byId["chat-mic"].attrs["aria-pressed"],
        // The word is the label since 2026-09-10; the face is a glyph.
        label: byId["chat-mic"].attrs["aria-label"],
        text: byId["chat-mic"].textContent,
      },
      plays,
      // Each row's title; its "when" beside it; the address the page wrote (#238).
      list: (byId["chat-list"].children || []).map((li) =>
        li.children[0].children.length ? li.children[0].children[0].textContent : li.children[0].textContent,
      ),
      whens: (byId["chat-list"].children || []).map((li) =>
        li.children[0].children.length > 1 ? li.children[0].children[1].textContent : "",
      ),
      hash: global.location.hash,
      english: {
        hidden: byId["chat-english"].hidden,
        pressed: byId["chat-english"].attrs["aria-pressed"],
        text: byId["chat-english"].textContent,
        kept: global.localStorage.getItem("targum:chat-english"),
      },
      chips: {
        hidden: byId["chat-chips"].hidden,
        ids: (byId["chat-chips"].children || []).map((li) => li.children[0].attrs["data-chip"]),
        lines: (byId["chat-chips"].children || []).map((li) => li.children[0].textContent),
      },
      asked: opened.map((u) => u.replace(/[?&]k=[^&]*/, "")),
      listOpen: byId["chat-list"].classList.contains("open"),
      pillExpanded: byId["chat-open-list"].attrs["aria-expanded"],
      said: { text: byId["chat-said"].textContent, hidden: byId["chat-said"].hidden },
      sendDisabled: byId["chat-send"].disabled,
      syncStarted,
    }),
  );
})();
