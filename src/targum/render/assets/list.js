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

  /* Where an item is opened from inside the list. `go` only on the way forward; `listen`
   * where the reader is listening (design.md §12, 2026-10-09), so the item's recording
   * starts as it arrives, and `seconds` where the voice already got to in it. */
  function addressOf(item, list, at, go, listen, seconds) {
    var base = String(item.open);
    var join = base.indexOf("?") >= 0 ? "&" : "?";
    return (
      base +
      join +
      "list=" +
      encodeURIComponent(list) +
      "&at=" +
      at +
      (go ? "&go=1" : "") +
      (listen ? "&listen=1" : "") +
      (seconds > 0 ? "&t=" + Math.floor(seconds) : "")
    );
  }

  /* The playlist, added up: how many of its texts were finished, the words that became
   * known across them, the share known across all of their words (weighted by words, so
   * a long text counts for more than a short one), and the words looked up. Null where
   * no item has figures. Pure, for the harness. */
  function addUp(kept) {
    var places = Object.keys(kept || {});
    if (!places.length) return null;
    var sum = { texts: 0, known: 0, here: 0, of: 0, looked: 0 };
    places.forEach(function (place) {
      var one = kept[place] || {};
      sum.texts += 1;
      sum.known += Number(one.known || 0);
      sum.here += Number(one.here || 0);
      sum.of += Number(one.of || 0);
      sum.looked += Number(one.looked || 0);
    });
    sum.share = sum.of ? Math.round((sum.here / sum.of) * 100) : 0;
    return sum;
  }

  window.TargumList = { neighbours: neighbours, addressOf: addressOf, addUp: addUp };

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

  /* One word for what an item is, and its length and how much of it is known, as the
     playlist's page says them: "Dialogue · 3 min · 91% known". */
  function kindOf(facts) {
    if (!facts) return "";
    if (facts.video) return t("reader.list.kind.video", "Video");
    var words = {
      article: t("reader.list.kind.article", "Article"),
      talk: t("reader.list.kind.video", "Video"),
      dialogue: t("reader.list.kind.dialogue", "Dialogue"),
      story: t("reader.list.kind.story", "Story"),
      novel: t("reader.list.kind.book", "Book"),
      essay: t("reader.list.kind.essay", "Essay"),
      prose: t("reader.list.kind.tanakh", "Tanakh"),
      poetry: t("reader.list.kind.poetry", "Poetry"),
      play: t("reader.list.kind.play", "Play"),
      liturgy: t("reader.list.kind.prayer", "Prayer"),
      document: t("reader.list.kind.document", "Document"),
    };
    return words[facts.kind] || "";
  }
  function factsOf(item) {
    var facts = (item && item.facts) || null;
    var said = [];
    var kind = kindOf(facts);
    if (kind) said.push(kind);
    var seconds = facts ? Number(facts.seconds || 0) || Number(facts.minutes || 0) * 60 : 0;
    if (seconds > 0) said.push(minutesOf(Math.max(1, Math.round(seconds / 60))));
    if (facts && typeof facts.known === "number") {
      said.push(t("reader.list.known", "{share}% known", { share: Math.round(facts.known * 100) }));
    }
    return said.join(" · ");
  }
  // An item's picture at a thumb's size, resting on its letter until it has loaded.
  function thumbOf(item, className) {
    var box = document.createElement("span");
    box.className = className;
    box.setAttribute("aria-hidden", "true");
    var letter = document.createElement("span");
    letter.className = "list-thumb-letter";
    letter.textContent = String((item && item.title) || "?").replace(/^[^\wא-תЀ-ӿ]+/, "").charAt(0);
    box.appendChild(letter);
    var src = pictureOf(item);
    if (src) {
      var picture = new Image();
      picture.alt = "";
      picture.onload = function () {
        letter.remove();
        box.appendChild(picture);
      };
      picture.src = src;
    }
    return box;
  }
  // A line drawing from 16×16 strokes, at the size of the words beside it.
  function glyph(paths, className) {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", "list-glyph" + (className ? " " + className : ""));
    paths.forEach(function (d) {
      var path = document.createElementNS(ns, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }
  var DOWN = ["M8 3v10", "M4 9l4 4 4-4"];
  var UP = ["M4 10l4-4 4 4"];
  var PLAYING = ["M4 6v4", "M8 4v8", "M12 6.5v3"];

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
  function forward(how, marking, listening) {
    var reader = window.TargumReader;
    var title = items[at] ? String(items[at].title || "") : "";
    if (near.next !== null) {
      note(how);
      if (reader && reader.leave) reader.leave(!!marking, title);
      keepFigures(reader);
      location.href = keyed(addressOf(items[near.next], list, near.next, true, !!listening));
      return true;
    }
    if (reader && reader.press) reader.press(!!marking);
    keepFigures(reader);
    return showEnd();
  }

  /* What each item came to, kept by its place in the playlist so the end card can add
   * them up (design.md §12, "The finished box is three figures", 2026-09-25). By place,
   * so an item finished twice is counted once, with what it came to the last time. In
   * this browser, as the figures themselves are. */
  var TALLY = "targum:list-tally";
  function tallies() {
    try {
      var all = JSON.parse(localStorage.getItem(TALLY) || "{}");
      return all && typeof all === "object" ? all : {};
    } catch (e) {
      return {};
    }
  }
  function keepFigures(reader) {
    var figures = reader && reader.figures ? reader.figures() : null;
    if (!figures) return;
    try {
      var all = tallies();
      var mine = all[list] || {};
      mine[String(at)] = figures;
      all[list] = mine;
      localStorage.setItem(TALLY, JSON.stringify(all));
    } catch (e) {}
  }


  function backward(how) {
    if (near.back === null) return false;
    note(how);
    location.href = keyed(addressOf(items[near.back], list, near.back, false));
    return true;
  }

  /* The end card, once (#367, #435; design.md §12, 2026-10-09): what the set held, the
   * words met with what they mean, and one next set picked for them — confirmed here, on
   * the card, or changed on its own page. Nothing that loads more. When the end has
   * nothing to say it still says where the reader is and where their playlists are. */
  function line(className, text) {
    var node = document.createElement("p");
    node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function wordsMet(end, words) {
    end.appendChild(
      line(
        "list-end-words",
        words.new
          ? tn(
              "reader.list.end-words-new",
              words.met,
              "You met {n} word, {new} of them new.",
              "You met {n} words, {new} of them new.",
              { new: words.new }
            )
          : tn("reader.list.end-words", words.met, "You met {n} word.", "You met {n} words.")
      )
    );
    // The words, not only their count, the new ones first, as many as the server names;
    // each with its meaning where the text's glossary has one.
    var shown = Array.isArray(words.list) ? words.list : [];
    if (!shown.length) return;
    var chips = document.createElement("ul");
    chips.className = "list-end-list";
    shown.forEach(function (one) {
      chips.appendChild(chip(one));
    });
    function chip(one) {
      var row = document.createElement("li");
      if (one.new) row.className = "new";
      var word = document.createElement("bdi");
      word.setAttribute("dir", "auto");
      if (one.language) word.setAttribute("lang", String(one.language));
      word.textContent = String(one.word || "");
      row.appendChild(word);
      if (one.gloss) {
        var gloss = document.createElement("span");
        gloss.className = "list-end-gloss";
        gloss.setAttribute("dir", "ltr");
        gloss.textContent = String(one.gloss).split(/[;,]/)[0].trim();
        row.appendChild(gloss);
      }
      return row;
    }
    end.appendChild(chips);
    // "All 41 new words" (board PlaylistEnd): the rest of the new ones open out in place,
    // with what each means, and the press goes. Nothing is fetched for it.
    var more = Array.isArray(words.more) ? words.more : [];
    if (more.length && words.new > 0) {
      var all = document.createElement("button");
      all.type = "button";
      all.className = "list-end-all";
      all.textContent = tn("reader.list.all-new", words.new, "All {n} new word", "All {n} new words");
      all.addEventListener("click", function () {
        more.forEach(function (one) {
          chips.appendChild(chip(one));
        });
        all.remove();
        var first = chips.children[shown.length];
        if (first && first.focus) {
          first.tabIndex = -1;
          first.focus();
        }
      });
      chips.appendChild(all);
    }
  }

  function minutesOf(n) {
    return t("reader.list.minutes", "{n} min", { n: n });
  }

  function creditsOf(n) {
    return tn("reader.list.credits", n, "{n} credit", "{n} credits");
  }

  // Confirm: the set's own press, here (`POST /set/<id>`, all or nothing).
  function confirmSet(next, foot) {
    var press = foot.querySelector(".list-end-confirm");
    var said = foot.querySelector(".list-end-said");
    press.disabled = true;
    said.hidden = true;
    var headers = { "Content-Type": "application/json", "X-Targum-Press": "1" };
    if (key) headers["X-Targum-Key"] = key;
    fetch(keyed("/set/" + next.id), {
      method: "POST",
      credentials: "same-origin",
      headers: headers,
      body: JSON.stringify({
        keep: (next.items || []).map(function (item, n) {
          return n;
        }),
      }),
    })
      .then(function (answer) {
        return answer
          .json()
          .catch(function () {
            return {};
          })
          .then(function (body) {
            return { ok: answer.ok, body: body || {} };
          });
      })
      .then(function (got) {
        if (!got.ok) {
          press.disabled = false;
          said.hidden = false;
          said.textContent = got.body.error || t("reader.list.end-could-not", "We couldn't start it. Try again.");
          return;
        }
        started(next, foot);
      })
      .catch(function () {
        press.disabled = false;
        said.hidden = false;
        said.textContent = t("reader.list.end-could-not", "We couldn't start it. Try again.");
      });
  }

  function started(next, foot) {
    foot.textContent = "";
    var note = line("list-end-started", t("reader.list.end-started", "Getting it ready. It's in your playlists."));
    note.setAttribute("role", "status");
    foot.appendChild(note);
    var go = document.createElement("a");
    go.className = "list-end-next";
    go.href = keyed(String(next.page || "/playlists"));
    go.textContent = t("reader.list.end-open", "Open the playlist");
    foot.appendChild(go);
  }

  function nextSet(end, next) {
    var card = document.createElement("section");
    card.className = "list-end-set";
    card.appendChild(line("list-end-lead", t("reader.list.end-next", "Next playlist")));
    // Its cover beside its name (board PlaylistEnd): the first four texts' pictures.
    var top = document.createElement("div");
    top.className = "list-end-set-top";
    var mosaic = document.createElement("span");
    var some = (next.items || []).slice(0, 4);
    mosaic.className = "list-end-mosaic n-" + some.length;
    mosaic.setAttribute("aria-hidden", "true");
    some.forEach(function (item) {
      mosaic.appendChild(thumbOf({ title: item.title, reader: item.entry || item.reader }, "list-end-cell"));
    });
    top.appendChild(mosaic);
    var heading = document.createElement("div");
    heading.className = "list-end-set-what";
    var name = document.createElement("h3");
    name.className = "list-end-name";
    var bdi = document.createElement("bdi");
    bdi.setAttribute("dir", "auto");
    bdi.textContent = String(next.name || "");
    name.appendChild(bdi);
    heading.appendChild(name);
    top.appendChild(heading);
    card.appendChild(top);
    var facts = [
      next.made_by === "connector"
        ? t("reader.list.by-assistant", "From an assistant")
        : t("reader.list.by-targum", "From targum"),
      tn("reader.list.texts", next.count || 0, "{n} text", "{n} texts"),
    ];
    if (next.seconds) facts.push(minutesOf(Math.round(next.seconds / 60)));
    facts.push(t("reader.list.picked", "picked for the words you just met"));
    heading.appendChild(line("list-end-facts", facts.join(" · ")));
    var rows = document.createElement("ul");
    rows.className = "list-end-items";
    // A row a text (board PlaylistEnd): its picture, its title, what it is, how long,
    // how much of it is known as a meter, and its credits.
    (next.items || []).forEach(function (item) {
      var row = document.createElement("li");
      row.appendChild(thumbOf({ title: item.title, reader: item.entry || item.reader }, "list-end-thumb"));
      var title = document.createElement("bdi");
      title.setAttribute("dir", "auto");
      title.className = "list-end-item";
      title.textContent = String(item.title || "");
      row.appendChild(title);
      var kind = kindOf({ kind: item.kind, video: item.video });
      row.appendChild(line("list-end-item-kind", kind));
      row.appendChild(line("list-end-item-length", item.minutes ? minutesOf(item.minutes) : ""));
      var known = line("list-end-item-facts", "");
      if (typeof item.known === "number") {
        var meter = document.createElement("span");
        meter.className = "list-end-meter";
        meter.setAttribute("aria-hidden", "true");
        var fill = document.createElement("span");
        fill.style.inlineSize = Math.round(Math.max(0, Math.min(1, item.known)) * 100) + "%";
        meter.appendChild(fill);
        known.appendChild(meter);
        known.appendChild(
          document.createTextNode(
            t("reader.list.share", "{share}%", { share: Math.round(item.known * 100) })
          )
        );
      }
      row.appendChild(known);
      // On a phone the columns fold under the title: "Dialogue · 2 min · 95%".
      var folded = [kind];
      if (item.minutes) folded.push(minutesOf(item.minutes));
      if (typeof item.known === "number") {
        folded.push(t("reader.list.share", "{share}%", { share: Math.round(item.known * 100) }));
      }
      row.appendChild(
        line(
          "list-end-item-folded",
          folded
            .filter(function (one) {
              return !!one;
            })
            .join(" · ")
        )
      );
      row.appendChild(line("list-end-item-credits", item.credits ? creditsOf(item.credits) : ""));
      rows.appendChild(row);
    });
    card.appendChild(rows);
    var foot = document.createElement("div");
    foot.className = "list-end-foot";
    if (next.state === "waiting") {
      foot.appendChild(
        line(
          "list-end-total",
          tn("reader.list.credits-in-all", next.credits || 0, "Uses {n} credit in all", "Uses {n} credits in all")
        )
      );
      var change = document.createElement("a");
      change.className = "list-end-change";
      change.href = keyed(String(next.open));
      change.textContent = t("reader.list.change", "Change what's in it");
      foot.appendChild(change);
      var press = document.createElement("button");
      press.type = "button";
      press.className = "list-end-confirm";
      press.textContent = t("reader.list.confirm", "Confirm");
      press.addEventListener("click", function () {
        confirmSet(next, foot);
      });
      foot.appendChild(press);
      var said = line("list-end-said");
      said.setAttribute("role", "status");
      said.hidden = true;
      foot.appendChild(said);
    } else {
      started(next, foot);
      if (next.state === "ready") {
        foot.firstChild.textContent = t("reader.list.end-ready", "It's ready in your playlists.");
      }
    }
    card.appendChild(foot);
    end.appendChild(card);
  }

  function drawEnd(end, said) {
    var words = said && said.words;
    var next = said && said.next;
    /* Its own screen (board PlaylistEnd): "‹ Mornings · The end" at its head, the way
       back to the playlist's page. */
    var head = document.createElement("div");
    head.className = "list-end-top";
    var back = document.createElement("a");
    back.className = "list-end-back";
    back.href = keyed("/playlists/" + list);
    back.setAttribute("aria-label", t("reader.list.end-back", "Back to {name}", { name: setName }));
    back.appendChild(glyph(["M10 3.5 5.5 8l4.5 4.5"], "list-end-back-glyph"));
    var called = document.createElement("bdi");
    called.setAttribute("dir", "auto");
    called.className = "list-end-set-name";
    called.textContent = setName;
    back.appendChild(called);
    head.appendChild(back);
    head.appendChild(line("list-end-the-end", t("reader.list.the-end", "The end")));
    end.appendChild(head);
    var over = withTitle(
      document.createElement("h2"),
      t("reader.list.end-of", "That's the end of {name}."),
      "name",
      setName
    );
    over.className = "list-end-over";
    end.appendChild(over);
    if (words && words.met) wordsMet(end, words);
    if (next && next.open) nextSet(end, next);
    var home = document.createElement("a");
    home.className = "list-end-home";
    home.href = keyed("/playlists");
    home.textContent = t("reader.list.your-playlists", "Your playlists");
    var way = document.createElement("p");
    way.className = "list-end-way";
    way.appendChild(home);
    end.appendChild(way);
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
      // Under a large picture the transcript is a panel, and the card is at its foot:
      // the panel opens, so the card is on the page and not behind the picture (#422).
      if (window.TargumVideo && window.TargumVideo.transcript) window.TargumVideo.transcript(true);
      if (end.scrollIntoView) end.scrollIntoView({ block: "start" });
      tellHere(items.length);
      // The rail says where the reader is now: at its End.
      var rail = document.getElementById("list-rail");
      if (rail) {
        var was = rail.querySelector(".list-rail-tile.is-here");
        if (was) {
          was.classList.remove("is-here");
          was.removeAttribute("aria-current");
        }
        var last = rail.querySelector(".list-rail-end");
        if (last) {
          last.classList.add("is-here");
          last.setAttribute("aria-current", "true");
        }
      }
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

  /* Where the reader is in the playlist, kept on the account (targum-internal#434): the
   * playlist opened last is "the one you're in" on the Playlists tab, and "Play next"
   * puts a text after this place. Past the last item is a playlist gone through. Said
   * and forgotten: a page that cannot say it still reads. */
  function tellHere(position) {
    var headers = { "Content-Type": "application/json" };
    if (key) headers["X-Targum-Key"] = key;
    try {
      fetch(keyed("/playlists/" + list), {
        method: "POST",
        credentials: "same-origin",
        headers: headers,
        body: JSON.stringify({ do: "here", position: position }),
      }).catch(function () {});
    } catch (e) {}
  }

  function draw(set) {
    items = (set && set.items) || [];
    if (!items[at]) return;
    tellHere(at);
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
    if (voiced()) {
      nav.appendChild(document.createTextNode(" · "));
      nav.appendChild(playOnSwitch());
    }

    // What comes next, small, under the press: the press says Next and this says where.
    var ahead = document.createElement("div");
    ahead.className = "list-ahead";
    ahead.setAttribute("dir", uiDir);
    if (near.next !== null) {
      /* What comes next, as a card (boards PlaylistSwipePhone and ReaderPhone): its
         picture, "Next · 3 of 6", its title, and what it is, how long and how much is
         known. A press like Next: it goes on without marking, as a swipe does. */
      var coming = items[near.next];
      var upNext = document.createElement("button");
      upNext.type = "button";
      upNext.className = "list-up-next";
      upNext.appendChild(thumbOf(coming, "list-up-thumb"));
      var said = document.createElement("span");
      said.className = "list-up-what";
      said.appendChild(
        withTitle(
          document.createElement("span"),
          t("reader.list.next-of", "Next · {at} of {count}", { at: near.next + 1, count: items.length }),
          "title",
          ""
        )
      ).className = "list-up-lead";
      var named = document.createElement("bdi");
      named.setAttribute("dir", "auto");
      named.className = "list-up-title";
      named.textContent = String(coming.title || "");
      said.appendChild(named);
      var about = factsOf(coming);
      if (about) {
        var line = document.createElement("span");
        line.className = "list-up-facts";
        line.textContent = about;
        said.appendChild(line);
      }
      upNext.appendChild(said);
      upNext.appendChild(glyph(UP, "list-up-go"));
      upNext.setAttribute(
        "aria-label",
        t("reader.list.up-next", "Up next: {title}", { title: String(coming.title || "") })
      );
      upNext.addEventListener("click", function () {
        forward("list-up-next");
      });
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

    // And under the picture, where the foot of the text cannot be seen while it stands
    // large: the same Next in the row of its controls (#422).
    var keys = document.querySelector("#video .film-tools");
    if (keys) {
      if (near.back !== null) {
        keys.appendChild(
          control("list-back video-list-back", t("reader.list.back", "Back"), function () {
            backward("list-back");
          })
        );
      }
      /* "Next [picture] באוטובוס ↓" (board PlaylistSwipeDesk): the press says where it
         goes. At the last item it is Finish, and says only that. */
      var onward = control("list-next video-list-next", "", function () {
        forward("list-next");
      });
      var word = document.createElement("span");
      word.className = "video-list-word";
      word.textContent = nextLabel;
      onward.appendChild(word);
      if (near.next !== null) {
        onward.classList.add("has-next");
        onward.appendChild(thumbOf(items[near.next], "video-list-thumb"));
        var whose = document.createElement("bdi");
        whose.setAttribute("dir", "auto");
        whose.className = "video-list-title";
        whose.textContent = String(items[near.next].title || "");
        onward.appendChild(whose);
        onward.appendChild(glyph(DOWN, "video-list-go"));
        onward.setAttribute(
          "aria-label",
          t("reader.list.up-next", "Up next: {title}", { title: String(items[near.next].title || "") })
        );
      }
      keys.appendChild(onward);
      if (voiced()) {
        var onKey = playOnSwitch();
        onKey.classList.add("list-key", "video-list-on");
        keys.appendChild(onKey);
      }
    }
    if (wideRail && wideRail.matches) drawRail();
    if (voiced()) whenPlayer(listenTo);
    document.dispatchEvent(new CustomEvent("targum:list", { detail: { list: list, at: at } }));
  }

  /* --- one player across items (targum-internal#434) ---------------------------------
   *
   * design.md §12, "Listening plays on by itself, and reading still waits for a swipe"
   * (2026-10-09). Listening is the screen locked, targum behind another app, or Play on.
   * When this item's recording plays to its end then, the next item's starts by itself:
   * with the screen in front of the reader, as a swipe would; with it locked, in the
   * same player, because a locked phone neither loads a page nor starts one. The item
   * that ended hands its media element to the next item's recording and the page stays
   * what it was, saying what plays now. An item with nothing to hear is where it stops.
   */
  /* Whether this item can be heard: its play control is drawn by the server, so this is
     known before the reader's own script has run, which a list that answers quickly can
     beat (#434). */
  function voiced() {
    return !!document.querySelector("[data-play-scene]") || document.body.classList.contains("has-voice");
  }

  var PLAY_ON = "targum:play-on";
  function playOn() {
    try {
      return localStorage.getItem(PLAY_ON) === "1";
    } catch (e) {
      return false;
    }
  }
  function choosePlayOn(on) {
    try {
      if (on) localStorage.setItem(PLAY_ON, "1");
      else localStorage.removeItem(PLAY_ON);
    } catch (e) {}
  }

  // An item's own picture, for the rail and the lock screen: `/thumb/` answers with the
  // text's picture or its drawn letter, from this box.
  function pictureOf(item) {
    var facts = item && item.facts;
    var name = (facts && (facts.entry || facts.name)) || (item && item.reader) || "";
    return name ? keyed("/thumb/" + encodeURIComponent(name) + "?drawn=1") : "";
  }

  /* What an item's recording is, read off its own page: the voice and never its
     picture, because a phone goes on playing a sound behind a locked screen and stops a
     film. Null where it has none. Asked for ahead, so the next one is in hand the moment
     this one ends: a locked phone gives a page little time once its sound has stopped. */
  var heard = {};
  function recordingOf(index) {
    var item = items[index];
    if (!item || !item.open || item.failed) return Promise.resolve(null);
    if (heard[index]) return heard[index];
    var page = new URL(keyed(String(item.open)), location.href);
    heard[index] = fetch(page.href, { credentials: "same-origin" })
      .then(function (answer) {
        return answer.ok ? answer.text() : "";
      })
      .then(function (html) {
        if (!html || typeof DOMParser === "undefined") return null;
        var doc = new DOMParser().parseFromString(html, "text/html");
        var node = doc.getElementById("targum-data");
        var data = node ? JSON.parse(node.textContent || "{}") : {};
        var sound = data && data.speech && data.speech.audio;
        if (!sound) return null;
        if (/^data:/.test(sound)) return sound;
        // Beside the page, asked for with the page's own key, as the reader asks.
        var src = new URL(sound, page.href);
        src.search = page.search;
        return src.href;
      })
      .catch(function () {
        return null;
      });
    return heard[index];
  }

  var handed = null; // { element, at }: the player, once it plays another item
  var wasFollowing = false;

  function lockScreen(index, sounding) {
    if (typeof navigator === "undefined" || !navigator.mediaSession) return;
    var item = items[index] || {};
    try {
      if (typeof MediaMetadata !== "undefined") {
        var art = pictureOf(item);
        navigator.mediaSession.metadata = new MediaMetadata({
          title: String(item.title || setName),
          artist: t("reader.list.where-short", "{name} · {at} of {count}", {
            name: setName,
            at: Math.min(index + 1, items.length),
            count: items.length,
          }),
          album: "targum",
          artwork: art ? [{ src: new URL(art, location.href).href, sizes: "512x512" }] : [],
        });
      }
      if (sounding === false) navigator.mediaSession.playbackState = "paused";
    } catch (e) {}
  }

  // The line that says, once the screen is back, what is playing now and opens it there.
  function drawNow(said, index, withTime) {
    var now = document.getElementById("list-now");
    if (!now) {
      now = document.createElement("p");
      now.id = "list-now";
      now.className = "list-now";
      now.setAttribute("role", "status");
      now.setAttribute("dir", uiDir);
      document.body.appendChild(now);
    }
    now.textContent = "";
    var item = items[index];
    withTitle(now, said, "title", String((item && item.title) || setName));
    if (item && item.open) {
      now.appendChild(document.createTextNode(" "));
      var open = document.createElement("a");
      open.className = "list-now-open";
      open.textContent = t("reader.list.open-it", "Open it");
      open.addEventListener("click", function () {
        var seconds = withTime && handed ? handed.element.currentTime : 0;
        open.href = keyed(addressOf(item, list, index, true, withTime, seconds));
      });
      open.href = keyed(addressOf(item, list, index, true, withTime));
      now.appendChild(open);
    }
  }

  function endOfList() {
    handed.at = items.length;
    tellHere(items.length);
    lockScreen(items.length - 1, false);
    var now = document.getElementById("list-now");
    if (now) now.remove();
    var over = document.createElement("p");
    over.id = "list-now";
    over.className = "list-now";
    over.setAttribute("role", "status");
    over.setAttribute("dir", uiDir);
    withTitle(over, t("reader.list.end-of", "That's the end of {name}."), "name", setName);
    document.body.appendChild(over);
  }

  function playItem(index) {
    return recordingOf(index).then(function (src) {
      if (!handed) return;
      handed.at = index;
      tellHere(index);
      if (!src) {
        // Nothing to hear: it waits to be read, and the queue waits with it.
        lockScreen(index, false);
        drawNow(t("reader.list.up-to-read", "Up next, to read: {title}"), index, false);
        return;
      }
      var element = handed.element;
      var rate = element.playbackRate || 1;
      element.src = src;
      element.playbackRate = rate;
      element.defaultPlaybackRate = rate;
      var started = element.play();
      if (started && started.catch) started.catch(function () {});
      lockScreen(index, true);
      drawNow(
        t("reader.list.now-playing", "Now playing {at} of {count}: {title}", {
          at: index + 1,
          count: items.length,
        }),
        index,
        true
      );
      var after = neighbours(items, index).next;
      if (after !== null) recordingOf(after);
    });
  }

  // The player becomes another item's: this page's own reading lets go of it.
  function handOver(index) {
    if (index === null || index === undefined) return false;
    if (!handed) {
      var player = window.TargumPlayer;
      var element = player && player.release ? player.release() : null;
      if (!element) return false;
      handed = { element: element, at: at };
      document.body.classList.add("list-handed");
      element.addEventListener("ended", handedEnded);
    }
    playItem(index);
    return true;
  }

  function handedEnded() {
    if (!handed || handed.at >= items.length) return;
    var next = neighbours(items, handed.at).next;
    if (next === null) return endOfList();
    playItem(next);
  }

  function ownEnded() {
    if (handed) return;
    var listening = wasFollowing && (document.hidden || playOn());
    wasFollowing = false;
    if (!listening || near.next === null) return;
    if (!document.hidden) {
      // Play on, with the screen in front of them: on, the way a swipe goes.
      forward("play-on", false, true);
      return;
    }
    // Listened to its end: finished, without marking, as a swipe finishes it.
    var reader = window.TargumReader;
    if (reader && reader.press) reader.press(false);
    keepFigures(reader);
    handOver(near.next);
  }

  // Previous and next on the lock screen, a headset or a keyboard's media keys: between
  // items. With the screen in front of the reader, a press like Next and Back.
  function lockKeys() {
    if (typeof navigator === "undefined" || !navigator.mediaSession) return;
    var session = navigator.mediaSession;
    function set(action, run) {
      try {
        session.setActionHandler(action, run);
      } catch (e) {}
    }
    set("nexttrack", function () {
      var from = handed ? handed.at : at;
      var next = neighbours(items, from).next;
      if (next === null) return;
      if (handed || document.hidden) handOver(next);
      else forward("lock-next", false, true);
    });
    set("previoustrack", function () {
      var from = handed ? handed.at : at;
      var back = neighbours(items, Math.min(from, items.length)).back;
      if (back === null) return;
      if (handed || document.hidden) handOver(back);
      else backward("lock-back");
    });
  }

  // The player of this page, once the reader has drawn it: its end, and the lock screen.
  function listenTo() {
    var player = window.TargumPlayer;
    var element = player && player.element ? player.element() : null;
    if (!element) return false;
    // Read while it plays: by the time it has ended the reader has already stopped.
    element.addEventListener("timeupdate", function () {
      if (!handed && !element.paused) wasFollowing = !!(player.following && player.following());
    });
    element.addEventListener("ended", ownEnded);
    element.addEventListener("play", function () {
      if (!handed) lockScreen(at, true);
    });
    // Named from the start, so the lock screen has it whenever the voice begins.
    lockScreen(at, !element.paused);
    lockKeys();
    // Arriving listening: where the voice had got to, and on from there (`addressOf`).
    var seconds = Number(asked.get("t") || 0);
    if (asked.get("listen") === "1" || seconds > 0) {
      var arrive = function () {
        if (seconds > 0 && player.seek) player.seek(seconds);
        if (asked.get("listen") === "1" && player.play) player.play();
      };
      if (player.length && player.length() > 0) setTimeout(arrive, 0);
      else
        element.addEventListener(
          "loadedmetadata",
          function () {
            setTimeout(arrive, 0);
          },
          { once: true }
        );
    }
    var next = near.next;
    if (next !== null) recordingOf(next);
    return true;
  }

  /* Play on (design.md §12, 2026-10-09): the reader's own say that, with the screen in
     front of them, the end of a recording moves on. Kept on this device; off until they
     turn it on. */
  function playOnSwitch() {
    var press = document.createElement("button");
    press.type = "button";
    press.className = "list-play-on";
    press.textContent = t("reader.list.play-on", "Play on");
    press.title = t("reader.list.play-on-title", "When a recording ends, the next one starts");
    press.setAttribute("aria-pressed", playOn() ? "true" : "false");
    press.addEventListener("click", function () {
      var on = press.getAttribute("aria-pressed") !== "true";
      choosePlayOn(on);
      // Every copy: the foot's, and the one among the picture's keys in Theatre.
      Array.prototype.forEach.call(document.querySelectorAll(".list-play-on"), function (one) {
        one.setAttribute("aria-pressed", on ? "true" : "false");
      });
    });
    return press;
  }

  /* At a desk, the playlist's pictures down the side (board PlaylistSwipeDesk): the one
     here marked, the end at the foot, and a step either way. A picture is a press like
     Next. On a phone the swipe and the foot are the way through. */
  var wideRail = window.matchMedia ? window.matchMedia("(min-width: 64rem)") : null;
  function drawRail() {
    if (document.getElementById("list-rail")) return;
    var rail = document.createElement("aside");
    rail.id = "list-rail";
    rail.className = "list-rail";
    rail.setAttribute("aria-label", t("reader.list.label", "Your playlist"));
    rail.setAttribute("dir", uiDir);
    var name = document.createElement("p");
    name.className = "list-rail-name";
    var bdi = document.createElement("bdi");
    bdi.setAttribute("dir", "auto");
    bdi.textContent = setName;
    name.appendChild(bdi);
    rail.appendChild(name);
    var where = document.createElement("p");
    where.className = "list-rail-at";
    where.textContent = t("reader.list.of", "{at} of {count}", { at: at + 1, count: items.length });
    rail.appendChild(where);
    var up = control("list-rail-step list-rail-up", "↑", function () {
      backward("rail");
    });
    up.setAttribute("aria-label", t("reader.list.back", "Back"));
    up.disabled = near.back === null;
    rail.appendChild(up);
    var strip = document.createElement("ol");
    strip.className = "list-rail-items";
    items.forEach(function (item, index) {
      var row = document.createElement("li");
      var here = index === at;
      var tile = document.createElement(here || !item.open ? "span" : "a");
      tile.className = "list-rail-tile" + (here ? " is-here" : "") + (item.open ? "" : " is-waiting");
      if (here) tile.setAttribute("aria-current", "true");
      else if (item.open) tile.href = keyed(addressOf(item, list, index, index > at));
      tile.setAttribute("aria-label", String(item.title || ""));
      tile.title = String(item.title || "");
      var src = pictureOf(item);
      var letter = document.createElement("span");
      letter.className = "list-rail-letter";
      letter.setAttribute("aria-hidden", "true");
      letter.textContent = String(item.title || "?").replace(/^[^\wא-תЀ-ӿ]+/, "").charAt(0);
      tile.appendChild(letter);
      if (src) {
        var picture = new Image();
        picture.alt = "";
        picture.onload = function () {
          letter.remove();
          tile.insertBefore(picture, tile.firstChild);
        };
        picture.src = src;
      }
      if (here) tile.appendChild(glyph(PLAYING, "list-rail-playing"));
      row.appendChild(tile);
      strip.appendChild(row);
    });
    var end = document.createElement("li");
    end.className = "list-rail-end";
    end.textContent = t("reader.list.rail-end", "End");
    strip.appendChild(end);
    rail.appendChild(strip);
    var down = control("list-rail-step list-rail-down", "↓", function () {
      forward("rail-next");
    });
    down.setAttribute("aria-label", near.next !== null ? t("reader.list.next", "Next") : t("reader.list.done", "Finish"));
    rail.appendChild(down);
    document.body.appendChild(rail);
    document.body.classList.add("has-list-rail");
    var shown = strip.querySelector(".is-here");
    if (shown && shown.scrollIntoView) shown.scrollIntoView({ block: "nearest" });
  }

  /* The wheel, at a desk: on to the next item only at the end of a text, and only by a
     turn of the wheel begun there, as the swipe and the arrow (design.md §12,
     2026-10-09). A scroll that carried on into the end was reading. */
  var wheel = { sum: 0, at: 0, end: false, start: false, spent: false };
  document.addEventListener(
    "wheel",
    function (event) {
      if (!items.length || event.ctrlKey || handed) return;
      if (event.target && event.target.closest && event.target.closest(".card, .sheet, .list-rail, .bar-pop, .bar-more, .list"))
        return;
      var now = Date.now();
      if (now - wheel.at > 300) {
        wheel = { sum: 0, at: now, end: atEnd(), start: atStart(), spent: false };
      }
      wheel.at = now;
      if (wheel.spent) return;
      wheel.sum += event.deltaY;
      if (wheel.sum > 80 && wheel.end && atEnd()) {
        wheel.spent = true;
        forward("wheel");
      } else if (wheel.sum < -80 && wheel.start && atStart() && near.back !== null) {
        wheel.spent = true;
        backward("wheel");
      }
    },
    { passive: true }
  );

  function whenPlayer(run) {
    if (run()) return;
    var tries = 0;
    var again = setInterval(function () {
      if (run() || ++tries > 40) clearInterval(again);
    }, 250);
  }

  /* Whether this item has been read to its end, so a swipe may leave it. Watching, the
   * picture is the whole item and there is nothing to scroll. Reading, it is the foot of
   * the last page — the reader's own answer, where it gives one — and the bottom of the
   * window. */
  function watchingNow() {
    // A large picture with its transcript put away: there is nothing to scroll (#422).
    var body = document.body.classList;
    return body.contains("film-theatre") && !body.contains("film-panel");
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
