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
  // Every way the page names a language, to its code (targum-internal#524).
  var codes = given.names || {};
  // The form that stands in where a language has none of the one asked for.
  var standIn = { "in": "in", adv: "in", nom: "nom" };

  /* A language's name in the form a sentence asks for, `{language:in}`: «на иврите»
     rather than the menu's «Иврит». The same rule as `strings.case_form` on the server;
     a capital, `{language:In}`, starts a sentence with it. */
  function cased(name, asked) {
    var low = asked.toLowerCase();
    var code = Object.prototype.hasOwnProperty.call(codes, name) ? codes[name] : null;
    var form = code ? said["language-" + low + "." + code] || said["language-" + standIn[low] + "." + code] : "";
    if (!form) form = (said["language-" + standIn[low] + ".any"] || "{language}").split("{language}").join(name);
    return asked.charAt(0) === low.charAt(0) ? form : form.charAt(0).toUpperCase() + form.slice(1);
  }

  function fillIn(text, fill) {
    if (!fill) return text;
    return text.replace(/\{(\w+)(?::(in|adv|nom|In|Adv|Nom))?\}/g, function (all, name, asked) {
      if (!Object.prototype.hasOwnProperty.call(fill, name)) return all;
      return asked ? cased(String(fill[name]), asked) : String(fill[name]);
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

  window.TargumStrings = { t: t, tn: tn, language: language, figure: figure, figureSaid: figureSaid };
})();
