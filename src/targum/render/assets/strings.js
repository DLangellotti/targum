/* The words a desk page says, in the reader's language (targum-internal#184).
 *
 * The page hands over `window.TARGUM_STRINGS` — `{strings, language}`, only the keys its
 * scripts use, and nothing at all for English — and a script says `t(key, English, fill)`
 * or `tn(key, count, one, other, fill)`. A key the language has not filled is said in
 * the English written at the call, never as its name, and `tn` chooses the form by the
 * language's own plural rules. The same pair as `reader.js`'s, which carries its own
 * because a reader is one file; `tests/test_strings.py` holds every call to `en.json`.
 */
(function () {
  "use strict";

  var given = window.TARGUM_STRINGS || {};
  var said = given.strings || {};
  var language = given.language || "en";

  function fillIn(text, fill) {
    if (!fill) return text;
    return text.replace(/\{(\w+)\}/g, function (all, name) {
      return Object.prototype.hasOwnProperty.call(fill, name) ? String(fill[name]) : all;
    });
  }

  function t(key, english, fill) {
    var text = said[key];
    return fillIn(typeof text === "string" ? text : english, fill);
  }

  function tn(key, count, one, other, fill) {
    var form = "other";
    try {
      form = new Intl.PluralRules(language).select(count);
    } catch (e) {
      form = count === 1 ? "one" : "other";
    }
    var text = said[key + "." + form];
    if (typeof text !== "string") text = said[key + ".other"];
    var values = { n: count };
    for (var name in fill || {}) values[name] = fill[name];
    return fillIn(typeof text === "string" ? text : count === 1 ? one : other, values);
  }

  window.TargumStrings = { t: t, tn: tn, language: language };
})();
