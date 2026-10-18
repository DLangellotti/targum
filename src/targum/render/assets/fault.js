/* How targum says no, drawn once (design.md §12, "A refusal is drawn on one of five
 * surfaces", 2026-10-09). A page hands this the sentence and the way on; the drawing is
 * `.fault-*` in `reader.css`, which every page carries.
 *
 *   TargumFault.field(input, sentence)   under a field: clay outline, focus kept, a line
 *   TargumFault.clear(input)             and gone again
 *   TargumFault.line(sentence, act?, onAct?)              a line in a card, as an element
 *   TargumFault.panel(sentence, {act, href, onAct, fact, topUp})   a panel, as an element
 *   TargumFault.refusal(sentence, fact, act)   the panel for a refusal the server sent
 *   TargumFault.upgrade(sentence, fact?)  the panel where a free reader reaches for the plan
 *   TargumFault.unreachable(retry?)      the connection banner, under the top bar
 *   TargumFault.reached()                and gone again
 *   TargumFault.tellUs()                 the Tell us box, which `[data-tell-us]` opens too
 *
 * The whole page is a template (`missing.html.j2`, the sign-in page's expired and closing
 * doors), because there is nothing on it for a script to do.
 *
 * Its words are said through whichever `t` the page has: `strings.js` on the desk,
 * `reader.js`'s own in a reader. Both set `window.TargumStrings`, and both are asked at
 * the moment of saying, so this can load before either.
 */
(function () {
  "use strict";

  function t(key, english) {
    var said = window.TargumStrings;
    return said && typeof said.t === "function" ? said.t(key, english) : english;
  }

  var SVG = "http://www.w3.org/2000/svg";

  // §7: a stroke at text weight, no fill. The circle with its mark is the refusal's own;
  // the cloud crossed out is the connection's.
  function glyph(className, paths) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", className);
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    paths.forEach(function (d) {
      var path = document.createElementNS(SVG, "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  function alertGlyph() {
    return glyph("fault-icon", ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M12 7.5V13", "M12 16.5v.1"]);
  }

  function cloudGlyph() {
    return glyph("fault-cloud", ["M7 18h10a4 4 0 0 0 .8-7.9A6 6 0 0 0 6.3 9 4.5 4.5 0 0 0 7 18z", "M3 3l18 18"]);
  }

  function said(sentence) {
    var span = document.createElement("span");
    span.className = "fault-said";
    span.textContent = sentence;
    return span;
  }

  function tryAgain() {
    return t("fault.try-again", "Try again");
  }

  /* 2 · A line in a card. `act` is the button's word ("Try again" when it is left out
     and `onAct` is given); with neither, the line is the sentence alone. `inline` makes
     it a span, for a line that stands inside a line of text. */
  function line(sentence, act, onAct, inline) {
    if (typeof act === "function") {
      inline = onAct;
      onAct = act;
      act = "";
    }
    var p = document.createElement(inline ? "span" : "p");
    p.className = "fault-line";
    p.setAttribute("role", "status");
    p.appendChild(alertGlyph());
    p.appendChild(said(sentence));
    if (onAct) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "fault-act";
      button.textContent = act || tryAgain();
      button.addEventListener("click", function (event) {
        event.stopPropagation();
        onAct(event);
      });
      p.appendChild(button);
    }
    return p;
  }

  /* 3 · A panel in place. `act` with `href` is a link, with `onAct` a button; `topUp`
     draws Top up greyed with "Payments open soon" beside it, until there is somewhere to
     pay (§12). `fact` is the quiet line of what still works. */
  function panel(sentence, options) {
    options = options || {};
    var box = document.createElement("div");
    box.className = "fault-panel";
    box.setAttribute("role", "status");
    var p = document.createElement("p");
    p.className = "fault-panel-said";
    p.textContent = sentence;
    box.appendChild(p);
    var row = document.createElement("div");
    row.className = "fault-panel-row";
    var fact = options.fact || "";
    if (options.topUp) {
      var up = document.createElement("button");
      up.type = "button";
      up.className = "fault-go";
      up.disabled = true;
      up.textContent = t("fault.top-up", "Top up");
      row.appendChild(up);
      var soon = document.createElement("span");
      soon.className = "fault-fact";
      soon.textContent = t("fault.payments-soon", "Payments open soon");
      row.appendChild(soon);
    } else if (options.act && options.href) {
      var link = document.createElement("a");
      link.className = "fault-go";
      link.href = options.href;
      link.textContent = options.act;
      row.appendChild(link);
    } else if (options.onAct) {
      var go = document.createElement("button");
      go.type = "button";
      go.className = "fault-go";
      go.textContent = options.act || tryAgain();
      go.addEventListener("click", function (event) {
        event.stopPropagation();
        options.onAct(event);
      });
      row.appendChild(go);
    }
    if (fact) {
      var quiet = document.createElement("span");
      quiet.className = "fault-fact";
      quiet.textContent = fact;
      row.appendChild(quiet);
    }
    // And a way to say what happened (targum-internal#456): on every panel that is a
    // fault, which a reader out of credits is not, and only where there is a targum to
    // say it to.
    if (!options.topUp && options.tellUs !== false && served) row.appendChild(tellUsButton());
    if (row.childNodes.length) box.appendChild(row);
    return box;
  }

  /* 6 · Tell us (targum-internal#456; privacy notice clause 3.14). One box, Send, and a
     line of thanks: in the account menu, on every panel above and on the whole page for
     an address with nothing at it. Anything carrying `data-tell-us` opens it. What is
     sent is what was written, the page's path, the window's size, the page's language
     and the build; the server adds the account. */
  var served = /^https?:$/.test(location.protocol);
  var asking = null;

  function tellUsButton() {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "fault-act";
    button.setAttribute("data-tell-us", "");
    button.textContent = t("fault.tell-us", "Tell us");
    return button;
  }

  function tellUsBox() {
    var box = document.createElement("dialog");
    box.className = "tell-us";
    box.setAttribute("aria-labelledby", "tell-us-title");
    var form = document.createElement("form");
    form.className = "tell-us-form";
    var title = document.createElement("h2");
    title.id = "tell-us-title";
    title.className = "tell-us-title";
    title.textContent = t("fault.tell-us", "Tell us");
    form.appendChild(title);
    var label = document.createElement("label");
    label.className = "tell-us-label";
    label.setAttribute("for", "tell-us-said");
    label.textContent = t("fault.tell-us.label", "What happened, or what would help?");
    form.appendChild(label);
    var said = document.createElement("textarea");
    said.id = "tell-us-said";
    said.className = "tell-us-said";
    said.rows = 5;
    said.maxLength = 4000;
    // A message in Hebrew stands right to left from its first letter.
    said.setAttribute("dir", "auto");
    form.appendChild(said);
    var fact = document.createElement("p");
    fact.className = "fault-fact tell-us-fact";
    fact.textContent = t("fault.tell-us.fact", "We'll see which page you were on.");
    form.appendChild(fact);
    var row = document.createElement("div");
    row.className = "fault-panel-row";
    var send = document.createElement("button");
    send.type = "submit";
    send.className = "fault-go";
    send.textContent = t("fault.tell-us.send", "Send");
    row.appendChild(send);
    var cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "fault-act";
    cancel.textContent = t("fault.tell-us.cancel", "Cancel");
    cancel.addEventListener("click", function () {
      closeTellUs();
    });
    row.appendChild(cancel);
    form.appendChild(row);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      sendTellUs(form, said, send);
    });
    box.appendChild(form);
    box.addEventListener("click", function (event) {
      // A press on the dimmed page around the box, which is the dialog itself.
      if (event.target === box) closeTellUs();
    });
    box.addEventListener("close", function () {
      if (asking === box && box.parentNode) box.parentNode.removeChild(box);
      if (asking === box) asking = null;
    });
    return box;
  }

  function sendTellUs(form, said, send) {
    var text = said.value.trim();
    if (!text) return field(said, t("fault.tell-us.empty", "Write something first."));
    clear(said);
    send.disabled = true;
    var build = (window.TargumReport && window.TargumReport.build) || "";
    fetch(keyed("/tell-us"), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        said: text,
        page: location.pathname,
        build: build,
        viewport: window.innerWidth + "x" + window.innerHeight,
        language: document.documentElement.getAttribute("lang") || "",
      }),
    })
      .then(function (answer) {
        return answer.json().then(
          function (body) {
            return { ok: answer.ok, body: body || {} };
          },
          function () {
            return { ok: false, body: {} };
          }
        );
      })
      .then(function (got) {
        if (got.ok) return thankTellUs(form);
        // The server's own sentence where it sent one: sign in first, or too many.
        refuseTellUs(said, send, typeof got.body.error === "string" ? got.body.error : "");
      })
      .catch(function () {
        refuseTellUs(said, send, "");
      });
  }

  function refuseTellUs(said, send, sentence) {
    send.disabled = false;
    field(said, sentence || t("fault.tell-us.failed", "We couldn't send that. Try again in a minute."));
  }

  function thankTellUs(form) {
    form.innerHTML = "";
    var thanks = document.createElement("p");
    thanks.className = "tell-us-thanks";
    thanks.setAttribute("role", "status");
    thanks.textContent = t("fault.tell-us.thanks", "Thanks for telling us. We read every message.");
    form.appendChild(thanks);
    var row = document.createElement("div");
    row.className = "fault-panel-row";
    var done = document.createElement("button");
    done.type = "button";
    done.className = "fault-go";
    done.textContent = t("fault.tell-us.close", "Close");
    done.addEventListener("click", function () {
      closeTellUs();
    });
    row.appendChild(done);
    form.appendChild(row);
    done.focus();
  }

  function tellUs() {
    if (!served) return null;
    if (asking) return asking;
    asking = tellUsBox();
    document.body.appendChild(asking);
    if (typeof asking.showModal === "function") asking.showModal();
    else asking.setAttribute("open", "");
    var said = asking.querySelector("textarea");
    if (said) said.focus();
    return asking;
  }

  function closeTellUs() {
    var box = asking;
    if (!box) return;
    if (typeof box.close === "function" && box.open) box.close();
    else {
      asking = null;
      if (box.parentNode) box.parentNode.removeChild(box);
    }
  }

  document.addEventListener("click", function (event) {
    var opener = event.target && event.target.closest && event.target.closest("[data-tell-us]");
    if (!opener) return;
    event.preventDefault();
    event.stopPropagation();
    tellUs();
  });

  /* A refusal the server sent with what its panel draws beside it (`serve.Refusal`):
     `fact`, the quiet line of what still works, and `act`, the one way on — Top up
     (greyed), the library, or the reader's own targums. Any of the three may be absent;
     the sentence alone is still a panel. */
  function keyed(path) {
    var key = window.TARGUM_KEY || "";
    if (!key) {
      try {
        key = new URLSearchParams(location.search).get("k") || "";
      } catch (e) {
        key = "";
      }
    }
    return key ? path + "?k=" + encodeURIComponent(key) : path;
  }

  /* A panel where a free reader reaches for the plan (design.md §12, "A free reader meets
     the plan where they reach for it", 2026-10-09; board PlanUpgradeMoment): the sentence,
     Start a plan greyed with "Payments open soon" beside it, See plans at the far end,
     and under a hairline the quiet line of what still works. Plans are behind a switch;
     a page only ever draws this because the server said `plan`. */
  function clockGlyph() {
    return glyph("fault-clock", ["M8 2.25a5.75 5.75 0 1 0 0 11.5a5.75 5.75 0 1 0 0-11.5z", "M8 5v3.2l2 1.3"]);
  }
  function upgrade(sentence, fact) {
    var box = document.createElement("div");
    box.className = "fault-panel fault-upgrade";
    box.setAttribute("role", "status");
    var p = document.createElement("p");
    p.className = "fault-panel-said";
    p.textContent = sentence;
    box.appendChild(p);
    var row = document.createElement("div");
    row.className = "fault-panel-row";
    var start = document.createElement("button");
    start.type = "button";
    start.className = "fault-go";
    start.disabled = true;
    start.textContent = t("fault.start-a-plan", "Start a plan");
    row.appendChild(start);
    var soon = document.createElement("span");
    soon.className = "fault-fact fault-soon";
    var clock = clockGlyph();
    clock.setAttribute("viewBox", "0 0 16 16");
    soon.appendChild(clock);
    soon.appendChild(document.createTextNode(t("fault.payments-soon", "Payments open soon")));
    row.appendChild(soon);
    var see = document.createElement("a");
    see.className = "fault-see";
    see.href = keyed("/plans");
    see.textContent = t("fault.see-plans", "See plans");
    row.appendChild(see);
    box.appendChild(row);
    if (fact) {
      var foot = document.createElement("p");
      foot.className = "fault-panel-foot";
      foot.textContent = fact;
      box.appendChild(foot);
    }
    return box;
  }

  function refusal(sentence, fact, act) {
    if (act === "plan") return upgrade(sentence, fact);
    var options = { fact: fact || "" };
    if (act === "top-up") options.topUp = true;
    else if (act === "library") {
      options.act = t("fault.open-library", "Open the library");
      options.href = keyed("/library");
    } else if (act === "yours") {
      options.act = t("fault.open-yours", "Open your targums");
      options.href = keyed("/");
    }
    return panel(sentence, options);
  }

  /* 1 · Under a field. The line is the field's description while it stands, and the
     next thing typed into it takes the outline and the line away. `frame` is what is
     drawn as the field where that is not the input itself: the Upload page's well, which
     holds the box and the files dropped into it. */
  var counter = 0;
  function field(input, sentence, frame) {
    if (!input) return null;
    clear(input);
    var p = document.createElement("p");
    p.className = "fault-under";
    p.id = "fault-under-" + ++counter;
    p.setAttribute("role", "alert");
    p.appendChild(alertGlyph());
    p.appendChild(said(sentence));
    frame = frame || input;
    frame.parentNode.insertBefore(p, frame.nextSibling);
    frame.classList.add("fault-field");
    input._faultFrame = frame;
    input.setAttribute("aria-invalid", "true");
    var described = input.getAttribute("aria-describedby");
    input.setAttribute("data-fault-was", described === null ? "" : described);
    input.setAttribute("aria-describedby", ((described ? described + " " : "") + p.id).trim());
    input._fault = p;
    function mend() {
      input.removeEventListener("input", mend);
      clear(input);
    }
    input.addEventListener("input", mend);
    if (document.activeElement !== input && typeof input.focus === "function") {
      try {
        input.focus({ preventScroll: true });
      } catch (e) {
        input.focus();
      }
    }
    return p;
  }

  function clear(input) {
    if (!input || !input._fault) return;
    if (input._fault.parentNode) input._fault.parentNode.removeChild(input._fault);
    input._fault = null;
    (input._faultFrame || input).classList.remove("fault-field");
    input._faultFrame = null;
    input.removeAttribute("aria-invalid");
    var was = input.getAttribute("data-fault-was");
    if (was) input.setAttribute("aria-describedby", was);
    else input.removeAttribute("aria-describedby");
    input.removeAttribute("data-fault-was");
  }

  /* 4 · The connection banner. One per page, under the top bar: the desk's header
     carries an empty one (`_nav.html.j2`); anywhere else it is made under the reader's
     bar or at the top of the page. It has no ×; it goes when targum answers, which is
     the next press that reaches it (`reached`), the browser saying it is online again,
     or Try again succeeding. */
  var retries = [];

  function banner() {
    var band = document.getElementById("fault-banner");
    if (band) return band;
    band = document.createElement("div");
    band.id = "fault-banner";
    band.className = "fault-banner";
    band.setAttribute("role", "status");
    // Its words are the interface's, not the text's: in a Hebrew reader the band stood
    // right to left, with its full stop at the start of the sentence.
    band.setAttribute("dir", "auto");
    band.hidden = true;
    var bar = document.querySelector("body > header.bar, .site-head");
    if (bar && bar.classList.contains("bar")) {
      band.classList.add("is-under-bar");
      bar.parentNode.insertBefore(band, bar.nextSibling);
    } else if (bar) {
      bar.appendChild(band);
    } else {
      document.body.insertBefore(band, document.body.firstChild);
    }
    return band;
  }

  function unreachable(retry) {
    var band = banner();
    if (typeof retry === "function" && retries.indexOf(retry) < 0) retries.push(retry);
    band.innerHTML = "";
    band.appendChild(cloudGlyph());
    band.appendChild(said(t("fault.unreachable", "We can't reach targum. This page stays open.")));
    var again = document.createElement("button");
    again.type = "button";
    again.className = "fault-act";
    again.textContent = tryAgain();
    again.addEventListener("click", function () {
      var waiting = retries.splice(0);
      reached();
      if (!waiting.length) return location.reload();
      waiting.forEach(function (run) {
        try {
          run();
        } catch (e) {}
      });
    });
    band.appendChild(again);
    // With no connection, the way to what is saved and what is waiting to go (`offline.js`,
    // design.md §12, 2026-10-09): added each time the band is drawn, by whichever page.
    if (window.TargumOffline && typeof window.TargumOffline.inBanner === "function") {
      window.TargumOffline.inBanner(band);
    }
    if (band.classList.contains("is-under-bar")) {
      var bar = band.previousElementSibling;
      band.style.insetBlockStart = (bar ? bar.offsetHeight : 0) + "px";
    }
    band.hidden = false;
  }

  function reached() {
    var band = document.getElementById("fault-banner");
    if (band) band.hidden = true;
  }

  window.addEventListener("online", function () {
    var waiting = retries.splice(0);
    reached();
    waiting.forEach(function (run) {
      try {
        run();
      } catch (e) {}
    });
  });

  window.TargumFault = {
    line: line,
    panel: panel,
    upgrade: upgrade,
    refusal: refusal,
    field: field,
    clear: clear,
    unreachable: unreachable,
    reached: reached,
    tryAgain: tryAgain,
    tellUs: tellUs,
  };
})();
