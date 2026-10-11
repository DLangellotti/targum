# Decisions needed — QA pass of 2026-10-11

Only the items that need you. Each has a recommendation; none blocks the fixes already made.

**D1 · Merge and deploy the 20 fixes.**
The branch `qa-audit-2026-10-11` carries them as one commit each, with regression tests.
Fixes to readers (QA-005) reach readers already on the shelf only through the rebuild that
`deploy.sh` runs.
*Recommendation:* merge when CI is green, and deploy in the usual way. There is no schema
change and no annotator rename, so the deploy needs no long rebuild.

**D2 · A signed-out deep link says "COMING SOON".**
An expired session or a bookmarked `/you`, `/add` or reader address shows the holding page.
That page tells a returning reader the product does not exist yet, and nothing brings them
back to the page they wanted after signing in. It is the worst moment of the "come back
later and resume" journey on a phone, where sessions are most often lost.
*Recommendation:* for page routes, redirect a signed-out request to
`/account/signin?next=<same-origin path>`. Carry `next` through the mailed link, and land
there after the press. Accept only same-origin paths, so it cannot become an open redirect.

**D3 · The desk's focus ring is gold on a ground it cannot be seen on.**
design.md §4 records the gold `#b8935e` at 2.31:1 on `#ece7de`. That is why the public
pages moved to teal on 2026-10-02. Every desk page stands on the same `#ece7de` (§13) and
still uses gold, so keyboard focus fails WCAG 1.4.11 across the signed-in product.
*Recommendation:* teal `#1f6f6b` inside the product too, the same reasoning as §12,
2026-10-02. It is a design.md change first, then `tokens.css` and `test_brand.py`.

**D4 · Offline fallback when `/you/saved` was never opened (READER-03).**
Offline, any unsaved page shows the browser's own error page unless the reader once opened
"Saved on this device" while online. The obvious fix is to keep that page when the first
text is saved. It conflicts with §12 "A worker keeps what the reader saved, and fetches
nothing else", and with the eviction tests built on that rule.
*Recommendation:* treat the first save as consent to keep the Saved page too. Write a §12
line, keep it outside the eviction count, and update the five offline tests to match.

**D5 · One figure for "how much of this you know" (READER-06).**
The reader counts words assumed known from the level the reader declared (§12, "An advanced
reader is not asked about the commonest words"). The contents page and the Library count
only words marked known. So one text says 25% in the reader and 0% on its contents page.
*Recommendation:* one rule everywhere. Count assumed-known words wherever a share is shown,
computed on the server once and handed to the page.

**D6 · "ignore" on Your Words (DESK-11).**
"ignore" sits next to "known", removes the word at once, has no undo, and leaves no view in
which to find the word again.
*Recommendation:* an Undo for a few seconds, and an "Ignored" filter.

**D7 · The drawer left open covers the next page on a phone.**
design.md §12, "A drawer left open comes back undimmed", marks it as a default for you to
overrule. On a phone it returns as a full-screen sheet over the page the reader just chose
to open, for example after "Open your targums" in the drawer.
*Recommendation:* overrule on phones only. Close it on navigation there, and keep it at a
desk.

**D8 · Pressing a word's current stage clears it (reader).**
A second tap on the stage a word already has removes the stage, so an accidental double
tap un-marks a word without a sign.
*Recommendation:* pressing the current stage does nothing. Leaving a stage happens through
another stage or "ignore".

**D9 · "A stretch" holds every text never measured.**
On the laptop's library that is 724 texts under a line that says "You know 75–90% of their
words", above cards that say "Not measured yet".
*Recommendation:* give unmeasured texts their own shelf, or rank them after the measured
ones, and never under a percentage.
