/* The library: what we have picked out, and what the reader has open.
 *
 * A picked text arrives with a translation somebody published, so opening one is only
 * a matter of fetching two texts and matching them up. Nothing about that is the
 * reader's business, and none of it belongs in what the page says.
 *
 * One language at a time. Someone reading Hebrew should not have to look past a
 * Russian novel to find their own shelf, and the language they pick here is the one
 * their words page opens on.
 */

(function () {
  "use strict";

  var key = window.TARGUM_KEY;
  /* Hosted there is no start-up key: the session cookie identifies the reader, and a key
     riding in every URL is a bearer token in browser history, on a shared screen, and in
     a Referer. Local it stays, because there it proves the page came from the terminal
     that started the process. Both cases are this one branch. */
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }
  var names = window.TARGUM_LANGUAGES || {};
  var catalogue = window.TARGUM_CATALOGUE || [];
  var lang = window.TargumLang;
  // What a text is, for the card. The catalogue is one list; these say which entries a
  // reader who wants only Jewish texts came for.
  var TAGS = { tanakh: "Tanakh", judaica: "Judaica" };

  function named(code) {
    return names[code] || (code || "").toUpperCase();
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  function post(path, body) {
    return ask(path, body).then(function (answer) {
      if (answer && answer.error) throw new Error(answer.error);
      return answer;
    });
  }

  function reload() {
    location.reload();
  }

  Array.prototype.forEach.call(document.querySelectorAll(".site-nav a"), function (link) {
    link.href = keyed(link.getAttribute("href"));
  });

  /* --- building one --------------------------------------------------------- */

  function entryFor(id) {
    for (var i = 0; i < catalogue.length; i++) if (catalogue[i].id === id) return catalogue[i];
    return null;
  }

  function build(card, entry) {
    var status = card.querySelector(".card-status");
    var button = card.querySelector("[data-build]");
    button.disabled = true;
    status.hidden = false;
    status.textContent = "Getting ready…";

    ask("/prepare", {
      source: entry.source,
      to: "en",
      from: entry.language,
      words: true,
      gloss: false,
      // Every published translation this text has. The reader switches between them.
      translations: entry.translations.map(function (t) {
        return t.source;
      }),
    })
      .then(function (job) {
        if (job.error) throw new Error(job.error);
        if (job.blocked) throw new Error(job.blocked);
        status.textContent = "Lining up…";
        return ask("/build", { id: job.id }).then(function () {
          return watch(job.id, status);
        });
      })
      .catch(function (problem) {
        status.textContent = String(problem.message || problem);
        button.disabled = false;
      });
  }

  // The pipeline narrates itself in its own words. This is the reader's.
  var PLAIN = {
    "Finding each word's dictionary form…": "Reading the words…",
    "Adding vowel points…": "Adding vowel points…",
    "Building the reader…": "Setting the page…",
  };

  function say(message) {
    if (!message) return "";
    if (PLAIN[message]) return PLAIN[message];
    if (message.indexOf("Matching") === 0) return "Lining up…";
    if (message.indexOf("Looking up") === 0) return "Looking words up…";
    return "Almost there…";
  }

  function watch(id, status) {
    return new Promise(function (resolve) {
      var timer = setInterval(function () {
        ask("/job/" + id).then(function (state) {
          if (state.error) {
            clearInterval(timer);
            status.textContent = state.error;
            resolve();
            return;
          }
          status.textContent = say(state.message) || "Almost there…";
          if (state.stage === "done") {
            clearInterval(timer);
            window.location.href = keyed("/reader/" + state.reader);
            resolve();
          }
        });
      }, 700);
    });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-build]") : null;
    if (!button) return;
    var card = button.closest(".card");
    var entry = entryFor(button.getAttribute("data-build"));
    if (entry) build(card, entry);
  });

  /* --- what you have already ------------------------------------------------ */

  function ago(stamp) {
    var minutes = Math.round((Date.now() - stamp) / 60000);
    if (minutes < 2) return "just now";
    if (minutes < 60) return minutes + " minutes ago";
    var hours = Math.round(minutes / 60);
    if (hours < 24) return hours === 1 ? "an hour ago" : hours + " hours ago";
    var days = Math.round(hours / 24);
    return days === 1 ? "yesterday" : days + " days ago";
  }

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  function base(code) {
    return (code || "").split("-")[0].toLowerCase();
  }

  /* --- the picked texts ------------------------------------------------------ */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function minutes(words) {
    return Math.max(1, Math.round(words / 130));
  }

  function card(entry) {
    var item = el("li", "card");
    item.setAttribute("data-entry", entry.id);

    var head = el("div", "card-head");
    var title = el("h3");
    title.setAttribute("lang", entry.language);
    var bdi = el("bdi", null, entry.title);
    title.appendChild(bdi);
    head.appendChild(title);
    // No language tag: the page is one language, and it says which at the top. What the
    // text *is* does go here, though — Tanakh and a novel share this list now, and the
    // reader who cares which is which is the one this tag exists for.
    var named = TAGS[(entry.tags || [])[0]];
    if (named) head.appendChild(el("span", "tag", named));
    item.appendChild(head);

    item.appendChild(el("p", "byline", entry.author));
    item.appendChild(el("p", "blurb", entry.blurb));
    item.appendChild(
      el("p", "facts", "about " + minutes(entry.words) + " minutes of reading")
    );

    var list = el("ul", "renderings");
    entry.translations.forEach(function (t) {
      var row = el("li");
      row.appendChild(el("b", null, t.name));
      if (t.note) row.appendChild(document.createTextNode(" — " + t.note));
      list.appendChild(row);
    });
    item.appendChild(list);

    var button = el("button", "go build", "Start reading");
    button.type = "button";
    button.setAttribute("data-build", entry.id);
    item.appendChild(button);

    var status = el("p", "card-status");
    status.hidden = true;
    item.appendChild(status);
    return item;
  }

  function drawPicked(code) {
    var host = document.getElementById("catalogue");
    var empty = document.getElementById("picked-empty");
    var note = document.getElementById("picked-note");
    host.textContent = "";
    var mine = catalogue.filter(function (entry) {
      return base(entry.language) === code;
    });
    mine.forEach(function (entry) {
      host.appendChild(card(entry));
    });
    empty.hidden = mine.length > 0;
    note.hidden = mine.length === 0;
    if (!mine.length) {
      empty.textContent =
        "Nothing picked out in " + named(code) + " yet.";
    }
  }


  function kept() {
    var found = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var name = localStorage.key(i) || "";
        if (name.indexOf("targum:vocab:") === 0) {
          found.push({ language: name.slice("targum:vocab:".length) });
        }
      }
    } catch (e) {}
    return found;
  }

  /* --- putting it together --------------------------------------------------- */

  ask("/readers").then(function (data) {
    var readers = data.readers || [];
    var trash = data.trash || [];
    var opened = stored("targum:opened");
    readers.forEach(function (reader) {
      reader.opened = opened[reader.document] || 0;
    });
    readers.sort(function (a, b) {
      return b.opened - a.opened || b.built * 1000 - a.built * 1000;
    });

    // Hebrew is always on offer, whether or not anything is on the shelf in it.
    //
    // The languages after it are the reader's own: what they have built, and what they
    // have kept words in. The catalogue deliberately does not add to this list. It
    // holds one Russian novel, and letting it in put Russian in front of every visitor
    // who had never touched it — which is the opposite of what this switcher is for,
    // and flatly against what lang.js says it does: someone who never touches another
    // language should never see a switcher at all. The catalogue is then shown filtered
    // to whichever language is chosen, the same as the shelf.
    var codes = [lang.HOME];
    readers.concat(kept()).forEach(function (thing) {
      var code = base(thing.language);
      if (code && codes.indexOf(code) < 0) codes.push(code);
    });
    codes = lang.order(codes, names);

    var chosen = lang.current(codes);
    var betaNote = document.getElementById("beta-note");

    function show(code) {
      chosen = code;
      lang.switcher(document.getElementById("langs"), codes, names, code, show);
      betaNote.hidden = !lang.beta(code);
      if (lang.beta(code)) betaNote.textContent = lang.betaNote(code, names);
      drawPicked(code);
    }

    show(chosen);

    // The shelf is sorted by when you last opened each text, and that is one of the
    // things the account keeps. Signing in on a second machine should therefore
    // reorder the shelf to match where you actually are in your reading.
    if (window.TargumSync) {
      window.TargumSync.onChange(function (changed) {
        if (!changed) return;
        var opened = stored("targum:opened");
        readers.forEach(function (reader) {
          reader.opened = opened[reader.document] || 0;
        });
        readers.sort(function (a, b) {
          return b.opened - a.opened || b.built * 1000 - a.built * 1000;
        });
        show(chosen);
      });
      window.TargumSync.start();
    }
  });
})();
