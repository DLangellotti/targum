/* Saving texts for offline, from the page (design.md §12, "A worker keeps what the reader
 * saved, and fetches nothing else", 2026-10-09).
 *
 * The page saves and the worker answers. Saving happens here, in the page the reader is
 * looking at, so it lasts exactly as long as the page is open: there is no saving in the
 * background, and nothing is fetched that the reader did not ask for — by a press, or by
 * opening a text that is then kept on its own. `sw.js` reads what this file writes and
 * answers out of it when the network is not there.
 *
 * What is kept lives in one cache, `targum-offline`, with its index beside the files as
 * one JSON entry at `/offline/index`, so the worker can read it as easily as a page can.
 * A text is kept under the address its files are served under — `/reader/<name>/reader/`
 * — and that address is its id here.
 *
 * Nothing here runs on a page opened off a disk: there is no origin to keep anything for.
 */
(function () {
  "use strict";

  var STORE = "targum-offline";
  var INDEX = "/offline/index";
  var VERSION = 1;
  var READER = /^\/(?:reader\/[^/]+\/reader|parasha\/read\/[^/]+\/reader|[^/]+\/read\/\d{4}-\d{2}-\d{2}\/reader)\//;

  var served = /^https?:$/.test(location.protocol);
  var able =
    served &&
    typeof caches !== "undefined" &&
    typeof fetch === "function" &&
    "serviceWorker" in navigator;
  var key = window.TARGUM_KEY || new URLSearchParams(location.search).get("k") || "";

  /* The address a file is kept under — the worker's `keyOf`, the same rule written twice
     because the two never share a scope: a reader's own files lose their whole query, and
     anything else loses only the start-up key. `test_offline.py` holds the two together. */
  function keyOf(address) {
    var url = new URL(address, location.origin);
    url.hash = "";
    if (READER.test(url.pathname)) {
      url.search = "";
    } else {
      url.searchParams.delete("k");
    }
    return url.href;
  }

  // The text a page belongs to: the address its files are served under, or "".
  function textOf(address) {
    var url = new URL(address || location.href, location.origin);
    var found = READER.exec(url.pathname);
    return found ? found[0] : "";
  }

  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function headers(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  /* --- the index ------------------------------------------------------------- */

  var known = null; // the index as last read or written by this page

  function readIndex() {
    if (!able) return Promise.resolve({ version: VERSION, items: {} });
    return caches
      .open(STORE)
      .then(function (cache) {
        return cache.match(INDEX);
      })
      .then(function (answer) {
        return answer ? answer.json() : null;
      })
      .then(function (index) {
        known = index && index.items ? index : { version: VERSION, items: {} };
        return known;
      })
      .catch(function () {
        known = { version: VERSION, items: {} };
        return known;
      });
  }

  function writeIndex(index) {
    known = index;
    return caches
      .open(STORE)
      .then(function (cache) {
        return cache.put(
          INDEX,
          new Response(JSON.stringify(index), {
            headers: { "Content-Type": "application/json" },
          })
        );
      })
      .then(tellWorker)
      .then(function () {
        announce();
        return index;
      });
  }

  // The worker keeps the index in memory, so it is told when it changed.
  function tellWorker() {
    try {
      var worker = navigator.serviceWorker && navigator.serviceWorker.controller;
      if (worker) worker.postMessage({ type: "saved" });
    } catch (e) {}
  }

  var listeners = [];
  function announce() {
    listeners.forEach(function (listener) {
      try {
        listener(known);
      } catch (e) {}
    });
  }

  // Change one index under a lock, so two saves finishing together do not lose one.
  var queue = Promise.resolve();
  function change(edit) {
    var next = queue.then(function () {
      return readIndex().then(function (index) {
        var edited = edit(index) || index;
        return writeIndex(edited);
      });
    });
    queue = next.catch(function () {});
    return next;
  }

  /* --- what a text takes ---------------------------------------------------- */

  /* Every file of the text a page belongs to, with sizes, from the server (`/offline.json`).
     `film: false` leaves the picture out, for "Sound and text": the page carries its own
     sound, so a film's text without its sidecar still plays. */
  function plan(page, options) {
    var wantFilm = !(options && options.film === false);
    return fetch(keyed("/offline.json?page=" + encodeURIComponent(textOf(page) || page)), {
      headers: headers(),
      credentials: "same-origin",
    })
      .then(function (answer) {
        if (!answer.ok) throw new Error(String(answer.status));
        return answer.json();
      })
      .then(function (told) {
        var files = (told.files || []).filter(function (file) {
          return wantFilm || !file.film;
        });
        var hasFilm = (told.files || []).some(function (file) {
          return file.film;
        });
        return {
          id: told.base || textOf(page),
          title: told.title || "",
          files: files,
          film: hasFilm,
          bytes: files.reduce(function (sum, file) {
            return sum + Number(file.bytes || 0);
          }, 0),
        };
      });
  }

  /* A response as it is kept, the worker's `kept`: the body already decoded, so the
     headers that described the journey go. `count` hears every chunk as it lands. */
  function keep(answer, count) {
    var head = new Headers();
    answer.headers.forEach(function (value, name) {
      if (!/^(content-encoding|content-length|set-cookie|transfer-encoding)$/i.test(name)) {
        head.set(name, value);
      }
    });
    var body = answer.body;
    if (body && typeof TransformStream === "function" && body.pipeThrough) {
      body = body.pipeThrough(
        new TransformStream({
          transform: function (chunk, out) {
            count(chunk.byteLength || 0);
            out.enqueue(chunk);
          },
        })
      );
    }
    return new Response(body, { status: answer.status, statusText: answer.statusText, headers: head });
  }

  function isFull(error) {
    return !!error && (error.name === "QuotaExceededError" || error.code === 22);
  }

  /* Save the text `page` belongs to. Returns a handle at once:
       { done: Promise<item>, stop(), id }
     and calls `options.progress({done, total})` as bytes land. A failure rejects with
     `reason` "full" (the device has no room), "stopped" or "failed"; whatever this save
     had already put away is taken back out, unless the text was saved before it began. */
  function save(page, options) {
    options = options || {};
    var stopping = typeof AbortController === "function" ? new AbortController() : null;
    var handle = { id: textOf(page), stop: function () {}, done: null };
    if (!able) {
      handle.done = Promise.reject(reasoned("failed"));
      return handle;
    }
    var stopped = false;
    handle.stop = function () {
      stopped = true;
      if (stopping) stopping.abort();
    };
    var put = [];
    var wasSaved = false;
    handle.done = readIndex()
      .then(function (index) {
        wasSaved = !!index.items[handle.id];
        return plan(page, options);
      })
      .then(function (planned) {
        handle.id = planned.id;
        var total = planned.bytes;
        var done = 0;
        function told() {
          if (options.progress) {
            try {
              options.progress({ done: Math.min(done, total), total: total });
            } catch (e) {}
          }
        }
        told();
        return caches.open(STORE).then(function (cache) {
          // One file at a time: a film's part is tens of megabytes, and two at once
          // halves the speed of both for nothing.
          return planned.files
            .reduce(function (before, file) {
              return before.then(function () {
                if (stopped) throw reasoned("stopped");
                return fetch(keyed(file.url), {
                  headers: headers({ "X-Targum-Save": "1" }),
                  credentials: "same-origin",
                  signal: stopping ? stopping.signal : undefined,
                }).then(function (answer) {
                  if (!answer.ok) throw reasoned("failed");
                  put.push(keyOf(file.url));
                  return cache.put(
                    keyOf(file.url),
                    keep(answer, function (n) {
                      done += n;
                      told();
                    })
                  );
                });
              });
            }, Promise.resolve())
            .then(function () {
              done = total;
              told();
              return change(function (index) {
                var was = index.items[planned.id] || {};
                index.items[planned.id] = {
                  id: planned.id,
                  title: options.title || was.title || planned.title,
                  kind: options.kind || was.kind || "",
                  open: was.open || keyOf(options.open || page),
                  // Once a reader has saved it themselves, opening it again never makes
                  // it one of the texts that are kept on their own and let go.
                  how: was.how === "you" || options.how === "you" ? "you" : "auto",
                  film: planned.film,
                  withFilm: planned.files.some(function (f) {
                    return f.film;
                  }),
                  bytes: planned.bytes,
                  files: planned.files.map(function (f) {
                    return keyOf(f.url);
                  }),
                  at: Date.now(),
                };
                return index;
              }).then(function (index) {
                return index.items[planned.id];
              });
            });
        });
      })
      .catch(function (error) {
        var reason = stopped ? "stopped" : isFull(error) ? "full" : (error && error.reason) || "failed";
        var undo = wasSaved ? Promise.resolve() : forgetFiles(put);
        return undo.then(function () {
          throw reasoned(reason);
        });
      });
    return handle;
  }

  function reasoned(reason) {
    var error = new Error(reason);
    error.reason = reason;
    return error;
  }

  // Take files out of the cache, unless another saved text still keeps them.
  function forgetFiles(keys, index) {
    if (!keys.length) return Promise.resolve();
    var still = {};
    var items = (index || known || { items: {} }).items;
    Object.keys(items).forEach(function (id) {
      (items[id].files || []).forEach(function (file) {
        still[file] = true;
      });
    });
    return caches
      .open(STORE)
      .then(function (cache) {
        return Promise.all(
          keys
            .filter(function (k) {
              return !still[k];
            })
            .map(function (k) {
              return cache.delete(k);
            })
        );
      })
      .catch(function () {});
  }

  function remove(id) {
    var files = [];
    return change(function (index) {
      var item = index.items[id];
      if (!item) return index;
      files = item.files || [];
      delete index.items[id];
      return index;
    }).then(function (index) {
      return forgetFiles(files, index);
    });
  }

  // Everything off this device: the files and the index both.
  function removeAll() {
    if (!able) return Promise.resolve();
    return caches
      .delete(STORE)
      .then(function () {
        known = { version: VERSION, items: {} };
        tellWorker();
        announce();
      })
      .catch(function () {});
  }

  function register() {
    if (!able) return;
    // A page framed by another — the front page's picture of a reader, the talk drawer —
    // is not where the worker is asked for: the page around it already did.
    try {
      if (window.top !== window) return;
    } catch (e) {
      return;
    }
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
  }

  if (able) {
    if (document.readyState === "complete") register();
    else window.addEventListener("load", register);
  }

  window.TargumOffline = {
    able: able,
    keyOf: keyOf,
    textOf: textOf,
    plan: plan,
    save: save,
    remove: remove,
    removeAll: removeAll,
    list: function () {
      return readIndex().then(function (index) {
        return Object.keys(index.items).map(function (id) {
          return index.items[id];
        });
      });
    },
    // Whether a text is saved, from the index as this page last read it; `null` before
    // the first read has come back.
    saved: function (id) {
      if (!known) return null;
      return known.items[id] || false;
    },
    onChange: function (listener) {
      listeners.push(listener);
    },
    ready: readIndex,
  };
})();
