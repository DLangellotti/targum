/* targum Connect's moving parts (targum-internal#80, remade 2026-09-24).

   Three things, none of them needed to read the page or to set anything up:

   - the conversation in the hero, which plays three examples in two apps;
   - the tabs of apps, and beside each app's steps a small picture of that app walking
     through them, with a pointer doing the pressing;
   - the Copy buttons.

   With JavaScript off every app's steps stand one under another and the conversation is
   the first example, drawn still. With reduced motion the pictures still change when a
   step is chosen, but nothing moves on its own.

   The apps' menus are drawn in English whatever the page's language, because they are
   the apps' words and not ours: a reader looks for "Connectors" in the menu that says
   "Connectors". What targum says in them goes through the catalogue.
*/
(function () {
  "use strict";

  var words = window.TargumStrings || {};
  var t =
    typeof words.t === "function"
      ? words.t
      : function (key, english, fill) {
          return english.replace(/\{(\w+)\}/g, function (all, name) {
            return fill && name in fill ? fill[name] : all;
          });
        };
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.body.classList.add("js");

  var CANCEL = {};
  function sleep(ms, still) {
    return new Promise(function (done, fail) {
      setTimeout(function () {
        if (still && !still()) fail(CANCEL);
        else done();
      }, reduced ? 0 : ms);
    });
  }
  function make(tag, cls, html) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html != null) node.innerHTML = html;
    return node;
  }
  function esc(text) {
    return String(text).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  // Writes `text` into `node` a few letters at a time, the way somebody types it.
  function type(node, text, still, pace) {
    if (reduced) { node.textContent = text; return Promise.resolve(); }
    var letters = Array.from(text), i = 0, step = pace || 38;
    node.classList.add("caret");
    return new Promise(function (done, fail) {
      (function next() {
        if (still && !still()) { node.classList.remove("caret"); return fail(CANCEL); }
        i = Math.min(letters.length, i + (letters.length > 40 ? 2 : 1));
        node.textContent = letters.slice(0, i).join("");
        if (i >= letters.length) { node.classList.remove("caret"); return done(); }
        setTimeout(next, step);
      })();
    });
  }

  var MARK = (document.querySelector(".kicker .mark") || {}).outerHTML || "";
  function logoOf(tab) {
    var svg = document.querySelector("#tab-" + tab + " .logo");
    return svg ? svg.outerHTML : "";
  }
  var CHECK = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var addressButton = document.querySelector(".address-card [data-copy]");
  var ADDRESS = addressButton ? addressButton.getAttribute("data-copy") : "https://targum.page/mcp";

  /* ---- the app's name in the headline ----------------------------------------------- */
  // The names and marks are the tabs' own, so the headline can only name an app the
  // steps cover. Still under reduced motion: a name that changes by itself is motion.
  var rotor = document.getElementById("rotor");
  var names = Array.prototype.filter.call(document.querySelectorAll(".plat"), function (tab) {
    return tab.id !== "tab-other";
  }).map(function (tab) {
    return [tab.querySelector(".logo").outerHTML, tab.querySelector("span").textContent];
  });
  if (rotor && names.length > 1 && !reduced) {
    var turn = 0;
    rotor.style.inlineSize = rotor.getBoundingClientRect().width + "px";
    setInterval(function () {
      if (document.hidden) return;
      turn = (turn + 1) % names.length;
      var old = rotor.querySelector(".rotor-name:not(.leave)");
      var next = make("span", "rotor-name enter", names[turn][0] + "<span></span>");
      next.lastChild.textContent = names[turn][1];
      rotor.appendChild(next);
      var pad = rotor.getBoundingClientRect().width - old.getBoundingClientRect().width;
      rotor.style.inlineSize = next.getBoundingClientRect().width + pad + "px";
      old.classList.add("leave");
      setTimeout(function () { old.remove(); }, 450);
    }, 2400);
  }

  /* ---- Copy ------------------------------------------------------------------------ */
  document.querySelectorAll(".copy").forEach(function (button) {
    button.hidden = false;
    var label = button.querySelector("span");
    var said = label.textContent;
    button.addEventListener("click", function () {
      var text = button.getAttribute("data-copy");
      function copied() {
        button.classList.add("done");
        label.textContent = t("connect.demo.copied", "Copied");
        setTimeout(function () { button.classList.remove("done"); label.textContent = said; }, 1600);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(copied, function () { select(button); });
      } else select(button);
    });
  });
  // Where the clipboard is refused, the text is selected so a press of the keys copies it.
  function select(button) {
    var code = button.parentNode.querySelector("code");
    var range = document.createRange();
    range.selectNodeContents(code);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  /* ---- the conversation ------------------------------------------------------------ */
  var thread = document.getElementById("demoThread");
  var host = document.getElementById("demoHost");
  var scenesEl = document.getElementById("scenes");
  var replay = document.getElementById("replay");
  var chips = scenesEl ? scenesEl.querySelectorAll(".scene") : [];

  function you(text, hebrew) {
    var m = make("div", "msg you in");
    var p = make("p", hebrew ? "he" : "");
    m.appendChild(p);
    thread.appendChild(m);
    return p;
  }
  function tool(working) {
    var chip = make("div", "tool in", '<span class="tool-glyph">' + MARK + "</span><span></span>");
    chip.lastChild.textContent = working;
    thread.appendChild(chip);
    return chip;
  }
  function toolDone(chip, said) {
    chip.classList.add("done");
    chip.lastChild.textContent = said;
  }
  function them(html) {
    var m = make("div", "msg them in", html);
    thread.appendChild(m);
    return m;
  }
  function find(title, kind, share) {
    return '<div class="find"><span class="t">' + esc(title) + '</span><span class="k">' + esc(kind) + '</span><span class="open">' +
      esc(t("connect.demo.open", "Open")) + '</span><span class="meter"><i data-share="' + share + '"></i></span></div>';
  }
  function fillMeters(node) {
    node.querySelectorAll("[data-share]").forEach(function (bar, n) {
      bar.style.inlineSize = "0%";
      bar.style.transition = "inline-size 700ms cubic-bezier(0.2, 0.8, 0.2, 1) " + (120 * n + 150) + "ms";
      requestAnimationFrame(function () { requestAnimationFrame(function () { bar.style.inlineSize = bar.getAttribute("data-share") + "%"; }); });
    });
  }

  var SCENES = [
    {
      host: "claude", name: "Claude", length: 9500,
      play: async function (still) {
        await sleep(400, still);
        await type(you(), t("connect.demo.find-me-something-short-to-read-about-food", "Find me something short to read about food. Nothing too hard."), still);
        await sleep(350, still);
        var chip = tool(t("connect.demo.targum-is-searching-the-library", "targum is searching the library"));
        await sleep(1300, still);
        toolDone(chip, t("connect.demo.found-three-texts-at-your-level", "targum found three texts at your level"));
        await sleep(350, still);
        var m = them("<p></p><div class=\"finds\">" +
          find(t("connect.demo.shakshuka-in-ten-minutes", "Shakshuka in ten minutes"), t("connect.demo.video-you-know-80", "Video · you know 80%"), 80) +
          find(t("connect.demo.this-week-s-news-easy", "This week’s news · easy"), t("connect.demo.article-you-know-90", "Article · you know 90%"), 90) +
          find(t("connect.demo.homemade-hummus-step-by-step", "Homemade hummus, step by step"), t("connect.demo.video-you-know-70", "Video · you know 70%"), 70) +
          "</div>");
        m.firstChild.textContent = t("connect.demo.here-are-three-you-ll-mostly-understand", "Here are three you’ll mostly understand:");
        fillMeters(m);
        await sleep(1200, still);
        var note = make("p", "en in");
        note.textContent = t("connect.demo.each-opens-in-targum", "Each one opens in targum, with vowels and English beside every line.");
        m.appendChild(note);
      }
    },
    {
      host: "chatgpt", name: "ChatGPT", length: 11500,
      play: async function (still) {
        await sleep(400, still);
        await type(you("", true), "השקשוקה שלי היה טעים", still, 70);
        await sleep(350, still);
        var chip = tool(t("connect.demo.targum-is-checking-your-hebrew", "targum is checking your Hebrew"));
        await sleep(1300, still);
        toolDone(chip, t("connect.demo.targum-checked-your-hebrew", "targum checked your Hebrew"));
        await sleep(350, still);
        var m = them("<div class=\"recast\"><span class=\"tag\"></span><p class=\"he\">הַשַּׁקְשׁוּקָה שֶׁלִּי <mark>הָיְתָה</mark> <mark>טְעִימָה</mark>.</p></div>");
        m.querySelector(".tag").textContent = t("connect.demo.corrected", "Corrected");
        await sleep(900, still);
        var why = make("p", "why-line in", '<span class="he">שַׁקְשׁוּקָה</span> ');
        why.appendChild(document.createTextNode(t("connect.demo.is-feminine-so-the-verb-and-the-adjective-are-too", "is feminine, so the verb and the adjective are too.")));
        m.appendChild(why);
        await sleep(1200, still);
        var reply = make("p", "he in", "נִשְׁמָע טָעִים. מָה שַׂמְתָּ בִּפְנִים?");
        m.appendChild(reply);
        var fold = make("button", "fold-en in");
        fold.type = "button";
        fold.textContent = t("connect.demo.english", "English");
        m.appendChild(fold);
        var en = make("p", "en in");
        en.textContent = t("connect.demo.sounds-delicious-what-did-you-put-in-it", "Sounds delicious. What did you put in it?");
        fold.addEventListener("click", function () { fold.replaceWith(en); });
        await sleep(1300, still);
        if (fold.isConnected) fold.replaceWith(en);
        await sleep(500, still);
        var kept = make("p", "noted in", CHECK + "<span></span>");
        kept.lastChild.textContent = t("connect.demo.kept-on-your-record", "Kept on your record, to work on later");
        thread.appendChild(kept);
      }
    },
    {
      host: "claude", name: "Claude", length: 10500,
      play: async function (still) {
        await sleep(400, still);
        await type(you(), t("connect.demo.what-was-i-working-on-this-week", "What was I working on this week?"), still);
        await sleep(350, still);
        var chip = tool(t("connect.demo.targum-is-reading-your-record", "targum is reading your record"));
        await sleep(1300, still);
        toolDone(chip, t("connect.demo.targum-read-your-record", "targum read your record"));
        await sleep(350, still);
        var m = them('<div class="stat"><div><b class="tnum">3</b><span></span></div><div><b class="tnum">41</b><span></span></div><div><b class="tnum">2,140</b><span></span></div></div><p></p>');
        var labels = m.querySelectorAll(".stat span");
        labels[0].textContent = t("connect.demo.texts-finished", "texts finished");
        labels[1].textContent = t("connect.demo.new-words", "new words");
        labels[2].textContent = t("connect.demo.words-known", "words known");
        m.lastChild.textContent = t("connect.demo.these-five-keep-coming-back", "These five keep coming back:");
        await sleep(700, still);
        var list = make("div", "words");
        m.appendChild(list);
        var WORDS = [
          ["מַחֲבַת", t("connect.demo.gloss-frying-pan", "frying pan")],
          ["רֹטֶב", t("connect.demo.gloss-sauce", "sauce")],
          ["הִתְחַמֵּם", t("connect.demo.gloss-to-heat-up", "to heat up")],
          ["יְשִׁירוֹת", t("connect.demo.gloss-straight", "straight")],
          ["שָׁבַר", t("connect.demo.gloss-to-break", "to break")]
        ];
        for (var i = 0; i < WORDS.length; i++) {
          var w = make("span", "in", '<b class="he"></b><small></small>');
          w.firstChild.textContent = WORDS[i][0];
          w.lastChild.textContent = WORDS[i][1];
          list.appendChild(w);
          await sleep(160, still);
        }
        await sleep(700, still);
        var ask = make("p", "in");
        ask.textContent = t("connect.demo.want-to-see-them-where-you-met-them", "Want to see them in the sentences you met them in?");
        m.appendChild(ask);
      }
    }
  ];

  var sceneAt = 0, sceneRun = 0, heroSeen = true, heroPinned = false;
  function setHost(scene) {
    host.classList.add("swap");
    setTimeout(function () {
      host.innerHTML = logoOf(scene.host) + "<span></span>";
      host.lastChild.textContent = scene.name;
      host.classList.remove("swap");
    }, reduced ? 0 : 160);
  }
  async function playScene(n) {
    var run = ++sceneRun;
    var still = function () { return run === sceneRun; };
    sceneAt = n;
    var scene = SCENES[n];
    chips.forEach(function (chip, i) {
      chip.setAttribute("aria-pressed", String(i === n));
      var bar = chip.querySelector("i");
      bar.classList.remove("run");
      if (i === n && !reduced && !heroPinned) {
        chip.style.setProperty("--run", scene.length + 2200 + "ms");
        void bar.offsetWidth;
        bar.classList.add("run");
      }
    });
    setHost(scene);
    thread.textContent = "";
    try {
      await scene.play(still);
      if (reduced || heroPinned) return;
      await sleep(2200, still);
      while (!heroSeen) await sleep(400, still);
      playScene((n + 1) % SCENES.length);
    } catch (e) {
      if (e !== CANCEL) throw e;
    }
  }
  if (scenesEl && thread) {
    scenesEl.hidden = false;
    replay.hidden = false;
    chips.forEach(function (chip, i) {
      chip.addEventListener("click", function () { heroPinned = true; playScene(i); });
    });
    replay.addEventListener("click", function () {
      heroPinned = false;
      var demo = document.getElementById("demo");
      var r = demo.getBoundingClientRect();
      if (r.top < 0 || r.bottom > window.innerHeight) demo.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
      playScene(0);
    });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (seen) { heroSeen = seen[0].isIntersecting; }).observe(document.getElementById("demo"));
    }
    playScene(0);
  }

  /* ---- the apps' own screens -------------------------------------------------------- */
  // What each app looks like, drawn small: the menu the steps name, the button they press
  // and the questions it asks. `frames` walks through them, and `step` says which of the
  // steps beside the picture each frame belongs to.
  var SIGN_IN = "Opening your browser to sign in…";
  var APPS = {
    claude: {
      kind: "app", name: "Claude", side: ["General", "Account", "Privacy", "Connectors"], pick: 3,
      title: "Connectors", add: "Add custom connector",
      dialog: { title: "Add custom connector", fields: [["Name", "targum"], ["Remote MCP server URL", ADDRESS]], ok: "Add" },
      client: "Claude",
      frames: [["menu", 0], ["press", 1], ["dialog", 2], ["grant", 3], ["done", 3]]
    },
    chatgpt: {
      kind: "app", name: "ChatGPT", side: ["General", "Personalization", "Apps & Connectors", "Security"], pick: 2,
      title: "Apps & Connectors", add: "Create", toggle: "Developer mode",
      dialog: { title: "New connector", fields: [["Name", "targum"], ["MCP server URL", ADDRESS], ["Authentication", "OAuth", true]], ok: "Create" },
      client: "ChatGPT",
      frames: [["menu", 0], ["toggle", 1], ["press", 2], ["dialog", 2], ["grant", 3], ["done", 3]]
    },
    other: {
      kind: "app", name: "", side: ["General", "Integrations", "Privacy"], pick: 1,
      title: "Integrations", add: "Add server",
      dialog: { title: "Remote MCP server", fields: [["URL", ADDRESS], ["Transport", "HTTP", true], ["Sign-in", "OAuth", true]], ok: "Add" },
      client: "",
      frames: [["menu", 0], ["dialog", 1], ["grant", 2], ["done", 2]]
    },
    code: {
      kind: "term", name: "Terminal", client: "Claude Code",
      frames: [
        ["term", 0, [["$ ", "claude mcp add --transport http targum " + ADDRESS], ["", "Added HTTP MCP server targum with URL: " + ADDRESS + " to local config", "out"]]],
        ["term", 1, [["$ ", "claude"], ["> ", "/mcp"], ["", "Manage MCP servers", "out"], ["", "› targum · needs authentication", "pick"]]],
        ["term", 2, [["", "targum MCP server", "out"], ["", "› 1. Authenticate", "pick"], ["", SIGN_IN, "out"]]],
        ["grant", 2],
        ["term", 2, [["", "Authentication successful. Connected to targum.", "ok"]]]
      ]
    },
    gemini: {
      kind: "term", name: "Terminal", client: "Gemini CLI",
      frames: [
        ["term", 0, [["$ ", "gemini mcp add --transport http targum " + ADDRESS], ["", "MCP server \"targum\" added to project settings. (http)", "out"]]],
        ["term", 1, [["$ ", "gemini"], ["> ", "/mcp auth targum"], ["", SIGN_IN, "out"]]],
        ["grant", 2],
        ["term", 2, [["", "Successfully authenticated with MCP server 'targum'.", "ok"]]]
      ]
    },
    codex: {
      kind: "term", name: "Terminal", client: "Codex",
      frames: [
        ["term", 0, [["$ ", "codex mcp add targum --url " + ADDRESS], ["", "Added global MCP server 'targum'.", "out"]]],
        ["term", 1, [["$ ", "codex mcp login targum"], ["", SIGN_IN, "out"]]],
        ["grant", 2],
        ["term", 2, [["", "Successfully logged in to MCP server 'targum'.", "ok"]]]
      ]
    },
    vscode: {
      kind: "code", name: "Visual Studio Code", client: "Visual Studio Code",
      frames: [["palette", 0], ["transport", 1], ["url", 1], ["grant", 2], ["agent", 3]]
    }
  };

  var POINTER = '<svg class="pointer" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.8v11.4l3.1-2.9 2 4.4 1.9-.9-2-4.3h4.3z" fill="currentColor" stroke="var(--card)" stroke-width="1" stroke-linejoin="round"/></svg>';

  function windowOf(app, plat) {
    return '<div class="sc"><div class="sc-top"><span class="dots"><i></i><i></i><i></i></span>' +
      (app.name ? logoOf(plat) : "") + "<span>" + esc(app.name || "") + "</span></div>";
  }
  function settings(app, plat, opts) {
    var side = app.side.map(function (item, n) {
      return '<span class="' + (n === app.pick && opts.picked ? "on" : "") + '">' + esc(item) + "</span>";
    }).join("");
    var main = '<div class="sc-main"><p class="sc-h">' + esc(opts.picked ? app.title : app.side[0]) + "</p>";
    if (opts.picked) {
      if (app.toggle) main += '<p class="sc-p">Advanced settings</p><div class="sc-row"><span>' + esc(app.toggle) + '</span><span class="sc-switch' + (opts.toggled ? " on" : "") + '" data-hit="toggle"></span></div>';
      if (opts.done) main += '<div class="sc-row in">' + MARK + '<span>targum</span><span class="ok">' + CHECK + esc(t("connect.screen.connected", "Connected")) + "</span></div>";
      else main += '<p class="sc-p">' + esc(t("connect.screen.nothing-added-yet", "Nothing added yet")) + "</p>";
      if (!opts.done) main += '<span class="sc-btn' + (opts.pressed ? " pressed" : "") + '" data-hit="add">+ ' + esc(app.add) + "</span>";
      if (opts.done) main += '<div class="sc-chat in"><span class="sc-bubble">' + esc(t("connect.screen.find-me-something-to-read-in-hebrew", "Find me something to read in Hebrew")) + "</span></div>";
    } else {
      main += '<p class="sc-p">' + esc(t("connect.screen.your-settings", "Your settings")) + "</p>";
    }
    main += "</div>";
    return windowOf(app, plat) + '<div class="sc-body"><div class="sc-side">' + side + "</div>" + main + "</div></div>";
  }
  function dialog(app) {
    var fields = app.dialog.fields.map(function (f, n) {
      return '<div class="sc-field"><label>' + esc(f[0]) + '</label><span class="' + (f[2] ? "plain" : "") + '" data-field="' + n + '"></span></div>';
    }).join("");
    return '<div class="sc-veil"><div class="sc-dialog"><p class="sc-h">' + esc(app.dialog.title) + "</p>" + fields +
      '<span class="sc-btn" data-hit="ok">' + esc(app.dialog.ok) + "</span></div></div>";
  }
  function grant(app) {
    var scopes = [
      t("connect.scope.library", "Search the library and look up what is at a link"),
      t("connect.scope.record", "Read your words, your mistakes and how far you have got"),
      t("connect.scope.chat", "Read what you write and keep it, mark words, turn on a language you practise, and price a text")
    ];
    return '<div class="sc-grant"><div class="grant"><span class="sc-url">' + esc(ADDRESS.replace(/^https?:\/\//, "").replace(/\/mcp$/, "")) + "/oauth/authorize</span>" +
      '<p class="grant-brand">' + MARK + "<span>targum</span></p>" +
      '<p class="grant-title">' + esc(t("connect.screen.connect-to-targum", "Connect {client} to targum", { client: app.client || t("connect.screen.your-app", "your app") })) + "</p>" +
      '<ul class="grant-list">' + scopes.map(function (s, n) { return '<li data-scope="' + n + '"><span class="box"></span><span>' + esc(s) + "</span></li>"; }).join("") + "</ul>" +
      '<p class="grant-press"><span class="btn cta small" data-hit="connect">' + esc(t("connect.screen.connect", "Connect")) + "</span></p></div></div>";
  }
  function terminal(app, lines) {
    return '<div class="sc"><div class="sc-top"><span class="dots"><i></i><i></i><i></i></span><span>' + esc(app.name) + '</span></div><div class="sc-term">' +
      lines.map(function (l, n) { return '<div class="ln ' + (l[2] || "") + '" data-line="' + n + '"></div>'; }).join("") + "</div></div>";
  }
  function editor(app, plat, inner) {
    return windowOf(app, plat) + '<div class="sc-body"><div class="sc-side"><span>Explorer</span><span>Search</span><span class="on">Chat</span><span>Extensions</span></div><div class="sc-main">' + inner + "</div></div></div>";
  }

  function Screen(panel) {
    this.panel = panel;
    this.plat = panel.getAttribute("data-plat");
    this.app = APPS[this.plat];
    this.el = panel.querySelector(".screen");
    this.steps = panel.querySelectorAll(".steps > li");
    this.run = 0;
    this.pinned = false;
    var self = this;
    this.steps.forEach(function (li, n) {
      li.tabIndex = 0;
      function choose(e) {
        if (e.target.closest && e.target.closest(".copy")) return;
        self.pinned = true;
        self.play(self.firstFrameOf(n), true);
      }
      li.addEventListener("click", choose);
      li.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(e); }
      });
    });
  }
  Screen.prototype.firstFrameOf = function (step) {
    for (var i = 0; i < this.app.frames.length; i++) if (this.app.frames[i][1] === step) return i;
    return 0;
  };
  Screen.prototype.mark = function (step) {
    this.steps.forEach(function (li, n) {
      li.classList.toggle("now", n === step);
      li.classList.toggle("past", n < step);
      if (n === step) li.setAttribute("aria-current", "step");
      else li.removeAttribute("aria-current");
    });
  };
  Screen.prototype.stop = function () { this.run++; };
  // Moves the pointer onto whatever `hit` names, and taps.
  Screen.prototype.point = async function (hit, still) {
    var target = this.el.querySelector('[data-hit="' + hit + '"]');
    var pointer = this.el.querySelector(".pointer");
    if (!target || !pointer || reduced) return;
    var box = this.el.getBoundingClientRect(), at = target.getBoundingClientRect();
    var x = at.left - box.left + at.width * 0.6, y = at.top - box.top + at.height * 0.55;
    if (document.dir === "rtl") x = x - box.width;
    pointer.classList.add("shown");
    pointer.style.transform = "translate(" + x + "px, " + y + "px)";
    await sleep(760, still);
    pointer.classList.remove("tap");
    void pointer.getBoundingClientRect();
    pointer.classList.add("tap");
    await sleep(260, still);
  };
  Screen.prototype.draw = function (html) {
    var keep = this.el.querySelector(".pointer");
    this.el.innerHTML = html + (keep ? keep.outerHTML : POINTER);
    var pointer = this.el.querySelector(".pointer");
    if (keep) pointer.style.transform = keep.style.transform;
    if (keep && keep.classList.contains("shown")) pointer.classList.add("shown");
  };
  // Draws one frame and acts it out. Whatever it types, it types; whatever it presses,
  // the pointer goes to first.
  Screen.prototype.frame = async function (n, still) {
    var app = this.app, plat = this.plat, frame = app.frames[n], kind = frame[0];
    this.mark(frame[1]);
    if (kind === "menu") {
      this.draw(settings(app, plat, { picked: false }));
      await sleep(500, still);
      var item = this.el.querySelectorAll(".sc-side span")[app.pick];
      item.setAttribute("data-hit", "pick");
      await this.point("pick", still);
      this.draw(settings(app, plat, { picked: true }));
      await sleep(1100, still);
    } else if (kind === "toggle") {
      this.draw(settings(app, plat, { picked: true }));
      await this.point("toggle", still);
      this.el.querySelector(".sc-switch").classList.add("on");
      await sleep(1000, still);
    } else if (kind === "press") {
      this.draw(settings(app, plat, { picked: true, toggled: !!app.toggle }));
      await this.point("add", still);
      this.el.querySelector('[data-hit="add"]').classList.add("pressed");
      await sleep(600, still);
    } else if (kind === "dialog") {
      this.draw(settings(app, plat, { picked: true, toggled: !!app.toggle, pressed: true }));
      this.el.querySelector(".sc").insertAdjacentHTML("beforeend", dialog(app));
      await sleep(400, still);
      for (var f = 0; f < app.dialog.fields.length; f++) {
        var field = app.dialog.fields[f];
        await type(this.el.querySelector('[data-field="' + f + '"]'), field[1], still, field[1].length > 20 ? 22 : 60);
        await sleep(200, still);
      }
      await this.point("ok", still);
      await sleep(300, still);
    } else if (kind === "grant") {
      this.draw(grant(app));
      await sleep(600, still);
      var rows = this.el.querySelectorAll("[data-scope]");
      for (var r = 0; r < rows.length; r++) {
        rows[r].classList.add("on");
        await sleep(reduced ? 0 : 380, still);
      }
      await this.point("connect", still);
      await sleep(400, still);
    } else if (kind === "done") {
      this.draw(settings(app, plat, { picked: true, toggled: !!app.toggle, done: true }));
      await sleep(2200, still);
    } else if (kind === "term") {
      var lines = frame[2];
      this.draw(terminal(app, lines));
      for (var l = 0; l < lines.length; l++) {
        var ln = this.el.querySelector('[data-line="' + l + '"]');
        if (lines[l][0]) {
          ln.innerHTML = '<span class="ps">' + esc(lines[l][0]) + "</span><span></span>";
          await sleep(300, still);
          await type(ln.lastChild, lines[l][1], still, 24);
          await sleep(350, still);
        } else {
          ln.textContent = lines[l][1];
          ln.classList.add("in");
          await sleep(450, still);
        }
      }
      await sleep(1300, still);
    } else if (kind === "palette" || kind === "transport" || kind === "url") {
      var q = kind === "palette" ? "> MCP: Add Server" : "";
      var opts = kind === "palette"
        ? [["MCP: Add Server…", true], ["MCP: List Servers", false], ["MCP: Show Installed Servers", false]]
        : kind === "transport"
          ? [["Command (stdio)", false], ["HTTP (HTTP or Server-Sent Events)", true], ["NPM Package", false]]
          : [];
      var inner = '<div class="sc-palette"><div class="q" data-q></div>' +
        opts.map(function (o) { return '<div class="opt" data-opt="' + (o[1] ? "on" : "") + '">' + esc(o[0]) + "</div>"; }).join("") + "</div>";
      if (kind === "url") inner = '<div class="sc-palette"><div class="opt">Enter Server URL</div><div class="q" data-q></div><div class="opt">Enter Server ID</div><div class="q" data-q2></div></div>';
      this.draw(editor(app, plat, '<p class="sc-h">Chat</p>' + inner));
      if (kind === "url") {
        await type(this.el.querySelector("[data-q]"), ADDRESS, still, 22);
        await sleep(300, still);
        await type(this.el.querySelector("[data-q2]"), "targum", still, 60);
      } else {
        if (q) await type(this.el.querySelector("[data-q]"), q, still, 45);
        await sleep(350, still);
        var on = this.el.querySelector('[data-opt="on"]');
        on.classList.add("on");
        on.setAttribute("data-hit", "opt");
        await this.point("opt", still);
      }
      await sleep(900, still);
    } else if (kind === "agent") {
      this.draw(editor(app, plat, '<p class="sc-h">Chat · Agent</p><div class="sc-row in">' + MARK + '<span>targum</span><span class="ok">' + CHECK + esc(t("connect.screen.connected", "Connected")) +
        '</span></div><div class="sc-chat"><span class="sc-bubble" data-q></span></div>'));
      await sleep(400, still);
      await type(this.el.querySelector("[data-q]"), t("connect.screen.find-me-something-to-read-in-hebrew", "Find me something to read in Hebrew"), still, 40);
      await sleep(2000, still);
    }
  };
  Screen.prototype.play = async function (from, once) {
    var run = ++this.run, self = this;
    var still = function () { return run === self.run; };
    try {
      var n = from || 0;
      while (!once && !reduced && !screenSeen) await sleep(300, still);
      for (;;) {
        await this.frame(n, still);
        if (reduced || once) return;
        while (!screenSeen) await sleep(400, still);
        n = (n + 1) % this.app.frames.length;
        if (n === 0) await sleep(800, still);
      }
    } catch (e) {
      if (e !== CANCEL) throw e;
    }
  };
  /* ---- the tabs --------------------------------------------------------------------- */
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".plat"));
  var panels = document.querySelectorAll(".panel");
  var screens = {};
  var current = null, screenSeen = false;
  panels.forEach(function (panel) {
    var s = new Screen(panel);
    if (!s.app || !s.el) return;
    s.el.hidden = false;
    screens[s.plat] = s;
  });
  function choose(tab, focus) {
    tabs.forEach(function (other) {
      var on = other === tab;
      other.setAttribute("aria-selected", String(on));
      other.tabIndex = on ? 0 : -1;
      document.getElementById(other.getAttribute("aria-controls")).hidden = !on;
    });
    if (focus) tab.focus();
    var plat = tab.id.replace("tab-", "");
    if (current) current.stop();
    current = screens[plat] || null;
    if (current) { current.pinned = false; current.play(0, reduced); }
  }
  if (tabs.length) {
    document.getElementById("plats").hidden = false;
    tabs.forEach(function (tab, n) {
      tab.addEventListener("click", function () { choose(tab, false); });
      tab.addEventListener("keydown", function (e) {
        var go = { ArrowRight: n + 1, ArrowLeft: n - 1, Home: 0, End: tabs.length - 1 }[e.key];
        if (go == null) return;
        e.preventDefault();
        choose(tabs[(go + tabs.length) % tabs.length], true);
      });
    });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (seen) { screenSeen = seen[0].isIntersecting; }, { threshold: 0.2 }).observe(document.querySelector(".panels"));
    } else screenSeen = true;
    choose(tabs[0], false);
  }
})();
