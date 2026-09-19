/* Where a write goes, for every page targum serves.
 *
 * `durable.js` defines these first and better, but it is only inlined into a reader —
 * the one artefact that gets opened from disk, where `localStorage` does not reliably
 * keep what it is given (targum-internal#137). Every other page is served over HTTP,
 * where a write keeps and the plain call is the whole of it.
 *
 * This file is in the <head> of every template that keeps anything, so defining the
 * fallback here covers every page, and `||` means the reader's durable version is never displaced.
 *
 * It was `theme.js` until 2026-09-19, and chose between light and dark as well. There is
 * one look now (design.md §12), and this is what was left.
 */
window.targumKeep =
  window.targumKeep ||
  function (name, value) {
    try {
      localStorage.setItem(name, value);
    } catch (error) {}
  };
window.targumForget =
  window.targumForget ||
  function (name) {
    try {
      localStorage.removeItem(name);
    } catch (error) {}
  };
