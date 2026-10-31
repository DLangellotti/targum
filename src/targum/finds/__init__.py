"""Things to read that targum found on the web (targum-internal#617, slice 1 is #619).

Plan: `docs/web-discovery-2026-10-31.md` in targum-internal. design.md §12, "A web find is
a pasted link targum found", 2026-10-31.

- `score`: the cheap surface-form → lemma scorer, built from the public shelf's own
  annotations, and its calibration against DICTA.
- `pool`: the shared candidate pool in `targum.db`, with an expiry. Metadata and a bag of
  lemma counts per find, never the text.
- `screen` and `robots`: what keeps a find off Home, and what keeps targum's own fetches
  polite.
- `news`: the hourly round over the feeds targum already follows.
- `provider`: the pool scored for one reader, as candidates for Read next.

Nothing here spends a reader's credits. Opening a find is a pasted link's press
(`serve.Handler._open_find`), through `Library.press` and so `Library.claim`, and what
it builds is the reader's own import.
"""
