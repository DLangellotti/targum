/* targum Connect's two moving parts (targum-internal#80; as boards ConnConnect and
   ConnConnectPhone draw the page since 2026-10-09, design.md §12, "The connector's pages
   are the boards'").

   - The tabs of apps. The chosen app's steps stand, and its name goes into the heading
     and the small approval page beside the steps ("Connect Claude to targum").
   - The Copy buttons.

   With JavaScript off every app's steps stand one under another, the heading names the
   first app, and the addresses are there to select. Nothing moves on its own: the
   conversation in the hero is drawn still, and a name that changed by itself would be
   motion.
*/
(function () {
  "use strict";

  var words = window.TargumStrings || {};
  var t =
    typeof words.t === "function"
      ? words.t
      : function (key, english, fill) {
          return english.replace(/\{(\w+)\}/g, function (all, name) {
            return fill && name in fill ? fill[name] : all;
          });
        };

  /* ---- Copy ------------------------------------------------------------------------ */
  document.querySelectorAll(".cn-copy").forEach(function (button) {
    button.hidden = false;
    var label = button.querySelector("span");
    var said = label.textContent;
    button.addEventListener("click", function () {
      var text = button.getAttribute("data-copy");
      function copied() {
        button.classList.add("done");
        label.textContent = t("connect.demo.copied", "Copied");
        setTimeout(function () {
          button.classList.remove("done");
          label.textContent = said;
        }, 1600);
      }
      function refused() {
        select(button);
        // The text is selected, so the button says which keys copy it, and so does the
        // live region: a press that changed nothing said nothing (targum-internal#721).
        var keys = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "\u2318C" : "Ctrl+C";
        var press = t("connect.demo.press-to-copy", "Press {keys}", { keys: keys });
        label.textContent = press;
        announce(press);
        setTimeout(function () {
          label.textContent = said;
        }, 4000);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(copied, refused);
      } else refused();
    });
  });
  // Where the clipboard is refused, the text is selected so a press of the keys copies it.
  function select(button) {
    var code = button.parentNode.querySelector("code");
    var range = document.createRange();
    range.selectNodeContents(code);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }
  function announce(words) {
    var region = document.getElementById("cn-said");
    if (!region) return;
    region.textContent = "";
    setTimeout(function () {
      region.textContent = words;
    }, 50);
  }

  /* ---- the tabs --------------------------------------------------------------------- */
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".cn-plat"));
  var panels = document.querySelector(".cn-panels");
  var heading = document.getElementById("cn-app");
  var grant = document.getElementById("cn-grant-title");

  function choose(tab, focus) {
    tabs.forEach(function (other) {
      var on = other === tab;
      other.setAttribute("aria-selected", String(on));
      other.tabIndex = on ? 0 : -1;
      var panel = document.getElementById(other.getAttribute("aria-controls"));
      if (panel) panel.classList.toggle("on", on);
    });
    if (focus) tab.focus();
    // "Another app" names none, so the heading and the small approval page say "your own
    // app" and "this app" rather than keep the last app picked (targum-internal#721).
    var app = tab.getAttribute("data-app");
    if (heading) heading.textContent = app || heading.getAttribute("data-other") || heading.textContent;
    if (grant) {
      grant.textContent = app
        ? (grant.getAttribute("data-says") || "{client}").split("{client}").join(app)
        : grant.getAttribute("data-other") || grant.textContent;
    }
  }

  if (tabs.length && panels) {
    document.getElementById("plats").hidden = false;
    panels.classList.add("tabbed");
    tabs.forEach(function (tab, n) {
      tab.addEventListener("click", function () {
        choose(tab, false);
      });
      tab.addEventListener("keydown", function (e) {
        var go = { ArrowRight: n + 1, ArrowLeft: n - 1, Home: 0, End: tabs.length - 1 }[e.key];
        if (go == null) return;
        e.preventDefault();
        choose(tabs[(go + tabs.length) % tabs.length], true);
      });
    });
    choose(tabs[0], false);
  }
})();
