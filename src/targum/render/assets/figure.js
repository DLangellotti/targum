/* A text's one figure (targum-internal#716 P1-1), added to the page's `TargumStrings`:
 * `figure(row)` and `figureSaid(found, marked)`. Its own file, after `strings.js`, which
 * every desk page carries inline and keeps to a few lines; the pages that print a text's
 * figure from a script (Your targums and a playlist) load this too.
 */
(function () {
  "use strict";

  var strings = window.TargumStrings;
  if (!strings) return;
  var t = strings.t;

  /* A text's one figure (design.md §12, "A text's figure is our estimate until your marks
     settle it", 2026-11-04): what every row, card and column on a desk page prints for
     how much of a text the reader knows, read off what the server sent with it — `known`,
     the marked share, and `estimated` where our estimate is the figure (`coverage.state`).
     `{share, percent, estimated}`, or null where nothing was measured, so "0% known" and
     "not measured" stay different claims. `percent` is the whole percentage
     `level.known_percent` prints: rounded, never 100 under all of it nor 0 above none
     (2026-10-29, an exact percentage). Continue, the shelf's meter and a playlist's Known
     column all read it here, so one text says one number (targum-internal#716, P1-1). */
  function figure(row) {
    // A row that says how many words it counted and counted none was not measured.
    if (!row || ("words" in row && !row.words)) return null;
    var estimated = typeof row.estimated === "number";
    var share = estimated ? row.estimated : row.known;
    if (typeof share !== "number" || share < 0) return null;
    var percent = Math.max(0, Math.min(100, Math.round(share * 100)));
    if (share < 1 && percent >= 100) percent = 99;
    if (share > 0 && percent <= 0) percent = 1;
    return { share: Math.max(0, Math.min(1, share)), percent: percent, estimated: estimated };
  }

  /* The figure said short, as a column or a meter's label says it: ours always says it
     is one, "About 93% (our estimate)"; the marked share is said in the caller's own
     words, `marked`, a function of the percentage ("72% known", or "72%" where a
     column's head says Known). */
  function figureSaid(found, marked) {
    if (!found) return "";
    if (found.estimated) {
      return t("known.estimate.about", "About {n}%", { n: found.percent }) + " " + t("known.estimate.ours", "(our estimate)");
    }
    return marked ? marked(found.percent) : found.percent + "%";
  }

  strings.figure = figure;
  strings.figureSaid = figureSaid;
})();
