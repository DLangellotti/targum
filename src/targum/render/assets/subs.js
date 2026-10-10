/* Subscriptions (design.md §12, "A subscription is the account's, and what it brings
 * comes under Continue", 2026-10-09; boards SubsTab and SubDetail).
 *
 * Two places, one file:
 *
 *  - home's Subscriptions tab (`drawTab`, called by `yours.js`): every subscription as a
 *    row — what it is, its newest, how often it comes out and, for a channel or a podcast,
 *    the month's credits against its cap — sorted into chips, and under them the series
 *    this box has that the reader has not taken, each with Subscribe.
 *  - `/subscriptions/<id>`: one subscription, what it brought newest first, what was out
 *    before, Pause and Unsubscribe.
 *
 * The server keeps every subscription and answers with the whole of one after each
 * change. Nothing here spends: an item that is not ready is a link to the Upload page with
 * its address in the box, where it is got ready on the reader's own press.
 */

(function () {
  "use strict";

  var words = window.TargumStrings;
  var t = words.t;
  var tn = words.tn;
  var key = window.TARGUM_KEY || "";
  var covers = window.TargumCovers;

  function keyed(path) {
    if (!key) return path;
    var parts = String(path).split("#");
    return (
      parts[0] +
      (parts[0].indexOf("?") < 0 ? "?" : "&") +
      "k=" +
      encodeURIComponent(key) +
      (parts[1] ? "#" + parts[1] : "")
    );
  }

  var UNREACHED = t("subs.unreached", "We couldn't reach targum. Try again in a moment.");
  var FAILED = t("subs.failed", "We couldn't do that. Try again.");

  function ask(path, body) {
    var head = { "Content-Type": "application/json" };
    if (key) head["X-Targum-Key"] = key;
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      credentials: "same-origin",
      headers: head,
      body: body ? JSON.stringify(body) : undefined,
    })
      .then(function (response) {
        return response
          .json()
          .catch(function () {
            return {};
          })
          .then(function (answer) {
            answer = answer || {};
            answer.status = response.status;
            return answer;
          });
      })
      .catch(function () {
        return { status: 0, error: UNREACHED };
      });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function said(text, language) {
    var node = el("bdi", "", text);
    node.setAttribute("dir", "auto");
    if (language) node.setAttribute("lang", language);
    return node;
  }

  /* --- words ------------------------------------------------------------------------ */

  // What a kind is called on a row, and on the chips (which count news as one).
  function kindWord(kind) {
    return {
      series: t("subs.kind.series", "Series"),
      topic: t("subs.kind.topic", "News topic"),
      outlet: t("subs.kind.outlet", "Outlet"),
      channel: t("subs.kind.channel", "Channel"),
      podcast: t("subs.kind.podcast", "Podcast"),
    }[kind] || "";
  }

  var CHIPS = [
    ["all", function () { return t("subs.chip.all", "All"); }],
    ["series", function () { return t("subs.chip.series", "Series"); }],
    ["news", function () { return t("subs.chip.news", "News"); }],
    ["channel", function () { return t("subs.chip.channels", "Channels"); }],
    ["podcast", function () { return t("subs.chip.podcasts", "Podcasts"); }],
  ];

  function chipOf(kind) {
    return kind === "topic" || kind === "outlet" ? "news" : kind;
  }

  function languageName(code) {
    var names = window.TARGUM_LANGUAGES || {};
    return names[code] || "";
  }

  function topicName(key) {
    return {
      world: t("subs.topic.world", "World"),
      politics: t("subs.topic.politics", "Politics"),
      economy: t("subs.topic.economy", "Economy"),
      culture: t("subs.topic.culture", "Culture"),
      science: t("subs.topic.science", "Science"),
      tech: t("subs.topic.tech", "Technology"),
      sport: t("subs.topic.sport", "Sport"),
      health: t("subs.topic.health", "Health"),
    }[key] || key;
  }

  function nameOf(one) {
    return one.kind === "topic" ? topicName(one.key) : one.name;
  }

  function every(one) {
    if (one.every === "day") return t("subs.every.day", "Every day");
    if (one.every === "week") return t("subs.every.week", "Every week");
    if (one.every === "monday") return t("subs.every.monday", "Every Monday");
    var week = Number(one.perWeek || 0);
    if (week >= 1) return tn("subs.every.per-week", Math.round(week), "About {n} a week", "About {n} a week");
    if (week > 0) {
      return tn("subs.every.per-month", Math.max(1, Math.round((week * 30) / 7)), "About {n} a month", "About {n} a month");
    }
    return t("subs.every.as-it-comes", "As it comes out");
  }

  function month(one) {
    if (!one.builds) return t("subs.month.free", "No credits");
    return t("subs.month.used", "{used} of {cap} credits", { used: one.used, cap: one.cap });
  }

  function minutes(seconds) {
    return t("subs.minutes", "{n} min", { n: Math.max(1, Math.round(Number(seconds) / 60)) });
  }

  function credits(seconds) {
    return Math.max(1, Math.round(Number(seconds) / 60));
  }

  // The verb an item opens with, after its medium (design.md §6).
  function verb(one) {
    if (one.kind === "channel") return t("subs.act.watch", "Watch");
    if (one.kind === "podcast") return t("subs.act.listen", "Listen");
    return t("subs.act.read", "Read");
  }

  // What an item is now, in a few words, or "".
  function stateWord(item, back) {
    if (item.state === "building") return t("subs.state.building", "Getting ready");
    if (item.state === "due") return t("subs.state.due", "Gets ready by itself");
    if (item.state === "waiting") return t("subs.state.waiting", "Waiting for {date}", { date: back || "" });
    if (item.state === "failed") return t("subs.state.failed", "We couldn't get it ready");
    return "";
  }

  // Where an item opens: its reader once it has one, else the Upload page with its
  // address in the box — free to look at, got ready only on the reader's own press.
  function doorOf(item) {
    if (item.reader) return item.reader;
    if (item.link) return "/add?source=" + encodeURIComponent(item.link);
    return "";
  }

  /* The one tile path (covers.js `picture`): the newest one's own picture where it has
     one, or its letter on the colour of the subscription's kind — the Hebrew name's
     letter first, so a series is not a Latin "T" (P2, 2026-10-09). */
  function tile(one) {
    var newest = one.latest || {};
    return covers
      ? covers.picture(
          {
            entry: newest.entry || newest.name || "",
            title: one.hebrew || nameOf(one),
            language: one.hebrew ? "he" : one.language,
            kind: chipOf(one.kind),
          },
          { keyed: keyed, className: "thumb sub-tile" }
        )
      : el("span", "thumb sub-tile is-letter");
  }

  /* --- the tab ------------------------------------------------------------------------ */

  var tabView = { chip: "all", language: "" };

  function row(one, back) {
    var item = el("li", "sub-row" + (one.state === "paused" ? " is-paused" : ""));
    item.setAttribute("data-kind", one.kind);
    var who = el("div", "sub-who");
    who.appendChild(tile(one));
    var names = el("div", "sub-names");
    var link = el("a", "sub-name");
    link.href = keyed(one.page);
    link.appendChild(said(nameOf(one), one.kind === "series" ? "" : one.language));
    names.appendChild(link);
    if (one.hebrew) {
      var hebrew = said(one.hebrew, "he");
      hebrew.className = "sub-hebrew";
      names.appendChild(hebrew);
    }
    // Its kind as a `.tag`, and where it comes from (board SubsTab).
    var meta = el("span", "sub-meta");
    meta.appendChild(el("span", "tag", kindWord(one.kind)));
    var from = [];
    if (one.kind === "channel") from.push("YouTube");
    if (one.kind === "topic" || one.kind === "outlet") from.push(t("subs.chip.news", "News"));
    if (languageName(one.language)) from.push(languageName(one.language));
    if (from.length) meta.appendChild(document.createTextNode(" " + from.join(" · ")));
    names.appendChild(meta);
    who.appendChild(names);
    item.appendChild(who);

    var latest = el("div", "sub-latest");
    var newest = one.latest;
    if (newest) {
      if (newest.state !== "building" && !newest.seen && one.new > 0) {
        latest.appendChild(el("span", "sub-new", t("subs.state.new", "New")));
      }
      var title = el(doorOf(newest) ? "a" : "span", "sub-latest-title");
      if (doorOf(newest)) title.href = keyed(doorOf(newest));
      title.appendChild(said(newest.title, one.language));
      latest.appendChild(title);
      var state = stateWord(newest, back);
      if (state) latest.appendChild(el("span", "sub-state", state));
    } else {
      latest.appendChild(el("span", "sub-state", t("subs.state.nothing-yet", "Nothing yet")));
    }
    item.appendChild(latest);

    item.appendChild(el("span", "sub-every", every(one)));

    var right = el("div", "sub-month");
    if (one.state === "paused") {
      right.appendChild(el("span", "sub-state", t("subs.state.paused", "Paused")));
      var resume = el("button", "btn ghost outline small sub-resume", t("subs.resume", "Resume"));
      resume.type = "button";
      resume.onclick = function () {
        resume.disabled = true;
        ask("/subscriptions/" + one.id, { action: "resume" }).then(function () {
          drawTab(lastHost);
        });
      };
      right.appendChild(resume);
    } else {
      var full = one.builds && one.cap && one.used >= one.cap;
      var used = el("span", "sub-used" + (full ? " is-full" : ""), month(one));
      right.appendChild(used);
      if (one.builds && one.cap) {
        // The month's credits against the cap, as a meter: clay at the cap (§4).
        var meter = el("span", "meter sub-meter " + (full ? "is-full" : "is-spent"));
        var fill = el("span");
        fill.style.setProperty("--done", String(Math.min(1, Number(one.used || 0) / Number(one.cap))));
        meter.appendChild(fill);
        right.appendChild(meter);
      }
      if (full) {
        var raise = el("a", "btn text small danger sub-raise", t("subs.act.raise-cap", "Raise the cap"));
        raise.href = keyed(one.page + "#sub-cap");
        right.appendChild(raise);
      }
    }
    item.appendChild(right);

    // Pause in one press, and the way to its own page.
    var acts = el("div", "sub-row-acts");
    if (one.state === "on") {
      var pause = el("button", "btn ghost small sub-row-pause");
      pause.type = "button";
      pause.title = t("subs.pause", "Pause");
      pause.setAttribute("aria-label", t("subs.pause", "Pause") + " · " + nameOf(one));
      pause.appendChild(glyph("pause"));
      pause.onclick = function () {
        pause.disabled = true;
        ask("/subscriptions/" + one.id, { action: "pause" }).then(function () {
          drawTab(lastHost);
        });
      };
      acts.appendChild(pause);
    }
    var open = el("a", "btn ghost small sub-row-open");
    open.href = keyed(one.page);
    open.setAttribute("aria-label", nameOf(one));
    open.appendChild(glyph("chevron"));
    acts.appendChild(open);
    item.appendChild(acts);
    return item;
  }

  function chips(host, rows, redraw) {
    var counts = { all: rows.length, series: 0, news: 0, channel: 0, podcast: 0 };
    rows.forEach(function (one) {
      counts[chipOf(one.kind)] += 1;
    });
    host.textContent = "";
    CHIPS.forEach(function (pair) {
      var press = el("button", "tab chip");
      press.type = "button";
      press.setAttribute("aria-pressed", tabView.chip === pair[0] ? "true" : "false");
      press.appendChild(document.createTextNode(pair[1]() + " "));
      press.appendChild(el("span", "tab-count chip-count", String(counts[pair[0]])));
      press.onclick = function () {
        tabView.chip = pair[0];
        redraw();
      };
      host.appendChild(press);
    });
  }

  function offer(host, series, taken) {
    host.textContent = "";
    var left = (series || []).filter(function (one) {
      return !taken[one.id];
    });
    if (!left.length) return;
    host.appendChild(el("h3", "sub-offer-head", t("subs.offer.head", "Series you can subscribe to")));
    var list = el("ul", "sub-offer");
    left.forEach(function (one) {
      var item = el("li", "sub-offer-row");
      var names = el("div", "sub-names");
      names.appendChild(said(one.name));
      if (one.hebrew) {
        var hebrew = said(one.hebrew, "he");
        hebrew.className = "sub-hebrew";
        names.appendChild(hebrew);
      }
      if (one.what) names.appendChild(el("span", "sub-meta", one.what));
      item.appendChild(names);
      var press = el("button", "btn tonal sub-subscribe", t("subs.subscribe", "Subscribe"));
      press.type = "button";
      press.onclick = function () {
        press.disabled = true;
        ask("/account/follows", { series: one.id, on: true }).then(function () {
          drawTab(lastHost);
        });
      };
      item.appendChild(press);
      list.appendChild(item);
    });
    host.appendChild(list);
  }

  var lastHost = null;

  /* Home's Subscriptions tab, drawn into `host` (`#subs-panel`). Signed out — a machine
     somebody runs with nobody signed in — the browser's own list of series is all there
     is, and `follow.js` draws it as before. */
  function drawTab(host) {
    if (!host) return Promise.resolve(false);
    lastHost = host;
    return ask("/subscriptions.json").then(function (answer) {
      var table = host.querySelector("#subs-rows");
      var chipHost = host.querySelector("#subs-chips");
      var line = host.querySelector("#subs-credits");
      var none = host.querySelector("#subs-empty");
      var offered = host.querySelector("#subs-offer");
      var sayLine = host.querySelector("#subs-said");
      if (answer.status !== 0 && answer.signedIn !== true) {
        // Nobody signed in — or a page off the disk with no server behind it.
        return drawSignedOut(host);
      }
      if (answer.status !== 200) {
        if (sayLine) {
          sayLine.textContent = answer.status === 0 ? UNREACHED : FAILED;
          sayLine.hidden = false;
        }
        return false;
      }
      if (sayLine) sayLine.hidden = true;
      var every = answer.subscriptions || [];
      var back = (answer.credits && answer.credits.back) || "";
      var languages = host.querySelector("#subs-languages");
      var spoken = [];
      every.forEach(function (one) {
        if (one.language && spoken.indexOf(one.language) < 0) spoken.push(one.language);
      });
      if (tabView.language && spoken.indexOf(tabView.language) < 0) tabView.language = "";
      if (languages) {
        // All languages, and each a subscription is in (board SubsTab).
        languages.textContent = "";
        var all = el("option", "", t("subs.languages.all", "All languages"));
        all.value = "";
        languages.appendChild(all);
        spoken.forEach(function (code) {
          var option = el("option", "", languageName(code) || code);
          option.value = code;
          languages.appendChild(option);
        });
        languages.value = tabView.language;
        languages.hidden = spoken.length < 1;
        languages.onchange = function () {
          tabView.language = languages.value;
          redraw();
        };
      }
      var rows = every;
      function redraw() {
        rows = every.filter(function (one) {
          return !tabView.language || one.language === tabView.language;
        });
        chips(chipHost, rows, redraw);
        table.textContent = "";
        rows
          .filter(function (one) {
            return tabView.chip === "all" || chipOf(one.kind) === tabView.chip;
          })
          .forEach(function (one) {
            table.appendChild(row(one, back));
          });
      }
      redraw();
      var head = host.querySelector("#subs-head");
      if (head) head.hidden = !every.length;
      chipHost.hidden = !every.length;
      if (none) none.hidden = every.length > 0;
      if (line) {
        var builds = every.filter(function (one) {
          return one.builds;
        });
        var spent = builds.reduce(function (sum, one) {
          return sum + Number(one.used || 0);
        }, 0);
        var parts = [];
        var known = every.length && answer.credits && answer.credits.left !== null && answer.credits.left !== undefined;
        if (builds.length || known) parts.push(tn("subs.credits.used", spent, "{n} credit on subscriptions this month", "{n} credits on subscriptions this month"));
        if (known) {
          parts.push(tn("subs.credits.left", answer.credits.left, "{n} left in all, resets on {date}", "{n} left in all, resets on {date}", { date: back }));
        }
        line.textContent = parts.join(" · ");
        line.hidden = !parts.length;
      }
      var taken = {};
      every.forEach(function (one) {
        if (one.kind === "series") taken[one.key] = true;
      });
      // The series not taken are offered here only while there is nothing on the tab:
      // Subscribe lives on a series' own page and in the Library (design.md §12, "A
      // subscription's page is two columns, and the tab is a table with its filters").
      offer(offered, every.length ? [] : answer.series, taken);
      return true;
    });
  }

  function drawSignedOut(host) {
    var follow = window.TargumFollow;
    var list = host.querySelector("#home-series");
    var none = host.querySelector("#subs-empty");
    if (!follow || !list) return Promise.resolve(false);
    return follow.list().then(function (series) {
      var order = series.slice().sort(function (a, b) {
        return (follow.following(b.id) ? 1 : 0) - (follow.following(a.id) ? 1 : 0);
      });
      follow.draw(list, order);
      list.hidden = false;
      if (none) none.hidden = series.length > 0;
      return true;
    });
  }

  /* --- one subscription ------------------------------------------------------------- */

  /* A series' items are named for what the series is (design review, 2026-10-09):
     "Instalments" was the catalogue's word for all three. */
  function itemsHead(one) {
    if (one.kind === "series") {
      if (one.key === "weekly") return t("subs.items.issues", "Issues");
      if (one.key === "parasha") return t("subs.items.portions", "Portions");
      return t("subs.items.days", "Days");
    }
    return {
      topic: t("subs.items.news", "Articles"),
      outlet: t("subs.items.news", "Articles"),
      channel: t("subs.items.channel", "Videos"),
      podcast: t("subs.items.podcast", "Episodes"),
    }[one.kind];
  }

  // A small line drawing (§7): sixteen pixels, a stroke at 1.4, round caps.
  var GLYPHS = {
    play: "M6 4.5v7l5.5-3.5z",
    tick: "M3.5 8.5l3 3 6-7",
    clock: "M8 2.5a5.5 5.5 0 1 0 0 11a5.5 5.5 0 1 0 0-11M8 5v3.2l2 1.3",
    pause: "M5.5 3.5v9M10.5 3.5v9",
    stop: "M8 2.5a5.5 5.5 0 1 0 0 11a5.5 5.5 0 1 0 0-11M4.1 4.1l7.8 7.8",
    mail: "M2.5 4h11v8h-11zM2.5 4.5 8 9l5.5-4.5",
    lock: "M4.5 7.5h7v6h-7zM6 7.5V5.5a2 2 0 0 1 4 0v2",
    back: "M10 3.5 5.5 8l4.5 4.5",
    chevron: "M6 3.5 10.5 8 6 12.5",
  };
  function glyph(name, className) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", "sub-glyph" + (className ? " " + className : ""));
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", GLYPHS[name]);
    svg.appendChild(path);
    return svg;
  }

  // What the one who opened an item did with it, in the medium's word.
  function doneWord(one) {
    if (one.kind === "channel") return t("subs.state.watched", "Watched");
    if (one.kind === "podcast") return t("subs.state.listened", "Listened");
    return t("subs.state.read", "Read");
  }

  // The verb an item opens with once it was opened before: Watch again, Read again.
  function againWord(one) {
    if (one.kind === "channel") return t("subs.act.watch-again", "Watch again");
    if (one.kind === "podcast") return t("subs.act.listen-again", "Listen again");
    return t("subs.act.read-again", "Read again");
  }

  /* An item's picture: the frame its reader keeps once it is made, else a plain cell
     with the medium's glyph — never somebody else's server. */
  function itemPicture(one, item) {
    var box = el("span", "sub-item-pic" + (one.kind === "channel" ? " is-wide" : ""));
    var found = /^\/reader\/([^/]+)\/reader\//.exec(item.reader || "");
    if (found) {
      var img = el("img");
      img.alt = "";
      img.loading = "lazy";
      img.src = keyed("/thumb/" + found[1]);
      img.onerror = function () {
        img.remove();
      };
      box.appendChild(img);
    }
    box.appendChild(glyph(one.kind === "channel" ? "play" : one.kind === "podcast" ? "play" : "tick", "sub-item-pic-glyph"));
    return box;
  }

  function itemRow(one, item, back) {
    var li = el("li", "sub-item");
    var door = doorOf(item);
    li.appendChild(itemPicture(one, item));
    var what = el("div", "sub-item-what");
    var title = el(item.reader ? "a" : "span", "sub-item-title");
    if (item.reader) title.href = keyed(door);
    title.appendChild(said(item.title, one.language));
    what.appendChild(title);
    var facts = [];
    if (item.seconds > 0) facts.push(minutes(item.seconds));
    if (one.builds && item.seconds > 0) {
      facts.push(tn("subs.credits.about", credits(item.seconds), "about {n} credit", "about {n} credits"));
    }
    if (facts.length) what.appendChild(el("span", "sub-item-facts", facts.join(" · ")));
    var state = el("span", "sub-item-state");
    var isNew = !item.seen && item.came === "" && (item.state === "ready" || item.state === "listed") && item.found >= one.since;
    if (isNew) {
      li.classList.add("is-new");
      state.appendChild(el("span", "sub-new", t("subs.state.new", "New")));
    }
    if (item.state === "waiting") {
      var waiting = el("span", "sub-waiting");
      waiting.appendChild(glyph("clock"));
      waiting.appendChild(document.createTextNode(stateWord(item, back)));
      state.appendChild(waiting);
    } else if (item.seen && item.reader) {
      var done = el("span", "sub-done");
      done.appendChild(glyph("tick"));
      done.appendChild(document.createTextNode(doneWord(one)));
      state.appendChild(done);
    } else {
      var word = stateWord(item, back);
      if (word) state.appendChild(el("span", "sub-state", word));
    }
    if (state.childNodes.length) what.appendChild(state);
    li.appendChild(what);

    var act;
    if (item.state === "waiting" && item.why === "cap") {
      act = el("a", "btn text small danger sub-act", t("subs.act.raise-cap", "Raise the cap"));
      act.href = "#sub-cap";
    } else if (item.reader) {
      act = el("a", "btn text small sub-act", item.seen ? againWord(one) : verb(one));
      act.href = keyed(door);
    } else if (item.link && item.state !== "building" && item.state !== "due") {
      // Not ready, and not going to get ready by itself: one press on the Upload page.
      var label = one.builds
        ? item.seconds > 0
          ? tn("subs.act.get-ready-about", credits(item.seconds), "Get it ready · about {n} credit", "Get it ready · about {n} credits")
          : t("subs.act.get-ready", "Get it ready")
        : t("subs.act.read-on-targum", "Read on targum");
      act = el("a", "btn ghost outline small sub-act is-quiet", label);
      act.href = keyed(door);
    }
    if (act) li.appendChild(act);
    return li;
  }

  function section(head, note, items, one, back) {
    if (!items.length) return null;
    var box = el("section", "card sub-items");
    var top = el("div", "sub-items-head");
    top.appendChild(el("h2", "section-title", head));
    if (note) top.appendChild(el("p", "note", note));
    box.appendChild(top);
    var list = el("ul", "sub-item-list");
    items.forEach(function (item) {
      list.appendChild(itemRow(one, item, back));
    });
    box.appendChild(list);
    return box;
  }

  function whenSaid(ms) {
    if (!ms) return "";
    var at = new Date(Number(ms));
    if (isNaN(at.getTime())) return "";
    var code = words.language || document.documentElement.lang || undefined;
    try {
      return at.toLocaleDateString(code, { day: "numeric", month: "long" });
    } catch (e) {
      return at.toDateString();
    }
  }

  function thisMonth() {
    var code = words.language || document.documentElement.lang || undefined;
    try {
      return new Date().toLocaleDateString(code, { month: "long" });
    } catch (e) {
      return "";
    }
  }

  /* One subscription's page (design.md §12, "A subscription's page is two columns",
     2026-10-09; boards SubDetail and SubCapped): the head with Pause and Unsubscribe; at
     the cap, a card that says so first; then what it brought beside its cap and its
     mail. On a phone the cap comes first, and Pause and Unsubscribe stand at the foot
     with what each does. */
  function drawOne(answer, body, saidLine) {
    var one = answer.subscription;
    var back = (answer.credits && answer.credits.back) || "";
    body.textContent = "";
    document.title = nameOf(one) + " — targum";

    function act(label, action, className, glyphName) {
      var press = el("button", className);
      press.type = "button";
      if (glyphName) press.appendChild(glyph(glyphName));
      press.appendChild(document.createTextNode(label));
      press.onclick = function () {
        press.disabled = true;
        ask("/subscriptions/" + one.id, { action: action }).then(function (got) {
          if (got.status === 200 && got.subscription) {
            drawOne(got, body, saidLine);
            if (action === "unsubscribe") {
              saidLine.textContent = t("subs.unsubscribed", "You're unsubscribed. Nothing more comes from it.");
              saidLine.hidden = false;
            }
            return;
          }
          press.disabled = false;
          saidLine.textContent = got.status === 0 ? UNREACHED : FAILED;
          saidLine.hidden = false;
        });
      };
      return press;
    }
    function presses() {
      var out = [];
      if (one.state === "on") {
        out.push(act(t("subs.pause", "Pause"), "pause", "btn ghost outline sub-pause", "pause"));
        out.push(act(t("subs.unsubscribe", "Unsubscribe"), "unsubscribe", "btn ghost outline danger sub-stop", "stop"));
      } else if (one.state === "paused") {
        out.push(act(t("subs.resume", "Resume"), "resume", "btn ghost outline sub-resume", "play"));
        out.push(act(t("subs.unsubscribe", "Unsubscribe"), "unsubscribe", "btn ghost outline danger sub-stop", "stop"));
      } else {
        out.push(act(t("subs.subscribe-again", "Subscribe again"), "resume", "btn filled sub-resume"));
      }
      return out;
    }

    var head = el("header", "sub-head");
    head.appendChild(tile(one));
    var names = el("div", "sub-names");
    var h1 = el("h1", "sub-title");
    h1.id = "sub-name";
    h1.appendChild(said(nameOf(one), one.kind === "series" ? "" : one.language));
    names.appendChild(h1);
    if (one.hebrew) {
      var hebrew = said(one.hebrew, "he");
      hebrew.className = "sub-hebrew";
      names.appendChild(hebrew);
    }
    var meta = el("p", "sub-meta");
    meta.appendChild(el("span", "tag", kindWord(one.kind)));
    var facts = [];
    if (languageName(one.language)) facts.push(languageName(one.language));
    facts.push(every(one));
    if (one.since) facts.push(t("subs.since", "subscribed since {date}", { date: whenSaid(one.since) }));
    meta.appendChild(document.createTextNode(" " + facts.join(" · ")));
    names.appendChild(meta);
    head.appendChild(names);
    var acts = el("div", "sub-head-acts");
    presses().forEach(function (press) {
      acts.appendChild(press);
    });
    head.appendChild(acts);
    body.appendChild(head);

    if (one.state === "paused") {
      body.appendChild(el("p", "sub-paused-note", t("subs.paused.note", "Paused. Nothing gets ready and nothing is mailed. When you resume, what came out meanwhile is listed here for you to choose.")));
    }

    var items = one.items || [];
    var now = items.filter(function (item) {
      return item.came === "";
    });
    var paused = items.filter(function (item) {
      return item.came === "paused";
    });
    var before = items.filter(function (item) {
      return item.came === "before";
    });

    // At the cap, the page says so before anything else (board SubCapped).
    var capped = one.builds && one.cap && one.used >= one.cap && one.state === "on";
    if (capped) {
      var waiting = now.filter(function (item) {
        return item.state === "waiting";
      })[0];
      var full = el("section", "card sub-capped");
      full.appendChild(
        el(
          "p",
          "",
          waiting
            ? t("subs.capped.says", "This month's {cap} credits for {name} are used. {title} gets ready by itself on {date}.", {
                cap: one.cap,
                name: nameOf(one),
                title: waiting.title,
                date: back,
              })
            : t("subs.capped.says-none", "This month's {cap} credits for {name} are used. The next one gets ready by itself on {date}.", {
                cap: one.cap,
                name: nameOf(one),
                date: back,
              })
        )
      );
      var row = el("div", "sub-capped-row");
      var raise = el("a", "btn filled", t("subs.act.raise-cap", "Raise the cap"));
      raise.href = "#sub-cap";
      row.appendChild(raise);
      row.appendChild(el("span", "note", t("subs.capped.others", "Your other subscriptions carry on")));
      full.appendChild(row);
      body.appendChild(full);
    }

    var cols = el("div", "sub-cols");
    var main = el("div", "sub-main");
    var side = el("div", "sub-side");
    var listed = section(itemsHead(one), t("subs.items.newest", "Newest first"), now, one, back);
    if (listed) main.appendChild(listed);
    else {
      var none = el("section", "card sub-items");
      none.appendChild(el("h2", "section-title", itemsHead(one)));
      none.appendChild(el("p", "note sub-none", t("subs.items.none", "Nothing yet. New ones appear here as they come out.")));
      main.appendChild(none);
    }
    var meanwhile = section(t("subs.paused.head", "Out while it was paused"), t("subs.not-by-itself", "Not got ready unless you choose"), paused, one, back);
    if (meanwhile) main.appendChild(meanwhile);
    var earlier = section(t("subs.before.head", "Out before you subscribed"), t("subs.not-by-itself", "Not got ready unless you choose"), before, one, back);
    if (earlier) main.appendChild(earlier);

    if (one.builds) side.appendChild(capSection(answer, body, saidLine, now));
    // The mail (design.md §12, "Everything new comes in one mail a day"): one a day, with
    // everything new; the way out of it is the way out of the subscription.
    var mail = el("section", "card sub-mail");
    mail.appendChild(el("h2", "section-title", t("subs.mail.head", "Mail")));
    var line = el("p", "sub-mail-line");
    line.appendChild(glyph("mail"));
    line.appendChild(
      document.createTextNode(
        one.key === "weekly" && one.kind === "series"
          ? t("subs.mail.weekly", "The weekly comes by mail every Monday. To stop it, unsubscribe.")
          : t("subs.mail.says", "What's new comes in one mail a day, with everything else new. To stop it, unsubscribe.")
      )
    );
    mail.appendChild(line);
    mail.appendChild(el("p", "note", t("subs.mail.continue", "It shows under Continue too.")));
    side.appendChild(mail);

    // On a phone, Pause and Unsubscribe at the foot, each with what it does.
    var stop = el("section", "card sub-stop-card");
    presses().forEach(function (press) {
      var wrap = el("div", "sub-stop-one");
      wrap.appendChild(press);
      var what = press.classList.contains("sub-stop")
        ? t("subs.stop.says", "Ends the subscription and its mail. What you have stays in Your targums.")
        : press.classList.contains("sub-pause")
        ? t("subs.pause.says", "Nothing new gets ready and nothing is mailed until you resume. What came out meanwhile waits for you to choose.")
        : "";
      if (what) wrap.appendChild(el("p", "note", what));
      stop.appendChild(wrap);
    });

    cols.appendChild(main);
    cols.appendChild(side);
    cols.appendChild(stop);
    body.appendChild(cols);
    // For whatever draws more onto the page — the cap's choices (`TargumSubs.onOne`).
    hooks.forEach(function (hook) {
      try {
        hook(answer, body, saidLine);
      } catch (e) {}
    });
  }

  /* The month's cap, changed here and nowhere else (design.md §12, "A monthly cap is the
     second press that lasts", 2026-10-09): the four the confirm page offers as one
     `.seg`, each with about how many that is, the one chosen marked, and Save. */
  function capSection(answer, body, saidLine, items) {
    var one = answer.subscription;
    var cap = el("section", "card sub-cap");
    cap.id = "sub-cap";
    cap.appendChild(el("h2", "section-title", t("subs.cap.head", "Monthly cap")));
    var month = thisMonth();
    cap.appendChild(
      el(
        "p",
        "sub-cap-used",
        month
          ? t("subs.cap.used-in", "{used} of {cap} credits used in {month}", { used: one.used, cap: one.cap, month: month })
          : t("subs.cap.used", "{used} of {cap} credits used this month", { used: one.used, cap: one.cap })
      )
    );
    var meter = el("span", "meter " + (one.cap && one.used >= one.cap ? "is-full" : "is-spent"));
    var fill = el("span");
    fill.style.setProperty("--done", String(one.cap ? Math.min(1, one.used / one.cap) : 0));
    meter.appendChild(fill);
    cap.appendChild(meter);
    // About how many a cap is, from how long this one's items have run.
    var lengths = (items || [])
      .map(function (item) {
        return Number(item.seconds || 0);
      })
      .filter(function (seconds) {
        return seconds > 0;
      });
    var each = lengths.length
      ? Math.max(1, Math.round(lengths.reduce(function (a, b) { return a + b; }, 0) / lengths.length / 60))
      : 0;
    var form = el("form", "sub-cap-form");
    var group = el("div", "seg cap-choices");
    group.setAttribute("role", "radiogroup");
    group.setAttribute("aria-label", t("subs.cap.head", "Monthly cap"));
    (one.caps || [30, 60, 120, 240]).forEach(function (value) {
      var label = el("label", "cap-choice");
      var radio = el("input");
      radio.type = "radio";
      radio.name = "cap";
      radio.value = String(value);
      radio.checked = Number(value) === Number(one.cap);
      label.appendChild(radio);
      label.appendChild(el("span", "cap-number", String(value)));
      if (each) {
        label.appendChild(
          el(
            "span",
            "cap-about",
            one.kind === "podcast"
              ? tn("subs.cap.about-episodes", Math.max(1, Math.round(value / each)), "about {n} episode", "about {n} episodes")
              : tn("subs.cap.about-videos", Math.max(1, Math.round(value / each)), "about {n} video", "about {n} videos")
          )
        );
      }
      if (radio.checked) label.classList.add("on");
      group.appendChild(label);
    });
    form.appendChild(group);
    form.appendChild(el("p", "note", t("subs.cap.says", "New ones get ready by themselves until the cap is reached. Then the next one waits until the 1st, or until you raise the cap.")));
    var foot = el("div", "sub-cap-foot");
    if (answer.credits && answer.credits.left !== null && answer.credits.left !== undefined) {
      foot.appendChild(el("p", "note", tn("subs.cap.left", answer.credits.left, "{n} credit left in your plan this month.", "{n} credits left in your plan this month.")));
    }
    var save = el("button", "btn filled sub-cap-save", t("subs.cap.save", "Save"));
    save.type = "submit";
    save.disabled = true;
    foot.appendChild(save);
    form.appendChild(foot);
    group.addEventListener("change", function () {
      var picked = form.querySelector("input[name=cap]:checked");
      [].forEach.call(group.querySelectorAll(".cap-choice"), function (choice) {
        choice.classList.toggle("on", choice.contains(picked));
      });
      save.disabled = !picked || Number(picked.value) === Number(one.cap);
    });
    form.onsubmit = function (event) {
      event.preventDefault();
      var picked = form.querySelector("input[name=cap]:checked");
      if (!picked) return;
      save.disabled = true;
      ask("/subscriptions/" + one.id, { action: "cap", cap: Number(picked.value) }).then(function (got) {
        if (got.status === 200 && got.subscription) {
          drawOne(got, body, saidLine);
          saidLine.textContent = t("subs.cap.saved", "Saved. The cap is {cap} credits a month.", { cap: got.subscription.cap });
          saidLine.hidden = false;
          return;
        }
        save.disabled = false;
        saidLine.textContent = got.status === 0 ? UNREACHED : FAILED;
        saidLine.hidden = false;
      });
    };
    cap.appendChild(form);
    return cap;
  }

  var hooks = [];

  function mountOne() {
    var section = document.getElementById("sub-one");
    if (!section) return;
    var found = /^\/subscriptions\/(\d+)\/?$/.exec(window.location.pathname);
    var stranger = document.getElementById("stranger");
    var gone = document.getElementById("gone");
    var body = document.getElementById("sub-body");
    var saidLine = document.getElementById("sub-said");
    var backLink = document.getElementById("sub-back");
    if (backLink) backLink.href = keyed(backLink.getAttribute("href"));
    if (!found) {
      gone.hidden = false;
      return;
    }
    ask("/subscriptions/" + found[1] + ".json").then(function (answer) {
      if (answer.status === 401) {
        stranger.hidden = false;
        return;
      }
      if (answer.status !== 200 || !answer.subscription) {
        if (answer.status === 0) {
          saidLine.textContent = UNREACHED;
          saidLine.hidden = false;
          section.hidden = false;
          return;
        }
        gone.hidden = false;
        return;
      }
      section.hidden = false;
      drawOne(answer, body, saidLine);
    });
  }

  window.TargumSubs = {
    drawTab: drawTab,
    // For the tests and for what draws more onto one subscription's page.
    onOne: function (hook) {
      hooks.push(hook);
    },
    every: every,
    doorOf: doorOf,
    kindWord: kindWord,
  };

  if (document.readyState === "loading" && document.addEventListener) {
    document.addEventListener("DOMContentLoaded", mountOne);
  } else {
    mountOne();
  }
})();
