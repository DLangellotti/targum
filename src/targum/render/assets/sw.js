/* targum's worker: what a reader saved for offline, answered when the network is not
 * there (design.md §12, "A worker keeps what the reader saved, and fetches nothing else",
 * 2026-10-09).
 *
 * It is served from the site's root as `/sw.js`, so its scope is the whole site, and it
 * is registered by `offline.js` from a page that was served — never from a reader opened
 * off a disk, which has no origin to register on and fetches nothing.
 *
 * **It never fetches anything by itself.** Nothing is cached when it installs, nothing is
 * fetched ahead, and nothing is refreshed behind the reader's back. The page saves — the
 * reader's own press, or the last texts they opened — and puts each file into the one
 * cache below; this file only answers out of that cache. The one fetch it makes is the
 * one the browser was already making: a page being opened goes to the network first, and
 * only when that fails is the saved copy the answer.
 *
 * Three rules, and nothing else is intercepted:
 *
 * - **Opening a page** (a navigation) goes to the network first. When the network is not
 *   there, the saved copy answers, with the headers it was served with — its own content
 *   policy, hashes and all. When the page is a saved one and the network did answer, the
 *   saved copy is replaced by the bytes that just arrived, so a saved text is never older
 *   than the last time it was opened.
 * - **A recording or a film beside a reader** answers from the cache when it was saved,
 *   in slices: a player asks for ranges, and Safari opens every film with `bytes=0-1` and
 *   will not play unless that comes back as a real 206. What was not saved is not touched.
 * - **Everything else** is the browser's own business: never answered from here.
 *
 * The cache key drops what does not name the file. A reader is a file on disk, and the
 * query on its address (`?k=` on a machine somebody runs themselves, `?list=` inside a
 * playlist) is read by the page and never by the server — so for a reader's own files
 * the whole query goes. Anywhere else only `k` goes: it is the start-up key, a bearer
 * token, and it has no business in a cache's index.
 */

"use strict";

/* One cache, for everything saved. A version in its name would make every update of this
   file a quiet delete of what the reader saved for a plane; the index inside it is what
   changes shape, and it says its own version. */
var STORE = "targum-offline";
var INDEX = "/offline/index";

/* The three addresses a reader's files are served under: a reader's own and the shared
   shelf's (`/reader/<name>/reader/`), a Torah portion's, and a day of a daily cycle's. */
var READER = /^\/(?:reader\/[^/]+\/reader|parasha\/read\/[^/]+\/reader|[^/]+\/read\/\d{4}-\d{2}-\d{2}\/reader)\//;
var MEDIA = /\.(?:mp4|m4v|webm|mp3)$/i;

/* What is saved, held in memory once it has been read, so that a film that was not saved
   is never even looked at: the answer to "is it ours" has to be known while the request
   is still being dispatched, and a cache lookup is a promise. Until the index has been
   read, the slower path asks the cache. */
var saved = null;

function keyOf(address) {
  var url = new URL(address, self.location.origin);
  url.hash = "";
  if (READER.test(url.pathname)) {
    url.search = "";
  } else {
    url.searchParams.delete("k");
  }
  return url.href;
}

function readIndex() {
  return caches
    .open(STORE)
    .then(function (cache) {
      return cache.match(INDEX);
    })
    .then(function (answer) {
      return answer ? answer.json() : {};
    })
    .then(function (index) {
      var keys = {};
      var items = (index && index.items) || {};
      Object.keys(items).forEach(function (id) {
        (items[id].files || []).forEach(function (file) {
          keys[keyOf(file)] = true;
        });
      });
      saved = keys;
      return keys;
    })
    .catch(function () {
      saved = {};
      return saved;
    });
}

self.addEventListener("install", function () {
  // Nothing to fetch: the worker arrives empty and stays so until somebody saves.
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    Promise.all([
      self.clients.claim(),
      readIndex(),
      // The page's own request goes out while the worker wakes, so a navigation is no
      // slower for having a worker in front of it.
      self.registration.navigationPreload
        ? self.registration.navigationPreload.enable().catch(function () {})
        : null,
    ])
  );
});

// The page says when it saved or removed something, and the index is read again.
self.addEventListener("message", function (event) {
  if (event.data && event.data.type === "saved") {
    var done = readIndex();
    if (event.waitUntil) event.waitUntil(done);
  }
});

/* A cached file as the player asked for it: the whole thing, or one slice of it as a 206.
   The cached answer is always the whole file, because the page saved it that way. */
function sliced(request, whole) {
  var range = request.headers.get("range");
  if (!range) return whole;
  var found = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
  if (!found || (!found[1] && !found[2])) return whole;
  var kind = whole.headers.get("content-type") || "application/octet-stream";
  return whole.blob().then(function (body) {
    var size = body.size;
    var start;
    var end = size - 1;
    if (found[1]) {
      start = Number(found[1]);
      if (found[2]) end = Math.min(Number(found[2]), size - 1);
    } else {
      // The last N bytes: how a player reads the index a plain mp4 keeps at its tail.
      start = Math.max(0, size - Number(found[2]));
    }
    if (start >= size || end < start) {
      return new Response(null, {
        status: 416,
        headers: { "Content-Range": "bytes */" + size },
      });
    }
    return new Response(body.slice(start, end + 1), {
      status: 206,
      statusText: "Partial Content",
      headers: {
        "Content-Type": kind,
        "Content-Length": String(end - start + 1),
        "Content-Range": "bytes " + start + "-" + end + "/" + size,
        "Accept-Ranges": "bytes",
      },
    });
  });
}

function fromStore(request) {
  return caches.open(STORE).then(function (cache) {
    // `ignoreVary`: the page saved it with its own request's headers, and a film asked for
    // by a player sends others. The address is the whole of what names a saved file.
    return cache.match(keyOf(request.url), { ignoreVary: true });
  });
}

function media(request) {
  return fromStore(request).then(function (whole) {
    // Not saved after all — the index was not read yet when this was asked. The network,
    // exactly as the browser would have asked it.
    if (!whole) return fetch(request);
    return sliced(request, whole);
  });
}

/* A page the reader is opening. The network first, always; the saved copy when there is
   no network; and nothing invented when neither is there — the browser says it is offline
   in its own words. */
function opening(event) {
  var request = event.request;
  var key = keyOf(request.url);
  var asked = Promise.resolve(event.preloadResponse).then(function (preloaded) {
    return preloaded || fetch(request);
  });
  return asked.then(
    function (answer) {
      // A saved page that opened online is saved again as it is now: the reader is
      // reading these bytes, and the copy for the plane should be the same one.
      if (answer && answer.ok && answer.type === "basic" && saved && saved[key]) {
        var copy = answer.clone();
        event.waitUntil(
          caches.open(STORE).then(function (cache) {
            return cache.put(key, kept(copy));
          })
        );
      }
      return answer;
    },
    function (offline) {
      return fromStore(request).then(function (copy) {
        if (copy) return copy;
        throw offline;
      });
    }
  );
}

/* A response as it is kept: its own body and headers, less the ones that described the
   journey rather than the file. The body is already decoded when it reaches a script, so
   a `Content-Encoding` left on it would describe bytes that are not there. */
function kept(answer) {
  var headers = new Headers();
  answer.headers.forEach(function (value, name) {
    if (!/^(content-encoding|content-length|set-cookie|transfer-encoding)$/i.test(name)) {
      headers.set(name, value);
    }
  });
  return new Response(answer.body, {
    status: answer.status,
    statusText: answer.statusText,
    headers: headers,
  });
}

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === "navigate") {
    event.respondWith(opening(event));
    return;
  }
  // A save in progress asks the network for the real file, never for the copy it is
  // about to replace.
  if (request.headers.get("x-targum-save")) return;
  if (!READER.test(url.pathname) || !MEDIA.test(url.pathname)) return;
  if (saved && !saved[keyOf(request.url)]) return;
  event.respondWith(media(request));
});
