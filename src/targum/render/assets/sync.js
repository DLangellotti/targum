/* Keeping the browser's word list and the account's word list the same thing.
 *
 * The stores themselves do not move. Every page still reads and writes
 * `targum:vocab:<language>`, `targum:picked:<document>` and `targum:docs` exactly as
 * it did when there were no accounts, because that is what makes the signed-out case
 * keep working and what made this possible to add without rewriting three pages. This
 * file sits underneath: on load it takes whatever the account has that the browser
 * lacks, and after any change it hands back whatever the browser has that the account
 * lacks.
 *
 * Two decisions worth knowing about.
 *
 * **Pull on load, push during.** A pull that arrived mid-session would have to reconcile
 * with a page that has already read its store into memory and drawn from it. Instead the
 * pull happens once, on load, and a page that is told something changed re-reads and
 * redraws itself. Anything a second device does shows up the next time a page is opened,
 * which for a reading app is soon enough and is worth what it saves.
 *
 * **Deletes are remembered separately.** Taking a word off the list removes it from its
 * store, and a store cannot say why something is absent. `targum:gone` holds the fact
 * that a removal happened and when, which is the difference between "I deleted this"
 * and "I have not heard of this yet" — and without it every delete comes back on the
 * next sync from the other device.
 */

(function () {
  "use strict";

  var STATE = "targum:sync"; // { email, revision, pushed }
  var GONE = "targum:gone"; // { "w:he:lemma": seen, "p:<id>": seen }
  var VOCAB = "targum:vocab:";
  var PICKED = "targum:picked:";
  var DOCS = "targum:docs";
  var OPENED = "targum:opened";

  // A tombstone is a few bytes and a delete is rare, but a browser that has been in use
  // for years should not carry every word it ever unmarked. Anything this old has long
  // since reached every device that was going to see it.
  var TOMBSTONE_DAYS = 120;

  // The chrome pages are handed the key in a variable; a reader carries it in its own
  // address, because a reader is also a file you can open straight off the disk.
  var key =
    window.TARGUM_KEY || new URLSearchParams(location.search).get("k") || "";
  var listeners = [];
  var pending = null;
  var busy = false;
  var again = false;

  /* --- the browser's own store ---------------------------------------------- */

  function read(name, fallback) {
    try {
      return JSON.parse(localStorage.getItem(name) || fallback) || JSON.parse(fallback);
    } catch (e) {
      return JSON.parse(fallback);
    }
  }

  function write(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {}
  }

  function drop(name) {
    try {
      localStorage.removeItem(name);
    } catch (e) {}
  }

  function names(prefix) {
    var found = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var name = localStorage.key(i);
        if (name && name.indexOf(prefix) === 0) found.push(name);
      }
    } catch (e) {}
    return found;
  }

  function state() {
    return read(STATE, "{}");
  }

  // `seen` is when the reader last touched a record. Older records predate the field
  // and only have `at`, which is when it was first kept — near enough, and it is what
  // makes everything already in a browser get claimed on the first sync.
  function touchedAt(record) {
    return Number(record.seen || record.at || 0) || 0;
  }

  /* --- what this browser has, in the shape the account speaks --------------- */

  function localWords(since) {
    var out = [];
    names(VOCAB).forEach(function (name) {
      var language = name.slice(VOCAB.length);
      var store = read(name, "{}");
      Object.keys(store).forEach(function (lemma) {
        var word = store[lemma] || {};
        if (touchedAt(word) <= since) return;
        out.push({
          language: language,
          lemma: lemma,
          surface: word.surface || "",
          status: word.status === undefined ? null : word.status,
          meaning: word.meaning || "",
          note: word.note || "",
          band: word.band || "",
          at: word.at || 0,
          seen: touchedAt(word),
        });
      });
    });
    return out;
  }

  function localPhrases(since) {
    var out = [];
    names(PICKED).forEach(function (name) {
      var document_ = name.slice(PICKED.length);
      var store = read(name, "{}");
      var changed = false;
      Object.keys(store).forEach(function (segment) {
        (store[segment] || []).forEach(function (pick) {
          // A phrase's place in an array is not a name for it: deleting the first
          // phrase in a sentence renames every phrase after it. One is minted here,
          // the first time a phrase is looked at, and never changes again.
          if (!pick.id) {
            pick.id = "p" + (pick.at || Date.now()) + "-" + Math.random().toString(36).slice(2, 8);
            changed = true;
          }
          if (touchedAt(pick) <= since) return;
          out.push({
            id: pick.id,
            document: document_,
            segment: segment,
            span_start: pick.start || 0,
            span_end: pick.end || 0,
            text: pick.text || "",
            status: pick.status === undefined ? null : pick.status,
            note: pick.note || "",
            meaning: pick.meaning || "",
            at: pick.at || 0,
            seen: touchedAt(pick),
          });
        });
      });
      if (changed) write(name, store);
    });
    return out;
  }

  function localDocs(since) {
    var docs = read(DOCS, "{}");
    var opened = read(OPENED, "{}");
    var out = [];
    var hashes = {};
    Object.keys(docs).forEach(function (hash) {
      hashes[hash] = true;
    });
    Object.keys(opened).forEach(function (hash) {
      hashes[hash] = true;
    });
    Object.keys(hashes).forEach(function (hash) {
      var doc = docs[hash] || {};
      var when = Math.max(Number(doc.updated || 0), Number(opened[hash] || 0));
      if (when <= since) return;
      out.push({
        hash: hash,
        title: doc.title || "",
        language: doc.language || "",
        updated: doc.updated || 0,
        opened: opened[hash] || 0,
        seen: when,
      });
    });
    return out;
  }

  function tombstones(since) {
    var gone = read(GONE, "{}");
    var words = [];
    var phrases = [];
    Object.keys(gone).forEach(function (name) {
      var when = Number(gone[name]) || 0;
      if (when <= since) return;
      if (name.indexOf("w:") === 0) {
        var rest = name.slice(2);
        var cut = rest.indexOf(":");
        words.push({
          language: rest.slice(0, cut),
          lemma: rest.slice(cut + 1),
          gone: 1,
          seen: when,
        });
      } else if (name.indexOf("p:") === 0) {
        phrases.push({ id: name.slice(2), gone: 1, seen: when });
      }
    });
    return { words: words, phrases: phrases };
  }

  /* --- taking what the account has ------------------------------------------ */

  function applyWords(rows) {
    var stores = {};
    var touched = false;
    rows.forEach(function (row) {
      var name = VOCAB + row.language;
      if (!stores[name]) stores[name] = read(name, "{}");
      var store = stores[name];
      var here = store[row.lemma];
      if (here && touchedAt(here) >= Number(row.seen || 0)) return;
      touched = true;
      if (row.gone) {
        delete store[row.lemma];
        remember("w:" + row.language + ":" + row.lemma, Number(row.seen || 0));
        return;
      }
      store[row.lemma] = {
        status: row.status,
        surface: row.surface || "",
        meaning: row.meaning || "",
        note: row.note || "",
        band: row.band || "",
        at: row.at || 0,
        seen: row.seen || 0,
      };
    });
    Object.keys(stores).forEach(function (name) {
      write(name, stores[name]);
    });
    return touched;
  }

  function applyPhrases(rows) {
    var stores = {};
    var touched = false;
    rows.forEach(function (row) {
      // A tombstone carries only the id, so the store it belongs to has to be found by
      // looking. There are not many, and this only runs on a delete from elsewhere.
      var name = row.document ? PICKED + row.document : null;
      var where = name ? [name] : names(PICKED);
      where.forEach(function (store_name) {
        if (!stores[store_name]) stores[store_name] = read(store_name, "{}");
        var store = stores[store_name];
        var segment = row.segment;
        if (!segment) {
          Object.keys(store).forEach(function (each) {
            (store[each] || []).forEach(function (pick) {
              if (pick.id === row.id) segment = each;
            });
          });
        }
        if (!segment) return;
        var list = store[segment] || (store[segment] = []);
        var at = -1;
        for (var i = 0; i < list.length; i++) if (list[i].id === row.id) at = i;
        if (at > -1 && touchedAt(list[at]) >= Number(row.seen || 0)) return;
        touched = true;
        if (row.gone) {
          if (at > -1) list.splice(at, 1);
          if (!list.length) delete store[segment];
          remember("p:" + row.id, Number(row.seen || 0));
          return;
        }
        var pick = {
          id: row.id,
          start: row.span_start || 0,
          end: row.span_end || 0,
          text: row.text || "",
          status: row.status,
          note: row.note || "",
          meaning: row.meaning || "",
          at: row.at || 0,
          seen: row.seen || 0,
        };
        if (at > -1) list[at] = pick;
        else list.push(pick);
      });
    });
    Object.keys(stores).forEach(function (name) {
      write(name, stores[name]);
    });
    return touched;
  }

  function applyDocs(rows) {
    var docs = read(DOCS, "{}");
    var opened = read(OPENED, "{}");
    var touched = false;
    rows.forEach(function (row) {
      var here = docs[row.hash];
      if (here && Number(here.updated || 0) >= Number(row.updated || 0)) {
        // Still take a later opening: the two halves move independently.
        if (Number(row.opened || 0) > Number(opened[row.hash] || 0)) {
          opened[row.hash] = row.opened;
          touched = true;
        }
        return;
      }
      touched = true;
      if (row.gone) {
        delete docs[row.hash];
        delete opened[row.hash];
        return;
      }
      docs[row.hash] = {
        title: row.title || "",
        language: row.language || "",
        updated: row.updated || 0,
      };
      if (Number(row.opened || 0) > Number(opened[row.hash] || 0)) opened[row.hash] = row.opened;
    });
    write(DOCS, docs);
    write(OPENED, opened);
    return touched;
  }

  /* --- deletes -------------------------------------------------------------- */

  function remember(name, when) {
    var gone = read(GONE, "{}");
    gone[name] = when || Date.now();
    var cutoff = Date.now() - TOMBSTONE_DAYS * 24 * 60 * 60 * 1000;
    Object.keys(gone).forEach(function (each) {
      if (Number(gone[each]) < cutoff) delete gone[each];
    });
    write(GONE, gone);
  }

  /* --- talking to the account ----------------------------------------------- */

  function ask(path, body) {
    var options = {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      // Same origin, so the session cookie rides along; the key is still what proves
      // this page may drive the builder.
      credentials: "same-origin",
    };
    if (key) options.headers["X-Targum-Key"] = key;
    if (body) options.body = JSON.stringify(body);
    return fetch(path + (key ? "?k=" + encodeURIComponent(key) : ""), options).then(function (
      response
    ) {
      if (!response.ok && response.status !== 401) throw new Error(String(response.status));
      return response.json();
    });
  }

  function announce(changed) {
    listeners.forEach(function (listener) {
      try {
        listener(changed);
      } catch (e) {}
    });
  }

  function clearLocal() {
    names(VOCAB).forEach(drop);
    names(PICKED).forEach(drop);
    drop(DOCS);
    drop(OPENED);
    drop(GONE);
    drop(STATE);
  }

  function exchange(full) {
    var was = state();
    var since = full ? 0 : Number(was.pushed || 0);
    var mark = Date.now();
    var dead = tombstones(since);
    var body = {
      since: full ? 0 : Number(was.revision || 0),
      words: localWords(since).concat(dead.words),
      phrases: localPhrases(since).concat(dead.phrases),
      docs: localDocs(since),
    };
    busy = true;
    return ask("/sync", body)
      .then(function (answer) {
        busy = false;
        if (!answer || answer.signedIn === false) return false;
        // What the account holds now, rather than what it held before this push.
        if (api.who && answer.counts) api.who.counts = answer.counts;
        var changed = applyWords(answer.words || []);
        changed = applyPhrases(answer.phrases || []) || changed;
        changed = applyDocs(answer.docs || []) || changed;
        write(STATE, { email: was.email, revision: answer.revision, pushed: mark });
        if (again) {
          again = false;
          exchange(false);
        }
        return changed;
      })
      .catch(function () {
        busy = false;
        // Offline, or the server went away. The browser keeps working from its own
        // store and everything unsent is still unsent, because `pushed` did not move.
        return false;
      });
  }

  /* --- what the pages call -------------------------------------------------- */

  var api = {
    // Called by a page that wants to know when the account handed it something.
    onChange: function (listener) {
      listeners.push(listener);
    },

    // Whoever is signed in, or null. Resolved once and reused.
    who: null,

    start: function () {
      return ask("/account/me")
        .then(function (me) {
          api.who = me && me.signedIn ? me : null;
          if (!api.who) return false;
          var was = state();
          if (was.email && was.email !== me.email) {
            // Another person signed in on this browser. Nothing of theirs is mixed in
            // with what is already here, and none of what is here goes up with it.
            clearLocal();
          }
          var fresh = !state().email;
          write(STATE, {
            email: me.email,
            revision: fresh ? 0 : state().revision,
            pushed: fresh ? 0 : state().pushed,
          });
          // First sync on this browser sends everything: whatever was kept while
          // signed out is claimed by the account rather than stranded.
          return exchange(fresh);
        })
        .then(function (changed) {
          announce(!!changed);
          return changed;
        })
        .catch(function () {
          announce(false);
          return false;
        });
    },

    // After any local change. Batched, because marking five words in a sentence is
    // five calls to this and should be one request.
    touched: function () {
      if (!api.who) return;
      if (busy) {
        again = true;
        return;
      }
      clearTimeout(pending);
      pending = setTimeout(function () {
        exchange(false);
      }, 1200);
    },

    // A word or phrase taken off the list. Recorded even when signed out, so that
    // signing in later does not resurrect it.
    forgetWord: function (language, lemma) {
      remember("w:" + language + ":" + lemma, Date.now());
    },
    forgetPhrase: function (id) {
      if (id) remember("p:" + id, Date.now());
    },

    signIn: function (email) {
      return ask("/account/sign-in", { email: email });
    },

    signOut: function () {
      return ask("/account/sign-out", {}).then(function () {
        // The point of signing out is that the next person to open this browser is
        // shown nothing. Leaving the words behind would defeat the whole exercise.
        clearLocal();
        api.who = null;
        return true;
      });
    },
  };

  window.TargumSync = api;
})();
