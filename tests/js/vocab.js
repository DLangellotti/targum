/* Runs the vocabulary editor against a stub document and reports what it built.
 *
 *   node tests/js/vocab.js payload.json
 *
 * One control, used by the word card, the phrase card, the list beside the text and the
 * words page, so a change here reaches four surfaces at once. What it is asked here is
 * the thing a reader complained about: whether there is a way to finish, and whether
 * pressing it keeps what was typed.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
install({ stored: payload.stored || {} });
require(path.join(path.resolve(__dirname, "../../src/targum/render/assets"), "vocab.js"));

/* The move out of the word and into the pair, when a test asks for it.
 *
 * `migrate` is what every page runs on load, so this runs the same thing: `runs` many
 * times, because the one property that matters as much as the result is that running it
 * twice is running it once. What comes back is the whole of localStorage, so a test can
 * say what moved, what stayed and what was taken away.
 */
if (payload.migrate) {
  for (let n = 0; n < (payload.runs || 1); n += 1) {
    window.TargumVocab.migrate(payload.language || "he", payload.document || "");
  }
  const after = {};
  for (let n = 0; n < localStorage.length; n += 1) {
    const name = localStorage.key(n);
    after[name] = JSON.parse(localStorage.getItem(name));
  }
  process.stdout.write(JSON.stringify({ stored: after }));
  process.exit(0);
}

const kept = [];
const levels = [];
const box = window.TargumVocab.editor({
  status: payload.status,
  note: payload.note || "",
  placeholder: payload.placeholder,
  // The list beside the text draws the scale without a field. A caller that wants no
  // note must not be given one, nor a button to press on it.
  onNote: payload.noNote ? undefined : (text) => kept.push(text),
  onStatus: (value) => levels.push(value),
});

const field = box.querySelector(".note-field");
const save = box.querySelector(".note-save");
const nothing = { stopPropagation() {} };

/** What a reader does: type, then say they are finished — by the button, by Enter, or
 *  by reaching straight for a level, which means the same thing. */
if (field && payload.type !== undefined) {
  field.value = payload.type;
  // The event a browser fires as the characters land. It is what tells the editor the
  // field has been written in, which is not the same question as whether the field and
  // the store currently differ — the note saves itself a moment after you stop typing.
  field.fire("input", nothing);
}
if (save && payload.press) save.fire("click", nothing);
if (field && payload.enter) field.fire("keydown", { key: "Enter", ...nothing });
if (payload.level !== undefined) {
  const button = box.querySelector(".level-" + payload.level);
  if (button) button.fire("click", nothing);
}

process.stdout.write(
  JSON.stringify({
    hasField: Boolean(field),
    placeholder: field ? field.placeholder : null,
    hasSave: Boolean(save),
    saveLabel: save ? save.textContent : null,
    kept,
    levels,
  })
);
