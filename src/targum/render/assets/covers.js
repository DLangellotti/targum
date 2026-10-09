/* The cover tile, drawn the same way everywhere it appears.
 *
 * Every page that shows a text shows one: the library's rows, Your targums, and home's
 * Continue (`picture`, below). Written once because a second copy is a tile that drifts —
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

  /* The colour a letter rests on, by what the text is: thumbs.py's `tone`, which draws
     the same tile on the server, so a letter drawn here and one drawn there agree
     (design.md §12, "Every text has a picture", 2026-10-08). Teal news, iris sets and
     the rabbinic shelf, clay things said, and the muted grey of books, which is what
     anything unnamed is. A subscription's kinds are here too: a series is a set, a
     channel or a podcast is said. */
  var TONES = {
    article: "news",
    news: "news",
    talk: "spoken",
    video: "spoken",
    podcast: "spoken",
    podcasts: "spoken",
    channel: "spoken",
    channels: "spoken",
    dialogue: "set",
    liturgy: "set",
    set: "set",
    series: "set",
  };

  function tone(kind, register) {
    var named = TONES[String(kind || "")];
    if (named) return named;
    return register === "rabbinic" ? "set" : "book";
  }

  function tile(source, options) {
    var settings = options || {};
    var box = document.createElement("span");
    box.className = settings.className || "thumb";
    box.classList.add("tone-" + tone(settings.kind, settings.register));

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
    // Known now to stay a letter, so a layout can size it as one without waiting to see
    // whether a picture arrives (targum-internal#375).
    if (!source || settings.drawn === false) box.classList.add("is-letter");
    if (source && settings.drawn !== false) {
      var image = new Image();
      image.onload = function () {
        box.textContent = "";
        image.alt = "";
        box.appendChild(image);
      };
      // A picture that never came is a letter after all.
      image.onerror = function () {
        box.classList.add("is-letter");
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

  /* A text's picture, wherever home draws one (design.md §12, "Every text has a
     picture", 2026-10-08): `/thumb/<name>?drawn=1` answers with the text's own picture,
     an upload's from the asker's own home, a video's frame, or — where there is none —
     the server's letter on the colour of its kind. So this draws no letter of its own
     for a text with a name; a build, which has no folder yet, rests on its letter.
     `keyed` adds the start-up key to the address on a machine somebody runs itself. */
  function picture(reader, options) {
    var settings = options || {};
    var address =
      settings.keyed ||
      function (path) {
        return path;
      };
    var named = reader.entry || reader.id || reader.name || "";
    var source = named ? address("/thumb/" + encodeURIComponent(named) + "?drawn=1") : "";
    return tile(source, {
      title: reader.title,
      language: reader.language,
      kind: reader.kind,
      register: reader.register,
      drawn: !!source,
      className: settings.className || "thumb home-thumb",
    });
  }

  window.TargumCovers = { tile: tile, tone: tone, chapterName: chapterName, picture: picture };
})();
