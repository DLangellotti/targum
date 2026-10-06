// The build card (design.md §12, "A card in someone else's chat", 2026-10-06).
//
// A host that draws MCP Apps puts this page in a sandboxed frame beside a `check_job`
// result and talks to it over postMessage, JSON-RPC 2.0, as the MCP Apps extension
// (SEP-1865, spec 2026-01-26) says: the card asks `ui/initialize`, is told the host's
// theme and what it can do, says `ui/notifications/initialized`, and is handed the tool
// result in `ui/notifications/tool-result`. ChatGPT speaks the same bridge; its older
// `window.openai` is read only where the bridge never answers.
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

  var root = document.documentElement;
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

  var host = null;
  var asked = 0;
  var waiting = {};
  var job = "";
  var began = Date.now();
  var following = false;
  var misses = 0;
  var ended = false;
  var superseded = false;
  var channel = null;

  function send(message) {
    message.jsonrpc = "2.0";
    window.parent.postMessage(message, "*");
  }

  function request(method, params) {
    return new Promise(function (resolve, reject) {
      asked += 1;
      waiting[asked] = { resolve: resolve, reject: reject };
      send({ id: asked, method: method, params: params || {} });
    });
  }

  function notify(method, params) {
    send({ method: method, params: params || {} });
  }

  // -- the theme -------------------------------------------------------------------

  function themed(context) {
    var theme = context && context.theme;
    if (theme === "dark" || theme === "light") {
      root.setAttribute("data-theme", theme);
    }
  }

  // Before the host says anything: ChatGPT's global, or the frame's own preference,
  // so the first paint is not a light card in a dark room.
  if (window.openai && window.openai.theme) {
    themed({ theme: window.openai.theme });
  } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    themed({ theme: "dark" });
  }

  // -- drawing the rows ------------------------------------------------------------

  function rowsOf(result) {
    if (!result) return null;
    if (result.structuredContent && typeof result.structuredContent === "object") {
      return result.structuredContent;
    }
    // A host that passed only the text: it is the same JSON (`mcp_http._call`).
    var content = result.content || [];
    for (var i = 0; i < content.length; i += 1) {
      if (content[i] && content[i].type === "text") {
        try {
          return JSON.parse(content[i].text);
        } catch (error) {
          return null;
        }
      }
    }
    return null;
  }

  function show(result, mirrored) {
    var rows = rowsOf(result);
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
    var bridge = host && (host.hostCapabilities || {}).serverTools;
    if (host && (bridge || !(window.openai && window.openai.callTool))) {
      return request("tools/call", { name: "check_job", arguments: args });
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
    if (!url) return;
    event.preventDefault();
    if (host) {
      request("ui/open-link", { url: url }).catch(function () {
        window.open(url, "_blank", "noopener");
      });
    } else if (window.openai && typeof window.openai.openExternal === "function") {
      window.openai.openExternal({ href: url });
    } else {
      window.open(url, "_blank", "noopener");
    }
  });

  // -- the bridge ------------------------------------------------------------------

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var message = event.data;
    if (!message || message.jsonrpc !== "2.0") return;
    if (message.method === undefined && message.id !== undefined) {
      var pending = waiting[message.id];
      if (!pending) return;
      delete waiting[message.id];
      if (message.error) pending.reject(message.error);
      else pending.resolve(message.result);
      return;
    }
    if (message.method === "ui/notifications/tool-input") {
      var given = (message.params || {}).arguments || {};
      if (given.id) job = String(given.id);
    } else if (message.method === "ui/notifications/tool-result") {
      show(message.params, false);
    } else if (message.method === "ui/notifications/host-context-changed") {
      themed(message.params);
    } else if (message.id !== undefined) {
      // A request from the host — `ping`, or `ui/resource-teardown` before the frame
      // goes. Nothing to clean up: an empty answer is the whole reply.
      send({ id: message.id, result: {} });
    }
  });

  var tall = 0;
  function measured() {
    if (!host) return;
    var height = Math.ceil(root.getBoundingClientRect().height);
    if (height === tall) return;
    tall = height;
    notify("ui/notifications/size-changed", {
      width: Math.ceil(root.getBoundingClientRect().width),
      height: height,
    });
  }
  if (window.ResizeObserver) new ResizeObserver(measured).observe(card);

  request("ui/initialize", {
    protocolVersion: "2026-01-26",
    appCapabilities: { availableDisplayModes: ["inline"] },
    clientInfo: { name: "targum", version: "1" },
  }).then(function (result) {
    host = result || {};
    themed(host.hostContext);
    notify("ui/notifications/initialized");
    measured();
  });

  // ChatGPT's own globals, for a frame the bridge never answers.
  if (window.openai && window.openai.toolOutput) {
    show({ structuredContent: window.openai.toolOutput }, false);
  }
  window.addEventListener("openai:set_globals", function (event) {
    var globals = (event.detail || {}).globals || {};
    if (globals.theme) themed({ theme: globals.theme });
    if (globals.toolOutput && !host) show({ structuredContent: globals.toolOutput }, false);
  });
})();
