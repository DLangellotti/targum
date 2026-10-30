/* Home's first asks, from the page's head (targum-internal#555).
 *
 * Home is drawn from the account, the shelf (`/readers`), the builds (`/jobs`), the
 * account's places and its subscriptions' new items. They were asked by `home.js` and
 * `yours.js` at the foot, so they waited for the whole page to arrive, and `/readers`
 * waited on the account as well: a round trip each on a phone. Asked here, they arrive
 * with the page, side by side, as the Library's do (`library-early.js`, #484).
 *
 * Each answer is taken once from `TARGUM_HOME_ASKED`, by address, and a script that finds
 * nothing there asks for itself, so a guess that goes unused costs only its bytes.
 * `/account/me` goes through `keep.js`'s one shared ask, which every script on the page
 * reads.
 *
 * The shelf is asked lean (targum-internal#556): the reader's own texts, of the shared
 * shelf only what this browser has had open, and no catalogue, which only the Library
 * draws. `TargumShelfAddress` works that address out, here and for `yours.js`'s later
 * asks, and `TARGUM_HOME_SHELF` is the one this head asked for, so the page takes its
 * answer by the same address and asks the shelf once.
 */
(function () {
  /* Each opened text is named by the start of its hash; the server adds what the account
     knows was opened on other devices. A browser that has opened more than an address
     should carry asks for the whole shared shelf, as before. The whole of it was ~430 kB
     of the answer, measured on the server, for the few rows home keeps (`gather`). */
  var OPENED_PREFIX = 12;
  var OPENED_NAMED_AT_MOST = 300;
  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}") || {};
    } catch (e) {
      return {};
    }
  }
  window.TargumShelfAddress = function () {
    var named = {};
    [stored("targum:opened"), stored("targum:places")].forEach(function (record) {
      Object.keys(record).forEach(function (hash) {
        if (/^[0-9a-f]{12,}$/i.test(hash)) named[hash.slice(0, OPENED_PREFIX).toLowerCase()] = true;
      });
    });
    var starts = Object.keys(named);
    if (starts.length > OPENED_NAMED_AT_MOST) return "/readers?catalogue=0";
    // "-" names none, and still has the account's added: an empty value is no value.
    return "/readers?catalogue=0&shared=" + (starts.join(".") || "-");
  };
})();

window.TARGUM_HOME_ASKED = (function () {
  var asked = {};
  if (typeof fetch !== "function") return asked;
  var key = window.TARGUM_KEY || "";
  function options() {
    var headers = { "Content-Type": "application/json" };
    if (key) headers["X-Targum-Key"] = key;
    return { credentials: "same-origin", headers: headers };
  }
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  if (window.targumMe) {
    window.targumMe(keyed("/account/me"), options()).catch(function () {});
  }
  window.TARGUM_HOME_SHELF = window.TargumShelfAddress();
  [window.TARGUM_HOME_SHELF, "/jobs", "/account/places?limit=20", "/subscriptions/new.json"].forEach(function (path) {
    asked[path] = fetch(keyed(path), options());
    asked[path].catch(function () {});
  });
  return asked;
})();
