# targum for Chrome

One press sends the page you're on to targum's Add. Right-click sends a link or the
text you selected instead. Add shows what it found and what it uses; nothing is used
until you press Confirm there.

It opens a tab on targum.page and does nothing else: it fetches nothing, reads nothing
of the page beyond its address and your selection, and asks for two permissions —
`activeTab`, for the address of the tab you pressed it on, and `contextMenus`, for the
right-click rows. design.md §12, "Share > targum lands in Add" (2026-10-27), is the
decision; `tests/test_share_target.py` holds the extension to it.

## Trying it

`chrome://extensions` → Developer mode → Load unpacked → this folder.

## Publishing

Zip the folder's contents (not the folder) and upload the zip to the Chrome Web Store
developer dashboard. Raise `version` in `manifest.json` first.
