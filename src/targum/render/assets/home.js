/* Home — Your targums, led by Continue (design.md §12, "Home is Your targums, and
 * Continue leads it", 2026-10-08).
 *
 * What this file draws is the head of the page: Continue, the one text to try next, and
 * the way to upload. The shelf under it is `yours.js`, which drew Your targums before it
 * was home and still does.
 *
 * Continue is the last few texts the reader opened or uploaded, newest first, each
 * picking up exactly where they stopped. "Where" is `Store.places` (targum-internal#430):
 * the part, the sentence and the second of its recording, on the account and so on every
 * device, and in this browser (`targum:places`) for somebody signed out. A text still
 * being built is a card too, and a followed series' newest instalment leads, once.
 *
 * Nothing here spends. The suggestion is a link: building it is pressed for on the
 * page it opens, as it is everywhere else.
 */
(function () {
  "use strict";

  var words = window.TargumStrings;
  var t = words.t;
  var tn = words.tn;

  var key = window.TARGUM_KEY;
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
  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }
  function ask(path) {
    return fetch(keyed(path), {
      credentials: "same-origin",
      headers: keyHeaders({ "Content-Type": "application/json" }),
    }).then(function (response) {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}") || {};
    } catch (e) {
      return {};
    }
  }

  var shelf = window.TargumShelf;
  var covers = window.TargumCovers;
  var lang = window.TargumLang;

  //: How many cards Continue holds. A phone shows the first two (`home.css`).
  var CONTINUE_AT_MOST = 4;
  var PLACES = "targum:places";
  //: Set by the arrival for this visit once it is over, so home does not send the reader
  //: straight back to it (`arrival.js`).
  var ARRIVAL_OVER = "targum:arrival-over";

  /* --- what a text is, in a word ---------------------------------------------------- */

  // The verb follows the medium (design.md §6, targum-internal#337).
  function mediumOf(reader) {
    if (reader && reader.video) return "watch";
    return reader && reader.heard ? "listen" : "read";
  }

  function kindWord(reader) {
    if (reader.video) return t("home.kind.video", "Video");
    var kinds = {
      article: t("home.kind.article", "Article"),
      talk: t("home.kind.talk", "Talk"),
      dialogue: t("home.kind.dialogue", "Scene"),
      story: t("home.kind.story", "Story"),
      novel: t("home.kind.novel", "Book"),
      essay: t("home.kind.essay", "Essay"),
      prose: t("home.kind.prose", "Tanakh"),
      poetry: t("home.kind.poetry", "Poetry"),
      play: t("home.kind.play", "Play"),
      liturgy: t("home.kind.liturgy", "Prayer"),
      document: t("home.kind.document", "Document"),
    };
    return kinds[reader.kind] || t("home.kind.text", "Text");
  }

  function partsOf(reader) {
    return (reader.chapters && reader.chapters.length) || reader.sections || 1;
  }

  // The share of a text's parts the reader has finished, 0 to 1, off `targum:docs`.
  function progress(reader, docs) {
    var record = reader.document ? docs[reader.document] : null;
    if (!record) return 0;
    var total = partsOf(reader);
    if (record.sections && typeof record.sections === "object") {
      var done = 0;
      Object.keys(record.sections).forEach(function (part) {
        if (record.sections[part]) done += 1;
      });
      return Math.min(1, done / total);
    }
    return record.done ? 1 : 0;
  }

  function clock(seconds) {
    var whole = Math.max(0, Math.floor(seconds));
    var m = Math.floor(whole / 60);
    var s = whole % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  // Which part a place is in, counted from one: a book's chapter by its number, a long
  // text's section as the reader numbers it.
  function partNumber(reader, place) {
    var section = String((place && place.section) || "");
    if (!section) return 0;
    var chapters = reader.chapters || [];
    for (var i = 0; i < chapters.length; i++) {
      if (String(chapters[i].number) === section) return i + 1;
    }
    return /^\d+$/.test(section) ? Number(section) : 0;
  }

  /* --- where the reader left off ----------------------------------------------------- */

  /* The account's places and this browser's, newest per text. A place the account has and
     this browser does not is kept here too, as the contents page keeps it
     (targum-internal#430): the reader puts the reader back on its sentence and its second
     from this browser's copy, so a card that opens a part must find it here. */
  function mergePlaces(theirs) {
    var all = stored(PLACES);
    var touched = false;
    (theirs || []).forEach(function (row) {
      if (!row || !row.hash || !row.section) return;
      var mine = all[row.hash];
      if (mine && Number(mine.at || 0) >= Number(row.at || 0)) return;
      all[row.hash] = {
        section: String(row.section),
        path: row.path || "",
        segment: row.segment || "",
        seconds: Number(row.seconds || 0),
        at: Number(row.at || 0),
        title: row.title || "",
        language: row.language || "",
      };
      touched = true;
    });
    if (touched) {
      try {
        window.targumKeep(PLACES, JSON.stringify(all));
      } catch (e) {}
    }
    return Object.keys(all)
      .map(function (hash) {
        var place = all[hash] || {};
        return {
          hash: hash,
          section: String(place.section || ""),
          path: place.path || "",
          seconds: Number(place.seconds || 0),
          at: Number(place.at || 0),
          title: place.title || "",
          language: place.language || "",
        };
      })
      .sort(function (a, b) {
        return b.at - a.at;
      });
  }

  function accountPlaces() {
    return ask("/account/places?limit=" + CONTINUE_AT_MOST * 2)
      .then(function (answer) {
        return (answer && answer.places) || [];
      })
      .catch(function () {
        // Signed out, or the box went away: this browser's own places are all there is.
        return [];
      });
  }

  /* --- Continue ------------------------------------------------------------------------ */

  /* What Continue holds, newest first: the reader's places, then the texts this browser
     opened before there were places, then what they uploaded and have not opened, and
     builds still running. One card a text. */
  function gatherContinue(readers, places, building, opened, code) {
    var byDocument = {};
    readers.forEach(function (reader) {
      if (reader.document) byDocument[reader.document] = reader;
    });
    var seen = {};
    var cards = [];
    function inCode(language) {
      return !code || !language || shelf.base(language) === code;
    }
    places.forEach(function (place) {
      if (seen[place.hash]) return;
      var reader = byDocument[place.hash];
      if (!reader && !place.path) return;
      var language = reader ? reader.language : place.language;
      if (!inCode(language)) return;
      seen[place.hash] = true;
      cards.push({ at: place.at, reader: reader || null, place: place });
    });
    readers.forEach(function (reader) {
      if (!reader.document || seen[reader.document] || !inCode(reader.language)) return;
      var when = opened[reader.document] || 0;
      var upload = !reader.entry && !reader.shared;
      // An upload counts from when it arrived, opened or not: what you brought is what
      // you came back for.
      var at = Math.max(when, upload ? (reader.built || 0) * 1000 : 0);
      if (!at) return;
      seen[reader.document] = true;
      cards.push({ at: at, reader: reader, place: null });
    });
    building.forEach(function (job) {
      if (!inCode(job.language)) return;
      cards.push({ at: Number(job.made || 0) * 1000 || Date.now(), job: job });
    });
    cards.sort(function (a, b) {
      // A build first: it is the newest thing there is, and the one being waited on.
      if (!!a.job !== !!b.job) return a.job ? -1 : 1;
      return b.at - a.at;
    });
    return cards.slice(0, CONTINUE_AT_MOST);
  }

  // The folder a reader's address names: `/reader/<name>/…`, for a place whose text is
  // not on the shelf this page was handed.
  function folderOf(path) {
    var found = /^\/reader\/([^/?#]+)/.exec(String(path || ""));
    if (!found) return "";
    try {
      return decodeURIComponent(found[1]);
    } catch (e) {
      return found[1];
    }
  }

  function coverFor(reader, title, language, path) {
    return covers.picture(reader || { name: folderOf(path), title: title, language: language }, {
      keyed: keyed,
    });
  }

  function tag(text, kind) {
    return el("span", "home-tag" + (kind ? " is-" + kind : ""), text);
  }

  function bar(share, building) {
    var line = el("span", "home-bar" + (building ? " is-building" : ""));
    line.setAttribute("aria-hidden", "true");
    var fill = el("span", "home-fill");
    fill.style.setProperty("--done", String(Math.max(0, Math.min(1, share))));
    line.appendChild(fill);
    return line;
  }

  function titled(text, language) {
    var title = el("bdi", "home-card-title", text);
    title.setAttribute("lang", language || "und");
    return title;
  }

  function textCard(card, docs) {
    var reader = card.reader || {
      title: card.place.title,
      language: card.place.language,
      document: card.place.hash,
    };
    var place = card.place;
    var item = el("li", "home-card");
    var link = el("a", "home-card-open");
    var href = place && place.path ? place.path : "/reader/" + encodeURIComponent(reader.name) + "/reader/index.html";
    link.href = keyed(href);
    item.appendChild(coverFor(card.reader, reader.title, reader.language, place && place.path));

    var total = partsOf(reader);
    var at = partNumber(reader, place);
    var what = kindWord(reader);
    if (total > 1 && at) what = t("home.card.part-of", "{kind} · part {n} of {total}", { kind: what, n: at, total: total });
    var upload = card.reader && !card.reader.entry && !card.reader.shared;
    item.appendChild(tag(upload ? t("home.card.uploaded", "Uploaded by you") : what));

    link.appendChild(titled(reader.title, reader.language));
    item.appendChild(link);

    var facts = [];
    if (upload) facts.push(what);
    if (typeof reader.known === "number" && reader.words && reader.known > 0) {
      facts.push(t("home.card.known", "You know {share}%", { share: Math.round(reader.known * 100) }));
    }
    if (!place && card.reader && !(stored("targum:opened")[reader.document] || 0)) {
      facts.push(t("home.card.not-opened", "Not opened yet"));
    }
    if (facts.length) item.appendChild(el("span", "home-card-facts", facts.join(" · ")));
    var share = progress(reader, docs);
    item.appendChild(bar(share));

    var go;
    var medium = mediumOf(reader);
    if (place && place.seconds > 0 && medium !== "read") {
      go = t("home.card.pick-up-at-time", "Pick up at {time}", { time: clock(place.seconds) });
    } else if (place && total > 1 && at) {
      go = t("home.card.pick-up-at-part", "Pick up at part {n}", { n: at });
    } else if (place || (card.reader && stored("targum:opened")[reader.document])) {
      // Opened before there were places: the reader keeps its own place on the page.
      go = t("home.card.pick-up", "Pick up");
    } else {
      go = {
        read: t("home.card.read", "Read"),
        listen: t("home.card.listen", "Listen"),
        watch: t("home.card.watch", "Watch"),
      }[medium];
    }
    var press = el("span", "home-card-go", go);
    press.setAttribute("aria-hidden", "true");
    item.appendChild(press);
    // The link says the whole of it to a screen reader: what, and where it picks up.
    link.setAttribute("aria-label", reader.title + " — " + go);
    return item;
  }

  function buildCard(job) {
    var item = el("li", "home-card is-building");
    item.setAttribute("role", "status");
    item.appendChild(coverFor(null, job.title, job.language));
    item.appendChild(tag(t("home.card.getting-ready", "Uploaded · getting ready"), "building"));
    item.appendChild(titled(job.title, job.language));
    var facts = [];
    if (job.total > 1) {
      facts.push(t("shelf.building.share", "{n}% done", { n: Math.floor((job.done / job.total) * 100) }));
    }
    if (facts.length) item.appendChild(el("span", "home-card-facts", facts.join(" · ")));
    item.appendChild(bar(job.total > 0 ? job.done / job.total : 0.1, true));
    item.appendChild(el("span", "home-card-go is-waiting", t("home.card.opens-when-ready", "Opens when it’s ready")));
    return item;
  }

  /* A followed series' newest instalment, the first time this browser sees it: the first
     card, marked New, and a line in the bell, as Learn's sheet did (2026-09-11). Seen
     once it is pressed. Hebrew's: under another language these are not this page's. */
  function seriesCard(one) {
    var follow = window.TargumFollow;
    var inst = one.instalment;
    var item = el("li", "home-card is-new");
    var link = el("a", "home-card-open");
    link.href = keyed(follow.readerOf(one));
    var title = inst.hebrew || inst.title;
    item.appendChild(coverFor(null, title, "he", follow.readerOf(one)));
    item.appendChild(tag(t("home.card.new-from", "New · {name}", { name: one.name }), "new"));
    link.appendChild(titled(title, inst.hebrew ? "he" : "und"));
    item.appendChild(link);
    var when = /\d/.test(title || "") ? "" : follow.whenSaid(inst.when);
    if (when) item.appendChild(el("span", "home-card-facts", when));
    var go = t("home.card.read", "Read");
    item.appendChild(el("span", "home-card-go", go));
    link.setAttribute("aria-label", title + " — " + go);
    link.addEventListener("click", function () {
      follow.markSeen(one.id, inst.id);
    });
    return item;
  }

  /* What a subscription brought and the reader has not opened from here (design.md §12,
     "A subscription is the account's, and what it brings comes under Continue",
     2026-10-09): first, marked New and named by what it came from. A series' instalment
     or a video that got ready by itself opens as its text; a news article is a link to
     the Upload page with its address in the box. Opening one says so to the account, so
     it is New on no device after. */
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

  function newCard(item) {
    var name = item.kind === "topic" ? topicName(item.topic) : item.name;
    var card = el("li", "home-card is-new");
    var link = el("a", "home-card-open");
    link.href = keyed(item.door);
    var reader = /^\/reader\//.test(item.door) ? null : undefined;
    card.appendChild(coverFor(reader, item.title, item.language, item.door));
    card.appendChild(tag(t("home.card.new-from", "New · {name}", { name: name }), "new"));
    link.appendChild(titled(item.title, item.language));
    card.appendChild(link);
    var facts = [];
    if (item.seconds > 0) facts.push(t("home.minutes", "{n} min", { n: Math.max(1, Math.round(item.seconds / 60)) }));
    if (facts.length) card.appendChild(el("span", "home-card-facts", facts.join(" · ")));
    var go = {
      channel: t("home.card.watch", "Watch"),
      podcast: t("home.card.listen", "Listen"),
    }[item.kind] || t("home.card.read", "Read");
    card.appendChild(el("span", "home-card-go", go));
    link.setAttribute("aria-label", item.title + " — " + go);
    link.addEventListener("click", function () {
      seen(item);
    });
    return card;
  }

  function seen(item) {
    try {
      fetch(keyed("/subscriptions/seen"), {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: keyHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ subscription: item.subscription, key: item.key }),
      }).catch(function () {});
    } catch (e) {}
  }

  //: How many New cards lead Continue at most.
  var NEW_AT_MOST = 2;

  function drawContinue(cards, fresh, brought) {
    var host = document.getElementById("continue");
    var list = document.getElementById("continue-cards");
    if (!host || !list) return;
    list.textContent = "";
    var docs = stored("targum:docs");
    (brought || []).slice(0, NEW_AT_MOST).forEach(function (item) {
      list.appendChild(newCard(item));
    });
    (fresh || []).slice(0, 1).forEach(function (one) {
      list.appendChild(seriesCard(one));
    });
    cards.slice(0, CONTINUE_AT_MOST - list.children.length).forEach(function (card) {
      list.appendChild(card.job ? buildCard(card.job) : textCard(card, docs));
    });
    host.hidden = !list.children.length;
  }

  /* --- one to try next ------------------------------------------------------------------ */

  // What this reader has finished, by catalogue id, so it is not suggested again.
  function finished(readers) {
    var docs = stored("targum:docs");
    var ids = [];
    readers.forEach(function (reader) {
      if (reader.entry && progress(reader, docs) >= 1 && ids.indexOf(reader.entry) < 0) ids.push(reader.entry);
    });
    return ids;
  }

  function drawTry(row, first) {
    var host = document.getElementById("try-next");
    if (!host) return;
    host.textContent = "";
    if (!row || !row.id) {
      host.hidden = true;
      return;
    }
    var reader = {
      id: row.id,
      entry: row.id,
      title: row.title,
      language: row.language || "he",
      kind: row.kind,
      register: row.register,
      drawn: row.drawn,
    };
    host.appendChild(coverFor(reader, row.title, row.language));
    var what = el("div", "try-what");
    what.appendChild(
      el("p", "home-label", first ? t("home.try.first", "One to start with") : t("home.try.next", "One to try next"))
    );
    what.appendChild(titled(row.title, row.language || "he"));
    var facts = [];
    if (row.because) facts.push(row.because);
    if (row.minutes) facts.push(t("home.minutes", "{n} min", { n: row.minutes }));
    if (facts.length) what.appendChild(el("p", "home-card-facts", facts.join(" · ")));
    var open = el("a", "try-open", t("home.try.open", "Open it"));
    // targum-internal#313: the press opens the text, not the library row.
    open.href = keyed(row.reader || "/open/" + encodeURIComponent(row.id));
    what.appendChild(open);
    host.appendChild(what);
    host.hidden = false;
  }

  function suggest(code, readers, first) {
    var skip = finished(readers);
    ask(
      "/suggest?language=" +
        encodeURIComponent(code) +
        (skip.length ? "&skip=" + encodeURIComponent(skip.join(",")) : "")
    )
      .then(function (got) {
        drawTry(got && got.suggestion, first);
      })
      .catch(function () {
        drawTry(null, first);
      });
  }

  /* --- the arrival ------------------------------------------------------------------------ */

  /* A reader who has opened nothing and answered nothing is asked the arrival's questions
     first, on their own page (`/welcome`). Only Hebrew asks them; the page there says the
     last word and sends anybody it has nothing to ask back here. */
  function arriving(me, readers, places, code) {
    if (code !== "he") return false;
    try {
      if (window.sessionStorage.getItem(ARRIVAL_OVER)) return false;
    } catch (e) {
      return false;
    }
    var answered = "";
    try {
      answered = localStorage.getItem("targum:arrived") || "";
    } catch (e) {
      answered = "";
    }
    if (answered || (me && me.signedIn && (me.interest || []).length)) return false;
    if (Object.keys(stored("targum:opened")).length || places.length) return false;
    return !readers.some(function (reader) {
      return !reader.shared;
    });
  }

  /* --- putting it together ------------------------------------------------------------------ */

  var me = ask("/account/me").catch(function () {
    return null;
  });

  /* Called by `yours.js` once it has the shelf, in the language the menu is on, and again
     each time the menu moves. `readers` is everything of the reader's own and every shared
     text this browser has opened; `building` the builds still running. */
  var first = true;
  var placed = null;
  var brought = null;
  // Asked once a language and kept for the visit: `yours.js` draws again every few
  // seconds while something builds, and the series and the suggestion do not move.
  var seriesIn = {};
  var suggestedIn = {};
  var rang = {};
  function draw(code, readers, building) {
    var opened = stored("targum:opened");
    var follow = window.TargumFollow;
    // The account's subscriptions first; signed out, this browser's follows as before.
    brought = brought || ask("/subscriptions/new.json").catch(function () {
      return null;
    });
    if (!seriesIn[code]) {
      seriesIn[code] = brought.then(function (answer) {
        if (answer && answer.signedIn) return [];
        return code === "he" && follow ? follow.list() : [];
      });
    }
    var sawSeries = seriesIn[code];
    placed = placed || accountPlaces();
    return Promise.all([me, placed, sawSeries, brought]).then(function (all) {
      var who = all[0];
      var places = mergePlaces(all[1]);
      // Only from a page a server is behind: off the disk there is no `/welcome`.
      var served = !window.location.protocol || /^https?:$/.test(window.location.protocol);
      if (first && served && arriving(who, readers, places, code)) {
        window.location.replace(keyed("/welcome"));
        return false;
      }
      first = false;
      var fresh = follow && code === "he" ? follow.fresh(all[2]) : [];
      var mine = ((all[3] && all[3].items) || []).filter(function (item) {
        return shelf.base(item.language) === code;
      });
      var cards = gatherContinue(readers, places, building, opened, code);
      drawContinue(cards, fresh, mine);
      var nothing = !cards.length && !fresh.length && !mine.length;
      var empty = document.getElementById("first-home");
      if (empty) empty.hidden = !nothing;
      if (suggestedIn[code] !== nothing) {
        suggestedIn[code] = nothing;
        suggest(code, readers, nothing);
      }
      if (mine.length && !rang["subs:" + code]) {
        rang["subs:" + code] = true;
        mine.forEach(function (item) {
          var notices = window.TargumNotices;
          if (!notices || !notices.note) return;
          var name = item.kind === "topic" ? topicName(item.topic) : item.name;
          var line = name + ": " + item.title;
          if (notices.bdi) {
            line = document.createDocumentFragment();
            line.appendChild(notices.bdi(name));
            line.appendChild(document.createTextNode(": "));
            line.appendChild(notices.bdi(item.title));
          }
          notices.note("sub:" + item.subscription + ":" + item.key, line, {
            href: keyed(item.door),
            label: t("home.open", "Open"),
          });
        });
      }
      if (follow && fresh.length && !rang[code]) {
        rang[code] = true;
        fresh.forEach(function (one) {
          var notices = window.TargumNotices;
          if (!notices || !notices.note) return;
          var line = one.name + ": " + (one.instalment.hebrew || one.instalment.title);
          if (notices.bdi) {
            // Each name in the bell's own isolate (2026-10-06).
            line = document.createDocumentFragment();
            line.appendChild(notices.bdi(one.name));
            line.appendChild(document.createTextNode(": "));
            line.appendChild(notices.bdi(one.instalment.hebrew || one.instalment.title));
          }
          notices.note("series:" + one.id + ":" + one.instalment.id, line, {
            href: keyed(one.page || follow.readerOf(one)),
            label: t("home.open", "Open"),
          });
        });
      }
      return true;
    });
  }

  // The upload card's address carries the key on a machine somebody runs themselves.
  Array.prototype.forEach.call(document.querySelectorAll("[data-home-link]"), function (link) {
    link.href = keyed(link.getAttribute("href"));
  });

  window.TargumHome = {
    draw: draw,
    // For the tests: what Continue would hold, without the page.
    gather: gatherContinue,
    language: function () {
      return lang && lang.current ? lang.current(lang.learning ? lang.learning() : ["he"]) : "he";
    },
  };
})();
