/* The front door's moving parts (targum-internal#69; rebuilt 2026-10-01).

   The box under the headline, which asks `/waitlist/look` what a pasted link is
   (targum-internal#399); the word card's vowel switch and its two marks; and the Torah
   sheet's two switches. Nothing else here is required to read the page: with JavaScript
   off the box stays hidden, every word and verse is already on the page, and the
   waitlist's form is a plain post.
*/
(function () {
  "use strict";

  // The page's words, in the page's language (targum-internal#184). English is the
  // fallback written at every call, so a key the catalogue has not filled still says
  // something rather than its own name.
  var words = window.TargumStrings || {};
  var t =
    typeof words.t === "function"
      ? words.t
      : function (key, english) {
          return english;
        };
  // Vowels and the other points, and the cantillation marks alone.
  var MARKS = /[֑-ׇֽֿׁׂׅׄ]/g;
  var TAAMIM = /[֑-ֽ֯]/g;

  /* ---- the box: say what the link is; nothing is made, nothing is spent ---- */
  var tryPart = document.getElementById("try");
  var tryForm = document.getElementById("tryForm");
  var tryInput = document.getElementById("tryInput");
  var tryOut = document.getElementById("tryOut");
  var keep = document.getElementById("keep");
  var keepLink = document.getElementById("keepLink");
  var asked = "";

  function line(cls, text) {
    var p = document.createElement("p");
    p.className = cls;
    p.textContent = text;
    return p;
  }

  function answer(said) {
    tryOut.textContent = "";
    if (!said || !said.ok) {
      keep.hidden = true;
      keepLink.value = "";
      tryOut.appendChild(line("said-err", (said && said.said) || t("landing.door.try.failed", "We couldn’t look at that just now. Try again in a moment.")));
      return;
    }
    // The server's own sentences, set as text and never as markup: the title came from
    // somebody else's page.
    var found = document.createElement("div");
    found.className = "found";
    if (said.title) found.appendChild(line("t", said.title));
    found.appendChild(line("say", said.said));
    if (said.wait) found.appendChild(line("wait", said.wait));
    tryOut.appendChild(found);
    keepLink.value = said.link || asked;
    keep.hidden = false;
  }

  function look() {
    var link = tryInput.value.trim();
    if (!link || link === asked) return;
    asked = link;
    keep.hidden = true;
    tryOut.textContent = "";
    tryOut.appendChild(line("looking", t("landing.door.try.looking", "Looking at the link…")));
    fetch(tryForm.getAttribute("action"), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: "url=" + encodeURIComponent(link),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (said) {
        if (link === asked) answer(said);
      })
      .catch(function () {
        if (link === asked) answer(null);
      });
  }

  if (tryPart && tryForm && window.fetch) {
    tryPart.hidden = false;
    tryForm.addEventListener("submit", function (event) {
      event.preventDefault();
      asked = "";
      look();
    });
    // A paste is the press: the link is all there is to say.
    tryInput.addEventListener("paste", function () {
      setTimeout(look, 0);
    });
  }

  /* ---- the word card ---- */
  var vowelLine = document.getElementById("vowelLine");
  var swVowels = document.getElementById("swVowels");
  if (vowelLine && swVowels) {
    var pointed = vowelLine.textContent;
    swVowels.addEventListener("click", function () {
      var on = swVowels.getAttribute("aria-checked") !== "true";
      swVowels.setAttribute("aria-checked", String(on));
      vowelLine.textContent = on ? pointed : pointed.replace(MARKS, "");
    });
  }
  var marks = document.querySelectorAll("[data-state]");
  Array.prototype.forEach.call(marks, function (button) {
    button.addEventListener("click", function () {
      Array.prototype.forEach.call(marks, function (other) {
        other.setAttribute("aria-pressed", String(other === button));
      });
    });
  });
  // A tapped word in the example above draws the eye to its card.
  var wcard = document.getElementById("wcard");
  Array.prototype.forEach.call(document.querySelectorAll("a.w"), function (word) {
    word.addEventListener("click", function () {
      if (!wcard) return;
      wcard.classList.add("flash");
      setTimeout(function () {
        wcard.classList.remove("flash");
      }, 1400);
    });
  });

  /* ---- the Torah sheet ---- */
  var swChant = document.getElementById("swChant");
  var swOnk = document.getElementById("swOnk");
  var chanted = document.querySelectorAll("[data-chant]");
  Array.prototype.forEach.call(chanted, function (verse) {
    verse.setAttribute("data-chant", verse.textContent);
  });
  function sheet() {
    var chant = swChant.getAttribute("aria-checked") === "true";
    var onkelos = swOnk.getAttribute("aria-checked") === "true";
    Array.prototype.forEach.call(chanted, function (verse) {
      var full = verse.getAttribute("data-chant");
      verse.textContent = chant ? full : full.replace(TAAMIM, "");
    });
    Array.prototype.forEach.call(document.querySelectorAll(".v-arc"), function (aramaic) {
      aramaic.hidden = !onkelos;
    });
  }
  [swChant, swOnk].forEach(function (sw) {
    if (!sw) return;
    sw.addEventListener("click", function () {
      sw.setAttribute("aria-checked", String(sw.getAttribute("aria-checked") !== "true"));
      sheet();
    });
  });
})();
