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

  function close() {
    if (!open) return;
    open.menu.remove();
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
          status(menu, got.answer.error || say("playlist-menu.failed", "Couldn't add it. Try again."), true);
          return;
        }
        status(menu, say("playlist-menu.added", "Added to {name}", { name: got.answer.name || target.name }));
        setTimeout(close, 900);
      })
      .catch(function () {
        status(menu, say("playlist-menu.failed", "Couldn't add it. Try again."), true);
      });
  }

  function status(menu, words, bad) {
    var line = menu.querySelector(".pm-status");
    line.textContent = words;
    line.hidden = !words;
    line.classList.toggle("bad", !!bad);
  }

  function draw(menu, text, key, playlists) {
    var list = menu.querySelector(".pm-list");
    list.textContent = "";
    playlists.forEach(function (one) {
      var item = document.createElement("li");
      var choose = document.createElement("button");
      choose.type = "button";
      choose.className = "pm-choice";
      choose.setAttribute("role", "menuitem");
      var name = document.createElement("bdi");
      name.textContent = one.name;
      choose.appendChild(name);
      var count = document.createElement("span");
      count.className = "pm-count";
      count.textContent = sayCount(one.count);
      choose.appendChild(count);
      choose.onclick = function () {
        add(menu, text, key, one);
      };
      item.appendChild(choose);
      list.appendChild(item);
    });
    list.hidden = !playlists.length;
    if (open && open.menu === menu) place(menu, open.press);
    var first = menu.querySelector(playlists.length ? ".pm-choice" : ".pm-name");
    if (first) first.focus();
  }

  function build(text, key) {
    var menu = document.createElement("div");
    menu.className = "playlist-menu";
    menu.setAttribute("role", "dialog");
    menu.setAttribute("aria-label", say("playlist-menu.label", "Add to a playlist"));

    var list = document.createElement("ul");
    list.className = "pm-list";
    list.setAttribute("role", "menu");
    list.hidden = true;
    menu.appendChild(list);

    var form = document.createElement("form");
    form.className = "pm-new";
    var field = document.createElement("input");
    field.type = "text";
    field.className = "pm-name";
    field.maxLength = 80;
    field.dir = "auto";
    field.autocomplete = "off";
    field.placeholder = say("playlist-menu.new", "New playlist");
    field.setAttribute("aria-label", say("playlist-menu.new", "New playlist"));
    form.appendChild(field);
    var confirm = document.createElement("button");
    confirm.type = "submit";
    confirm.className = "pm-confirm";
    confirm.textContent = say("playlist-menu.confirm", "Confirm");
    form.appendChild(confirm);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var name = field.value.trim();
      if (!name) {
        field.focus();
        return;
      }
      add(menu, text, key, { name: name });
    });
    menu.appendChild(form);

    var line = document.createElement("p");
    line.className = "pm-status";
    line.setAttribute("role", "status");
    line.hidden = true;
    menu.appendChild(line);
    return menu;
  }

  /* Opens the menu under `press` for one text: `{name, title}`, the shelf name and the
   * title said to the reader. `key` is the local serve key, where there is one. */
  function toggle(press, text, key) {
    if (open && open.press === press) {
      close();
      return;
    }
    close();
    var menu = build(text, key);
    // On the body, so a row that clips its overflow cannot clip the menu, and placed under
    // the press by its end edge, kept inside the window.
    document.body.appendChild(menu);
    place(menu, press);
    press.setAttribute("aria-expanded", "true");
    open = { press: press, menu: menu };
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
        status(menu, "");
        draw(menu, text, key, (got.answer && got.answer.playlists) || []);
      })
      .catch(function () {
        status(menu, say("playlist-menu.failed", "Couldn't add it. Try again."), true);
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

  window.TargumPlaylistMenu = { attach: attach, close: close };
})();
