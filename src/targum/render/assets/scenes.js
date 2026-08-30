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

  var SCENE = /^scene-(\d+)-/;

  function numberOf(id) {
    var found = SCENE.exec(String(id || ""));
    return found ? parseInt(found[1], 10) : 0;
  }

  /* Scenes by number, then everything else in the order it came. */
  function ordered(list) {
    return list.slice().sort(function (a, b) {
      var left = numberOf(a.id);
      var right = numberOf(b.id);
      if (left && right) return left - right;
      if (left) return -1;
      if (right) return 1;
      return 0;
    });
  }

  window.TargumScenes = { numberOf: numberOf, ordered: ordered };
})();
