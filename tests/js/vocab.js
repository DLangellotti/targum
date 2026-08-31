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

/* The copy control, when a test asks for one.
 *
 * Node has no clipboard, so the test says what kind of browser this is: one whose
 * clipboard takes the text, one whose clipboard refuses it, or one with no clipboard at
 * all — and, separately, whether the old command works. What comes back is what the
 * control said and did, at once and again after the beat it says "Copied" for.
 */
if (payload.copy !== undefined) {
  const written = [];
  if (payload.clipboard === "ok" || payload.clipboard === "refuses") {
    global.navigator = {
      clipboard: {
        writeText: (text) => {
          written.push(text);
          return payload.clipboard === "ok" ? Promise.resolve() : Promise.reject(new Error("no"));
        },
      },
    };
  }
  if (payload.command) document.execCommand = () => true;
  const said = () =>
    document.body.children.find((child) => child.attrs.role === "status") || { textContent: "" };
  const button = window.TargumVocab.copyButton(payload.copy, { label: payload.label });
  let stopped = 0;
  const before = { label: button.attrs["aria-label"], title: button.title, text: button.textContent };
  button.fire("click", { stopPropagation: () => (stopped += 1) });
  // Two turns of the queue: the clipboard's promise, then the one that says so.
  setTimeout(() => {
    const after = {
      text: button.textContent,
      copied: button.classList.contains("copied"),
      announced: said().textContent,
    };
    setTimeout(() => {
      process.stdout.write(
        JSON.stringify({
          before,
          after,
          reverted: { text: button.textContent, copied: button.classList.contains("copied") },
          written,
          stopped,
        })
      );
      process.exit(0);
    }, window.TargumVocab.COPIED_FOR + 100);
  }, 20);
}

const kept = [];
const levels = [];
let saved = 0;
const box = window.TargumVocab.editor({
  onSaved: () => (saved += 1),
  status: payload.status,
  note: payload.note || "",
  placeholder: payload.placeholder,
  legend: Boolean(payload.legend),
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
/** Typing again after saving: the button has to offer to save again. */
if (field && payload.again !== undefined) {
  field.value = payload.again;
  field.fire("input", nothing);
}
if (field && payload.enter) field.fire("keydown", { key: "Enter", ...nothing });
if (payload.level !== undefined) {
  const button = box.querySelector(".level-" + payload.level);
  if (button) button.fire("click", nothing);
}

if (payload.copy === undefined)
  process.stdout.write(
    JSON.stringify({
    hasField: Boolean(field),
    placeholder: field ? field.placeholder : null,
    hasSave: Boolean(save),
    saveLabel: save ? save.textContent : null,
    saveDisabled: save ? Boolean(save.disabled) : null,
    saved,
    legend: (box.querySelector(".level-legend") || {}).textContent || null,
    kept,
    levels,
  })
);
