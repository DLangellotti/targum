/* targum's extension: one press sends what you are looking at to Add (design.md §12,
 * "Share > targum lands in Add", 2026-10-27).
 *
 * It opens a tab and nothing else. It fetches nothing, reads nothing of the page but the
 * address of the tab or the link pressed and the text the reader selected, holds no key
 * and spends nothing: Add prices what it is given, and the build waits for Confirm there.
 *
 * A link goes in `?source=`, the door the weekly's "Read the whole thing" uses, so it
 * survives a sign-in on the way. Selected text goes after the `#`, which a browser never
 * sends, so the words reach targum only when the reader presses Upload.
 */

"use strict";

var TARGUM = "https://targum.page";

function isLink(address) {
  return /^https?:\/\//i.test(address || "");
}

function open(where) {
  chrome.tabs.create({ url: TARGUM + where });
}

function sendLink(address) {
  // A page of targum's own, or a browser's (`chrome://`), is not a thing to read.
  if (!isLink(address) || address.indexOf(TARGUM + "/") === 0) {
    open("/add");
    return;
  }
  open("/add?source=" + encodeURIComponent(address));
}

function sendText(text) {
  var said = (text || "").trim();
  open(said ? "/add#shared=" + encodeURIComponent(said) : "/add");
}

chrome.action.onClicked.addListener(function (tab) {
  sendLink(tab && tab.url);
});

chrome.runtime.onInstalled.addListener(function () {
  chrome.contextMenus.removeAll(function () {
    chrome.contextMenus.create({
      id: "page",
      title: chrome.i18n.getMessage("page"),
      contexts: ["page"],
    });
    chrome.contextMenus.create({
      id: "link",
      title: chrome.i18n.getMessage("link"),
      contexts: ["link"],
    });
    chrome.contextMenus.create({
      id: "selection",
      title: chrome.i18n.getMessage("selection"),
      contexts: ["selection"],
    });
  });
});

chrome.contextMenus.onClicked.addListener(function (info, tab) {
  if (info.menuItemId === "link") return sendLink(info.linkUrl);
  if (info.menuItemId === "selection") return sendText(info.selectionText);
  sendLink(info.pageUrl || (tab && tab.url));
});
