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
});
// The segmented mode control is the template's markup, so it is built here: two
// buttons the script reads and presses through the group's one click listener.
const { element } = require("./dom.js");
const modeGroup = byId["chat-mode"] || (byId["chat-mode"] = element("div"));
const segments = ["find", "talk"].map((m) => {
  const b = element("button");
  b.className = "segment";
  b.attrs["data-mode"] = m;
  b.attrs["aria-pressed"] = m === "find" ? "true" : "false";
  b.closest = (sel) => (sel === ".segment" ? b : null);
  modeGroup.children.push(b);
  return b;
});
modeGroup.querySelectorAll = (sel) => (sel === ".segment" ? segments : []);

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
          : JSON.parse(options.body || "{}"),
    });
  }
  return Promise.resolve({ json: () => Promise.resolve(answers[at] || {}) });
};

require(path.join(assets, "chat.js"));

const turns = byId["turns"];

function lineOf(li) {
  return li.children.find((child) => child.className === "chat-line");
}

function cards() {
  const out = [];
  const walk = (node) => {
    if (String(node.className).split(" ")[0] === "quote") {
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
      out.push({
        he: node.children[0].textContent,
        en: node.children[1].textContent,
        recast: String(node.className).split(" ").includes("recast"),
      });
    }
    (node.children || []).forEach(walk);
  };
  walk(turns);
  return out;
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
  for (const step of payload.do || []) {
    if (step.type === "say") {
      byId["say"].value = step.text;
      byId["composer"].fire("submit", { preventDefault() {} });
    }
    if (step.type === "stream") {
      sources[sources.length - 1].fire(step.event, step.data || "");
    }
    if (step.type === "mode") {
      const button = segments.find((b) => b.attrs["data-mode"] === step.mode);
      modeGroup.fire("click", { target: button });
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
      pairs: pairsDrawn(),
      doors: doors(),
      hours: byId["chat-hours"] ? byId["chat-hours"].textContent : "",
      mode: segments.find((b) => b.attrs["aria-pressed"] === "true").attrs["data-mode"],
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
