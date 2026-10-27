/* The numbered scenes, as a sequence.
 *
 * A hundred short dialogues ship with ids of the shape `scene-NN-slug`, and the number is
 * the order somebody with no Hebrew is meant to read them in. Nothing else in the
 * catalogue carries that order: their measured difficulty is noise at this size (a
 * twenty-word scene with one uncommon word scores higher than a thirty-word one with
 * none), so any page that shows them as a path sorts on the number, never on the share.
 *
 * Parsed from the id rather than stored beside it: the id is the one key every page and
 * every test already has, and a third copy of the number would be a third thing to
 * drift.
 */
(function () {
  "use strict";

  // A scene in another language names it after `scene-`: `scene-ru-01-slug` (2026-10-13).
  // The code names a series, not only a language: Hebrew's B1 conversations are
  // `scene-he-01…` (2026-10-27) and number from 1 again, so a number is only an order
  // inside its series. The unprefixed `scene-NN` path is series "", and Hebrew's path.
  var SCENE = /^scene-(?:([a-z]{2,3})-)?(\d+)-/;

  function numberOf(id) {
    var found = SCENE.exec(String(id || ""));
    return found ? parseInt(found[2], 10) : 0;
  }

  function seriesOf(id) {
    var found = SCENE.exec(String(id || ""));
    return found ? found[1] || "" : "";
  }

  /* The series a language's path is: the unprefixed scenes for Hebrew, its own code for
     any other. Hebrew's B1 series is a shelf of its own, never the first-day path. */
  function pathOf(code) {
    var wanted = String(code || "he").split("-")[0].toLowerCase();
    return wanted === "he" ? "" : wanted;
  }

  /* Whether an id is a scene on a language's path. */
  function onPath(id, code) {
    return numberOf(id) > 0 && seriesOf(id) === pathOf(code);
  }

  /* Scenes by series (the A1 path first), then number, then id; everything else after,
     in the order it came. */
  function ordered(list) {
    return list.slice().sort(function (a, b) {
      var left = numberOf(a.id);
      var right = numberOf(b.id);
      if (left && right) {
        var leftSeries = seriesOf(a.id);
        var rightSeries = seriesOf(b.id);
        if (leftSeries !== rightSeries) return leftSeries < rightSeries ? -1 : 1;
        if (left !== right) return left - right;
        return String(a.id) < String(b.id) ? -1 : String(a.id) > String(b.id) ? 1 : 0;
      }
      if (left) return -1;
      if (right) return 1;
      return 0;
    });
  }

  /* The first scene not yet finished, among the shared readers the server handed the
     page — the row the library chips and the door Learn opens. `docs` is the reader's
     own `targum:docs`, keyed by content hash, where a finish is written (and synced).
     Nothing when no scene is seeded, or every one is finished. One language's scenes at
     a time, Hebrew's unless another is named: two languages' scene 1s are both first.
     Only the language's path series: Hebrew's B1 scene 1 is not where a new reader starts. */
  function next(shared, docs, code) {
    var wanted = code || "he";
    var scenes = ordered(
      (shared || []).filter(function (reader) {
        var language = String(reader.language || "he").split("-")[0].toLowerCase();
        return onPath(reader.entry, wanted) && language === wanted;
      }).map(function (reader) {
        return { id: reader.entry, reader: reader };
      })
    );
    for (var i = 0; i < scenes.length; i++) {
      var record = docs && docs[scenes[i].reader.document];
      if (!(record && record.done)) return scenes[i].reader;
    }
    return null;
  }

  function finished(reader, docs) {
    var record = reader && docs && docs[reader.document];
    return !!(record && record.done);
  }

  window.TargumScenes = {
    numberOf: numberOf,
    seriesOf: seriesOf,
    pathOf: pathOf,
    onPath: onPath,
    ordered: ordered,
    next: next,
    finished: finished,
  };
})();
