/* The parasha page's own script.

   Everything works without it: the reader is framed, the chanting-marks switch is two
   links to the same page, and the list of portions is open in the markup. This makes the
   switch change the reader in place instead of reloading the page under it, which is the
   difference between choosing a form and losing your place.

   Same origin, so it calls into the frame directly — the pattern `weekly.js` already
   uses to read the frame's address. `reader.js` puts `targumReader.setTaamim` on its own
   window for exactly this. */
(function () {
  "use strict";

  /* Words said through the page's `TargumStrings`, looked up when a thing is said: this
     file runs before the page has handed its strings over. Where there are none, the
     English here (targum-internal#184). */
  function t(key, english, fill) {
    var said = window.TargumStrings;
    if (said) return said.t(key, english, fill);
    return english.replace(/\{(\w+)\}/g, function (all, name) {
      return fill && Object.prototype.hasOwnProperty.call(fill, name) ? String(fill[name]) : all;
    });
  }
  function tn(key, count, one, other, fill) {
    var said = window.TargumStrings;
    if (said) return said.tn(key, count, one, other, fill);
    var values = { n: count };
    for (var name in fill || {}) values[name] = fill[name];
    return t(key, count === 1 ? one : other, values);
  }

  /* Two frames on the page now — the Torah reading and the haftarah — and everything
     below treats them alike: each has its own full-screen handle, and the chanting-marks
     switch reaches both. The Torah reading's frame comes first in the markup and is the
     one the page asks about the current setting. */
  var embeds = Array.prototype.slice.call(document.querySelectorAll(".embed"));
  var frames = [];
  embeds.forEach(function (embed) {
    var framed = embed.querySelector("iframe");
    if (framed) frames.push(framed);
  });
  var framed = frames[0] || null;

  /* Full screen, the way the weekly's frame does it: the slot keeps the height it had so
     the page below does not jump when the frame is pinned over it. */
  embeds.forEach(function (embed) {
    var handle = embed.querySelector(".handle");
    if (!handle || !embed.querySelector("iframe")) return;
    var pinned = false;
    function unpin() {
      pinned = false;
      embed.classList.remove("pinned");
      handle.setAttribute("aria-expanded", "false");
      handle.textContent = t("parasha.full-screen", "Full screen");
    }
    handle.addEventListener("click", function () {
      pinned = !pinned;
      embed.classList.toggle("pinned", pinned);
      handle.setAttribute("aria-expanded", pinned ? "true" : "false");
      handle.textContent = pinned ? t("parasha.close", "Exit full screen") : t("parasha.full-screen", "Full screen");
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && pinned) unpin();
    });
  });

  /* The chanting marks. The chips are links; this turns them into a switch.

     The reader inside the frame owns the setting — it is the thing that has both forms
     of every verse — so the page asks it rather than keeping a copy. Where the frame has
     not loaded yet, or is a browser that will not let us in, the links stay links and the
     page reloads, which is what they did before this ran. */
  var chips = document.querySelectorAll(".ladder.taamim a[data-taamim]");
  function readerIn(frame) {
    try {
      return frame && frame.contentWindow && frame.contentWindow.targumReader;
    } catch (error) {
      return null;
    }
  }
  function reader() {
    return readerIn(framed);
  }
  /* The setting, handed to every frame that is up: the haftarah carries the marks the
     same way the reading does, and one switch should change both. */
  function setTaamimEverywhere(on) {
    frames.forEach(function (frame) {
      var api = readerIn(frame);
      if (api && api.setTaamim) api.setTaamim(on);
    });
  }

  function mark(on) {
    Array.prototype.forEach.call(chips, function (chip) {
      var mine = chip.getAttribute("data-taamim") === (on ? "on" : "off");
      chip.classList.toggle("here", mine);
      if (mine) chip.setAttribute("aria-current", "page");
      else chip.removeAttribute("aria-current");
    });
    if (window.history && history.replaceState) {
      /* Only the marks change: a language or a schedule in the address stays in it. */
      var query = new URLSearchParams(location.search);
      if (on) query.delete("taamim");
      else query.set("taamim", "off");
      var rest = query.toString();
      history.replaceState(null, "", location.pathname + (rest ? "?" + rest : "") + location.hash);
    }
  }

  Array.prototype.forEach.call(chips, function (chip) {
    chip.addEventListener("click", function (event) {
      var api = reader();
      if (!api || !api.setTaamim) return; /* let the link do it */
      event.preventDefault();
      var on = chip.getAttribute("data-taamim") === "on";
      setTaamimEverywhere(on);
      mark(on);
    });
  });

  /* What the page was asked for, handed to each frame once it is up. The address is the
     source of truth on arrival — a link to `?taamim=off` has to open that way — and the
     reader's own remembered choice takes over from there. The chips follow the Torah
     reading's frame; the haftarah's is brought into line with it when it loads. */
  var asked = /[?&]taamim=off/.test(location.search) ? false : null;
  frames.forEach(function (frame) {
    frame.addEventListener("load", function () {
      var api = readerIn(frame);
      if (!api || !api.setTaamim) return;
      if (asked === false) api.setTaamim(false);
      if (frame === framed) {
        if (api.taamim) mark(api.taamim());
      } else {
        var lead = reader();
        if (lead && lead.taamim) api.setTaamim(lead.taamim());
      }
    });
  });

  /* This week's reading, part by part (targum-internal#203). A part is read this week
     when the reader finished it after the week began: the moment is the server's, off
     the same turn that decides which portion this page shows, so nothing here keeps a
     clock. The finish times are the reader's own, in `targum:docs`, the record every
     reader writes when a section is marked finished — a year-old finish of the same
     portion is before the week began and says nothing about this one.

     `section` names one aliyah of the reading. `sections` names a whole document — the
     haftarah — which is read when every part of it is, and a one-part document keeps the
     whole-text `done` its record may carry from before sections existed. */
  function readThisWeek(record, section, sections, began) {
    if (!record || !began) return false;
    var times = record.sections && typeof record.sections === "object" ? record.sections : {};
    if (section > 0) return Number(times[String(section)] || 0) >= began;
    if (sections <= 1) return Number(times["1"] || record.done || 0) >= began;
    for (var part = 1; part <= sections; part++) {
      if (!(Number(times[String(part)] || 0) >= began)) return false;
    }
    return true;
  }

  var weekParts = document.querySelectorAll(".week-part");
  function markWeek() {
    var docs = {};
    try {
      docs = JSON.parse(localStorage.getItem("targum:docs") || "{}") || {};
    } catch (error) {
      docs = {};
    }
    Array.prototype.forEach.call(weekParts, function (part) {
      var read = readThisWeek(
        docs[part.getAttribute("data-document")],
        Number(part.getAttribute("data-section")) || 0,
        Number(part.getAttribute("data-sections")) || 0,
        Number(part.getAttribute("data-began")) || 0
      );
      if (read) part.setAttribute("data-read", "");
      else part.removeAttribute("data-read");
      var said = part.querySelector(".read");
      if (said) said.hidden = !read;
    });
  }
  if (weekParts.length) {
    markWeek();
    /* A section is finished inside a frame, which is another window of this origin, so
       its write arrives here as a storage event and the list follows it at once. */
    window.addEventListener("storage", function (event) {
      if (!event || !event.key || event.key === "targum:docs") markWeek();
    });
    Array.prototype.forEach.call(weekParts, function (part) {
      part.addEventListener("click", function () {
        var into = document.getElementById(
          part.getAttribute("target") === "haftarah" ? "haftarah" : "embed"
        );
        if (into && into.scrollIntoView) into.scrollIntoView({ block: "start" });
      });
    });
  }
  window.targumWeek = { readThisWeek: readThisWeek, mark: markWeek };

  /* The week's sheet (QA, 2026-10-05). The PDF is set when it is asked for and takes
     five or six seconds the first time, and a button that does nothing for that long is
     pressed again. So the press says it is preparing until the file arrives, and says the
     one sentence the box says when it cannot. Without this — no script, or no `fetch` —
     the form is an ordinary GET and the browser downloads the file itself. */
  var sheetForm = document.querySelector("form.sheet-choices");
  var sheetButton = sheetForm && sheetForm.querySelector('button[type="submit"]');
  if (sheetForm && sheetButton && typeof fetch === "function" && window.URL && URL.createObjectURL) {
    var sheetNote = document.createElement("p");
    sheetNote.className = "sheet-note";
    sheetNote.setAttribute("role", "status");
    sheetNote.hidden = true;
    sheetForm.appendChild(sheetNote);
    var sheetLabel = sheetButton.textContent;
    var preparing = false;

    function sheetName(response) {
      var said = response.headers.get("Content-Disposition") || "";
      var found = /filename="?([^";]+)"?/.exec(said);
      return found ? found[1] : "parasha.pdf";
    }
    function settle() {
      preparing = false;
      sheetButton.textContent = sheetLabel;
      sheetButton.removeAttribute("aria-busy");
    }

    sheetForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (preparing) return;
      preparing = true;
      sheetNote.hidden = true;
      sheetButton.textContent = t("parasha.sheet.preparing", "Preparing PDF…");
      sheetButton.setAttribute("aria-busy", "true");
      var asking = new URLSearchParams(new FormData(sheetForm)).toString();
      var address = sheetForm.getAttribute("action") + (asking ? "?" + asking : "");
      fetch(address, { credentials: "same-origin" })
        .then(function (response) {
          if (!response.ok) throw new Error(String(response.status));
          var name = sheetName(response);
          return response.blob().then(function (blob) {
            var link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = name;
            link.hidden = true;
            document.body.appendChild(link);
            link.click();
            setTimeout(function () {
              URL.revokeObjectURL(link.href);
              link.remove();
            }, 60000);
          });
        })
        .then(settle, function () {
          settle();
          sheetNote.textContent = t(
            "parasha.sheet.not-now",
            "We can't make the PDF right now. Try again in a minute."
          );
          sheetNote.hidden = false;
        });
    });
  }

  /* The portions, folded on a phone: fifty-odd rows are a long tail under the ask. */
  var sources = document.getElementById("sources");
  if (sources && window.matchMedia("(max-width: 60rem)").matches) sources.open = false;
})();
