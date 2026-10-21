/* What a page says about itself when it breaks (targum-internal#457; privacy notice
 * clause 3.14). A reader who meets a broken page usually leaves without telling anyone,
 * and until this the server's 5xx were all anybody saw.
 *
 * Three things are reported, to `/errors` on the page's own origin and nowhere else: an
 * error nothing caught, a promise refused with nobody listening, and a request to targum
 * answered with a 5xx. Each says its message, where in our script it arose, the page's
 * path without its query, and the build (`data-build` on this script's own tag). Never
 * the text on the page and never a cookie; the server adds the account, where there is
 * one, and keeps the report thirty days.
 *
 * Off a disk it does nothing: there is nobody to tell. A message is sent once per page,
 * and a page sends at most a few; the server counts the rest by account or by a hash of
 * the address, for an hour. A connection that is down is not a fault: "Failed to fetch"
 * is the banner's to say (`fault.js`), not ours to count.
 */
(function () {
  "use strict";

  if (!/^https?:$/.test(location.protocol) || typeof window.fetch !== "function") return;

  var me = document.currentScript;
  var build = (me && me.getAttribute("data-build")) || "";
  var MOST_A_PAGE = 5;
  var sent = 0;
  var said = {};
  var post = window.fetch;

  // An address as we keep it: our own origin taken off, and never a query or a fragment,
  // where a start-up key or a sign-in token could ride.
  function plain(text) {
    return String(text || "")
      .split(location.origin)
      .join("")
      .replace(/(\/[^\s?#)'"]*)[?#][^\s)'":]*/g, "$1")
      .replace(/\s+/g, " ")
      .trim();
  }

  // The first frames of a stack that are ours, which say more than a line number does in
  // a page whose scripts are all inline.
  function frames(stack) {
    var ours = String(stack || "")
      .split("\n")
      .filter(function (frame) {
        return frame.indexOf(location.origin) >= 0;
      })
      .slice(0, 2)
      .map(plain);
    return ours.join(" < ").slice(0, 300);
  }

  function offline(message) {
    if (navigator.onLine === false) return true;
    return /failed to fetch|networkerror|load failed|network request failed/i.test(message);
  }

  function report(message, place) {
    message = plain(message).slice(0, 300);
    if (!message || sent >= MOST_A_PAGE || said[message] || offline(message)) return;
    said[message] = true;
    sent += 1;
    try {
      post
        .call(window, "/errors", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          keepalive: true,
          body: JSON.stringify({
            message: message,
            place: place || "",
            page: location.pathname,
            build: build,
          }),
        })
        .catch(function () {
          /* lost, and that is the right failure: a report is not worth a retry */
        });
    } catch (e) {}
  }

  window.addEventListener("error", function (event) {
    // A picture or a stylesheet that failed to load arrives here only in the capturing
    // phase, so what reaches this listener is a script's error.
    if (!event || typeof event.message !== "string") return;
    var file = event.filename || "";
    // Another origin's script, a browser extension's: "Script error." and nothing else.
    if (file && file.indexOf(location.origin) !== 0) return;
    var place = (event.error && frames(event.error.stack)) || "";
    if (!place && file) place = plain(file) + ":" + (event.lineno || 0) + ":" + (event.colno || 0);
    report(event.message, place);
  });

  window.addEventListener("unhandledrejection", function (event) {
    var reason = event && event.reason;
    if (reason === undefined || reason === null) return;
    var message = reason && reason.message ? reason.name + ": " + reason.message : String(reason);
    report(message, frames(reason && reason.stack));
  });

  // A part of the address that names one thing rather than a kind of thing: a number, a
  // job's id. Counted together, so one broken door is one row rather than one per text.
  function door(path) {
    return path
      .split("/")
      .map(function (part) {
        return /\d/.test(part) || part.length > 24 ? ":id" : part;
      })
      .join("/");
  }

  window.fetch = function (input) {
    var answer = post.apply(window, arguments);
    try {
      var address = new URL(typeof input === "string" ? input : (input && input.url) || "", location.href);
      if (address.origin === location.origin && address.pathname !== "/errors") {
        answer.then(
          function (response) {
            if (response && response.status >= 500) {
              report("HTTP " + response.status + " from " + door(address.pathname), "");
            }
          },
          function () {}
        );
      }
    } catch (e) {}
    return answer;
  };

  window.TargumReport = { build: build, report: report };
})();
