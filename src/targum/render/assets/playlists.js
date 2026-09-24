/* Your playlists (targum-internal#364): texts kept in an order, to go through one after
 * another.
 *
 * Two jobs on one page. With `?add=<name>&title=<title>` — the address a shelf row's
 * "Add to playlist" and a reader's ⋯ menu both open — it is the sheet: every playlist a
 * button, and a new one a name. Below that, always, the playlists themselves, each with
 * its texts in order and the keys that move, take out, rename and take away.
 *
 * The server keeps every playlist and answers with the whole of one after each change,
 * so nothing here works out what a playlist now holds.
 */

(function () {
  "use strict";

  var t = window.TargumStrings.t;
  var tn = window.TargumStrings.tn;
  var key = window.TARGUM_KEY;

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

  // §13's three kinds: tonal for the ordinary press, ghost for moving and taking away.
  // The page's one filled press is Confirm, in the template.
  function button(label, onPress, kind) {
    var press = document.createElement("button");
    press.type = "button";
    press.className = kind || "tonal";
    press.textContent = label;
    press.onclick = onPress;
    return press;
  }

  // A name the reader typed, isolated in its own direction, so a Hebrew name's
  // punctuation stays on its own side of it.
  function isolated(text) {
    var bdi = document.createElement("bdi");
    bdi.setAttribute("dir", "auto");
    bdi.textContent = text;
    return bdi;
  }

  // A press named for a playlist: its name and its count, the name free to wrap.
  function named(one, onPress) {
    var press = button("", onPress);
    press.classList.add("named");
    var name = isolated(one.name);
    name.className = "name";
    press.appendChild(name);
    var count = document.createElement("span");
    count.className = "count";
    count.textContent = tn("playlists.texts", one.count, "{n} text", "{n} texts");
    press.appendChild(count);
    return press;
  }

  var query = new URLSearchParams(location.search);
  var adding = query.get("add") || "";
  var addingTitle = query.get("title") || adding;

  /* --- the sheet -------------------------------------------------------------- */

  function drawSheet(playlists) {
    if (!adding) return;
    at("adding").hidden = false;
    var head = at("adding-head");
    head.textContent = "";
    var said = t("playlists.add-to", "Add {title} to a playlist");
    var cut = said.indexOf("{title}");
    if (cut < 0) head.textContent = said;
    else {
      head.appendChild(document.createTextNode(said.slice(0, cut)));
      head.appendChild(isolated(addingTitle));
      head.appendChild(document.createTextNode(said.slice(cut + "{title}".length)));
    }
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
      load();
    });
  });

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
      var item = document.createElement("li");
      var press = named(one, function () {
        openSet(one);
      });
      press.setAttribute("aria-label", t("playlists.open-named", "Open {name}", { name: one.name }));
      item.appendChild(press);
      holder.appendChild(item);
    });
  }

  /* --- the playlists ------------------------------------------------------------ */

  // A change that worked clears whatever an earlier one said went wrong.
  function change(id, body) {
    return ask("/playlists/" + id, body).then(function (answer) {
      say("lists-said", answer.error ? plainly(answer) : "", !!answer.error);
      load();
    });
  }

  function drawItem(list, one, item, last) {
    var row = document.createElement("li");
    row.className = "item" + (item.failed ? " failed" : "");
    var name;
    if (item.open) {
      name = document.createElement("a");
      name.href = keyed(listed(item.open, one.id, item.position));
    } else {
      name = document.createElement("span");
    }
    name.className = "item-title";
    var title = document.createElement("bdi");
    title.setAttribute("dir", "auto");
    title.textContent = item.title;
    name.appendChild(title);
    row.appendChild(name);
    if (!item.open) {
      var state = document.createElement("span");
      state.className = "item-state";
      state.textContent = item.failed
        ? t("playlists.could-not", "Couldn't prepare this text.")
        : t("playlists.getting-ready", "Getting ready");
      row.appendChild(state);
    }
    var keys = document.createElement("span");
    keys.className = "item-keys";
    var up = button("↑", function () {
      change(one.id, { do: "move", position: item.position, by: -1 });
    }, "ghost");
    up.setAttribute("aria-label", t("playlists.move-up", "Move {title} up", { title: item.title }));
    up.disabled = item.position === 0;
    var down = button("↓", function () {
      change(one.id, { do: "move", position: item.position, by: 1 });
    }, "ghost");
    down.setAttribute("aria-label", t("playlists.move-down", "Move {title} down", { title: item.title }));
    down.disabled = last;
    var out = button(t("playlists.take-out", "Remove"), function () {
      change(one.id, { do: "drop", position: item.position });
    }, "ghost");
    out.setAttribute("aria-label", t("playlists.take-out-named", "Remove {title}", { title: item.title }));
    keys.appendChild(up);
    keys.appendChild(down);
    keys.appendChild(out);
    row.appendChild(keys);
    list.appendChild(row);
  }

  function drawPlaylist(one) {
    var box = document.createElement("section");
    box.className = "playlist";
    var head = document.createElement("div");
    head.className = "playlist-head";
    var name = document.createElement("h3");
    name.appendChild(isolated(one.name));
    head.appendChild(name);
    var start = one.items.filter(function (item) {
      return item.open;
    })[0];
    if (start) {
      var go = document.createElement("a");
      go.className = "tonal start";
      go.href = keyed(listed(start.open, one.id, start.position));
      go.textContent = t("playlists.start", "Start");
      head.appendChild(go);
    }
    head.appendChild(
      button(t("playlists.rename", "Rename"), function () {
        rename(box, one);
      })
    );
    // Two presses to delete a whole playlist (2026-09-24): the first asks, and the same
    // key then says so; it goes back to Delete if nothing is pressed for a few seconds or
    // the focus leaves it.
    var away = button(t("playlists.delete", "Delete"), function () {
      if (away.getAttribute("data-asking") === "1") {
        change(one.id, { do: "gone" });
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
    head.appendChild(away);
    box.appendChild(head);
    var list = document.createElement("ol");
    list.className = "items";
    one.items.forEach(function (item, index) {
      drawItem(list, one, item, index === one.items.length - 1);
    });
    box.appendChild(list);
    return box;
  }

  function rename(box, one) {
    var form = document.createElement("form");
    form.className = "rename";
    var field = document.createElement("input");
    field.type = "text";
    field.maxLength = 80;
    field.value = one.name;
    field.dir = "auto";
    field.setAttribute("aria-label", t("playlists.rename", "Rename"));
    form.appendChild(field);
    var save = document.createElement("button");
    save.type = "submit";
    save.className = "tonal";
    save.textContent = t("playlists.save", "Save");
    form.appendChild(save);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      change(one.id, { do: "rename", name: field.value });
    });
    field.addEventListener("keydown", function (event) {
      if (event.key === "Escape") load();
    });
    box.querySelector(".playlist-head").replaceWith(form);
    field.focus();
    field.select();
  }

  // The account button in the header asks who is here once sync has started, as it
  // does on every other desk page; without this it said "Sign in" to a signed-in reader.
  var synced = false;

  function load() {
    ask("/playlists.json").then(function (answer) {
      if (answer.status === 0) {
        // Nothing answered: not the same as not being signed in.
        at("lists").hidden = false;
        say("lists-said", UNREACHED, true);
        return;
      }
      if (answer.status === 401) {
        at("stranger").hidden = false;
        return;
      }
      at("stranger").hidden = true;
      if (!synced && window.TargumSync) {
        synced = true;
        window.TargumSync.start();
      }
      var playlists = answer.playlists || [];
      drawSheet(playlists);
      drawTargum(answer.targum || []);
      at("lists").hidden = false;
      at("none").hidden = playlists.length > 0;
      var holder = at("playlists");
      return Promise.all(
        playlists.map(function (one) {
          return ask("/playlists/" + one.id + ".json");
        })
      ).then(function (full) {
        holder.textContent = "";
        full.forEach(function (one) {
          if (one && one.items) holder.appendChild(drawPlaylist(one));
        });
      });
    });
  }

  load();
})();
