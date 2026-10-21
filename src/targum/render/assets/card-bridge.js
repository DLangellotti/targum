// What every card says to its host (design.md §12, "A card in someone else's chat",
// 2026-10-06). Split out of the build card the day the text card was built, so the two
// speak the bridge one way and a fix to it is made once.
//
// A host that draws MCP Apps puts a card in a sandboxed frame beside a tool's result and
// talks to it over postMessage, JSON-RPC 2.0, as the MCP Apps extension (SEP-1865, spec
// 2026-01-26) says: the card asks `ui/initialize`, is told the host's theme and what it
// can do, says `ui/notifications/initialized`, and is handed the tool result in
// `ui/notifications/tool-result`. ChatGPT speaks the same bridge; its older
// `window.openai` is read only where the bridge never answers.
//
// This file names no tool and asks for none. It draws nothing either: a card hands it
// what to do with a result, and it hands back the means to ask the host something and
// to open a page of ours. Whatever a card may ask for is named in that card's own file,
// where `test_cards.py` reads it.

var TargumCard = (function () {
  "use strict";

  var root = document.documentElement;

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

  // The rows a result carries: `structuredContent` where the host passed it, and the
  // same JSON read out of the text where it passed only that (`mcp_http._call`).
  function rowsOf(result) {
    if (!result) return null;
    if (result.structuredContent && typeof result.structuredContent === "object") {
      return result.structuredContent;
    }
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

  // One card, started: `on.result(result)` for each tool result, `on.input(arguments)`
  // for what the model asked, and `watched`, the element whose size the host is told.
  function start(on, watched) {
    var host = null;
    var asked = 0;
    var waiting = {};

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

    // A page of ours, opened by the host where it can, and by the frame where not.
    function open(url) {
      if (!url) return;
      if (host) {
        request("ui/open-link", { url: url }).catch(function () {
          window.open(url, "_blank", "noopener");
        });
      } else if (window.openai && typeof window.openai.openExternal === "function") {
        window.openai.openExternal({ href: url });
      } else {
        window.open(url, "_blank", "noopener");
      }
    }

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
        if (on.input) on.input((message.params || {}).arguments || {});
      } else if (message.method === "ui/notifications/tool-result") {
        on.result(message.params || {});
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
    if (window.ResizeObserver && watched) new ResizeObserver(measured).observe(watched);

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

    // ChatGPT's own globals, for a frame the bridge never answers. Its `_meta` arrives
    // apart from its rows, as `toolResponseMetadata`.
    function openaiResult(globals) {
      return { structuredContent: globals.toolOutput, _meta: globals.toolResponseMetadata };
    }
    if (window.openai && window.openai.toolOutput) {
      on.result(openaiResult(window.openai));
    }
    window.addEventListener("openai:set_globals", function (event) {
      var globals = (event.detail || {}).globals || {};
      if (globals.theme) themed({ theme: globals.theme });
      if (globals.toolOutput && !host) on.result(openaiResult(globals));
    });

    return {
      request: request,
      open: open,
      host: function () {
        return host;
      },
    };
  }

  return { start: start, rowsOf: rowsOf };
})();
