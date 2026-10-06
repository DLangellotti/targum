// The text card (design.md §12, "A card in someone else's chat", 2026-10-06).
//
// A host that draws MCP Apps puts this page in a sandboxed frame beside a `find_text`,
// `open_library_text` or `search_sources` result. How it talks to the host is `card-bridge.js`, inlined
// before this file and shared with the build card; this file is what the text card does
// with what it hears.
//
// What the card may do, and all it may do:
//   - draw each text it was handed, in the host's theme: the title in the reading face
//     (Hebrew right to left), the English title, how long it is, how much of it the
//     reader knows, said the way the app says it;
//   - ask the host to open a text's door, a page of ours, when the reader presses it;
//   - for an article a publisher put out (`search_sources`, 2026-10-06), which is not on
//     targum yet, say who published it, and make the door our add page with its address
//     already in the box. Never the publisher's page: the reader came to read it here.
//   - play a recording the text already has, from the short-lived address the result
//     carries in `_meta`, when the reader presses Listen. That is the one thing it ever
//     loads, and only into the one `<audio>` on the page.
//
// It asks for no tool at all. Its rows are the tool result, its doors and recordings
// came with them, and a card never presses (§12). `test_cards.py` holds that.

(function () {
  "use strict";

  var list = document.getElementById("cards");
  var none = document.getElementById("none");
  var one = document.getElementById("one");
  var ear = document.getElementById("ear");

  var HEBREW = /[֐-׿]/;
  // What `mcp_http.TEXT_CARD_META` names: the rows' doors and recordings.
  var META = "targum.page/texts";
  var TENTHS = [];
  try {
    TENTHS = JSON.parse(list.getAttribute("data-tenths") || "[]");
  } catch (error) {
    TENTHS = [];
  }
  var PACE = Number(list.getAttribute("data-pace")) || 130;

  var bridge = null;
  var playing = null;
  var shown = [];

  function said(name, fill) {
    var text = list.getAttribute("data-" + name) || "";
    Object.keys(fill || {}).forEach(function (key) {
      text = text.split("{" + key + "}").join(String(fill[key]));
    });
    return text;
  }

  // How much of it the reader knows, in tenths, the way `level.words_in_ten` says it.
  function known(share) {
    if (share === null || share === undefined || share === "") return "";
    var tenths = Math.max(0, Math.min(10, Math.round(Number(share) * 10)));
    return isNaN(tenths) ? "" : TENTHS[tenths] || "";
  }

  // The minutes the library gives, or a shelf text's words at the library's own pace,
  // or a found video's or episode's own length. A found article gives none: its feed
  // carries a summary, not the article, so it says nothing rather than guess.
  function minutes(row) {
    var given = Number(row.minutes) || 0;
    if (!given && Number(row.words) > 0) given = Math.max(1, Math.round(Number(row.words) / PACE));
    if (!given && Number(row.seconds) > 0) given = Math.max(1, Math.round(Number(row.seconds) / 60));
    return given ? said("minutes", { n: given }) : "";
  }

  // What the door to a found item says: what the reader will do with it there.
  function arriving(row) {
    if (row.kind === "video") return said("watch-on");
    if (row.kind === "podcast") return said("listen-on");
    return said("read-on");
  }

  // -- the recording ---------------------------------------------------------------

  function idle(button) {
    button.setAttribute("aria-pressed", "false");
    button.querySelector(".card-play-word").textContent = said("listen");
  }

  function silence() {
    if (playing) idle(playing);
    playing = null;
    ear.pause();
  }

  function gone(button) {
    if (playing === button) silence();
    button.hidden = true;
    var credit = button.parentNode.querySelector(".card-credit");
    if (credit) credit.hidden = true;
  }

  function listen(button, audio) {
    if (playing === button) {
      silence();
      return;
    }
    silence();
    // Past its twenty minutes the address opens nothing; the button goes rather than
    // failing when pressed.
    if (Date.now() >= Number(audio.ends)) {
      gone(button);
      return;
    }
    playing = button;
    button.setAttribute("aria-pressed", "true");
    button.querySelector(".card-play-word").textContent = said("pause");
    if (ear.getAttribute("data-for") !== audio.src) {
      ear.setAttribute("data-for", audio.src);
      ear.src = audio.src;
    }
    var started = ear.play();
    if (started && started.catch) {
      started.catch(function () {
        if (playing === button) gone(button);
      });
    }
  }

  ear.addEventListener("ended", silence);
  ear.addEventListener("error", function () {
    if (playing) gone(playing);
  });

  // -- drawing the rows ------------------------------------------------------------

  function draw(row, beside, found) {
    var card = one.content.firstElementChild.cloneNode(true);
    var title = card.querySelector(".card-title");
    var name = String(row.title || row.name || "");
    title.textContent = name;
    if (HEBREW.test(name)) {
      title.setAttribute("dir", "rtl");
      title.setAttribute("lang", row.language === "arc" ? "arc" : "he");
    }

    var english = card.querySelector(".card-english");
    var gloss = String(row.english || "");
    english.textContent = gloss;
    english.hidden = !gloss || gloss === name;

    var facts = card.querySelector(".card-facts");
    var from = found ? String(row.publisher || "") : "";
    var length = minutes(row);
    var share = known(row.known_share);
    [
      [".card-from", from],
      [".card-minutes", length],
      [".card-known", share],
    ].forEach(function (pair) {
      var part = card.querySelector(pair[0]);
      part.textContent = pair[1];
      part.hidden = !pair[1];
    });
    facts.hidden = !from && !length && !share;

    var door = card.querySelector(".card-door");
    // A found item's door comes only from beside it: its own `link` is the publisher's.
    var url = String(beside.door || (found ? "" : row.reader) || "");
    if (url) {
      door.setAttribute("href", url);
      door.textContent = found ? arriving(row) : row.reader ? said("open") : said("library");
      door.hidden = false;
      door.addEventListener("click", function (event) {
        event.preventDefault();
        if (bridge) bridge.open(url);
      });
    }

    var audio = found ? null : beside.audio;
    if (audio && audio.src && Number(audio.ends) > Date.now()) {
      var button = card.querySelector(".card-play");
      idle(button);
      button.setAttribute("aria-label", said("listen") + " · " + name);
      button.hidden = false;
      button.addEventListener("click", function () {
        listen(button, audio);
      });
      window.setTimeout(function () {
        gone(button);
      }, Math.max(0, Number(audio.ends) - Date.now()));
      if (audio.credit) {
        var credit = card.querySelector(".card-credit");
        credit.textContent = said("read-by", { who: audio.credit });
        credit.hidden = false;
      }
    }
    return card;
  }

  function show(result) {
    var rows = TargumCard.rowsOf(result);
    if (!rows) return;
    var meta = (result && result._meta && result._meta[META]) || [];
    silence();
    shown.forEach(function (card) {
      card.remove();
    });
    shown = [];
    if (rows.error) {
      none.textContent = String(rows.error);
      none.hidden = false;
      return;
    }
    var found = Array.isArray(rows.items);
    var texts = found ? rows.items : Array.isArray(rows.texts) ? rows.texts : rows.title ? [rows] : [];
    none.hidden = texts.length > 0;
    list.classList.toggle("stack", texts.length > 1);
    texts.forEach(function (row, n) {
      var card = draw(row || {}, meta[n] || {}, found);
      list.appendChild(card);
      shown.push(card);
    });
  }

  // -- the bridge ------------------------------------------------------------------

  bridge = TargumCard.start({ result: show }, list);
})();
