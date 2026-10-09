/* Add to a playlist, in place (targum-internal#364, 2026-09-24).
 *
 * "Why do I need to go to an entire new page to add a targum to a playlist, it should be
 * doable in a single dropdown." So a press on Add to playlist opens a small menu under
 * the press: the reader's playlists, one press each, and a name field for a new one.
 * The link underneath still goes to `/playlists?add=`, which is where a page with no
 * script, or a reader opened off a disk, ends up.
 *
 * Shared by the shelf (shelf.js) and the reader's ⋯ menu (reader.js), which is why it
 * takes its strings and its key from whoever calls it rather than from the page.
 */
(function () {
  "use strict";

  var open = null;

  function say(key, english, fill) {
    var strings = window.TargumStrings;
    return strings && strings.t ? strings.t(key, english, fill) : english.replace(/\{(\w+)\}/g, function (all, name) {
      return fill && name in fill ? String(fill[name]) : all;
    });
  }

  function sayCount(n) {
    var strings = window.TargumStrings;
    if (strings && strings.tn) return strings.tn("playlist-menu.texts", n, "{n} text", "{n} texts");
    return n === 1 ? "1 text" : n + " texts";
  }

  function address(path, key) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function ask(method, path, key, body) {
    var headers = { Accept: "application/json" };
    if (body) headers["Content-Type"] = "application/json";
    if (key) headers["X-Targum-Key"] = key;
    return fetch(address(path, key), {
      method: method,
      headers: headers,
      credentials: "same-origin",
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response
        .json()
        .catch(function () {
          return {};
        })
        .then(function (answer) {
          return { status: response.status, answer: answer };
        });
    });
  }

  // A phone's sheet rises from the foot over a dimmed page (board PlaylistMake); a desk's
  // menu hangs under its press, and its "New playlist" is a small window on the dim.
  function narrow() {
    return !!(window.matchMedia && window.matchMedia("(max-width: 40rem)").matches);
  }

  function close() {
    if (!open) return;
    open.menu.remove();
    if (open.scrim) open.scrim.remove();
    document.body.classList.remove("pm-sheet-open");
    open.press.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", outside, true);
    document.removeEventListener("keydown", escape, true);
    window.removeEventListener("scroll", scrolled, true);
    window.removeEventListener("resize", close);
    var press = open.press;
    open = null;
    press.focus();
  }

  function place(menu, press) {
    var at = press.getBoundingClientRect();
    var gutter = 8;
    var width = Math.min(menu.offsetWidth || 280, window.innerWidth - 2 * gutter);
    var rtl = getComputedStyle(press).direction === "rtl";
    var left = rtl ? at.left : at.right - width;
    left = Math.max(gutter, Math.min(left, window.innerWidth - width - gutter));
    var top = at.bottom + 6;
    var height = menu.offsetHeight;
    if (top + height > window.innerHeight - gutter && at.top - 6 - height > gutter) top = at.top - 6 - height;
    menu.style.left = left + "px";
    menu.style.top = top + "px";
  }

  // The page moving takes the menu away; its own list scrolling does not.
  function scrolled(event) {
    if (open && !open.menu.contains(event.target)) close();
  }

  function outside(event) {
    if (open && !open.menu.contains(event.target) && event.target !== open.press) close();
  }

  function escape(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  }

  /* One text into one playlist: an existing one by id, or a new one by name. */
  function add(menu, text, key, target) {
    var sent = target.id
      ? ask("POST", "/playlists/" + target.id, key, { do: "add", reader: text.name, title: text.title })
      : ask("POST", "/playlists", key, { name: target.name, reader: text.name, title: text.title });
    sent
      .then(function (got) {
        if (got.status >= 400) {
          // The server's own refusal where it wrote one for a reader ("A playlist holds
          // up to 20 texts."); a bare "not found" or "bad request" is protocol, not a
          // sentence, and is said as the plain failure.
          var why = got.answer && got.answer.error;
          if (got.status === 404 || got.status === 401 || /^(not found|bad request)$/i.test(String(why || ""))) why = "";
          status(menu, why || say("playlist-menu.failed", "We couldn't add it to the playlist."), true, again);
          return;
        }
        status(menu, say("playlist-menu.added", "Added to {name}.", { name: got.answer.name || target.name }));
        setTimeout(close, 900);
      })
      .catch(function () {
        status(menu, say("playlist-menu.failed", "We couldn't add it to the playlist."), true, again);
      });
    function again() {
      status(menu, "");
      add(menu, text, key, target);
    }
  }

  // A refusal is a line with the clay mark and Try again (design.md §12, 2026-10-09).
  function status(menu, words, bad, again) {
    var line = menu.querySelector(".pm-status");
    line.textContent = words;
    line.hidden = !words;
    line.classList.toggle("bad", !!bad);
    if (bad && words && window.TargumFault) {
      line.textContent = "";
      line.appendChild(window.TargumFault.line(words, "", again || null, true));
    }
  }

  /* A playlist's cover at the size of a row: its first four texts' pictures, from this
     box's `/thumb/`, each resting on its letter until it has loaded. The playlist page's
     mosaic, small; drawn here because a reader carries no `covers.js`. */
  function cover(one, key) {
    var box = document.createElement("span");
    var some = (one.covers || []).slice(0, 4);
    box.className = "pm-cover n-" + some.length;
    box.setAttribute("aria-hidden", "true");
    some.forEach(function (member) {
      var cell = document.createElement("span");
      cell.className = "pm-cell";
      var letter = document.createElement("span");
      letter.className = "pm-letter";
      letter.textContent = String(member.title || "").replace(/^[^\wא-תЀ-ӿ]+/, "").charAt(0);
      cell.appendChild(letter);
      if (member.name) {
        var picture = new Image();
        picture.alt = "";
        picture.onload = function () {
          letter.remove();
          cell.appendChild(picture);
        };
        picture.src = address("/thumb/" + encodeURIComponent(member.name) + "?drawn=1", key);
      }
      box.appendChild(cell);
    });
    return box;
  }

  function sayIn(node, said, title) {
    var cut = said.indexOf("{title}");
    if (cut < 0) {
      node.textContent = said;
      return node;
    }
    node.appendChild(document.createTextNode(said.slice(0, cut)));
    var name = document.createElement("bdi");
    name.setAttribute("dir", "auto");
    name.textContent = title;
    node.appendChild(name);
    node.appendChild(document.createTextNode(said.slice(cut + 7)));
    return node;
  }

  function draw(menu, text, key, playlists, current) {
    var list = menu.querySelector(".pm-list");
    list.textContent = "";
    playlists.forEach(function (one) {
      var item = document.createElement("li");
      var choose = document.createElement("button");
      choose.type = "button";
      choose.className = "pm-choice";
      choose.setAttribute("role", "menuitem");
      choose.appendChild(cover(one, key));
      var what = document.createElement("span");
      what.className = "pm-what";
      var name = document.createElement("bdi");
      name.setAttribute("dir", "auto");
      name.className = "pm-label";
      name.textContent = one.name;
      what.appendChild(name);
      var count = document.createElement("span");
      count.className = "pm-count";
      var facts = [sayCount(one.count)];
      if (current && String(current.id) === String(one.id)) {
        facts.push(say("playlist-menu.in-this-one", "you're in it"));
      }
      count.textContent = facts.join(" · ");
      what.appendChild(count);
      choose.appendChild(what);
      // Already in it: said at the row's end, and the row stays a press that adds it
      // again only if the reader wants a second copy — the server keeps both.
      if ((one.holds || []).indexOf(text.name) >= 0) {
        var held = document.createElement("span");
        held.className = "pm-in";
        held.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M3 8.5 6.5 12 13 4.5"></path></svg>';
        held.appendChild(document.createTextNode(say("playlist-menu.in-it", "In it")));
        choose.appendChild(held);
        choose.classList.add("is-in");
      }
      choose.onclick = function () {
        add(menu, text, key, one);
      };
      item.appendChild(choose);
      list.appendChild(item);
    });
    list.hidden = !playlists.length;
    if (open && open.menu === menu && !open.scrim) place(menu, open.press);
    var first = menu.querySelector(playlists.length ? ".pm-choice" : ".pm-name");
    if (first) first.focus();
  }

  function build(text, key, sheet) {
    var menu = document.createElement("div");
    menu.className = "playlist-menu" + (sheet ? " is-sheet" : "");
    // The interface's direction, not the page's: on a Hebrew reader the root reads right
    // to left, and the menu's English rows came out back to front ("texts 2 Kitchen").
    var strings = window.TargumStrings;
    var spoken = String((strings && strings.language) || document.documentElement.lang || "en").split("-")[0];
    menu.setAttribute("dir", /^(he|yi|ar|fa|ur|arc)$/.test(spoken) ? "rtl" : "ltr");
    menu.setAttribute("role", "dialog");
    menu.setAttribute("aria-label", say("playlist-menu.label", "Add to playlist"));
    if (sheet) {
      var grab = document.createElement("button");
      grab.type = "button";
      grab.className = "sheet-grab";
      grab.setAttribute("aria-label", say("playlist-menu.close", "Close"));
      grab.addEventListener("click", close);
      menu.appendChild(grab);
    }
    // "Add רות to" (board PlaylistMake), the title in its own direction.
    menu.appendChild(sayIn(document.createElement("p"), say("playlist-menu.add-to", "Add {title} to"), text.title)).className = "pm-head";

    var list = document.createElement("ul");
    list.className = "pm-list";
    list.setAttribute("role", "menu");
    list.hidden = true;
    menu.appendChild(list);

    // At a desk, New playlist is a row that opens its own small window; on a phone the
    // name field stands in the sheet itself (board PlaylistMake).
    var opener = document.createElement("button");
    opener.type = "button";
    opener.className = "pm-new-open";
    opener.textContent = say("playlist-menu.new", "New playlist");
    menu.appendChild(opener);

    var form = document.createElement("form");
    form.className = "pm-new";
    var top = document.createElement("div");
    top.className = "pm-new-top";
    var heading = document.createElement("h2");
    heading.className = "pm-new-title";
    heading.textContent = say("playlist-menu.new", "New playlist");
    top.appendChild(heading);
    var shut = document.createElement("button");
    shut.type = "button";
    shut.className = "pm-shut";
    shut.textContent = "×";
    shut.setAttribute("aria-label", say("playlist-menu.close", "Close"));
    shut.addEventListener("click", close);
    top.appendChild(shut);
    form.appendChild(top);
    var label = document.createElement("label");
    label.className = "pm-field-label";
    label.textContent = sheet ? say("playlist-menu.new", "New playlist") : say("playlist-menu.name", "Name");
    form.appendChild(label);
    var field = document.createElement("input");
    field.type = "text";
    field.className = "pm-name";
    field.maxLength = 80;
    field.dir = "auto";
    field.autocomplete = "off";
    field.placeholder = say("playlist-menu.name", "Name");
    field.setAttribute("aria-label", say("playlist-menu.new", "New playlist"));
    field.id = "pm-name-" + Math.random().toString(36).slice(2, 8);
    label.htmlFor = field.id;
    form.appendChild(field);
    // What it starts with: this text, its picture and its title.
    var starts = document.createElement("p");
    starts.className = "pm-starts";
    if (text.name) {
      var thumb = document.createElement("span");
      thumb.className = "pm-cover n-1";
      thumb.setAttribute("aria-hidden", "true");
      var shown = new Image();
      shown.alt = "";
      shown.onload = function () {
        var cell = document.createElement("span");
        cell.className = "pm-cell";
        cell.appendChild(shown);
        thumb.appendChild(cell);
      };
      shown.src = address("/thumb/" + encodeURIComponent(text.name) + "?drawn=1", key);
      starts.appendChild(thumb);
    }
    starts.appendChild(sayIn(document.createElement("span"), say("playlist-menu.starts-with", "Starts with {title}"), text.title));
    form.appendChild(starts);
    var presses = document.createElement("div");
    presses.className = "pm-presses";
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "pm-cancel";
    cancel.textContent = say("playlist-menu.cancel", "Cancel");
    cancel.addEventListener("click", close);
    presses.appendChild(cancel);
    var confirm = document.createElement("button");
    confirm.type = "submit";
    confirm.className = "pm-confirm";
    confirm.textContent = say("playlist-menu.confirm", "Confirm");
    presses.appendChild(confirm);
    form.appendChild(presses);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var name = field.value.trim();
      if (!name) {
        field.focus();
        return;
      }
      add(menu, text, key, { name: name });
    });
    // A refusal of the name is said under its field, before the presses.
    var line = document.createElement("p");
    line.className = "pm-status";
    line.setAttribute("role", "status");
    line.hidden = true;
    form.insertBefore(line, presses);
    menu.appendChild(form);
    opener.addEventListener("click", function () {
      newWindow(menu);
      field.focus();
    });
    return menu;
  }

  // The desk's New playlist: the menu becomes a small window in the middle of the dim.
  function newWindow(menu) {
    if (!open || open.menu !== menu) return;
    menu.classList.add("is-new");
    document.body.classList.add("pm-sheet-open");
    menu.style.left = "";
    menu.style.top = "";
    if (!open.scrim) {
      open.scrim = scrim();
      menu.parentNode.insertBefore(open.scrim, menu);
    }
  }

  function scrim() {
    var dim = document.createElement("div");
    dim.className = "scrim pm-scrim";
    dim.setAttribute("aria-hidden", "true");
    return dim;
  }

  /* Opens the menu under `press` for one text: `{name, title}`, the shelf name and the
   * title said to the reader. `key` is the local serve key, where there is one. */
  function toggle(press, text, key) {
    if (open && open.press === press) {
      close();
      return;
    }
    close();
    var sheet = narrow();
    var menu = build(text, key, sheet);
    // On the body, so a row that clips its overflow cannot clip the menu, and placed under
    // the press by its end edge, kept inside the window. A phone's sheet is placed by its
    // stylesheet, at the foot, over the dim.
    var dim = sheet ? scrim() : null;
    if (dim) document.body.appendChild(dim);
    document.body.appendChild(menu);
    if (!sheet) place(menu, press);
    press.setAttribute("aria-expanded", "true");
    open = { press: press, menu: menu, scrim: dim };
    // The sheet takes the reader's ⋯ sheet's place while it stands (board PlaylistMake).
    if (sheet) document.body.classList.add("pm-sheet-open");
    window.addEventListener("scroll", scrolled, true);
    window.addEventListener("resize", close);
    status(menu, say("playlist-menu.loading", "Loading…"));
    document.addEventListener("click", outside, true);
    document.addEventListener("keydown", escape, true);
    ask("GET", "/playlists.json", key)
      .then(function (got) {
        if (got.status === 401) {
          status(menu, say("playlist-menu.sign-in", "Sign in to use playlists."), true);
          menu.querySelector(".pm-new").hidden = true;
          return;
        }
        if (got.status >= 400) {
          status(menu, say("playlist-menu.load-failed", "We couldn't load your playlists. Try again."), true);
          return;
        }
        status(menu, "");
        draw(menu, text, key, (got.answer && got.answer.playlists) || [], got.answer && got.answer.current);
      })
      .catch(function () {
        status(menu, say("playlist-menu.load-failed", "We couldn't load your playlists. Try again."), true);
      });
  }

  /* Turns a link to `/playlists?add=` into the press that opens the menu. The link keeps
   * its address, so a middle-click still opens the page. */
  function attach(link, text, key) {
    link.setAttribute("aria-haspopup", "dialog");
    link.setAttribute("aria-expanded", "false");
    link.setAttribute("role", "button");
    link.addEventListener("click", function (event) {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
      event.preventDefault();
      toggle(link, text, key);
    });
  }

  /* "Play next" (targum-internal#434): a text put straight after the one the reader is
   * on, in the playlist they are in — the one they opened an item of last and have not
   * gone through. Asked for once a page; `playing()` is what came back, or null before
   * it has, so a menu drawn in the same moment as it is opened can offer it or not. */
  var currentAsk = null;
  var currentNow = null;
  function current(key) {
    if (!currentAsk) {
      currentAsk = ask("GET", "/playlists/current.json", key)
        .then(function (got) {
          currentNow = got.status < 400 && got.answer && got.answer.current ? got.answer.current : null;
          return currentNow;
        })
        .catch(function () {
          return null;
        });
    }
    return currentAsk;
  }

  /* The press itself, for any menu: "Play next in Mornings". Pressed, it says what it
   * did in its own place and hands `done` the line, so the menu it stands in can close. */
  function nextButton(text, key, playlist, className, done) {
    var press = document.createElement("button");
    press.type = "button";
    press.className = className || "pm-next";
    var label = say("playlist-menu.play-next", "Play next in {name}", { name: playlist.name });
    press.textContent = label;
    press.onclick = function (event) {
      event.preventDefault();
      press.disabled = true;
      ask("POST", "/playlists/" + playlist.id, key, { do: "next", reader: text.name, title: text.title })
        .then(function (got) {
          var why = got.answer && got.answer.error;
          if (got.status >= 400) {
            if (got.status === 404 || got.status === 401 || /^(not found|bad request)$/i.test(String(why || ""))) why = "";
            failed(why || say("playlist-menu.failed", "We couldn't add it to the playlist."));
            return;
          }
          press.textContent = say("playlist-menu.plays-next", "It plays next in {name}.", { name: playlist.name });
          press.setAttribute("role", "status");
          if (done) setTimeout(done, 900);
        })
        .catch(function () {
          failed(say("playlist-menu.failed", "We couldn't add it to the playlist."));
        });
    };
    // The press keeps its words, and a line under it says what went wrong, with Try
    // again (design.md §12, 2026-10-09). The refusal was the press's own label.
    function failed(words) {
      press.disabled = false;
      var old = press.nextElementSibling;
      if (old && old.classList.contains("fault-line")) old.parentNode.removeChild(old);
      if (!window.TargumFault || !press.parentNode) {
        press.textContent = words;
        return;
      }
      var line = window.TargumFault.line(words, function () {
        if (line.parentNode) line.parentNode.removeChild(line);
        press.click();
      });
      press.parentNode.insertBefore(line, press.nextSibling);
    }
    return press;
  }

  window.TargumPlaylistMenu = {
    attach: attach,
    close: close,
    current: current,
    playing: function () {
      return currentNow;
    },
    nextButton: nextButton,
  };
})();
