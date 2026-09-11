/* Your subscriptions (2026-09-11).
 *
 * A series is a thing that comes out on its own clock — the weekly, the weekly portion,
 * a learning cycle — and following one is a fact about this browser (`targum:follows`).
 * `GET /series` says where each one is this week; the Library draws the row to follow
 * from, and Learn puts the newest instalment of a followed series in the sheet the first
 * time it is seen (`targum:series-seen`) and tells the bell. Nothing here is bought, and
 * nothing a series says is fetched from anywhere but this origin.
 */
(function () {
  "use strict";

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  var FOLLOWS = "targum:follows";
  var SEEN = "targum:series-seen";

  function read(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }
  function write(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {
      /* nothing to keep it in; the page still stands */
    }
  }

  function follows() {
    return read(FOLLOWS);
  }
  function following(id) {
    return !!follows()[id];
  }
  function follow(id, on) {
    var kept = follows();
    if (on) kept[id] = 1;
    else delete kept[id];
    write(FOLLOWS, kept);
  }
  function seen() {
    return read(SEEN);
  }
  function markSeen(id, instalment) {
    var kept = seen();
    kept[id] = instalment;
    write(SEEN, kept);
  }

  function list() {
    if (typeof fetch !== "function") return Promise.resolve([]);
    return fetch(keyed("/series"), { headers: keyHeaders({}) })
      .then(function (response) {
        return response.json();
      })
      .then(function (answer) {
        return (answer && answer.series) || [];
      })
      .catch(function () {
        return [];
      });
  }

  // The reader of a series' current instalment. The weekly is written three ways, and
  // the one for this reader is chosen the way Learn's line chose it: their marked words
  // against the issue's own levels, the lowest rung for a reader with none.
  function readerOf(series) {
    var inst = series && series.instalment;
    if (!inst) return "";
    if (inst.reader) return inst.reader;
    if (!inst.levels || !inst.levels.length) return "";
    var level = inst.levels[0];
    try {
      var charts = window.TargumCharts;
      if (charts && charts.levelFor) {
        var store = charts.collect(charts.meaningLanguage("he"))["he"];
        var picked = charts.levelFor((store && store.words) || [], inst.levels);
        if (picked) level = picked;
      }
    } catch (e) {
      level = inst.levels[0];
    }
    return level.reader || "/reader/" + encodeURIComponent(level.folder) + "/reader/index.html";
  }

  // The followed series whose current instalment this browser has not seen, newest
  // first: what lands in the sheet and the bell.
  function fresh(series) {
    var kept = follows();
    var saw = seen();
    return series
      .filter(function (one) {
        return kept[one.id] && one.instalment && saw[one.id] !== one.instalment.id;
      })
      .sort(function (a, b) {
        return String(b.instalment.when || "").localeCompare(String(a.instalment.when || ""));
      });
  }

  function whenSaid(iso) {
    if (!iso) return "";
    var at = new Date(iso);
    if (isNaN(at.getTime())) return String(iso);
    return at.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /* The row on the Library: each series with what it is, where it is this week, one
     press to follow it and one to open its page. */
  function draw(host, series) {
    host.textContent = "";
    series.forEach(function (one) {
      var li = el("li", "series-row");
      li.setAttribute("data-series", one.id);
      var what = el("div", "series-what");
      var name = el("span", "series-name", one.name);
      what.appendChild(name);
      if (one.hebrew) {
        var hebrew = el("bdi", "series-hebrew", one.hebrew);
        hebrew.setAttribute("lang", "he");
        hebrew.setAttribute("dir", "rtl");
        what.appendChild(hebrew);
      }
      what.appendChild(el("p", "series-blurb", one.what || ""));
      var now = el("p", "series-now");
      if (one.instalment) {
        var title = el("bdi", "series-title", one.instalment.hebrew || one.instalment.title);
        if (one.instalment.hebrew) {
          title.setAttribute("lang", "he");
          title.setAttribute("dir", "rtl");
        }
        now.appendChild(title);
        var when = whenSaid(one.instalment.when);
        if (when) now.appendChild(el("span", "series-when", when));
      } else {
        now.textContent = "Nothing this week yet.";
      }
      what.appendChild(now);
      li.appendChild(what);

      var acts = el("div", "series-acts");
      var toggle = el("button", "series-follow");
      toggle.type = "button";
      function settle() {
        var on = following(one.id);
        toggle.textContent = on ? "Following" : "Follow";
        toggle.setAttribute("aria-pressed", on ? "true" : "false");
        li.classList.toggle("followed", on);
      }
      toggle.onclick = function () {
        follow(one.id, !following(one.id));
        settle();
      };
      settle();
      acts.appendChild(toggle);
      if (one.page) {
        var open = el("a", "series-open", "Open");
        open.href = keyed(one.page);
        acts.appendChild(open);
      }
      li.appendChild(acts);
      host.appendChild(li);
    });
  }

  window.TargumFollow = {
    list: list,
    follows: follows,
    following: following,
    follow: follow,
    seen: seen,
    markSeen: markSeen,
    readerOf: readerOf,
    fresh: fresh,
    whenSaid: whenSaid,
    draw: draw,
  };

  // The Library carries the row; anywhere else this only answers questions.
  var host = document.getElementById("series");
  var section = document.getElementById("subscriptions");
  if (host && section) {
    list().then(function (series) {
      if (!series.length) return;
      draw(host, series);
      section.hidden = false;
    });
  }
})();
