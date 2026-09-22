/* Just enough DOM for a page's script to run under node.
 *
 * The reader and the library are the two places bugs have actually shipped, and neither
 * has ever had a test that ran the code — a parse check and source-level greps stood in
 * for it. A real browser (Playwright) is the eventual answer and a dependency decision;
 * this is the eighty per cent of it that costs nothing: enough of a document that a
 * script can build its rows, and enough of an assertion surface to read them back.
 *
 * Deliberately not a DOM implementation. Nothing here lays anything out, computes a
 * style, or fires an event. What it supports is what the page scripts actually use.
 */

"use strict";

/** Whether a node wears every class in a selector: `.src.plain` is a cell that is both,
 *  the way the reader asks for the form on show. One class is the common case. */
function wearing(selector) {
  const wanted = String(selector).split(".").filter(Boolean);
  return (node) => {
    const worn = String(node.className || "").split(" ");
    return wanted.every((name) => worn.includes(name));
  };
}

function element(tag) {
  return {
    tagName: tag,
    children: [],
    attrs: {},
    // Properties are read back by name, and custom ones (--size) go in the same bag.
    style: {
      setProperty(name, value) {
        this[name] = value;
      },
      removeProperty(name) {
        delete this[name];
      },
    },
    className: "",
    classList: {
      _names: new Set(),
      add(name) {
        this._names.add(name);
      },
      remove(name) {
        this._names.delete(name);
      },
      toggle(name, on) {
        if (on === undefined) on = !this._names.has(name);
        return on ? this._names.add(name) : this._names.delete(name);
      },
      contains(name) {
        return this._names.has(name);
      },
    },
    disabled: false,
    hidden: false,
    // A form control's own state, which the vocabulary editor reads back out of the
    // field it made. Nothing here lays anything out, but a value is not layout.
    value: "",
    placeholder: "",
    // And a tick box's, which the profile page draws and reads back.
    checked: false,
    type: "",
    _text: "",

    get textContent() {
      return this._text || this.children.map((child) => child.textContent).join("");
    },
    set textContent(value) {
      this._text = value;
      this.children = [];
    },

    appendChild(child) {
      this.children.push(child);
      // The reader asks a cell for the pair it is in, to find the segment it draws.
      child.parentNode = this;
      return child;
    },
    removeChild(child) {
      this.children = this.children.filter((c) => c !== child);
      return child;
    },
    setAttribute(name, value) {
      this.attrs[name] = value;
    },
    getAttribute(name) {
      return name in this.attrs ? this.attrs[name] : null;
    },
    /* The other half of `setAttribute`, missing until 2026-09-18. An absent attribute is
       how the DOM says "not this one" — `aria-current` on the rail is the case that found
       it — so a stub that can only ever add one cannot express the ordinary state. */
    removeAttribute(name) {
      delete this.attrs[name];
    },
    addEventListener(type, handler) {
      (this.listeners[type] = this.listeners[type] || []).push(handler);
    },
    /** Not a dispatch: no bubbling, no default. It calls what was registered. */
    fire(type, event) {
      (this.listeners[type] || []).forEach((handler) => handler(event || {}));
      // A browser calls the `onclick` property as well as the registered listeners, and
      // pages here use both: the arrival's Done is assigned, its chips are registered.
      // Without this half a press on an assigned handler did nothing and the test that
      // pressed it passed anyway, which is how the arrival's Done went untested.
      const assigned = this["on" + type];
      if (typeof assigned === "function") assigned.call(this, event || {});
    },
    /** A real method on a real element, and the one way a page saves a file: an anchor
     *  is made, clicked and thrown away. Without it `link.click()` threw and no test
     *  could ever have reached an export. */
    click() {
      this.fire("click");
    },
    focus() {},
    /** Leaving a field is what commits what you typed into it, so this has to be the
     *  event and not just a method that returns. */
    blur() {
      this.fire("blur");
    },
    listeners: {},
    closest() {
      return null;
    },
    /** Where a test says this element is. Nothing here lays anything out. */
    getBoundingClientRect() {
      return Object.assign({ top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 }, this.rect);
    },
    /* One box unless `hidden`: with no stylesheet there is nothing else to hide an
       element, so the stub is always the desk. A phone is a browser test's job. */
    getClientRects() {
      return this.hidden ? [] : [this.getBoundingClientRect()];
    },
    /* Classes, and one attribute form: `[data-row="..."]`, which is how the library
       page finds the row a reader was sent to. Without it the selector fell through to
       the class match, never hit, and the stub quietly answered null. */
    /* Whether a node is this one or inside it. Scripts poll with it to find out
       whether the block they drew is still on the page before touching it again. */
    contains(node) {
      if (node === this) return true;
      return (this.children || []).some((child) => child.contains && child.contains(node));
    },
    querySelector(selector) {
      const attr = /^\[([\w-]+)="?([^"\]]*)"?\]$/.exec(selector);
      const hit = attr ? (node) => node.attrs[attr[1]] === attr[2] : wearing(selector);
      const find = (node) => (hit(node) ? node : node.children.map(find).find(Boolean));
      return find(this) || null;
    },
    /* Every descendant carrying the class, in document order — the record's foot counts
       the words drawn above it this way. Class selectors only, like querySelector. */
    querySelectorAll(selector) {
      const hit = wearing(selector);
      const out = [];
      const walk = (node) => {
        (node.children || []).forEach((child) => {
          if (hit(child)) out.push(child);
          walk(child);
        });
      };
      walk(this);
      return out;
    },
  };
}

/** Everything the script asked for by id, so a test can read what it drew. */
const byId = {};

function install(globals) {
  const listeners = {};
  global.document = {
    createElement: element,
    /* The library's cards draw their audio and video marks as SVG, and a stub with no
       namespace-aware constructor threw before a single card was built. The namespace
       itself is not under test — nothing here asserts about a glyph — so it is dropped
       and the tag behaves like any other element. */
    createElementNS: (namespace, tag) => element(tag),
    createTextNode: (text) => ({ textContent: text, children: [] }),
    /* A fragment, which several scripts build a block in before saying it once. Made of
       the same stuff as an element: nothing here lays anything out, so a fragment that
       stays a node when it is appended rather than dissolving into its parent is a tree
       one level deeper and the same nodes in the same order. Every harness that reads a
       block walks the children anyway. */
    createDocumentFragment: () => element("fragment"),
    getElementById(id) {
      byId[id] = byId[id] || element("div");
      return byId[id];
    },
    querySelector: () => null,
    /* A stub document has no tree to search: every element here was made by the script
       under test or asked for by id. A harness that wants a page's own markup — the fold
       buttons, which come from the template — hands the answers in as `selectors`. */
    querySelectorAll: (selector) => (globals.selectors || {})[selector] || [],
    addEventListener(type, handler) {
      (listeners[type] = listeners[type] || []).push(handler);
    },
    /** What a browser would do on a click or a keypress, minus everything else. */
    fire(type, event) {
      (listeners[type] || []).forEach((handler) => handler(event || {}));
    },
    documentElement: element("html"),
    body: element("body"),
  };
  global.window = Object.assign(
    {
      innerWidth: 1200,
      innerHeight: 800,
      scrollX: 0,
      scrollY: 0,
      addEventListener: () => {},
      matchMedia: () => ({ matches: false, addEventListener: () => {}, addListener: () => {} }),
      // Never called back: nothing in a test waits a frame, and a callback that ran
      // would redraw a page that has no cells to redraw.
      requestAnimationFrame: () => 0,
    },
    globals
  );
  global.requestAnimationFrame = global.window.requestAnimationFrame;
  // A real bag rather than a read-only stub: the profile page's whole job is writing
  // preferences into it, and a setItem that dropped them would pass every assertion.
  const stored = globals.stored || (globals.stored = {});
  global.localStorage = {
    get length() {
      return Object.keys(stored).length;
    },
    getItem: (name) => (name in stored ? stored[name] : null),
    setItem: (name, value) => {
      stored[name] = String(value);
    },
    removeItem: (name) => {
      delete stored[name];
    },
    key: (index) => Object.keys(stored)[index] ?? null,
  };
  /* Where a write goes. On a page these are defined by `keep.js`, which is in the
     <head> of all eighteen templates, and replaced by `durable.js` in a reader — the one
     artefact opened from disk, where `localStorage` does not reliably keep what it is
     given (targum-internal#137). A harness that loads one asset on its own has neither,
     so it stands in for the page and provides them. */
  /* The same object under both names, as a browser has it. Without this a script
     reaching for `window.localStorage` wrote to `undefined` — which throws, which the
     `try` every one of them is wrapped in then swallowed, so the write vanished and the
     test that made it passed. Found on the fold's handoff, 2026-09-18. */
  global.window.localStorage = global.localStorage;
  global.targumKeep = (name, value) => global.localStorage.setItem(name, value);
  global.targumForget = (name) => global.localStorage.removeItem(name);
  global.window.targumKeep = global.targumKeep;
  global.window.targumForget = global.targumForget;
  global.Image = function () {
    return {
      set src(value) {
        this._src = value;
      },
    };
  };
  global.location = { reload: () => {}, href: "", search: "", hash: "", pathname: "/" };
  /* The same object under both names. A page reaches for `window.location` as often as
     the bare one — sending somebody to a built reader is `window.location.href = …` —
     and a stub that only had the bare one threw there rather than recording it. */
  global.window.location = global.location;
  return byId;
}

module.exports = { install, byId, element };
