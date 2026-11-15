/* Runs Send to Anki (`anki-send.js`; targum-internal#540) against a fake AnkiConnect and
 * a fake targum origin, with no page and no Anki.
 *
 *   node tests/js/anki_send.js payload.json
 *
 * The payload says what the account holds (`words`, as `/account/anki/notes` answers),
 * what Anki already holds and how it answers, and how many presses to make. What comes
 * back is every call the page made to 127.0.0.1, the line said after each press, and the
 * notes Anki holds at the end.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const dom = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");
const ANKI = "http://127.0.0.1:8765";

const byId = dom.install({
  stored: payload.stored || {},
  matchMedia: (query) => ({
    matches: query === "(pointer: fine)" ? payload.fine !== false : false,
    addEventListener: () => {},
  }),
});
global.window.TARGUM_KEY = "";
global.window.TargumLists = {
  ankiContext: () => ({ code: "he", name: "Hebrew", deck: "targum Hebrew" }),
};
// Node 21 and later define `navigator` as a getter, so it is defined over, not assigned.
Object.defineProperty(global, "navigator", {
  configurable: true,
  writable: true,
  value: {
    onLine: payload.online !== false,
    permissions: {
      query: () => Promise.resolve({ state: payload.lna || "granted" }),
    },
  },
});
global.window.navigator = global.navigator;
["send-anki", "send-anki-help", "send-anki-how", "send-anki-key", "export-said"].forEach((id) => {
  global.document.getElementById(id).hidden = true;
});

/* --- Anki, as AnkiConnect answers --------------------------------------------- */
const anki = payload.anki || {};
const decks = (anki.decks || ["Default"]).slice();
const models = (anki.models || ["Basic"]).slice();
const notes = {};
let nextId = 1000;
(anki.notes || []).forEach((note) => {
  const id = nextId++;
  notes[id] = { model: note.model, deck: note.deck || "targum Hebrew", fields: note.fields, tags: note.tags || [] };
});
const calls = [];
const media = {};
let anki_calls = 0;
let dropped = false;

function info(id) {
  const note = notes[id];
  const fields = {};
  Object.keys(note.fields).forEach((name, order) => {
    fields[name] = { value: note.fields[name], order };
  });
  return { noteId: Number(id), modelName: note.model, tags: note.tags, fields };
}

function act(action, params, key) {
  if (anki.busy === action) return { result: null, error: "Anki is busy" };
  if (action !== "requestPermission" && anki.key && key !== anki.key) {
    return { result: null, error: "valid api key must be provided" };
  }
  switch (action) {
    case "requestPermission":
      return {
        result: {
          permission: anki.permission || "granted",
          requireApikey: !!anki.key,
          version: anki.version || 6,
        },
        error: null,
      };
    case "version":
      return { result: anki.version || 6, error: null };
    case "deckNames":
      return { result: decks, error: null };
    case "createDeck":
      decks.push(params.deck);
      return { result: 1, error: null };
    case "modelNames":
      return { result: models, error: null };
    case "createModel":
      models.push(params.modelName);
      return { result: {}, error: null };
    case "findNotes": {
      const model = /"note:([^"]+)"/.exec(params.query)[1];
      return {
        result: Object.keys(notes)
          .filter((id) => notes[id].model === model)
          .map(Number),
        error: null,
      };
    }
    case "notesInfo":
      return { result: params.notes.map(info), error: null };
    case "storeMediaFile":
      media[params.filename] = params.data;
      return { result: params.filename, error: null };
    case "addNotes":
      return {
        result: params.notes.map((note) => {
          if (anki.refuse && note.fields.targum === anki.refuse) return null;
          const id = nextId++;
          notes[id] = { model: note.modelName, deck: note.deckName, fields: Object.assign({ "Your notes": "" }, note.fields), tags: note.tags };
          return id;
        }),
        error: null,
      };
    case "updateNoteFields":
      // Inside `multi` a refusal is an answer of its own, not the call's error.
      if (anki.refuseUpdate && notes[params.note.id].fields.targum === anki.refuseUpdate) {
        return { result: null, error: "cannot update" };
      }
      Object.assign(notes[params.note.id].fields, params.note.fields);
      return { result: null, error: null };
    case "updateNoteTags":
      notes[params.note].tags = params.tags;
      return { result: null, error: null };
    case "multi":
      return { result: params.actions.map((one) => act(one.action, one.params, key)), error: null };
    default:
      return { result: null, error: "unsupported action" };
  }
}

/* --- targum's origin ---------------------------------------------------------- */
const PAGE = payload.page || 200;
const targum = [];

global.fetch = function (url, options) {
  url = String(url);
  if (url.indexOf(ANKI) === 0) {
    anki_calls += 1;
    if (anki.unreachable || (anki.dropAfter && anki_calls > anki.dropAfter && !dropped)) {
      if (anki.dropAfter) dropped = "now";
      return Promise.reject(new TypeError("Failed to fetch"));
    }
    const body = JSON.parse(options.body);
    calls.push({
      action: body.action,
      params: body.params,
      key: body.key || "",
      contentType: !!(options.headers && (options.headers["Content-Type"] || options.headers["content-type"])),
    });
    if (body.action === "multi") {
      body.params.actions.forEach((one) => calls.push({ action: one.action, params: one.params, inner: true }));
    }
    const answer = act(body.action, body.params, body.key);
    return Promise.resolve({ ok: true, json: () => Promise.resolve(answer) });
  }
  targum.push(url);
  if (url.indexOf("/account/anki/notes") === 0) {
    const page = Number(/page=(\d+)/.exec(url)[1]);
    const words = payload.words.slice(page * PAGE, (page + 1) * PAGE);
    const more = (page + 1) * PAGE < payload.words.length;
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ signedIn: true, words, next: more ? page + 1 : null }),
    });
  }
  if (url.indexOf("/account/anki/") === 0) {
    const bytes = new Uint8Array([73, 68, 51, 1, 2, 3]);
    return Promise.resolve({ ok: true, arrayBuffer: () => Promise.resolve(bytes.buffer) });
  }
  return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
};

require(path.join(assets, "anki-send.js"));
const send = global.window.TargumAnkiSend;

function settle() {
  return new Promise((resolve) => {
    const wait = () => (send.isRunning() ? setImmediate(wait) : setTimeout(resolve, 0));
    setImmediate(wait);
  });
}

(async () => {
  send.offer(payload.signedIn !== false);
  const offered = {
    button: byId["send-anki"].hidden === false,
    help: byId["send-anki-help"].hidden === false,
  };
  const said = [];
  const callsAt = [];
  for (let n = 0; n < (payload.presses == null ? 1 : payload.presses); n++) {
    if (dropped === "now") dropped = true;
    if (payload.editBetween && n > 0) {
      payload.editBetween.forEach((edit) => Object.assign(payload.words[edit.at], edit.set));
    }
    if (payload.keyBetween && n > 0) {
      byId["send-anki-key-field"].value = payload.keyBetween;
      byId["send-anki-key"].onsubmit({ preventDefault() {} });
    } else {
      byId["send-anki"].onclick();
    }
    await settle();
    said.push(byId["export-said"].textContent);
    callsAt.push(calls.length);
  }
  if (payload.help) byId["send-anki-help"].onclick();
  const held = Object.keys(notes).map((id) => Object.assign({ id: Number(id) }, notes[id]));
  process.stdout.write(
    JSON.stringify({
      offered,
      said,
      calls,
      callsAt,
      notes: held,
      media: Object.keys(media),
      decks,
      models,
      keyForm: byId["send-anki-key"].hidden === false,
      help: {
        open: byId["send-anki-how"].hidden === false,
        expanded: byId["send-anki-help"].getAttribute("aria-expanded"),
        scope: byId["send-anki-scope"] ? byId["send-anki-scope"].textContent : "",
      },
      targum,
    })
  );
})().catch((error) => {
  process.stderr.write(String((error && error.stack) || error));
  process.exit(1);
});
