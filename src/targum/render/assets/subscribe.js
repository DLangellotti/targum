/* Subscribe, where a series is (design.md §12, "A subscription is the account's",
 * 2026-10-09; boards SeriesWeekly, SeriesPortion and SeriesCycle), and the hook a Library
 * row calls.
 *
 *  - On a series' own page (`_series_subscribe.html.j2`): one switch, Subscribe and
 *    Subscribed, on the account's `/account/follows`. A series is free, so the press is
 *    the subscription; nothing is confirmed elsewhere.
 *  - `TargumSubscribe.button(kind, key, words)`, for a Library row: the same switch for a
 *    series, and for anything else — a channel, a podcast, an outlet, a topic — a link to
 *    targum's confirm page (`/subscribe`), where the cap is chosen and the press is made.
 *    It fetches nothing until pressed.
 *
 * The words are the page's own (`data-subscribe`, `data-subscribed`), so a public page
 * that hands its scripts no catalogue still says them in its language.
 */
(function () {
  "use strict";

  var key = window.TARGUM_KEY || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  function ask(path, body) {
    var head = { "Content-Type": "application/json" };
    if (key) head["X-Targum-Key"] = key;
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      credentials: "same-origin",
      headers: head,
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.ok ? response.json() : null;
    });
  }

  var held = null;
  function follows() {
    if (!held) {
      held = ask("/account/follows").catch(function () {
        return null;
      });
    }
    return held;
  }

  // The switch for one series: Subscribe until pressed, Subscribed after.
  function seriesSwitch(press, series, words) {
    var on = false;
    function settle() {
      press.textContent = on ? words.subscribed : words.subscribe;
      press.setAttribute("aria-pressed", on ? "true" : "false");
    }
    settle();
    press.addEventListener("click", function () {
      press.disabled = true;
      ask("/account/follows", { series: series, on: !on })
        .then(function (answer) {
          if (answer && Array.isArray(answer.follows)) on = answer.follows.indexOf(series) >= 0;
          held = Promise.resolve(answer);
          settle();
        })
        .catch(function () {})
        .then(function () {
          press.disabled = false;
        });
    });
    return follows().then(function (answer) {
      if (!answer || !answer.signedIn) return false;
      on = (answer.follows || []).indexOf(series) >= 0;
      settle();
      return true;
    });
  }

  /* A Library row's Subscribe (design.md §12, 2026-10-09: "Subscribe from … Library
     rows"). `kind` is series, topic, outlet, channel or podcast; `given` is the series'
     id, the topic, the outlet's key, or the channel's or podcast's address; `words` is
     `{subscribe, subscribed}`. Returns the element to put in the row. */
  function button(kind, given, words) {
    if (kind === "series") {
      var press = document.createElement("button");
      press.type = "button";
      press.className = "sub-subscribe";
      seriesSwitch(press, given, words);
      return press;
    }
    var link = document.createElement("a");
    link.className = "sub-subscribe";
    var field = kind === "channel" || kind === "podcast" ? "source" : "key";
    link.href = keyed(
      "/subscribe?kind=" + encodeURIComponent(kind) + "&" + field + "=" + encodeURIComponent(given) + "&via=library"
    );
    link.textContent = words.subscribe;
    return link;
  }

  window.TargumSubscribe = { button: button };

  function mount() {
    var box = document.getElementById("series-subscribe");
    if (!box) return;
    var press = box.querySelector("button");
    var words = {
      subscribe: box.getAttribute("data-subscribe") || "",
      subscribed: box.getAttribute("data-subscribed") || "",
    };
    seriesSwitch(press, box.getAttribute("data-series") || "", words).then(function (shown) {
      box.hidden = !shown;
    });
  }
  if (document.readyState === "loading" && document.addEventListener) {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
