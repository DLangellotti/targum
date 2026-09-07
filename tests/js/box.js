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
          : typeof options.body === "string" || !options.body
            ? JSON.parse(options.body || "{}")
            : "<chunk>",
    });
  }
  return Promise.resolve({ json: () => Promise.resolve(answers[at] || {}) });
};



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
    if (step.type === "file") {
      // One file, or several chosen together (`files`): the pages of one text.
      byId["chat-file"].files = (step.files || [step.file]).map(fakeFile);
      byId["chat-file"].onchange();
      // An upload is several round trips; let them all settle.
      for (let i = 0; i < 12; i++) await new Promise((resolve) => setImmediate(resolve));
    }
    if (step.type === "record") {
      byId["chat-mic"].onclick();
      await new Promise((resolve) => setImmediate(resolve));
      byId["chat-mic"].onclick();
    }
    if (step.type === "drop") {
      // The × on the n-th chip: let that file go.
      byId["chat-held"].children[step.index].children[1].onclick();
    }
    if (step.type === "send") {
      byId["say"].value = step.text || "";
      byId["composer"].fire("submit", { preventDefault() {} });
      for (let i = 0; i < 16; i++) await new Promise((resolve) => setImmediate(resolve));
    }
    await new Promise((resolve) => setImmediate(resolve));
    await new Promise((resolve) => setImmediate(resolve));
  }
  console.log(
    JSON.stringify({
      posted,
      went: global.location.href,
      // What the + chose and the box still holds: one chip a file.
      held: (byId["chat-held"].children || []).map((chip) => chip.children[0].textContent),
      heldHidden: byId["chat-held"].hidden,
      mic: { hidden: byId["chat-mic"].hidden },
      said: { text: byId["chat-said"].textContent, hidden: byId["chat-said"].hidden },
      sendDisabled: byId["chat-send"].disabled,
    }),
  );
})();
