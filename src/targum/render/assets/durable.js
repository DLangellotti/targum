/* targum: a store that keeps what it is told.

   A targum is one file — a phone, an e-reader, offline — so the reader people carry is
   opened from disk, and on `file://` `localStorage` does not keep what it is given.
   Measured, paired, 2,000 write-then-reload rounds in Chromium: `localStorage` lost the
   most recent write 66 times, IndexedDB lost it none. The rate climbed as the store
   filled, so the reader with the most to lose is the one most likely to lose it.

   The loss is a stale read rather than an empty store. `setItem` returns when the value
   is in memory; when it reaches disk is the browser's business, and a navigation can
   arrive first. Nothing available to a page can force that flush — reading the value
   back is answered from memory, and a pause is not something you can impose on somebody
   closing a tab. Both were measured and both did nothing.

   IndexedDB has what `localStorage` lacks: `oncomplete` fires on commit. So every write
   goes to both — `localStorage` because reading it is synchronous and that is what lets
   the page draw itself before anything is awaited, IndexedDB because it is the copy that
   survives.

   On the way back in, IndexedDB is believed. It can only disagree with `localStorage` by
   being right: the two are written together, and the one that loses a write is the one
   that has no commit. If that ever inverts, the cost is one reverted write — which is
   today's bug at 0% instead of 3.3%.

   The reader does not wait forever for the way back in. If the shelf is slow the page
   starts on what `localStorage` holds, which on `file://` is exactly the copy that may
   have lost a write — and a page started that way must not then write over the better
   copy it never saw with a fresher stamp, or a slow read becomes a permanent bad write.
   A session started blind keeps its writes below the shelf's copy until it can be shown
   the shelf was not ahead; the shelf wins on the next opening, which is the one loss
   this file is allowed. (targum-internal#154)
*/

(function () {
  "use strict";

  var DB = "targum";
  var SHELF = "kept";
  var MINE = /^targum:/;
  /* The stamps are bookkeeping, not state: never mirrored, never restored. */
  var STAMP = /^targum:at:/;

  /* The reader starts anyway if the store does not answer. A page that will not draw
     because a database is wedged is a worse failure than the one this file is for. */
  var PATIENCE = 500;

  var queue = [];
  var open = false;

  /* How the page was started, and what it has and has not seen.

     `blind` is set when patience ran out before recovery landed: the page is running on
     `localStorage` alone. `landed` is set when recovery finishes, whichever came first.
     `wrote` holds the names a blind page wrote before recovery landed, and `unseen`
     the stamp of every shelf copy that recovery found ahead of what a blind page had
     already read — a copy the page's state cannot have taken into account. */
  var blind = false;
  var landed = false;
  var wrote = {};
  var unseen = {};

  function shelf(mode, use, otherwise) {
    var ask;
    try {
      ask = indexedDB.open(DB, 1);
    } catch (error) {
      return otherwise();
    }
    ask.onupgradeneeded = function () {
      if (!ask.result.objectStoreNames.contains(SHELF)) ask.result.createObjectStore(SHELF);
    };
    ask.onerror = otherwise;
    ask.onsuccess = function () {
      var db = ask.result;
      var deal;
      try {
        deal = db.transaction(SHELF, mode);
      } catch (error) {
        db.close();
        return otherwise();
      }
      use(deal.objectStore(SHELF), function () {
        db.close();
      });
      deal.onerror = function () {
        db.close();
        otherwise();
      };
    };
  }

  /* Every value carries when it was written, and the same stamp goes into
     `localStorage` beside it.

     Without this, recovery cannot tell which copy is newer and can only guess. Guessing
     that IndexedDB always wins is wrong and destructive: a value written straight to
     `localStorage` by something that does not know about this file has no durable copy,
     so the shelf holds an older one and recovery would quietly put the older one back.
     That is a worse bug than the one this file exists for, and a test caught it doing
     exactly that — 100 writes out of 100 reverted.

     With a stamp on both sides the question is answerable. The shelf wins only when it
     is provably ahead, which is the case this file is for: a `localStorage` write that
     did not reach disk lost its stamp in the same breath as its value. */
  function stamp(name) {
    return "targum:at:" + name;
  }

  var ticks = 0;

  function now() {
    ticks += 1;
    return Date.now() + ticks;
  }

  function mirror(name, value, at) {
    shelf(
      "readwrite",
      function (store, done) {
        store.put({ value: value, at: at }, name);
        done();
      },
      function () {}
    );
  }

  function drop(name) {
    shelf(
      "readwrite",
      function (store, done) {
        store.delete(name);
        done();
      },
      function () {}
    );
  }

  /* What the browser held last time, put back where the page will look for it.

     A value is restored only when the shelf is provably ahead of what is in
     `localStorage` — the stamps say so, and where they do not, the page keeps what it
     has. So a write that never went through `keep` is left alone rather than reverted.

     Seeding runs the other way: a reader read before this file existed has everything in
     `localStorage` and nothing on the shelf, and its first visit after an update is what
     gives it a durable copy. Seeded at the stamp it already carries, or at zero, so
     seeding can never look newer than a real write. */
  function recover(then) {
    shelf(
      "readonly",
      function (store, done) {
        var names = store.getAllKeys();
        var values = store.getAll();
        names.onsuccess = function () {
          values.onsuccess = function () {
            var held = {};
            for (var n = 0; n < names.result.length; n++) {
              var name = String(names.result[n]);
              var record = values.result[n];
              held[name] = true;
              if (!record || typeof record !== "object") continue;
              try {
                var mine = Number(localStorage.getItem(stamp(name)) || 0);
                var theirs = Number(record.at || 0);
                if (theirs > mine) {
                  if (wrote[name]) {
                    /* A blind page already wrote this name, on a copy the shelf was
                       ahead of. The page is live on its own value, so it keeps it
                       where it reads — stamped just below the shelf's, so the copy it
                       never saw is the one that survives the next opening. */
                    localStorage.setItem(stamp(name), String(theirs - 1));
                  } else {
                    localStorage.setItem(name, record.value);
                    localStorage.setItem(stamp(name), String(theirs));
                  }
                  if (blind) unseen[name] = theirs;
                } else if (theirs < mine || (wrote[name] && record.value !== localStorage.getItem(name))) {
                  /* The shelf is behind: a mirror that never committed, or a blind write
                     the shelf was not ahead of, which is now known to be a real write
                     and gets the fresh stamp it was held back from. */
                  var at = wrote[name] ? now() : mine;
                  if (wrote[name]) localStorage.setItem(stamp(name), String(at));
                  mirror(name, localStorage.getItem(name), at);
                }
              } catch (error) {}
            }
            try {
              for (var k = 0; k < localStorage.length; k++) {
                var key = localStorage.key(k);
                if (!MINE.test(key) || STAMP.test(key) || held[key]) continue;
                var fresh = wrote[key] ? now() : Number(localStorage.getItem(stamp(key)) || 0);
                if (wrote[key]) localStorage.setItem(stamp(key), String(fresh));
                mirror(key, localStorage.getItem(key), fresh);
              }
            } catch (error) {}
            wrote = {};
            landed = true;
            done();
            then();
          };
        };
      },
      function () {
        landed = true;
        then();
      }
    );
  }

  window.targumKeep = function (name, value) {
    window.TargumStore.keep(name, value);
  };
  window.targumForget = function (name) {
    window.TargumStore.forget(name);
  };

  window.TargumStore = {
    /* Write. Synchronously where the page reads from, durably beside it. */
    keep: function (name, value) {
      if (blind && !landed) {
        /* Written before the shelf has answered, by a page that did not wait for it.
           The value goes where the page reads; the stamp stays what the page read,
           so a shelf copy ahead of that still wins when recovery lands — here, or on
           the next opening if this page is gone by then. The mirror waits for the
           same answer. */
        wrote[name] = true;
        try {
          localStorage.setItem(name, value);
          if (!localStorage.getItem(stamp(name))) localStorage.setItem(stamp(name), "0");
        } catch (error) {}
        return;
      }
      if (unseen[name]) {
        /* The page is running on a copy the shelf was ahead of, and this write comes
           out of that state. Kept where the page reads, below the shelf's stamp and
           off the shelf, so the copy the page never saw survives it. */
        try {
          localStorage.setItem(name, value);
          localStorage.setItem(stamp(name), String(unseen[name] - 1));
        } catch (error) {}
        return;
      }
      var at = now();
      try {
        localStorage.setItem(name, value);
        localStorage.setItem(stamp(name), String(at));
      } catch (error) {}
      mirror(name, value, at);
    },

    forget: function (name) {
      try {
        localStorage.removeItem(name);
        localStorage.removeItem(stamp(name));
      } catch (error) {}
      delete wrote[name];
      delete unseen[name];
      drop(name);
    },

    /* Run once the durable copy is back in place, or once patience runs out. */
    ready: function (run) {
      if (open) return run();
      queue.push(run);
    },
  };

  function begin() {
    if (open) return;
    open = true;
    blind = !landed;
    for (var n = 0; n < queue.length; n++) {
      try {
        queue[n]();
      } catch (error) {}
    }
    queue = [];
  }

  window.setTimeout(begin, PATIENCE);
  try {
    recover(begin);
  } catch (error) {
    begin();
  }
})();
