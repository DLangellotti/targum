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

install({ TARGUM_KEY: payload.key === undefined ? "k" : payload.key });

const answers = payload.answers || {};
global.fetch = (url, options) => {
  const at = String(url).split("?")[0];
  opened.push(String(url));
  if (options && options.method === "POST") {
    posted.push({ path: at, body: JSON.parse(options.body || "{}") });
  }
  return Promise.resolve({ json: () => Promise.resolve(answers[at] || {}) });
};

require(path.join(assets, "chat.js"));

const turns = byId["turns"];

function lineOf(li) {
  return li.children.find((child) => child.className === "line");
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
    // Let the promises settle between steps.
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
  }
  console.log(
    JSON.stringify({
      posted,
      streams: sources.map((s) => s.url),
      turns: drawn(),
      list: (byId["chat-list"].children || []).map((li) => li.children[0].textContent),
      said: { text: byId["chat-said"].textContent, hidden: byId["chat-said"].hidden },
      sendDisabled: byId["chat-send"].disabled,
    }),
  );
})();
