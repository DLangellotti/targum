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
 * What comes after the last item is the end card (#367): `aside#list-end`, filled from
 * `/playlists/<id>/end.json` the first time it is shown — the words met across the set,
 * and one next set to press on its own page. It offers that once and loads nothing
 * after it: the end never refills itself.
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

  /* The direction of the interface, not of the text: the root carries the text's
   * direction, and the English under a Hebrew text read ".You met 35 words" (2026-09-24).
   * The root's `lang` is the interface's own (reader.html.j2). */
  var uiLanguage = String(
    (window.TargumStrings && window.TargumStrings.language) || document.documentElement.lang || "en"
  ).split("-")[0];
  var uiDir = /^(he|yi|ar|fa|ur|arc)$/.test(uiLanguage) ? "rtl" : "ltr";

  /* A line with a title in it, the title isolated so its own punctuation stays on its
   * own side: "Up next: {title}" with a Hebrew title that ends in "?". */
  function withTitle(node, said, name, value) {
    var cut = said.indexOf("{" + name + "}");
    if (cut < 0) {
      node.textContent = said;
      return node;
    }
    node.appendChild(document.createTextNode(said.slice(0, cut)));
    var inner = document.createElement("bdi");
    inner.setAttribute("dir", "auto");
    inner.textContent = value;
    node.appendChild(inner);
    node.appendChild(document.createTextNode(said.slice(cut + name.length + 2)));
    return node;
  }

  var items = [];
  var setName = "";
  var near = { next: null, back: null, waiting: 0, last: true };

  function note(name) {
    var events = window.TargumEvents;
    if (events && events.note) {
      try {
        events.note({ kind: "control", control: name });
      } catch (e) {}
    }
  }

  /* Moving on finishes the item (design.md §12, "The foot is one block", 2026-09-25):
   * "Next" finished nothing, so a reader who went Next, Next, Next through a set had
   * finished nothing on Your Progress. The press at the foot marks the words never marked
   * when it says so; a swipe, the arrow and the Next among a video's keys finish without
   * marking, because marking words is never done by a gesture. The reader does the
   * finishing — it owns the record — and says where the reader lands what it did. */
  function forward(how, marking) {
    var reader = window.TargumReader;
    var title = items[at] ? String(items[at].title || "") : "";
    if (near.next !== null) {
      note(how);
      if (reader && reader.leave) reader.leave(!!marking, title);
      location.href = keyed(addressOf(items[near.next], list, near.next, true));
      return true;
    }
    if (reader && reader.press) reader.press(!!marking);
    return showEnd();
  }

  function backward(how) {
    if (near.back === null) return false;
    note(how);
    location.href = keyed(addressOf(items[near.back], list, near.back, false));
    return true;
  }

  /* The end card, once (#367): real counts, the words themselves, and one door, and
   * nothing that loads more. When the end has nothing to say — end.json failed, or
   * answered with neither — it still says where the reader is and where their
   * playlists are. */
  function drawEnd(end, said) {
    var words = said && said.words;
    var next = said && said.next;
    if (!(words && words.met) && !(next && next.open)) {
      var over = withTitle(
        document.createElement("p"),
        t("reader.list.end-of", "That's the end of {name}."),
        "name",
        setName
      );
      over.className = "list-end-over";
      end.appendChild(over);
      var home = document.createElement("a");
      home.className = "list-end-home";
      home.href = keyed("/playlists");
      home.textContent = t("reader.list.your-playlists", "Your playlists");
      end.appendChild(home);
      return;
    }
    if (words && words.met) {
      var met = document.createElement("p");
      met.className = "list-end-words";
      met.textContent = words.new
        ? tn(
            "reader.list.end-words-new",
            words.met,
            "You met {n} word, {new} of them new.",
            "You met {n} words, {new} of them new.",
            { new: words.new }
          )
        : tn(
            "reader.list.end-words",
            words.met,
            "You met {n} word.",
            "You met {n} words."
          );
      end.appendChild(met);
      // The words, not only their count (design.md §12: "the words met across the set"):
      // the new ones first, as many as the server names — it caps them.
      var shown = Array.isArray(words.list) ? words.list : [];
      if (shown.length) {
        var list = document.createElement("ul");
        list.className = "list-end-list";
        shown.forEach(function (one) {
          var row = document.createElement("li");
          if (one.new) row.className = "new";
          var word = document.createElement("bdi");
          word.setAttribute("dir", "auto");
          if (one.language) word.setAttribute("lang", String(one.language));
          word.textContent = String(one.word || "");
          row.appendChild(word);
          list.appendChild(row);
        });
        end.appendChild(list);
      }
    }
    if (next && next.open) {
      var lead = document.createElement("p");
      lead.className = "list-end-lead";
      lead.textContent = t("reader.list.end-next", "Next playlist");
      end.appendChild(lead);
      var door = document.createElement("a");
      door.className = "list-end-next";
      door.href = keyed(String(next.open));
      // One span inside the pill, so the name and its count stay one line of text.
      var label = document.createElement("span");
      withTitle(
        label,
        tn("reader.list.end-next-door", next.count || 0, "{name}, {n} text", "{name}, {n} texts"),
        "name",
        String(next.name || "")
      );
      door.appendChild(label);
      end.appendChild(door);
    }
  }
  var ended = false;
  function fillEnd(end) {
    if (ended) return;
    ended = true;
    fetch(keyed("/playlists/" + list + "/end.json"), { credentials: "same-origin" })
      .then(function (answer) {
        return answer.ok ? answer.json() : null;
      })
      .then(function (said) {
        drawEnd(end, said);
      })
      .catch(function () {
        drawEnd(end, null);
      });
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
      fillEnd(end);
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
    setName = String((set && set.name) || "");

    // Where you are, at the head of the foot's one block (design.md §12, "The foot is one
    // block", 2026-09-25): "← Back · Couples and everyday life, 2 of 3". Back is a small
    // link on this line and not a second button beside the press — it is the rare way,
    // and a pill beside Next made the two one decision.
    var nav = document.createElement("nav");
    nav.id = "list-nav";
    nav.className = "list-nav";
    nav.setAttribute("aria-label", t("reader.list.label", "Your playlist"));
    nav.setAttribute("dir", uiDir);
    if (near.back !== null) {
      var back = document.createElement("button");
      back.type = "button";
      back.className = "list-back";
      back.textContent = t("reader.list.back-link", "← Back");
      back.addEventListener("click", function () {
        backward("list-back");
      });
      nav.appendChild(back);
      nav.appendChild(document.createTextNode(" · "));
    }
    var where = withTitle(
      document.createElement("span"),
      t("reader.list.where", "{name}, {at} of {count}", { at: at + 1, count: items.length }),
      "name",
      setName
    );
    where.className = "list-where";
    nav.appendChild(where);

    // What comes next, small, under the press: the press says Next and this says where.
    var ahead = document.createElement("div");
    ahead.className = "list-ahead";
    ahead.setAttribute("dir", uiDir);
    if (near.next !== null) {
      var upNext = withTitle(
        document.createElement("p"),
        t("reader.list.up-next", "Up next: {title}"),
        "title",
        String(items[near.next].title || "")
      );
      upNext.className = "list-up-next";
      ahead.appendChild(upNext);
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
      ahead.appendChild(waiting);
    }
    var nextLabel =
      near.next !== null ? t("reader.list.next", "Next") : t("reader.list.done", "Finish");
    var end = document.createElement("aside");
    end.id = "list-end";
    end.className = "list-end";
    end.setAttribute("dir", uiDir);
    end.hidden = true;

    // Into the foot the reader drew, whose press becomes Next.
    var foot = document.getElementById("foot");
    var main = document.querySelector("main") || document.body;
    if (foot) {
      foot.insertBefore(nav, foot.firstChild);
      var under = document.getElementById("foot-next");
      if (under && ahead.firstChild) {
        under.appendChild(ahead);
        under.hidden = false;
      }
      foot.parentNode.insertBefore(end, foot.nextSibling);
    } else {
      main.appendChild(nav);
      main.appendChild(ahead);
      main.appendChild(end);
    }
    /* The reader may not have finished drawing when the list arrives — it hangs itself
       off the window last — so the way on is left where it will look for it, as well as
       handed over when it is already there. */
    var way = {
      verb: near.next !== null ? "next" : "finish",
      go: function (marking) {
        forward("list-next", marking);
      },
    };
    window.TargumFootWay = way;
    if (window.TargumReader && window.TargumReader.foot) window.TargumReader.foot(way);

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
   * are not touched.
   *
   * On pages, a page that fits the window has nothing to scroll, so down at its foot
   * turns to the next page and up at its head to the one before — the arrows' "go on
   * until the text runs out" on a text that is cut into pages. Without that, a paged
   * scene answered the arrow with nothing until its last page, and the key to Next
   * looked dead (2026-09-24). Heard first, in the capture phase, so no control that
   * happens to hold the focus — a word walked to, the player's own track — keeps the
   * key from reaching the list at the end of the text; everywhere else it is left to go
   * on as it was. */
  function turnPage(by) {
    if (!document.body.classList.contains("paged")) return false;
    var reader = window.TargumReader;
    if (!reader) return false;
    if (by > 0 && reader.onLastPage && reader.onLastPage()) return false;
    if (by < 0 && reader.onFirstPage && reader.onFirstPage()) return false;
    var turn = document.querySelector('.turn button[data-turn="' + (by > 0 ? "1" : "-1") + '"]');
    if (!turn) return false;
    turn.click();
    return true;
  }
  function scrolledToFoot() {
    var root = document.documentElement;
    return window.innerHeight + window.scrollY >= root.scrollHeight - 4;
  }
  document.addEventListener(
    "keydown",
    function (event) {
      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      var on = event.target;
      if (on && (/^(INPUT|SELECT|TEXTAREA)$/.test(on.tagName) || on.isContentEditable)) return;
      var moved = false;
      if (event.key === "ArrowDown") {
        if (atEnd()) moved = forward("list-arrow");
        else if (scrolledToFoot()) moved = turnPage(1);
      } else if (atStart()) {
        moved = near.back !== null && backward("list-arrow");
      } else if (window.scrollY <= 4) {
        moved = turnPage(-1);
      }
      if (moved) {
        event.preventDefault();
        event.stopPropagation();
      }
    },
    true
  );

  fetch(keyed("/playlists/" + list + ".json"), { credentials: "same-origin" })
    .then(function (answer) {
      return answer.ok ? answer.json() : null;
    })
    .then(function (set) {
      if (set) draw(set);
    })
    .catch(function () {});
})();
