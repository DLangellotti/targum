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
      handle.textContent = "Full screen";
    }
    handle.addEventListener("click", function () {
      pinned = !pinned;
      embed.classList.toggle("pinned", pinned);
      handle.setAttribute("aria-expanded", pinned ? "true" : "false");
      handle.textContent = pinned ? "Close" : "Full screen";
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
      var url = location.pathname + (on ? "" : "?taamim=off");
      history.replaceState(null, "", url);
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

  /* The portions, folded on a phone: fifty-odd rows are a long tail under the ask. */
  var sources = document.getElementById("sources");
  if (sources && window.matchMedia("(max-width: 60rem)").matches) sources.open = false;
})();
