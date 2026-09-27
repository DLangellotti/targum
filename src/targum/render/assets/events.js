/* What a reader did in a text, handed to the account (targum-internal#127).
 *
 * A word looked up, a stretch of a recording played, a page turned, a section finished,
 * where a sitting stopped, a control pressed. "It is worthless retroactively", which is
 * the whole argument for keeping it — and it is a record of a person, so most of this file
 * is about when it does nothing:
 *
 *  - off a disk it does nothing: there is nobody to hand anything to;
 *  - in the framed preview on Learn it does nothing: nobody is reading there yet;
 *  - signed out it does nothing;
 *  - where the box keeps no such record it does nothing (`TARGUM_EVENTS`, off unless the
 *    deployment says so — see `serve.keeps_events`);
 *  - and where the reader has stopped it, on their account page, it does nothing.
 *
 * All five are one question asked of `/account/me`, which `sync.js` has already asked:
 * `who.events.kept && who.events.on`. Until that is answered, what happens is held here
 * and no further; answered no, it is dropped.
 *
 * Nothing is kept in this browser and nothing comes back: the figures on Your Progress are
 * the account's reading of its own log, so they are the sum across every device.
 *
 * A control pressed says its name, how wide the window is and the day — never which text,
 * never where in it, never the time. The page does not send those and the server would
 * drop them if it did.
 */
(function () {
  "use strict";

  var served = /^https?:$/.test(location.protocol);
  var preview = false;
  try {
    preview = new URLSearchParams(location.search).get("preview") === "1";
  } catch (e) {}

  var held = [];
  var about = { document: "", language: "", address: null };
  //: null until the account has answered; then whether anything is to be sent at all.
  var keeping = null;
  var timer = null;
  //: Enough for a sitting, and no more: a page that cannot send must not grow for ever.
  var MOST = 400;
  var SOON = 20000;

  function today() {
    // The reader's own calendar day, from its parts: an ISO string is the day in London.
    var now = new Date();
    var two = function (n) {
      return (n < 10 ? "0" : "") + n;
    };
    return now.getFullYear() + "-" + two(now.getMonth() + 1) + "-" + two(now.getDate());
  }

  function width() {
    if (!window.matchMedia) return "desk";
    if (window.matchMedia("(max-width: 60rem)").matches) return "phone";
    return window.matchMedia("(max-width: 75rem)").matches ? "narrow" : "desk";
  }

  function decide() {
    if (keeping !== null) return keeping;
    var who = window.TargumSync && window.TargumSync.who;
    if (!who || !who.events) return null;
    keeping = !!(who.events.kept && who.events.on);
    if (!keeping) held = [];
    return keeping;
  }

  function send(last) {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (!held.length || decide() !== true || !about.address) return;
    var batch = held;
    held = [];
    try {
      fetch(about.address("/events"), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        // So the last of a sitting still leaves when the page does.
        keepalive: !!last,
        body: JSON.stringify({ events: batch }),
      })
        .then(function (answer) {
          return answer.json();
        })
        .then(function (said) {
          // The account says when to stop: stopped from another tab, or a box that has
          // ceased to keep anything.
          if (said && said.keeping === false) {
            keeping = false;
            held = [];
          }
        })
        .catch(function () {
          /* lost, and that is the right failure: a record is not worth a retry queue */
        });
    } catch (e) {}
  }

  function note(event) {
    if (!served || preview || keeping === false || !event || !event.kind) return;
    var row = { kind: event.kind, day: today() };
    if (event.kind === "control") {
      row.control = String(event.control || "");
      row.width = width();
      if (!row.control) return;
    } else {
      row.at = Date.now();
      row.document = about.document;
      row.language = about.language;
      row.medium = event.medium || "read";
      row.segment = event.segment || "";
      row.amount = event.amount || 0;
    }
    held.push(row);
    if (held.length > MOST) held.shift();
    if (decide() === false) return;
    if (held.length >= 40) send(false);
    else if (!timer) timer = setTimeout(send, SOON);
  }

  if (served && !preview) {
    window.addEventListener("pagehide", function () {
      send(true);
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") send(true);
    });
  }

  window.TargumEvents = {
    /** Which text this is, and how this page addresses the server. */
    about: function (said) {
      about.document = String((said && said.document) || "");
      about.language = String((said && said.language) || "");
      about.address = (said && said.address) || null;
    },
    note: note,
    /** Send what is held. `last` where the page is going, so the request outlives it. */
    flush: function (last) {
      send(!!last);
    },
    //: For a test: what is waiting to go.
    held: function () {
      return held.slice();
    },
  };
})();
