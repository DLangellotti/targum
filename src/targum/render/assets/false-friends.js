/* A French word's false friend, on its card (targum-internal#267; `annotate/false_friends.py`).
 *
 * "false friend: not *actually* — currently". The page carries, beside its lemmas, what
 * each looks like in English and what it means (`extensions.friends`), and the line is
 * added to the card a tap opens, only while the text is read into English: the look-alike
 * is an English word, and a reader reading into Russian was never going to take it for one.
 * In English only, for the same reason, and so through no catalogue.
 *
 * Carried only by a page written with `TARGUM_FALSE_FRIENDS` on, which is off until a
 * person has read the list. A script of its own rather than lines in `reader.js`, so a page
 * written with the switch off is byte for byte what it was.
 */
(function () {
  "use strict";

  var card = document.getElementById("gloss-card");
  var data = document.getElementById("targum-data");
  if (!card || !data) return;
  var friends;
  try {
    friends = (JSON.parse(data.textContent).extensions || {}).friends || [];
  } catch (e) {
    return;
  }
  if (!friends.length) return;

  // The language the text is being read into: the translation column's own, which the
  // picker changes.
  function readInto() {
    var cell = document.querySelector(".pair .tr[lang]");
    return cell ? String(cell.getAttribute("lang")).split("-")[0].toLowerCase() : "";
  }

  function add() {
    if (card.querySelector(".false-friend")) return;
    var word = document.querySelector(".w.looked-up");
    if (!word || readInto() !== "en") return;
    var friend = friends[parseInt(word.getAttribute("data-lemma"), 10)];
    if (!friend || friend.length !== 2) return;
    var line = document.createElement("span");
    // Set as the register line is: the same kind of fact about the word, and a French
    // card has no register line of its own.
    line.className = "register false-friend";
    line.appendChild(document.createTextNode("false friend: not "));
    var looks = document.createElement("i");
    looks.setAttribute("lang", "en");
    looks.textContent = friend[0];
    line.appendChild(looks);
    line.appendChild(document.createTextNode(" — " + friend[1]));
    // Above the scale, where the card's facts about the word end.
    var before = card.querySelector(".vocab-editor");
    if (before && before.parentNode === card) card.insertBefore(line, before);
    else card.appendChild(line);
  }

  // The card is drawn afresh on every tap, and again when a meaning arrives.
  new MutationObserver(add).observe(card, { childList: true });
})();
