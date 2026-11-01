/* Your account (boards AccountDesk, AccountPhone, ConnYou; design.md §12, "Your account
 * is the board's sections", 2026-10-09): the languages you are learning and the one you
 * read into, what is connected, and the half of an account that is slow or impossible to
 * undo. Credits and the plan are `account.js`'s, which knows the month.
 *
 * The languages live on the account and nowhere else. A preference in the browser is
 * swept on sign-out with everything else `targum:*`, on purpose, and would be forgotten
 * every time somebody signed out on their own machine; `sync.js` keeps a copy of the
 * account's answer the way it keeps a copy of the words, and that copy is a cache, not a
 * second setting. What the reader is looking at right now — which switcher is pressed —
 * is a different question and stays in the browser.
 */

(function () {
  "use strict";

  // The page's words in the reader's language, from `strings.js` (targum-internal#184).
  var t = window.TargumStrings.t;
  var tn = window.TargumStrings.tn;
  var SIGNED_OUT = t("you.signed-out", "You've been signed out. Sign in again.");
  var SAVED = t("you.saved", "Saved.");

  var key = window.TARGUM_KEY;

  // `/account/me`, asked once for the whole page and shared: `keep.js` (targum-internal#484).
  function meOnce(address, options) {
    return window.targumMe ? window.targumMe(address, options) : fetch(address, options);
  }

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: key
        ? { "Content-Type": "application/json", "X-Targum-Key": key }
        : { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  var panels = ["languages", "ending"];

  function at(id) {
    return document.getElementById(id);
  }

  function show(signedIn) {
    at("stranger").hidden = signedIn;
    panels.forEach(function (name) {
      at(name).hidden = !signedIn;
    });
  }

  // One card on show, every other card in `main` put away: the states that are not the
  // account (loading, unreachable, offline) and the one after Delete.
  function only(id) {
    var cards = document.querySelectorAll("main.account > section");
    for (var n = 0; n < cards.length; n++) cards[n].hidden = cards[n].id !== id;
  }

  function say(where, message, bad, again) {
    var node = at(where);
    node.hidden = !message;
    node.textContent = message || "";
    // An error and "Saved." were the same sentence in the same ink, and the only way to
    // tell them apart was to read them. A refusal is a line with the clay mark, and Try
    // again where there is something to try again (design.md §12, 2026-10-09); it was a
    // sentence in clay.
    node.classList.toggle("bad", !!bad);
    if (bad && message && window.TargumFault) {
      node.textContent = "";
      node.appendChild(window.TargumFault.line(message, "", again || null, true));
    }
  }

  /* A day as the page's language writes it, in the one form the page uses (targum-
     internal#469, polish 3 and 4): the day and the month in full, as credits and the plan
     say "November 1", with the year only when it isn't this one, and never broken from
     its month at the end of a line. Connections and Telegram said "Oct 12, 2026". */
  function day(stamp) {
    var root = document.documentElement;
    try {
      var when = new Date(stamp);
      var form = { day: "numeric", month: "long" };
      if (when.getFullYear() !== new Date().getFullYear()) form.year = "numeric";
      return when.toLocaleDateString((root && root.lang) || "en", form).replace(/ /g, "\u00a0");
    } catch (e) {
      return "";
    }
  }

  /* A row as Your languages draws one (targum-internal#469, polish 6): its name over a
     quiet line at the start, which `clamp` holds to two lines, and the press at the end.
     Prompts and Telegram were bare items, the name in plain body and the text a size up
     in ink, which turned the hierarchy over. */
  function acctRow(name, says, press, clamp) {
    var row = document.createElement("li");
    row.className = "row";
    var main = document.createElement("span");
    main.className = "row-main";
    var called = document.createElement("span");
    called.className = "acct-name";
    called.textContent = name;
    var what = document.createElement("span");
    what.className = clamp ? "acct-says acct-clamp" : "acct-says";
    what.textContent = says;
    main.appendChild(called);
    main.appendChild(what);
    var end = document.createElement("span");
    end.className = "acct-end";
    end.appendChild(press);
    row.appendChild(main);
    row.appendChild(end);
    return row;
  }

  function grouped(count) {
    return String(count).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  /* --- who you are ----------------------------------------------------------- */

  // The address, on the Account card. The name is no longer asked here (the board draws
  // none); the Hebrew form of address is a row of Your languages (`drawAddress`).
  function drawWho(who) {
    at("you-email").textContent = who.email || "";
  }

  /* --- your languages ---------------------------------------------------------- */

  /* As the board draws them: a row each language being learned, with Remove where it
     may go; Start another, from the rest; and the language meanings, translations and
     the menus are in. What the account said is kept here and sent whole, because the
     account is told what the set is, not what changed. */
  var learning = ["he"];
  var reads = ["en"];

  function named(rows, code) {
    for (var n = 0; n < rows.length; n++) if (rows[n].code === code) return rows[n].name;
    return code;
  }

  function option(value, text, chosen) {
    var one = document.createElement("option");
    one.value = value;
    one.textContent = text;
    if (chosen) one.selected = true;
    return one;
  }

  function drawLearning() {
    var list = at("you-learning");
    var rows = window.TARGUM_READING || [];
    var required = window.TARGUM_REQUIRED || [];
    list.textContent = "";
    rows.forEach(function (row) {
      if (learning.indexOf(row.code) < 0) return;
      var line = document.createElement("li");
      line.className = "row";
      line.setAttribute("data-code", row.code);
      var main = document.createElement("span");
      main.className = "row-main";
      var name = document.createElement("span");
      name.className = "acct-name";
      name.textContent = row.name;
      main.appendChild(name);
      var says = document.createElement("span");
      says.className = "acct-says";
      says.textContent = t("you.page.learning", "Learning");
      main.appendChild(says);
      line.appendChild(main);
      // The one that stays on has no Remove: the server holds the same line.
      if (required.indexOf(row.code) < 0) {
        var gone = document.createElement("button");
        gone.type = "button";
        gone.className = "btn ghost outline";
        gone.textContent = t("you.remove", "Remove");
        gone.setAttribute("aria-label", t("you.remove-named", "Remove {language}", { language: row.name }));
        gone.addEventListener("click", function () {
          if (learning.length <= 1) return say("you-languages-said", t("you.keep-one-language", "This is your only language, so it stays. Start another to remove this one."));
          learning = learning.filter(function (code) {
            return code !== row.code;
          });
          saveLanguages();
        });
        line.appendChild(gone);
      }
      list.appendChild(line);
    });

    var start = at("you-start");
    start.textContent = "";
    start.appendChild(option("", t("you.choose", "Choose…"), true));
    var more = 0;
    rows.forEach(function (row) {
      if (learning.indexOf(row.code) >= 0) return;
      start.appendChild(option(row.code, row.name, false));
      more += 1;
    });
    // Nothing left to start: the row says so by not being there.
    var startRow = start.parentNode;
    if (startRow && startRow.tagName === "LI") startRow.hidden = !more;
  }

  /* One language for meanings, translations and the menus: it is one setting on the
     account (`strings.reading_language`), so it is one control here. An account that
     reads into both keeps that answer as a choice of its own. */
  function drawReads() {
    var pick = at("you-reads");
    var rows = window.TARGUM_INTO || [];
    pick.textContent = "";
    rows.forEach(function (row) {
      var own = window.TargumLang && window.TargumLang.native ? window.TargumLang.native(row.code) : null;
      var text = own && own.textContent ? own.textContent : row.name;
      pick.appendChild(option(row.code, text, reads.length === 1 && reads[0] === row.code));
    });
    if (reads.length > 1) {
      pick.appendChild(
        option(
          reads.join(" "),
          reads.length === 2
            ? t("you.reads.both", "{one} and {other}", { one: named(rows, reads[0]), other: named(rows, reads[1]) })
            : reads
                .map(function (code) {
                  return named(rows, code);
                })
                .join(", "),
          true
        )
      );
    }
  }

  function drawLanguages(who) {
    learning = (who.learning || ["he"]).slice();
    reads = (who.reads || ["en"]).slice();
    drawLearning();
    drawReads();
    drawAddress();
  }

  /* How the conversation says "you" in Hebrew: 'm', 'f', or '' where they have not said.
     A row of Your languages, there only while Hebrew is being learned, and saved on the
     press at the endpoint that has always kept it. */
  var address = "";

  function drawAddress() {
    var row = at("you-address-row");
    if (row) row.hidden = learning.indexOf("he") < 0;
    ["m", "f"].forEach(function (form) {
      var press = at("address-" + form);
      if (press) press.setAttribute("aria-checked", String(address === form));
    });
  }

  function wireAddress() {
    ["m", "f"].forEach(function (form) {
      var press = at("address-" + form);
      if (!press) return;
      press.addEventListener("click", function () {
        if (address === form) return;
        ask("/account/address", { address: form }).then(function (answer) {
          if (answer.error || answer.signedIn === false) {
            drawAddress();
            return say("you-languages-said", answer.error || SIGNED_OUT, true);
          }
          address = answer.address || "";
          drawAddress();
          say("you-languages-said", SAVED);
        });
      });
    });
  }

  var savingLanguages = null;

  function saveLanguages() {
    // Once, a moment after the last change: two presses together are one change.
    clearTimeout(savingLanguages);
    savingLanguages = setTimeout(function () {
      ask("/account/languages", {
        learning: learning.slice(),
        reads: reads.slice(),
      }).then(function (answer) {
        // Drawn back from the answer either way. What the account kept is what stands,
        // and a refused change puts its rows back rather than showing what was asked.
        if (answer.learning || answer.reads) drawLanguages(answer);
        if (answer.error || answer.signedIn === false) {
          return say("you-languages-said", answer.error || SIGNED_OUT);
        }
        say("you-languages-said", SAVED);
        // The pages that offer a language read the account's answer through sync, so
        // asking it to look again is what makes them agree.
        if (window.TargumSync) window.TargumSync.start(true);
        // The menus are in the language read into: a change there is a new page.
        // `strings.reading_language`: the one language read into other than English, or
        // English.
        var before = (window.TargumStrings && window.TargumStrings.language) || "en";
        var others = (answer.reads || reads).filter(function (code) {
          return code !== "en";
        });
        var now = others.length === 1 ? others[0] : "en";
        if (now !== before && window.location && window.location.reload) window.location.reload();
      });
    }, 400);
  }

  function wireLanguages() {
    at("you-start").addEventListener("change", function () {
      var code = at("you-start").value;
      if (!code || learning.indexOf(code) >= 0) return;
      learning.push(code);
      saveLanguages();
    });
    at("you-reads").addEventListener("change", function () {
      var value = at("you-reads").value;
      if (!value) return;
      reads = value.split(" ");
      saveLanguages();
    });
  }

  /* What is recorded of a sitting, and the reader's two controls over it
     (targum-internal#127). Absent where the box keeps no such record. Erasing asks twice,
     the way leaving does: it cannot be put back. */
  function drawRecord(who) {
    var panel = at("record");
    var events = who && who.events;
    if (!panel || !events || !events.kept) return;
    panel.hidden = false;
    var toggle = at("record-switch");
    var erase = at("record-erase");
    var said = at("record-said");
    function tell(text) {
      said.textContent = text;
      said.hidden = !text;
    }
    function paint(on) {
      toggle.setAttribute("aria-pressed", on ? "true" : "false");
      toggle.textContent = on
        ? t("you.record.stop", "Stop recording")
        : t("you.record.start", "Start recording again");
    }
    paint(!!events.on);
    toggle.onclick = function () {
      var next = toggle.getAttribute("aria-pressed") !== "true";
      ask("/account/events", { collect: next }).then(function (answer) {
        var on = !!(answer && answer.events && answer.events.on);
        paint(on);
        tell(
          on
            ? t("you.record.started", "We're recording again from now.")
            : t("you.record.stopped", "Stopped. What's already recorded is still here until you erase it.")
        );
      });
    };
    erase.onclick = function () {
      if (erase.getAttribute("data-sure") !== "yes") {
        erase.setAttribute("data-sure", "yes");
        erase.textContent = t("you.record.sure", "Erase it for good");
        return;
      }
      ask("/account/events", { forget: true }).then(function () {
        erase.removeAttribute("data-sure");
        erase.textContent = t("you.page.record-erase", "Erase what's recorded");
        tell(t("you.record.erased", "Erased. Your words and your texts are untouched."));
      });
    };
  }

  /* Whether what the reader brings is counted with everybody's (David, 2026-11-01).
     Absent where the box pools nothing. One switch and no Erase: the pool is made again
     from nothing every night, so off is out by the morning, and nothing in it was ever
     the reader's alone to erase. */
  function drawCounting(who) {
    var panel = at("counting");
    var counting = who && who.counting;
    if (!panel || !counting || !counting.kept) return;
    panel.hidden = false;
    var toggle = at("counting-switch");
    var said = at("counting-said");
    function paint(on) {
      toggle.setAttribute("aria-pressed", on ? "true" : "false");
      toggle.textContent = on
        ? t("you.counting.stop", "Stop counting")
        : t("you.counting.start", "Start counting again");
    }
    paint(!!counting.on);
    toggle.onclick = function () {
      var next = toggle.getAttribute("aria-pressed") !== "true";
      ask("/account/counting", { count: next }).then(function (answer) {
        var on = !!(answer && answer.counting && answer.counting.on);
        paint(on);
        said.textContent = on
          ? t("you.counting.started", "We'll count your texts again from tonight.")
          : t("you.counting.stopped", "Stopped. Your texts leave the counts tonight.");
        said.hidden = false;
      });
    };
  }

  /* What holds a token for this account, and the press that ends it (#80).

     One row a connector, never a token: what is shown is that Claude is connected and
     what it may do, which is a fact about the reader. The token is a credential and is
     on no page.

     Disconnecting takes both kinds at once — an access token revoked while its refresh
     token lives is a disconnection that undoes itself within the hour — and it does not
     ask twice, because reconnecting is one press in the app it came from. */
  function drawConnections(who) {
    var panel = at("connections");
    var rows = at("connection-rows");
    var said = at("connections-said");
    if (!panel || !rows) return;

    function tell(text) {
      said.textContent = text;
      said.hidden = !text;
    }


    /* One row an app, as board ConnYou draws it. Claude registers itself afresh each
       time it is reconnected, and removing it in Claude does not tell us, so two grants
       called "Claude" are one app connected twice: one row, both dates ("Connected 22
       September, again 6 October"), and Disconnect takes both. */
    function grouped(connections) {
      var byName = {};
      var order = [];
      (connections || []).forEach(function (one) {
        var name = one.name || "";
        var key = name || "client:" + one.client;
        if (!byName[key]) {
          byName[key] = { name: name, clients: [], scopes: {}, made: [], seen: 0 };
          order.push(key);
        }
        var app = byName[key];
        app.clients.push(one.client);
        String(one.scopes || "")
          .split(" ")
          .forEach(function (scope) {
            if (scope) app.scopes[scope] = true;
          });
        if (one.made) app.made.push(one.made);
        app.seen = Math.max(app.seen, Number(one.seen) || 0);
      });
      return order.map(function (key) {
        var app = byName[key];
        app.made.sort(function (x, y) {
          return x - y;
        });
        app.scopes = Object.keys(app.scopes).join(" ");
        return app;
      });
    }

    /* When it was connected (and again, where it was reconnected), and when it was last
       used. */
    function whenSaid(app) {
      if (!app.made.length) return "";
      var first = day(app.made[0]);
      var last = app.made.length > 1 ? day(app.made[app.made.length - 1]) : "";
      var said =
        last && last !== first
          ? t("you.connections.connected-again", "Connected {made}, reconnected {again}", { made: first, again: last })
          : t("you.connections.connected-on", "Connected {made}", { made: first });
      if (app.seen) said += t("you.connections.last-used", ", last used {seen}", { seen: day(app.seen) });
      return said;
    }

    /* A small line drawing before each thing it may do (§7). */
    var GLYPH = {
      library: "M7 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM10 10l3.5 3.5",
      record: "M3 4.5h10M3 8h10M3 11.5h6",
      chat: "M3 3.5h10v7H7l-3 2.5v-2.5H3z",
    };
    function glyph(scope) {
      var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 16 16");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("focusable", "false");
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", GLYPH[scope] || GLYPH.library);
      svg.appendChild(path);
      return svg;
    }

    function paint(connections) {
      rows.textContent = "";
      var apps = grouped(connections);
      /* Drawn with nothing connected too (targum-internal#469, polish 1): one quiet line
         and "Connect an app", so the account says apps can be connected at all. */
      panel.hidden = false;
      var none = at("connections-none");
      var says = at("connections-says");
      var more = at("connect-link");
      if (none) none.hidden = !!apps.length;
      if (says) says.hidden = !apps.length;
      if (more) {
        more.textContent = apps.length
          ? t("you.page.connect-another", "Connect another app")
          : t("you.page.connect-an-app", "Connect an app");
      }
      apps.forEach(function (app) {
        var row = document.createElement("li");
        row.className = "conn-row";
        var mark = document.createElement("span");
        mark.className = "conn-mark";
        mark.setAttribute("aria-hidden", "true");
        var name = app.name || t("you.connections.an-app", "An app");
        mark.textContent = Array.from(name)[0] || "·";
        row.appendChild(mark);

        var main = document.createElement("div");
        main.className = "conn-main";
        var head = document.createElement("p");
        head.className = "conn-head";
        var title = document.createElement("b");
        title.className = "conn-name";
        title.textContent = name;
        head.appendChild(title);
        var when = document.createElement("span");
        when.className = "conn-when";
        when.textContent = whenSaid(app);
        head.appendChild(when);
        main.appendChild(head);

        var lines = mayLines(app.scopes);
        if (lines.length) {
          var may = document.createElement("p");
          may.className = "conn-may";
          may.textContent = t("you.connections.it-may", "It may:");
          main.appendChild(may);
          var list = document.createElement("ul");
          list.className = "conn-scopes";
          lines.forEach(function (line) {
            var item = document.createElement("li");
            item.appendChild(glyph(line.scope));
            var words = document.createElement("span");
            words.textContent = line.says;
            item.appendChild(words);
            list.appendChild(item);
          });
          main.appendChild(list);
        }
        row.appendChild(main);

        var press = document.createElement("button");
        press.type = "button";
        press.className = "btn ghost outline conn-off";
        press.textContent = t("you.connections.disconnect", "Disconnect");
        press.setAttribute("aria-label", t("you.connections.disconnect-named", "Disconnect {app}", { app: name }));
        press.onclick = function () {
          press.disabled = true;
          // Every grant the app holds, one after another, and the list as the last
          // answer left it.
          var last = null;
          app.clients
            .reduce(function (chain, client) {
              return chain.then(function () {
                return ask("/account/disconnect", { client: client }).then(function (answer) {
                  last = answer;
                });
              });
            }, Promise.resolve())
            .then(function () {
              paint(last && last.connections);
              tell(t("you.connections.disconnected-app", "Disconnected. {app} can't reach your account any more.", { app: name }));
            })
            .catch(function () {
              press.disabled = false;
              tell(t("you.connections.could-not", "We couldn't disconnect that. Try again."));
            });
        };
        row.appendChild(press);
        rows.appendChild(row);
      });
    }

    /* What each grant lets the app do, in the approval page's own sentences, in the
       order it listed them. Chatting is said to be included, as the approval page says
       it (design.md §12, 2026-09-24), because this is the page a reader comes to when
       they want to know what they agreed to.

       `chat` was `check` until 2026-09-23 (§12, "A cost is credits, and a credit is a
       minute"). A grant made before then still holds the old word, so this answers to
       both spellings rather than showing a reader one fewer thing than they agreed to. */
    function mayLines(scopes) {
      var held = (scopes || "").split(" ");
      var lines = [];
      if (held.indexOf("library") >= 0) {
        lines.push({ scope: "library", says: t("connect.scope.library", "Search the library and look up what is at a link") });
      }
      if (held.indexOf("record") >= 0) {
        lines.push({ scope: "record", says: t("connect.scope.record", "Read your words, your mistakes and your progress") });
      }
      if (held.indexOf("chat") >= 0 || held.indexOf("check") >= 0) {
        lines.push({
          scope: "chat",
          says:
            t("connect.scope.chat", "Send us what you write in a language you're learning, for us to correct") +
            ". " +
            t(
              "connect.scope.chat-also",
              "It can also add texts to your playlists, and suggest texts, playlists and subscriptions for you to confirm on targum."
            ) +
            // A sentence of its own since ling-en's pass (targum-internal#473), full stop and all.
            " " +
            t("you.connections.chat-included", "Chatting is included."),
        });
      }
      return lines;
    }

    paint(who && who.connections);
  }

  /* What a reader wrote for their connector to offer (#80, note 17).

     Two fields and no jargon: what to call it, and what it should do. The name is
     narrowed by the server to one lowercase word, because a host draws these as things
     to pick by name and several draw them as slash commands, where a space ends the
     name. The page does not pretend otherwise — what comes back is what was saved, and
     the row shows that.

     Drawn only where something is connected: a box for writing prompts, shown to
     somebody with no connector to show them in, is a control without a job. */
  function drawPrompts(who) {
    var panel = at("prompts");
    var rows = at("prompt-rows");
    var name = at("prompt-name");
    var says = at("prompt-says");
    var save = at("prompt-save");
    var said = at("prompts-said");
    if (!panel || !rows || !save) return;
    var connected = !!(who && who.connections && who.connections.length);

    function tell(text) {
      said.textContent = text;
      said.hidden = !text;
    }

    function paint(prompts) {
      rows.textContent = "";
      panel.hidden = !connected;
      (prompts || []).forEach(function (one) {
        var press = document.createElement("button");
        press.type = "button";
        press.className = "btn ghost outline";
        press.textContent = t("you.prompts.remove", "Remove");
        press.onclick = function () {
          press.disabled = true;
          ask("/account/prompts", { name: one.name, gone: true })
            .then(function (answer) {
              paint(answer && answer.prompts);
              tell(t("you.prompts.removed", "Removed."));
            })
            .catch(function () {
              press.disabled = false;
              tell(t("you.prompts.could-not-remove", "We couldn't remove that. Try again."));
            });
        };
        var row = acctRow(one.name, one.says, press, true);
        rows.appendChild(row);
        openable(row.querySelector && row.querySelector(".acct-clamp"));
      });
    }

    /* Clamped to two lines, a long prompt had nowhere to show the rest (qa-claude on
       #871): where it runs over, the text itself opens and closes on a press. */
    function openable(text) {
      if (!text || !(text.scrollHeight > text.clientHeight + 1)) return;
      text.tabIndex = 0;
      text.setAttribute("role", "button");
      text.setAttribute("aria-expanded", "false");
      function flip() {
        var open = text.classList.toggle("acct-open");
        text.setAttribute("aria-expanded", open ? "true" : "false");
      }
      text.addEventListener("click", flip);
      text.addEventListener("keydown", function (event) {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        flip();
      });
    }

    save.onclick = function () {
      ask("/account/prompts", { name: name.value, says: says.value })
        .then(function (answer) {
          if (answer && answer.error) {
            tell(answer.error);
            paint(answer.prompts);
            return;
          }
          paint(answer && answer.prompts);
          name.value = "";
          says.value = "";
          var written = answer && answer.written;
          tell(
            written
              ? t("you.prompts.saved", "Saved as {name}. It's in your apps now.", {
                  name: written.name,
                })
              : t("you.prompts.saved-plain", "Saved.")
          );
        })
        .catch(function () {
          tell(t("you.prompts.could-not", "We couldn't save that. Try again."));
        });
    };

    paint(who && who.prompts);
  }

  /* Accepting the contribution grant (targum-internal#164, door 3), which is the whole
     of what decides whether a word's card offers a way to correct a meaning.

     Once, and not undone from here: a correction already offered stays under the terms
     it arrived with, and withdrawing means offering no more rather than unmaking what
     was given. So the control says what it does and then says it is done, instead of
     becoming a switch that implies the first half can be taken back. */
  function drawGrant(who) {
    var panel = at("correcting");
    var go = at("grant-go");
    var said = at("grant-said");
    if (!panel || !go) return;
    if (who && who.granted) {
      go.hidden = true;
      said.hidden = false;
      said.textContent = t("you.grant.done", "You've accepted the grant, so a word's card offers a correction.");
      return;
    }
    go.textContent = t("you.page.correcting-accept", "Accept and turn it on");
    go.onclick = function () {
      go.disabled = true;
      ask("/account/grant", {}).then(function (answer) {
        if (!(answer && answer.granted)) {
          go.disabled = false;
          return;
        }
        go.hidden = true;
        said.hidden = false;
        said.textContent = t("you.grant.thanks", "Thank you. A word's card now offers a correction.");
      });
    };
  }

  /* --- your Hebrew -------------------------------------------------------------- */

  /* The rung named on arrival (design.md §12, "The arrival is two questions"). Learn asks
     it once; this is where it changes. Kept the way Learn keeps it — the account has it,
     the browser holds a copy — so a change here reaches the next page opened at once. */
  var RUNGS = ["aleph", "aleph-plus", "bet", "bet-plus", "gimel", "dalet", "hey", "vav"];

  function rungLabels() {
    return {
      "": t("you.level.none", "Not set"),
      aleph: t("learn.level.aleph", "Just starting"),
      "aleph-plus": t("learn.level.aleph-plus", "I know some words"),
      bet: t("learn.level.bet", "I can hold a simple conversation"),
      "bet-plus": t("learn.level.bet-plus", "I follow slow Hebrew with help"),
      gimel: t("learn.level.gimel", "I follow the news with a dictionary"),
      dalet: t("learn.level.dalet", "I follow most things comfortably"),
      hey: t("learn.level.hey", "I follow almost anything"),
      vav: t("learn.level.vav", "Hebrew is a language I live in"),
    };
  }

  function keepRung(rung) {
    try {
      if (rung) window.targumKeep("targum:declared", rung);
      else window.targumForget("targum:declared");
    } catch (e) {}
  }

  function drawLevel(who) {
    var pick = at("you-level");
    if (!pick) return;
    var labels = rungLabels();
    var said = RUNGS.indexOf(who.declared || "") >= 0 ? who.declared : "";
    pick.textContent = "";
    [""].concat(RUNGS).forEach(function (rung) {
      var option = document.createElement("option");
      option.value = rung;
      option.textContent = labels[rung];
      option.selected = rung === said;
      pick.appendChild(option);
    });
    pick.onchange = function () {
      ask("/account/level", { level: pick.value }).then(function (answer) {
        if (answer.error || answer.signedIn === false) {
          drawLevel({ declared: said });
          return say("you-languages-said", answer.error || SIGNED_OUT);
        }
        said = answer.declared || "";
        keepRung(said);
        say("you-languages-said", SAVED);
      });
    };
  }

  /* --- ending it -------------------------------------------------------------- */

  /* Export says when it fails and when it is done (targum-internal#469, B6). Fetched
     here rather than followed, so a session that has gone is said, not saved as a file
     named "export"; the href stays for a page with no script. */
  function wireExport() {
    var link = at("you-export");
    link.href = keyed("/account/export");
    link.addEventListener("click", function (event) {
      if (typeof fetch !== "function" || typeof Blob !== "function") return;
      event.preventDefault();
      var failed = function () {
        say("you-ending-said", t("you.export.failed", "We couldn't make the file."), true, function () {
          say("you-ending-said", "");
          link.click();
        });
      };
      fetch(keyed("/account/export"), {
        credentials: "same-origin",
        headers: key ? { "X-Targum-Key": key } : {},
      })
        .then(function (response) {
          if (response.status === 401) return say("you-ending-said", SIGNED_OUT, true);
          if (!response.ok) return failed();
          return response.blob().then(function (blob) {
            var url = URL.createObjectURL(blob);
            var save = document.createElement("a");
            save.href = url;
            save.download = "targum.json";
            document.body.appendChild(save);
            save.click();
            document.body.removeChild(save);
            setTimeout(function () {
              URL.revokeObjectURL(url);
            }, 1000);
            say("you-ending-said", t("you.export.done", "Downloaded targum.json."));
          });
        })
        .catch(failed);
    });
  }

  function ending() {
    wireExport();
    at("you-out").addEventListener("click", function () {
      // Through sync, not straight at the endpoint: signing out empties this browser's
      // store as well as ending the session, and only sync knows how to do both.
      window.TargumSync.signOut().then(function () {
        location.href = keyed("/");
      });
    });
    at("you-forget").addEventListener("click", function () {
      var press = at("you-forget");
      if (press.getAttribute("data-sure") !== "yes") {
        // Asked twice, in the button itself. A dialog for this would be a dialog nobody
        // reads; a button that changes what it says is read by everybody who presses it.
        // And a way back beside it (2026-09-14): the second question had no answer but
        // reloading the page.
        press.setAttribute("data-sure", "yes");
        press.textContent = t("you.forget.sure", "Yes, delete my account");
        var keep = at("you-keep");
        if (keep) {
          keep.hidden = false;
          // The safe choice first: the focus goes to Keep my account (§14.3).
          keep.focus();
          keep.onclick = function () {
            press.removeAttribute("data-sure");
            press.textContent = t("you.forget", "Delete account");
            keep.hidden = true;
          };
        }
        return;
      }
      press.disabled = true;
      var keeping = at("you-keep");
      if (keeping) keeping.hidden = true;
      ask("/account/forget", {})
        .then(function (answer) {
          // Success ends the session too, and answers signed out; only an error is one.
          if (answer && answer.error) {
            press.disabled = false;
            return say("you-ending-said", answer.error, true);
          }
          // One card that says what happened, focused so a screen reader hears it, and a
          // way on that the reader presses: no redirect on a timer (targum-internal#469,
          // B5). It was one line for a second and a half, then the front door.
          only("you-closed");
          at("you-closed-said").textContent =
            answer.message || t("you.closing", "We've signed you out.");
          at("you-closed").focus();
          // The words were left in this browser and the page went on showing the profile
          // (2026-09-14). Signed out here too, the way Sign out empties the browser.
          if (window.TargumSync && window.TargumSync.signOut) window.TargumSync.signOut();
        })
        .catch(function () {
          press.disabled = false;
          say(
            "you-ending-said",
            t("you.forget.unreachable", "We couldn't reach targum, so nothing was deleted."),
            true,
            function () {
              say("you-ending-said", "");
              press.click();
            }
          );
        });
    });
  }

  /* Telegram (targum-internal#328): drawn only where the server said there is a bot.
     Link asks for a fresh one-time link and follows it, which opens Telegram on the
     bot with the token in hand; each linked chat is a row with Unlink, which does not
     ask twice, because linking again is one press here. */
  function drawTelegram(who) {
    var panel = at("telegram");
    var rows = at("telegram-rows");
    var go = at("telegram-go");
    var said = at("telegram-said");
    if (!panel || !rows || !go || !who.telegram) return;
    panel.hidden = false;

    function tell(text) {
      said.textContent = text;
      said.hidden = !text;
    }


    function paint(chats) {
      rows.textContent = "";
      (chats || []).forEach(function (one) {
        var press = document.createElement("button");
        press.type = "button";
        press.className = "btn ghost outline";
        press.textContent = t("you.telegram.unlink", "Unlink");
        press.onclick = function () {
          press.disabled = true;
          ask("/account/telegram", { unlink: one.chat })
            .then(function (answer) {
              paint(answer && answer.chats);
              tell(t("you.telegram.unlinked", "Unlinked."));
            })
            .catch(function () {
              press.disabled = false;
              tell(t("you.telegram.could-not", "We couldn't do that. Try again."));
            });
        };
        rows.appendChild(
          acctRow(
            t("you.telegram.chat", "A Telegram chat"),
            t("you.telegram.linked-on", "Linked {made}", { made: day(one.linked) }),
            press,
            false
          )
        );
      });
    }

    paint(who.telegram.chats);
    go.onclick = function () {
      go.disabled = true;
      ask("/account/telegram", {})
        .then(function (answer) {
          go.disabled = false;
          if (!answer || !answer.link) throw new Error("no link");
          window.location.href = answer.link;
        })
        .catch(function () {
          go.disabled = false;
          tell(t("you.telegram.could-not", "We couldn't do that. Try again."));
        });
    };
  }

  /* --- the plan, with plans on ------------------------------------------------- */

  /* Board PlanAccount (design.md §12, "Free and Plan, behind a switch", 2026-10-09).
     Nothing at all while plans are off: the early-access card `account.js` fills is the
     plan then, as it was before the switch existed. */
  function drawPlan(who) {
    var plan = who.plan || {};
    var card = document.getElementById("plan-on");
    if (!card || !plan.on) return;
    var free = plan.plan !== "plan";
    var back = (who.hours && who.hours.ends) || "";
    var hours = Math.round((plan.planCredits || 0) / 60);
    var seeAll = document.getElementById("plan-see");
    if (seeAll) seeAll.hidden = false;
    document.getElementById("plan-free").hidden = !free;
    document.getElementById("plan-paid").hidden = free;
    if (free) {
      document.getElementById("plan-free-says").textContent = t(
        "you.plan.free-says",
        "The library, word cards and your text uploads, with {n} credits a month",
        { n: plan.credits }
      );
      document.getElementById("plan-offer").textContent = t(
        "you.plan.offer",
        "A plan gives you {n} credits a month, which is {hours} hours of audio or video. It also lets you subscribe to YouTube channels and podcasts.",
        { n: plan.planCredits, hours: hours }
      );
      if (plan.words) {
        /* Past nine in ten of the cap, the line says how many more fit and points to the
           plans (targum-internal#469, polish 10): 287 of 300 read the same as 12 of 300. */
        var listed = plan.listed || 0;
        var left = Math.max(0, plan.words - listed);
        var near = listed >= plan.words * 0.9;
        document.getElementById("plan-words").textContent = !near
          ? t("you.plan.words", "{n} of {cap} saved words. Known words don't count.", {
              n: listed,
              cap: plan.words,
            })
          : left
            ? t(
                "you.plan.words-near",
                "{n} of {cap} saved words. You can save {left} more on Free. Known words don't count.",
                { n: listed, cap: plan.words, left: left }
              )
            : t(
                "you.plan.words-full",
                "{n} of {cap} saved words, as many as Free keeps. Mark words known to make room.",
                { n: listed, cap: plan.words }
              );
        var more = document.getElementById("plan-words-more");
        if (more) more.hidden = !near;
        // "See plans" once: near the cap the row's link says why, so the head's goes
        // (qa-claude on #871).
        if (seeAll) seeAll.hidden = near;
        document.getElementById("plan-words-row").hidden = false;
      }
    } else {
      document.getElementById("plan-paid-says").textContent = t(
        "you.plan.paid-says",
        "{n} credits a month, which is {hours} hours of audio or video",
        { n: plan.credits, hours: hours }
      );
      document.getElementById("plan-back").textContent = back
        ? t("you.plan.back", "Your credits reset on {date}", { date: back })
        : "";
      var ups = document.getElementById("plan-top-ups");
      ups.textContent = "";
      (plan.topUps || []).forEach(function (n) {
        var one = document.createElement("span");
        one.textContent = t("you.plan.top-up-credits", "{n} credits", { n: n });
        ups.appendChild(one);
      });
    }
    card.hidden = false;
  }

  /* --- putting it together ---------------------------------------------------- */

  /* Three answers that are not the account, told apart (targum-internal#469, B1, B2):
     still asking, with a line past three seconds; offline; and not reached, with Try
     again. Only the server saying nobody is signed in draws the line to sign in. */
  var slow = setTimeout(function () {
    var line = at("you-slow");
    if (line && !at("you-loading").hidden) line.hidden = false;
  }, 3000);
  ["you-slow-again", "you-reach-again"].forEach(function (id) {
    var press = at(id);
    if (press) {
      press.addEventListener("click", function () {
        location.reload();
      });
    }
  });

  meOnce(keyed("/account/me"), {
    credentials: "same-origin",
    headers: key ? { "X-Targum-Key": key } : {},
  })
    .then(function (response) {
      if (!response.ok && response.status !== 401) throw new Error(String(response.status));
      return response.json();
    })
    .then(function (who) {
      clearTimeout(slow);
      at("you-loading").hidden = true;
      show(!!who.signedIn);
      if (!who.signedIn) return;
      drawWho(who);
      address = who.address || "";
      drawLanguages(who);
      drawLevel(who);
      drawRecord(who);
      drawCounting(who);
      drawConnections(who);
      drawTelegram(who);
      drawPrompts(who);
      drawGrant(who);
      drawPlan(who);
      wireLanguages();
      wireAddress();
      ending();
      if (window.TargumSync) window.TargumSync.start();
    })
    // A server that cannot be reached is not a reader who is signed out, and telling a
    // signed-in reader on a train to sign in was the old answer here. Offline says what
    // still works; anything else says the account could not be reached, with Try again.
    .catch(function () {
      clearTimeout(slow);
      only(typeof navigator !== "undefined" && navigator.onLine === false ? "you-offline" : "you-unreachable");
    });
})();
