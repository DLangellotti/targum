/* The back office's tabs (design.md §12, 2026-09-28).

   One page, four panels, switched in place: the open one is named in the address, so a
   reload and a form's answer (`serve.py` redirects to `#people`, `#shelf`,
   `#operations`) land where they left. Without this file the tabs are links to their
   panels and every panel shows. Arrow keys move along the row, as a tab list's do. */
(function () {
  // The tabs (2026-09-28): one panel at a time, the open one named in the address.
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".bo-tabs a"));
  var panels = Array.prototype.slice.call(document.querySelectorAll(".tab-panel"));
  if (!tabs.length || !panels.length) return;
  // The address says `#shelf` and the panel is `tab-shelf`: an id the address named
  // would be scrolled to by the browser, past the header and the tabs.
  function show(name) {
    var id = "tab-" + name;
    if (!panels.some(function (panel) { return panel.id === id; })) id = panels[0].id;
    panels.forEach(function (panel) { panel.hidden = panel.id !== id; });
    tabs.forEach(function (tab) {
      var on = "tab-" + tab.hash.slice(1) === id;
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.tabIndex = on ? 0 : -1;
    });
  }
  tabs.forEach(function (tab, at) {
    tab.addEventListener("click", function (event) {
      event.preventDefault();
      history.replaceState(null, "", tab.hash);
      show(tab.hash.slice(1));
    });
    tab.addEventListener("keydown", function (event) {
      var step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      var next = tabs[(at + step + tabs.length) % tabs.length];
      next.focus();
      next.click();
    });
  });
  function arrive() { show(location.hash.slice(1)); }
  window.addEventListener("hashchange", arrive);
  arrive();
})();
