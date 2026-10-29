/* The Library's first asks, from the page's head (targum-internal#484, #557).
 *
 * The shelf's files, `/readers`, `/jobs` and `/portions` were asked by `library.js` at the
 * foot, so they waited for the whole page to arrive, and on the phone profile the shelf
 * then took a second of its own. Asked here, they arrive with the page. `library.js`
 * takes each answer from `TARGUM_SHELF_ASKED` once, and asks for whatever it does not
 * find there, so a wrong guess below costs only the bytes.
 *
 * The file it will open on is the one `library.js` would choose: the language the reader
 * last chose, else the account's (`TARGUM_ACCOUNT`, filled in per request for a signed-in
 * reader), else Hebrew; and that shelf's blurbs in the page's language, else in English.
 */
window.TARGUM_SHELF_ASKED = (function (files, account) {
  var asked = {};
  if (typeof fetch !== "function") return asked;
  var common = files ? files[""] : null;
  if (!common) return asked;
  function ask(address, later) {
    var how = { credentials: "same-origin" };
    // What the first card does not need goes out in the same wave, behind the rest where
    // the browser weighs requests at all.
    if (later) how.priority = "low";
    asked[address] = fetch(address, how);
    asked[address].catch(function () {});
  }
  var code = "";
  try {
    code = localStorage.getItem("targum:language") || "";
  } catch (e) {}
  code = code.split("-")[0];
  if (!code || !files[code]) {
    code = account && account.language && files[account.language] ? account.language : "he";
  }
  var page = (document.documentElement.lang || "en").split("-")[0];
  ask(common);
  if (files[code]) ask(files[code]);
  if (files[code + "." + page] || files[code + ".en"]) {
    ask(files[code + "." + page] || files[code + ".en"]);
  }
  // The catalogue's whole order and what a Build press sends were a second wave, asked
  // only once the first had been drawn, so on a phone they started at 2.6 s and the covers
  // waited behind them (targum-internal#557). Asked here they share the first wave.
  if (files.order) ask(files.order, true);
  if (files[code + ".build"]) ask(files[code + ".build"], true);
  // And what the shelf is drawn against, asked as `library.js` asks them.
  var key = window.TARGUM_KEY || "";
  ["/readers", "/jobs", "/portions"].forEach(function (path) {
    var headers = { "Content-Type": "application/json" };
    if (key) headers["X-Targum-Key"] = key;
    asked[path] = fetch(key ? path + "?k=" + encodeURIComponent(key) : path, { headers: headers });
    asked[path].catch(function () {});
  });
  return asked;
})(window.TARGUM_SHELF_FILES, window.TARGUM_ACCOUNT);
