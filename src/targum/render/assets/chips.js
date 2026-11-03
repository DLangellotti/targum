/* The chips: the things most readers ask, as buttons (targum-internal#240).
 *
 * Shared by the two pages that carry the box, the way `bring.js` is: the list comes
 * from `/chat/list`, each page hands over what a press does — a line said, a door
 * opened, the field focused — and this only draws them. "Something to read", the one
 * most readers press, never reaches the model: the page posts `/chat/suggest`, which
 * answers it from the library with no turn and no spend, and hands back a card.
 */
(function () {
  "use strict";

  var host = document.getElementById("chat-chips");

  /* Words said through the page's `TargumStrings`, looked up when a thing is said. */
  function t(key, english, fill) {
    var said = window.TargumStrings;
    return said ? said.t(key, english, fill) : english;
  }

  //: The lines a press says, by chip. Fixed, so a press is the same line every time, and
  //: in the reader's language: the line is posted as the reader's own turn, and a Russian
  //: reader's press said English for them (beta review, 2026-11-03, R9).
  function line(id) {
    if (id === "words") return t("chat.chip-line.words", "Use my new words in a short conversation.");
    if (id === "know") return t("chat.chip-line.know", "Show me what I know.");
    if (id === "news") return t("chat.chip-line.news", "Read me today's news.");
    return "";
  }

  // Draw `chips` — `[{id, line, reader?}]` — and wire each press through `on`:
  // `on.suggest()` for the first, `on.say(line)` for a line, `on.open(path)` for a
  // door, `on.stuck()` for the field. Nothing drawn where there are none.
  function draw(chips, on) {
    if (!host) return;
    host.textContent = "";
    (chips || []).forEach(function (chip) {
      var li = document.createElement("li");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "chat-ask";
      button.setAttribute("data-chip", chip.id);
      button.textContent = chip.line;
      if (chip.title) {
        // "Continue", then the title, which the stylesheet cuts short: a chip never
        // runs out of the card it stands in, whatever the text was called.
        button.textContent = "";
        button.appendChild(document.createTextNode(chip.line + " "));
        var title = document.createElement("span");
        title.className = "chip-title";
        title.setAttribute("dir", "auto");
        // The title's own language, never the page's (#472 B10).
        if (chip.language) title.setAttribute("lang", chip.language);
        if (/^(he|yi|arc)$/.test(chip.language || "")) title.setAttribute("dir", "rtl");
        title.textContent = chip.title;
        button.appendChild(title);
      }
      button.onclick = function () {
        if (chip.id === "read") return on.suggest();
        if (chip.id === "continue" && chip.reader) return on.open(chip.reader);
        if (chip.id === "stuck") return on.stuck();
        if (line(chip.id)) return on.say(line(chip.id));
      };
      li.appendChild(button);
      host.appendChild(li);
    });
    host.hidden = !(chips && chips.length);
  }

  function show(showing) {
    if (host) host.hidden = !showing || !host.children.length;
  }

  window.TargumChips = { draw: draw, show: show, line: line };
})();
