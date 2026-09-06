/* Runs the front door's box against a stub document and reports what it did.
 *
 *   node tests/js/box.js payload.json
 *
 * The box on Learn opens a conversation and goes to it; what a test needs to know is
 * what was posted, where the page was sent, and whether Speak was offered.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");

if (payload.record) {
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

install({ TARGUM_KEY: payload.key === undefined ? "k" : payload.key });

const posted = [];
const answers = payload.answers || {};
global.fetch = (url, options) => {
  const at = String(url).split("?")[0];
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

// The template gives the `+` its address; the stub document has no template.
byId["chat-bring"] = byId["chat-bring"] || require("./dom.js").element("a");
byId["chat-bring"].getAttribute = () => "/add";

require(path.join(assets, "speak.js"));
require(path.join(assets, "box.js"));

(async () => {
  // Let `/chat/list` answer before anything is pressed.
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  for (const step of payload.do || []) {
    if (step.type === "say") {
      byId["say"].value = step.text;
      byId["composer"].fire("submit", { preventDefault() {} });
    }
    if (step.type === "record") {
      byId["chat-mic"].onclick();
      await new Promise((resolve) => setImmediate(resolve));
      byId["chat-mic"].onclick();
    }
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
  }
  console.log(
    JSON.stringify({
      posted,
      went: global.location.href,
      bring: byId["chat-bring"].href,
      mic: { hidden: byId["chat-mic"].hidden },
      said: { text: byId["chat-said"].textContent, hidden: byId["chat-said"].hidden },
      sendDisabled: byId["chat-send"].disabled,
    }),
  );
})();
