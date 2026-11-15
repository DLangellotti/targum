/* Send to Anki: Your Words sends the reader's learning words straight into the Anki on
 * their own computer, through the AnkiConnect add-on (targum-internal#540; design.md §12,
 * "Send to Anki talks to the Anki on your own computer", 2026-11-14).
 *
 * At a desk only: AnkiConnect is a desktop add-on, and a phone keeps the `.apkg` and CSV.
 * The words come from targum's own origin (`/account/anki/notes`), and every clip too; the
 * page hands Anki the bytes, never an address to fetch. Anki's own `Sent` field is the
 * record of what targum last wrote, so a second press with nothing changed adds and
 * updates nothing, and a send that stopped midway is finished by the next press. Nothing
 * is kept here about what was sent. The page calls only `ALLOWED`: it never deletes a
 * note and never touches scheduling.
 */
(function () {
  "use strict";

  var ANKI = "http://127.0.0.1:8765";
  var VERSION = 6;
  var NOTETYPE = "targum word and sentence";
  var IMPORTED = "targum word";
  var KEY_STORE = "targum:anki-key";
  var BATCH = 50;
  var INFO_BATCH = 500;
  var ALLOWED = [
    "requestPermission",
    "version",
    "deckNames",
    "createDeck",
    "modelNames",
    "createModel",
    "findNotes",
    "notesInfo",
    "addNotes",
    "updateNoteFields",
    "updateNoteTags",
    "storeMediaFile",
    "multi",
  ];
  var FIELDS = [
    "Word",
    "Meaning",
    "Sound",
    "Before",
    "Gap",
    "After",
    "Translation",
    "Sentence sound",
    "Source",
    "Word card",
    "targum",
    "Sent",
    "Your notes",
  ];
  // Plain and light, like the `.apkg`'s own (`anki.CSS`): Anki draws its own night mode.
  var CSS =
    ".card { font-family: sans-serif; font-size: 22px; line-height: 1.5; text-align: center; }\n" +
    ".word { font-size: 40px; }\n" +
    ".line { margin: 12px 0; }\n" +
    ".tr, .src { font-size: 16px; opacity: 0.7; }\n";
  var TEMPLATES = [
    {
      Name: "Word",
      Front: '{{#Word card}}<div dir="auto" class="word">{{Word}}</div>{{Sound}}{{/Word card}}',
      Back:
        '{{FrontSide}}<hr id="answer"><div dir="auto">{{Meaning}}</div>' +
        '{{#Gap}}<div dir="auto" class="line">{{Before}}<b>{{Gap}}</b>{{After}}</div>{{/Gap}}' +
        '<div dir="auto" class="src">{{Source}}</div>' +
        '{{#Your notes}}<div dir="auto">{{Your notes}}</div>{{/Your notes}}',
    },
    {
      Name: "Gap",
      Front:
        '{{#Gap}}<div dir="auto" class="line">{{Before}}<span class="gap">[…]</span>{{After}}</div>' +
        '<div dir="auto" class="tr">{{Translation}}</div>{{/Gap}}',
      Back:
        '<div dir="auto" class="line">{{Before}}<b>{{Gap}}</b>{{After}}</div>' +
        '<div dir="auto" class="tr">{{Translation}}</div>{{Sentence sound}}' +
        '<div dir="auto">{{Meaning}}</div><div dir="auto" class="src">{{Source}}</div>' +
        '{{#Your notes}}<div dir="auto">{{Your notes}}</div>{{/Your notes}}',
    },
  ];

  var running = false;
  var offered = false;

  function t(key, fallback, values) {
    var said = window.TargumStrings;
    if (said) return said.t(key, fallback, values);
    return String(fallback).replace(/\{(\w+)\}/g, function (all, name) {
      return values && name in values ? values[name] : all;
    });
  }
  function tn(key, count, one, other, fill) {
    var said = window.TargumStrings;
    if (said) return said.tn(key, count, one, other, fill);
    var values = { n: count };
    for (var name in fill || {}) values[name] = fill[name];
    return t(key, count === 1 ? one : other, values);
  }

  function at(id) {
    return document.getElementById(id);
  }

  function keyed(path) {
    var key = window.TARGUM_KEY || "";
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function desk() {
    try {
      return !!(window.matchMedia && window.matchMedia("(pointer: fine)").matches);
    } catch (e) {
      return false;
    }
  }

  function said(text) {
    var line = at("export-said");
    if (!line) return;
    line.hidden = !text;
    line.textContent = text || "";
  }

  function context() {
    var lists = window.TargumLists;
    return (lists && lists.ankiContext && lists.ankiContext()) || { code: "", name: "", deck: "targum" };
  }

  /** Every value targum writes into a note is the reader's text, never markup. */
  function escaped(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }
  function unescaped(value) {
    return String(value == null ? "" : value)
      .replace(/<[^>]*>/g, "")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .trim();
  }

  function storedKey() {
    try {
      return localStorage.getItem(KEY_STORE) || "";
    } catch (e) {
      return "";
    }
  }

  /* --- AnkiConnect ------------------------------------------------------------- */

  function Stop(kind, detail) {
    this.kind = kind;
    this.detail = detail || "";
  }

  /** One AnkiConnect action, POSTed with no Content-Type so the body goes as text/plain
   *  and the browser asks no preflight. Anything off `ALLOWED`, inside `multi` too, is
   *  refused here before it leaves the page. */
  function call(action, params) {
    if (ALLOWED.indexOf(action) < 0) return Promise.reject(new Stop("refused-action", action));
    if (action === "multi") {
      var inner = (params && params.actions) || [];
      for (var i = 0; i < inner.length; i++) {
        if (ALLOWED.indexOf(inner[i].action) < 0 || inner[i].action === "multi") {
          return Promise.reject(new Stop("refused-action", inner[i].action));
        }
        inner[i].version = VERSION;
      }
    }
    var body = { action: action, version: VERSION, params: params || {} };
    var key = storedKey();
    if (key) body.key = key;
    return fetch(ANKI, { method: "POST", body: JSON.stringify(body) })
      .then(
        function (answer) {
          return answer.json();
        },
        function () {
          throw new Stop("unreachable");
        }
      )
      .then(function (answer) {
        if (answer && answer.error) {
          var error = String(answer.error);
          if (/api ?key/i.test(error)) throw new Stop("key", error);
          throw new Stop("busy", error);
        }
        return answer ? answer.result : null;
      });
  }

  /** Whether the browser itself said no to reaching this computer (Chrome's Local
   *  Network Access). Anything it cannot answer is taken as not blocked. */
  function blocked() {
    try {
      if (!navigator.permissions || !navigator.permissions.query) return Promise.resolve(false);
      return navigator.permissions
        .query({ name: "local-network-access" })
        .then(function (state) {
          return !!state && state.state === "denied";
        })
        .catch(function () {
          return false;
        });
    } catch (e) {
      return Promise.resolve(false);
    }
  }

  /* --- targum's own origin ----------------------------------------------------- */

  function words(code) {
    var all = [];
    function page(n) {
      return fetch(keyed("/account/anki/notes?language=" + encodeURIComponent(code) + "&page=" + n), {
        credentials: "same-origin",
      })
        .then(function (answer) {
          if (!answer.ok) throw new Stop("targum");
          return answer.json();
        }, function () {
          throw new Stop("targum");
        })
        .then(function (answer) {
          all = all.concat(answer.words || []);
          return answer.next != null ? page(answer.next) : all;
        });
    }
    return page(0);
  }

  function base64(buffer) {
    var bytes = new Uint8Array(buffer);
    var out = "";
    for (var i = 0; i < bytes.length; i += 0x8000) {
      out += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(out);
  }

  /** A clip off targum's own origin into Anki's media, by its stable name. False where
   *  the clip could not be had, so the note's `Sent` is left blank and the next press
   *  tries it again. */
  function media(address, name) {
    if (!address || !name) return Promise.resolve(true);
    return fetch(keyed(address), { credentials: "same-origin" })
      .then(function (answer) {
        if (!answer.ok) return null;
        return answer.arrayBuffer();
      })
      .catch(function () {
        return null;
      })
      .then(function (buffer) {
        if (!buffer) return false;
        return call("storeMediaFile", { filename: name, data: base64(buffer) }).then(function () {
          return true;
        });
      });
  }

  function fields(word, whole) {
    var out = {
      Word: escaped(word.term),
      Meaning: escaped(word.meaning),
      Sound: word.soundFile ? "[sound:" + word.soundFile + "]" : "",
      Before: escaped(word.before),
      Gap: escaped(word.gap),
      After: escaped(word.after),
      Translation: escaped(word.translation),
      "Sentence sound": word.lineFile ? "[sound:" + word.lineFile + "]" : "",
      Source: escaped(word.source),
      targum: escaped(word.key),
      Sent: whole ? escaped(word.hash) : "",
    };
    return out;
  }

  function tagsOf(word) {
    return String(word.tags || "").split(" ").filter(Boolean);
  }

  function notesInfo(ids) {
    var out = [];
    function next(from) {
      if (from >= ids.length) return Promise.resolve(out);
      return call("notesInfo", { notes: ids.slice(from, from + INFO_BATCH) }).then(function (rows) {
        out = out.concat(rows || []);
        return next(from + INFO_BATCH);
      });
    }
    return next(0);
  }

  function fieldOf(row, name) {
    var one = row && row.fields && row.fields[name];
    return one ? String(one.value || "") : "";
  }

  /* --- the send ---------------------------------------------------------------- */

  function setUp(deck) {
    return call("deckNames")
      .then(function (decks) {
        if ((decks || []).indexOf(deck) >= 0) return null;
        return call("createDeck", { deck: deck });
      })
      .then(function () {
        return call("modelNames");
      })
      .then(function (models) {
        if ((models || []).indexOf(NOTETYPE) >= 0) return null;
        return call("createModel", {
          modelName: NOTETYPE,
          inOrderFields: FIELDS,
          css: CSS,
          isCloze: false,
          cardTemplates: TEMPLATES,
        });
      });
  }

  /** What Anki already holds: targum's sent notes by key, and the words an `.apkg`
   *  import already gave a card in this deck (design.md §12, decision 6). */
  function holding(code, deck) {
    var sent = {};
    var imported = {};
    return call("findNotes", { query: '"note:' + NOTETYPE + '"' })
      .then(notesInfo)
      .then(function (rows) {
        rows.forEach(function (row) {
          var key = unescaped(fieldOf(row, "targum"));
          if (key) sent[key] = { id: row.noteId, sent: unescaped(fieldOf(row, "Sent")) };
        });
        return call("findNotes", {
          query: '"note:' + IMPORTED + '" "deck:' + deck.replace(/"/g, "") + '" "tag:targum::' + code + '"',
        });
      })
      .then(notesInfo)
      .then(function (rows) {
        rows.forEach(function (row) {
          var word = unescaped(fieldOf(row, "Word"));
          if (word) imported[word] = true;
        });
        return { sent: sent, imported: imported };
      });
  }

  function send() {
    if (running) return;
    var where = context();
    if (!where.code) return;
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      said(t("lists.anki-send.offline", "You're offline. Send to Anki when you're back online."));
      return;
    }
    if (typeof fetch !== "function" || typeof Promise !== "function") return;
    running = true;
    var button = at("send-anki");
    if (button) button.disabled = true;
    var progress = { done: 0, total: 0, added: 0, updated: 0, failed: 0, writing: false };
    said(t("lists.anki-send.asking", "Anki will ask whether targum may add cards. Choose Yes in Anki."));

    function sending() {
      said(
        t("lists.anki-send.sending", "Sending to Anki: {done} of {total} words. Keep this page open.", {
          done: progress.done,
          total: progress.total,
        })
      );
    }

    call("requestPermission")
      .then(function (answer) {
        if (!answer || answer.permission !== "granted") throw new Stop("refused");
        if (answer.requireApikey && !storedKey()) throw new Stop("key");
        return call("version");
      })
      .then(function (version) {
        if (typeof version !== "number" || version < VERSION) throw new Stop("old");
        return setUp(where.deck);
      })
      .then(function () {
        return Promise.all([words(where.code), holding(where.code, where.deck)]);
      })
      .then(function (both) {
        var all = both[0];
        var have = both[1];
        var adds = [];
        var updates = [];
        all.forEach(function (word) {
          var there = have.sent[word.key];
          if (!there) {
            // A word the `.apkg` already carries and with no line has no card to add.
            if (word.add && !(have.imported[word.term] && !word.gap)) adds.push(word);
          } else if (there.sent !== word.hash) {
            updates.push({ word: word, id: there.id });
          }
        });
        progress.total = adds.length + updates.length;
        if (!progress.total) return null;
        progress.writing = true;
        sending();
        return addAll(adds, have.imported).then(function () {
          return updateAll(updates);
        });
      })
      .then(function () {
        finish(summary());
      })
      .catch(function (stop) {
        if (!(stop instanceof Stop)) stop = new Stop("busy");
        if (stop.kind === "unreachable") {
          if (progress.writing) return finish(stopped());
          return blocked().then(function (no) {
            finish(
              no
                ? t("lists.anki-send.blocked", "Your browser is blocking targum from reaching Anki. Allow it in this site's settings, then try again.")
                : t("lists.anki-send.unreachable", "We couldn't reach Anki on this computer. Open Anki and check that AnkiConnect is installed.")
            );
          });
        }
        if (stop.kind === "key") {
          askKey();
          return finish(t("lists.anki-send.key", "Anki asks for a key. Copy it from AnkiConnect's settings in Anki."));
        }
        if (stop.kind === "refused") {
          return finish(t("lists.anki-send.refused", "Anki said no. Press Send to Anki again and choose Yes in Anki."));
        }
        if (stop.kind === "old") {
          return finish(
            t("lists.anki-send.old", "AnkiConnect needs an update. In Anki, choose Tools, then Add-ons, then Check for Updates.")
          );
        }
        if (stop.kind === "targum") {
          return finish(progress.writing ? stopped() : t("lists.anki-send.failed", "We couldn't get your words just now. Try again."));
        }
        finish(t("lists.anki-send.busy", "Anki is busy. Close any open windows in Anki and try again."));
      });

    function stopped() {
      return t(
        "lists.anki-send.stopped",
        "We sent {done} of {total} words before the connection dropped. Press Send to Anki to send the rest.",
        { done: progress.done, total: progress.total }
      );
    }

    function summary() {
      if (!progress.total) return t("lists.anki-send.nothing", "Anki already has all your words.");
      var parts = [];
      if (progress.added) {
        parts.push(tn("lists.anki-send.added", progress.added, "Added {n} word to Anki.", "Added {n} words to Anki."));
      }
      if (progress.updated) parts.push(t("lists.anki-send.updated", "Updated {n}.", { n: progress.updated }));
      if (progress.failed) {
        parts.push(
          tn("lists.anki-send.some-failed", progress.failed, "{n} word couldn't be added.", "{n} words couldn't be added.")
        );
      }
      return parts.join(" ") || t("lists.anki-send.nothing", "Anki already has all your words.");
    }

    function finish(text) {
      running = false;
      if (button) button.disabled = false;
      said(text);
    }

    function withMedia(word) {
      return media(word.sound, word.soundFile).then(function (one) {
        return media(word.line, word.lineFile).then(function (two) {
          return one && two;
        });
      });
    }

    function addAll(adds, imported) {
      function batch(from) {
        if (from >= adds.length) return Promise.resolve();
        var some = adds.slice(from, from + BATCH);
        var whole = [];
        return some
          .reduce(function (chain, word, n) {
            return chain.then(function () {
              return withMedia(word).then(function (ok) {
                whole[n] = ok;
              });
            });
          }, Promise.resolve())
          .then(function () {
            var notes = some.map(function (word, n) {
              var values = fields(word, whole[n]);
              // A word an `.apkg` already carries gets only its Gap card.
              values["Word card"] = imported[word.term] ? "" : "y";
              return {
                deckName: where.deck,
                modelName: NOTETYPE,
                fields: values,
                tags: tagsOf(word),
                options: { allowDuplicate: true, duplicateScope: "deck" },
              };
            });
            // A newer AnkiConnect refuses the whole call for one note it cannot add, so
            // the batch is then added one note at a time and only that one is counted.
            return call("addNotes", { notes: notes }).catch(function (stop) {
              if (!(stop instanceof Stop) || stop.kind !== "busy") throw stop;
              return notes.reduce(function (chain, one) {
                return chain.then(function (ids) {
                  return call("addNotes", { notes: [one] })
                    .then(function (got) {
                      return ids.concat([(got || [])[0] || null]);
                    })
                    .catch(function (again) {
                      if (!(again instanceof Stop) || again.kind !== "busy") throw again;
                      return ids.concat([null]);
                    });
                });
              }, Promise.resolve([]));
            });
          })
          .then(function (ids) {
            (ids || []).forEach(function (id) {
              if (id) progress.added += 1;
              else progress.failed += 1;
            });
            progress.done += some.length;
            sending();
            return batch(from + BATCH);
          });
      }
      return batch(0);
    }

    function updateAll(updates) {
      function batch(from) {
        if (from >= updates.length) return Promise.resolve();
        var some = updates.slice(from, from + BATCH);
        var whole = [];
        return some
          .reduce(function (chain, one, n) {
            return chain.then(function () {
              return withMedia(one.word).then(function (ok) {
                whole[n] = ok;
              });
            });
          }, Promise.resolve())
          .then(function () {
            var actions = [];
            some.forEach(function (one, n) {
              // targum's own fields only: never Your notes, and never Word card, which
              // was settled when the note was added.
              actions.push({ action: "updateNoteFields", params: { note: { id: one.id, fields: fields(one.word, whole[n]) } } });
              actions.push({ action: "updateNoteTags", params: { note: one.id, tags: tagsOf(one.word) } });
            });
            return call("multi", { actions: actions });
          })
          .then(function () {
            progress.updated += some.length;
            progress.done += some.length;
            sending();
            return batch(from + BATCH);
          });
      }
      return batch(0);
    }
  }

  /* --- the controls ------------------------------------------------------------ */

  function askKey() {
    var form = at("send-anki-key");
    if (!form) return;
    form.hidden = false;
    var field = at("send-anki-key-field");
    if (field && field.focus) field.focus();
  }

  function keyGiven(event) {
    if (event && event.preventDefault) event.preventDefault();
    var field = at("send-anki-key-field");
    var key = field ? String(field.value || "").trim() : "";
    if (!key) return;
    try {
      localStorage.setItem(KEY_STORE, key);
    } catch (e) {}
    at("send-anki-key").hidden = true;
    send();
  }

  function toggleHelp() {
    var press = at("send-anki-help");
    var how = at("send-anki-how");
    if (!press || !how) return;
    var open = how.hidden;
    how.hidden = !open;
    press.setAttribute("aria-expanded", open ? "true" : "false");
    var scope = at("send-anki-scope");
    if (scope) {
      scope.textContent = t("lists.anki-send.scope", "Sends every word you're learning in {language}.", {
        language: context().name,
      });
    }
  }

  /** Shown where an account is there and the pointer is fine: a phone sees exactly
   *  what it saw before, the deck and the CSV. */
  function offer(signedIn) {
    offered = !!signedIn && desk();
    var button = at("send-anki");
    var press = at("send-anki-help");
    if (button) button.hidden = !offered;
    if (press) press.hidden = !offered;
    if (!offered) {
      var how = at("send-anki-how");
      if (how) how.hidden = true;
      var form = at("send-anki-key");
      if (form) form.hidden = true;
      if (press) press.setAttribute("aria-expanded", "false");
    }
  }

  function mount() {
    var button = at("send-anki");
    if (!button) return;
    button.onclick = send;
    var press = at("send-anki-help");
    if (press) press.onclick = toggleHelp;
    var form = at("send-anki-key");
    if (form) form.onsubmit = keyGiven;
  }

  window.TargumAnkiSend = {
    mount: mount,
    offer: offer,
    send: send,
    escaped: escaped,
    ALLOWED: ALLOWED,
    NOTETYPE: NOTETYPE,
    isRunning: function () {
      return running;
    },
  };
  if (typeof document !== "undefined" && document.getElementById) mount();
})();
