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
  var DAYS = "targum:days"; // { "2026-08-25": 1 } — a set, written by the reader
  /* Which languages the account says it reads, mirrored here so a page can ask without
     waiting for a round trip.
   *
   * A page draws before the account answers, and the pages that show definitions cannot
   * afford to be generous in the meantime: being briefly wrong here means printing a
   * column of meanings in a language somebody does not read. The account stays the
   * authority — this is rewritten on every start — and being one page load stale is the
   * price of never showing the wrong language for a frame.
   *
   * Absent means nobody has ever signed in on this browser, which is not the same as
   * "reads nothing": signed out, on a machine somebody runs themselves, everything they
   * have is theirs and nothing is hidden. `clearLocal` sweeps this with the rest. */
  var READS = "targum:reads";
  // And which it says are being learned, for the same reason and read by `lang.js`: the
  // switcher on the reading pages is drawn before the account answers.
  var LEARNING = "targum:learning";

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

  // The reader's own local day, as `reader.js` writes it. Two copies of one rule, which
  // is what separate IIFEs cost — but they have to agree: if this one said UTC, the day
  // the reader just wrote would not match the day this filters for, and it would sit in
  // the browser unpushed until the next full exchange.
  function today() {
    var now = new Date();
    return (
      now.getFullYear() +
      "-" +
      String(now.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(now.getDate()).padStart(2, "0")
    );
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
        // No `meaning` and no `note`. What a word means is a fact about a language pair
        // and lives in `targum:meanings:<source>:<target>`; the word record is what is
        // true about the word whichever language you read it in. The columns are still
        // on the account, holding what was written before the two were told apart, and
        // the merge keeps a field a push does not mention — which is what stops this
        // from erasing them on the way past.
        out.push({
          language: language,
          lemma: lemma,
          surface: word.surface || "",
          status: word.status === undefined ? null : word.status,
          band: word.band || "",
          learned: word.learned ? 1 : 0,
          at: word.at || 0,
          seen: touchedAt(word),
        });
      });
    });
    return out;
  }

  /* What words and phrases mean, per language pair.
   *
   * `targum:meanings:<source>:<target>` on this side, one row per (source, target, term)
   * on the account's. Kept apart from the word for the reason the table's own comment
   * gives: the word is the same word whichever language you read it in, and the meaning
   * is not — one slot for both let a Russian reading overwrite an English one under a
   * merge that had no way of telling they were about different things.
   */
  var MEANINGS = "targum:meanings:";

  function localMeanings(since) {
    var out = [];
    names(MEANINGS).forEach(function (name) {
      var pair = name.slice(MEANINGS.length).split(":");
      if (pair.length !== 2 || !pair[0] || !pair[1]) return;
      var store = read(name, "{}");
      Object.keys(store).forEach(function (term) {
        var record = store[term] || {};
        if (touchedAt(record) <= since) return;
        out.push({
          source: pair[0],
          target: pair[1],
          term: term,
          meaning: record.meaning || "",
          note: record.note || "",
          at: record.at || 0,
          seen: touchedAt(record),
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
          // The span is the phrase and belongs to the source sentence; what it reads as
          // belongs to a language pair and travels with the meanings. See `localWords`.
          out.push({
            id: pick.id,
            document: document_,
            segment: segment,
            span_start: pick.start || 0,
            span_end: pick.end || 0,
            text: pick.text || "",
            status: pick.status === undefined ? null : pick.status,
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

  // Every day this browser knows about, or just today.
  //
  // The other collectors filter on `since` by comparing each record's own `seen` stamp
  // against the watermark. A day has no such stamp — the value beside it is a constant,
  // and deriving one from the day string would be a UTC midnight standing in for the
  // reader's, which is the wrong day for half the world. So the rule is positional
  // instead: on a full exchange send everything, and on any other send today, because
  // today's is the only entry this browser can have written since it last pushed.
  function localDays(since) {
    var days = read(DAYS, "{}");
    var keys = Object.keys(days);
    if (since) {
      keys = keys.filter(function (day) {
        return day === today();
      });
    }
    // `seen: 0`, deliberately. The account's merge rule is "an older edit does not
    // overwrite a newer one", compared on `seen` — so a zero means the first push of a
    // day writes it and every push after that is skipped rather than rewriting the same
    // row under a fresh revision all afternoon. A day has no edit time to report anyway:
    // it either happened or it did not.
    return keys.map(function (day) {
      return { day: day, count: 1, seen: 0 };
    });
  }

  function tombstones(since) {
    var gone = read(GONE, "{}");
    var words = [];
    var phrases = [];
    var meanings = [];
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
      } else if (name.indexOf("m:") === 0) {
        // Three parts, not two: a meaning is named by a pair of languages and a term,
        // and a term can hold a colon of its own — `phrase:<id>`. Split from the left
        // twice and take the rest whole, or a phrase's reading loses its own name.
        var about = name.slice(2).split(":");
        var term = about.slice(2).join(":");
        if (about.length > 2 && term) {
          meanings.push({
            source: about[0],
            target: about[1],
            term: term,
            gone: 1,
            seen: when,
          });
        }
      } else if (name.indexOf("p:") === 0) {
        phrases.push({ id: name.slice(2), gone: 1, seen: when });
      }
    });
    return { words: words, phrases: phrases, meanings: meanings };
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
        band: row.band || "",
        // Rebuilt from a named list, so anything not named here is dropped on every sync.
        learned: row.learned ? 1 : 0,
        at: row.at || 0,
        seen: row.seen || 0,
      };
      seed(row.language, row.lemma, row);
    });
    Object.keys(stores).forEach(function (name) {
      write(name, stores[name]);
    });
    flushSeeds();
    return touched;
  }

  function applyMeanings(rows) {
    var stores = {};
    var touched = false;
    rows.forEach(function (row) {
      if (!row.source || !row.target || !row.term) return;
      var name = MEANINGS + row.source + ":" + row.target;
      if (!stores[name]) stores[name] = read(name, "{}");
      var store = stores[name];
      var here = store[row.term];
      if (here && touchedAt(here) >= Number(row.seen || 0)) return;
      touched = true;
      if (row.gone) {
        delete store[row.term];
        remember("m:" + row.source + ":" + row.target + ":" + row.term, Number(row.seen || 0));
        return;
      }
      store[row.term] = {
        meaning: row.meaning || "",
        note: row.note || "",
        at: row.at || 0,
        seen: row.seen || 0,
      };
    });
    Object.keys(stores).forEach(function (name) {
      write(name, stores[name]);
    });
    return touched;
  }

  /* The other half of the move out of the word and into the pair.
   *
   * A browser that has had these words locally has already moved its own; a browser
   * signing in for the first time has never seen them, and the only copy is the account's
   * — in the `meaning` and `note` columns, written before either knew which language it
   * was in. Read as English, the same reading the local move makes and for the same
   * reason: nothing was ever built into anything else.
   *
   * Only where the pair holds nothing already. A meaning this browser has under the pair
   * is one that knows its language, and a column that does not must never win over it.
   */
  var LEGACY_TARGET = "en";
  var seeds = {};

  function seed(source, term, row) {
    if (!row.meaning && !row.note) return;
    var name = "targum:meanings:" + source + ":" + LEGACY_TARGET;
    if (!seeds[name]) seeds[name] = { records: read(name, "{}"), changed: false };
    var into = seeds[name];
    if (into.records[term]) return;
    into.records[term] = {
      meaning: row.meaning || "",
      note: row.note || "",
      at: row.at || 0,
      seen: Number(row.seen || 0),
    };
    into.changed = true;
  }

  function flushSeeds() {
    Object.keys(seeds).forEach(function (name) {
      if (seeds[name].changed) write(name, seeds[name].records);
    });
    seeds = {};
  }

  function applyPhrases(rows) {
    var stores = {};
    var touched = false;
    // Which language each text is in, for filing a phrase's reading under its pair.
    var docs = read(DOCS, "{}");
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
          at: row.at || 0,
          seen: row.seen || 0,
        };
        if (at > -1) list[at] = pick;
        else list.push(pick);
        // A phrase knows which text it was cut from and the text knows its language.
        // Where it does not — a phrase pulled before its document — the reading is left
        // to the sentence's own translation, which is the right answer anyway.
        var source = ((docs[row.document] || {}).language || "").split("-")[0].toLowerCase();
        if (source) seed(source, "phrase:" + row.id, row);
      });
    });
    Object.keys(stores).forEach(function (name) {
      write(name, stores[name]);
    });
    flushSeeds();
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

  // A union, and nothing else. There is no `gone` branch and no `remember()` call: a day
  // somebody read on is not a thing they can take back, so the only direction this moves
  // is more.
  function applyDays(rows) {
    var days = read(DAYS, "{}");
    var touched = false;
    rows.forEach(function (row) {
      if (!row.day || days[row.day]) return;
      days[row.day] = 1;
      touched = true;
    });
    if (touched) write(DAYS, days);
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

  /* Everything about the person who was signed in, off this browser.
   *
   * A keep-list rather than a drop-list, and that is the whole point: the drop-list
   * this replaces named six keys and missed six others, including `targum:master` and
   * `targum:saved:` — the vocabulary store from before it was reshaped, still holding
   * the words — and `targum:language`, which is a record of what someone reads. A list
   * of things to delete goes stale every time a key is added; a list of things to keep
   * fails safe instead.
   *
   * The theme is the only survivor. It is a display preference rather than anything
   * about the reader, and resetting somebody's dark mode when they sign out is a small
   * hostility with nothing to show for it.
   */
  var KEEP = ["targum:theme"];

  function clearLocal() {
    var doomed = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var name = localStorage.key(i);
        if (name && name.indexOf("targum:") === 0 && KEEP.indexOf(name) < 0) doomed.push(name);
      }
    } catch (e) {
      return;
    }
    doomed.forEach(drop);
  }

  function exchange(full) {
    var was = state();
    var since = full ? 0 : Number(was.pushed || 0);
    var mark = Date.now();
    var dead = tombstones(since);
    var body = {
      since: full ? 0 : Number(was.revision || 0),
      words: localWords(since).concat(dead.words),
      meanings: localMeanings(since).concat(dead.meanings),
      phrases: localPhrases(since).concat(dead.phrases),
      docs: localDocs(since),
      days: localDays(since),
    };
    busy = true;
    return ask("/sync", body)
      .then(function (answer) {
        busy = false;
        if (!answer || answer.signedIn === false) return false;
        // What the account holds now, rather than what it held before this push.
        if (api.who && answer.counts) api.who.counts = answer.counts;
        var changed = applyWords(answer.words || []);
        // After the words: a word's meaning may have been seeded from the account's own
        // older columns on the way past, and a row that knows its language wins over it.
        changed = applyMeanings(answer.meanings || []) || changed;
        changed = applyPhrases(answer.phrases || []) || changed;
        changed = applyDocs(answer.docs || []) || changed;
        changed = applyDays(answer.days || []) || changed;
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

    /* Which room they read in. On the account rather than in this browser, and for a
       blunt reason: `clearLocal()` below deletes every `targum:*` key but the theme on
       sign-out, on purpose, so a local preference would be forgotten every time somebody
       signed out on their own machine. */

    start: function () {
      return ask("/account/me")
        .then(function (me) {
          api.who = me && me.signedIn ? me : null;
          if (!api.who) return false;
          write(READS, me.reads || []);
          write(LEARNING, me.learning || []);
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

    // A word's meanings, in every language they were written in, taken off with the
    // word. Left behind, a meaning with no word under it kept a language in the
    // definitions switcher after the last word learned through it was gone.
    forgetMeanings: function (source, term) {
      var head = "targum:meanings:" + source + ":";
      var names = [];
      try {
        for (var i = 0; i < localStorage.length; i++) {
          var name = localStorage.key(i) || "";
          if (name.indexOf(head) === 0) names.push(name);
        }
      } catch (e) {
        return;
      }
      names.forEach(function (name) {
        var records = read(name, "{}");
        if (!(term in records)) return;
        delete records[term];
        write(name, records);
        remember("m:" + source + ":" + name.slice(head.length) + ":" + term, Date.now());
      });
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

  /* Which languages this account is offered a translation into.
   *
   * Everything, until the account has answered — a page drawn before the answer arrives
   * offers what it always offered, and the server refuses anything the account may not
   * have whatever the picker was showing. A picker is not a boundary; this is only what
   * it is polite to show.
   */
  api.reads = function () {
    return (api.who && api.who.reads) || null;
  };

  // And which it is learning, the same way.
  api.learning = function () {
    return (api.who && api.who.learning) || null;
  };

  /* A language to build into that this account will actually be allowed. What somebody
   * last read into is remembered in this browser and the account is the authority, so
   * the two can disagree — a marking taken back, or a browser signed into somebody
   * else's account. English is the fallback, being the one everybody is offered.
   */
  api.into = function (wanted) {
    var allowed = api.reads();
    if (!wanted) return "en";
    if (!allowed || allowed.indexOf(wanted) >= 0) return wanted;
    return "en";
  };

  window.TargumSync = api;
})();
