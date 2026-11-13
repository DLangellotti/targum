/* A speaker's words on /credits, fetched when their row is opened (targum-internal#484,
 * step 2).
 *
 * The page drew every speaker's every word, each linked to its file on Commons: 3,546
 * links and 863 kB of markup in front of anything else on a phone. Now a row holds a link
 * to the page with that row drawn, which is what a browser without this script follows,
 * and this swaps the link for the list the first time the row is opened. The list comes
 * from `/credits/words` on this origin; nothing is asked of any other site. A fetch that
 * fails leaves the link where it was, so every file's credit is still a press away.
 */
(function () {
  var rows = document.querySelectorAll("details[data-words]");
  function draw(row, words) {
    var list = document.createElement("ul");
    list.setAttribute("lang", words.language || "he");
    list.setAttribute("dir", "rtl");
    words.words.forEach(function (one) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href = one.page;
      link.title = one.attribution;
      link.textContent = one.word;
      item.appendChild(link);
      list.appendChild(item);
    });
    var stand = row.querySelector(".words-link");
    if (stand) row.replaceChild(list, stand);
  }
  function open(row) {
    if (!row.open || row.getAttribute("data-asked")) return;
    if (!row.querySelector(".words-link")) return;
    row.setAttribute("data-asked", "1");
    fetch(row.getAttribute("data-words"), { credentials: "same-origin" })
      .then(function (answer) {
        if (!answer.ok) throw new Error(String(answer.status));
        return answer.json();
      })
      .then(function (words) {
        draw(row, words);
      })
      .catch(function () {
        row.removeAttribute("data-asked");
      });
  }
  for (var n = 0; n < rows.length; n++) {
    rows[n].addEventListener(
      "toggle",
      (function (row) {
        return function () {
          open(row);
        };
      })(rows[n])
    );
  }
})();
