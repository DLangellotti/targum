// The build card (design.md §12, "A card in someone else's chat", 2026-10-06).
//
// A host that draws MCP Apps puts this page in a sandboxed frame beside a `check_job`
// result. How it talks to the host is `card-bridge.js`, inlined before this file and
// shared with the text card; this file is what the build card does with what it hears.
//
// What the card may do, and all it may do:
//   - draw the rows it was handed, in the host's theme;
//   - ask the host to call `check_job` again, with `wait_seconds`, until the build is
//     done or has stopped. That tool is read only and free, and it is the only tool
//     named in this file — a card never presses (§12). `test_cards.py` holds that;
//   - ask the host to open the door, a page of ours, when the reader presses it.
//
// It fetches nothing. Everything it shows came in from the tool result.

(function () {
  "use strict";

  var card = document.getElementById("card");
  var label = document.getElementById("label");
  var title = document.getElementById("title");
  var english = document.getElementById("english");
  var bar = document.getElementById("bar");
  var fill = document.getElementById("fill");
  var said = document.getElementById("said");
  var stopped = document.getElementById("stopped");
  var door = document.getElementById("door");

  // The longest a held `check_job` waits, the tool's own `WAIT_MOST`.
  var WAIT = 25;
  // A card stops following after an hour and says so; asking again in the chat draws a
  // new card. A build longer than that is rare, and a frame left open in a tab nobody
  // is reading should not ask the host something every half minute for a day.
  var LONGEST = 60 * 60 * 1000;
  // Three failed asks in a row and the card stops, rather than retrying for ever.
  var MISSES = 3;
  var ENDED = { done: true, failed: true, blocked: true };
  var HEBREW = /[֐-׿]/;

  var bridge = null;
  var job = "";
  var began = Date.now();
  var following = false;
  var misses = 0;
  var ended = false;
  var superseded = false;
  var channel = null;

  // -- drawing the rows ------------------------------------------------------------

  function show(result, mirrored) {
    var rows = TargumCard.rowsOf(result);
    if (!rows) return;
    if (rows.error) {
      said.textContent = rows.error;
      label.textContent = card.getAttribute("data-not-ready");
      stop(false);
      return;
    }
    if (rows.id) job = String(rows.id);
    var stage = String(rows.stage || "");
    card.setAttribute("data-stage", stage);

    var name = String(rows.title || "");
    title.textContent = name;
    title.hidden = !name;
    if (HEBREW.test(name)) {
      title.setAttribute("dir", "rtl");
      title.setAttribute("lang", rows.language === "arc" ? "arc" : "he");
    } else {
      title.setAttribute("dir", "auto");
      title.removeAttribute("lang");
    }
    var gloss = String(rows.english || "");
    english.textContent = gloss;
    english.hidden = !gloss || gloss === name;

    var total = Number(rows.total) || 0;
    var done = Math.min(Number(rows.done) || 0, total);
    var share = stage === "done" ? 100 : total > 0 ? Math.round((done / total) * 100) : 0;
    bar.hidden = !(stage === "done" || (stage === "working" && total > 0));
    fill.style.inlineSize = share + "%";
    bar.setAttribute("aria-valuenow", String(share));

    if (rows.said) said.textContent = String(rows.said);

    if (stage === "done") {
      label.textContent = card.getAttribute("data-ready");
    } else if (stage === "failed" || stage === "blocked") {
      label.textContent = card.getAttribute("data-not-ready");
    } else {
      label.textContent = card.getAttribute("data-working");
    }

    if (rows.open) {
      door.setAttribute("href", String(rows.open));
      door.hidden = false;
    } else {
      door.removeAttribute("href");
      door.hidden = true;
    }

    if (!mirrored && channel && job) {
      channel.postMessage({ job: job, began: began, result: { structuredContent: rows } });
    }
    if (ENDED[stage]) {
      stop(false);
      return;
    }
    if (!mirrored) follow();
  }

  function stop(saying) {
    ended = true;
    if (saying) stopped.hidden = false;
  }

  // -- following the build ---------------------------------------------------------

  // The one tool this card may ask for, and the only tool named in this file.
  function check(args) {
    var host = bridge && bridge.host();
    var serving = host && (host.hostCapabilities || {}).serverTools;
    if (host && (serving || !(window.openai && window.openai.callTool))) {
      return bridge.request("tools/call", { name: "check_job", arguments: args });
    }
    if (window.openai && typeof window.openai.callTool === "function") {
      return window.openai.callTool("check_job", args);
    }
    return Promise.reject(new Error("no host to ask"));
  }

  function follow() {
    if (following || ended || superseded || !job) return;
    if (Date.now() - began > LONGEST) {
      stop(true);
      return;
    }
    following = true;
    check({ id: job, wait_seconds: WAIT }).then(
      function (result) {
        following = false;
        misses = 0;
        show(result, false);
      },
      function () {
        following = false;
        misses += 1;
        if (misses >= MISSES) {
          stop(true);
          return;
        }
        window.setTimeout(follow, 5000 * misses);
      }
    );
  }

  // Each `check_job` the model makes draws a card of its own, and they would all follow
  // the same build. The youngest follows and says what it heard; the older ones listen.
  try {
    channel = new BroadcastChannel("targum-build-card");
    channel.onmessage = function (event) {
      var heard = event.data || {};
      if (!heard.job || heard.job !== job || heard.began <= began) return;
      superseded = true;
      show(heard.result, true);
    };
  } catch (error) {
    channel = null;
  }

  // -- the door --------------------------------------------------------------------

  door.addEventListener("click", function (event) {
    var url = door.getAttribute("href");
    if (!url || !bridge) return;
    event.preventDefault();
    bridge.open(url);
  });

  // -- the bridge ------------------------------------------------------------------

  bridge = TargumCard.start(
    {
      input: function (given) {
        if (given.id) job = String(given.id);
      },
      result: function (result) {
        show(result, false);
      },
    },
    card
  );
})();
