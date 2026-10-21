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
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(copied, function () {
          select(button);
        });
      } else select(button);
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
    // "Another app" names none: the heading keeps the last app it named.
    var app = tab.getAttribute("data-app");
    if (app && heading) heading.textContent = app;
    if (app && grant) {
      grant.textContent = (grant.getAttribute("data-says") || "{client}").split("{client}").join(app);
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
