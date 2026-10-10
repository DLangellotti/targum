/* Saving texts for offline, from the page (design.md §12, "A worker keeps what the reader
 * saved, and fetches nothing else", and "A text is kept for offline by a press, or by
 * being opened", both 2026-10-09).
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
 * — and that address is its id here. A playlist is `playlist:<id>`, and holds texts.
 *
 * Two ways in, one index:
 *
 * - **Saved on its own.** Opening a text keeps it (`how: "auto"`), and the oldest of these
 *   is let go once there are more than the reader's number (5 unless they chose 3, 10 or
 *   none). A text with a contents page, a book or a series, keeps only the parts that
 *   were opened (`part: true`), each joining the last (David, 2026-10-10). Opening a text
 *   from a playlist keeps the whole playlist the same way.
 * - **Saved by you.** Save for offline, in a text's ⋯ or on a playlist's page
 *   (`how: "you"`): kept until it is removed.
 *
 * Nothing here runs on a page opened off a disk: there is no origin to keep anything for.
 */
(function () {
  "use strict";

  var STORE = "targum-offline";
  var INDEX = "/offline/index";
  var VERSION = 1;
  var READER = /^\/(?:reader\/[^/]+\/reader|parasha\/read\/[^/]+\/reader|[^/]+\/read\/\d{4}-\d{2}-\d{2}\/reader)\//;
  // What the reader chose about saving on its own: this device's, so this browser's.
  var CHOICES = "targum:offline";
  // A save under way in some tab of this browser, with when it last moved: the sweep of
  // files nobody indexed leaves them alone while it is fresh.
  var BUSY = "targum:offline:busy";
  var RECENT_CHOICES = [0, 3, 5, 10];

  /* The page that lists what is saved, kept so that it opens with no connection; its
     query (`?away=`) is for the page to read, so it is one page whatever it says. */
  var SAVED = "/you/saved";
  var served = /^https?:$/.test(location.protocol);
  var able =
    served &&
    typeof caches !== "undefined" &&
    typeof fetch === "function" &&
    "serviceWorker" in navigator;
  var key = window.TARGUM_KEY || new URLSearchParams(location.search).get("k") || "";

  function t(name, english, fill) {
    var strings = window.TargumStrings;
    if (strings && strings.t) return strings.t(name, english, fill);
    return english.replace(/\{(\w+)\}/g, function (all, field) {
      return fill && field in fill ? String(fill[field]) : all;
    });
  }

  /* The address a file is kept under — the worker's `keyOf`, the same rule written twice
     because the two never share a scope: a reader's own files lose their whole query, and
     anything else loses only the start-up key. `test_offline.py` holds the two together. */
  function keyOf(address) {
    var url = new URL(address, location.origin);
    url.hash = "";
    if (READER.test(url.pathname) || url.pathname === SAVED) {
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

  /* --- what the reader chose -------------------------------------------------- */

  function choices() {
    var kept = {};
    try {
      kept = JSON.parse(localStorage.getItem(CHOICES) || "{}") || {};
    } catch (e) {
      kept = {};
    }
    var recent = Number(kept.recent);
    return {
      recent: RECENT_CHOICES.indexOf(recent) >= 0 ? recent : 5,
      playlist: kept.playlist !== false,
      // A film saves with its picture unless the reader chose sound and text.
      film: kept.film !== false,
    };
  }

  function choose(patch) {
    var next = choices();
    Object.keys(patch || {}).forEach(function (name) {
      next[name] = patch[name];
    });
    try {
      localStorage.setItem(CHOICES, JSON.stringify(next));
    } catch (e) {}
    return trim().then(function () {
      return next;
    });
  }

  /* --- the index ------------------------------------------------------------- */

  var known = null; // the index as last read or written by this page

  function empty() {
    return { version: VERSION, items: {} };
  }

  function readIndex() {
    if (!able) return Promise.resolve(empty());
    return caches
      .open(STORE)
      .then(function (cache) {
        return cache.match(INDEX);
      })
      .then(function (answer) {
        return answer ? answer.json() : null;
      })
      .then(function (index) {
        known = index && index.items ? index : empty();
        return known;
      })
      .catch(function () {
        known = empty();
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
    var wantFilm = options && options.film !== undefined ? options.film : choices().film;
    // A part alone names the page itself; the whole is asked for by the text's address.
    var asked = options && options.part ? keyOf(page).replace(location.origin, "") : textOf(page) || page;
    var narrow = options && options.part ? "&part=1" : "";
    return fetch(keyed("/offline.json?page=" + encodeURIComponent(asked) + narrow), {
      headers: headers(),
      credentials: "same-origin",
    })
      .then(function (answer) {
        if (!answer.ok) throw reasoned("failed");
        return answer.json();
      })
      .then(function (told) {
        var files = (told.files || []).filter(function (file) {
          return wantFilm || !file.film;
        });
        return {
          id: told.base || textOf(page),
          title: told.title || "",
          kind: told.kind || "",
          name: told.name || "",
          pages: told.pages || 0,
          part: !!told.part,
          files: files,
          film: (told.files || []).some(function (file) {
            return file.film;
          }),
          sound: files.some(function (file) {
            return /\.mp3$/i.test(file.url);
          }),
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

  function reasoned(reason) {
    var error = new Error(reason);
    error.reason = reason;
    return error;
  }

  function busy() {
    try {
      localStorage.setItem(BUSY, String(Date.now()));
    } catch (e) {}
  }

  /* Save the text `page` belongs to. Returns a handle at once:
       { done: Promise<item>, stop(), id }
     and calls `options.progress({done, total})` as bytes land. A failure rejects with
     `reason` "full" (the device has no room), "stopped" or "failed"; whatever this save
     had already put away is taken back out, unless the text was saved before it began.

     A file already in the cache is not fetched again: a save the reader left halfway —
     they turned the page, and the page is what was saving — picks up where it stopped. */
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
          busy();
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
                var at = keyOf(file.url);
                return cache.match(at).then(function (had) {
                  if (had) {
                    done += Number(file.bytes || 0);
                    told();
                    return null;
                  }
                  return fetch(keyed(file.url), {
                    headers: headers({ "X-Targum-Save": "1" }),
                    credentials: "same-origin",
                    signal: stopping ? stopping.signal : undefined,
                  }).then(function (answer) {
                    if (!answer.ok) throw reasoned("failed");
                    put.push(at);
                    return cache.put(
                      at,
                      keep(answer, function (n) {
                        done += n;
                        told();
                      })
                    );
                  });
                });
              });
            }, Promise.resolve())
            .then(function () {
              done = total;
              told();
              return change(function (index) {
                var was = index.items[planned.id] || {};
                // A part saved on its own, of a text kept whole meanwhile: nothing to add.
                if (planned.part && index.items[planned.id] && !was.part) {
                  if (options.opened) was.opened = Date.now();
                  return index;
                }
                var held = (was.held || []).slice();
                // A part joins the parts already kept; the whole replaces them.
                var files = planned.files.map(function (f) {
                  return keyOf(f.url);
                });
                var bytes = planned.bytes;
                var pages = planned.pages;
                if (planned.part && was.part) {
                  files = (was.files || []).slice();
                  bytes = Number(was.bytes || 0);
                  planned.files.forEach(function (f) {
                    if (files.indexOf(keyOf(f.url)) >= 0) return;
                    files.push(keyOf(f.url));
                    bytes += Number(f.bytes || 0);
                  });
                  pages = files.filter(function (one) {
                    return /\.html$/i.test(one);
                  }).length;
                }
                if (options.held && held.indexOf(options.held) < 0) held.push(options.held);
                index.items[planned.id] = {
                  id: planned.id,
                  title: options.title || was.title || planned.title,
                  kind: options.kind || was.kind || planned.kind,
                  name: planned.name || was.name || "",
                  pages: pages,
                  part: planned.part,
                  open: was.open || keyOf(options.open || page),
                  // Once a reader has saved it themselves, opening it again never makes
                  // it one of the texts that are kept on their own and let go.
                  how: was.how === "you" || options.how === "you" ? "you" : "auto",
                  held: held,
                  film: (planned.part && was.film) || planned.film,
                  sound: (planned.part && was.sound) || planned.sound,
                  withFilm: (planned.part && was.withFilm) || planned.files.some(function (f) {
                    return f.film;
                  }),
                  bytes: bytes,
                  files: files,
                  at: was.at || Date.now(),
                  opened: options.opened ? Date.now() : was.opened || 0,
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

  /* Save a playlist, every text in it that can be opened, one after another. The handle
     is a text's; `progress` hears `{done, total}` in texts. One text that cannot be had
     does not stop the rest, and the set is said to have failed at the end; a device with
     no room stops it at once. */
  function saveSet(id, options) {
    options = options || {};
    var current = null;
    var stopped = false;
    var setId = "playlist:" + id;
    var handle = {
      id: setId,
      stop: function () {
        stopped = true;
        if (current) current.stop();
      },
      done: null,
    };
    if (!able) {
      handle.done = Promise.reject(reasoned("failed"));
      return handle;
    }
    handle.done = fetch(keyed("/playlists/" + encodeURIComponent(id) + ".json"), {
      headers: headers({ Accept: "application/json" }),
      credentials: "same-origin",
    })
      .then(function (answer) {
        if (!answer.ok) throw reasoned("failed");
        return answer.json();
      })
      .then(function (playlist) {
        var items = (playlist.items || []).filter(function (item) {
          return item.open && !item.failed;
        });
        var members = [];
        var missed = 0;
        var done = 0;
        function told() {
          if (options.progress) {
            try {
              options.progress({ done: done, total: items.length });
            } catch (e) {}
          }
        }
        told();
        return items
          .reduce(function (before, item) {
            return before.then(function () {
              if (stopped) throw reasoned("stopped");
              current = save(item.open, {
                how: "auto",
                held: setId,
                title: item.title,
                kind: (item.facts && item.facts.kind) || "",
              });
              return current.done.then(
                function (saved) {
                  members.push(saved.id);
                  done += 1;
                  told();
                },
                function (error) {
                  if (error && (error.reason === "full" || error.reason === "stopped")) throw error;
                  missed += 1;
                }
              );
            });
          }, Promise.resolve())
          .then(function () {
            return change(function (index) {
              var was = index.items[setId] || {};
              index.items[setId] = {
                id: setId,
                kind: "playlist",
                title: playlist.name || was.title || "",
                how: was.how === "you" || options.how === "you" ? "you" : "auto",
                members: members,
                count: items.length,
                bytes: members.reduce(function (sum, member) {
                  return sum + Number((index.items[member] || {}).bytes || 0);
                }, 0),
                at: was.at || Date.now(),
                opened: Date.now(),
              };
              return index;
            });
          })
          .then(function (index) {
            if (missed) throw reasoned("failed");
            return index.items[setId];
          });
      })
      .catch(function (error) {
        throw reasoned(stopped ? "stopped" : (error && error.reason) || "failed");
      });
    return handle;
  }

  // Take files out of the cache, unless another saved text still keeps them.
  function forgetFiles(keys, index) {
    if (!keys.length) return Promise.resolve();
    var still = {};
    var items = (index || known || empty()).items;
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

  /* Take a text or a playlist off this device. A playlist lets go of the texts it held,
     and a text it held that nothing else keeps goes with it — unless it was opened, in
     which case it is one of the recent texts and `trim` decides. */
  function remove(id) {
    var files = [];
    return change(function (index) {
      var item = index.items[id];
      if (!item) return index;
      delete index.items[id];
      if (item.kind === "playlist") {
        Object.keys(index.items).forEach(function (other) {
          var text = index.items[other];
          if (!text.held || text.held.indexOf(id) < 0) return;
          text.held = text.held.filter(function (one) {
            return one !== id;
          });
          if (text.how === "auto" && !text.held.length && !text.opened) {
            files = files.concat(text.files || []);
            delete index.items[other];
          }
        });
      } else {
        files = item.files || [];
        // And out of any playlist that held it.
        Object.keys(index.items).forEach(function (other) {
          var set = index.items[other];
          if (set.members) {
            set.members = set.members.filter(function (one) {
              return one !== id;
            });
          }
        });
      }
      return index;
    })
      .then(function (index) {
        return forgetFiles(files, index);
      })
      .then(trim);
  }

  /* Kept until removed: a text or a playlist saved on its own becomes one the reader saved. */
  function keepIt(id) {
    return change(function (index) {
      if (index.items[id]) index.items[id].how = "you";
      return index;
    });
  }

  /* Let go of the texts kept on their own beyond the reader's number, oldest opened first,
     and the playlist kept on its own when the reader turned that off. A text a playlist
     still holds is the playlist's to let go. */
  function trim() {
    if (!able) return Promise.resolve();
    var chosen = choices();
    var files = [];
    return change(function (index) {
      var items = index.items;
      if (!chosen.playlist) {
        Object.keys(items).forEach(function (id) {
          var set = items[id];
          if (set.kind !== "playlist" || set.how !== "auto") return;
          delete items[id];
          Object.keys(items).forEach(function (other) {
            if (items[other].held) {
              items[other].held = items[other].held.filter(function (one) {
                return one !== id;
              });
            }
          });
        });
      }
      var mine = Object.keys(items)
        .map(function (id) {
          return items[id];
        })
        .filter(function (item) {
          return item.kind !== "playlist" && item.how === "auto" && !(item.held || []).length;
        })
        .sort(function (a, b) {
          return Number(b.opened || 0) - Number(a.opened || 0);
        });
      mine.slice(chosen.recent).forEach(function (item) {
        files = files.concat(item.files || []);
        delete items[item.id];
      });
      return index;
    }).then(function (index) {
      return forgetFiles(files, index);
    });
  }

  /* One desk page kept so it opens with no connection: the Saved page, which the banner
     sends a reader to. Fetched once, the first time it is opened — the worker keeps it
     as it is each time after that, the way it keeps a saved text's pages. */
  function keepPage(address) {
    if (!able) return Promise.resolve();
    var url = new URL(address, location.origin);
    var id = "page:" + url.pathname;
    var at = keyOf(address);
    return caches
      .open(STORE)
      .then(function (cache) {
        return cache.match(at).then(function (had) {
          if (had) return null;
          return fetch(keyed(url.pathname), {
            headers: headers({ "X-Targum-Save": "1" }),
            credentials: "same-origin",
          }).then(function (answer) {
            if (!answer.ok) return null;
            return cache.put(at, keep(answer, function () {}));
          });
        });
      })
      .then(function () {
        return readIndex();
      })
      .then(function (index) {
        if (index.items[id]) return null;
        return change(function (fresh) {
          fresh.items[id] = { id: id, kind: "page", how: "page", files: [at], bytes: 0, at: Date.now() };
          return fresh;
        });
      })
      .catch(function () {});
  }

  // Everything off this device: the files and the index both.
  function removeAll() {
    if (!able) return Promise.resolve();
    return caches
      .delete(STORE)
      .then(function () {
        known = empty();
        tellWorker();
        announce();
      })
      .catch(function () {});
  }

  /* Files in the cache that no saved text names: a save the page was closed in the middle
     of. Left alone while any tab of this browser is still saving. */
  function sweep() {
    var since = 0;
    try {
      since = Number(localStorage.getItem(BUSY) || 0);
    } catch (e) {}
    if (Date.now() - since < 60 * 1000) return Promise.resolve();
    return Promise.all([readIndex(), caches.open(STORE)])
      .then(function (both) {
        var index = both[0];
        var cache = both[1];
        var named = {};
        named[new URL(INDEX, location.origin).href] = true;
        Object.keys(index.items).forEach(function (id) {
          (index.items[id].files || []).forEach(function (file) {
            named[file] = true;
          });
        });
        return cache.keys().then(function (requests) {
          return Promise.all(
            requests
              .filter(function (request) {
                return !named[request.url];
              })
              .map(function (request) {
                return cache.delete(request);
              })
          );
        });
      })
      .catch(function () {});
  }

  /* --- how much room ---------------------------------------------------------- */

  // A size the way the menus say it: "3 MB", "1.2 MB", "103 MB", "1.4 GB".
  function size(bytes) {
    var mb = Number(bytes || 0) / 1e6;
    if (mb >= 1000) {
      return t("offline.gb", "{n} GB", { n: tidy(mb / 1000) });
    }
    return t("offline.mb", "{n} MB", { n: tidy(mb) });
  }

  // One place after the point under ten, none above; never "0".
  function tidy(n) {
    if (n >= 10) return String(Math.round(n));
    var one = Math.round(n * 10) / 10;
    if (one === 0) one = 0.1;
    return String(one).replace(/\.0$/, "").replace(".", t("offline.decimal-point", "."));
  }

  function sizeOf(done, total) {
    var mb = Number(total || 0) / 1e6;
    if (mb >= 1000) {
      return t("offline.of-gb", "{done} of {total} GB", {
        done: tidy(Number(done) / 1e9),
        total: tidy(mb / 1000),
      });
    }
    return t("offline.of-mb", "{done} of {total} MB", {
      done: tidy(Number(done) / 1e6),
      total: tidy(mb),
    });
  }

  /* --- drawn --------------------------------------------------------------------- */

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function press(className, label, onPress) {
    var button = element("button", className, label);
    button.type = "button";
    button.addEventListener("click", onPress);
    return button;
  }

  function bar(share) {
    var track = element("span", "offline-bar");
    var fill = element("span", "offline-fill");
    fill.style.inlineSize = Math.round(Math.max(0, Math.min(1, share)) * 100) + "%";
    track.appendChild(fill);
    track.setAttribute("aria-hidden", "true");
    return track;
  }

  /* The drawing at the start of a row in a reader's ⋯ (`data-glyphs`; design.md §12,
     2026-10-09, "The reader's menus are the board's"): an arrow down to save, a tick
     once it is here. The menu's rows each start with one; a playlist's page has none. */
  var GLYPHS = {
    save: '<path d="M8 2.5v7.5M4.75 7 8 10.25 11.25 7M3 13.5h10"></path>',
    saved: '<path d="M3 8.5 6.5 12 13 4.5"></path>',
  };
  function glyph(row, kind) {
    if (!row.hasAttribute("data-glyphs")) return null;
    var span = element("span", "m-icon offline-glyph");
    span.setAttribute("aria-hidden", "true");
    span.innerHTML = '<svg viewBox="0 0 16 16" focusable="false">' + GLYPHS[kind] + "</svg>";
    return span;
  }

  /* The saves this page is making, by id, so a menu drawn again while one runs shows it
     and a second press does not start another. */
  var running = {};
  // The parts of texts being saved on their own, by page: a part says nothing in the row.
  var parting = {};

  /* One row that says where a text or a playlist stands and offers the one thing to do
     next: save, stop, remove, try again. `what` is { id, title, start(progress) → handle,
     kind: "text"|"playlist" }, and `row` is redrawn in place. */
  function drawRow(row, what) {
    row.textContent = "";
    row.className = row.className.replace(/\boffline-(idle|saving|saved|failed|full)\b/g, "").trim();
    var state = running[what.id];
    var item = known && known.items[what.id];
    var playlist = what.kind === "playlist";
    function redraw() {
      drawRow(row, what);
    }
    function begin() {
      var job = { progress: { done: 0, total: 0 }, error: null };
      running[what.id] = job;
      job.handle = what.start(function (progress) {
        job.progress = progress;
        if (running[what.id] === job) redraw();
      });
      job.handle.done.then(
        function () {
          delete running[what.id];
          redraw();
        },
        function (error) {
          job.error = (error && error.reason) || "failed";
          job.handle = null;
          if (job.error === "stopped") delete running[what.id];
          redraw();
        }
      );
      redraw();
    }
    if (state && state.handle) {
      row.classList.add("offline-saving");
      var saving = glyph(row, "save");
      if (saving) row.appendChild(saving);
      var head = element("span", "offline-what");
      head.appendChild(element("span", "offline-label", t("offline.saving", "Saving for offline")));
      var counted = playlist
        ? t("offline.of-texts", "{done} of {total}", {
            done: state.progress.done,
            total: state.progress.total,
          })
        : sizeOf(state.progress.done, state.progress.total);
      head.appendChild(element("span", "offline-size", counted));
      row.appendChild(head);
      row.appendChild(
        press("offline-stop", t("offline.stop", "Stop"), function () {
          state.handle.stop();
        })
      );
      row.appendChild(bar(state.progress.total ? state.progress.done / state.progress.total : 0));
      row.appendChild(
        element("p", "offline-note", t("offline.keep-open", "Keep this page open until it's saved."))
      );
      return;
    }
    if (state && state.error) {
      // A line in a card (design.md §12, "A refusal is drawn on one of five surfaces"):
      // what went wrong in words, and the one thing to do about it.
      var full = state.error === "full";
      row.classList.add(full ? "offline-full" : "offline-failed");
      var sentence = full
        ? t(
            "offline.full",
            "This device is full, so we couldn't save {title}. Remove something you've finished and try again.",
            { title: what.title || t("offline.this-text", "this text") }
          )
        : t("offline.failed", "We couldn't save this for offline.");
      var again = function () {
        delete running[what.id];
        begin();
      };
      var fault = window.TargumFault;
      if (full && fault && fault.line) {
        // Room is made on the page of what is saved, so that is where it goes.
        var room = fault.line(sentence, t("offline.see-saved", "Saved on this device"), function () {
          location.assign(keyed(SAVED));
        });
        room.classList.add("offline-said");
        row.appendChild(room);
      } else if (fault && fault.line) {
        var said = fault.line(sentence, t("offline.try-again", "Try again"), again);
        said.classList.add("offline-said");
        row.appendChild(said);
      } else {
        row.appendChild(element("p", "offline-said", sentence));
        row.appendChild(press("offline-again", t("offline.try-again", "Try again"), again));
      }
      return;
    }
    // A text kept only in the parts that were opened is not saved: the row offers the whole.
    if (item && !item.part) {
      row.classList.add("offline-saved");
      var tick = glyph(row, "saved");
      if (tick) row.appendChild(tick);
      var saved = element("span", "offline-what");
      saved.appendChild(
        element(
          "span",
          "offline-label",
          playlist
            ? t("offline.saved-playlist", "Saved for offline")
            : t("offline.saved", "Saved on this device")
        )
      );
      saved.appendChild(element("span", "offline-size", size(item.bytes)));
      row.appendChild(saved);
      row.appendChild(
        press(
          "offline-remove",
          playlist ? t("offline.remove", "Remove") : t("offline.remove-here", "Remove from this device"),
          function () {
            remove(what.id).then(redraw);
          }
        )
      );
      return;
    }
    row.classList.add("offline-idle");
    var go = press("offline-go", "", begin);
    var arrow = glyph(row, "save");
    if (arrow) go.appendChild(arrow);
    go.appendChild(element("span", "offline-label", t("offline.save", "Save for offline")));
    var meta = element("span", "offline-size", what.bytes ? size(what.bytes) : "");
    go.appendChild(meta);
    row.appendChild(go);
  }

  /* --- in a reader --------------------------------------------------------------- */

  function inReader() {
    var row = document.getElementById("offline-row");
    var here = textOf(location.href);
    if (!row || !here) return;
    try {
      if (window.top !== window) return;
    } catch (e) {
      return;
    }
    var titled = row.getAttribute("data-title") || document.title;
    var what = {
      id: here,
      title: titled,
      kind: "text",
      bytes: 0,
      start: function (progress) {
        return save(location.href, { how: "you", title: titled, progress: progress });
      },
    };
    function draw() {
      drawRow(row, what);
    }
    readIndex().then(function () {
      row.hidden = false;
      draw();
      // The size, asked once the reader opens the menu: what it will take, before it is
      // pressed. Not asked while the menu is shut, which is most of the time.
      var more = document.getElementById("more");
      var asked = false;
      function sized() {
        if (asked || !more || !more.classList.contains("open")) return;
        asked = true;
        plan(location.href).then(
          function (planned) {
            what.bytes = planned.bytes;
            var had = known && known.items[here];
            if (!running[here] && !(had && !had.part)) draw();
          },
          function () {}
        );
      }
      if (more && typeof MutationObserver === "function") {
        new MutationObserver(sized).observe(more, { attributes: true, attributeFilter: ["class"] });
      }
      sized();
    });
    onChange(function () {
      if (!running[here]) draw();
    });
    // Saved on its own: this text, once the page has settled, then the playlist it was
    // opened from. Never in a frame, never off a disk, and not when the reader chose none.
    whenSettled(function () {
      var chosen = choices();
      var list = new URLSearchParams(location.search).get("list");
      var first = chosen.recent > 0 ? autoText(what, draw) : Promise.resolve();
      first.then(function () {
        if (list && /^\d+$/.test(list) && chosen.playlist) return autoSet(list);
        return null;
      });
    });
  }

  function whenSettled(then) {
    function later() {
      setTimeout(then, 1500);
    }
    if (document.readyState === "complete") later();
    else window.addEventListener("load", later);
  }

  // This text, kept on its own: opened again it is only marked as opened, never fetched
  // again (the worker already keeps its pages as they were last opened). A text with a
  // contents page keeps only the parts that were opened, the contents page among them,
  // and each part opened later joins them (David, 2026-10-10): the whole is the press.
  // A part saved on its own says nothing in the row, which still offers the whole.
  function autoText(what, draw) {
    var page = keyOf(location.href);
    return readIndex().then(function (index) {
      var item = index.items[what.id];
      if (item && (!item.part || hasPage(item, page))) {
        return change(function (fresh) {
          if (fresh.items[what.id]) fresh.items[what.id].opened = Date.now();
          return fresh;
        }).then(trim);
      }
      if (running[what.id] || parting[page]) return null;
      parting[page] = true;
      var handle = save(location.href, {
        how: "auto",
        opened: true,
        part: true,
        title: what.title,
      });
      return handle.done.then(
        function () {
          delete parting[page];
          draw();
          return trim();
        },
        function () {
          delete parting[page];
        }
      );
    });
  }

  // Whether a text kept in parts holds the page at `address`: the text's own address
  // stands for its contents page, `index.html`.
  function hasPage(item, address) {
    var at = keyOf(address);
    if (/\/$/.test(at)) at += "index.html";
    return (item.files || []).indexOf(at) >= 0;
  }

  function autoSet(list) {
    var id = "playlist:" + list;
    return readIndex().then(function (index) {
      var set = index.items[id];
      if (running[id]) return null;
      // Kept already, and nothing added since it was: only marked as opened.
      if (set && set.members && set.members.length >= Number(set.count || 0)) {
        return change(function (fresh) {
          if (fresh.items[id]) fresh.items[id].opened = Date.now();
          return fresh;
        });
      }
      var job = { progress: { done: 0, total: 0 }, error: null };
      running[id] = job;
      job.handle = saveSet(list, {
        how: "auto",
        progress: function (progress) {
          job.progress = progress;
        },
      });
      return job.handle.done.then(
        function () {
          delete running[id];
          announce();
        },
        function (error) {
          job.handle = null;
          job.error = (error && error.reason) || "failed";
          announce();
        }
      );
    });
  }

  /* --- on a playlist's card and its page (playlists.js's slot) -------------------- */

  function onPlaylist(one, slot, where) {
    if (!able || !one || one.id === undefined) return false;
    var id = "playlist:" + one.id;
    var what = {
      id: id,
      title: one.name || "",
      kind: "playlist",
      bytes: 0,
      start: function (progress) {
        return saveSet(one.id, { how: "you", progress: progress });
      },
    };
    slot.classList.add("offline-row");
    if (where === "card") {
      // A card says only what is so: saved, or being saved. The press is on its page.
      var drawCard = function () {
        slot.textContent = "";
        var state = running[id];
        var item = known && known.items[id];
        if (state && state.handle) {
          slot.textContent = t("offline.saving-texts", "Saving for offline · {done} of {total}", {
            done: state.progress.done,
            total: state.progress.total,
          });
        } else if (item) {
          slot.textContent = t("offline.saved-size", "Saved for offline · {size}", {
            size: size(item.bytes),
          });
        }
        slot.hidden = !slot.textContent;
      };
      readIndex().then(drawCard);
      onChange(drawCard);
      return true;
    }
    // The page's press is a pill with its drawing at the start, the arrow down or the
    // tick, as the reader's menu rows are (board PlaylistDetail).
    slot.setAttribute("data-glyphs", "");
    function draw() {
      drawRow(slot, what);
    }
    readIndex().then(function () {
      draw();
      // What it will take, said before it is pressed (board PlaylistDetail: "Save for
      // offline [64 MB]"): each text's own plan, added up. Asked only while nothing is
      // kept or running, which is the only time the press shows a size.
      if (known && known.items[id]) return;
      var texts = (one.items || []).filter(function (item) {
        return item && item.open && !item.failed;
      });
      if (!texts.length) return;
      Promise.all(
        texts.map(function (item) {
          return plan(new URL(item.open, location.origin).href).then(
            function (planned) {
              return planned.bytes || 0;
            },
            function () {
              return 0;
            }
          );
        })
      ).then(function (sizes) {
        what.bytes = sizes.reduce(function (sum, n) {
          return sum + n;
        }, 0);
        if (!running[id] && !(known && known.items[id])) draw();
      });
    });
    onChange(function () {
      if (!running[id] || !running[id].handle) draw();
    });
    return true;
  }

  /* --- with no connection (design.md §12, "With no connection, a page says what still
   * works", 2026-10-09; boards OffOfflineDesk, OffOfflineHomePhone, OffOfflineReaderPhone,
   * OffOfflineUnsavedPhone, OffOfflineLookupPhone and OffBackPhone) ----------------------
   *
   * Said by the connection's banner (`TargumFault.unreachable`, the error surface of the
   * same day), which this file adds two things to: the way to what is saved, and how many
   * changes are waiting to go. Under it, the page says what it can and cannot do: a text
   * not on this device is dimmed and says so, Talk and Upload are greyed with the reason,
   * and a word with no meaning in the page can be asked about later. When the connection
   * comes back, what was done offline goes at once, and a band says so until it has gone.
   *
   * Never a word about how long a browser keeps what is saved, and never an offer to add
   * targum to a home screen (David, 2026-10-08).
   */

  var ASKS = "targum:offline:asks";

  function away() {
    return served && typeof navigator !== "undefined" && navigator.onLine === false;
  }

  // How many changes are waiting to go up: the sync layer counts them.
  function owed() {
    var sync = window.TargumSync;
    try {
      return sync && typeof sync.owed === "function" ? sync.owed() : 0;
    } catch (e) {
      return 0;
    }
  }

  function tn(name, count, one, other, fill) {
    var strings = window.TargumStrings;
    if (strings && strings.tn) return strings.tn(name, count, one, other, fill);
    return (count === 1 ? one : other).replace("{n}", String(count));
  }

  /* What the banner carries besides its sentence: asked for by `fault.js` every time it
     draws the banner, so a page's own "we couldn't reach targum" says the same. */
  function inBanner(band) {
    if (!away() && !document.documentElement.classList.contains("is-away")) return;
    var saved = element("a", "offline-to-saved", t("offline.saved-texts", "Saved texts"));
    saved.href = keyed(SAVED);
    band.appendChild(saved);
    var waiting = element("span", "offline-owed");
    band.appendChild(waiting);
    countOwed(waiting);
  }

  function countOwed(node) {
    var spot = node || document.querySelector("#fault-banner .offline-owed");
    if (!spot) return;
    var n = owed();
    spot.textContent = n
      ? tn(
          "offline.owed",
          n,
          "{n} change saved here, sent when you're back",
          "{n} changes saved here, sent when you're back"
        )
      : "";
    spot.hidden = !n;
  }

  // Containers a text's link stands in, where the dimming and its reason go.
  function holderOf(link) {
    return link.closest("li, article, tr, .row, .card") || link;
  }

  /* Every link to a text on the page: dimmed with its reason where the text is not on
     this device, and said to be here where it is. Nothing is fetched to find out: the
     index this page already read is the whole of the answer. */
  function markLinks() {
    if (!known) return;
    var links = document.querySelectorAll("main a[href], .site-main a[href], #continue a[href]");
    Array.prototype.forEach.call(links, function (link) {
      var id = "";
      try {
        id = textOf(new URL(link.getAttribute("href"), location.href).href);
      } catch (e) {
        id = "";
      }
      // The page of what is saved says so of every row already. A link within this text
      // is marked only where the text is kept in parts, chapter by chapter.
      if (!id || link.closest(".saved-row")) return;
      var item = known.items[id];
      if (id === textOf(location.href) && !(item && item.part)) return;
      var holder = holderOf(link);
      if (holder.getAttribute("data-offline")) return;
      var here = !!item && (!item.part || hasPage(item, link.href));
      holder.setAttribute("data-offline", here ? "here" : "away");
      if (!here) holder.classList.add("offline-away");
      var tag = element(
        "span",
        "offline-tag" + (here ? " is-here" : ""),
        here ? t("offline.here", "On this device") : t("offline.not-here", "Not on this device")
      );
      tag.setAttribute("data-offline-tag", "");
      (holder === link ? link.parentNode : holder).insertBefore(
        tag,
        holder === link ? link.nextSibling : null
      );
      if (!here) {
        link.setAttribute("aria-disabled", "true");
        link.setAttribute(
          "data-offline-why",
          t("offline.not-here-why", "This text isn't on this device, so it opens when you're back online.")
        );
      }
    });
  }

  function unmarkLinks() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-offline]"), function (holder) {
      holder.removeAttribute("data-offline");
      holder.classList.remove("offline-away");
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-offline-tag]"), function (tag) {
      tag.remove();
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-offline-why]"), function (link) {
      link.removeAttribute("aria-disabled");
      link.removeAttribute("data-offline-why");
    });
  }

  // What needs the connection, greyed, with the reason beside it.
  var NEEDS = [
    {
      // The pill, the conversation's Send, and Ask on a word's card, which asks it.
      find: "#talk-open, .talk-cta, .chat-send, .gloss-card .ask-go",
      why: function () {
        return t("offline.talk-needs", "Talk needs the connection.");
      },
    },
    {
      find: 'a[href="/add"], a[href^="/add?"], .site-nav a[href*="/add"]',
      why: function () {
        return t("offline.upload-needs", "Uploading needs the connection.");
      },
    },
  ];

  function greyNeeds() {
    NEEDS.forEach(function (need) {
      Array.prototype.forEach.call(document.querySelectorAll(need.find), function (node) {
        if (node.getAttribute("data-offline-off")) return;
        node.setAttribute("data-offline-off", "1");
        node.classList.add("offline-off");
        node.setAttribute("aria-disabled", "true");
        node.setAttribute("data-why", need.why());
        if (!node.getAttribute("title")) {
          node.setAttribute("title", need.why());
          node.setAttribute("data-offline-titled", "1");
        }
      });
    });
  }

  function ungreyNeeds() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-offline-off]"), function (node) {
      node.removeAttribute("data-offline-off");
      node.classList.remove("offline-off");
      node.removeAttribute("aria-disabled");
      node.removeAttribute("data-why");
      if (node.getAttribute("data-offline-titled")) {
        node.removeAttribute("title");
        node.removeAttribute("data-offline-titled");
      }
    });
  }

  // A press on something that needs the connection, or on a text that is not here, says
  // why instead of failing: a link left to fail opens the browser's own offline page.
  document.addEventListener(
    "click",
    function (event) {
      if (!away()) return;
      var target =
        event.target && event.target.closest
          ? event.target.closest("[data-offline-off], [data-offline-why]")
          : null;
      if (!target) return;
      event.preventDefault();
      event.stopPropagation();
      var why = target.getAttribute("data-why") || target.getAttribute("data-offline-why");
      say(target, why);
    },
    true
  );

  // One short line, under the band, for the press that was just refused.
  function say(near, why) {
    var line = document.getElementById("offline-why");
    if (!line) {
      line = element("p", "offline-why");
      line.id = "offline-why";
      line.setAttribute("role", "status");
      var band = document.getElementById("fault-banner");
      if (band && band.parentNode) band.parentNode.insertBefore(line, band.nextSibling);
      else document.body.appendChild(line);
    }
    line.textContent = why || "";
    line.hidden = !why;
  }

  var watching = null;
  var counting = null;

  function enterAway() {
    document.documentElement.classList.add("is-away");
    if (window.TargumFault && window.TargumFault.unreachable) window.TargumFault.unreachable();
    readIndex().then(function () {
      markLinks();
      greyNeeds();
    });
    // Home and the shelves draw their rows after they load: marked as they arrive.
    if (!watching && typeof MutationObserver === "function" && document.body) {
      var soon = null;
      watching = new MutationObserver(function () {
        if (soon) return;
        soon = setTimeout(function () {
          soon = null;
          if (away()) {
            markLinks();
            greyNeeds();
          }
        }, 150);
      });
      watching.observe(document.body, { childList: true, subtree: true });
    }
    // What is waiting to go grows as the reader reads.
    if (!counting) {
      counting = setInterval(function () {
        countOwed();
      }, 2000);
    }
  }

  function back() {
    var band = document.getElementById("offline-back");
    if (!band) {
      band = element("p", "offline-back");
      band.id = "offline-back";
      band.setAttribute("role", "status");
      var fault = document.getElementById("fault-banner");
      if (fault && fault.parentNode) {
        fault.parentNode.insertBefore(band, fault.nextSibling);
        if (fault.classList.contains("is-under-bar")) band.classList.add("is-under-bar");
      } else {
        document.body.insertBefore(band, document.body.firstChild);
      }
    }
    return band;
  }

  /* Back: everything done offline goes at once — the words and the places, then the
     words asked about — and the band says so until it has gone. */
  function leaveAway() {
    document.documentElement.classList.remove("is-away");
    if (watching) {
      watching.disconnect();
      watching = null;
    }
    if (counting) {
      clearInterval(counting);
      counting = null;
    }
    unmarkLinks();
    ungreyNeeds();
    say(null, "");
    var band = back();
    band.textContent = t("offline.back", "We're back. Sending what you did offline.");
    band.hidden = false;
    var sync = window.TargumSync;
    var sent = sync && typeof sync.flush === "function" ? sync.flush() : Promise.resolve(true);
    Promise.all([sent, askNow()]).then(
      function () {
        band.hidden = true;
      },
      function () {
        band.hidden = true;
      }
    );
  }

  /* --- a word asked about with no connection ------------------------------------------
     "Look it up when I'm back": the reader's own press, kept until there is a connection
     and then made exactly as the tap would have made it — the same request, so the same
     cost and no other. Kept in this browser, so it goes from whatever page is open. */

  function asks() {
    try {
      var held = JSON.parse(localStorage.getItem(ASKS) || "[]");
      return Array.isArray(held) ? held : [];
    } catch (e) {
      return [];
    }
  }

  function writeAsks(held) {
    try {
      if (held.length) localStorage.setItem(ASKS, JSON.stringify(held));
      else localStorage.removeItem(ASKS);
    } catch (e) {}
  }

  // `ask` is { term, body }: the word as the page keeps it, and the request a tap makes.
  function askLater(ask) {
    if (!ask || !ask.body) return;
    var held = asks().filter(function (one) {
      return !(one.body.lemma === ask.body.lemma && one.body.target === ask.body.target);
    });
    held.push({ term: ask.term || ask.body.lemma, body: ask.body, at: Date.now() });
    writeAsks(held);
  }

  function askedLater(lemma, target) {
    return asks().some(function (one) {
      return one.body.lemma === lemma && one.body.target === target;
    });
  }

  var asking = null;
  function askNow() {
    if (asking) return asking;
    var held = asks();
    if (!held.length || away()) return Promise.resolve();
    asking = held
      .reduce(function (before, one) {
        return before.then(function () {
          return fetch(keyed("/gloss"), {
            method: "POST",
            headers: headers({ "Content-Type": "application/json" }),
            credentials: "same-origin",
            body: JSON.stringify(one.body),
          })
            .then(function (answer) {
              return answer.json();
            })
            .then(function (answer) {
              writeAsks(
                asks().filter(function (other) {
                  return !(other.body.lemma === one.body.lemma && other.body.target === one.body.target);
                })
              );
              // The reader that holds the word keeps the meaning as a tap would have.
              try {
                window.dispatchEvent(
                  new CustomEvent("targum:looked-up", {
                    detail: { term: one.term, body: one.body, answer: answer || {} },
                  })
                );
              } catch (e) {}
            });
        });
      }, Promise.resolve())
      .catch(function () {})
      .then(function () {
        asking = null;
      });
    return asking;
  }

  if (served) {
    window.addEventListener("offline", enterAway);
    window.addEventListener("online", leaveAway);
    var settle = function () {
      if (away()) enterAway();
      else askNow();
    };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", settle);
    else settle();
  }

  function onChange(listener) {
    listeners.push(listener);
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
    sweep();
  }

  if (able) {
    if (document.readyState === "complete") register();
    else window.addEventListener("load", register);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", inReader);
    else inReader();
  }

  window.TargumOffline = {
    able: able,
    keyOf: keyOf,
    textOf: textOf,
    plan: plan,
    save: save,
    saveSet: saveSet,
    remove: remove,
    removeAll: removeAll,
    keep: keepIt,
    keepPage: keepPage,
    trim: trim,
    choices: choices,
    choose: choose,
    size: size,
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
    // The same, asked by a reader's address, as a playlist's rows carry it.
    savedText: function (address) {
      if (!known) return null;
      var id = textOf(address);
      return (id && known.items[id]) || false;
    },
    playlist: onPlaylist,
    // With no connection (design.md §12, 2026-10-09).
    away: away,
    inBanner: inBanner,
    askLater: askLater,
    askedLater: askedLater,
    askNow: askNow,
    onChange: onChange,
    ready: readIndex,
  };
})();
