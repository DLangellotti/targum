# targum

## The brand guidelines are binding

`Design.pdf` in the private vault (`Project Planning/Targum internal docs/`) governs
every visible surface. It is not advisory and it is not a starting point to riff on.
Read it before changing anything visual; if it is not to hand, ask rather than guess.

`tests/test_brand.py` enforces the machine-checkable half — palette, radii, type scale,
focus colour, no emoji, lowercase name, no exclamation marks, no gamification, motion
always optional. **When a brand test fails, the code is wrong, not the test.** Change
the test only when the guidelines themselves change.

The half no tests can reach, and which matters as much:

- **Flat, matte, sparing.** No gradients, bevels, metallic ramps or drop shadows in the
  identity. Shadows exist only on floating overlays — the gloss card, menus, tips.
- **One accent hue, and it is rationed.** Reserved for the single primary action in a
  view and for what the reader has kept. Selection is quiet ink, never accent. The
  accent is never body text and never a large field.
- **The reader is a reader, not a player.** No mascots, no flags, no streaks, badges or
  scores. The only progress worth showing: the page gets quieter as you learn it.
- **Bilingual parity.** Hebrew and Latin share a screen at the same font-size — never
  scale Hebrew down. Parity comes from leading: 1.75 Latin, 1.95 Hebrew.
- **RTL is structural.** Logical CSS properties throughout, so every layout mirrors
  itself. Never `left`/`right`.
- **Icons are drawings, not a library.** Inline SVG, 16px viewBox, no fill, stroke
  `currentColor` at 1.4, round caps. Typed characters elsewhere: arrows per reading
  direction, × to close, A− A+ ? as themselves.
- **Voice:** literary, precise, unpatronising — a designer-engineer explaining a
  decision, never marketing. Second person for the reader's actions. Complete sentences.
  Plain about limits. The name is always lowercase, even at the start of a sentence.

## Checks

`uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q`
— all four, as CI runs them. Note `.venv/bin/*` shebangs are stale on this machine, so
`.venv/bin/python -m pytest` works where `uv run pytest` may not.

## Two things that are easy to get wrong

- **Do not bump `SCHEMA_VERSION`** to invalidate one stage. It feeds the cache key for
  every stage, so it forces paid re-translation of every text. To make a new word-level
  feature reach existing readers, change the annotator's name instead — re-annotating is
  free because Stanza runs locally.
- **Readers must fetch nothing.** No script, stylesheet, font or image from the network.
  Outbound links a reader chooses to click are the one exception, and `test_render.py`
  pins the allowlist.
