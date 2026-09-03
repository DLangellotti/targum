/* Runs the reader's own script against a stub document and reports what it decided.
 *
 *   node tests/js/reader.js payload.json
 *
 * Three things, each of which either shipped a bug or decides one: where a card lands
 * beside a word, whether a hover survives the keypress that marked the word under it,
 * and which word the arrows go to next. Everything else in `reader.js` rebuilds spans
 * through innerHTML and a TreeWalker, which a stub cannot honestly pretend to be — that
 * half belongs to a real browser, and the note in `tests/test_reader_js.py` says so.
 *
 * The queue belongs here rather than there because it never asks the page anything: it
 * is decided in the data the page was built with, which is exactly what a stub can hold.
 *
 * The script is loaded, not copied. What is exercised is `window.TargumReader`, which
 * the reader hangs off the window the same way every other script here does.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { install, byId, element } = require("./dom.js");

const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf-8"));
const assets = path.resolve(__dirname, "../../src/targum/render/assets");
const language = payload.language || "he";

install({
  innerWidth: payload.window.width,
  innerHeight: payload.window.height,
  // What you have already said about words in this language, as the browser would have
  // it — the reader reads its vocabulary out of localStorage and nowhere else.
  stored: Object.assign(
    { ["targum:vocab:" + language]: JSON.stringify(payload.vocab || {}) },
    // A doc record that predates this page — the sync writes some with no language.
    payload.docs ? { "targum:docs": JSON.stringify(payload.docs) } : {},
  ),
});

// Both before the script runs: it reads the language off the page and parses the
// embedded chapter once, at the top.
document.documentElement.setAttribute("lang", language);
document.getElementById("targum-data").textContent = JSON.stringify({
  words: payload.chapter || {},
  lemmas: payload.lemmas || [],
  registers: payload.registers || [],
  sourceRegister: payload.sourceRegister || "",
  document: "a-chapter",
});

// The first-time line as the template ships it: hidden, with its sentence in it. The
// script decides whether to show it and what it says after the first word is marked.
byId.first = Object.assign(element("p"), {
  textContent: "Tap a word to say how well you know it.",
  hidden: true,
});

// The page loads this first and the reader leans on it: the level names it announces
// and the steps the card draws are both `TargumVocab.STEPS`.
require(path.join(assets, "vocab.js"));
require(path.join(assets, "reader.js"));
const reader = window.TargumReader;

/** A queue entry as a test would say it: the word itself, not its index. */
function entry(item) {
  if (!item) return null;
  return {
    segment: item.segment,
    lemma: (payload.lemmas || [])[item.lemma],
    start: item.start,
  };
}

/** Where the card ended up, in the same numbers the page would use. */
function place(word, card) {
  const element = document.createElement("div");
  element.rect = { width: card.width, height: card.height };
  reader.placeNear(element, word);
  const at = (value) => parseFloat(String(value || "0").replace("px", ""));
  const height = element.style.maxHeight ? at(element.style.maxHeight) : card.height;
  const top = at(element.style.top);
  return {
    top,
    left: at(element.style.left),
    height,
    bottom: top + height,
    capped: Boolean(element.style.maxHeight),
  };
}

const hover = { started: reader.hovering() };
reader.stopHover();
hover.afterKey = { hovering: reader.hovering(), marked: document.body.classList.contains("no-hover") };
document.fire("mousemove");
hover.afterMove = { hovering: reader.hovering(), marked: document.body.classList.contains("no-hover") };

/* Levels said and taken back, in order, each one against the queue it left behind.
 *
 * A level is one keystroke and there are five of them, so the wrong one is a matter of
 * time — and `k` takes the word out of the queue the arrows walk, which is the only way
 * back to it. What `u` has to restore is the queue itself, which is data, so it is
 * decided here rather than in a browser. */
const said = [];
(payload.levels || []).forEach((ask) => {
  if (ask.undo) reader.undo();
  else reader.level((payload.lemmas || []).indexOf(ask.word), ask.status);
  said.push({
    queue: reader.queue().map(entry),
    // What a reader listening rather than looking is told a key just did.
    spoken: byId.spoken ? byId.spoken.textContent : "",
  });
});

/* Finished with the text: said, said again, and what the record holds. */
(payload.finish || []).forEach((on) => reader.finish(on));

/* The offer at the foot: everything never marked, known at once, and one undo. */
if (payload.markRest) reader.markRest();
if (payload.undoAfter) reader.undo();

process.stdout.write(
  JSON.stringify({
    placed: (payload.words || []).map((word) => ({ word, card: place(word, payload.card) })),
    hover,
    queue: reader.queue().map(entry),
    // Each asked of a freshly built queue, the way a keypress asks it.
    steps: (payload.steps || []).map((ask) => entry(reader.step(ask.from, ask.forward))),
    said,
    finished: {
      at: reader.finishedAt(),
      record: (JSON.parse(localStorage.getItem("targum:docs") || "{}")["a-chapter"] || {}).done || 0,
      language:
        (JSON.parse(localStorage.getItem("targum:docs") || "{}")["a-chapter"] || {}).language || "",
      button: byId["done-mark"].textContent,
      said: byId["done-said"].hidden ? "" : byId["done-said"].textContent,
    },
    // The card's grammar line, as the annotator's pipe strings come out in words.
    grammar: (payload.grammarLines || []).map((line) => reader.useLine(line)),
    persons: (payload.personLines || []).map((line) => reader.personWord(line)),
    // The register line, from where the reader is standing: [code, sourceRegister].
    registers: (payload.registerLines || []).map((pair) =>
      reader.registerLine(pair[0], pair[1]),
    ),
    // The arithmetic of a page, asked of the pure half: a stub lays nothing out.
    pages: payload.pages
      ? reader.boundariesFrom(
          payload.pages.tops,
          payload.pages.heights,
          payload.pages.room,
          payload.pages.opens,
          payload.pages.glue,
        )
      : null,
    pageFor: payload.pageFor
      ? reader.pageFor(payload.pageFor.index, payload.pageFor.pages)
      : null,
    // The first-time line under the bar, after everything above.
    first: { hidden: Boolean(byId.first.hidden), text: byId.first.textContent },
    rest: {
      hidden: Boolean(byId.rest.hidden),
      text: byId["rest-text"].textContent,
      button: byId["rest-mark"].textContent,
      undo: !byId["rest-undo"].hidden,
    },
    // The list beside the text after every level above was said, top to bottom.
    list: reader.entries().map((item) => ({
      lemma: item.lemma,
      status: item.status,
      done: Boolean(item.done),
    })),
  })
);
