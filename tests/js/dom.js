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
      return child;
    },
    setAttribute(name, value) {
      this.attrs[name] = value;
    },
    getAttribute(name) {
      return name in this.attrs ? this.attrs[name] : null;
    },
    addEventListener(type, handler) {
      (this.listeners[type] = this.listeners[type] || []).push(handler);
    },
    /** Not a dispatch: no bubbling, no default. It calls what was registered. */
    fire(type, event) {
      (this.listeners[type] || []).forEach((handler) => handler(event || {}));
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
    querySelector(selector) {
      const wanted = selector.replace(".", "");
      const find = (node) =>
        String(node.className).split(" ").includes(wanted)
          ? node
          : node.children.map(find).find(Boolean);
      return find(this) || null;
    },
    querySelectorAll() {
      return [];
    },
  };
}

/** Everything the script asked for by id, so a test can read what it drew. */
const byId = {};

function install(globals) {
  const listeners = {};
  global.document = {
    createElement: element,
    createTextNode: (text) => ({ textContent: text, children: [] }),
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
  global.Image = function () {
    return {
      set src(value) {
        this._src = value;
      },
    };
  };
  global.location = { reload: () => {}, href: "", search: "", hash: "", pathname: "/" };
  return byId;
}

module.exports = { install, byId, element };
