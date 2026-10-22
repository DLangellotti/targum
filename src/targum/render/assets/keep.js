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

/* Who is signed in, asked once for the whole page (targum-internal#484).
 *
 * Every desk page has four or five scripts that want `/account/me` — the inbox, the
 * language keys, the account's corner, the page's own script — and each asked for itself,
 * so a cold load sent the same question three to five times, some of them waiting on each
 * other, at 150 ms a round trip on a phone. Here, the first to ask sends it and the rest are
 * handed a copy of the same answer. A copy because a response can be read only once.
 *
 * `fresh` asks again and keeps the new answer: what `sync.js` does after the reader has
 * changed something the answer carries, their languages. A request that fails is
 * forgotten, so the next to ask tries again rather than inheriting the failure.
 */
window.targumMe =
  window.targumMe ||
  (function () {
    var asked = null;
    return function (address, options, fresh) {
      if (!asked || fresh) {
        var going = fetch(address, options);
        asked = going;
        going.catch(function () {
          if (asked === going) asked = null;
        });
      }
      return asked.then(function (response) {
        return response.clone();
      });
    };
  })();
