/* One of Learn's lists, whole.
 *
 * Learn caps every list it shows and points here for the rest. Which list this is comes
 * from `window.TARGUM_LIST`; the drawing is the same `TargumShelf` and `TargumLists` that
 * Learn uses, so a row cannot look one way there and another way here.
 *
 * The language switcher is the same one too, and it decides what a list holds: words are
 * kept per language, and a shelf of Hebrew is not a shelf of Russian.
 */

(function () {
  "use strict";

  var key = window.TARGUM_KEY;

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  var which = window.TARGUM_LIST || "words";
  var charts = window.TargumCharts;
  var lists = window.TargumLists;
  var shelf = window.TargumShelf;
  var lang = window.TargumLang;
  var names = window.TARGUM_LANGUAGES || {};

  Array.prototype.forEach.call(
    document.querySelectorAll(".site-nav a, .upload, [data-back]"),
    function (link) {
      link.href = keyed(link.getAttribute("href"));
    }
  );

  function ask(path) {
    return fetch(keyed(path), { headers: keyHeaders({ "Content-Type": "application/json" }) }).then(
      function (response) {
        return response.json();
      }
    );
  }

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  /* --- the shelf ------------------------------------------------------------- */

  function drawTexts() {
    var opened = stored("targum:opened");
    return ask("/readers").then(function (data) {
      var readers = (data && data.readers) || [];
      var trash = (data && data.trash) || [];
      readers.forEach(function (reader) {
        reader.opened = opened[reader.document] || 0;
      });
      readers.sort(function (a, b) {
        return b.opened - a.opened || b.built * 1000 - a.built * 1000;
      });

      var codes = [lang.HOME];
      readers.forEach(function (reader) {
        var code = shelf.base(reader.language);
        if (code && codes.indexOf(code) < 0) codes.push(code);
      });
      codes = lang.order(codes, names);

      if (!readers.length) {
        document.getElementById("nothing").hidden = false;
        return;
      }
      document.getElementById("page").hidden = false;

      function show(code) {
        lang.set(code);
        lang.switcher(document.getElementById("langs"), codes, names, code, show);
        // No ceiling: this page is the whole of it, which is what it is for.
        shelf.draw(code, readers, { note: "Last read first." });
        shelf.trash(code, trash);
      }

      show(lang.current(codes));
    });
  }

  /* --- the words and the phrases ---------------------------------------------- */

  function drawKept() {
    if (window.TargumVocab) window.TargumVocab.migrate();
    var data = charts.collect();
    var codes = lang.order(Object.keys(data), names);
    if (!codes.length) {
      document.getElementById("nothing").hidden = false;
      return Promise.resolve();
    }
    document.getElementById("page").hidden = false;

    lists.mount({ languages: names });
    // Picking another language for the meanings redraws the same rows with the other
    // answer in them. The words themselves do not move: they are the same words.
    lists.onMeaningLanguage(function () {
      lists.draw(shown, charts.collect(charts.meaningLanguage(shown))[shown]);
    });

    var shown = "";

    function show(code) {
      shown = code;
      lang.set(code);
      lang.switcher(document.getElementById("langs"), codes, names, code, show);
      // Re-collected rather than sliced out of `data`: which language the meanings are
      // in is a question about the language being shown, and the answer changes with it.
      lists.draw(code, charts.collect(charts.meaningLanguage(code))[code]);
    }

    show(lang.current(codes));
    return Promise.resolve();
  }

  var drawing = which === "texts" ? drawTexts() : drawKept();

  drawing.catch(function () {
    // Signed out, or the server went away. The nav is still there to leave by.
    document.getElementById("nothing").hidden = false;
  });

  if (window.TargumSync) {
    window.TargumSync.onChange(function (changed) {
      if (changed) location.reload();
    });
    window.TargumSync.start().then(function () {
      if (lists) lists.offerExports(!!window.TargumSync.who);
    });
  }
})();
