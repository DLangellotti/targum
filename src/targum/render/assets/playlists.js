/* Your playlists (targum-internal#364), the Playlists tab of Your targums, and one
 * playlist on its own page (targum-internal#434; boards PlaylistsTab and PlaylistDetail).
 *
 * Three jobs on one page, chosen by the address:
 *
 *  - `/playlists?add=<name>&title=<title>` — the address a shelf row's "Add to playlist"
 *    and a reader's ⋯ menu both open where no script can — is the sheet: every playlist
 *    a button, and a new one a name.
 *  - `/playlists` is the tab: each playlist a card with a cover made of its first four
 *    texts, whose hand made it, how long it is, how much of it the reader knows, and the
 *    one they are in marked. targum's own sets stand under it.
 *  - `/playlists/<id>` is one playlist: its texts in order, moved by a drag, by Alt+↑/↓,
 *    or by the Move up and Move down keys, and taken out one at a time.
 *
 * The server keeps every playlist and answers with the whole of one after each change,
 * so nothing here works out what a playlist now holds.
 */

(function () {
  "use strict";

  var t = window.TargumStrings.t;
  var tn = window.TargumStrings.tn;
  var key = window.TARGUM_KEY;
  var covers = window.TargumCovers;

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  /* An item opened from its playlist carries the list and its place in it, so the
     reader draws Next and Back (targum-internal#366). Never `go`: opening one from here
     is not a swipe, and it plays nothing until pressed. */
  function listed(path, id, position) {
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "list=" + id + "&at=" + position;
  }

  var UNREACHED = t("playlists.unreached", "We couldn't reach targum. Try again in a moment.");
  var FAILED = t("playlists.failed", "We couldn't do that. Try again.");
  var GONE = t("playlists.gone", "We couldn't find that playlist.");

  /* What the server said, as a line for the reader. A refusal written for a reader
     ("A playlist holds up to 20 texts.") is passed on; the protocol's own words — "not
     found", "bad request" — never reach the page (2026-09-24). */
  function plainly(answer) {
    var said = String((answer && answer.error) || "");
    if (!said) return "";
    if (answer.status === 0) return UNREACHED;
    if (answer.status === 404 || /^not found$/i.test(said)) return GONE;
    if (/^bad request$/i.test(said) || answer.status >= 500) return FAILED;
    return said;
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: key
        ? { "Content-Type": "application/json", "X-Targum-Key": key }
        : { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json().then(function (answer) {
        answer = answer || {};
        answer.status = response.status;
        return answer;
      });
    }).catch(function () {
      // No server behind the page, or none reachable: said as an error the page shows,
      // never thrown, so nothing below this stops running.
      return { error: UNREACHED, status: 0 };
    });
  }

  function at(id) {
    return document.getElementById(id);
  }

  function say(where, message, bad) {
    var node = at(where);
    node.hidden = !message;
    node.textContent = message || "";
    node.classList.toggle("bad", !!bad);
  }

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // §13's three kinds: tonal for the ordinary press, ghost for moving and taking away.
  // A view's one filled press is Confirm on the tab and Continue on a playlist.
  function button(label, onPress, kind) {
    var press = element("button", kind || "tonal", label);
    press.type = "button";
    press.onclick = onPress;
    return press;
  }

  // A line drawing at the size of the text beside it: `paths` are 16×16 strokes.
  function drawing(paths, className) {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", "pl-glyph" + (className ? " " + className : ""));
    paths.forEach(function (d) {
      var path = document.createElementNS(ns, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }
  var GRIP = ["M3 5h10", "M3 8h10", "M3 11h10"];
  var PLUS = ["M8 3.5v9", "M3.5 8h9"];
  var CROSS = ["M4.5 4.5l7 7", "M11.5 4.5l-7 7"];
  var PLAYING = ["M4 6v4", "M8 4v8", "M12 6.5v3"];
  var BACK = ["M10 3.5L5.5 8l4.5 4.5"];

  // A name the reader typed, isolated in its own direction, so a Hebrew name's
  // punctuation stays on its own side of it.
  function isolated(text) {
    var bdi = document.createElement("bdi");
    bdi.setAttribute("dir", "auto");
    bdi.textContent = text;
    return bdi;
  }

  // A sentence with a name in it, the name isolated: "Add {title} to a playlist".
  function withName(node, said, name, value) {
    var cut = said.indexOf("{" + name + "}");
    if (cut < 0) {
      node.textContent = said;
      return node;
    }
    node.appendChild(document.createTextNode(said.slice(0, cut)));
    node.appendChild(isolated(value));
    node.appendChild(document.createTextNode(said.slice(cut + name.length + 2)));
    return node;
  }

  // A press named for a playlist: its name and its count, the name free to wrap.
  function named(one, onPress) {
    var press = button("", onPress);
    press.classList.add("named");
    var name = isolated(one.name);
    name.className = "name";
    press.appendChild(name);
    press.appendChild(element("span", "count", textCount(one.count)));
    return press;
  }

  /* --- what a playlist is, in words -------------------------------------------- */

  function textCount(n) {
    return tn("playlists.texts", n, "{n} text", "{n} texts");
  }

  // How long, the way a clock on a shelf says it: "48 min", "2 h 10 min".
  function length(seconds) {
    var minutes = Math.round(Number(seconds || 0) / 60);
    if (minutes <= 0) return "";
    if (minutes < 60) return t("playlists.minutes", "{n} min", { n: minutes });
    var hours = Math.floor(minutes / 60);
    var rest = minutes % 60;
    return rest
      ? t("playlists.hours-minutes", "{h} h {m} min", { h: hours, m: rest })
      : t("playlists.hours", "{h} h", { h: hours });
  }

  /* Whose hand made it (design.md §12, 2026-09-23: a playlist is the reader's, whoever
     made it). targum's own chat and targum's sets are targum; an assistant reached
     through the connector is "an assistant", without saying which one. */
  function byline(madeBy) {
    if (madeBy === "connector") return t("playlists.by-assistant", "From an assistant");
    if (madeBy === "targum" || madeBy === "chat") return t("playlists.by-targum", "From targum");
    return t("playlists.by-you", "By you");
  }

  // One word for what a text is, as home says it.
  function kindWord(facts) {
    if (!facts) return "";
    if (facts.video) return t("home.kind.video", "Video");
    var kinds = {
      article: t("home.kind.article", "Article"),
      talk: t("home.kind.talk", "Video"),
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
    return kinds[facts.kind] || t("home.kind.text", "Text");
  }

  function itemSeconds(facts) {
    if (!facts) return 0;
    return Number(facts.seconds || 0) || Number(facts.minutes || 0) * 60;
  }

  /* How much of it the reader knows, in leaf (§4: green is progress), with its share
     written beside the bar. Nothing at all where nothing was measured: "0% known" and
     "not measured" are different claims. */
  function knownBar(share, className) {
    if (typeof share !== "number") return null;
    var whole = Math.round(share * 100);
    var box = element("span", "pl-known" + (className ? " " + className : ""));
    var bar = element("span", "pl-bar");
    bar.setAttribute("aria-hidden", "true");
    var fill = element("span", "pl-fill");
    fill.style.setProperty("--done", String(Math.max(0, Math.min(1, share))));
    bar.appendChild(fill);
    box.appendChild(bar);
    box.appendChild(element("span", "pl-share", t("playlists.known", "{share}% known", { share: whole })));
    return box;
  }

  /* The cover: the first four texts' own pictures in a square (#429, design.md §12,
     "Every text has a picture"). A text still being made has no folder to draw from and
     rests on its letter; fewer than four leave the rest of the square empty. */
  function mosaic(cover, className) {
    var box = element("span", "pl-mosaic" + (className ? " " + className : ""));
    box.setAttribute("aria-hidden", "true");
    for (var n = 0; n < 4; n++) {
      var one = (cover || [])[n];
      if (!one) {
        box.appendChild(element("span", "pl-cell pl-empty"));
        continue;
      }
      var tile = covers
        ? covers.picture(
            { entry: one.name, title: one.title, language: one.language },
            { keyed: keyed, className: "thumb pl-cell" }
          )
        : element("span", "thumb pl-cell is-letter");
      box.appendChild(tile);
    }
    return box;
  }

  /* --- where this page is -------------------------------------------------------- */

  var query = new URLSearchParams(location.search);
  var adding = query.get("add") || "";
  var addingTitle = query.get("title") || adding;
  // `/playlists/<id>`, or `?playlist=<id>` where the page is opened off a disk.
  var opened = (function () {
    var path = /\/playlists\/(\d+)\/?$/.exec(location.pathname);
    if (path) return path[1];
    var asked = query.get("playlist") || "";
    return /^\d+$/.test(asked) ? asked : "";
  })();

  /* --- the sheet -------------------------------------------------------------- */

  function drawSheet(playlists) {
    if (!adding) return;
    at("adding").hidden = false;
    var head = at("adding-head");
    head.textContent = "";
    withName(head, t("playlists.add-to", "Add {title} to a playlist"), "title", addingTitle);
    var choose = at("choose");
    choose.textContent = "";
    playlists.forEach(function (one) {
      var item = document.createElement("li");
      item.appendChild(
        named(one, function () {
          addTo(one.id, one.name);
        })
      );
      choose.appendChild(item);
    });
    var first = choose.querySelector("button") || at("new-name");
    if (first) first.focus();
  }

  function added(name) {
    say("adding-said", t("playlists.added", "Added to {name}.", { name: name }));
    adding = "";
    // The address stops asking, so a reload does not offer the sheet again.
    history.replaceState(null, "", location.pathname + (key ? "?k=" + encodeURIComponent(key) : ""));
    at("choose").textContent = "";
    at("new-list").hidden = true;
    load();
  }

  function addTo(id, name) {
    ask("/playlists/" + id, { do: "add", reader: adding, title: addingTitle }).then(function (answer) {
      if (answer.error) return say("adding-said", plainly(answer), true);
      added(name);
    });
  }

  at("new-list").addEventListener("submit", function (event) {
    event.preventDefault();
    var name = at("new-name").value.trim();
    var body = { name: name };
    if (adding) {
      body.reader = adding;
      body.title = addingTitle;
    }
    ask("/playlists", body).then(function (answer) {
      if (answer.error) return say(adding ? "adding-said" : "lists-said", plainly(answer), true);
      say("lists-said", "");
      at("new-name").value = "";
      if (adding) return added(answer.name);
      at("adding").hidden = true;
      load();
    });
  });

  /* New playlist, from the tab's strip or its last card: the name field, in the sheet's
     panel, with the heading saying what it is for. */
  function startNew() {
    at("adding").hidden = false;
    at("adding-head").textContent = t("playlists.new-heading", "Name your playlist");
    at("choose").textContent = "";
    at("new-list").hidden = false;
    at("new-name").focus();
  }
  at("new-press").addEventListener("click", startNew);

  /* --- targum's own (targum-internal#368) --------------------------------------- */

  /* Opening one copies it into the reader's playlists, or finds the copy they have, and
     goes to its first text. Nothing is claimed: every text in it is built already. The
     first text opens as any list item does from this page, without `go`. */
  function openSet(one) {
    ask("/playlists/targum/" + encodeURIComponent(one.id), {}).then(function (answer) {
      if (answer.error) return say("targum-said", plainly(answer), true);
      say("targum-said", "");
      var first = (answer.items || []).filter(function (item) {
        return item.open;
      })[0];
      if (!first) return load();
      location.href = keyed(listed(first.open, answer.id, first.position));
    });
  }

  function drawTargum(sets) {
    var holder = at("targum-sets");
    holder.textContent = "";
    at("from-targum").hidden = !sets.length;
    sets.forEach(function (one) {
      var item = element("li", "pl-targum-card");
      item.appendChild(mosaic(one.covers, "is-small"));
      var what = element("span", "pl-targum-what");
      var name = element("span", "pl-targum-name");
      name.appendChild(isolated(one.name));
      what.appendChild(name);
      var facts = [];
      if (one.english && one.english !== one.name) facts.push(one.english);
      facts.push(textCount(one.count));
      if (one.seconds) facts.push(length(one.seconds));
      what.appendChild(element("span", "pl-facts", facts.join(" · ")));
      var known = knownBar(one.known);
      if (known) what.appendChild(known);
      item.appendChild(what);
      var press = button(t("playlists.open", "Open"), function () {
        openSet(one);
      });
      press.setAttribute("aria-label", t("playlists.open-named", "Open {name}", { name: one.name }));
      item.appendChild(press);
      holder.appendChild(item);
    });
  }

  /* --- the tab: a card a playlist ---------------------------------------------- */

  function waitingLine(one) {
    if (one.unconfirmed) {
      var line = element("span", "pl-foot pl-waiting");
      line.appendChild(element("span", "pl-not-yet", t("playlists.not-confirmed", "Not confirmed yet")));
      // The set's own page is the press (design.md §12, 2026-09-23): this only goes there.
      var go = element("a", "pl-confirm");
      go.href = keyed("/set/" + one.id);
      go.textContent = tn(
        "playlists.uses-credits",
        one.credits || 0,
        "Uses {n} credit · Confirm",
        "Uses {n} credits · Confirm"
      );
      line.appendChild(go);
      return line;
    }
    if (one.waiting) {
      return element(
        "span",
        "pl-foot pl-getting-ready",
        t("playlists.ready-of", "Getting ready · {ready} of {count} ready", {
          ready: one.ready || 0,
          count: one.count || 0,
        })
      );
    }
    return null;
  }

  /* Where the offline slice puts "Saved for offline" on a card and on a playlist's page
     (calmer surfaces, 2026-10-08: the playlist you are in saves itself). Nothing here
     yet: `window.TargumOffline`, when there is one, is handed the playlist and the place
     to draw in, and answers whether it drew. */
  function offlineSlot(one, where) {
    var offline = window.TargumOffline;
    if (!offline || !offline.playlist) return null;
    var slot = element("span", "pl-offline");
    return offline.playlist(one, slot, where) ? slot : null;
  }

  function card(one, current) {
    var box = element("article", "pl-card");
    var here = current && String(current.id) === String(one.id);
    if (here) box.classList.add("is-current");
    var picture = element("span", "pl-card-cover");
    picture.appendChild(mosaic(one.covers));
    if (here) {
      var chip = element("span", "pl-here");
      chip.appendChild(drawing(PLAYING));
      chip.appendChild(
        document.createTextNode(
          t("playlists.in-it", "You're in it · {at} of {count}", {
            at: Math.min(current.at + 1, one.count || 1),
            count: one.count || 0,
          })
        )
      );
      picture.appendChild(chip);
    }
    box.appendChild(picture);
    var title = element("h3", "pl-card-name");
    var open = element("a", "pl-card-open");
    open.href = keyed("/playlists/" + one.id);
    open.appendChild(isolated(one.name));
    title.appendChild(open);
    box.appendChild(title);
    var facts = [byline(one.made_by), textCount(one.count)];
    if (one.seconds) facts.push(length(one.seconds));
    box.appendChild(element("p", "pl-facts", facts.join(" · ")));
    var known = knownBar(one.known);
    if (known) box.appendChild(known);
    var foot = waitingLine(one) || offlineSlot(one, "card");
    if (foot) box.appendChild(foot);
    return box;
  }

  function newCard() {
    var press = element("button", "pl-card pl-new-card");
    press.type = "button";
    press.appendChild(drawing(PLUS));
    press.appendChild(element("span", "", t("playlists.new", "New playlist")));
    press.onclick = startNew;
    return press;
  }

  function drawTab(answer) {
    var playlists = answer.playlists || [];
    drawSheet(playlists);
    drawTargum(answer.targum || []);
    at("new-press").hidden = false;
    at("lists").hidden = false;
    at("none").hidden = playlists.length > 0;
    var holder = at("playlists");
    holder.textContent = "";
    playlists.forEach(function (one) {
      holder.appendChild(card(one, answer.current));
    });
    holder.appendChild(newCard());
  }

  /* --- one playlist ---------------------------------------------------------------- */

  // After a change the same text keeps the focus, at the place it moved to.
  var refocus = null;

  // A change that worked clears whatever an earlier one said went wrong.
  function change(id, body) {
    return ask("/playlists/" + id, body).then(function (answer) {
      say("one-said", answer.error ? plainly(answer) : "", !!answer.error);
      if (!answer.error && answer.items) return drawOne(answer);
      load();
    });
  }

  function move(one, position, to, focusOn) {
    if (to < 0 || to >= one.items.length || to === position) return;
    refocus = { position: to, which: focusOn || ".grip" };
    change(one.id, { do: "move", position: position, to: to });
  }

  /* A drag by the grip, for a mouse and a finger alike (pointer events, so a phone that
     has no HTML drag and drop still moves a row). The row travels with the pointer by
     taking its place among the others; nothing is animated, so reduced motion has
     nothing to stop. Let go where it started and nothing is sent. */
  function draggable(grip, row, list, one, position) {
    grip.addEventListener("pointerdown", function (event) {
      if (event.button !== 0 || one.items.length < 2) return;
      event.preventDefault();
      // Heard on the window, not captured by the grip: the row moves in the list as it
      // is dragged, and a moved element loses its capture.
      var pointer = event.pointerId;
      row.classList.add("is-dragged");
      list.classList.add("is-sorting");
      var to = position;
      function follow(moved) {
        if (moved.pointerId !== pointer) return;
        moved.preventDefault();
        var y = moved.clientY;
        var others = Array.prototype.filter.call(list.children, function (other) {
          return other !== row;
        });
        var before = null;
        for (var n = 0; n < others.length; n++) {
          var box = others[n].getBoundingClientRect();
          if (y < box.top + box.height / 2) {
            before = others[n];
            break;
          }
        }
        if (row.nextSibling !== before) list.insertBefore(row, before);
        to = Array.prototype.indexOf.call(list.children, row);
      }
      function done(cancelled) {
        window.removeEventListener("pointermove", follow);
        window.removeEventListener("pointerup", dropped);
        window.removeEventListener("pointercancel", cancel);
        row.classList.remove("is-dragged");
        list.classList.remove("is-sorting");
        if (cancelled || to === position) return drawOne(one);
        move(one, position, to);
      }
      function dropped(up) {
        if (up.pointerId === pointer) done(false);
      }
      function cancel(up) {
        if (up.pointerId === pointer) done(true);
      }
      window.addEventListener("pointermove", follow);
      window.addEventListener("pointerup", dropped);
      window.addEventListener("pointercancel", cancel);
    });
  }

  function drawItem(list, one, item, here) {
    var position = item.position;
    var last = position === one.items.length - 1;
    var facts = item.facts;
    var row = element("li", "item" + (item.failed ? " failed" : ""));
    row.setAttribute("data-position", String(position));
    if (here) row.classList.add("is-here");

    var mark = element("span", "item-mark");
    if (here) mark.appendChild(drawing(PLAYING));
    else mark.textContent = String(position + 1);
    row.appendChild(mark);

    var grip = element("button", "grip");
    grip.type = "button";
    grip.appendChild(drawing(GRIP));
    grip.setAttribute(
      "aria-label",
      t("playlists.reorder", "Move {title}. Drag, or press Alt with ↑ or ↓.", { title: item.title })
    );
    grip.title = t("playlists.reorder-hint", "Drag to move, or Alt+↑/↓");
    draggable(grip, row, list, one, position);
    row.appendChild(grip);

    row.appendChild(
      covers
        ? covers.picture(
            {
              entry: (facts && (facts.entry || facts.name)) || item.reader || "",
              title: item.title,
              language: facts && facts.language,
            },
            { keyed: keyed, className: "thumb pl-thumb" }
          )
        : element("span", "thumb pl-thumb is-letter")
    );

    var what = element("span", "item-what");
    var name;
    if (item.open) {
      name = element("a", "item-title");
      name.href = keyed(listed(item.open, one.id, position));
    } else {
      name = element("span", "item-title");
    }
    var title = isolated(item.title);
    if (facts && facts.language) title.setAttribute("lang", facts.language);
    name.appendChild(title);
    what.appendChild(name);
    var under = element("span", "item-kind");
    if (here) {
      under.classList.add("is-here");
      under.textContent = t("playlists.you-are-here", "You're here");
    } else if (!item.open) {
      under.textContent = item.failed
        ? t("playlists.could-not", "We couldn't get this text ready.")
        : t("playlists.getting-ready", "Getting ready");
      under.classList.add("item-state");
    } else {
      under.textContent = kindWord(facts);
    }
    // On a phone the columns fold into this line (board PlaylistDetailPhone).
    var folded = [];
    if (itemSeconds(facts)) folded.push(length(itemSeconds(facts)));
    if (facts && typeof facts.known === "number") {
      folded.push(t("playlists.known", "{share}% known", { share: Math.round(facts.known * 100) }));
    }
    if (folded.length) {
      under.appendChild(element("span", "item-folded", " · " + folded.join(" · ")));
    }
    what.appendChild(under);
    row.appendChild(what);

    row.appendChild(element("span", "item-length", length(itemSeconds(facts))));
    var cell = element("span", "item-known");
    var known = knownBar(facts && facts.known, "is-row");
    if (known) cell.appendChild(known);
    row.appendChild(cell);

    var keys = element("span", "item-keys");
    var up = button("↑", function () {
      move(one, position, position - 1, ".item-keys .up");
    }, "ghost up");
    up.setAttribute("aria-label", t("playlists.move-up", "Move {title} up", { title: item.title }));
    up.disabled = position === 0;
    var down = button("↓", function () {
      move(one, position, position + 1, ".item-keys .down");
    }, "ghost down");
    down.setAttribute("aria-label", t("playlists.move-down", "Move {title} down", { title: item.title }));
    down.disabled = last;
    var out = button("", function () {
      change(one.id, { do: "drop", position: position });
    }, "ghost out");
    out.appendChild(drawing(CROSS));
    out.setAttribute("aria-label", t("playlists.take-out-named", "Remove {title}", { title: item.title }));
    out.title = t("playlists.take-out", "Remove");
    keys.appendChild(up);
    keys.appendChild(down);
    keys.appendChild(out);
    row.appendChild(keys);
    list.appendChild(row);
  }

  /* The rare presses, behind ⋯: Rename and Delete. Two presses to delete a whole
     playlist (2026-09-24): the first asks, and the same key then says so; it goes back
     to Delete if nothing is pressed for a few seconds or the focus leaves it. */
  function moreMenu(holder, one) {
    var wrap = element("span", "pl-more-wrap");
    var press = element("button", "ghost pl-more", "⋯");
    press.type = "button";
    press.setAttribute("aria-haspopup", "true");
    press.setAttribute("aria-expanded", "false");
    press.setAttribute("aria-label", t("playlists.more-named", "More for {name}", { name: one.name }));
    var menu = element("span", "pl-menu");
    menu.hidden = true;
    press.onclick = function () {
      menu.hidden = !menu.hidden;
      press.setAttribute("aria-expanded", String(!menu.hidden));
      if (!menu.hidden) menu.querySelector("button").focus();
    };
    menu.appendChild(
      button(t("playlists.rename", "Rename"), function () {
        rename(holder, one);
      }, "ghost")
    );
    var away = button(t("playlists.delete", "Delete"), function () {
      if (away.getAttribute("data-asking") === "1") {
        ask("/playlists/" + one.id, { do: "gone" }).then(function (answer) {
          if (answer.error) return say("one-said", plainly(answer), true);
          location.href = keyed("/playlists");
        });
        return;
      }
      away.setAttribute("data-asking", "1");
      away.textContent = t("playlists.delete-confirm", "Confirm delete");
      away.setAttribute(
        "aria-label",
        t("playlists.delete-confirm-named", "Confirm delete {name}", { name: one.name })
      );
      clearTimeout(away.settle);
      away.settle = setTimeout(calmDown, 5000);
    }, "ghost danger");
    function calmDown() {
      clearTimeout(away.settle);
      away.removeAttribute("data-asking");
      away.textContent = t("playlists.delete", "Delete");
      away.setAttribute("aria-label", t("playlists.delete-named", "Delete {name}", { name: one.name }));
    }
    away.addEventListener("blur", calmDown);
    away.setAttribute("aria-label", t("playlists.delete-named", "Delete {name}", { name: one.name }));
    menu.appendChild(away);
    menu.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      menu.hidden = true;
      press.setAttribute("aria-expanded", "false");
      press.focus();
    });
    wrap.appendChild(press);
    wrap.appendChild(menu);
    return wrap;
  }

  function rename(holder, one) {
    var form = element("form", "rename");
    var field = document.createElement("input");
    field.type = "text";
    field.maxLength = 80;
    field.value = one.name;
    field.dir = "auto";
    field.setAttribute("aria-label", t("playlists.rename", "Rename"));
    form.appendChild(field);
    var save = element("button", "tonal", t("playlists.save", "Save"));
    save.type = "submit";
    form.appendChild(save);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      change(one.id, { do: "rename", name: field.value });
    });
    field.addEventListener("keydown", function (event) {
      if (event.key === "Escape") drawOne(one);
    });
    holder.querySelector(".pl-name").replaceWith(form);
    field.focus();
    field.select();
  }

  function drawOne(one) {
    at("one").hidden = false;
    var body = at("one-body");
    body.textContent = "";
    var current = typeof one.at === "number" && one.at < one.items.length ? one.at : -1;

    var head = element("header", "pl-head playlist-head");
    head.appendChild(mosaic(one.covers, "is-large"));
    var said = element("div", "pl-head-what");
    said.appendChild(element("p", "pl-byline", byline(one.made_by)));
    var name = element("h2", "pl-name");
    name.id = "one-name";
    name.appendChild(isolated(one.name));
    said.appendChild(name);
    var line = element("p", "pl-facts");
    var facts = [textCount(one.items.length)];
    if (one.seconds) facts.push(length(one.seconds));
    line.appendChild(document.createTextNode(facts.join(" · ")));
    var known = knownBar(one.known);
    if (known) line.appendChild(known);
    said.appendChild(line);

    var presses = element("div", "pl-presses");
    var pickUp = current >= 0 && one.items[current] && one.items[current].open ? one.items[current] : null;
    var start =
      pickUp ||
      one.items.filter(function (item) {
        return item.open;
      })[0];
    if (start) {
      var go = element("a", "filled start");
      go.href = keyed(listed(start.open, one.id, start.position));
      go.textContent = pickUp
        ? t("playlists.continue-at", "Continue at {at} of {count}", {
            at: current + 1,
            count: one.items.length,
          })
        : t("playlists.start", "Start");
      presses.appendChild(go);
    }
    var waiting = waitingLine({
      id: one.id,
      unconfirmed: one.unconfirmed,
      credits: one.credits,
      waiting: one.waiting,
      ready: one.ready,
      count: one.items.length,
    });
    if (waiting) presses.appendChild(waiting);
    var offline = offlineSlot(one, "page");
    if (offline) presses.appendChild(offline);
    presses.appendChild(moreMenu(head, one));
    said.appendChild(presses);
    head.appendChild(said);
    body.appendChild(head);

    var list = element("ol", "pl-items items");
    list.setAttribute("aria-label", t("playlists.in-order", "Texts in order"));
    one.items.forEach(function (item) {
      drawItem(list, one, item, item.position === current);
    });
    // Alt+↑ and Alt+↓ move the row the focus is in, from any of its presses.
    list.addEventListener("keydown", function (event) {
      if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
      var row = event.target.closest && event.target.closest(".item");
      if (!row) return;
      event.preventDefault();
      var position = Number(row.getAttribute("data-position"));
      move(one, position, position + (event.key === "ArrowUp" ? -1 : 1), ".grip");
    });
    body.appendChild(list);
    if (!one.items.length) {
      body.appendChild(element("p", "note", t("playlists.empty", "Nothing in it yet.")));
    }

    var more = element("p", "pl-add");
    var add = element("a", "pl-add-link");
    add.href = keyed("/library");
    add.appendChild(drawing(PLUS));
    add.appendChild(document.createTextNode(t("playlists.add-from", "Add from Your targums or the Library")));
    more.appendChild(add);
    more.appendChild(element("span", "pl-cap", t("playlists.up-to", "Up to 20 texts")));
    body.appendChild(more);

    if (refocus) {
      var target = list.querySelector('.item[data-position="' + refocus.position + '"]');
      var press = target && (target.querySelector(refocus.which) || target.querySelector(".grip"));
      if (press && press.disabled) press = target.querySelector(".grip");
      if (press) press.focus();
      refocus = null;
    }
  }

  /* --- load ------------------------------------------------------------------------ */

  // The account button in the header asks who is here once sync has started, as it
  // does on every other desk page; without this it said "Sign in" to a signed-in reader.
  var synced = false;

  function arrived(answer, where) {
    if (answer.status === 0) {
      // Nothing answered: not the same as not being signed in.
      at(where === "one" ? "one" : "lists").hidden = false;
      say(where === "one" ? "one-said" : "lists-said", UNREACHED, true);
      return false;
    }
    if (answer.status === 401) {
      at("stranger").hidden = false;
      return false;
    }
    at("stranger").hidden = true;
    if (!synced && window.TargumSync) {
      synced = true;
      window.TargumSync.start();
    }
    return true;
  }

  if (opened) {
    document.body.classList.add("pl-one-open");
    at("tabs-row").hidden = true;
    at("back").href = keyed("/playlists");
    at("back").insertBefore(drawing(BACK), at("back").firstChild);
  }

  function load() {
    if (opened) {
      return ask("/playlists/" + opened + ".json").then(function (answer) {
        if (!arrived(answer, "one")) return;
        if (answer.error || !answer.items) {
          at("one").hidden = false;
          return say("one-said", plainly(answer) || GONE, true);
        }
        drawOne(answer);
      });
    }
    return ask("/playlists.json").then(function (answer) {
      if (!arrived(answer, "tab")) return;
      drawTab(answer);
    });
  }

  load();
})();
