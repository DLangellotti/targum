/* A series' own page (design.md §12, "A series is one page of the desk, for everyone",
   2026-10-09). Everything on it works without this: every row is a link. What this adds
   is the week's sheet said while it is made (QA, 2026-10-05): the PDF is set when it is
   asked for and takes five or six seconds the first time, and a press that does nothing
   for that long is pressed again. So the press says it is preparing until the file
   arrives, and says the one sentence the box says when it cannot. Without a script, or
   without `fetch`, the link is an ordinary one and the browser downloads the file. */
(function () {
  "use strict";

  function t(key, english) {
    var said = window.TargumStrings;
    return said ? said.t(key, english) : english;
  }

  var press = document.querySelector("a.series-pdf");
  if (!press || typeof fetch !== "function" || !window.URL || !URL.createObjectURL) return;
  var note = document.createElement("p");
  note.className = "series-pdf-note";
  note.setAttribute("role", "status");
  note.hidden = true;
  var row = press.closest(".series-acts") || press.parentNode;
  row.appendChild(note);
  var label = press.getAttribute("aria-label") || "";
  var preparing = false;

  function nameOf(response) {
    var said = response.headers.get("Content-Disposition") || "";
    var found = /filename="?([^";]+)"?/.exec(said);
    return found ? found[1] : "parasha.pdf";
  }
  function settle() {
    preparing = false;
    press.setAttribute("aria-label", label);
    press.removeAttribute("aria-busy");
    note.hidden = true;
  }

  press.addEventListener("click", function (event) {
    event.preventDefault();
    if (preparing) return;
    preparing = true;
    var busy = t("parasha.sheet.preparing", "Preparing PDF…");
    press.setAttribute("aria-busy", "true");
    press.setAttribute("aria-label", busy);
    note.textContent = busy;
    note.hidden = false;
    fetch(press.getAttribute("href"), { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error(String(response.status));
        var name = nameOf(response);
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
        note.textContent = t("parasha.sheet.not-now", "We can't make the PDF right now. Try again in a minute.");
        note.hidden = false;
      });
  });
})();
