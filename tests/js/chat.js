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
install({
  TARGUM_KEY: payload.key === undefined ? "k" : payload.key,
  TargumBuilding: { ask: () => strip.asked++ },
  // The reader's own ledger, as the reader writes it, when the payload gives one.
  stored: payload.ledger ? { "targum:vocab:he": JSON.stringify(payload.ledger) } : {},
});

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
  return Promise.resolve({ json: () => Promise.resolve(answers[at] || {}) });
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
global.FileReader = class {
  readAsDataURL(file) {
    this.result = "data:text/plain;base64," + Buffer.from(file._content).toString("base64");
    setImmediate(() => this.onload());
  }
};

require(path.join(assets, "bring.js"));
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

function drawn() {
  return (turns.children || []).map((li) => {
    const line = lineOf(li);
    return {
      cls: li.className,
      text: line ? line.textContent : "",
      links: line ? line.children.filter((c) => c.tagName === "a").map((a) => a.href) : [],
      hebrew: line ? line.children.filter((c) => c.attrs && c.attrs.lang === "he").length : 0,
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
      for (let i = 0; i < 16; i++) await new Promise((resolve) => setImmediate(resolve));
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
    if (step.type === "press") {
      // The newest control with that class, anywhere in the thread.
      const found = [];
      const walk = (node) => {
        if (String(node.className).split(" ").includes(step.selector)) found.push(node);
        (node.children || []).forEach(walk);
      };
      walk(turns);
      found[found.length - 1].onclick();
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
      held: (byId["chat-held"].children || []).map((chip) => chip.children[0].textContent),
      pairs: pairsDrawn(),
      foot: foot(),
      doors: doors(),
      hours: byId["chat-hours"] ? byId["chat-hours"].textContent : "",
      stripAsked: strip.asked,
      mic: {
        hidden: byId["chat-mic"].hidden,
        pressed: byId["chat-mic"].attrs["aria-pressed"],
        text: byId["chat-mic"].textContent,
      },
      plays,
      list: (byId["chat-list"].children || []).map((li) => li.children[0].textContent),
      said: { text: byId["chat-said"].textContent, hidden: byId["chat-said"].hidden },
      sendDisabled: byId["chat-send"].disabled,
    }),
  );
})();
