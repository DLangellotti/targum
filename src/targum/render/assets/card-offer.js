// The offer card (design.md §12, "A third card, the offer", 2026-10-09; board ConnCards).
//
// A host that draws MCP Apps puts this page in a sandboxed frame beside a `quote_set` or
// a `quote_subscription` result. How it talks to the host is `card-bridge.js`, inlined
// before this file and shared with the other two cards.
//
// What the card may do, and all it may do:
//   - draw what was offered, in the host's theme: a set's name, each text with its length
//     and its credits, and the total; or a subscription's name, what it is, how often
//     something new comes out and what a new one usually uses;
//   - ask the host to open the one door, targum's own page where the reader confirms it —
//     the set's press page, or the subscription's confirm page where the cap is chosen.
//
// It asks for no tool and confirms nothing: the press is the reader's, on targum's page
// (§12, "A card never presses"). `test_cards.py` holds that.

(function () {
  "use strict";

  var list = document.getElementById("offer");
  var none = document.getElementById("none");
  var one = document.getElementById("one");
  var item = document.getElementById("item");
  var HEBREW = /[֐-׿]/;
  var bridge = null;
  var shown = [];

  function said(name, fill) {
    var text = list.getAttribute("data-" + name) || "";
    Object.keys(fill || {}).forEach(function (key) {
      text = text.split("{" + key + "}").join(String(fill[key]));
    });
    return text;
  }

  // A counted label, in the form the reader's language takes for `n`.
  function counted(name, n) {
    var forms = {};
    try {
      forms = JSON.parse(list.getAttribute("data-" + name) || "{}");
    } catch (error) {
      forms = {};
    }
    var form = "other";
    try {
      form = new Intl.PluralRules(document.documentElement.lang || "en").select(n);
    } catch (error) {
      form = n === 1 ? "one" : "other";
    }
    var text = forms[form] || forms.other || forms.one || "";
    return text.split("{n}").join(String(n));
  }

  function titled(node, text) {
    node.textContent = text;
    if (HEBREW.test(text)) {
      node.setAttribute("dir", "rtl");
      node.setAttribute("lang", "he");
    }
  }

  function door(card, url, words) {
    var link = card.querySelector(".card-door");
    if (!url) return;
    link.setAttribute("href", url);
    link.textContent = words;
    link.hidden = false;
    link.addEventListener("click", function (event) {
      event.preventDefault();
      if (bridge) bridge.open(url);
    });
  }

  function drawSet(rows) {
    var set = rows.set || {};
    var card = one.content.firstElementChild.cloneNode(true);
    card.querySelector(".card-label").textContent = said("kind-set");
    titled(card.querySelector(".card-title"), String(set.name || ""));
    var items = card.querySelector(".card-items");
    (set.items || []).forEach(function (text) {
      var row = item.content.firstElementChild.cloneNode(true);
      titled(row.querySelector(".card-item-title"), String(text.title || ""));
      var facts = [];
      var seconds = Number(text.seconds) || 0;
      if (seconds > 0) facts.push(said("minutes", { n: Math.max(1, Math.round(seconds / 60)) }));
      if (Number(text.credits) > 0) facts.push(counted("credits", Number(text.credits)));
      row.querySelector(".card-item-facts").textContent = facts.join(" · ");
      items.appendChild(row);
    });
    items.hidden = !items.children.length;
    if (Number(set.credits) > 0) {
      var sum = card.querySelector(".card-sum");
      sum.textContent = counted("total", Number(set.credits));
      sum.hidden = false;
    }
    door(card, String(rows.open || ""), said("confirm"));
    return card;
  }

  function drawSubscription(rows) {
    var offer = rows.subscription || {};
    var card = one.content.firstElementChild.cloneNode(true);
    card.querySelector(".card-label").textContent = said("kind-" + String(offer.kind || "series"));
    titled(card.querySelector(".card-title"), String(offer.name || ""));
    var facts = [];
    var week = Math.round(Number(offer.per_week) || 0);
    if (week > 0) facts.push(counted("week", week));
    if (offer.builds) {
      if (Number(offer.credits_each) > 0) facts.push(counted("each", Number(offer.credits_each)));
      facts.push(said("cap"));
    } else {
      facts.push(said("free"));
    }
    var line = card.querySelector(".card-facts");
    line.textContent = facts.join(" · ");
    line.hidden = !facts.length;
    door(card, String(rows.open || ""), said("confirm"));
    return card;
  }

  function drawHeld(rows) {
    var card = one.content.firstElementChild.cloneNode(true);
    card.querySelector(".card-title").textContent = said("subscribed");
    door(card, String(rows.open || ""), said("manage"));
    return card;
  }

  function show(result) {
    var rows = TargumCard.rowsOf(result);
    if (!rows) return;
    shown.forEach(function (card) {
      card.remove();
    });
    shown = [];
    if (rows.error) {
      none.textContent = String(rows.error);
      none.hidden = false;
      return;
    }
    none.hidden = true;
    var card = rows.set ? drawSet(rows) : rows.subscription ? drawSubscription(rows) : rows.subscribed ? drawHeld(rows) : null;
    if (!card) return;
    list.appendChild(card);
    shown.push(card);
  }

  bridge = TargumCard.start({ result: show }, list);
})();
