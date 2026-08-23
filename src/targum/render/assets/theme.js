/* Light or dark, chosen once and kept for every page targum serves.
 *
 * Loaded from the <head> so the choice is stamped on <html> before anything is painted;
 * left to the end of the body it would show one theme and then swap to the other.
 *
 * Three states, not two: until you choose, there is no stamp and the pages follow the
 * system setting. The button chooses, and from then on your choice wins in both
 * directions — a light stamp beats an OS set to dark, and the other way round.
 */
(function () {
  "use strict";

  var KEY = "targum:theme";
  var root = document.documentElement;

  function stored() {
    try {
      var value = localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (e) {
      return null;
    }
  }

  function stamp(value) {
    if (value) root.setAttribute("data-theme", value);
    else root.removeAttribute("data-theme");
  }

  function systemDark() {
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  // What the reader is actually looking at, whether they chose it or the system did.
  function showing() {
    return stored() || (systemDark() ? "dark" : "light");
  }

  // Before first paint.
  stamp(stored());

  var SUN =
    '<circle cx="8" cy="8" r="3.2"/><path d="M8 1v1.8M8 13.2V15M1 8h1.8M13.2 8H15' +
    'M3.05 3.05l1.27 1.27M11.68 11.68l1.27 1.27M12.95 3.05l-1.27 1.27M4.32 11.68l-1.27 1.27"/>';
  var MOON = '<path d="M13.2 9.6A5.8 5.8 0 0 1 6.4 2.8a5.8 5.8 0 1 0 6.8 6.8z"/>';

  var buttons = [];

  function paint() {
    var dark = showing() === "dark";
    // The icon is the thing you would get, and the label says so, because an icon of
    // the state you are already in reads as a switch nobody needs to press.
    var label = dark ? "Switch to light" : "Switch to dark";
    buttons.forEach(function (button) {
      button.innerHTML =
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">' +
        (dark ? SUN : MOON) +
        "</svg>";
      button.title = label;
      button.setAttribute("aria-label", label);
      button.setAttribute("aria-pressed", dark ? "true" : "false");
    });
  }

  function choose(value) {
    try {
      localStorage.setItem(KEY, value);
    } catch (e) {}
    stamp(value);
    paint();
  }

  function wire() {
    buttons = Array.prototype.slice.call(document.querySelectorAll("[data-theme-toggle]"));
    buttons.forEach(function (button) {
      button.addEventListener("click", function (event) {
        event.stopPropagation();
        choose(showing() === "dark" ? "light" : "dark");
      });
    });
    paint();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }

  // Another targum page open in another tab is the same choice, so it moves too.
  window.addEventListener("storage", function (event) {
    if (event.key !== KEY) return;
    stamp(stored());
    paint();
  });

  // While nothing has been chosen, the system is still in charge and the button has to
  // keep saying the right thing when it changes.
  if (window.matchMedia) {
    var watch = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () {
      if (!stored()) paint();
    };
    if (watch.addEventListener) watch.addEventListener("change", onChange);
    else if (watch.addListener) watch.addListener(onChange);
  }
})();
