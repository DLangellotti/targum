# targum

## The brand guidelines are binding

`Design updated.pdf` in the private vault (`Project Planning/Targum internal docs/`)
governs every visible surface. It replaced `Design.pdf` on Aug 24 2026 and the older
file is gone; a reference to `Design.pdf` anywhere is stale. It is not advisory and it is not a starting point to riff on.
Read it before changing anything visual; if it is not to hand, ask rather than guess.

`tests/test_brand.py` enforces the machine-checkable half — palette, radii, type scale,
focus colour, no emoji, lowercase name, no exclamation marks, no gamification, motion
always optional. **When a brand test fails, the code is wrong, not the test.** Change
the test only when the guidelines themselves change.

The half no tests can reach, and which matters as much:

- **The identity is flat forever; the UI may shine, measured.** No gradient, bevel or
  metallic ramp on the mark, lockup or wordmark, ever. Interactive and celebratory UI
  elements may carry the §9 gloss recipe: `--gloss` (≤14%) on primary buttons and
  progress fills, `--gloss-strong` (≤22%) on celebration chips, `--lift` on hover. One
  sheen per element, light on glass and never metal, never on a resting text surface.
- **One accent hue, and it is rationed.** Reserved for the single primary action in a
  view and for what the reader has kept. Selection is quiet ink, never accent. The
  accent is never body text and never a large field.
- **Functional colour (§4) is for UI features, never the identity.** `--leaf` progress
  and "known", `--clay` cost, errors and destructive actions, `--iris` phrases and
  discovery. One hue per moment, flat always. The bright set (`--sun`, `--leaf-bright`,
  `--iris-bright`, `--rose`) is for peak moments on ink panels; measured, `--sun` and
  `--leaf-bright` do not reach 3:1 on paper, so those two are ink-panel only.
- **Contrast is the engagement mechanism (§9).** Text the reader came for is full ink;
  muted is for genuinely secondary lines only — translations at rest, captions,
  metadata — and never for primary content. The page is near-white, not beige. One
  raised layer per view; if a card needs a card, use a hairline. A beige button on a
  beige card is forbidden: every tappable element carries ink or a hue. Numbers at
  display sizes are ink or leaf, never gold. Roughly 80% paper and ink, 15% structural
  neutrals, 5% hue, and the hue goes where the reader acts or achieved something.
- **Ink inversion is the wake-up move.** One block per screen may invert to the dark
  surface. Spent on one block it is striking; spent on three it is a dark theme.
- **The reader is a reader, not a player — engagement is welcome, arcade is not.**
  Streaks, goals and milestones are a ledger: real counts in serif tabular numbers,
  leaf for achievement, iris for novelty, celebration in type rather than motion. No
  invented currency — count real things ("12 days reading", "500 words known"), never
  XP, points or levels. Missed streak days are quiet, never red. Milestones brag the
  brand's way: "the page is 31% quieter than when you began."
- **Errors are `--clay`** (#b4553f on paper, #e0937d on ink), which the guidelines name
  directly. Worth knowing while reading the code: clay sits close to the accent under
  protanopia, so an error must never rest on colour alone — the wording carries it too,
  which the voice rules already require.
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
