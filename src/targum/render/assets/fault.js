/* How targum says no, drawn once (design.md §12, "A refusal is drawn on one of five
 * surfaces", 2026-10-09). A page hands this the sentence and the way on; the drawing is
 * `.fault-*` in `reader.css`, which every page carries.
 *
 *   TargumFault.field(input, sentence)   under a field: clay outline, focus kept, a line
 *   TargumFault.clear(input)             and gone again
 *   TargumFault.line(sentence, act?, onAct?)              a line in a card, as an element
 *   TargumFault.panel(sentence, {act, href, onAct, fact, topUp})   a panel, as an element
 *   TargumFault.refusal(sentence, fact, act)   the panel for a refusal the server sent
 *   TargumFault.unreachable(retry?)      the connection banner, under the top bar
 *   TargumFault.reached()                and gone again
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
    if (row.childNodes.length) box.appendChild(row);
    return box;
  }

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

  function refusal(sentence, fact, act) {
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
    refusal: refusal,
    field: field,
    clear: clear,
    unreachable: unreachable,
    reached: reached,
    tryAgain: tryAgain,
  };
})();
