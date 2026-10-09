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

  var tabView = { chip: "all" };

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
    var meta = [kindWord(one.kind)];
    if (languageName(one.language)) meta.push(languageName(one.language));
    names.appendChild(el("span", "sub-meta", meta.join(" · ")));
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
      var used = el("span", "sub-used" + (one.builds && one.cap && one.used >= one.cap ? " is-full" : ""), month(one));
      right.appendChild(used);
    }
    item.appendChild(right);
    return item;
  }

  function chips(host, rows, redraw) {
    var counts = { all: rows.length, series: 0, news: 0, channel: 0, podcast: 0 };
    rows.forEach(function (one) {
      counts[chipOf(one.kind)] += 1;
    });
    host.textContent = "";
    CHIPS.forEach(function (pair) {
      if (pair[0] !== "all" && !counts[pair[0]]) return;
      var press = el("button", "chip");
      press.type = "button";
      press.setAttribute("aria-pressed", tabView.chip === pair[0] ? "true" : "false");
      press.appendChild(document.createTextNode(pair[1]() + " "));
      press.appendChild(el("span", "chip-count", String(counts[pair[0]])));
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
      var rows = answer.subscriptions || [];
      var back = (answer.credits && answer.credits.back) || "";
      function redraw() {
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
      if (head) head.hidden = !rows.length;
      chipHost.hidden = rows.length < 2;
      if (none) none.hidden = rows.length > 0;
      if (line) {
        var builds = rows.filter(function (one) {
          return one.builds;
        });
        var spent = builds.reduce(function (sum, one) {
          return sum + Number(one.used || 0);
        }, 0);
        var parts = [];
        if (builds.length) parts.push(tn("subs.credits.used", spent, "{n} credit on subscriptions this month", "{n} credits on subscriptions this month"));
        if (builds.length && answer.credits && answer.credits.left !== null && answer.credits.left !== undefined) {
          parts.push(tn("subs.credits.left", answer.credits.left, "{n} left in all, back on {date}", "{n} left in all, back on {date}", { date: back }));
        }
        line.textContent = parts.join(" · ");
        line.hidden = !parts.length;
      }
      var taken = {};
      rows.forEach(function (one) {
        if (one.kind === "series") taken[one.key] = true;
      });
      offer(offered, answer.series, taken);
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

  function itemRow(one, item, back) {
    var li = el("li", "sub-item");
    var what = el("div", "sub-item-what");
    var door = doorOf(item);
    var title = el(item.reader ? "a" : "span", "sub-item-title");
    if (item.reader) title.href = keyed(door);
    title.appendChild(said(item.title, one.language));
    what.appendChild(title);
    var facts = [];
    if (!item.seen && item.came === "" && (item.state === "ready" || item.state === "listed") && item.found >= one.since) {
      li.classList.add("is-new");
      what.insertBefore(el("span", "sub-new", t("subs.state.new", "New")), title);
    }
    var state = stateWord(item, back);
    if (state) facts.push(state);
    if (item.seconds > 0) facts.push(minutes(item.seconds));
    if (facts.length) what.appendChild(el("span", "sub-item-facts", facts.join(" · ")));
    li.appendChild(what);

    var act;
    if (item.state === "waiting" && item.why === "cap") {
      act = el("a", "btn text small danger sub-act", t("subs.act.raise-cap", "Raise the cap"));
      act.href = "#sub-cap";
    } else if (item.reader) {
      act = el("a", "btn text small sub-act", verb(one));
      act.href = keyed(door);
    } else if (item.link && item.state !== "building" && item.state !== "due") {
      // Not ready, and not going to get ready by itself: one press on the Upload page.
      var label = one.builds
        ? item.seconds > 0
          ? tn("subs.act.get-ready-about", credits(item.seconds), "Get it ready · about {n} credit", "Get it ready · about {n} credits")
          : t("subs.act.get-ready", "Get it ready")
        : t("subs.act.read-on-targum", "Read on targum");
      act = el("a", "btn ghost small sub-act is-quiet", label);
      act.href = keyed(door);
    }
    if (act) li.appendChild(act);
    return li;
  }

  function section(head, note, items, one, back) {
    if (!items.length) return null;
    var box = el("section", "sub-items");
    var top = el("div", "sub-items-head");
    top.appendChild(el("h2", "", head));
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

  function drawOne(answer, body, saidLine) {
    var one = answer.subscription;
    var back = (answer.credits && answer.credits.back) || "";
    body.textContent = "";
    document.title = nameOf(one) + " — targum";

    var head = el("header", "card sub-head");
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
    var meta = [kindWord(one.kind)];
    if (languageName(one.language)) meta.push(languageName(one.language));
    meta.push(every(one));
    if (one.since) meta.push(t("subs.since", "subscribed since {date}", { date: whenSaid(one.since) }));
    names.appendChild(el("p", "sub-meta", meta.join(" · ")));
    head.appendChild(names);

    var acts = el("div", "sub-head-acts");
    function act(label, action, className) {
      var press = el("button", className, label);
      press.type = "button";
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
    if (one.state === "on") {
      acts.appendChild(act(t("subs.pause", "Pause"), "pause", "btn ghost outline sub-pause"));
      acts.appendChild(act(t("subs.unsubscribe", "Unsubscribe"), "unsubscribe", "btn ghost danger sub-stop"));
    } else if (one.state === "paused") {
      acts.appendChild(act(t("subs.resume", "Resume"), "resume", "btn ghost outline sub-resume"));
      acts.appendChild(act(t("subs.unsubscribe", "Unsubscribe"), "unsubscribe", "btn ghost danger sub-stop"));
    } else {
      acts.appendChild(act(t("subs.subscribe-again", "Subscribe again"), "resume", "btn tonal sub-resume"));
    }
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
    var main = section(itemsHead(one), t("subs.items.newest", "Newest first"), now, one, back);
    if (main) body.appendChild(main);
    else body.appendChild(el("p", "note sub-none", t("subs.items.none", "Nothing yet. New ones appear here as they come out.")));
    var meanwhile = section(t("subs.paused.head", "Out while it was paused"), t("subs.not-by-itself", "Not got ready unless you choose"), paused, one, back);
    if (meanwhile) body.appendChild(meanwhile);
    var earlier = section(t("subs.before.head", "Out before you subscribed"), t("subs.not-by-itself", "Not got ready unless you choose"), before, one, back);
    if (earlier) body.appendChild(earlier);

    if (one.builds) body.appendChild(capSection(answer, body, saidLine));
    // The mail (design.md §12, "Everything new comes in one mail a day"): one a day, with
    // everything new; the way out of it is the way out of the subscription.
    var mail = el("section", "card sub-cap sub-mail");
    mail.appendChild(el("h2", "", t("subs.mail.head", "Mail")));
    mail.appendChild(
      el(
        "p",
        "note",
        one.key === "weekly" && one.kind === "series"
          ? t("subs.mail.weekly", "The weekly comes by mail every Monday. To stop it, unsubscribe.")
          : t("subs.mail.says", "What's new comes in one mail a day, with everything else new. To stop it, unsubscribe.")
      )
    );
    body.appendChild(mail);
    // For whatever draws more onto the page — the cap's choices (`TargumSubs.onOne`).
    hooks.forEach(function (hook) {
      try {
        hook(answer, body, saidLine);
      } catch (e) {}
    });
  }

  /* The month's cap, changed here and nowhere else (design.md §12, "A monthly cap is the
     second press that lasts", 2026-10-09): the four the confirm page offers, the one
     chosen marked, and Save. */
  function capSection(answer, body, saidLine) {
    var one = answer.subscription;
    var cap = el("section", "card sub-cap");
    cap.id = "sub-cap";
    cap.appendChild(el("h2", "", t("subs.cap.head", "Monthly cap")));
    cap.appendChild(el("p", "sub-cap-used", t("subs.cap.used", "{used} of {cap} credits used this month", { used: one.used, cap: one.cap })));
    var form = el("form", "sub-cap-form");
    var group = el("div", "cap-choices");
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
      group.appendChild(label);
    });
    form.appendChild(group);
    form.appendChild(el("p", "note", t("subs.cap.says", "New ones get ready by themselves until the cap is reached. Then the next one waits until the 1st, or until you raise the cap.")));
    if (answer.credits && answer.credits.left !== null && answer.credits.left !== undefined) {
      form.appendChild(el("p", "note", tn("subs.cap.left", answer.credits.left, "{n} credit left in your plan this month.", "{n} credits left in your plan this month.")));
    }
    var save = el("button", "btn tonal sub-pause", t("subs.cap.save", "Save"));
    save.type = "submit";
    form.appendChild(save);
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
