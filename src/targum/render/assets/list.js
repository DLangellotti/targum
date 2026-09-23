/* A reader opened from a playlist: the next one is a swipe away (targum-internal#366).
 *
 * design.md §12, "A playlist is swiped, and one press takes the set" (2026-09-23). A
 * reader arrives here as its ordinary served address with `?list=<id>&at=<n>`, and only
 * then does anything below happen. Off a disk, or opened on its own, this file does
 * nothing: the built page still fetches nothing, and the one request made here is to the
 * page's own origin, for the list the reader made, the way `events.js` posts to it.
 *
 * Three rules from that entry, each held here:
 *
 *  - **A swipe is a press.** Moving on with a swipe, the Next key or the arrow puts
 *    `&go=1` on the next address, and the next item plays when it arrives. Nothing else
 *    sets it: opening an item from the playlist page, a link or the bell plays nothing,
 *    and going back plays nothing new.
 *  - **An article is read before it is left.** A swipe in the middle of a text scrolls
 *    the text, as it always did; only a swipe at the very end moves on. The keys are
 *    there the whole time, for a reader who wants to skip.
 *  - **No travel under reduced motion**, and nothing here animates in any case: the next
 *    item replaces this one.
 *
 * What comes after the last item is #367's: the end card. This file shows
 * `aside#list-end` there, empty, and fills nothing in it.
 */
(function () {
  "use strict";

  /* Which items are either side of `at`, from the list as `/playlists/<id>.json` answers
   * it. Pure, so the arithmetic is tested without a browser (tests/js/list.js).
   *
   * An item is somewhere to go only when it has an address: one still getting ready has
   * none yet and one that failed never will, so both are passed over — and the ones
   * getting ready between here and the next are counted, so the page can say so rather
   * than silently skipping something the reader chose. */
  function neighbours(items, at) {
    var list = Array.isArray(items) ? items : [];
    var next = null;
    var back = null;
    var waiting = 0;
    for (var n = at + 1; n < list.length; n++) {
      var ahead = list[n] || {};
      if (ahead.open && !ahead.failed) {
        next = n;
        break;
      }
      if (!ahead.failed) waiting++;
    }
    for (var m = at - 1; m >= 0; m--) {
      var behind = list[m] || {};
      if (behind.open && !behind.failed) {
        back = m;
        break;
      }
    }
    // Still getting ready after the last one that can be opened: said at the end.
    if (next === null) {
      waiting = 0;
      for (var k = at + 1; k < list.length; k++) {
        if (!(list[k] || {}).failed && !(list[k] || {}).open) waiting++;
      }
    }
    return { next: next, back: back, waiting: waiting, last: next === null };
  }

  /* Where an item is opened from inside the list. `go` only on the way forward. */
  function addressOf(item, list, at, go) {
    var base = String(item.open);
    var join = base.indexOf("?") >= 0 ? "&" : "?";
    return base + join + "list=" + encodeURIComponent(list) + "&at=" + at + (go ? "&go=1" : "");
  }

  window.TargumList = { neighbours: neighbours, addressOf: addressOf };

  if (typeof location === "undefined" || !/^https?:$/.test(location.protocol)) return;
  var asked;
  try {
    asked = new URLSearchParams(location.search);
  } catch (e) {
    return;
  }
  var list = asked.get("list") || "";
  // The key a local `targum serve` prints and wants on every address, carried along.
  var key = asked.get("k") || "";
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }
  var at = parseInt(asked.get("at") || "", 10);
  if (!/^\d+$/.test(list) || !(at >= 0)) return;

  function t(key, english, fill) {
    var said = window.TargumStrings;
    if (said) return said.t(key, english, fill);
    return english.replace(/\{(\w+)\}/g, function (all, name) {
      return fill && Object.prototype.hasOwnProperty.call(fill, name) ? String(fill[name]) : all;
    });
  }
  function tn(key, count, one, other, fill) {
    var said = window.TargumStrings;
    if (said) return said.tn(key, count, one, other, fill);
    var values = { n: count };
    for (var name in fill || {}) values[name] = fill[name];
    return t(key, count === 1 ? one : other, values);
  }

  document.body.classList.add("in-list");

  var items = [];
  var near = { next: null, back: null, waiting: 0, last: true };

  function note(name) {
    var events = window.TargumEvents;
    if (events && events.note) {
      try {
        events.note({ kind: "control", control: name });
      } catch (e) {}
    }
  }

  function forward(how) {
    if (near.next !== null) {
      note(how);
      location.href = keyed(addressOf(items[near.next], list, near.next, true));
      return true;
    }
    return showEnd();
  }

  function backward(how) {
    if (near.back === null) return false;
    note(how);
    location.href = keyed(addressOf(items[near.back], list, near.back, false));
    return true;
  }

  function showEnd() {
    var end = document.getElementById("list-end");
    if (!end) return false;
    if (end.hidden) {
      end.hidden = false;
      document.body.classList.add("list-ended");
      // Out of the watching frame, so the card is on the page and not under a film.
      var box = document.getElementById("video");
      var mode = box && box.classList.contains("watching") ? box.querySelector(".video-mode") : null;
      if (mode) mode.click();
      if (end.scrollIntoView) end.scrollIntoView({ block: "start" });
      document.dispatchEvent(new CustomEvent("targum:list-end", { detail: { list: list } }));
    }
    return true;
  }

  function control(className, label, onPress) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "list-key " + className;
    button.textContent = label;
    button.addEventListener("click", onPress);
    return button;
  }

  function draw(set) {
    items = (set && set.items) || [];
    if (!items[at]) return;
    near = neighbours(items, at);

    // At the foot of the text: where an article is left, after it has been read.
    var nav = document.createElement("nav");
    nav.id = "list-nav";
    nav.className = "list-nav";
    nav.setAttribute("aria-label", t("reader.list.label", "Your playlist"));
    nav.setAttribute("dir", "ltr");
    var where = document.createElement("p");
    where.className = "list-where";
    where.textContent = t("reader.list.where", "{name}, {at} of {count}", {
      name: String((set && set.name) || ""),
      at: at + 1,
      count: items.length,
    });
    nav.appendChild(where);
    if (near.back !== null) {
      nav.appendChild(
        control("list-back", t("reader.list.back", "Back"), function () {
          backward("list-back");
        })
      );
    }
    var nextLabel =
      near.next !== null ? t("reader.list.next", "Next") : t("reader.list.done", "Finish the playlist");
    nav.appendChild(
      control("list-next", nextLabel, function () {
        forward("list-next");
      })
    );
    if (near.next !== null) {
      var upNext = document.createElement("p");
      upNext.className = "list-up-next";
      upNext.textContent = t("reader.list.up-next", "Up next: {title}", {
        title: String(items[near.next].title || ""),
      });
      nav.appendChild(upNext);
    }
    if (near.waiting) {
      var waiting = document.createElement("p");
      waiting.className = "list-waiting";
      waiting.textContent = tn(
        "reader.list.getting-ready",
        near.waiting,
        "{n} more is getting ready.",
        "{n} more are getting ready."
      );
      nav.appendChild(waiting);
    }
    var end = document.createElement("aside");
    end.id = "list-end";
    end.className = "list-end";
    end.hidden = true;

    var main = document.querySelector("main") || document.body;
    main.appendChild(nav);
    main.appendChild(end);

    // And in the watching frame, where the foot of the text cannot be seen: the same
    // Next among the picture's own keys.
    var keys = document.querySelector("#video .video-keys");
    if (keys) {
      if (near.back !== null) {
        keys.appendChild(
          control("list-back video-list-back", t("reader.list.back", "Back"), function () {
            backward("list-back");
          })
        );
      }
      keys.appendChild(
        control("list-next video-list-next", nextLabel, function () {
          forward("list-next");
        })
      );
    }
    document.dispatchEvent(new CustomEvent("targum:list", { detail: { list: list, at: at } }));
  }

  /* Whether this item has been read to its end, so a swipe may leave it. Watching, the
   * picture is the whole item and there is nothing to scroll. Reading, it is the foot of
   * the last page — the reader's own answer, where it gives one — and the bottom of the
   * window. */
  function watchingNow() {
    return document.body.classList.contains("watching");
  }
  function atEnd() {
    if (watchingNow()) return true;
    var reader = window.TargumReader;
    if (reader && reader.onLastPage && !reader.onLastPage()) return false;
    var root = document.documentElement;
    return window.innerHeight + window.scrollY >= root.scrollHeight - 4;
  }
  function atStart() {
    if (watchingNow()) return true;
    var reader = window.TargumReader;
    if (reader && reader.onFirstPage && !reader.onFirstPage()) return false;
    return window.scrollY <= 4;
  }

  /* Up for the next one, down for the last, the way a feed is swiped. Only a clearly
   * vertical stroke counts: a sideways one turns the page, and a short one is a tap. */
  var from = null;
  document.addEventListener(
    "touchstart",
    function (event) {
      var touch = event.touches && event.touches[0];
      from = touch && event.touches.length === 1 ? { x: touch.clientX, y: touch.clientY, end: atEnd(), start: atStart() } : null;
    },
    { passive: true }
  );
  document.addEventListener(
    "touchend",
    function (event) {
      if (!from) return;
      var touch = event.changedTouches && event.changedTouches[0];
      var began = from;
      from = null;
      if (!touch) return;
      var dx = touch.clientX - began.x;
      var dy = touch.clientY - began.y;
      if (Math.abs(dy) < 60 || Math.abs(dy) < Math.abs(dx) * 1.5) return;
      if (event.target && event.target.closest && event.target.closest(".card, .sheet, input, textarea, select")) return;
      // Where the stroke began decides, not where the page ended up: a swipe that
      // scrolled the last lines into view was reading, not leaving.
      if (dy < 0 && began.end && atEnd()) forward("swipe");
      else if (dy > 0 && began.start && atStart()) backward("swipe");
    },
    { passive: true }
  );

  /* The arrows up and down, where they have nothing else to do: they scroll the text,
   * and go on scrolling it until it has run out. Left and right are the word walk's, and
   * are not touched. */
  document.addEventListener("keydown", function (event) {
    if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    var on = event.target;
    if (on && (/^(INPUT|SELECT|TEXTAREA)$/.test(on.tagName) || on.isContentEditable)) return;
    if (event.key === "ArrowDown" && atEnd()) {
      if (forward("list-arrow")) event.preventDefault();
    } else if (event.key === "ArrowUp" && atStart() && near.back !== null) {
      if (backward("list-arrow")) event.preventDefault();
    }
  });

  fetch(keyed("/playlists/" + list + ".json"), { credentials: "same-origin" })
    .then(function (answer) {
      return answer.ok ? answer.json() : null;
    })
    .then(function (set) {
      if (set) draw(set);
    })
    .catch(function () {});
})();
