/* The cover tile, drawn the same way everywhere it appears.
 *
 * Two pages show one: the library, where every text is a row, and Learn, where a book
 * opens into its chapters. Written once because a second copy is a tile that drifts —
 * one page would keep a fix and the other would not, and nobody would notice for months.
 *
 * A tile is a letter until it is a picture. The text's own first letter is drawn
 * immediately and the image replaces it only once it has loaded, so a library with no
 * covers drawn yet looks deliberate rather than broken, and a slow image never shows as
 * an empty frame. Covers arrive one at a time and over months — see
 * `scripts/thumbnails.py` — so the resting state is the ordinary state, not the error.
 */

(function () {
  "use strict";

  // Anything that is not a letter in some script: quotation marks, brackets, the
  // parentheses Wikisource puts round a disambiguation. The first *letter* is wanted,
  // not the first character.
  var NOT_A_LETTER = /^[^\wא-תЀ-ӿ]+/;

  function tile(source, options) {
    var settings = options || {};
    var box = document.createElement("span");
    box.className = settings.className || "thumb";

    var letter = String(settings.title || "?")
      .replace(NOT_A_LETTER, "")
      .charAt(0);
    var glyph = document.createElement("span");
    glyph.className = "glyph";
    glyph.textContent = letter;
    glyph.setAttribute("lang", settings.language || "und");
    // Decorative: the title is already beside it in text, and a screen reader that
    // announced the first letter of it twice would be reading the page wrong.
    glyph.setAttribute("aria-hidden", "true");
    box.appendChild(glyph);

    // `drawn: false` is the server saying outright that no picture exists. Asking
    // anyway bought nothing but a 404 in the console on every page that showed the
    // tile; the letter is the resting state, not the error.
    if (source && settings.drawn !== false) {
      var image = new Image();
      image.onload = function () {
        box.textContent = "";
        image.alt = "";
        box.appendChild(image);
      };
      image.src = source;
    }
    return box;
  }

  // Where a chapter's cover lives, which is beside its book's. A chapter without one of
  // its own falls back to the book's on the server, so this asks for the same thing
  // whether or not anybody has drawn it — see `_serve_thumb`.
  function chapterName(book, number) {
    var padded = String(number);
    while (padded.length < 3) padded = "0" + padded;
    return book + "-c" + padded;
  }

  window.TargumCovers = { tile: tile, chapterName: chapterName };
})();
